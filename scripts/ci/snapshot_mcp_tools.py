#!/usr/bin/env python3
"""Snapshot the tool inventory of every stdio MCP server bundled in this plugin.

Antigravity registers plugin MCP tools as ``mcp_<plugin>_<server>_<tool>`` and
silently drops any identifier that violates ``^[a-zA-Z0-9_-]{1,64}$``. Tool
names are only discoverable at runtime, so this script launches each pinned
stdio server from ``mcp_config.json``, performs the MCP ``initialize`` and
``tools/list`` handshake, and records the tool names in
``scripts/validation/mcp_tool_manifest.json``. The offline validator
(``MCP008``) then enforces the 64-character budget in CI without network access.

Placeholders such as ``${ADS_API_TOKEN}`` are resolved from the process
environment (the ``github`` server fetches its own token via ``gh auth token``). Servers whose variables are unset are skipped and keep
their previous manifest entry.

Usage:
    uv run python scripts/ci/snapshot_mcp_tools.py            # refresh manifest
    uv run python scripts/ci/snapshot_mcp_tools.py --check    # report only
"""

from __future__ import annotations

import argparse
import json
import os
import re
import selectors
import subprocess  # ruff: ignore[suspicious-subprocess-import] - launching pinned, repository-declared MCP servers is the purpose of this script
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / 'scripts' / 'validation' / 'mcp_tool_manifest.json'
MAX_TOOL_IDENTIFIER_LENGTH = 64
PLACEHOLDER_RE = re.compile(r'\$\{([A-Za-z0-9_]+)\}')
PROTOCOL_VERSION = '2025-06-18'


class SnapshotError(RuntimeError):
    """Raised when an MCP server cannot be launched or enumerated."""


def plugin_namespace(repo_root: Path) -> str:
    """Return the plugin namespace Antigravity prefixes onto tool identifiers.

    Args:
        repo_root: Plugin repository root.

    Returns:
        The ``name`` declared in ``plugin.json``, or the directory name.
    """
    manifest = repo_root / 'plugin.json'
    if manifest.is_file():
        name = json.loads(manifest.read_text(encoding='utf-8')).get('name')
        if isinstance(name, str) and name.strip():
            return name.strip()
    return repo_root.name


def _resolve(value: str, repo_root: Path) -> str:
    """Substitute ``${PLUGIN_ROOT}`` and environment placeholders in a string.

    A ``KeyError`` naming the variable propagates if a referenced environment variable is unset.

    Args:
        value: Raw configuration string.
        repo_root: Plugin repository root used for ``${PLUGIN_ROOT}``.

    Returns:
        The string with all placeholders substituted.
    """

    def _sub(match: re.Match[str]) -> str:
        var = match.group(1)
        if var == 'PLUGIN_ROOT':
            return str(repo_root)
        if var == 'PLUGIN_DATA':
            plugin_data = os.environ.get('PLUGIN_DATA', '').strip()
            return os.path.expanduser(plugin_data) if plugin_data else str((Path.home() / '.cache' / 'mimir-agent-kit' / 'plugin-data').resolve())
        resolved = os.environ.get(var)
        if not resolved:
            raise KeyError(var)
        return os.path.expanduser(resolved)

    return PLACEHOLDER_RE.sub(_sub, value)


def _read_response(proc: subprocess.Popen[bytes], request_id: int, deadline: float) -> dict[str, Any]:
    """Read JSON-RPC lines from the server until the response for ``request_id`` arrives.

    Args:
        proc: Running MCP server process.
        request_id: JSON-RPC request identifier to wait for.
        deadline: Absolute ``time.monotonic()`` deadline.

    Returns:
        The decoded JSON-RPC response object.

    Raises:
        SnapshotError: On timeout, process exit, or JSON-RPC error.
    """
    if proc.stdout is None:
        raise SnapshotError('server stdout is not piped')
    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)
    try:
        while (remaining := deadline - time.monotonic()) > 0:
            if not selector.select(timeout=remaining):
                continue
            line = proc.stdout.readline()
            if not line:
                raise SnapshotError(f'server exited (code {proc.poll()}) before answering request {request_id}')
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict) and message.get('id') == request_id:
                if 'error' in message:
                    raise SnapshotError(f'JSON-RPC error: {message["error"]}')
                return message
    finally:
        selector.close()
    raise SnapshotError(f'timed out waiting for response {request_id}')


def _send(proc: subprocess.Popen[bytes], payload: dict[str, Any]) -> None:
    """Write one newline-delimited JSON-RPC message to the server.

    Args:
        proc: Running MCP server process.
        payload: JSON-RPC message.

    Raises:
        SnapshotError: If stdin is not piped.
    """
    if proc.stdin is None:
        raise SnapshotError('server stdin is not piped')
    proc.stdin.write((json.dumps(payload) + '\n').encode('utf-8'))
    proc.stdin.flush()


def list_server_tools(spec: dict[str, Any], repo_root: Path, timeout: float) -> list[str]:
    """Launch a stdio MCP server and return its sorted tool names.

    ``SnapshotError`` propagates if the server fails to start or enumerate.

    Args:
        spec: Server specification from ``mcp_config.json``.
        repo_root: Plugin repository root.
        timeout: Seconds allowed for startup plus enumeration.

    Returns:
        Sorted tool names advertised via ``tools/list`` (all pages).
    """
    command = [_resolve(spec['command'], repo_root), *(_resolve(arg, repo_root) for arg in spec.get('args', []))]
    env = os.environ.copy()
    env.update({key: _resolve(val, repo_root) for key, val in spec.get('env', {}).items()})
    deadline = time.monotonic() + timeout
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env) as proc:  # ruff: ignore[subprocess-without-shell-equals-true] - argv comes from the repository's own mcp_config.json
        try:
            _send(proc, {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': PROTOCOL_VERSION, 'capabilities': {}, 'clientInfo': {'name': 'mimir-snapshot', 'version': '1'}}})
            _read_response(proc, 1, deadline)
            _send(proc, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
            tools: list[str] = []
            cursor: str | None = None
            request_id = 2
            while True:
                params: dict[str, Any] = {'cursor': cursor} if cursor else {}
                _send(proc, {'jsonrpc': '2.0', 'id': request_id, 'method': 'tools/list', 'params': params})
                result = _read_response(proc, request_id, deadline).get('result', {})
                tools.extend(str(tool['name']) for tool in result.get('tools', []))
                cursor = result.get('nextCursor')
                request_id += 1
                if not cursor:
                    return sorted(set(tools))
        finally:
            proc.kill()


def find_violations(namespace: str, manifest: dict[str, list[str]]) -> list[str]:
    """Return namespaced tool identifiers that exceed Antigravity's 64-character limit.

    Args:
        namespace: Plugin namespace.
        manifest: Mapping of server name to tool names.

    Returns:
        Human-readable violation descriptions.
    """
    violations: list[str] = []
    for server, tools in sorted(manifest.items()):
        for tool in tools:
            identifier = f'mcp_{namespace}_{server}_{tool}'
            if len(identifier) > MAX_TOOL_IDENTIFIER_LENGTH:
                violations.append(f'{identifier} ({len(identifier)} chars)')
    return violations


def main(argv: list[str] | None = None) -> int:
    """Refresh (or check) the MCP tool manifest.

    Args:
        argv: Optional command-line arguments.

    Returns:
        ``0`` on success, ``1`` if any server failed or any identifier is too long.
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true', help='Do not write the manifest; only report.')
    parser.add_argument('--timeout', type=float, default=120.0, help='Per-server timeout in seconds (default: 120).')
    parser.add_argument('--server', action='append', default=[], help='Limit to the named server(s).')
    args = parser.parse_args(argv)

    config = json.loads((REPO_ROOT / 'mcp_config.json').read_text(encoding='utf-8'))
    servers: dict[str, dict[str, Any]] = config['mcpServers']
    namespace = plugin_namespace(REPO_ROOT)
    previous: dict[str, list[str]] = json.loads(MANIFEST_PATH.read_text(encoding='utf-8')) if MANIFEST_PATH.is_file() else {}
    manifest: dict[str, list[str]] = {name: tools for name, tools in previous.items() if name in servers}
    failed = False

    for name, spec in servers.items():
        if (args.server and name not in args.server) or 'command' not in spec:
            continue
        try:
            manifest[name] = list_server_tools(spec, REPO_ROOT, args.timeout)
            longest = max(manifest[name], key=len, default='')
            sys.stdout.write(f'[ok]   {name}: {len(manifest[name])} tools; longest mcp_{namespace}_{name}_{longest} = {len(f"mcp_{namespace}_{name}_{longest}")} chars\n')
        except KeyError as exc:
            sys.stdout.write(f'[skip] {name}: environment variable {exc} is unset; keeping previous entry\n')
        except (SnapshotError, OSError) as exc:
            failed = True
            sys.stdout.write(f'[fail] {name}: {exc}\n')

    violations = find_violations(namespace, manifest)
    for violation in violations:
        sys.stdout.write(f'[long] {violation}\n')

    if not args.check:
        MANIFEST_PATH.write_text(json.dumps(dict(sorted(manifest.items())), indent=2) + '\n', encoding='utf-8')
        sys.stdout.write(f'Wrote {MANIFEST_PATH.relative_to(REPO_ROOT)}\n')
    return 1 if failed or violations else 0


if __name__ == '__main__':
    raise SystemExit(main())
