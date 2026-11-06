"""Validator for AntiGravity 2.29.0 Model Context Protocol configuration (mcp_config.json)."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from scripts.validation.codes import ErrorCode
from scripts.validation.models import Severity


if TYPE_CHECKING:
    from pathlib import Path

    from scripts.validation.models import ValidationReport


BUILTIN_MCP_PLACEHOLDERS = frozenset({'PLUGIN_ROOT', 'PLUGIN_DATA'})
VAR_PLACEHOLDER_PATTERN = re.compile(r'\$\{([A-Za-z0-9_]+)\}')
TOOL_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')
SERVER_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
MAX_TOOL_IDENTIFIER_LENGTH = 64


def validate_namespaced_tool_name(
    server_name: str,
    tool_name: str,
    report: ValidationReport,
    path: Path,
) -> None:
    """Validate that the namespaced MCP tool identifier adheres to ^[a-zA-Z0-9_-]{1,64}$.

    Args:
        server_name: Name of the MCP server.
        tool_name: Name of the tool.
        report: Aggregating ValidationReport.
        path: Target file path.
    """
    namespaced = f'mcp_{server_name}_{tool_name}'
    if len(namespaced) > MAX_TOOL_IDENTIFIER_LENGTH or not TOOL_NAME_PATTERN.match(namespaced):
        report.add(
            code=ErrorCode.MCP008,
            message=(f"Namespaced tool identifier '{namespaced}' ({len(namespaced)} chars) exceeds {MAX_TOOL_IDENTIFIER_LENGTH} characters or violates ^[a-zA-Z0-9_-]{{1,64}}$."),
            severity=Severity.ERROR,
            path=path,
            suggestion=(f"Shorten tool name '{tool_name}' or server name '{server_name}' so that 'mcp_{server_name}_{tool_name}' is <= 64 characters."),
        )


def validate_mcp_config_file(
    config_file: Path,
    report: ValidationReport,
    known_tools: dict[str, list[str]] | None = None,
) -> None:
    """Validate mcp_config.json against AntiGravity 2.29.0 specifications.

    Args:
        config_file: Path to mcp_config.json.
        report: Aggregating ValidationReport.
        known_tools: Optional mapping of server names to tool name lists to validate MCP008.
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

        if len(f'mcp_{server_name}_') >= MAX_TOOL_IDENTIFIER_LENGTH:
            report.add(
                code=ErrorCode.MCP008,
                message=(f"MCP server name '{server_name}' is too long ({len(server_name)} chars). Prefix 'mcp_{server_name}_' alone leaves no room for tool names under 64 characters."),
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
                    validate_namespaced_tool_name(server_name, tname, report, config_file)

        if known_tools and server_name in known_tools:
            for tname in known_tools[server_name]:
                validate_namespaced_tool_name(server_name, tname, report, config_file)


def validate_mcp_config(
    repo_root: Path,
    report: ValidationReport,
    known_tools: dict[str, list[str]] | None = None,
) -> None:
    """Validate mcp_config.json in the repository root.

    Args:
        repo_root: Root path of repository.
        report: Aggregating ValidationReport.
        known_tools: Optional mapping of server names to tool name lists.
    """
    config_file = repo_root / 'mcp_config.json'
    if config_file.is_file():
        validate_mcp_config_file(config_file, report, known_tools=known_tools)
