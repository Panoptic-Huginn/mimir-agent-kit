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
3. Reads the active multi-owner OAuth token from ``gh auth token --hostname github.com``
   (spanning both personal accounts and GitHub Enterprise Cloud organizations via
   Ubuntu ``libsecret`` / macOS Keychain) and replaces the current process via
   ``os.execve`` with ``github-mcp-server stdio``.
"""

from __future__ import annotations

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
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Final


GITHUB_MCP_SERVER_VERSION: Final[str] = '2.1.0'
GITHUB_RELEASE_BASE_URL: Final[str] = 'https://github.com/github/github-mcp-server/releases/download'
DEFAULT_GITHUB_HOSTNAME: Final[str] = 'github.com'
BINARY_NAME: Final[str] = 'github-mcp-server'
MACOS_EXTRA_PATH_DIRS: Final[tuple[str, ...]] = ('/opt/homebrew/bin', '/usr/local/bin')

_UNEXPANDED_PLACEHOLDER_RE: Final[re.Pattern[str]] = re.compile(r'^\$\{[A-Za-z0-9_]+\}$')

# Official SHA-256 archive digests from github-mcp-server_2.1.0_checksums.txt.
PLATFORM_ARCHIVE_SPECS: Final[dict[tuple[str, str], tuple[str, str]]] = {
    ('Linux', 'x86_64'): (
        'github-mcp-server_Linux_x86_64.tar.gz',
        'a442f9db287cea01008bcb55fe6bc0292270301046c3edbd1a8b22d6e4157b2b',
    ),
    ('Linux', 'aarch64'): (
        'github-mcp-server_Linux_arm64.tar.gz',
        '34d5a268f65cd1e9b7107fa976f3571ccd575f9df00cec489fec79a039923a22',
    ),
    ('Darwin', 'arm64'): (
        'github-mcp-server_Darwin_arm64.tar.gz',
        '3fb2936c33416693a8b268442ab9b1e838d4fbb8c2a6813d8a77f87c3009ced6',
    ),
    ('Darwin', 'x86_64'): (
        'github-mcp-server_Darwin_x86_64.tar.gz',
        '3c4b023b0d90bdc8f3a2ab63307ff55d293e98c27e733008eed0fa35aca55499',
    ),
}


class LauncherError(RuntimeError):
    """Raised when platform resolution, binary verification, or keyring auth fails."""


def normalize_platform(system_name: str | None = None, machine_name: str | None = None) -> tuple[str, str]:
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
    raw_arch = (machine_name if machine_name is not None else platform.machine()).strip().lower()

    if raw_arch in {'x86_64', 'amd64'}:
        norm_arch = 'x86_64'
    elif raw_arch in {'aarch64', 'arm64'}:
        norm_arch = 'arm64' if raw_sys == 'Darwin' else 'aarch64'
    else:
        raise LauncherError(f'Unsupported CPU architecture {raw_arch!r} on {raw_sys!r}.')

    key = (raw_sys, norm_arch)
    if key not in PLATFORM_ARCHIVE_SPECS:
        raise LauncherError(f'Unsupported platform {raw_sys}/{norm_arch} for github-mcp-server.')
    return key


def resolve_cache_root(cache_dir: Path | str | None = None, system_name: str | None = None) -> Path:
    """Resolve the writable root directory for cached ``github-mcp-server`` binaries.

    Uses ``cache_dir`` (typically ``${PLUGIN_DATA}``) when provided and expanded;
    otherwise falls back to ``~/Library/Caches/mimir-agent-kit`` on macOS or
    ``${XDG_CACHE_HOME:-~/.cache}/mimir-agent-kit`` on Linux.

    Args:
        cache_dir: Optional directory path or unexpanded placeholder.
        system_name: Optional OS override for deterministic testing.

    Returns:
        Resolved ``Path`` to the root cache directory.
    """
    candidate = str(cache_dir).strip() if cache_dir is not None else os.environ.get('PLUGIN_DATA', '').strip()
    if candidate and not _UNEXPANDED_PLACEHOLDER_RE.match(candidate):
        return Path(candidate).expanduser().resolve()

    active_sys = system_name if system_name is not None else platform.system()
    if active_sys == 'Darwin':
        return (Path.home() / 'Library' / 'Caches' / 'mimir-agent-kit').resolve()

    xdg_cache = os.environ.get('XDG_CACHE_HOME', '').strip()
    base = Path(xdg_cache).expanduser() if xdg_cache else (Path.home() / '.cache')
    return (base / 'mimir-agent-kit').resolve()


def build_archive_url(archive_name: str, version: str = GITHUB_MCP_SERVER_VERSION) -> str:
    """Construct the HTTPS GitHub Release asset download URL.

    Args:
        archive_name: Release tarball filename.
        version: Exact semantic version without leading ``v``.

    Returns:
        Full HTTPS URL for the release asset.

    Raises:
        LauncherError: If the constructed URL violates HTTPS or host constraints.
    """
    url = f'{GITHUB_RELEASE_BASE_URL}/v{version}/{archive_name}'
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.netloc != 'github.com':
        raise LauncherError(f'Refusing non-GitHub HTTPS download URL: {url}')
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
    if parsed.scheme != 'https' or parsed.netloc != 'github.com':
        raise LauncherError(f'Refusing untrusted download URL: {url}')
    request = urllib.request.Request(url, headers={'User-Agent': f'mimir-agent-kit/{GITHUB_MCP_SERVER_VERSION}'})  # ruff: ignore[suspicious-url-open-usage] - scheme=='https' and netloc=='github.com' verified above
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # ruff: ignore[suspicious-url-open-usage] - scheme=='https' and netloc=='github.com' verified above
            data: bytes = response.read()
            return data
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LauncherError(f'Failed to download {url}: {exc}') from exc


def extract_verified_binary(archive_bytes: bytes, expected_sha256: str, destination: Path) -> Path:
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
            f'SHA-256 mismatch for github-mcp-server v{GITHUB_MCP_SERVER_VERSION}: expected {expected_sha256.lower()}, got {actual_sha256}',
        )

    binary_payload: bytes | None = None
    try:
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:gz') as archive:
            for member in archive.getmembers():
                if Path(member.name).name == BINARY_NAME and member.isfile():
                    extracted = archive.extractfile(member)
                    if extracted is not None:
                        binary_payload = extracted.read()
                        break
    except (tarfile.TarError, OSError) as exc:
        raise LauncherError(f'Failed to unpack github-mcp-server archive: {exc}') from exc

    if not binary_payload:
        raise LauncherError(f'Archive passed SHA-256 check but did not contain regular file {BINARY_NAME!r}.')

    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = destination.parent / f'.{BINARY_NAME}.tmp.{os.getpid()}'
    try:
        with tmp_path.open('wb') as handle:
            handle.write(binary_payload)
            handle.flush()
            os.fsync(handle.fileno())
        tmp_path.chmod(0o755)
        os.replace(tmp_path, destination)
    except OSError as exc:
        tmp_path.unlink(missing_ok=True)
        raise LauncherError(f'Failed to write {destination}: {exc}') from exc

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
    install_dir = root / BINARY_NAME / f'v{GITHUB_MCP_SERVER_VERSION}' / f'{sys_key}_{arch_key}'
    binary_path = install_dir / BINARY_NAME
    digest_stamp = install_dir / f'{BINARY_NAME}.archive.sha256'

    if binary_path.is_file() and os.access(binary_path, os.X_OK) and digest_stamp.is_file():
        if digest_stamp.read_text(encoding='utf-8').strip() == expected_sha256:
            return binary_path

    install_dir.mkdir(parents=True, exist_ok=True)
    lock_path = install_dir / '.install.lock'
    with lock_path.open('w', encoding='utf-8') as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        if binary_path.is_file() and os.access(binary_path, os.X_OK) and digest_stamp.is_file():
            if digest_stamp.read_text(encoding='utf-8').strip() == expected_sha256:
                return binary_path

        url = build_archive_url(archive_name)
        archive_bytes = _download_bytes(url, timeout=timeout)
        extract_verified_binary(archive_bytes, expected_sha256, binary_path)
        digest_stamp.write_text(f'{expected_sha256}\n', encoding='utf-8')

    return binary_path


def resolve_github_token(hostname: str = DEFAULT_GITHUB_HOSTNAME, env: dict[str, str] | None = None) -> str:
    """Retrieve a GitHub token from the environment or ``gh auth token`` OS keyring.

    Appends standard Homebrew paths (``/opt/homebrew/bin``, ``/usr/local/bin``)
    when searching for ``gh`` so macOS GUI launches find Homebrew installations
    without shell profile sourcing.

    Args:
        hostname: GitHub hostname passed to ``gh auth token --hostname`` (default ``github.com``).
        env: Optional environment mapping (defaults to ``os.environ``).

    Returns:
        Non-empty GitHub bearer token string.

    Raises:
        LauncherError: If ``gh`` is not installed or ``gh auth token`` fails.
    """
    active_env = dict(os.environ if env is None else env)
    existing = active_env.get('GITHUB_PERSONAL_ACCESS_TOKEN', '').strip()
    if existing and not _UNEXPANDED_PLACEHOLDER_RE.match(existing):
        return existing

    path_entries = [p for p in active_env.get('PATH', '').split(os.pathsep) if p]
    for extra_dir in MACOS_EXTRA_PATH_DIRS:
        if extra_dir not in path_entries:
            path_entries.append(extra_dir)
    search_path = os.pathsep.join(path_entries)

    gh_bin = shutil.which('gh', path=search_path)
    if gh_bin is None:
        raise LauncherError(
            f"mimir-agent-kit github: 'gh' CLI not found on PATH ({search_path}); install GitHub CLI and run: gh auth login --hostname {hostname}",
        )

    active_env['PATH'] = search_path
    try:
        completed = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - resolved gh binary with fixed argv
            [gh_bin, 'auth', 'token', '--hostname', hostname],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10.0,
            check=False,
            env=active_env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LauncherError(f'mimir-agent-kit github: failed executing gh auth token: {exc}') from exc

    token = completed.stdout.strip()
    if completed.returncode != 0 or not token:
        raise LauncherError(
            f'mimir-agent-kit github: gh auth token failed for {hostname}; run: gh auth login --hostname {hostname}',
        )
    return token


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser.

    Returns:
        Configured ``ArgumentParser``.
    """
    parser = argparse.ArgumentParser(
        prog='github_mcp_launcher',
        description='Bootstrap SHA-256-pinned native github-mcp-server binary and exec stdio transport.',
    )
    parser.add_argument(
        '--cache-dir',
        type=str,
        default=None,
        help='Writable directory for cached github-mcp-server binary (typically ${PLUGIN_DATA}).',
    )
    parser.add_argument(
        '--hostname',
        type=str,
        default=os.environ.get('GITHUB_HOST', DEFAULT_GITHUB_HOSTNAME),
        help='GitHub hostname for gh auth token lookup (default: github.com).',
    )
    parser.add_argument(
        '--print-binary-path',
        action='store_true',
        help='Ensure the verified binary is cached, print its path to stdout, and exit without starting stdio.',
    )
    parser.add_argument(
        'server_args',
        nargs='*',
        help='Optional extra flags forwarded to github-mcp-server stdio.',
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Ensure the pinned ``github-mcp-server`` binary is cached and ``exec`` stdio mode.

    Args:
        argv: Optional CLI argument list (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit status when ``--print-binary-path`` is used or an error occurs.
    """
    args = build_parser().parse_args(argv)
    try:
        binary_path = ensure_binary(args.cache_dir)
        if args.print_binary_path:
            sys.stdout.write(f'{binary_path}\n')
            return 0

        token = resolve_github_token(hostname=str(args.hostname))
    except LauncherError as exc:
        sys.stderr.write(f'{exc}\n')
        return 1

    child_env = os.environ.copy()
    child_env['GITHUB_PERSONAL_ACCESS_TOKEN'] = token
    exec_argv = [str(binary_path), 'stdio', *(str(item) for item in args.server_args)]
    os.execve(str(binary_path), exec_argv, child_env)  # ruff: ignore[start-process-with-no-shell] - replaces process with SHA-256-verified static binary


if __name__ == '__main__':
    raise SystemExit(main())
