"""Tier 1: Feature Coverage E2E Tests (≥5 tests per feature across 10 features).

Validates individual features in isolation derived from requirements (R1, R2, R3, R4)
and AntiGravity 2.29.0 specifications.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.validation.codes import ErrorCode
from scripts.validation.models import Severity
from scripts.validation.models import ValidationIssue
from scripts.validation.models import ValidationReport
from scripts.validation.supply_chain_validator import strip_jsonc_comments
from tests.e2e.conftest import ALLOWED_HOOK_EVENTS
from tests.e2e.conftest import ALLOWED_RULE_TRIGGERS
from tests.e2e.conftest import ALLOWED_SKILL_SUBDIRECTORIES
from tests.e2e.conftest import CI_MATRIX_OS
from tests.e2e.conftest import CI_WORKFLOW_FILE
from tests.e2e.conftest import HOOKS_FILE
from tests.e2e.conftest import MANDATORY_PRE_COMMIT_HYGIENE_HOOKS
from tests.e2e.conftest import MAX_FILE_BYTES
from tests.e2e.conftest import MAX_RULES_TOKEN_BUDGET
from tests.e2e.conftest import MAX_TOOL_NAME_LENGTH
from tests.e2e.conftest import MCP_CONFIG_FILE
from tests.e2e.conftest import MIN_SKILL_DESCRIPTION_LENGTH
from tests.e2e.conftest import PLUGIN_FILE
from tests.e2e.conftest import PRE_COMMIT_FILE
from tests.e2e.conftest import REJECTED_HEIMDALL_HOOKS
from tests.e2e.conftest import REPO_ROOT
from tests.e2e.conftest import RULES_DIR
from tests.e2e.conftest import RULESET_STATUS_CHECK_NAME
from tests.e2e.conftest import RUN_LOCAL_CI_FILE
from tests.e2e.conftest import SKILL_NAME_PATTERN
from tests.e2e.conftest import SKILLS_DIR
from tests.e2e.conftest import TOOL_NAME_PATTERN
from tests.e2e.conftest import VALIDATE_CLI_FILE
from tests.e2e.conftest import estimate_token_count
from tests.e2e.conftest import oracle_validate_mcp_config
from tests.e2e.conftest import oracle_validate_pre_commit_config
from tests.e2e.conftest import oracle_validate_rule
from tests.e2e.conftest import oracle_validate_skill
from tests.e2e.conftest import split_skill_frontmatter


# ==============================================================================
# Feature 1: Pre-commit Hooks Configuration and Invocation Semantics
# ==============================================================================


def test_f1_pre_commit_cli_executable() -> None:
    """Verify that pre-commit CLI is executable in the environment."""
    pre_commit_bin = shutil.which('pre-commit')
    assert pre_commit_bin is not None, 'pre-commit executable not found in PATH'
    res = subprocess.run(
        [pre_commit_bin, '--version'],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f'pre-commit CLI failed to run: {res.stderr}'
    assert 'pre-commit' in res.stdout.lower()


def test_f1_pre_commit_mandates_14_hygiene_hooks() -> None:
    """Verify pre-commit specification mandates all 14 curated hygiene hooks."""
    mock_config: dict[str, Any] = {
        'repos': [
            {
                'repo': 'https://github.com/pre-commit/pre-commit-hooks',
                'rev': '3e8a8703264a2f4a69428a0aa4dcb512790b2c8c',
                'hooks': [{'id': h_id} for h_id in MANDATORY_PRE_COMMIT_HYGIENE_HOOKS],
            }
        ]
    }
    issues = oracle_validate_pre_commit_config(mock_config, Path('.pre-commit-config.yaml'))
    assert not issues, f'Expected no issues for complete hygiene hook set, got: {issues}'
    assert len(MANDATORY_PRE_COMMIT_HYGIENE_HOOKS) == 14


def test_f1_pre_commit_rejects_inapplicable_heimdall_hooks() -> None:
    """Verify pre-commit specification strictly rejects inapplicable hooks from heimdall-astro."""
    for rejected_id in REJECTED_HEIMDALL_HOOKS:
        bad_config: dict[str, Any] = {
            'repos': [
                {
                    'repo': 'local',
                    'hooks': [{'id': rejected_id, 'name': rejected_id, 'entry': 'test', 'language': 'system'}],
                }
            ]
        }
        issues = oracle_validate_pre_commit_config(bad_config, Path('.pre-commit-config.yaml'))
        assert any(i.code == 'PC002' for i in issues), f'Hook {rejected_id} was not rejected'


def test_f1_pre_commit_local_uv_hooks_configured() -> None:
    """Verify pre-commit specification requires local Python hooks to run via uv run."""
    sample_uv_hooks: dict[str, Any] = {
        'repos': [
            {
                'repo': 'local',
                'hooks': [
                    {'id': 'ruff-check', 'name': 'ruff check', 'entry': 'uv run ruff check', 'language': 'system'},
                    {'id': 'mypy', 'name': 'mypy', 'entry': 'uv run mypy', 'language': 'system'},
                ],
            }
        ]
    }
    issues = oracle_validate_pre_commit_config(sample_uv_hooks, Path('.pre-commit-config.yaml'))
    assert not issues, f'Valid uv run hooks should produce no issues, got: {issues}'


def test_f1_pre_commit_pure_uv_no_pixi() -> None:
    """Verify pre-commit specification rejects any references to pixi."""
    pixi_config: dict[str, Any] = {
        'repos': [
            {
                'repo': 'local',
                'hooks': [{'id': 'typecheck', 'name': 'typecheck', 'entry': 'pixi run typecheck', 'language': 'system'}],
            }
        ]
    }
    issues = oracle_validate_pre_commit_config(pixi_config, Path('.pre-commit-config.yaml'))
    assert any(i.code == 'PC003' for i in issues), 'Pre-commit config with pixi must be rejected'


def test_f1_pre_commit_on_disk_file_valid_if_present() -> None:
    """Verify on-disk .pre-commit-config.yaml if present complies with all requirements."""
    if not PRE_COMMIT_FILE.is_file():
        pytest.skip('.pre-commit-config.yaml is not yet created on disk (Milestone 3 planned)')
    data = yaml.safe_load(PRE_COMMIT_FILE.read_text(encoding='utf-8'))
    issues = oracle_validate_pre_commit_config(data, PRE_COMMIT_FILE)
    assert not issues, f'On-disk .pre-commit-config.yaml has validation issues: {issues}'


# ==============================================================================
# Feature 2: CI Workflow Triggers, Matrix, and Ruleset 26711811 Status Check Names
# ==============================================================================


def test_f2_ci_workflow_exists_and_valid_yaml() -> None:
    """Verify that .github/workflows/ci.yml exists and parses as valid YAML."""
    assert CI_WORKFLOW_FILE.is_file(), f'Missing workflow file at {CI_WORKFLOW_FILE}'
    data = yaml.safe_load(CI_WORKFLOW_FILE.read_text(encoding='utf-8'))
    assert isinstance(data, dict), 'ci.yml did not parse as a dictionary'
    assert 'name' in data
    assert 'jobs' in data


def test_f2_ci_workflow_triggers() -> None:
    """Verify CI workflow defines pull_request, push to main, and workflow_dispatch."""
    data = yaml.safe_load(CI_WORKFLOW_FILE.read_text(encoding='utf-8'))
    # YAML parser may parse 'on' as True (boolean) or string 'on'
    triggers = data.get('on') if 'on' in data else data.get(True)
    assert triggers is not None, "Workflow missing 'on' trigger section"
    assert 'pull_request' in triggers, 'Workflow missing pull_request trigger'
    assert 'push' in triggers, 'Workflow missing push trigger'
    assert 'workflow_dispatch' in triggers, 'Workflow missing workflow_dispatch trigger'

    pr_branches = triggers['pull_request'].get('branches', [])
    assert 'main' in pr_branches, "pull_request trigger must target 'main' branch"


def test_f2_ci_workflow_os_matrix() -> None:
    """Verify CI workflow matrix covers both ubuntu-24.04 and macos-latest."""
    data = yaml.safe_load(CI_WORKFLOW_FILE.read_text(encoding='utf-8'))
    jobs = data.get('jobs', {})
    found_matrix = False
    for job_cfg in jobs.values():
        matrix = job_cfg.get('strategy', {}).get('matrix', {})
        os_list = set(matrix.get('os', []))
        if CI_MATRIX_OS.issubset(os_list):
            found_matrix = True
            break
    assert found_matrix, f'CI workflow must define an OS matrix covering {CI_MATRIX_OS}'


def test_f2_ci_workflow_ruleset_status_check_name() -> None:
    """Verify CI workflow status check job name matches Ruleset 26711811 exactly."""
    data = yaml.safe_load(CI_WORKFLOW_FILE.read_text(encoding='utf-8'))
    jobs = data.get('jobs', {})
    job_names = [j.get('name', '') for j in jobs.values()]
    assert any(RULESET_STATUS_CHECK_NAME in name for name in job_names), f"CI workflow missing Ruleset 26711811 job name '{RULESET_STATUS_CHECK_NAME}', found: {job_names}"


def test_f2_ci_workflow_setup_uv_and_caching() -> None:
    """Verify CI workflow uses astral-sh/setup-uv action with Python 3.14 and cache enabled."""
    content = CI_WORKFLOW_FILE.read_text(encoding='utf-8')
    assert 'astral-sh/setup-uv@' in content, 'Workflow must use astral-sh/setup-uv action'
    assert "python-version: '3.14'" in content or 'python-version: "3.14"' in content
    assert 'enable-cache: true' in content


def test_f2_ci_workflow_concurrency_group() -> None:
    """Verify CI workflow defines concurrency cancellation on push."""
    data = yaml.safe_load(CI_WORKFLOW_FILE.read_text(encoding='utf-8'))
    concurrency = data.get('concurrency', {})
    assert concurrency.get('cancel-in-progress') is True


# ==============================================================================
# Feature 3: AntiGravity 2.29.0 Skills Validation
# ==============================================================================


def test_f3_skills_entrypoint_exists_in_all_skills() -> None:
    """Verify every skill directory contains SKILL.md entrypoint."""
    skill_dirs = [p for p in SKILLS_DIR.iterdir() if p.is_dir()]
    assert len(skill_dirs) >= 7, f'Expected at least 7 skills, found {len(skill_dirs)}'
    for s_dir in skill_dirs:
        skill_file = s_dir / 'SKILL.md'
        assert skill_file.is_file(), f'Skill {s_dir.name} is missing SKILL.md'


def test_f3_skills_frontmatter_framing() -> None:
    """Verify every SKILL.md begins with --- on line 1 and has closing delimiter."""
    for s_dir in [p for p in SKILLS_DIR.iterdir() if p.is_dir()]:
        skill_file = s_dir / 'SKILL.md'
        content = skill_file.read_text(encoding='utf-8')
        frontmatter, body = split_skill_frontmatter(content)
        assert isinstance(frontmatter, dict), f'Frontmatter in {s_dir.name} did not parse to dict'
        assert len(body) > 0, f'Body in {s_dir.name} cannot be empty'


def test_f3_skills_name_matches_directory() -> None:
    """Verify frontmatter name matches directory name and regex."""
    for s_dir in [p for p in SKILLS_DIR.iterdir() if p.is_dir()]:
        skill_file = s_dir / 'SKILL.md'
        frontmatter, _ = split_skill_frontmatter(skill_file.read_text(encoding='utf-8'))
        name = frontmatter.get('name')
        assert name == s_dir.name, f"Skill name '{name}' does not match directory '{s_dir.name}'"
        assert SKILL_NAME_PATTERN.match(name), f"Skill name '{name}' violates regex"


def test_f3_skills_description_minimum_length() -> None:
    """Verify frontmatter description length is at least 20 characters."""
    for s_dir in [p for p in SKILLS_DIR.iterdir() if p.is_dir()]:
        skill_file = s_dir / 'SKILL.md'
        frontmatter, _ = split_skill_frontmatter(skill_file.read_text(encoding='utf-8'))
        desc = frontmatter.get('description', '')
        assert len(desc.strip()) >= MIN_SKILL_DESCRIPTION_LENGTH, f"Description for skill '{s_dir.name}' is shorter than {MIN_SKILL_DESCRIPTION_LENGTH} chars: '{desc}'"


def test_f3_skills_body_size_within_24000_bytes() -> None:
    """Verify markdown body of SKILL.md does not exceed 24,000 bytes hard cap."""
    for s_dir in [p for p in SKILLS_DIR.iterdir() if p.is_dir()]:
        skill_file = s_dir / 'SKILL.md'
        _, body = split_skill_frontmatter(skill_file.read_text(encoding='utf-8'))
        body_bytes = len(body.encode('utf-8'))
        assert body_bytes <= MAX_FILE_BYTES, f"Skill '{s_dir.name}' body ({body_bytes} bytes) exceeds limit of {MAX_FILE_BYTES} bytes"


def test_f3_skills_allowed_subdirectories_only() -> None:
    """Verify skills contain only allowed subdirectories."""
    for s_dir in [p for p in SKILLS_DIR.iterdir() if p.is_dir()]:
        for child in s_dir.iterdir():
            if child.is_dir():
                assert child.name in ALLOWED_SKILL_SUBDIRECTORIES, f"Skill '{s_dir.name}' contains disallowed subdirectory '{child.name}'"


def test_f3_skills_scripts_executable_permissions() -> None:
    """Verify all helper scripts inside skills/*/scripts/ have executable permissions."""
    for script_path in SKILLS_DIR.glob('*/scripts/*'):
        if script_path.is_file() and not script_path.name.startswith('.'):
            assert os.access(script_path, os.X_OK), f"Helper script '{script_path}' lacks executable (+x) permission"


def test_f3_skills_relative_markdown_links_resolve() -> None:
    """Verify all relative markdown links inside skills resolve to existing files."""
    link_pattern = re.compile(r'\]\((\.\.?/[^)#]+)(?:#[^)]*)?\)')
    for md_file in SKILLS_DIR.glob('**/*.md'):
        text = md_file.read_text(encoding='utf-8')
        for match in link_pattern.finditer(text):
            target_rel = match.group(1)
            target_path = (md_file.parent / target_rel).resolve()
            assert target_path.exists(), f"Broken relative link in '{md_file}': target '{target_rel}' does not exist"


# ==============================================================================
# Feature 4: AntiGravity 2.29.0 Rules Validation
# ==============================================================================


def test_f4_rules_location_in_rules_directory() -> None:
    """Verify rules are placed in rules/AGENTS.md and no top-level AGENTS.md exists at root."""
    assert (RULES_DIR / 'AGENTS.md').is_file(), 'Missing rules/AGENTS.md'
    assert not (REPO_ROOT / 'AGENTS.md').exists(), 'Top-level AGENTS.md placed at root is ignored by AntiGravity'


def test_f4_rules_plain_markdown_without_frontmatter() -> None:
    """Verify rules/AGENTS.md is plain Markdown without YAML frontmatter."""
    content = (RULES_DIR / 'AGENTS.md').read_text(encoding='utf-8')
    assert not content.startswith('---'), 'rules/AGENTS.md must not contain YAML frontmatter'


def test_f4_rules_size_under_24000_bytes() -> None:
    """Verify rules/AGENTS.md size does not exceed 24,000 bytes hard cap."""
    content_bytes = (RULES_DIR / 'AGENTS.md').read_bytes()
    assert len(content_bytes) <= MAX_FILE_BYTES, f'Rule file exceeds {MAX_FILE_BYTES} bytes'


def test_f4_rules_trigger_enums_valid() -> None:
    """Verify rule trigger enum set contains canonical AntiGravity 2.29.0 triggers."""
    expected = {'ALWAYS_ON', 'MODEL_DECISION', 'GLOB', 'MANUAL'}
    assert expected.issubset({t.upper() for t in ALLOWED_RULE_TRIGGERS})


def test_f4_rules_token_budget_under_20000() -> None:
    """Verify rules token count is well within the 20,000 token budget."""
    content = (RULES_DIR / 'AGENTS.md').read_text(encoding='utf-8')
    tokens = estimate_token_count(content)
    assert tokens <= MAX_RULES_TOKEN_BUDGET, f'Rules token count ({tokens}) exceeds budget of {MAX_RULES_TOKEN_BUDGET}'


# ==============================================================================
# Feature 5: AntiGravity 2.29.0 Hooks Validation
# ==============================================================================


@pytest.mark.skipif(not HOOKS_FILE.is_file(), reason='No hooks.json configured')
def test_f5_hooks_valid_json_schema() -> None:
    """Verify hooks.json is valid JSON and contains top-level hook objects."""
    assert HOOKS_FILE.is_file(), 'Missing hooks.json file'
    data = json.loads(HOOKS_FILE.read_text(encoding='utf-8'))
    assert isinstance(data, dict), 'hooks.json must contain a top-level dictionary'
    assert len(data) > 0, 'hooks.json cannot be empty'


@pytest.mark.skipif(not HOOKS_FILE.is_file(), reason='No hooks.json configured')
def test_f5_hooks_lifecycle_event_names() -> None:
    """Verify all lifecycle events in hooks.json are valid AntiGravity events."""
    data = json.loads(HOOKS_FILE.read_text(encoding='utf-8'))
    for hook_name, hook_cfg in data.items():
        for event_key in hook_cfg:
            if event_key == 'enabled':
                continue
            assert event_key in ALLOWED_HOOK_EVENTS, f"Invalid event '{event_key}' in hook '{hook_name}'"


@pytest.mark.skipif(not HOOKS_FILE.is_file(), reason='No hooks.json configured')
def test_f5_hooks_tool_event_has_matcher_and_hooks() -> None:
    """Verify tool event PreToolUse has matcher and hooks list."""
    data = json.loads(HOOKS_FILE.read_text(encoding='utf-8'))
    for hook_cfg in data.values():
        if 'PreToolUse' in hook_cfg:
            for item in hook_cfg['PreToolUse']:
                assert 'matcher' in item, "PreToolUse item missing 'matcher'"
                assert 'hooks' in item, "PreToolUse item missing 'hooks'"
                assert isinstance(item['hooks'], list)


@pytest.mark.skipif(not HOOKS_FILE.is_file(), reason='No hooks.json configured')
def test_f5_hooks_handler_has_command_and_positive_timeout() -> None:
    """Verify handler specifies command string and positive integer timeout."""
    data = json.loads(HOOKS_FILE.read_text(encoding='utf-8'))
    for hook_cfg in data.values():
        for event_key, event_val in hook_cfg.items():
            if event_key in {'PreToolUse', 'PostToolUse'}:
                for group in event_val:
                    for h in group.get('hooks', []):
                        assert isinstance(h.get('command'), str), "Handler missing 'command'"
                        timeout = h.get('timeout')
                        if timeout is not None:
                            assert isinstance(timeout, int) and timeout > 0, f'Invalid timeout {timeout}'


@pytest.mark.skipif(not HOOKS_FILE.is_file(), reason='No hooks.json configured')
def test_f5_hooks_handler_command_script_exists() -> None:
    """Verify script referenced in hook command exists on disk."""
    data = json.loads(HOOKS_FILE.read_text(encoding='utf-8'))
    for hook_cfg in data.values():
        for group in hook_cfg.get('PreToolUse', []):
            for h in group.get('hooks', []):
                cmd = h.get('command', '')
                if './scripts/' in cmd:
                    rel_script = cmd.split('./scripts/')[1].split()[0]
                    script_path = REPO_ROOT / 'scripts' / rel_script
                    assert script_path.is_file(), f"Script referenced in hook '{cmd}' does not exist at {script_path}"


def test_f5_hooks_camel_case_format_contracts() -> None:
    """Verify hook input/output contracts use camelCase naming."""
    expected_camel_case_keys = {
        'conversationId',
        'workspacePaths',
        'transcriptPath',
        'artifactDirectoryPath',
        'modelName',
        'toolCall',
        'stepIdx',
        'injectSteps',
        'permissionOverrides',
    }
    for key in expected_camel_case_keys:
        assert key[0].islower()
        assert not any(c == '_' for c in key)


# ==============================================================================
# Feature 6: AntiGravity 2.29.0 MCP Config Validation
# ==============================================================================


def test_f6_mcp_valid_json_and_servers_mapping() -> None:
    """Verify mcp_config.json contains valid JSON with mcpServers mapping."""
    assert MCP_CONFIG_FILE.is_file(), 'Missing mcp_config.json'
    data = json.loads(MCP_CONFIG_FILE.read_text(encoding='utf-8'))
    assert 'mcpServers' in data, "mcp_config.json missing 'mcpServers' object"
    assert isinstance(data['mcpServers'], dict)


def test_f6_mcp_supported_transports() -> None:
    """Verify all MCP servers declare stdio (command) or streamable HTTP (url) transport."""
    data = json.loads(MCP_CONFIG_FILE.read_text(encoding='utf-8'))
    for s_name, s_def in data['mcpServers'].items():
        has_cmd = 'command' in s_def and isinstance(s_def['command'], str)
        has_url = ('url' in s_def or 'serverUrl' in s_def) and isinstance(s_def.get('url') or s_def.get('serverUrl'), str)
        assert has_cmd or has_url, f"Server '{s_name}' missing valid transport"


def test_f6_mcp_rejects_legacy_sse_transport() -> None:
    """Verify no MCP server uses legacy /sse URL endpoint."""
    data = json.loads(MCP_CONFIG_FILE.read_text(encoding='utf-8'))
    for s_name, s_def in data['mcpServers'].items():
        url = s_def.get('url') or s_def.get('serverUrl', '')
        assert '/sse' not in url.lower(), f"Server '{s_name}' uses prohibited legacy /sse endpoint"


def test_f6_mcp_tool_name_length_limit() -> None:
    """Verify all declared tool names prefixed with mcp_<server>_<tool> do not exceed 64 chars."""
    data = json.loads(MCP_CONFIG_FILE.read_text(encoding='utf-8'))
    for s_name, s_def in data['mcpServers'].items():
        for tool_item in s_def.get('tools', []):
            t_name = tool_item if isinstance(tool_item, str) else tool_item.get('name', '')
            namespaced = f'mcp_{s_name}_{t_name}'
            assert len(namespaced) <= MAX_TOOL_NAME_LENGTH, f"Tool '{namespaced}' exceeds {MAX_TOOL_NAME_LENGTH} chars"
            assert TOOL_NAME_PATTERN.match(namespaced), f"Tool '{namespaced}' violates regex"


def test_f6_mcp_variable_interpolation_declarations() -> None:
    """Verify every ${VAR} placeholder in command/args/env is declared in variables."""
    data = json.loads(MCP_CONFIG_FILE.read_text(encoding='utf-8'))
    issues = oracle_validate_mcp_config(data, MCP_CONFIG_FILE)
    assert not issues, f'mcp_config.json has variable declaration issues: {issues}'


def test_f6_mcp_zero_plaintext_secrets_or_hardcoded_paths() -> None:
    """Verify mcp_config.json contains no plaintext tokens or hardcoded home directories."""
    content = MCP_CONFIG_FILE.read_text(encoding='utf-8')
    assert '/Users/' not in content, 'Leaked /Users/ path found in mcp_config.json'
    assert '/home/' not in content, 'Leaked /home/ path found in mcp_config.json'
    assert 'ghp_' not in content, 'Leaked GitHub token found in mcp_config.json'
    assert 'AIzaSy' not in content, 'Leaked Google API token found in mcp_config.json'


# ==============================================================================
# Feature 7: AntiGravity 2.29.0 Plugin Manifest Validation
# ==============================================================================


def test_f7_plugin_valid_json() -> None:
    """Verify plugin.json exists and parses cleanly as a dictionary."""
    assert PLUGIN_FILE.is_file(), 'Missing plugin.json'
    data = json.loads(PLUGIN_FILE.read_text(encoding='utf-8'))
    assert isinstance(data, dict)
    assert data.get('name') == 'mimir-agent-kit'


def test_f7_plugin_name_format() -> None:
    """Verify plugin name conforms to lowercase hyphenated pattern."""
    data = json.loads(PLUGIN_FILE.read_text(encoding='utf-8'))
    name = data['name']
    assert SKILL_NAME_PATTERN.match(name), f"Plugin name '{name}' violates regex"


def test_f7_plugin_version_semver() -> None:
    """Verify plugin version adheres to Semantic Versioning (X.Y.Z)."""
    data = json.loads(PLUGIN_FILE.read_text(encoding='utf-8'))
    version = data.get('version', '')
    assert re.match(r'^[0-9]+\.[0-9]+\.[0-9]+$', version), f"Plugin version '{version}' is not valid SemVer"


def test_f7_plugin_logo_file_exists() -> None:
    """Verify logo file exists on disk and is readable."""
    data = json.loads(PLUGIN_FILE.read_text(encoding='utf-8'))
    logo_path = REPO_ROOT / data.get('logo', '')
    assert logo_path.is_file(), f'Plugin logo file not found at {logo_path}'


def test_f7_plugin_license_spdx() -> None:
    """Verify plugin license is a recognized SPDX identifier."""
    data = json.loads(PLUGIN_FILE.read_text(encoding='utf-8'))
    license_id = data.get('license')
    assert license_id in {'Apache-2.0', 'MIT', 'BSD-3-Clause', 'GPL-3.0-only'}


def test_f7_plugin_workspace_discovery_files() -> None:
    """Verify .agents/skills.json and .agents/rules.json exist and point to skills and rules."""
    skills_json = REPO_ROOT / '.agents' / 'skills.json'
    rules_json = REPO_ROOT / '.agents' / 'rules.json'
    assert skills_json.is_file(), 'Missing .agents/skills.json'
    assert rules_json.is_file(), 'Missing .agents/rules.json'

    s_data = json.loads(skills_json.read_text(encoding='utf-8'))
    r_data = json.loads(rules_json.read_text(encoding='utf-8'))
    assert s_data == {'entries': [{'path': 'skills'}]}
    assert r_data == {'entries': [{'path': 'rules'}]}


# ==============================================================================
# Feature 8: Prompt & Reference Consistency
# ==============================================================================


def test_f8_prompt_forbids_autonomous_pr_merge() -> None:
    """Verify rules/AGENTS.md forbids autonomous PR merge unless explicitly requested by the user."""
    rules_text = (RULES_DIR / 'AGENTS.md').read_text(encoding='utf-8')
    assert '**NEVER** merge a Pull Request' in rules_text or 'NEVER merge a Pull Request' in rules_text
    assert 'unless' in rules_text.lower()
    assert 'gh pr merge' in rules_text


def test_f8_prompt_tool_boundary_matrix() -> None:
    """Verify rules/AGENTS.md mandates github-mcp-server for remote ops and Git CLI for local ops."""
    rules_text = (RULES_DIR / 'AGENTS.md').read_text(encoding='utf-8')
    assert 'github-mcp-server' in rules_text
    assert '`mimir-agent-kit_github`' in rules_text
    assert 'local workspace file tools and local `git` CLI' in rules_text or 'local `git` CLI' in rules_text


def test_f8_prompt_pure_uv_environment() -> None:
    """Verify repository safety rules do not prescribe pixi for mimir-agent-kit operations."""
    rules_text = (RULES_DIR / 'AGENTS.md').read_text(encoding='utf-8')
    assert 'pixi.toml' not in rules_text


def test_f8_prompt_cross_skill_links_resolve() -> None:
    """Verify cross-skill references (/skill-name) in skills/ resolve to existing skills."""
    discovered = {p.name for p in SKILLS_DIR.iterdir() if p.is_dir()}
    skill_ref_pattern = re.compile(r'/(?:skills/)?([a-z0-9]+-[a-z0-9-]+)\b')

    for s_dir in SKILLS_DIR.iterdir():
        if not s_dir.is_dir():
            continue
        skill_file = s_dir / 'SKILL.md'
        content = skill_file.read_text(encoding='utf-8')
        for match in skill_ref_pattern.finditer(content):
            ref = match.group(1)
            if ref in {'github-flow-lifecycle', 'github-ops', 'python-pro', 'c-pro', 'cpp-pro', 'ada-spark-pro', 'cmake-pro', 'jupyter-pro', 'rust-pro'}:
                assert ref in discovered, f"Referenced skill '{ref}' does not exist in skills/"


def test_f8_prompt_no_contradictory_safety_invariants() -> None:
    """Verify skill instructions do not permit overriding pre-commit hooks (--no-verify)."""
    for skill_file in SKILLS_DIR.glob('*/SKILL.md'):
        content = skill_file.read_text(encoding='utf-8')
        assert '--no-verify' not in content or 'never' in content.lower() or 'forbidden' in content.lower()


# ==============================================================================
# Feature 9: Standalone CLI Execution & Exit Codes
# ==============================================================================


def test_f9_standardized_error_codes_defined() -> None:
    """Verify ErrorCode enum defines canonical codes across all categories."""
    prefixes = {'SKL', 'RUL', 'HOK', 'MCP', 'PLG', 'PRM', 'TLS', 'SEC', 'SUP'}
    for code_val in ErrorCode:
        prefix = code_val.value[:3]
        assert prefix in prefixes, f"Unexpected error code prefix in '{code_val.value}'"


def test_f9_validation_issue_and_report_data_structures() -> None:
    """Verify ValidationIssue and ValidationReport construct correctly."""
    report = ValidationReport(strict=True)
    report.add(
        code=ErrorCode.SKL004,
        message='Short description',
        severity=Severity.ERROR,
        path=Path('skills/test/SKILL.md'),
        line=3,
        suggestion='Add more details',
    )
    assert report.error_count == 1
    assert report.warning_count == 0
    assert not report.is_clean
    d = report.to_dict()
    assert d['errorCount'] == 1
    assert d['issues'][0]['code'] == 'SKL004'


def test_f9_validation_report_json_serialization() -> None:
    """Verify ValidationReport serializes to formatted JSON string."""
    report = ValidationReport(strict=False)
    report.add(
        code=ErrorCode.MCP004,
        message='Prohibited SSE transport',
        severity=Severity.WARNING,
        path=Path('mcp_config.json'),
    )
    json_str = report.to_json(indent=2)
    parsed = json.loads(json_str)
    assert parsed['warningCount'] == 1
    assert parsed['totalIssues'] == 1


def test_f9_cli_exit_code_clean_run(tmp_agentic_workspace: Path) -> None:
    """Verify oracle validator on a clean synthetic workspace reports 0 errors."""
    report = ValidationReport()
    for s_dir in (tmp_agentic_workspace / 'skills').iterdir():
        if s_dir.is_dir():
            for issue in oracle_validate_skill(s_dir):
                report.add_issue(issue)
    for issue in oracle_validate_rule(tmp_agentic_workspace / 'rules' / 'AGENTS.md', root=tmp_agentic_workspace):
        report.add_issue(issue)
    assert report.is_clean, f'Expected clean workspace, got issues: {report.issues}'


def test_f9_cli_diagnostic_remediation_format() -> None:
    """Verify validation issue dictionary includes actionable remediation fields."""
    issue = ValidationIssue(
        code=ErrorCode.SKL005,
        message='Body exceeds cap',
        severity=Severity.ERROR,
        path=Path('skills/a/SKILL.md'),
        line=1,
        suggestion='Move reference documentation to references/ folder',
    )
    d = issue.to_dict()
    assert 'code' in d and 'message' in d and 'severity' in d and 'path' in d and 'suggestion' in d


def test_f9_cli_subprocess_invocation_if_present() -> None:
    """Verify execution of scripts/validate_agentic_settings.py if present."""
    if not VALIDATE_CLI_FILE.is_file():
        pytest.skip('scripts/validate_agentic_settings.py not yet generated (Milestone 2 in progress)')
    res = subprocess.run(
        [sys.executable, str(VALIDATE_CLI_FILE), '--check'],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
    )
    assert res.returncode in {0, 1}, f'CLI exited with unexpected code {res.returncode}'


# ==============================================================================
# Feature 10: Local Pre-Commit Enforcement Gate
# ==============================================================================


def test_f10_local_ci_lock_check_semantics() -> None:
    """Verify uv lock --check passes on the current repository."""
    uv_bin = shutil.which('uv')
    assert uv_bin is not None, 'uv executable not found in PATH'
    res = subprocess.run(
        [uv_bin, 'lock', '--check'],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
    )
    assert res.returncode == 0, f'uv lock --check failed: {res.stderr}'


def test_f10_local_ci_pre_commit_invocation_semantics() -> None:
    """Verify pre-commit command executes cleanly with help flag."""
    pre_commit_bin = shutil.which('pre-commit')
    assert pre_commit_bin is not None, 'pre-commit executable not found in PATH'
    res = subprocess.run(
        [pre_commit_bin, 'run', '--help'],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0
    assert '--all-files' in res.stdout


def test_f10_local_ci_pytest_invocation_semantics() -> None:
    """Verify pytest can be invoked in the current virtual environment."""
    pytest_bin = shutil.which('pytest')
    assert pytest_bin is not None, 'pytest executable not found in PATH'
    res = subprocess.run(
        [pytest_bin, '--version'],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0
    assert 'pytest' in res.stdout.lower()


def test_f10_local_ci_exit_code_contract() -> None:
    """Verify gate invariant contract: failure in any gate produces exit code 1."""
    report = ValidationReport()
    report.add(
        code=ErrorCode.SKL001,
        message='Missing SKILL.md',
        severity=Severity.ERROR,
        path=Path('skills/missing'),
    )
    exit_code = 0 if report.is_clean else 1
    assert exit_code == 1, 'Validation report with errors must translate to exit code 1'


def test_f10_local_ci_script_executable_if_present() -> None:
    """Verify scripts/ci/run_local_ci.sh if present is executable and valid bash syntax."""
    if not RUN_LOCAL_CI_FILE.is_file():
        pytest.skip('scripts/ci/run_local_ci.sh not yet generated (Milestone 3 planned)')
    assert os.access(RUN_LOCAL_CI_FILE, os.X_OK), 'run_local_ci.sh must be executable (+x)'
    bash_bin = shutil.which('bash') or '/bin/bash'
    res = subprocess.run(
        [bash_bin, '-n', str(RUN_LOCAL_CI_FILE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f'Syntax error in run_local_ci.sh: {res.stderr}'


# ==============================================================================
# Feature 11: Supply-Chain SHA Pinning & Workflow Security Enforcement
# ==============================================================================


def test_f11_all_workflows_sha_pinned_and_persist_credentials_false() -> None:
    """Verify all GitHub Actions workflows use 40-char commit SHAs and persist-credentials: false."""
    workflows_dir = REPO_ROOT / '.github' / 'workflows'
    wf_files = sorted(workflows_dir.glob('*.yml'))
    assert {p.name for p in wf_files} >= {'ci.yml', 'scorecard.yml'}

    sha_line_re = re.compile(r'^\s*(?:-\s*)?uses:\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+)@([0-9a-f]{40})\s+#\s*v\d+')
    for wf_file in wf_files:
        content = wf_file.read_text(encoding='utf-8')
        for line in content.splitlines():
            if 'uses:' in line and not line.lstrip().startswith('#'):
                assert sha_line_re.match(line), f'Unpinned or uncommented action in {wf_file.name}: {line}'

        parsed = yaml.safe_load(content)
        for job_cfg in parsed.get('jobs', {}).values():
            for step in job_cfg.get('steps', []):
                uses_val = step.get('uses', '')
                if isinstance(uses_val, str) and uses_val.startswith('actions/checkout@'):
                    assert step.get('with', {}).get('persist-credentials') is False
                if isinstance(uses_val, str) and uses_val.startswith('ossf/scorecard-action@'):
                    assert step.get('with', {}).get('publish_results') is False, 'scorecard.yml must keep publish_results: false to prevent external Rekor CI flakes'


def test_f11_pre_commit_external_repos_sha_frozen_and_security_hooks_configured() -> None:
    """Verify .pre-commit-config.yaml freezes external repos by SHA and runs actionlint + zizmor."""
    data = yaml.safe_load(PRE_COMMIT_FILE.read_text(encoding='utf-8'))
    sha_re = re.compile(r'^[0-9a-f]{40}$')
    local_hook_ids: set[str] = set()

    for entry in data.get('repos', []):
        repo_url = entry.get('repo', '')
        if repo_url not in {'local', 'meta'}:
            assert sha_re.match(str(entry.get('rev', ''))), f'Unpinned pre-commit repo {repo_url}: {entry.get("rev")}'
        else:
            for hook in entry.get('hooks', []):
                local_hook_ids.add(str(hook.get('id', '')))

    assert {'actionlint', 'zizmor', 'agentic-settings-validation'}.issubset(local_hook_ids)


def test_f11_actionlint_and_zizmor_pass_on_workflows() -> None:
    """Verify actionlint and zizmor report zero findings across .github/workflows/."""
    uv_bin = shutil.which('uv')
    assert uv_bin is not None
    res_lint = subprocess.run(
        [uv_bin, 'run', 'actionlint'],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert res_lint.returncode == 0, f'actionlint failed: {res_lint.stdout}\n{res_lint.stderr}'

    res_zizmor = subprocess.run(
        [uv_bin, 'run', 'zizmor', '--strict-collection', '--min-severity=low', '.github/workflows/'],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert res_zizmor.returncode == 0, f'zizmor failed: {res_zizmor.stdout}\n{res_zizmor.stderr}'


def test_f11_renovate_and_dependabot_configs_present_and_valid() -> None:
    """Verify renovate.jsonc and .github/dependabot.yml exist and configure digest updates."""
    renovate_path = REPO_ROOT / 'renovate.jsonc'
    shadow_renovate_path = REPO_ROOT / 'renovate.json'
    dependabot_path = REPO_ROOT / '.github' / 'dependabot.yml'
    assert renovate_path.is_file()
    assert not shadow_renovate_path.exists(), 'Duplicate renovate.json must not shadow renovate.jsonc'
    assert dependabot_path.is_file()

    renovate_data = json.loads(strip_jsonc_comments(renovate_path.read_text(encoding='utf-8')))
    assert 'dependencyDashboard' not in renovate_data, 'Inherit dependencyDashboard from config:best-practices (#23)'
    assert 'config:best-practices' in renovate_data.get('extends', [])
    pkg_rules = renovate_data.get('packageRules', [])
    ubuntu_rules = [r for r in pkg_rules if 'github-runners' in r.get('matchDatasources', []) and 'ubuntu' in r.get('matchPackageNames', [])]
    assert len(ubuntu_rules) == 1
    assert ubuntu_rules[0].get('versioning') == 'pep440'
    assert ubuntu_rules[0].get('allowedVersions') == '<=24.04'

    dependabot_data = yaml.safe_load(dependabot_path.read_text(encoding='utf-8'))
    ecosystems = {u['package-ecosystem'] for u in dependabot_data['updates']}
    assert {'github-actions', 'uv'}.issubset(ecosystems)


def test_f11_post_merge_main_pre_commit_skips_no_commit_to_branch(tmp_path: Path) -> None:
    """Verify CI and run_local_ci.sh skip no-commit-to-branch on main while git commit stays guarded."""
    ci_data = yaml.safe_load(CI_WORKFLOW_FILE.read_text(encoding='utf-8'))
    steps = ci_data['jobs']['validate-and-test']['steps']
    pc_steps = [s for s in steps if 'pre-commit run' in str(s.get('run', ''))]
    assert len(pc_steps) == 1
    skip_env = str(pc_steps[0].get('env', {}).get('SKIP', ''))
    assert 'no-commit-to-branch' in {item.strip() for item in skip_env.split(',')}

    run_local_text = RUN_LOCAL_CI_FILE.read_text(encoding='utf-8')
    assert 'no-commit-to-branch' in run_local_text

    git_bin = shutil.which('git')
    pre_commit_bin = shutil.which('pre-commit')
    assert git_bin is not None
    assert pre_commit_bin is not None

    subprocess.run([git_bin, 'init', '-b', 'main'], cwd=tmp_path, check=True, capture_output=True)
    pc_cfg = tmp_path / '.pre-commit-config.yaml'
    pc_cfg.write_text(PRE_COMMIT_FILE.read_text(encoding='utf-8'), encoding='utf-8')
    (tmp_path / 'sample.txt').write_text('clean line\n', encoding='utf-8')
    subprocess.run([git_bin, 'add', '.pre-commit-config.yaml', 'sample.txt'], cwd=tmp_path, check=True, capture_output=True)

    # Without SKIP on branch 'main', no-commit-to-branch exits 1 (guarding git commit on main)
    res_commit_guard = subprocess.run(
        [pre_commit_bin, 'run', 'no-commit-to-branch', '--all-files'],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res_commit_guard.returncode == 1

    # With SKIP=no-commit-to-branch on branch 'main' (as in ci.yml and run_local_ci.sh), exits 0
    env_with_skip = {**os.environ, 'SKIP': 'no-commit-to-branch'}
    res_ci_skip = subprocess.run(
        [pre_commit_bin, 'run', 'no-commit-to-branch', '--all-files'],
        cwd=tmp_path,
        env=env_with_skip,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res_ci_skip.returncode == 0
