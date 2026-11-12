"""Validator for AntiGravity 2.29.0 Model Context Protocol configuration (mcp_config.json)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

from scripts.validation.codes import ErrorCode
from scripts.validation.models import Severity


if TYPE_CHECKING:
    from scripts.validation.models import ValidationReport


BUILTIN_MCP_PLACEHOLDERS = frozenset({'PLUGIN_ROOT', 'PLUGIN_DATA'})
VAR_PLACEHOLDER_PATTERN = re.compile(r'\$\{([A-Za-z0-9_]+)\}')
TOOL_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')
SERVER_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
MAX_TOOL_IDENTIFIER_LENGTH = 64
TOOL_MANIFEST_RELATIVE_PATH = Path('scripts') / 'validation' / 'mcp_tool_manifest.json'

DOCKER_DIGEST_IMAGE_PATTERN = re.compile(r'^[a-z0-9._/-]+(?::[A-Za-z0-9._-]+)?@sha256:[0-9a-f]{64}$')
PYPI_EXACT_PIN_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*(?:\[[A-Za-z0-9_,.-]+\])?==[0-9][A-Za-z0-9._+-]*$')
NPM_EXACT_PIN_PATTERN = re.compile(r'^(?:@[a-z0-9-~][a-z0-9-._~]*/)?[a-z0-9-~][a-z0-9-._~]*@[0-9]+\.[0-9]+\.[0-9]+[A-Za-z0-9._+-]*$')

DOCKER_RUN_VALUE_FLAGS = frozenset({
    '-e',
    '--env',
    '--env-file',
    '-v',
    '--volume',
    '--mount',
    '-p',
    '--publish',
    '-w',
    '--workdir',
    '-u',
    '--user',
    '--name',
    '--network',
    '--net',
    '--platform',
    '--entrypoint',
    '--hostname',
    '-h',
    '--label',
    '-l',
    '--memory',
    '-m',
    '--cpus',
    '--pull',
    '--restart',
    '--log-driver',
    '--log-opt',
})

UV_VALUE_FLAGS = frozenset({
    '-w',
    '--with',
    '--from',
    '-p',
    '--python',
    '--index-url',
    '--extra-index-url',
    '-c',
    '--constraints',
    '-b',
    '--build-constraints',
    '--overrides',
    '--env-file',
    '--with-requirements',
    '--with-editable',
    '--directory',
    '--project',
})

NPX_VALUE_FLAGS = frozenset({
    '-p',
    '--package',
    '-c',
    '--call',
    '--cache',
    '--userconfig',
    '--registry',
})


def _validate_docker_pinning(
    server_name: str,
    args: list[str],
    report: ValidationReport,
    path: Path,
) -> None:
    """Verify docker run MCP servers pin container images by @sha256:<64-hex> digest.

    Args:
        server_name: Name of the MCP server.
        args: Argument list passed to the docker command.
        report: Aggregating ValidationReport.
        path: Path to mcp_config.json.
    """
    if 'run' not in args:
        return
    idx = args.index('run') + 1
    image_ref: str | None = None
    while idx < len(args):
        arg_val = args[idx]
        if arg_val == '--':
            if idx + 1 < len(args):
                image_ref = args[idx + 1]
            break
        if arg_val in DOCKER_RUN_VALUE_FLAGS:
            idx += 2
            continue
        if arg_val.startswith('-'):
            idx += 1
            continue
        image_ref = arg_val
        break

    if not image_ref or not DOCKER_DIGEST_IMAGE_PATTERN.match(image_ref):
        report.add(
            code=ErrorCode.MCP009,
            message=(f"Docker MCP server '{server_name}' uses unpinned image '{image_ref or '<missing>'}'. Must pin an immutable '@sha256:<64-hex>' digest."),
            severity=Severity.ERROR,
            path=path,
            suggestion='Pin the container image as <registry>/<repo>:<tag>@sha256:<64-char-digest>.',
        )


def _validate_uv_pinning(
    server_name: str,
    cmd_name: str,
    args: list[str],
    report: ValidationReport,
    path: Path,
) -> None:
    """Verify uv and uvx MCP servers use exact ==X.Y.Z package version pins.

    Args:
        server_name: Name of the MCP server.
        cmd_name: Normalized command basename ('uv' or 'uvx').
        args: Argument list passed to uv/uvx.
        report: Aggregating ValidationReport.
        path: Path to mcp_config.json.
    """
    is_tool_runner = cmd_name == 'uvx' or args[:2] == ['tool', 'run']
    start_idx = 2 if (cmd_name == 'uv' and args[:2] == ['tool', 'run']) else 0
    has_from_pkg = False
    first_positional: str | None = None

    idx = start_idx
    while idx < len(args):
        arg_val = args[idx]
        pkg_val: str | None = None
        is_from_flag = False

        if arg_val in {'-w', '--with', '--from'}:
            is_from_flag = arg_val == '--from'
            if idx + 1 < len(args):
                pkg_val = args[idx + 1]
            idx += 2
        elif arg_val.startswith('--with='):
            pkg_val = arg_val.split('=', 1)[1]
            idx += 1
        elif arg_val.startswith('--from='):
            is_from_flag = True
            pkg_val = arg_val.split('=', 1)[1]
            idx += 1
        elif arg_val in UV_VALUE_FLAGS:
            idx += 2
            continue
        elif arg_val.startswith('-'):
            idx += 1
            continue
        else:
            if first_positional is None:
                first_positional = arg_val
            idx += 1
            continue

        if is_from_flag:
            has_from_pkg = True
        if not pkg_val or not PYPI_EXACT_PIN_PATTERN.match(pkg_val):
            report.add(
                code=ErrorCode.MCP009,
                message=(f"MCP server '{server_name}' passes unpinned PyPI requirement '{pkg_val or '<missing>'}' to {cmd_name}. Exact '==X.Y.Z' version pinning is required."),
                severity=Severity.ERROR,
                path=path,
                suggestion="Replace floating or range specifiers with an exact 'package==X.Y.Z' pin.",
            )

    if is_tool_runner and not has_from_pkg and first_positional is not None:
        if '/' not in first_positional and '$' not in first_positional and not PYPI_EXACT_PIN_PATTERN.match(first_positional):
            report.add(
                code=ErrorCode.MCP009,
                message=(f"MCP server '{server_name}' invokes '{cmd_name} {first_positional}' without an exact '==X.Y.Z' version pin."),
                severity=Severity.ERROR,
                path=path,
                suggestion=f"Pin the tool package version explicitly as '{first_positional}==X.Y.Z'.",
            )


def _validate_npx_pinning(
    server_name: str,
    args: list[str],
    report: ValidationReport,
    path: Path,
) -> None:
    """Verify npx MCP servers pin npm packages to an exact @X.Y.Z SemVer release.

    Args:
        server_name: Name of the MCP server.
        args: Argument list passed to npx.
        report: Aggregating ValidationReport.
        path: Path to mcp_config.json.
    """
    explicit_packages: list[str] = []
    first_positional: str | None = None

    idx = 0
    while idx < len(args):
        arg_val = args[idx]
        if arg_val in {'-p', '--package'}:
            if idx + 1 < len(args):
                explicit_packages.append(args[idx + 1])
            idx += 2
            continue
        if arg_val.startswith('--package='):
            explicit_packages.append(arg_val.split('=', 1)[1])
            idx += 1
            continue
        if arg_val in NPX_VALUE_FLAGS:
            idx += 2
            continue
        if arg_val.startswith('-'):
            idx += 1
            continue
        if first_positional is None:
            first_positional = arg_val
        idx += 1

    targets = explicit_packages if explicit_packages else ([first_positional] if first_positional is not None else [])
    for pkg_spec in targets:
        if not pkg_spec or not NPM_EXACT_PIN_PATTERN.match(pkg_spec):
            report.add(
                code=ErrorCode.MCP009,
                message=(f"npx MCP server '{server_name}' uses unpinned npm package '{pkg_spec or '<missing>'}'. Exact '@X.Y.Z' version pinning is required."),
                severity=Severity.ERROR,
                path=path,
                suggestion="Pin the npm package to an exact SemVer version (e.g., '@scope/pkg@1.2.3').",
            )


def validate_mcp_server_pinning(
    server_name: str,
    spec: dict[str, Any],
    report: ValidationReport,
    path: Path,
) -> None:
    """Validate supply-chain version/digest pinning for stdio MCP server launchers.

    Args:
        server_name: Name of the MCP server.
        spec: Server configuration dictionary.
        report: Aggregating ValidationReport.
        path: Path to mcp_config.json.
    """
    command = spec.get('command')
    raw_args = spec.get('args', [])
    if not isinstance(command, str) or not isinstance(raw_args, list):
        return
    if not all(isinstance(item, str) for item in raw_args):
        return

    cmd_name = Path(command.strip()).name
    if cmd_name == 'docker':
        _validate_docker_pinning(server_name, raw_args, report, path)
    elif cmd_name in {'uv', 'uvx'}:
        _validate_uv_pinning(server_name, cmd_name, raw_args, report, path)
    elif cmd_name == 'npx':
        _validate_npx_pinning(server_name, raw_args, report, path)


def namespaced_tool_prefix(server_name: str, plugin_name: str | None = None) -> str:
    """Return the identifier prefix Antigravity prepends to an MCP server's tools.

    Global servers register as ``mcp_<server>_<tool>``; plugin-bundled servers are
    additionally namespaced by the plugin as ``mcp_<plugin>_<server>_<tool>``.

    Args:
        server_name: Name of the MCP server.
        plugin_name: Plugin namespace, or None for a global ``mcp_config.json``.

    Returns:
        The prefix string including the trailing underscore.
    """
    return f'mcp_{plugin_name}_{server_name}_' if plugin_name else f'mcp_{server_name}_'


def resolve_plugin_name(repo_root: Path) -> str | None:
    """Return the plugin namespace for a repository root, or None if it is not a plugin.

    Args:
        repo_root: Root path of repository.

    Returns:
        The ``name`` field of ``plugin.json`` (falling back to the directory name), or None when no ``plugin.json`` exists.
    """
    manifest = repo_root / 'plugin.json'
    if not manifest.is_file():
        return None
    try:
        name = json.loads(manifest.read_text(encoding='utf-8')).get('name')
    except OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError:
        name = None
    return name.strip() if isinstance(name, str) and name.strip() else repo_root.name


def load_tool_manifest(manifest_file: Path) -> dict[str, list[str]]:
    """Load a server-to-tool-names manifest produced by ``scripts/ci/snapshot_mcp_tools.py``.

    Args:
        manifest_file: Path to the JSON manifest.

    Returns:
        Mapping of server names to tool name lists (empty if the file is absent or malformed).
    """
    if not manifest_file.is_file():
        return {}
    try:
        data = json.loads(manifest_file.read_text(encoding='utf-8'))
    except OSError, UnicodeDecodeError, json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(server): [str(tool) for tool in tools] for server, tools in data.items() if isinstance(tools, list)}


def validate_namespaced_tool_name(
    server_name: str,
    tool_name: str,
    report: ValidationReport,
    path: Path,
    plugin_name: str | None = None,
) -> None:
    """Validate that the namespaced MCP tool identifier adheres to ^[a-zA-Z0-9_-]{1,64}$.

    Args:
        server_name: Name of the MCP server.
        tool_name: Name of the tool.
        report: Aggregating ValidationReport.
        path: Target file path.
        plugin_name: Plugin namespace for plugin-bundled servers, or None for global servers.
    """
    namespaced = f'{namespaced_tool_prefix(server_name, plugin_name)}{tool_name}'
    if len(namespaced) > MAX_TOOL_IDENTIFIER_LENGTH or not TOOL_NAME_PATTERN.match(namespaced):
        report.add(
            code=ErrorCode.MCP008,
            message=(f"Namespaced tool identifier '{namespaced}' ({len(namespaced)} chars) exceeds {MAX_TOOL_IDENTIFIER_LENGTH} characters or violates ^[a-zA-Z0-9_-]{{1,64}}$."),
            severity=Severity.ERROR,
            path=path,
            suggestion=(f"Shorten tool name '{tool_name}' or server name '{server_name}' (or exclude the tool) so that '{namespaced}' is <= 64 characters."),
        )


def validate_mcp_config_file(
    config_file: Path,
    report: ValidationReport,
    known_tools: dict[str, list[str]] | None = None,
    plugin_name: str | None = None,
) -> None:
    """Validate mcp_config.json against AntiGravity 2.29.0 specifications.

    Args:
        config_file: Path to mcp_config.json.
        report: Aggregating ValidationReport.
        known_tools: Optional mapping of server names to tool name lists to validate MCP008.
        plugin_name: Plugin namespace applied to tool identifiers, or None for a global config.
    """
    try:
        content = config_file.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as exc:
        report.add(
            code=ErrorCode.MCP001,
            message=f'Failed to read mcp_config.json: {exc}',
            severity=Severity.ERROR,
            path=config_file,
        )
        return

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        report.add(
            code=ErrorCode.MCP001,
            message=f'Malformed JSON in mcp_config.json: {exc}',
            severity=Severity.ERROR,
            path=config_file,
            line=exc.lineno,
            suggestion='Ensure mcp_config.json contains valid JSON syntax.',
        )
        return

    if not isinstance(data, dict):
        report.add(
            code=ErrorCode.MCP001,
            message='Root of mcp_config.json must be a JSON object.',
            severity=Severity.ERROR,
            path=config_file,
        )
        return

    servers = data.get('mcpServers')
    if not isinstance(servers, dict):
        report.add(
            code=ErrorCode.MCP002,
            message="Missing or malformed 'mcpServers' object in mcp_config.json.",
            severity=Severity.ERROR,
            path=config_file,
            suggestion="Define 'mcpServers' as a top-level dictionary of server configurations.",
        )
        return

    for server_name, spec in servers.items():
        if not isinstance(server_name, str) or not SERVER_NAME_PATTERN.match(server_name):
            report.add(
                code=ErrorCode.MCP008,
                message=f"MCP server name '{server_name}' contains invalid characters (must match ^[a-zA-Z0-9_-]+$).",
                severity=Severity.ERROR,
                path=config_file,
            )

        prefix = namespaced_tool_prefix(server_name, plugin_name)
        if len(prefix) >= MAX_TOOL_IDENTIFIER_LENGTH:
            report.add(
                code=ErrorCode.MCP008,
                message=(f"MCP server name '{server_name}' is too long ({len(server_name)} chars). Prefix '{prefix}' alone leaves no room for tool names under 64 characters."),
                severity=Severity.ERROR,
                path=config_file,
            )

        if not isinstance(spec, dict):
            report.add(
                code=ErrorCode.MCP002,
                message=f"Server specification for '{server_name}' must be an object.",
                severity=Severity.ERROR,
                path=config_file,
            )
            continue

        # Validate Transport (MCP003, MCP004)
        has_command = 'command' in spec and isinstance(spec['command'], str) and bool(spec['command'].strip())
        url = spec.get('url') or spec.get('serverUrl')
        has_url = isinstance(url, str) and bool(url.strip())

        if not has_command and not has_url:
            report.add(
                code=ErrorCode.MCP003,
                message=(f"Server '{server_name}' has invalid transport configuration: missing required 'command' (stdio) or 'url' (Streamable HTTP)."),
                severity=Severity.ERROR,
                path=config_file,
                suggestion="Specify 'command' for a local stdio server or 'url' for a remote HTTP server.",
            )

        # Validate args and env types (MCP002)
        if 'args' in spec and not isinstance(spec['args'], list):
            report.add(
                code=ErrorCode.MCP002,
                message=f"Server '{server_name}' 'args' must be a list of strings.",
                severity=Severity.ERROR,
                path=config_file,
            )
        if 'env' in spec and not isinstance(spec['env'], dict):
            report.add(
                code=ErrorCode.MCP002,
                message=f"Server '{server_name}' 'env' must be a dictionary of environment variables.",
                severity=Severity.ERROR,
                path=config_file,
            )

        if has_url and isinstance(url, str):
            lower_url = url.lower()
            if '/sse' in lower_url or 'eventsource' in lower_url:
                report.add(
                    code=ErrorCode.MCP004,
                    message=(f"Server '{server_name}' uses prohibited legacy SSE URL '{url}'. AntiGravity 2.29.0 requires Streamable HTTP (/mcp) or a stdio bridge."),
                    severity=Severity.ERROR,
                    path=config_file,
                    suggestion='Migrate remote endpoint to Streamable HTTP (/mcp) or use a local stdio process.',
                )

        # Validate Variables Parity (MCP005, MCP006, MCP007)
        # Scan command, args, env for ${VAR} placeholders
        serialized_spec = json.dumps({k: v for k, v in spec.items() if k != 'variables'})
        referenced_vars = set(VAR_PLACEHOLDER_PATTERN.findall(serialized_spec)) - BUILTIN_MCP_PLACEHOLDERS

        declared_vars_list = spec.get('variables', [])
        if not isinstance(declared_vars_list, list):
            report.add(
                code=ErrorCode.MCP002,
                message=f"'variables' in server '{server_name}' must be a list of variable objects.",
                severity=Severity.ERROR,
                path=config_file,
            )
            declared_vars_list = []

        declared_vars: set[str] = set()
        for var_entry in declared_vars_list:
            if not isinstance(var_entry, dict) or 'name' not in var_entry:
                report.add(
                    code=ErrorCode.MCP007,
                    message=f"Variable definition in server '{server_name}' must be an object with 'name'.",
                    severity=Severity.ERROR,
                    path=config_file,
                )
                continue

            var_name = str(var_entry['name'])
            declared_vars.add(var_name)

            title = str(var_entry.get('title', '')).strip()
            desc = str(var_entry.get('description', '')).strip()
            if not title or not desc:
                report.add(
                    code=ErrorCode.MCP007,
                    message=(f"Variable '{var_name}' in server '{server_name}' is missing required 'title' or 'description'."),
                    severity=Severity.ERROR,
                    path=config_file,
                    suggestion="Provide descriptive 'title' and 'description' explaining scope and how to obtain it.",
                )

        # MCP005: Undeclared placeholder variable
        undeclared = referenced_vars - declared_vars
        for var in sorted(undeclared):
            report.add(
                code=ErrorCode.MCP005,
                message=(f"Undeclared placeholder variable '${{{var}}}' referenced in server '{server_name}'. Must be declared in 'variables' array."),
                severity=Severity.ERROR,
                path=config_file,
                suggestion=f"Add a variable declaration for '{var}' with title and description to 'variables'.",
            )

        # MCP006: Declared variable not referenced in config
        unreferenced = declared_vars - referenced_vars
        for var in sorted(unreferenced):
            report.add(
                code=ErrorCode.MCP006,
                message=(f"Variable '{var}' declared in server '{server_name}' variables array is not referenced in config."),
                severity=Severity.ERROR,
                path=config_file,
                suggestion=f"Reference '${{{var}}}' in command, args, or env, or remove it from 'variables'.",
            )

        # MCP008: Check tools defined directly in spec or passed in known_tools
        tools_in_spec = spec.get('tools', [])
        if isinstance(tools_in_spec, list):
            for tool_item in tools_in_spec:
                tname = tool_item if isinstance(tool_item, str) else tool_item.get('name') if isinstance(tool_item, dict) else None
                if isinstance(tname, str):
                    validate_namespaced_tool_name(server_name, tname, report, config_file, plugin_name)

        if known_tools and server_name in known_tools:
            for tname in known_tools[server_name]:
                validate_namespaced_tool_name(server_name, tname, report, config_file, plugin_name)

        # MCP009: Supply-chain digest & version pinning for container/package launchers
        validate_mcp_server_pinning(server_name, spec, report, config_file)


def validate_mcp_config(
    repo_root: Path,
    report: ValidationReport,
    known_tools: dict[str, list[str]] | None = None,
) -> None:
    """Validate mcp_config.json in the repository root.

    When the repository is a plugin (``plugin.json`` present), tool identifiers are
    validated with the plugin namespace, and the runtime tool inventory recorded in
    ``scripts/validation/mcp_tool_manifest.json`` is merged into ``known_tools``.

    Args:
        repo_root: Root path of repository.
        report: Aggregating ValidationReport.
        known_tools: Optional mapping of server names to tool name lists.
    """
    config_file = repo_root / 'mcp_config.json'
    if config_file.is_file():
        merged_tools = load_tool_manifest(repo_root / TOOL_MANIFEST_RELATIVE_PATH)
        for server, tools in (known_tools or {}).items():
            merged_tools[server] = sorted({*merged_tools.get(server, []), *tools})
        validate_mcp_config_file(config_file, report, known_tools=merged_tools or None, plugin_name=resolve_plugin_name(repo_root))
