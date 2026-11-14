"""Shared fixtures, specification constants, and oracle validators for E2E tests."""

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.validation.codes import ErrorCode
from scripts.validation.models import Severity, ValidationIssue, ValidationReport


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
RULES_DIR = REPO_ROOT / "rules"
HOOKS_FILE = REPO_ROOT / "hooks.json"
MCP_CONFIG_FILE = REPO_ROOT / "mcp_config.json"
PLUGIN_FILE = REPO_ROOT / "plugin.json"
CI_WORKFLOW_FILE = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PRE_COMMIT_FILE = REPO_ROOT / ".pre-commit-config.yaml"
RUN_LOCAL_CI_FILE = REPO_ROOT / "scripts" / "ci" / "run_local_ci.sh"
VALIDATE_CLI_FILE = REPO_ROOT / "scripts" / "validate_agentic_settings.py"

MAX_FILE_BYTES: int = 24_000
MAX_RULES_TOKEN_BUDGET: int = 20_000
MAX_TOOL_NAME_LENGTH: int = 64
MIN_SKILL_DESCRIPTION_LENGTH: int = 20

ALLOWED_SKILL_SUBDIRECTORIES: set[str] = {
    "scripts",
    "examples",
    "resources",
    "references",
}

ALLOWED_RULE_TRIGGERS: set[str] = {
    "ALWAYS_ON",
    "MODEL_DECISION",
    "GLOB",
    "MANUAL",
    "always_on",
    "model_decision",
    "glob",
    "manual",
}

ALLOWED_HOOK_EVENTS: set[str] = {
    "SessionStart",
    "PreToolUse",
    "PostToolUse",
    "PreInvocation",
    "PostInvocation",
    "Stop",
}

MANDATORY_PRE_COMMIT_HYGIENE_HOOKS: set[str] = {
    "trailing-whitespace",
    "end-of-file-fixer",
    "check-yaml",
    "check-toml",
    "check-json",
    "check-merge-conflict",
    "check-added-large-files",
    "check-case-conflict",
    "check-symlinks",
    "destroyed-symlinks",
    "detect-private-key",
    "mixed-line-ending",
    "check-ast",
    "debug-statements",
}

REJECTED_HEIMDALL_HOOKS: set[str] = {
    "validate-mathjax-markdown",
    "check-jupyter-output",
    "check-scenario-configs",
    "sort-pyproject-toml",
    "run-invariant-gates",
    "build-dist",
}

RULESET_STATUS_CHECK_NAME: str = "Validate & Test (${{ matrix.os }})"
CI_MATRIX_OS: set[str] = {"ubuntu-24.04", "macos-latest"}

BUILTIN_MCP_PLACEHOLDERS: set[str] = {"PLUGIN_ROOT", "PLUGIN_DATA"}
TOOL_NAME_PATTERN: re.Pattern[str] = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
SKILL_NAME_PATTERN: re.Pattern[str] = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SEMVER_PATTERN: re.Pattern[str] = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
VAR_PLACEHOLDER_PATTERN: re.Pattern[str] = re.compile(r"\$\{([A-Za-z0-9_]+)\}")


def split_skill_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split frontmatter and markdown body from SKILL.md content.

    Args:
        text: Entire text of SKILL.md.

    Returns:
        Tuple of (frontmatter dictionary, markdown body string).

    Raises:
        ValueError: If frontmatter framing is missing or malformed.
    """
    if not text.startswith("---\n"):
        raise ValueError(
            "SKILL.md must begin with YAML frontmatter delimiter --- on line 1"
        )
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        raise ValueError("SKILL.md missing closing YAML frontmatter delimiter ---")
    raw_yaml = parts[1]
    body = parts[2].lstrip("\n")
    parsed = yaml.safe_load(raw_yaml)
    if not isinstance(parsed, dict):
        raise ValueError("Skill frontmatter must parse to a dictionary")
    return parsed, body


def estimate_token_count(text: str) -> int:
    """Estimate token count for a text string using standard word/subword heuristic.

    Args:
        text: Input string.

    Returns:
        Estimated number of tokens.
    """
    words = len(text.split())
    char_tokens = len(text) // 4
    return max(words, char_tokens)


def oracle_validate_skill(skill_dir: Path) -> list[ValidationIssue]:
    """Authoritative AntiGravity 2.29.0 oracle validator for a skill directory.

    Args:
        skill_dir: Path to directory containing skill.

    Returns:
        List of ValidationIssue objects discovered.
    """
    issues: list[ValidationIssue] = []
    skill_file = skill_dir / "SKILL.md"

    if not skill_file.is_file():
        issues.append(
            ValidationIssue(
                code=ErrorCode.SKL001,
                message=f"Missing SKILL.md in {skill_dir.name}",
                severity=Severity.ERROR,
                path=skill_dir,
            )
        )
        return issues

    content_bytes = skill_file.read_bytes()
    try:
        content_text = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        issues.append(
            ValidationIssue(
                code=ErrorCode.SKL002,
                message="SKILL.md is not valid UTF-8 text",
                severity=Severity.ERROR,
                path=skill_file,
            )
        )
        return issues

    try:
        frontmatter, body = split_skill_frontmatter(content_text)
    except ValueError as exc:
        issues.append(
            ValidationIssue(
                code=ErrorCode.SKL002,
                message=str(exc),
                severity=Severity.ERROR,
                path=skill_file,
            )
        )
        return issues

    name = frontmatter.get("name")
    if not name or not isinstance(name, str):
        issues.append(
            ValidationIssue(
                code=ErrorCode.SKL003,
                message="Missing or invalid skill name in frontmatter",
                severity=Severity.ERROR,
                path=skill_file,
            )
        )
    elif name != skill_dir.name:
        issues.append(
            ValidationIssue(
                code=ErrorCode.SKL003,
                message=f"Skill name '{name}' does not match directory '{skill_dir.name}'",
                severity=Severity.ERROR,
                path=skill_file,
            )
        )
    elif not SKILL_NAME_PATTERN.match(name):
        issues.append(
            ValidationIssue(
                code=ErrorCode.SKL003,
                message=f"Skill name '{name}' must match ^[a-z0-9]+(-[a-z0-9]+)*$",
                severity=Severity.ERROR,
                path=skill_file,
            )
        )

    desc = frontmatter.get("description")
    if (
        not desc
        or not isinstance(desc, str)
        or len(desc.strip()) < MIN_SKILL_DESCRIPTION_LENGTH
    ):
        issues.append(
            ValidationIssue(
                code=ErrorCode.SKL004,
                message=f"Skill description must be at least {MIN_SKILL_DESCRIPTION_LENGTH} characters",
                severity=Severity.ERROR,
                path=skill_file,
            )
        )

    body_bytes_len = len(body.encode("utf-8"))
    if body_bytes_len > MAX_FILE_BYTES:
        issues.append(
            ValidationIssue(
                code=ErrorCode.SKL005,
                message=f"Skill body size ({body_bytes_len} bytes) exceeds limit of {MAX_FILE_BYTES} bytes",
                severity=Severity.ERROR,
                path=skill_file,
            )
        )

    issues.extend(
        ValidationIssue(
            code=ErrorCode.SKL006,
            message=f"Disallowed subdirectory '{item.name}' inside skill directory",
            severity=Severity.ERROR,
            path=item,
        )
        for item in skill_dir.iterdir()
        if item.is_dir() and item.name not in ALLOWED_SKILL_SUBDIRECTORIES
    )

    return issues


def oracle_validate_rule(
    rule_file: Path, root: Path | None = None
) -> list[ValidationIssue]:
    """Authoritative AntiGravity 2.29.0 oracle validator for a rule file.

    Args:
        rule_file: Path to rule markdown file.
        root: Optional repository root to check placement invariants.

    Returns:
        List of ValidationIssue objects discovered.
    """
    issues: list[ValidationIssue] = []

    if root and (root / "AGENTS.md").exists():
        issues.append(
            ValidationIssue(
                code=ErrorCode.RUL001,
                message="Top-level AGENTS.md placed at plugin root; must be in rules/AGENTS.md",
                severity=Severity.ERROR,
                path=root / "AGENTS.md",
            )
        )

    if not rule_file.is_file():
        return issues

    content_bytes = rule_file.read_bytes()
    if len(content_bytes) > MAX_FILE_BYTES:
        issues.append(
            ValidationIssue(
                code=ErrorCode.RUL004,
                message=f"Rule file size ({len(content_bytes)} bytes) exceeds limit of {MAX_FILE_BYTES} bytes",
                severity=Severity.ERROR,
                path=rule_file,
            )
        )

    text = content_bytes.decode("utf-8", errors="replace")
    if text.startswith("---\n"):
        issues.append(
            ValidationIssue(
                code=ErrorCode.RUL002,
                message="Standalone AGENTS.md must be plain Markdown without YAML frontmatter",
                severity=Severity.ERROR,
                path=rule_file,
            )
        )

    tokens = estimate_token_count(text)
    if tokens > MAX_RULES_TOKEN_BUDGET:
        issues.append(
            ValidationIssue(
                code=ErrorCode.RUL004,
                message=f"Rule token count ({tokens}) exceeds budget of {MAX_RULES_TOKEN_BUDGET}",
                severity=Severity.ERROR,
                path=rule_file,
            )
        )

    return issues


def oracle_validate_hooks(
    hooks_data: dict[str, Any], path: Path
) -> list[ValidationIssue]:
    """Authoritative AntiGravity 2.29.0 oracle validator for hooks data.

    Args:
        hooks_data: Parsed JSON data from hooks.json.
        path: Path to hooks.json.

    Returns:
        List of ValidationIssue objects discovered.
    """
    issues: list[ValidationIssue] = []

    for hook_name, hook_cfg in hooks_data.items():
        if not isinstance(hook_cfg, dict):
            issues.append(
                ValidationIssue(
                    code=ErrorCode.HOK001,
                    message=f"Hook configuration for '{hook_name}' must be an object",
                    severity=Severity.ERROR,
                    path=path,
                )
            )
            continue

        for event_key, event_val in hook_cfg.items():
            if event_key == "enabled":
                continue
            if event_key not in ALLOWED_HOOK_EVENTS:
                issues.append(
                    ValidationIssue(
                        code=ErrorCode.HOK002,
                        message=f"Invalid lifecycle event '{event_key}' in hook '{hook_name}'",
                        severity=Severity.ERROR,
                        path=path,
                    )
                )
                continue

            if event_key in {"PreToolUse", "PostToolUse"}:
                if not isinstance(event_val, list):
                    issues.append(
                        ValidationIssue(
                            code=ErrorCode.HOK003,
                            message=f"Event '{event_key}' must be a list of matcher objects",
                            severity=Severity.ERROR,
                            path=path,
                        )
                    )
                    continue
                for item in event_val:
                    if (
                        not isinstance(item, dict)
                        or "matcher" not in item
                        or "hooks" not in item
                    ):
                        issues.append(
                            ValidationIssue(
                                code=ErrorCode.HOK003,
                                message=f"Tool event '{event_key}' missing required 'matcher' or 'hooks'",
                                severity=Severity.ERROR,
                                path=path,
                            )
                        )
                    else:
                        for handler in item.get("hooks", []):
                            _validate_hook_handler(handler, path, issues)
            elif isinstance(event_val, list):
                for handler in event_val:
                    _validate_hook_handler(handler, path, issues)

    return issues


def _validate_hook_handler(
    handler: object, path: Path, issues: list[ValidationIssue]
) -> None:
    """Validate a single hook handler specification.

    Args:
        handler: Handler dictionary or object.
        path: Path to hooks.json.
        issues: Target issue list to append to.
    """
    if not isinstance(handler, dict):
        issues.append(
            ValidationIssue(
                code=ErrorCode.HOK004,
                message="Handler must be an object",
                severity=Severity.ERROR,
                path=path,
            )
        )
        return

    cmd = handler.get("command")
    if not cmd or not isinstance(cmd, str):
        issues.append(
            ValidationIssue(
                code=ErrorCode.HOK004,
                message="Handler missing required 'command' string",
                severity=Severity.ERROR,
                path=path,
            )
        )

    timeout = handler.get("timeout")
    if timeout is not None and (not isinstance(timeout, int) or timeout <= 0):
        issues.append(
            ValidationIssue(
                code=ErrorCode.HOK005,
                message=f"Handler timeout '{timeout}' must be a positive integer",
                severity=Severity.ERROR,
                path=path,
            )
        )


def oracle_validate_mcp_config(
    config_data: dict[str, Any], path: Path
) -> list[ValidationIssue]:
    """Authoritative AntiGravity 2.29.0 oracle validator for MCP configuration.

    Args:
        config_data: Parsed JSON data from mcp_config.json.
        path: Path to mcp_config.json.

    Returns:
        List of ValidationIssue objects discovered.
    """
    issues: list[ValidationIssue] = []

    servers = config_data.get("mcpServers")
    if not servers or not isinstance(servers, dict):
        issues.append(
            ValidationIssue(
                code=ErrorCode.MCP002,
                message="Missing or malformed 'mcpServers' object",
                severity=Severity.ERROR,
                path=path,
            )
        )
        return issues

    for server_name, server_def in servers.items():
        if not isinstance(server_def, dict):
            continue

        url = server_def.get("url") or server_def.get("serverUrl")
        cmd = server_def.get("command")

        if not url and not cmd:
            issues.append(
                ValidationIssue(
                    code=ErrorCode.MCP003,
                    message=f"Server '{server_name}' missing both 'command' and 'url' transports",
                    severity=Severity.ERROR,
                    path=path,
                )
            )

        if url and isinstance(url, str) and "/sse" in url.lower():
            issues.append(
                ValidationIssue(
                    code=ErrorCode.MCP004,
                    message=f"Server '{server_name}' uses prohibited legacy SSE URL transport",
                    severity=Severity.ERROR,
                    path=path,
                )
            )

        declared_vars: dict[str, dict[str, Any]] = {}
        vars_list = server_def.get("variables", [])
        if isinstance(vars_list, list):
            for v in vars_list:
                if isinstance(v, dict) and "name" in v:
                    v_name = v["name"]
                    declared_vars[v_name] = v
                    if not v.get("title") or not v.get("description"):
                        issues.append(
                            ValidationIssue(
                                code=ErrorCode.MCP007,
                                message=f"Variable '{v_name}' in server '{server_name}' missing required 'title' or 'description'",
                                severity=Severity.ERROR,
                                path=path,
                            )
                        )

        server_text = json.dumps(server_def)
        used_vars = set(VAR_PLACEHOLDER_PATTERN.findall(server_text))
        issues.extend(
            ValidationIssue(
                code=ErrorCode.MCP005,
                message=f"Server '{server_name}' uses undeclared placeholder variable '${{{u}}}'",
                severity=Severity.ERROR,
                path=path,
            )
            for u in used_vars
            if u not in BUILTIN_MCP_PLACEHOLDERS and u not in declared_vars
        )

        tools = server_def.get("tools", [])
        if isinstance(tools, list):
            for tool_item in tools:
                t_name = (
                    tool_item
                    if isinstance(tool_item, str)
                    else tool_item.get("name", "")
                )
                namespaced_tool = f"mcp_{server_name}_{t_name}"
                if len(
                    namespaced_tool
                ) > MAX_TOOL_NAME_LENGTH or not TOOL_NAME_PATTERN.match(
                    namespaced_tool
                ):
                    issues.append(
                        ValidationIssue(
                            code=ErrorCode.MCP008,
                            message=f"Tool identifier '{namespaced_tool}' exceeds {MAX_TOOL_NAME_LENGTH} chars or violates regex",
                            severity=Severity.ERROR,
                            path=path,
                        )
                    )

    return issues


def oracle_validate_plugin_manifest(
    manifest_data: dict[str, Any], path: Path, root: Path
) -> list[ValidationIssue]:
    """Authoritative AntiGravity 2.29.0 oracle validator for plugin manifest.

    Args:
        manifest_data: Parsed JSON data from plugin.json.
        path: Path to plugin.json.
        root: Plugin root directory.

    Returns:
        List of ValidationIssue objects discovered.
    """
    issues: list[ValidationIssue] = []

    name = manifest_data.get("name")
    if not name or not isinstance(name, str) or not SKILL_NAME_PATTERN.match(name):
        issues.append(
            ValidationIssue(
                code=ErrorCode.PLG002,
                message=f"Plugin name '{name}' must match ^[a-z0-9]+(-[a-z0-9]+)*$",
                severity=Severity.ERROR,
                path=path,
            )
        )

    version = manifest_data.get("version")
    if not version or not isinstance(version, str) or not SEMVER_PATTERN.match(version):
        issues.append(
            ValidationIssue(
                code=ErrorCode.PLG003,
                message=f"Plugin version '{version}' violates Semantic Versioning (X.Y.Z)",
                severity=Severity.ERROR,
                path=path,
            )
        )

    logo = manifest_data.get("logo")
    if logo and isinstance(logo, str) and not logo.startswith("http"):
        logo_path = root / logo
        if not logo_path.is_file():
            issues.append(
                ValidationIssue(
                    code=ErrorCode.PLG004,
                    message=f"Plugin logo file '{logo}' does not exist on disk",
                    severity=Severity.ERROR,
                    path=path,
                )
            )

    license_id = manifest_data.get("license")
    if not license_id or not isinstance(license_id, str):
        issues.append(
            ValidationIssue(
                code=ErrorCode.PLG005,
                message="Plugin missing valid 'license' field",
                severity=Severity.ERROR,
                path=path,
            )
        )

    return issues


def oracle_validate_ci_workflow(
    workflow_data: dict[str, Any], path: Path
) -> list[ValidationIssue]:
    """Authoritative oracle validator for GitHub Actions CI workflow.

    Args:
        workflow_data: Parsed YAML from .github/workflows/ci.yml.
        path: Path to workflow file.

    Returns:
        List of ValidationIssue objects discovered.
    """
    issues: list[ValidationIssue] = []

    jobs = workflow_data.get("jobs", {})
    if not isinstance(jobs, dict) or not jobs:
        issues.append(
            ValidationIssue(
                code="CI001",
                message="CI workflow missing jobs definition",
                severity=Severity.ERROR,
                path=path,
            )
        )
        return issues

    found_ruleset_check = False
    for job_id, job_cfg in jobs.items():
        if not isinstance(job_cfg, dict):
            continue
        job_name = job_cfg.get("name", "")
        if RULESET_STATUS_CHECK_NAME in job_name or job_id == "validate-and-test":
            found_ruleset_check = True

        strategy = job_cfg.get("strategy", {})
        matrix = strategy.get("matrix", {})
        os_list = set(matrix.get("os", []))
        if os_list and not CI_MATRIX_OS.issubset(os_list):
            issues.append(
                ValidationIssue(
                    code="CI002",
                    message=f"CI matrix must include {CI_MATRIX_OS}, found {os_list}",
                    severity=Severity.ERROR,
                    path=path,
                )
            )

    if not found_ruleset_check:
        issues.append(
            ValidationIssue(
                code="CI003",
                message=f"CI workflow missing Ruleset 26711811 status check name '{RULESET_STATUS_CHECK_NAME}'",
                severity=Severity.ERROR,
                path=path,
            )
        )

    return issues


def oracle_validate_pre_commit_config(
    config_data: dict[str, Any], path: Path
) -> list[ValidationIssue]:
    """Authoritative oracle validator for pre-commit configuration.

    Args:
        config_data: Parsed YAML from .pre-commit-config.yaml.
        path: Path to configuration file.

    Returns:
        List of ValidationIssue objects discovered.
    """
    issues: list[ValidationIssue] = []

    repos = config_data.get("repos", [])
    if not isinstance(repos, list) or not repos:
        issues.append(
            ValidationIssue(
                code="PC001",
                message="Pre-commit config missing 'repos' list",
                severity=Severity.ERROR,
                path=path,
            )
        )
        return issues

    discovered_hooks: set[str] = set()
    found_pixi: bool = False

    for repo_entry in repos:
        if not isinstance(repo_entry, dict):
            continue
        repo_url = repo_entry.get("repo", "")
        hooks = repo_entry.get("hooks", [])
        for h in hooks:
            if not isinstance(h, dict):
                continue
            h_id = h.get("id", "")
            discovered_hooks.add(h_id)
            entry = str(h.get("entry", ""))
            if "pixi" in entry.lower() or "pixi" in repo_url.lower():
                found_pixi = True

            if h_id in REJECTED_HEIMDALL_HOOKS:
                issues.append(
                    ValidationIssue(
                        code="PC002",
                        message=f"Inapplicable heimdall-astro hook '{h_id}' must not be adopted",
                        severity=Severity.ERROR,
                        path=path,
                    )
                )

    if found_pixi:
        issues.append(
            ValidationIssue(
                code="PC003",
                message="Pre-commit configuration references pixi in pure uv repository",
                severity=Severity.ERROR,
                path=path,
            )
        )

    return issues


@pytest.fixture
def repo_root() -> Path:
    """Fixture providing repository root path.

    Returns:
        Absolute Path to repository root.
    """
    return REPO_ROOT


@pytest.fixture
def clean_validation_report() -> ValidationReport:
    """Fixture providing a fresh empty ValidationReport.

    Returns:
        New ValidationReport instance.
    """
    return ValidationReport()


@pytest.fixture
def tmp_agentic_workspace(tmp_path: Path) -> Path:
    """Fixture generating a compliant minimal AntiGravity 2.29.0 workspace for boundary testing.

    Args:
        tmp_path: Pytest temporary directory.

    Returns:
        Path to initialized workspace root.
    """
    ws = tmp_path / "mock_workspace"
    ws.mkdir(parents=True)

    # 1. Plugin manifest
    plugin_data = {
        "$schema": "https://antigravity.google/schemas/v1/plugin.json",
        "name": "mock-plugin",
        "displayName": "Mock Plugin",
        "version": "1.0.0",
        "description": "Mock plugin for automated boundary testing.",
        "logo": "assets/logo.svg",
        "author": {"name": "Tester"},
        "license": "Apache-2.0",
    }
    (ws / "plugin.json").write_text(json.dumps(plugin_data, indent=2), encoding="utf-8")
    assets_dir = ws / "assets"
    assets_dir.mkdir()
    (assets_dir / "logo.svg").write_text("<svg></svg>", encoding="utf-8")

    # 2. Rules
    rules_dir = ws / "rules"
    rules_dir.mkdir()
    (rules_dir / "AGENTS.md").write_text(
        "# Mock Safety Invariants\n\nMandatory test rules without frontmatter.\n",
        encoding="utf-8",
    )

    # 3. Skills
    skill_dir = ws / "skills" / "mock-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: mock-skill\ndescription: Mock skill running test procedures.\n---\n\n## Instructions\n\nRun test steps.\n",
        encoding="utf-8",
    )

    # 4. Hooks
    hooks_data = {
        "mock-guard": {
            "enabled": True,
            "PreToolUse": [
                {
                    "matcher": "run_command",
                    "hooks": [{"type": "command", "command": "true", "timeout": 5}],
                }
            ],
        }
    }
    (ws / "hooks.json").write_text(json.dumps(hooks_data, indent=2), encoding="utf-8")

    # 5. MCP Config
    mcp_data = {
        "mcpServers": {
            "mock-server": {
                "command": "uv",
                "args": ["run", "echo", "hello"],
                "env": {"TEST_VAR": "${TEST_VAR}"},
                "variables": [
                    {
                        "name": "TEST_VAR",
                        "title": "Test Variable",
                        "description": "Variable for test isolation",
                    }
                ],
            }
        }
    }
    (ws / "mcp_config.json").write_text(
        json.dumps(mcp_data, indent=2), encoding="utf-8"
    )

    # 6. Agents discovery
    agents_dir = ws / ".agents"
    agents_dir.mkdir()
    (agents_dir / "skills.json").write_text(
        json.dumps({"entries": [{"path": "skills"}]}), encoding="utf-8"
    )
    (agents_dir / "rules.json").write_text(
        json.dumps({"entries": [{"path": "rules"}]}), encoding="utf-8"
    )

    return ws
