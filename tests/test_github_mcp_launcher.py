"""Unit tests for the Docker-free SHA-256-verified ``github-mcp-server`` launcher."""

import hashlib
import io
import os
import tarfile
from pathlib import Path

import pytest

from scripts import github_mcp_launcher as launcher


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
    """Explicit paths win; unexpanded ${PLUGIN_DATA} falls back to OS cache directories."""
    explicit = tmp_path / "plugin-data"
    assert launcher.resolve_cache_root(explicit) == explicit.resolve()

    monkeypatch.setenv("PLUGIN_DATA", "${PLUGIN_DATA}")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    assert (
        launcher.resolve_cache_root("${PLUGIN_DATA}", system_name="Linux")
        == (tmp_path / "xdg" / "mimir-agent-kit").resolve()
    )

    darwin_cache = launcher.resolve_cache_root(None, system_name="Darwin")
    assert darwin_cache.parts[-3:] == ("Library", "Caches", "mimir-agent-kit")


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
            "GITHUB_TOKEN": "${GITHUB_TOKEN}",
        },
    )
    assert resolved == "clean_keyring_val"


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
    assert "GH_TOKEN" not in exec_env


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
