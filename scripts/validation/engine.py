"""Central validation engine executing all AntiGravity 2.29.0 validators."""

from __future__ import annotations

from pathlib import Path

from scripts.validation.hooks_validator import validate_hooks
from scripts.validation.mcp_validator import validate_mcp_config
from scripts.validation.models import ValidationReport
from scripts.validation.plugin_validator import validate_plugin
from scripts.validation.prompt_validator import validate_prompts
from scripts.validation.rules_validator import validate_rules
from scripts.validation.secret_hygiene_validator import validate_secret_hygiene
from scripts.validation.skills_validator import validate_skills
from scripts.validation.supply_chain_validator import validate_supply_chain
from scripts.validation.tool_schema_validator import validate_tool_schemas


def validate_all(
    repo_root: Path | str | None = None,
    strict: bool = False,
    fix: bool = False,
    known_tools: dict[str, list[str]] | None = None,
) -> ValidationReport:
    """Run all AntiGravity 2.29.0 validation checks against target repository.

    Args:
        repo_root: Repository root path (defaults to current working directory).
        strict: If True, treats warnings as failure errors.
        fix: If True, automatically remediates fixable issues (like executable bits).
        known_tools: Optional mapping of MCP servers to known tool names.

    Returns:
        ValidationReport containing all discovered issues and summary metrics.
    """
    root = Path(repo_root).resolve() if repo_root is not None else Path.cwd().resolve()
    report = ValidationReport(strict=strict)

    validate_skills(root, report, fix=fix)
    validate_rules(root, report)
    validate_hooks(root, report, fix=fix)
    validate_mcp_config(root, report, known_tools=known_tools)
    validate_plugin(root, report)
    validate_prompts(root, report)
    validate_tool_schemas(root, report)
    validate_secret_hygiene(root, report)
    validate_supply_chain(root, report)

    return report
