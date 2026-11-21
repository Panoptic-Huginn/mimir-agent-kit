#!/usr/bin/env python3
"""Self-bootstrapping, SHA-256-verified native launcher for ``github-mcp-server``.

Eliminates the Docker daemon requirement on macOS and Linux while preserving
immutable supply-chain digest pinning and zero-plaintext OS-keyring authentication:

1. Resolves the persistent cache directory from ``--cache-dir`` (``${PLUGIN_DATA}``
   in Antigravity 2.31+) or the OS user cache directory.
2. Downloads the official precompiled ``github/github-mcp-server`` release archive
   for the host ``(OS, architecture)`` once, verifies its exact 64-character
   SHA-256 digest in memory before extraction, and atomically installs the static
   binary under ``<cache-dir>/github-mcp-server/v<version>/<os>_<arch>/``.
3. Reads the active multi-owner OAuth token from ``gh auth token --hostname <host>``
   (or non-placeholder environment tokens in headless CI/container runtimes) and
   replaces the current process via ``os.execve`` with ``github-mcp-server stdio``.
"""

import argparse
import fcntl
import hashlib
import io
import os
import platform
import re
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import] - invokes resolved gh CLI binary with static argv
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Final


if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


GITHUB_MCP_SERVER_VERSION: Final[str] = "2.2.0"
GITHUB_RELEASE_BASE_URL: Final[str] = (
    "https://github.com/github/github-mcp-server/releases/download"
)
DEFAULT_GITHUB_HOSTNAME: Final[str] = "github.com"
BINARY_NAME: Final[str] = "github-mcp-server"
DISABLE_FORM_DEFERRAL_FEATURE: Final[str] = "mcp_apps_disable_form_deferral"

EXTRA_PATH_DIRS: Final[tuple[str, ...]] = (
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/home/linuxbrew/.linuxbrew/bin",
    "/snap/bin",
)
# Retained as an alias of EXTRA_PATH_DIRS for backward compatibility with callers and tests.
MACOS_EXTRA_PATH_DIRS: Final[tuple[str, ...]] = EXTRA_PATH_DIRS

_TOKEN_ENV_KEYS: Final[tuple[str, ...]] = (
    "GITHUB_PERSONAL_ACCESS_TOKEN",
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GH_ENTERPRISE_TOKEN",
    "GITHUB_ENTERPRISE_TOKEN",
)
_GITHUB_COM_ENV_TOKEN_KEYS: Final[tuple[str, ...]] = ("GH_TOKEN", "GITHUB_TOKEN")
_ENTERPRISE_ENV_TOKEN_KEYS: Final[tuple[str, ...]] = (
    "GH_ENTERPRISE_TOKEN",
    "GITHUB_ENTERPRISE_TOKEN",
)

_UNEXPANDED_PLACEHOLDER_RE: Final[re.Pattern[str]] = re.compile(
    r"^\$(?:\{[^{}]+\}|[A-Za-z_][A-Za-z0-9_]*)$"
)
_EMBEDDED_PLACEHOLDER_RE: Final[re.Pattern[str]] = re.compile(
    r"\$(?:\{[^{}]+\}|[A-Za-z_][A-Za-z0-9_]*)"
)
_TOKEN_REDACTION_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|v1\.[0-9a-fA-F]{30,})\b"
)
_AUTH_HEADER_REDACTION_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)(authorization\s*:\s*(?:bearer|token)\s+)[^\s\"';,]+"
)
_URL_CREDENTIAL_REDACTION_RE: Final[re.Pattern[str]] = re.compile(
    r"(://[^/\s:@]+:)[^/\s@]+(@)"
)

# Official SHA-256 archive digests from github-mcp-server_2.2.0_checksums.txt.
PLATFORM_ARCHIVE_SPECS: Final[dict[tuple[str, str], tuple[str, str]]] = {
    ("Linux", "x86_64"): (
        "github-mcp-server_Linux_x86_64.tar.gz",
        "157c5664b273e5070126d414f88cbab765630acde588f75dafdf9998c2235c51",
    ),
    ("Linux", "aarch64"): (
        "github-mcp-server_Linux_arm64.tar.gz",
        "d21e4fca8603b59d99380f1c332aaea36d73033d52b389867adf2124ee150983",
    ),
    ("Darwin", "arm64"): (
        "github-mcp-server_Darwin_arm64.tar.gz",
        "5e46b05b87989d23267f0a69ee60a3acd1de51a72512ee5fcc2786ca60c54a6a",
    ),
    ("Darwin", "x86_64"): (
        "github-mcp-server_Darwin_x86_64.tar.gz",
        "a42e667b99915cf368b92aa419fd2f753549ea7133cb3572a3e7f3e2d4a8675b",
    ),
}


class LauncherError(RuntimeError):
    """Raised when platform resolution, binary verification, or keyring auth fails."""


def _safe_home_dir(env: Mapping[str, str] | None = None) -> Path | None:
    """Resolve the user home directory without crashing in UID-unmapped containers.

    Args:
        env: Optional environment mapping checked for ``HOME`` before ``Path.home()``.

    Returns:
        Resolved ``Path`` to the user home directory, or ``None`` if unavailable.
    """
    if env is not None:
        home_raw = env.get("HOME", "").strip()
        if home_raw and not _EMBEDDED_PLACEHOLDER_RE.search(home_raw):
            return Path(home_raw)
    try:
        return Path.home()
    except RuntimeError:
        return None


def _safe_expanduser(raw_path: str, env: Mapping[str, str]) -> Path | None:
    """Expand a leading ``~`` using ``env['HOME']`` or ``Path.home()`` safely.

    Args:
        raw_path: Raw filesystem path string.
        env: Active environment mapping.

    Returns:
        Expanded ``Path``, or ``None`` if ``~`` expansion fails in a headless runtime.
    """
    if raw_path == "~" or raw_path.startswith("~/"):
        home_dir = _safe_home_dir(env)
        if home_dir is None:
            return None
        suffix = raw_path[2:] if raw_path.startswith("~/") else ""
        return home_dir / suffix if suffix else home_dir
    try:
        return Path(raw_path).expanduser()
    except RuntimeError:
        return None


def normalize_platform(
    system_name: str | None = None, machine_name: str | None = None
) -> tuple[str, str]:
    """Normalize OS and CPU architecture identifiers to canonical release keys.

    Args:
        system_name: OS name (defaults to ``platform.system()``).
        machine_name: CPU architecture (defaults to ``platform.machine()``).

    Returns:
        Canonical ``(system, machine)`` tuple matching ``PLATFORM_ARCHIVE_SPECS``.

    Raises:
        LauncherError: If the OS or CPU architecture is unsupported.
    """
    raw_sys = (system_name if system_name is not None else platform.system()).strip()
    raw_arch = (
        (machine_name if machine_name is not None else platform.machine())
        .strip()
        .lower()
    )

    if raw_arch in {"x86_64", "amd64"}:
        norm_arch = "x86_64"
    elif raw_arch in {"aarch64", "arm64"}:
        norm_arch = "arm64" if raw_sys == "Darwin" else "aarch64"
    else:
        raise LauncherError(
            f"Unsupported CPU architecture {raw_arch!r} on {raw_sys!r}."
        )

    key = (raw_sys, norm_arch)
    if key not in PLATFORM_ARCHIVE_SPECS:
        raise LauncherError(
            f"Unsupported platform {raw_sys}/{norm_arch} for github-mcp-server."
        )
    return key


def resolve_cache_root(
    cache_dir: Path | str | None = None,
    system_name: str | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Resolve the writable root directory for cached ``github-mcp-server`` binaries.

    Uses ``cache_dir`` (typically ``${PLUGIN_DATA}``) when provided and expanded;
    otherwise falls back to ``~/Library/Caches/mimir-agent-kit`` on macOS,
    ``${XDG_CACHE_HOME:-~/.cache}/mimir-agent-kit`` on Linux, or the system
    temporary directory when no home directory can be determined.

    Args:
        cache_dir: Optional directory path or unexpanded placeholder.
        system_name: Optional OS override for deterministic testing.
        env: Optional environment mapping (defaults to ``os.environ``).

    Returns:
        Resolved ``Path`` to the root cache directory.
    """
    active_env: Mapping[str, str] = os.environ if env is None else env
    candidate = (
        str(cache_dir).strip()
        if cache_dir is not None
        else active_env.get("PLUGIN_DATA", "").strip()
    )
    if candidate and not _EMBEDDED_PLACEHOLDER_RE.search(candidate):
        expanded = _safe_expanduser(candidate, active_env)
        if expanded is not None:
            return expanded.resolve()

    home_dir = _safe_home_dir(active_env)
    active_sys = system_name if system_name is not None else platform.system()
    if active_sys == "Darwin":
        if home_dir is not None:
            return (home_dir / "Library" / "Caches" / "mimir-agent-kit").resolve()
        return (Path(tempfile.gettempdir()) / "mimir-agent-kit").resolve()

    xdg_cache = active_env.get("XDG_CACHE_HOME", "").strip()
    base: Path | None = None
    if xdg_cache and not _EMBEDDED_PLACEHOLDER_RE.search(xdg_cache):
        base = _safe_expanduser(xdg_cache, active_env)
    if base is None:
        base = (
            (home_dir / ".cache")
            if home_dir is not None
            else Path(tempfile.gettempdir())
        )
    return (base / "mimir-agent-kit").resolve()


def normalize_github_host(
    raw_host: str | None = None, env: Mapping[str, str] | None = None
) -> tuple[str, str | None]:
    """Normalize a GitHub host CLI flag or ``GITHUB_HOST`` URL into CLI and API forms.

    ``gh auth token --hostname`` requires a bare hostname without a URL scheme,
    whereas ``github-mcp-server`` requires ``GITHUB_HOST`` / ``--gh-host`` to carry
    an ``http`` or ``https`` scheme.

    Args:
        raw_host: Optional ``--hostname`` value or URL.
        env: Optional environment mapping checked for ``GITHUB_HOST`` when ``raw_host`` is unset.

    Returns:
        Tuple of ``(bare_hostname, api_host_url_or_none)`` where ``api_host_url_or_none``
        is ``None`` for standard ``github.com`` and ``scheme://netloc`` otherwise.

    Raises:
        LauncherError: If the supplied host starts with ``-``, contains whitespace, or uses an invalid URL scheme.
    """
    active_env: Mapping[str, str] = os.environ if env is None else env
    candidate = (raw_host or "").strip()
    if not candidate or _EMBEDDED_PLACEHOLDER_RE.search(candidate):
        candidate = active_env.get("GITHUB_HOST", "").strip()
    if not candidate or _EMBEDDED_PLACEHOLDER_RE.search(candidate):
        return (DEFAULT_GITHUB_HOSTNAME, None)

    if candidate.startswith("-") or any(ch.isspace() for ch in candidate):
        raise LauncherError(f"Invalid GitHub hostname: {candidate!r}")

    if "://" in candidate:
        parsed = urllib.parse.urlsplit(candidate)
        scheme = parsed.scheme.lower()
        if (
            scheme not in {"https", "http"}
            or not parsed.hostname
            or parsed.hostname.startswith("-")
        ):
            raise LauncherError(f"Invalid GitHub host URL: {candidate!r}")
        bare_host = parsed.hostname.lower()
        if (
            bare_host == DEFAULT_GITHUB_HOSTNAME
            and scheme == "https"
            and parsed.port is None
        ):
            return (DEFAULT_GITHUB_HOSTNAME, None)
        return (bare_host, f"{scheme}://{parsed.netloc}")

    parsed = urllib.parse.urlsplit(f"https://{candidate}")
    if (
        not parsed.hostname
        or parsed.hostname.startswith("-")
        or parsed.path not in {"", "/"}
    ):
        raise LauncherError(f"Invalid GitHub hostname: {candidate!r}")
    bare_host = parsed.hostname.lower()
    if bare_host == DEFAULT_GITHUB_HOSTNAME and parsed.port is None:
        return (DEFAULT_GITHUB_HOSTNAME, None)
    return (bare_host, f"https://{parsed.netloc}")


def build_archive_url(
    archive_name: str, version: str = GITHUB_MCP_SERVER_VERSION
) -> str:
    """Construct the HTTPS GitHub Release asset download URL.

    Args:
        archive_name: Release tarball filename.
        version: Exact semantic version without leading ``v``.

    Returns:
        Full HTTPS URL for the release asset.

    Raises:
        LauncherError: If the constructed URL violates HTTPS or host constraints.
    """
    url = f"{GITHUB_RELEASE_BASE_URL}/v{version}/{archive_name}"
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "github.com":
        raise LauncherError(f"Refusing non-GitHub HTTPS download URL: {url}")
    return url


def _download_bytes(url: str, timeout: float = 60.0) -> bytes:
    """Download release archive bytes over HTTPS from ``github.com``.

    Args:
        url: Validated ``https://github.com/...`` release asset URL.
        timeout: Socket timeout in seconds.

    Returns:
        Raw archive bytes.

    Raises:
        LauncherError: If the URL scheme/host is invalid or the HTTP download fails.
    """
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "github.com":
        raise LauncherError(f"Refusing untrusted download URL: {url}")
    request = urllib.request.Request(  # ruff: ignore[suspicious-url-open-usage] - scheme=='https' and netloc=='github.com' verified above
        url, headers={"User-Agent": f"mimir-agent-kit/{GITHUB_MCP_SERVER_VERSION}"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # ruff: ignore[suspicious-url-open-usage] - scheme=='https' and netloc=='github.com' verified above
            data: bytes = response.read()
            return data
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LauncherError(f"Failed to download {url}: {exc}") from exc


def _read_binary_from_archive(archive_bytes: bytes) -> bytes | None:
    """Extract the target binary payload from an in-memory ``.tar.gz`` archive.

    Args:
        archive_bytes: Raw ``.tar.gz`` archive bytes.

    Returns:
        Extracted binary bytes, or ``None`` if no matching entry exists.
    """
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        for member in archive.getmembers():
            if Path(member.name).name == BINARY_NAME and member.isfile():
                extracted = archive.extractfile(member)
                if extracted is not None:
                    return extracted.read()
    return None


def _write_executable_atomically(
    tmp_path: Path, payload: bytes, destination: Path
) -> None:
    """Write ``payload`` to ``tmp_path``, mark executable, and atomically rename.

    Args:
        tmp_path: Staging file path in the destination directory.
        payload: Verified executable bytes.
        destination: Final executable path.
    """
    with tmp_path.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    tmp_path.chmod(0o755)
    tmp_path.replace(destination)


def extract_verified_binary(
    archive_bytes: bytes, expected_sha256: str, destination: Path
) -> Path:
    """Verify the archive SHA-256 digest in memory and atomically write the binary.

    Args:
        archive_bytes: Raw ``.tar.gz`` bytes.
        expected_sha256: Expected lowercase 64-hex SHA-256 digest of ``archive_bytes``.
        destination: Target binary path to atomically populate.

    Returns:
        ``destination`` once verified, extracted, and marked ``0755``.

    Raises:
        LauncherError: On SHA-256 mismatch, malformed tar archive, or missing binary entry.
    """
    actual_sha256 = hashlib.sha256(archive_bytes).hexdigest()
    if actual_sha256 != expected_sha256.lower():
        raise LauncherError(
            f"SHA-256 mismatch for github-mcp-server v{GITHUB_MCP_SERVER_VERSION}: expected {expected_sha256.lower()}, got {actual_sha256}",
        )

    try:
        binary_payload = _read_binary_from_archive(archive_bytes)
    except (tarfile.TarError, OSError) as exc:
        raise LauncherError(
            f"Failed to unpack github-mcp-server archive: {exc}"
        ) from exc

    if not binary_payload:
        raise LauncherError(
            f"Archive passed SHA-256 check but did not contain regular file {BINARY_NAME!r}."
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = destination.parent / f".{BINARY_NAME}.tmp.{os.getpid()}"
    try:
        _write_executable_atomically(tmp_path, binary_payload, destination)
    except OSError as exc:
        tmp_path.unlink(missing_ok=True)
        raise LauncherError(f"Failed to write {destination}: {exc}") from exc

    return destination


def ensure_binary(
    cache_dir: Path | str | None = None,
    *,
    system_name: str | None = None,
    machine_name: str | None = None,
    timeout: float = 60.0,
) -> Path:
    """Return the path to the SHA-256-verified ``github-mcp-server`` binary, downloading once if absent.

    Uses an ``fcntl.flock`` advisory lock so concurrent MCP startups on a fresh
    machine serialize cleanly without duplicate downloads or partial-file races.

    Args:
        cache_dir: Optional cache root directory (e.g., ``${PLUGIN_DATA}``).
        system_name: Optional OS override for testing.
        machine_name: Optional CPU architecture override for testing.
        timeout: Download timeout in seconds.

    Returns:
        Path to the verified executable binary.
    """
    sys_key, arch_key = normalize_platform(system_name, machine_name)
    archive_name, expected_sha256 = PLATFORM_ARCHIVE_SPECS[sys_key, arch_key]
    root = resolve_cache_root(cache_dir, system_name=sys_key)
    install_dir = (
        root / BINARY_NAME / f"v{GITHUB_MCP_SERVER_VERSION}" / f"{sys_key}_{arch_key}"
    )
    binary_path = install_dir / BINARY_NAME
    digest_stamp = install_dir / f"{BINARY_NAME}.archive.sha256"

    if (
        binary_path.is_file()
        and os.access(binary_path, os.X_OK)
        and digest_stamp.is_file()
        and digest_stamp.read_text(encoding="utf-8").strip() == expected_sha256
    ):
        return binary_path

    install_dir.mkdir(parents=True, exist_ok=True)
    lock_path = install_dir / ".install.lock"
    with lock_path.open("w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        if (
            binary_path.is_file()
            and os.access(binary_path, os.X_OK)
            and digest_stamp.is_file()
            and digest_stamp.read_text(encoding="utf-8").strip() == expected_sha256
        ):
            return binary_path

        url = build_archive_url(archive_name)
        archive_bytes = _download_bytes(url, timeout=timeout)
        extract_verified_binary(archive_bytes, expected_sha256, binary_path)
        digest_stamp.write_text(f"{expected_sha256}\n", encoding="utf-8")

    return binary_path


def _sanitize_stderr(stderr_text: str) -> str:
    """Collapse whitespace and redact any credential tokens in CLI error output.

    Args:
        stderr_text: Raw standard error text from ``gh``.

    Returns:
        Single-line redacted error summary, or an empty string if blank.
    """
    collapsed = " ".join(stderr_text.strip().split())
    redacted = _TOKEN_REDACTION_RE.sub("<redacted>", collapsed)
    redacted = _AUTH_HEADER_REDACTION_RE.sub(r"\1<redacted>", redacted)
    return _URL_CREDENTIAL_REDACTION_RE.sub(r"\1<redacted>\2", redacted)


def _scrub_placeholder_tokens(env: dict[str, str]) -> None:
    """Remove unexpanded ``${VAR}`` or ``$VAR`` placeholders from GitHub env keys in place.

    Prevents ``gh auth token`` and ``github-mcp-server`` from short-circuiting on
    literal placeholder strings inherited from partially configured environments.

    Args:
        env: Mutable environment dictionary.
    """
    for key in (*_TOKEN_ENV_KEYS, "GITHUB_HOST", "GITHUB_FEATURES"):
        value = env.get(key, "").strip()
        if value and (
            _UNEXPANDED_PLACEHOLDER_RE.match(value)
            or _EMBEDDED_PLACEHOLDER_RE.search(value)
        ):
            env.pop(key, None)


def _lookup_env_token(env: Mapping[str, str], keys: Sequence[str]) -> str | None:
    """Return the first non-empty, non-placeholder token from ``keys`` in ``env``.

    Args:
        env: Scrubbed environment mapping.
        keys: Ordered environment variable names to inspect.

    Returns:
        Token value if present, otherwise ``None``.
    """
    for key in keys:
        candidate = env.get(key, "").strip()
        if candidate and not _UNEXPANDED_PLACEHOLDER_RE.match(candidate):
            return candidate
    return None


def _build_gh_search_path(active_env: Mapping[str, str]) -> str:
    """Construct the ``PATH`` used to locate ``gh`` across shell and GUI launches.

    Resolves ``HOME/.local/bin`` lazily from ``active_env`` (or ``Path.home()`` when
    fallback search directories are enabled) alongside Homebrew, Linuxbrew, and Snap.

    Args:
        active_env: Environment mapping for the lookup.

    Returns:
        ``os.pathsep``-joined search path string.
    """
    path_entries = [p for p in active_env.get("PATH", "").split(os.pathsep) if p]
    extra_candidates: list[str] = []
    if "HOME" in active_env:
        home_dir = _safe_home_dir(active_env)
        if home_dir is not None:
            extra_candidates.append(str(home_dir / ".local" / "bin"))
    elif MACOS_EXTRA_PATH_DIRS:
        home_dir = _safe_home_dir()
        if home_dir is not None:
            extra_candidates.append(str(home_dir / ".local" / "bin"))

    extra_candidates.extend(MACOS_EXTRA_PATH_DIRS)
    for extra_dir in extra_candidates:
        if extra_dir not in path_entries:
            path_entries.append(extra_dir)
    return os.pathsep.join(path_entries)


def resolve_github_token(
    hostname: str | None = DEFAULT_GITHUB_HOSTNAME,
    env: Mapping[str, str] | None = None,
) -> str:
    """Retrieve a GitHub token from the environment or ``gh auth token`` OS keyring.

    Honors ``GITHUB_PERSONAL_ACCESS_TOKEN`` directly, checks host-matched ``GH_TOKEN`` /
    ``GITHUB_TOKEN`` (or ``GH_ENTERPRISE_TOKEN`` / ``GITHUB_ENTERPRISE_TOKEN``) after
    placeholder scrubbing so headless CI/container environments work without ``gh``
    installed, and otherwise queries ``gh auth token --hostname <bare_host>``.

    Args:
        hostname: GitHub hostname or URL (default ``github.com``).
        env: Optional environment mapping (defaults to ``os.environ``).

    Returns:
        Non-empty GitHub bearer token string.

    Raises:
        LauncherError: If ``hostname`` is invalid, ``gh`` is not installed, or ``gh auth token`` fails.
    """
    active_env = dict(os.environ if env is None else env)
    bare_host, _ = normalize_github_host(hostname, active_env)

    existing = active_env.get("GITHUB_PERSONAL_ACCESS_TOKEN", "").strip()
    if (
        existing
        and not _UNEXPANDED_PLACEHOLDER_RE.match(existing)
        and not _EMBEDDED_PLACEHOLDER_RE.search(existing)
    ):
        return existing

    _scrub_placeholder_tokens(active_env)
    primary_env_keys = (
        _GITHUB_COM_ENV_TOKEN_KEYS
        if bare_host == DEFAULT_GITHUB_HOSTNAME
        else _ENTERPRISE_ENV_TOKEN_KEYS
    )
    direct_env_token = _lookup_env_token(active_env, primary_env_keys)
    if direct_env_token is not None:
        return direct_env_token

    search_path = _build_gh_search_path(active_env)
    gh_bin = shutil.which("gh", path=search_path)
    if gh_bin is None:
        fallback_token = _lookup_env_token(active_env, _GITHUB_COM_ENV_TOKEN_KEYS)
        if fallback_token is not None:
            return fallback_token
        raise LauncherError(
            f"mimir-agent-kit github: 'gh' CLI not found on PATH ({search_path}); install GitHub CLI and run: gh auth login --hostname {bare_host}",
        )

    active_env["PATH"] = search_path
    try:
        completed = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - resolved gh binary with fixed argv
            [gh_bin, "auth", "token", "--hostname", bare_host],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10.0,
            check=False,
            env=active_env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LauncherError(
            f"mimir-agent-kit github: failed executing gh auth token: {exc}"
        ) from exc

    token = completed.stdout.strip()
    if (
        completed.returncode != 0
        or not token
        or _UNEXPANDED_PLACEHOLDER_RE.match(token)
        or _EMBEDDED_PLACEHOLDER_RE.search(token)
    ):
        detail = _sanitize_stderr(completed.stderr)
        suffix = f" ({detail})" if detail else ""
        raise LauncherError(
            f"mimir-agent-kit github: gh auth token failed for {bare_host}{suffix}; run: gh auth login --hostname {bare_host}",
        )
    return token


def _append_csv_features(raw_csv: str, target: list[str]) -> None:
    """Split a comma-separated feature string and append unique tokens in order.

    Args:
        raw_csv: Comma-separated feature names.
        target: Mutable list accumulating deduplicated feature names.
    """
    for piece in raw_csv.split(","):
        token = piece.strip()
        if token and token not in target:
            target.append(token)


def _extract_features_and_passthrough(
    server_args: Sequence[str], env: Mapping[str, str] | None
) -> tuple[list[str], list[str], int | None]:
    """Separate ``--features`` tokens (from ``env`` and ``server_args``) from other flags.

    Args:
        server_args: Forwarded CLI arguments for ``github-mcp-server stdio``.
        env: Optional environment mapping inspected for ``GITHUB_FEATURES``.

    Returns:
        Tuple of ``(passthrough_args, merged_features, first_features_index)``.
    """
    features: list[str] = []
    if env is not None:
        env_raw = env.get("GITHUB_FEATURES", "").strip()
        if env_raw and not _EMBEDDED_PLACEHOLDER_RE.search(env_raw):
            _append_csv_features(env_raw, features)

    cleaned = [str(item) for item in server_args if str(item) != "--"]
    passthrough: list[str] = []
    first_feature_idx: int | None = None
    idx = 0
    while idx < len(cleaned):
        item = cleaned[idx]
        if item == "--features":
            if first_feature_idx is None:
                first_feature_idx = len(passthrough)
            if idx + 1 < len(cleaned):
                _append_csv_features(cleaned[idx + 1], features)
                idx += 2
            else:
                idx += 1
        elif item.startswith("--features="):
            if first_feature_idx is None:
                first_feature_idx = len(passthrough)
            _append_csv_features(item.split("=", 1)[1], features)
            idx += 1
        else:
            passthrough.append(item)
            idx += 1

    return (passthrough, features, first_feature_idx)


def build_stdio_argv(
    binary_path: Path | str,
    server_args: Sequence[str] = (),
    *,
    enable_form_deferral: bool = False,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    """Construct the ``github-mcp-server stdio`` argument vector.

    Merges feature flags from ``GITHUB_FEATURES`` (in ``env``) and ``--features``
    CLI arguments so Cobra/Viper CLI flag precedence never drops environment
    features. Injects ``mcp_apps_disable_form_deferral`` by default, or actively
    strips it when ``enable_form_deferral=True``.

    Args:
        binary_path: Verified ``github-mcp-server`` executable path.
        server_args: Extra CLI flags forwarded after ``stdio``.
        enable_form_deferral: If ``True``, strip ``mcp_apps_disable_form_deferral``.
        env: Optional environment mapping checked for ``GITHUB_FEATURES``.

    Returns:
        Complete ``argv`` list starting with ``str(binary_path)`` and ``"stdio"``.
    """
    passthrough, features, insert_idx = _extract_features_and_passthrough(
        server_args, env
    )
    if enable_form_deferral:
        features = [f for f in features if f != DISABLE_FORM_DEFERRAL_FEATURE]
    elif DISABLE_FORM_DEFERRAL_FEATURE not in features:
        features.append(DISABLE_FORM_DEFERRAL_FEATURE)

    if features:
        canonical_flag = f"--features={','.join(features)}"
        if insert_idx is not None:
            passthrough.insert(insert_idx, canonical_flag)
        else:
            passthrough.append(canonical_flag)

    return [str(binary_path), "stdio", *passthrough]


def _prepare_child_env(
    base_env: Mapping[str, str],
    token: str,
    api_host_url: str | None,
    server_args: Sequence[str],
    *,
    enable_form_deferral: bool,
) -> dict[str, str]:
    """Build the sanitized child environment passed to ``github-mcp-server stdio``.

    Args:
        base_env: Parent environment mapping.
        token: Resolved GitHub bearer token.
        api_host_url: Normalized ``scheme://netloc`` URL for non-default hosts, or ``None``.
        server_args: Forwarded CLI arguments checked for explicit ``--gh-host``.
        enable_form_deferral: Whether ``mcp_apps_disable_form_deferral`` should be stripped.

    Returns:
        Sanitized environment dictionary for ``os.execve``.
    """
    child_env = dict(base_env)
    _scrub_placeholder_tokens(child_env)
    child_env["GITHUB_PERSONAL_ACCESS_TOKEN"] = token

    has_gh_host_flag = any(
        item == "--gh-host" or item.startswith("--gh-host=")
        for item in server_args
        if item != "--"
    )
    if api_host_url is not None and not has_gh_host_flag:
        child_env["GITHUB_HOST"] = api_host_url
    elif api_host_url is None:
        child_env.pop("GITHUB_HOST", None)

    if enable_form_deferral and "GITHUB_FEATURES" in child_env:
        remaining: list[str] = []
        _append_csv_features(child_env["GITHUB_FEATURES"], remaining)
        filtered = [f for f in remaining if f != DISABLE_FORM_DEFERRAL_FEATURE]
        if filtered:
            child_env["GITHUB_FEATURES"] = ",".join(filtered)
        else:
            child_env.pop("GITHUB_FEATURES", None)

    return child_env


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser.

    Returns:
        Configured ``ArgumentParser``.
    """
    parser = argparse.ArgumentParser(
        prog="github_mcp_launcher",
        description="Bootstrap SHA-256-pinned native github-mcp-server binary and exec stdio transport.",
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        default=None,
        help="Writable directory for cached github-mcp-server binary (typically ${PLUGIN_DATA}).",
    )
    parser.add_argument(
        "--hostname",
        type=str,
        default=None,
        help="GitHub hostname or URL for gh auth token lookup (defaults to GITHUB_HOST or github.com).",
    )
    parser.add_argument(
        "--print-binary-path",
        action="store_true",
        help="Ensure the verified binary is cached, print its path to stdout, and exit without starting stdio.",
    )
    parser.add_argument(
        "--enable-form-deferral",
        action="store_true",
        help="Allow MCP Apps interactive form deferral on write tools instead of direct execution.",
    )
    parser.add_argument(
        "server_args",
        nargs="*",
        help="Optional extra flags forwarded to github-mcp-server stdio.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Ensure the pinned ``github-mcp-server`` binary is cached and ``exec`` stdio mode.

    Args:
        argv: Optional CLI argument sequence (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit status when ``--print-binary-path`` is used or an error occurs.
    """
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        binary_path = ensure_binary(args.cache_dir)
        if args.print_binary_path:
            sys.stdout.write(f"{binary_path}\n")
            return 0

        bare_host, api_host_url = normalize_github_host(args.hostname, os.environ)
        token = resolve_github_token(hostname=bare_host)
    except LauncherError as exc:
        sys.stderr.write(f"{exc}\n")
        return 1

    enable_deferral = bool(args.enable_form_deferral)
    child_env = _prepare_child_env(
        os.environ,
        token,
        api_host_url,
        args.server_args,
        enable_form_deferral=enable_deferral,
    )
    exec_argv = build_stdio_argv(
        binary_path,
        args.server_args,
        enable_form_deferral=enable_deferral,
        env=child_env,
    )
    os.execve(str(binary_path), exec_argv, child_env)  # ruff: ignore[start-process-with-no-shell] - replaces process with SHA-256-verified static binary


if __name__ == "__main__":
    raise SystemExit(main())
