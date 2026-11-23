"""Unit tests for the Docker-free SHA-256-verified ``github-mcp-server`` launcher."""

import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from scripts import github_mcp_launcher as launcher


if TYPE_CHECKING:
    from typing import Self


def _build_tar_gz(entries: dict[str, bytes]) -> bytes:
    """Create an in-memory ``.tar.gz`` archive from ``{filename: payload}``.

    Returns:
        Raw gzip-compressed tar archive bytes.
    """
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as archive:
        for name, payload in entries.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            info.mode = 0o755
            archive.addfile(info, io.BytesIO(payload))
    return buf.getvalue()


def test_normalize_platform_maps_linux_and_darwin_architectures() -> None:
    """Canonical OS/architecture pairs normalize across Linux and macOS aliases."""
    assert launcher.normalize_platform("Linux", "x86_64") == ("Linux", "x86_64")
    assert launcher.normalize_platform("Linux", "AMD64") == ("Linux", "x86_64")
    assert launcher.normalize_platform("Linux", "aarch64") == ("Linux", "aarch64")
    assert launcher.normalize_platform("Linux", "arm64") == ("Linux", "aarch64")
    assert launcher.normalize_platform("Darwin", "arm64") == ("Darwin", "arm64")
    assert launcher.normalize_platform("Darwin", "aarch64") == ("Darwin", "arm64")
    assert launcher.normalize_platform("Darwin", "x86_64") == ("Darwin", "x86_64")

    with pytest.raises(launcher.LauncherError, match="Unsupported CPU architecture"):
        launcher.normalize_platform("Linux", "riscv64")

    with pytest.raises(launcher.LauncherError, match="Unsupported platform"):
        launcher.normalize_platform("FreeBSD", "x86_64")


def test_resolve_cache_root_handles_placeholders_and_os_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Explicit paths win; unexpanded placeholders and headless runtimes fall back cleanly."""
    explicit = tmp_path / "plugin-data"
    assert launcher.resolve_cache_root(explicit) == explicit.resolve()

    monkeypatch.setenv("PLUGIN_DATA", "${PLUGIN_DATA}")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    assert (
        launcher.resolve_cache_root("${PLUGIN_DATA}", system_name="Linux")
        == (tmp_path / "xdg" / "mimir-agent-kit").resolve()
    )
    assert (
        launcher.resolve_cache_root("${PLUGIN_DATA}/sub", system_name="Linux")
        == (tmp_path / "xdg" / "mimir-agent-kit").resolve()
    )
    assert (
        launcher.resolve_cache_root("$PLUGIN_DATA/sub", system_name="Linux")
        == (tmp_path / "xdg" / "mimir-agent-kit").resolve()
    )

    darwin_cache = launcher.resolve_cache_root(None, system_name="Darwin")
    assert darwin_cache.parts[-3:] == ("Library", "Caches", "mimir-agent-kit")

    def _raise_no_home() -> Path:
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(Path, "home", _raise_no_home)
    tmp_fallback = tmp_path / "tmp-root"
    tmp_fallback.mkdir()
    monkeypatch.setattr(launcher.tempfile, "gettempdir", lambda: str(tmp_fallback))

    headless_darwin = launcher.resolve_cache_root(None, system_name="Darwin", env={})
    assert headless_darwin == (tmp_fallback / "mimir-agent-kit").resolve()

    headless_linux = launcher.resolve_cache_root(
        "~/cache", system_name="Linux", env={"XDG_CACHE_HOME": "${XDG_CACHE_HOME}"}
    )
    assert headless_linux == (tmp_fallback / "mimir-agent-kit").resolve()


def test_build_archive_url_enforces_github_https() -> None:
    """Release asset URLs always target https://github.com."""
    url = launcher.build_archive_url(
        "github-mcp-server_Darwin_arm64.tar.gz", version="2.2.0"
    )
    assert (
        url
        == "https://github.com/github/github-mcp-server/releases/download/v2.2.0/github-mcp-server_Darwin_arm64.tar.gz"
    )


def test_extract_verified_binary_verifies_sha256_and_writes_executable(
    tmp_path: Path,
) -> None:
    """Valid SHA-256 archive extracts github-mcp-server atomically with 0755 permissions."""
    payload = b"#!/bin/sh\necho ok\n"
    archive_bytes = _build_tar_gz({"README.md": b"docs", "github-mcp-server": payload})
    digest = hashlib.sha256(archive_bytes).hexdigest()
    dest = tmp_path / "bin" / "github-mcp-server"

    installed = launcher.extract_verified_binary(archive_bytes, digest, dest)
    assert installed == dest
    assert dest.read_bytes() == payload
    assert os.access(dest, os.X_OK)


def test_extract_verified_binary_rejects_tampered_or_incomplete_archives(
    tmp_path: Path,
) -> None:
    """SHA-256 mismatches, corrupt tarballs, and archives missing the binary raise LauncherError."""
    archive_bytes = _build_tar_gz({"github-mcp-server": b"binary"})
    dest = tmp_path / "github-mcp-server"

    with pytest.raises(launcher.LauncherError, match="SHA-256 mismatch"):
        launcher.extract_verified_binary(archive_bytes, "0" * 64, dest)
    assert not dest.exists()

    no_bin = _build_tar_gz({"README.md": b"only-readme"})
    with pytest.raises(launcher.LauncherError, match="did not contain regular file"):
        launcher.extract_verified_binary(
            no_bin, hashlib.sha256(no_bin).hexdigest(), dest
        )

    corrupt = b"not-a-gzip-stream"
    with pytest.raises(launcher.LauncherError, match="Failed to unpack"):
        launcher.extract_verified_binary(
            corrupt, hashlib.sha256(corrupt).hexdigest(), dest
        )


def test_ensure_binary_uses_warm_cache_and_reinstalls_on_stamp_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ensure_binary downloads once, skips network on warm cache, and refreshes if stamp differs."""
    payload = b"#!/bin/sh\nexit 0\n"
    archive_bytes = _build_tar_gz({"github-mcp-server": payload})
    real_digest = hashlib.sha256(archive_bytes).hexdigest()
    monkeypatch.setitem(
        launcher.PLATFORM_ARCHIVE_SPECS,
        ("Darwin", "arm64"),
        ("github-mcp-server_Darwin_arm64.tar.gz", real_digest),
    )

    calls: list[str] = []

    def _fake_download(url: str, timeout: float = 60.0) -> bytes:
        assert timeout > 0
        calls.append(url)
        return archive_bytes

    monkeypatch.setattr(launcher, "_download_bytes", _fake_download)

    first = launcher.ensure_binary(tmp_path, system_name="Darwin", machine_name="arm64")
    assert len(calls) == 1
    assert first.read_bytes() == payload

    second = launcher.ensure_binary(
        tmp_path, system_name="Darwin", machine_name="arm64"
    )
    assert second == first
    assert len(calls) == 1

    # Corrupting the digest stamp triggers a clean re-verification download.
    stamp = first.parent / "github-mcp-server.archive.sha256"
    stamp.write_text("f" * 64, encoding="utf-8")
    third = launcher.ensure_binary(tmp_path, system_name="Darwin", machine_name="arm64")
    assert third == first
    assert len(calls) == 2


def test_resolve_github_token_supports_env_and_gh_keyring(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """resolve_github_token honors explicit env tokens, ignores placeholders, searches Homebrew fallback dirs, and invokes gh CLI."""
    assert (
        launcher.resolve_github_token(
            env={"GITHUB_PERSONAL_ACCESS_TOKEN": "tok_explicit"}
        )
        == "tok_explicit"
    )

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        '#!/bin/sh\nif [ "$1" = "auth" ] && [ "$2" = "token" ]; then echo "tok_from_keyring"; exit 0; fi\nexit 1\n',
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)

    # Also verifies macOS GUI fallback search when PATH omits Homebrew directories.
    monkeypatch.setattr(launcher, "MACOS_EXTRA_PATH_DIRS", (str(fake_bin),))
    resolved = launcher.resolve_github_token(
        hostname="github.com",
        env={
            "GITHUB_PERSONAL_ACCESS_TOKEN": "${UNEXPANDED}",
            "PATH": str(tmp_path / "empty"),
        },
    )
    assert resolved == "tok_from_keyring"

    monkeypatch.setattr(launcher, "MACOS_EXTRA_PATH_DIRS", ())
    with pytest.raises(launcher.LauncherError, match="'gh' CLI not found"):
        launcher.resolve_github_token(env={"PATH": str(tmp_path / "empty")})

    leaked = "ghp_" + ("a" * 24)
    fake_gh.write_text(
        f'#!/bin/sh\necho "keychain locked: {leaked}" >&2\nexit 1\n',
        encoding="utf-8",
    )
    with pytest.raises(
        launcher.LauncherError,
        match=r"gh auth token failed for github\.com \(keychain locked: <redacted>\)",
    ):
        launcher.resolve_github_token(env={"PATH": str(fake_bin)})


def test_resolve_github_token_scrubs_placeholder_gh_token_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unexpanded ${GH_TOKEN}/${GITHUB_TOKEN} env values are stripped before invoking gh."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        '#!/bin/sh\nif [ -n "${GH_TOKEN:-}" ] || [ -n "${GITHUB_TOKEN:-}" ]; then echo "${GH_TOKEN:-$GITHUB_TOKEN}"; exit 0; fi\necho "clean_keyring_val"\n',
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)
    monkeypatch.setattr(launcher, "MACOS_EXTRA_PATH_DIRS", ())

    resolved = launcher.resolve_github_token(
        env={
            "PATH": str(fake_bin),
            "GH_TOKEN": "${GH_TOKEN}",
            "GITHUB_TOKEN": "${GITHUB_TOKEN:-}",
            "GITHUB_PERSONAL_ACCESS_TOKEN": "$GITHUB_TOKEN",
        },
    )
    assert resolved == "clean_keyring_val"


def test_resolve_github_token_env_fallbacks_without_gh_and_broadened_placeholders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Valid GH_TOKEN/GITHUB_TOKEN/GH_ENTERPRISE_TOKEN work without gh; placeholders are rejected."""
    monkeypatch.setattr(launcher, "MACOS_EXTRA_PATH_DIRS", ())
    empty_path = str(tmp_path / "no-gh")

    assert (
        launcher.resolve_github_token(
            hostname="github.com",
            env={"PATH": empty_path, "GH_TOKEN": "tok_gh_ci"},
        )
        == "tok_gh_ci"
    )
    assert (
        launcher.resolve_github_token(
            hostname="github.com",
            env={
                "PATH": empty_path,
                "GH_TOKEN": "${GH_TOKEN:-}",
                "GITHUB_TOKEN": "tok_actions_ci",
            },
        )
        == "tok_actions_ci"
    )
    assert (
        launcher.resolve_github_token(
            hostname="https://ghe.example.com",
            env={
                "PATH": empty_path,
                "GH_ENTERPRISE_TOKEN": "${env:GH_ENTERPRISE_TOKEN}",
                "GITHUB_ENTERPRISE_TOKEN": "tok_ghe_ent",
            },
        )
        == "tok_ghe_ent"
    )
    assert (
        launcher.resolve_github_token(
            hostname="ghe.example.com",
            env={"PATH": empty_path, "GH_TOKEN": "tok_cross_host_ci"},
        )
        == "tok_cross_host_ci"
    )

    for placeholder in ("${GITHUB_TOKEN:-}", "${env:GITHUB_TOKEN}", "$GITHUB_TOKEN"):
        with pytest.raises(launcher.LauncherError, match="'gh' CLI not found"):
            launcher.resolve_github_token(
                env={
                    "PATH": empty_path,
                    "GITHUB_PERSONAL_ACCESS_TOKEN": placeholder,
                }
            )


def test_lazy_home_resolution_and_headless_import_safety(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """resolve_github_token honors env['HOME']/.local/bin and module import survives missing HOME/passwd."""
    custom_home = tmp_path / "custom-home"
    local_bin = custom_home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    fake_gh = local_bin / "gh"
    fake_gh.write_text(
        '#!/bin/sh\necho "tok_from_env_home"\n',
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)

    monkeypatch.setattr(launcher, "MACOS_EXTRA_PATH_DIRS", ())
    assert (
        launcher.resolve_github_token(
            env={"HOME": str(custom_home), "PATH": str(tmp_path / "empty")}
        )
        == "tok_from_env_home"
    )

    # Headless runtime where Path.home() raises RuntimeError still searches fallback dirs cleanly.
    def _raise_no_home() -> Path:
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(Path, "home", _raise_no_home)
    monkeypatch.setattr(launcher, "MACOS_EXTRA_PATH_DIRS", (str(local_bin),))
    assert (
        launcher.resolve_github_token(env={"PATH": str(tmp_path / "empty")})
        == "tok_from_env_home"
    )

    # Fresh subprocess import with HOME unset and pwd.getpwuid raising KeyError must not crash.
    repo_root = Path(__file__).resolve().parent.parent
    sub_env = {k: v for k, v in os.environ.items() if k != "HOME"}
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import pwd; "
                "pwd.getpwuid = lambda uid: (_ for _ in ()).throw(KeyError(uid)); "
                "import scripts.github_mcp_launcher as m; "
                "assert m.MACOS_EXTRA_PATH_DIRS == m.EXTRA_PATH_DIRS"
            ),
        ],
        cwd=str(repo_root),
        env=sub_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_sanitize_stderr_redacts_all_credential_formats() -> None:
    """_sanitize_stderr redacts GitHub token prefixes, v1 tokens, auth headers, and URL credentials."""
    tok_gho = "gho_" + ("b" * 24)
    tok_ghu = "ghu_" + ("c" * 24)
    tok_ghs = "ghs_" + ("d" * 24)
    tok_ghr = "ghr_" + ("e" * 24)
    tok_pat = "github_pat_" + ("f" * 28)
    tok_v1 = "v1." + ("a1b2" * 10)

    raw = (
        f"err: {tok_gho} {tok_ghu} {tok_ghs} {tok_ghr} {tok_pat} {tok_v1}\n"
        "Authorization: Bearer custom_secret_999 "
        "Authorization: token 9988776655 "
        "https://x-access-token:url_secret_pw@ghe.example.com/api"
    )
    sanitized = launcher._sanitize_stderr(raw)
    for secret in (
        tok_gho,
        tok_ghu,
        tok_ghs,
        tok_ghr,
        tok_pat,
        tok_v1,
        "custom_secret_999",
        "9988776655",
        "url_secret_pw",
    ):
        assert secret not in sanitized
    assert "Authorization: Bearer <redacted>" in sanitized
    assert "Authorization: token <redacted>" in sanitized
    assert "https://x-access-token:<redacted>@ghe.example.com/api" in sanitized

    # Ordinary error text mentioning the word 'token' must remain readable.
    benign = "no oauth token found for github.com"
    assert launcher._sanitize_stderr(benign) == benign


def test_resolve_github_token_subprocess_errors_and_empty_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TimeoutExpired, OSError, empty stdout, and placeholder stdout raise LauncherError."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_gh.chmod(0o755)
    monkeypatch.setattr(launcher, "MACOS_EXTRA_PATH_DIRS", ())

    # Empty stdout with returncode 0
    with pytest.raises(
        launcher.LauncherError, match=r"gh auth token failed for github\.com;"
    ):
        launcher.resolve_github_token(env={"PATH": str(fake_bin)})

    # Placeholder stdout with returncode 0
    fake_gh.write_text('#!/bin/sh\necho "${GH_TOKEN}"\n', encoding="utf-8")
    with pytest.raises(
        launcher.LauncherError, match=r"gh auth token failed for github\.com;"
    ):
        launcher.resolve_github_token(env={"PATH": str(fake_bin)})

    def _raise_timeout(
        *_args: object, **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=["gh"], timeout=10.0)

    monkeypatch.setattr(subprocess, "run", _raise_timeout)
    with pytest.raises(launcher.LauncherError, match="failed executing gh auth token"):
        launcher.resolve_github_token(env={"PATH": str(fake_bin)})

    def _raise_oserror(
        *_args: object, **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        raise OSError("exec format error")

    monkeypatch.setattr(subprocess, "run", _raise_oserror)
    with pytest.raises(
        launcher.LauncherError,
        match="failed executing gh auth token: exec format error",
    ):
        launcher.resolve_github_token(env={"PATH": str(fake_bin)})


def test_normalize_github_host_handles_urls_bare_hosts_and_invalid_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """normalize_github_host bridges gh bare hostnames and github-mcp-server URL schemes."""
    assert launcher.normalize_github_host(None, {}) == ("github.com", None)
    assert launcher.normalize_github_host("", {"GITHUB_HOST": ""}) == (
        "github.com",
        None,
    )
    assert launcher.normalize_github_host(
        "${GITHUB_HOST}", {"GITHUB_HOST": "${GITHUB_HOST:-}"}
    ) == ("github.com", None)
    assert launcher.normalize_github_host("https://github.com/", {}) == (
        "github.com",
        None,
    )
    assert launcher.normalize_github_host(
        None, {"GITHUB_HOST": "https://ghe.example.com/api/v3"}
    ) == ("ghe.example.com", "https://ghe.example.com")
    assert launcher.normalize_github_host("ghe.example.com/", {}) == (
        "ghe.example.com",
        "https://ghe.example.com",
    )
    assert launcher.normalize_github_host("http://127.0.0.1:8080", {}) == (
        "127.0.0.1",
        "http://127.0.0.1:8080",
    )

    for bad_host in (
        "--help",
        "ftp://ghe.example.com",
        "ghe example.com",
        "https://-bad",
    ):
        with pytest.raises(launcher.LauncherError, match="Invalid GitHub host"):
            launcher.normalize_github_host(bad_host, {})

    # Verify resolve_github_token strips https:// before calling gh auth token --hostname.
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        '#!/bin/sh\nif [ "$4" = "ghe.example.com" ]; then echo "tok_ghe_keyring"; exit 0; fi\nexit 1\n',
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)
    monkeypatch.setattr(launcher, "MACOS_EXTRA_PATH_DIRS", ())
    assert (
        launcher.resolve_github_token(
            hostname="https://ghe.example.com/",
            env={"PATH": str(fake_bin)},
        )
        == "tok_ghe_keyring"
    )


def test_build_stdio_argv_disables_mcp_apps_form_deferral_by_default() -> None:
    """build_stdio_argv injects mcp_apps_disable_form_deferral once unless explicitly re-enabled."""
    default_argv = launcher.build_stdio_argv("/opt/bin/github-mcp-server")
    assert default_argv == [
        "/opt/bin/github-mcp-server",
        "stdio",
        "--features=mcp_apps_disable_form_deferral",
    ]

    deduped_argv = launcher.build_stdio_argv(
        "/opt/bin/github-mcp-server",
        ["--", "--features=mcp_apps_disable_form_deferral", "--read-only"],
    )
    assert deduped_argv == [
        "/opt/bin/github-mcp-server",
        "stdio",
        "--features=mcp_apps_disable_form_deferral",
        "--read-only",
    ]

    opted_in_argv = launcher.build_stdio_argv(
        "/opt/bin/github-mcp-server",
        ["--read-only"],
        enable_form_deferral=True,
    )
    assert opted_in_argv == ["/opt/bin/github-mcp-server", "stdio", "--read-only"]


def test_build_stdio_argv_merges_features_strips_opt_in_and_ignores_substrings() -> (
    None
):
    """build_stdio_argv merges GITHUB_FEATURES + CLI --features, strips on opt-in, and avoids substring traps."""
    stripped_mcp_cfg = launcher.build_stdio_argv(
        "/opt/bin/github-mcp-server",
        ["--", "--features=mcp_apps_disable_form_deferral"],
        enable_form_deferral=True,
    )
    assert stripped_mcp_cfg == ["/opt/bin/github-mcp-server", "stdio"]

    stripped_partial = launcher.build_stdio_argv(
        "/opt/bin/github-mcp-server",
        ["--read-only", "--features", "feat_cli,mcp_apps_disable_form_deferral"],
        enable_form_deferral=True,
        env={"GITHUB_FEATURES": "feat_env,mcp_apps_disable_form_deferral"},
    )
    assert stripped_partial == [
        "/opt/bin/github-mcp-server",
        "stdio",
        "--read-only",
        "--features=feat_env,feat_cli",
    ]

    merged_argv = launcher.build_stdio_argv(
        "/opt/bin/github-mcp-server",
        ["--features=feat_a", "--read-only", "--features", "feat_b"],
        enable_form_deferral=False,
        env={"GITHUB_FEATURES": "feat_env,feat_a"},
    )
    assert merged_argv == [
        "/opt/bin/github-mcp-server",
        "stdio",
        "--features=feat_env,feat_a,feat_b,mcp_apps_disable_form_deferral",
        "--read-only",
    ]

    non_feature_substring = launcher.build_stdio_argv(
        "/opt/bin/github-mcp-server",
        ["--log-file=/tmp/mcp_apps_disable_form_deferral.log"],
    )
    assert non_feature_substring == [
        "/opt/bin/github-mcp-server",
        "stdio",
        "--log-file=/tmp/mcp_apps_disable_form_deferral.log",
        "--features=mcp_apps_disable_form_deferral",
    ]


def test_main_execve_passes_token_and_form_deferral_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """main() scrubs placeholder env vars, sets GITHUB_PERSONAL_ACCESS_TOKEN, and execs stdio."""
    binary = tmp_path / "github-mcp-server"
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)

    monkeypatch.setattr(launcher, "ensure_binary", lambda *_args, **_kwargs: binary)
    monkeypatch.setattr(
        launcher, "resolve_github_token", lambda **_kwargs: "tok_keyring"
    )
    monkeypatch.setenv("GH_TOKEN", "${GH_TOKEN}")
    monkeypatch.delenv("GITHUB_HOST", raising=False)
    monkeypatch.delenv("GITHUB_FEATURES", raising=False)

    captured: dict[str, object] = {}

    def _fake_execve(
        path: str, argv: list[str], env: dict[str, str]
    ) -> None:  # pragma: no cover - terminates via SystemExit
        captured["path"] = path
        captured["argv"] = argv
        captured["env"] = env
        raise SystemExit(0)

    monkeypatch.setattr(os, "execve", _fake_execve)
    with pytest.raises(SystemExit) as exc_info:
        launcher.main(["--cache-dir", str(tmp_path), "--", "--read-only"])

    assert exc_info.value.code == 0
    assert captured["path"] == str(binary)
    assert captured["argv"] == [
        str(binary),
        "stdio",
        "--read-only",
        "--features=mcp_apps_disable_form_deferral",
    ]
    exec_env = captured["env"]
    assert isinstance(exec_env, dict)
    injected = exec_env.get("GITHUB_PERSONAL_ACCESS_TOKEN")
    assert injected == "tok_keyring"
    assert exec_env.get("GITHUB_FEATURES") == "mcp_apps_disable_form_deferral"
    assert "GH_TOKEN" not in exec_env


def test_main_handles_ghe_host_opt_in_deferral_and_launcher_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main() normalizes GITHUB_HOST, strips GITHUB_FEATURES on --enable-form-deferral, and exits 1 on error."""
    binary = tmp_path / "github-mcp-server"
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)

    monkeypatch.setattr(launcher, "ensure_binary", lambda *_args, **_kwargs: binary)
    seen_hosts: list[str | None] = []

    def _fake_resolve(*, hostname: str | None = None) -> str:
        seen_hosts.append(hostname)
        return "tok_ghe"

    monkeypatch.setattr(launcher, "resolve_github_token", _fake_resolve)
    monkeypatch.setenv("GITHUB_FEATURES", "custom_feat,mcp_apps_disable_form_deferral")
    monkeypatch.setenv("GITHUB_HOST", "ghe.example.com")

    captured: dict[str, object] = {}

    def _fake_execve(
        path: str, argv: list[str], env: dict[str, str]
    ) -> None:  # pragma: no cover - terminates via SystemExit
        captured["path"] = path
        captured["argv"] = argv
        captured["env"] = env
        raise SystemExit(0)

    monkeypatch.setattr(os, "execve", _fake_execve)
    with pytest.raises(SystemExit):
        launcher.main([
            "--enable-form-deferral",
            "--",
            "--features=mcp_apps_disable_form_deferral",
        ])

    assert seen_hosts == ["ghe.example.com"]
    assert captured["argv"] == [str(binary), "stdio", "--features=custom_feat"]
    exec_env = captured["env"]
    assert isinstance(exec_env, dict)
    assert exec_env.get("GITHUB_HOST") == "https://ghe.example.com"
    assert exec_env.get("GITHUB_FEATURES") == "custom_feat"

    # When GITHUB_FEATURES only contained mcp_apps_disable_form_deferral, it is removed cleanly.
    monkeypatch.setenv("GITHUB_FEATURES", "mcp_apps_disable_form_deferral")
    with pytest.raises(SystemExit):
        launcher.main(["--hostname", "github.com", "--enable-form-deferral"])
    exec_env_2 = captured["env"]
    assert isinstance(exec_env_2, dict)
    assert "GITHUB_FEATURES" not in exec_env_2
    assert "GITHUB_HOST" not in exec_env_2

    # LauncherError returns exit status 1 and prints diagnostics to stderr.
    def _fail_ensure(*_args: object, **_kwargs: object) -> Path:
        raise launcher.LauncherError("simulated bootstrap failure")

    monkeypatch.setattr(launcher, "ensure_binary", _fail_ensure)
    rc = launcher.main(["--cache-dir", str(tmp_path)])
    assert rc == 1
    assert "simulated bootstrap failure" in capsys.readouterr().err


def test_main_print_binary_path_outputs_verified_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """--print-binary-path bootstraps the binary and prints its path without requiring gh auth."""
    archive_bytes = _build_tar_gz({"github-mcp-server": b"#!/bin/sh\nexit 0\n"})
    digest = hashlib.sha256(archive_bytes).hexdigest()
    sys_key, arch_key = launcher.normalize_platform()
    monkeypatch.setitem(
        launcher.PLATFORM_ARCHIVE_SPECS, (sys_key, arch_key), ("test.tar.gz", digest)
    )
    monkeypatch.setattr(
        launcher, "_download_bytes", lambda *_args, **_kwargs: archive_bytes
    )

    rc = launcher.main(["--cache-dir", str(tmp_path), "--print-binary-path"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert Path(out).is_file()


class _FakeHttpResponse:
    """Minimal context-manager stub returned by mocked ``urllib.request.urlopen``."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        """Return raw HTTP response bytes.

        Returns:
            Raw response body bytes.
        """
        return self._payload

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def test_prepare_child_env_injects_and_deduplicates_github_features() -> None:
    """_prepare_child_env merges mcp_apps_disable_form_deferral when enabled=False and strips when True."""
    injected = launcher._prepare_child_env(
        {},
        "tok_test",
        None,
        (),
        enable_form_deferral=False,
    )
    assert injected["GITHUB_FEATURES"] == "mcp_apps_disable_form_deferral"

    merged = launcher._prepare_child_env(
        {"GITHUB_FEATURES": "feat_a, feat_b, feat_a"},
        "tok_test",
        None,
        (),
        enable_form_deferral=False,
    )
    assert merged["GITHUB_FEATURES"] == "feat_a,feat_b,mcp_apps_disable_form_deferral"

    already_present = launcher._prepare_child_env(
        {"GITHUB_FEATURES": "mcp_apps_disable_form_deferral,feat_a"},
        "tok_test",
        None,
        (),
        enable_form_deferral=False,
    )
    assert already_present["GITHUB_FEATURES"] == "mcp_apps_disable_form_deferral,feat_a"

    scrubbed_placeholder = launcher._prepare_child_env(
        {"GITHUB_FEATURES": "${GITHUB_FEATURES}"},
        "tok_test",
        None,
        (),
        enable_form_deferral=False,
    )
    assert scrubbed_placeholder["GITHUB_FEATURES"] == "mcp_apps_disable_form_deferral"

    stripped = launcher._prepare_child_env(
        {"GITHUB_FEATURES": "feat_a,mcp_apps_disable_form_deferral"},
        "tok_test",
        None,
        (),
        enable_form_deferral=True,
    )
    assert stripped["GITHUB_FEATURES"] == "feat_a"


def test_normalize_ls_base_url_enforces_loopback_and_valid_ports() -> None:
    """_normalize_ls_base_url accepts loopback host:port forms and rejects remote or malformed URLs."""
    assert launcher._normalize_ls_base_url("localhost:40801") == (
        "http://localhost:40801"
    )
    assert launcher._normalize_ls_base_url("127.0.0.1:5387") == "http://127.0.0.1:5387"
    assert launcher._normalize_ls_base_url("[::1]:40801") == "http://[::1]:40801"
    assert launcher._normalize_ls_base_url("http://LOCALHOST:40801/") == (
        "http://localhost:40801"
    )
    assert launcher._normalize_ls_base_url("https://127.0.0.1:44445") == (
        "https://127.0.0.1:44445"
    )

    rejected_inputs = (
        "",
        "   ",
        "${ANTIGRAVITY_LS_ADDRESS}",
        "/var/ls.sock",
        "localhost:40801 trailing",
        "example.com:40801",
        "http://192.168.1.10:40801",
        "http://10.0.0.5:40801",
        "0.0.0.0:40801",
        "127.0.0.2:40801",
        "ftp://localhost:40801",
        "ws://127.0.0.1:40801",
        "http://user:pw@localhost:40801",
        "http://localhost:40801/extra",
        "http://localhost:40801?q=1",
        "http://localhost:40801#frag",
        "localhost",
        "localhost:0",
        "localhost:70000",
        "localhost:notaport",
    )
    for bad_addr in rejected_inputs:
        with pytest.raises(launcher.LauncherError):
            launcher._normalize_ls_base_url(bad_addr)


def test_refresh_live_mcp_server_validates_args_and_required_env() -> None:
    """refresh_live_mcp_server raises actionable LauncherError on bad args or missing/placeholder env vars."""
    valid_env = {
        "ANTIGRAVITY_LS_ADDRESS": "localhost:40801",
        "ANTIGRAVITY_CSRF_TOKEN": "csrf-valid-token",
    }
    with pytest.raises(launcher.LauncherError, match="must not be empty"):
        launcher.refresh_live_mcp_server("   ", env=valid_env)

    with pytest.raises(launcher.LauncherError, match="must be positive"):
        launcher.refresh_live_mcp_server(env=valid_env, timeout=0.0)

    for bad_addr in ("", "${ANTIGRAVITY_LS_ADDRESS}", "$ANTIGRAVITY_LS_ADDRESS"):
        with pytest.raises(
            launcher.LauncherError,
            match="ANTIGRAVITY_LS_ADDRESS is unset or unexpanded",
        ):
            launcher.refresh_live_mcp_server(
                env={
                    "ANTIGRAVITY_LS_ADDRESS": bad_addr,
                    "ANTIGRAVITY_CSRF_TOKEN": "csrf-valid-token",
                }
            )

    for bad_csrf in ("", "${ANTIGRAVITY_CSRF_TOKEN}", "$ANTIGRAVITY_CSRF_TOKEN"):
        with pytest.raises(
            launcher.LauncherError,
            match="ANTIGRAVITY_CSRF_TOKEN is unset or unexpanded",
        ):
            launcher.refresh_live_mcp_server(
                env={
                    "ANTIGRAVITY_LS_ADDRESS": "127.0.0.1:40801",
                    "ANTIGRAVITY_CSRF_TOKEN": bad_csrf,
                }
            )


def test_refresh_live_mcp_server_polls_transition_to_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """refresh_live_mcp_server posts RefreshMcpServers, polls GetMcpServerStates to READY, and verifies GitHub flags."""
    csrf_val = "csrf-loopback-uuid-9876"
    seen_requests: list[tuple[str, str, dict[str, object]]] = []
    sleeps: list[float] = []
    monkeypatch.setattr(launcher.time, "sleep", sleeps.append)

    queued_payloads: list[dict[str, object]] = [
        {},
        {
            "states": [
                {
                    "spec": {"serverName": "mimir-agent-kit_github"},
                    "status": "MCP_SERVER_STATUS_STARTING",
                }
            ]
        },
        {
            "states": [
                {
                    "spec": {
                        "serverName": "mimir-agent-kit_github",
                        "args": ["--", "--features=mcp_apps_disable_form_deferral"],
                        "env": {"GITHUB_TOOLSETS": "all"},
                    },
                    "status": "MCP_SERVER_STATUS_READY",
                    "tools": [{"name": f"tool_{idx}"} for idx in range(87)],
                }
            ]
        },
    ]

    def _fake_urlopen(
        req: urllib.request.Request, timeout: float = 0.0
    ) -> _FakeHttpResponse:
        assert timeout > 0
        raw_data = req.data.decode("utf-8") if isinstance(req.data, bytes) else "{}"
        headers_lower = {k.lower(): v for k, v in req.header_items()}
        seen_requests.append((
            req.full_url,
            headers_lower.get("x-codeium-csrf-token", ""),
            json.loads(raw_data),
        ))
        return _FakeHttpResponse(json.dumps(queued_payloads.pop(0)).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    result = launcher.refresh_live_mcp_server(
        env={
            "ANTIGRAVITY_LS_ADDRESS": "localhost:40801",
            "ANTIGRAVITY_CSRF_TOKEN": csrf_val,
        },
        timeout=5.0,
    )

    assert result["serverName"] == "mimir-agent-kit_github"
    assert result["status"] == "MCP_SERVER_STATUS_READY"
    assert result["toolCount"] == 87
    assert len(sleeps) == 1
    assert seen_requests == [
        (
            "http://localhost:40801/exa.language_server_pb.LanguageServerService/RefreshMcpServers",
            csrf_val,
            {"serverName": "mimir-agent-kit_github"},
        ),
        (
            "http://localhost:40801/exa.language_server_pb.LanguageServerService/GetMcpServerStates",
            csrf_val,
            {},
        ),
        (
            "http://localhost:40801/exa.language_server_pb.LanguageServerService/GetMcpServerStates",
            csrf_val,
            {},
        ),
    ]


def test_refresh_live_mcp_server_supports_custom_server_and_env_only_feature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """refresh_live_mcp_server accepts non-GitHub servers and GITHUB_FEATURES env defense."""
    responses: list[dict[str, object]] = [
        {},
        {
            "states": [
                {
                    "serverName": "mimir-agent-kit_time",
                    "status": "MCP_SERVER_STATUS_READY",
                    "toolCount": 3,
                }
            ]
        },
        {},
        {
            "states": [
                {
                    "spec": {
                        "serverName": "mimir-agent-kit_github",
                        "args": ["run"],
                        "env": {"GITHUB_FEATURES": "mcp_apps_disable_form_deferral"},
                    },
                    "status": "MCP_SERVER_STATUS_READY",
                    "tools": [{"name": "get_me"}],
                }
            ]
        },
    ]

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _FakeHttpResponse(
            json.dumps(responses.pop(0)).encode("utf-8")
        ),
    )
    ls_env = {
        "ANTIGRAVITY_LS_ADDRESS": "http://127.0.0.1:40801",
        "ANTIGRAVITY_CSRF_TOKEN": "csrf-tok-ok",
    }

    time_state = launcher.refresh_live_mcp_server("mimir-agent-kit_time", env=ls_env)
    assert time_state["serverName"] == "mimir-agent-kit_time"
    assert time_state["toolCount"] == 3

    gh_state = launcher.refresh_live_mcp_server("mimir-agent-kit_github", env=ls_env)
    assert gh_state["toolCount"] == 1


def test_refresh_live_mcp_server_rejects_missing_stale_or_errored_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing servers, malformed states, or GitHub servers lacking form-deferral protection raise LauncherError."""
    ls_env = {
        "ANTIGRAVITY_LS_ADDRESS": "[::1]:40801",
        "ANTIGRAVITY_CSRF_TOKEN": "csrf-secret-val-777",
    }

    bad_state_scenarios: list[tuple[dict[str, object], str]] = [
        ({"states": "not-a-list"}, "missing 'states' list"),
        ({"states": []}, "was not found in GetMcpServerStates"),
        (
            {
                "states": [
                    {
                        "serverName": "mimir-agent-kit_github",
                        "status": "MCP_SERVER_STATUS_READY",
                    }
                ]
            },
            "without a valid server spec",
        ),
        (
            {
                "states": [
                    {
                        "spec": {
                            "serverName": "mimir-agent-kit_github",
                            "args": ["--enable-form-deferral"],
                        },
                        "status": "MCP_SERVER_STATUS_READY",
                    }
                ]
            },
            "--enable-form-deferral enabled",
        ),
        (
            {
                "states": [
                    {
                        "spec": {
                            "serverName": "mimir-agent-kit_github",
                            "args": ["run"],
                            "env": {},
                        },
                        "status": "MCP_SERVER_STATUS_READY",
                    }
                ]
            },
            "without 'mcp_apps_disable_form_deferral'",
        ),
    ]

    for states_body, expected_msg in bad_state_scenarios:
        pair = [{}, states_body]
        monkeypatch.setattr(
            urllib.request,
            "urlopen",
            lambda *_args, _q=pair, **_kwargs: _FakeHttpResponse(
                json.dumps(_q.pop(0)).encode("utf-8")
            ),
        )
        with pytest.raises(launcher.LauncherError, match=expected_msg):
            launcher.refresh_live_mcp_server(env=ls_env)


def test_refresh_live_mcp_server_redacts_csrf_on_http_network_and_state_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CSRF tokens and x-codeium-csrf-token headers never leak in HTTP, network, JSON, state, or timeout errors."""
    csrf_val = "csrf-super-nonce-00112233"
    ls_env = {
        "ANTIGRAVITY_LS_ADDRESS": "127.0.0.1:40801",
        "ANTIGRAVITY_CSRF_TOKEN": csrf_val,
    }

    def _raise_http_403(*_args: object, **_kwargs: object) -> _FakeHttpResponse:
        body = f"invalid x-codeium-csrf-token: {csrf_val}".encode()
        raise urllib.error.HTTPError(
            "http://127.0.0.1:40801/rpc", 403, "Forbidden", Message(), io.BytesIO(body)
        )

    monkeypatch.setattr(urllib.request, "urlopen", _raise_http_403)
    with pytest.raises(launcher.LauncherError, match="HTTP 403") as http_exc:
        launcher.refresh_live_mcp_server(env=ls_env)
    assert csrf_val not in str(http_exc.value)
    assert "x-codeium-csrf-token: <redacted>" in str(http_exc.value)

    def _raise_url_error(*_args: object, **_kwargs: object) -> _FakeHttpResponse:
        raise urllib.error.URLError(f"proxy rejected {csrf_val}")

    monkeypatch.setattr(urllib.request, "urlopen", _raise_url_error)
    with pytest.raises(
        launcher.LauncherError, match="proxy rejected <redacted>"
    ) as u_exc:
        launcher.refresh_live_mcp_server(env=ls_env)
    assert csrf_val not in str(u_exc.value)

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _FakeHttpResponse(f"not-json {csrf_val}".encode()),
    )
    with pytest.raises(launcher.LauncherError, match="invalid JSON") as json_exc:
        launcher.refresh_live_mcp_server(env=ls_env)
    assert csrf_val not in str(json_exc.value)

    errored_pair: list[dict[str, object]] = [
        {},
        {
            "states": [
                {
                    "spec": {"serverName": "mimir-agent-kit_github"},
                    "status": "MCP_SERVER_STATUS_ERROR",
                    "error": f"handshake failed ({csrf_val})",
                }
            ]
        },
    ]
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _FakeHttpResponse(
            json.dumps(errored_pair.pop(0)).encode("utf-8")
        ),
    )
    with pytest.raises(launcher.LauncherError, match="failed after refresh") as st_exc:
        launcher.refresh_live_mcp_server(env=ls_env)
    assert csrf_val not in str(st_exc.value)


def test_refresh_live_mcp_server_times_out_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """refresh_live_mcp_server raises LauncherError when server never reaches MCP_SERVER_STATUS_READY."""
    clock = [100.0]

    def _fake_monotonic() -> float:
        clock[0] += 0.3
        return clock[0]

    monkeypatch.setattr(launcher.time, "monotonic", _fake_monotonic)
    monkeypatch.setattr(launcher.time, "sleep", lambda _s: None)
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _FakeHttpResponse(
            json.dumps({
                "states": [
                    {
                        "spec": {"serverName": "mimir-agent-kit_github"},
                        "status": "MCP_SERVER_STATUS_STARTING",
                    }
                ]
            }).encode("utf-8")
        ),
    )

    with pytest.raises(launcher.LauncherError, match="Timed out"):
        launcher.refresh_live_mcp_server(
            env={
                "ANTIGRAVITY_LS_ADDRESS": "localhost:40801",
                "ANTIGRAVITY_CSRF_TOKEN": "csrf-timeout-tok",
            },
            timeout=0.5,
        )


def test_main_refresh_live_cli_dispatch_and_stderr_redaction(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main(['--refresh-live', ...]) prints concise status without starting stdio or leaking CSRF tokens."""
    csrf_val = "csrf-cli-never-print-999"
    monkeypatch.setenv("ANTIGRAVITY_LS_ADDRESS", "localhost:40801")
    monkeypatch.setenv("ANTIGRAVITY_CSRF_TOKEN", csrf_val)

    def _forbid_stdio(*_args: object, **_kwargs: object) -> Path:
        raise AssertionError("ensure_binary must not run during --refresh-live")

    monkeypatch.setattr(launcher, "ensure_binary", _forbid_stdio)

    ok_responses: list[dict[str, object]] = [
        {},
        {
            "states": [
                {
                    "spec": {
                        "serverName": "mimir-agent-kit_time",
                        "args": [],
                    },
                    "status": "MCP_SERVER_STATUS_READY",
                    "tools": [{"name": "a"}, {"name": "b"}, {"name": "c"}],
                }
            ]
        },
    ]
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _FakeHttpResponse(
            json.dumps(ok_responses.pop(0)).encode("utf-8")
        ),
    )

    rc = launcher.main(["--refresh-live", "--server-name", "mimir-agent-kit_time"])
    captured = capsys.readouterr()
    assert rc == 0
    assert (
        captured.out
        == "Refreshed mimir-agent-kit_time (MCP_SERVER_STATUS_READY, toolCount=3)\n"
    )
    assert not captured.err
    assert csrf_val not in captured.out

    def _fail_urlopen(*_args: object, **_kwargs: object) -> _FakeHttpResponse:
        raise OSError(f"socket error x-codeium-csrf-token={csrf_val}")

    monkeypatch.setattr(urllib.request, "urlopen", _fail_urlopen)
    rc_err = launcher.main(["--refresh-live"])
    err_captured = capsys.readouterr()
    assert rc_err == 1
    assert not err_captured.out
    assert "x-codeium-csrf-token=<redacted>" in err_captured.err
    assert csrf_val not in err_captured.err
