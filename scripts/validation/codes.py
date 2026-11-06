"""Standardized error codes for AntiGravity 2.29.0 agentic settings validation."""

from __future__ import annotations

import enum


class ErrorCode(enum.StrEnum):
    """Canonical error codes for AntiGravity 2.29.0 validation suite.

    Categorized into functional domains:
    - SKL: Agent Skills (skills/)
    - RUL: Workspace & Plugin Rules (rules/)
    - HOK: Lifecycle Hooks (hooks.json)
    - MCP: Model Context Protocol (mcp_config.json)
    - PLG: Plugin Manifest (plugin.json)
    - PRM: Prompt & Reference Consistency
    - TLS: Tool Schemas & Parameter Definitions
    - SEC: Secret Hygiene & Workspace Isolation
    """

    # Skills (SKL001-SKL008)
    SKL001 = 'SKL001'  # Missing SKILL.md in skill directory
    SKL002 = 'SKL002'  # Missing or malformed YAML frontmatter framing
    SKL003 = 'SKL003'  # Missing or invalid name field (must match directory name)
    SKL004 = 'SKL004'  # Missing or insufficient description (< 20 characters)
    SKL005 = 'SKL005'  # Markdown body exceeds 24,000 bytes hard cap
    SKL006 = 'SKL006'  # Disallowed top-level folder inside skill directory
    SKL007 = 'SKL007'  # Helper script inside scripts/ lacks executable bit (+x)
    SKL008 = 'SKL008'  # Broken relative markdown link inside skill documentation

    # Rules (RUL001-RUL004)
    RUL001 = 'RUL001'  # Top-level AGENTS.md placed at plugin root
    RUL002 = 'RUL002'  # Standalone AGENTS.md contains disallowed YAML frontmatter
    RUL003 = 'RUL003'  # Invalid rule trigger enum
    RUL004 = 'RUL004'  # Rule file exceeds 24,000 byte cap or always-on budget exceeds 20,000 tokens

    # Hooks (HOK001-HOK006)
    HOK001 = 'HOK001'  # Malformed JSON in hooks.json
    HOK002 = 'HOK002'  # Invalid lifecycle event name
    HOK003 = 'HOK003'  # Tool event missing matcher or hooks wrapper
    HOK004 = 'HOK004'  # Handler missing command string
    HOK005 = 'HOK005'  # Handler timeout not a positive integer
    HOK006 = 'HOK006'  # Handler command references script file that does not exist or lacks +x

    # MCP Config (MCP001-MCP008)
    MCP001 = 'MCP001'  # Malformed JSON in mcp_config.json
    MCP002 = 'MCP002'  # Missing or malformed mcpServers object
    MCP003 = 'MCP003'  # Invalid transport configuration (missing command or url)
    MCP004 = 'MCP004'  # Prohibited legacy SSE URL used instead of Streamable HTTP
    MCP005 = 'MCP005'  # Undeclared placeholder variable ${VAR} in command, args, or env
    MCP006 = 'MCP006'  # Declared variable in variables array not referenced in config
    MCP007 = 'MCP007'  # Variable declaration missing required title or description
    MCP008 = 'MCP008'  # Namespaced tool identifier mcp_<server>_<tool> exceeds 64 characters

    # Plugin Manifest (PLG001-PLG006)
    PLG001 = 'PLG001'  # Malformed JSON in plugin.json
    PLG002 = 'PLG002'  # Name does not match ^[a-z0-9]+(-[a-z0-9]+)*$
    PLG003 = 'PLG003'  # Version string violates Semantic Versioning (X.Y.Z)
    PLG004 = 'PLG004'  # Logo file path does not exist on disk
    PLG005 = 'PLG005'  # License is not a valid SPDX identifier
    PLG006 = 'PLG006'  # Missing .agents/skills.json or .agents/rules.json discovery file

    # Prompts & Cross-References (PRM001-PRM003)
    PRM001 = 'PRM001'  # Cross-skill link references non-existent skill
    PRM002 = 'PRM002'  # Contradictory PR merge directives (autonomous merge permitted)
    PRM003 = 'PRM003'  # Prescribing pixi for commands within pure uv repository

    # Tool Schemas (TLS001-TLS002)
    TLS001 = 'TLS001'  # Tool schema parameter missing valid JSON Schema type
    TLS002 = 'TLS002'  # Item in required array not present under properties

    # Secret Hygiene & Isolation (SEC001-SEC002)
    SEC001 = 'SEC001'  # Leaked absolute home path (/Users/..., /home/...) in repository file
    SEC002 = 'SEC002'  # Leaked authentication token (ghp_*, AIzaSy*, bearer secret)


CODE_DESCRIPTIONS: dict[ErrorCode, str] = {
    ErrorCode.SKL001: 'Missing SKILL.md in skill directory',
    ErrorCode.SKL002: 'Missing or malformed YAML frontmatter framing',
    ErrorCode.SKL003: 'Missing or invalid name field (must match directory name)',
    ErrorCode.SKL004: 'Missing or insufficient description (< 20 characters)',
    ErrorCode.SKL005: 'Markdown body exceeds 24,000 bytes hard cap',
    ErrorCode.SKL006: 'Disallowed top-level folder inside skill directory',
    ErrorCode.SKL007: 'Helper script inside scripts/ lacks executable bit (+x)',
    ErrorCode.SKL008: 'Broken relative markdown link inside skill documentation',
    ErrorCode.RUL001: 'Top-level AGENTS.md placed at plugin root',
    ErrorCode.RUL002: 'Standalone AGENTS.md contains disallowed YAML frontmatter',
    ErrorCode.RUL003: 'Invalid rule trigger enum',
    ErrorCode.RUL004: 'Rule file exceeds 24,000 byte cap or always-on budget exceeds 20,000 tokens',
    ErrorCode.HOK001: 'Malformed JSON in hooks.json',
    ErrorCode.HOK002: 'Invalid lifecycle event name',
    ErrorCode.HOK003: 'Tool event missing matcher or hooks wrapper',
    ErrorCode.HOK004: 'Handler missing command string',
    ErrorCode.HOK005: 'Handler timeout not a positive integer',
    ErrorCode.HOK006: 'Handler command references script file that does not exist or lacks +x',
    ErrorCode.MCP001: 'Malformed JSON in mcp_config.json',
    ErrorCode.MCP002: 'Missing or malformed mcpServers object',
    ErrorCode.MCP003: 'Invalid transport configuration (missing command or url)',
    ErrorCode.MCP004: 'Prohibited legacy SSE URL used instead of Streamable HTTP',
    ErrorCode.MCP005: 'Undeclared placeholder variable in command, args, or env',
    ErrorCode.MCP006: 'Declared variable in variables array not referenced in config',
    ErrorCode.MCP007: 'Variable declaration missing required title or description',
    ErrorCode.MCP008: 'Namespaced tool identifier mcp_<server>_<tool> exceeds 64 characters',
    ErrorCode.PLG001: 'Malformed JSON in plugin.json',
    ErrorCode.PLG002: 'Name does not match ^[a-z0-9]+(-[a-z0-9]+)*$',
    ErrorCode.PLG003: 'Version string violates Semantic Versioning (X.Y.Z)',
    ErrorCode.PLG004: 'Logo file path does not exist on disk',
    ErrorCode.PLG005: 'License is not a valid SPDX identifier',
    ErrorCode.PLG006: 'Missing .agents/skills.json or .agents/rules.json discovery file',
    ErrorCode.PRM001: 'Cross-skill link references non-existent skill',
    ErrorCode.PRM002: 'Contradictory PR merge directives (autonomous merge permitted)',
    ErrorCode.PRM003: 'Prescribing pixi for commands within pure uv repository',
    ErrorCode.TLS001: 'Tool schema parameter missing valid JSON Schema type',
    ErrorCode.TLS002: 'Item in required array not present under properties',
    ErrorCode.SEC001: 'Leaked absolute home path in repository file',
    ErrorCode.SEC002: 'Leaked authentication token in repository file',
}
