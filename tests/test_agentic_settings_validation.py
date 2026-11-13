"""Comprehensive test suite for AntiGravity 2.29.0 agentic settings validation engine."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts.validate_agentic_settings import main
from scripts.validation.codes import ErrorCode
from scripts.validation.engine import validate_all
from scripts.validation.hooks_validator import validate_hooks
from scripts.validation.hooks_validator import validate_hooks_file
from scripts.validation.mcp_validator import load_tool_manifest
from scripts.validation.mcp_validator import resolve_plugin_name
from scripts.validation.mcp_validator import validate_mcp_config
from scripts.validation.mcp_validator import validate_mcp_config_file
from scripts.validation.mcp_validator import validate_namespaced_tool_name
from scripts.validation.models import Severity
from scripts.validation.models import ValidationIssue
from scripts.validation.models import ValidationReport
from scripts.validation.plugin_validator import validate_discovery_configs
from scripts.validation.plugin_validator import validate_plugin_manifest_file
from scripts.validation.prompt_validator import validate_prompts
from scripts.validation.reporter import format_json
from scripts.validation.reporter import format_terminal
from scripts.validation.rules_validator import validate_rules
from scripts.validation.secret_hygiene_validator import validate_secret_hygiene
from scripts.validation.skills_validator import validate_skill_directory
from scripts.validation.skills_validator import validate_skills
from scripts.validation.supply_chain_validator import strip_jsonc_comments
from scripts.validation.supply_chain_validator import validate_pre_commit_file
from scripts.validation.supply_chain_validator import validate_renovate_file
from scripts.validation.supply_chain_validator import validate_supply_chain
from scripts.validation.supply_chain_validator import validate_workflow_file
from scripts.validation.tool_schema_validator import validate_tool_parameter_schema
from scripts.validation.tool_schema_validator import validate_tool_schemas


REPO_ROOT = Path(__file__).resolve().parent.parent


# ============================================================================
# 1. Clean Repository Integration & CLI Tests
# ============================================================================


def test_clean_repository_passes_all_validations() -> None:
    """Verify that current repository passes all strict validations cleanly."""
    report = validate_all(repo_root=REPO_ROOT, strict=True)
    assert report.is_clean, f'Validation failed with issues: {report.issues}'
    assert report.error_count == 0
    assert report.warning_count == 0
    assert len(report.issues) == 0


def test_cli_runner_clean_repository_exit_code_zero(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify CLI main entrypoint returns exit code 0 on clean repository."""
    exit_code = main(['--strict', '--path', str(REPO_ROOT), '--no-color'])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert '[PASS]' in captured.out


def test_cli_runner_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify CLI --json option emits parseable JSON report with passed: true."""
    exit_code = main(['--json', '--path', str(REPO_ROOT)])
    captured = capsys.readouterr()
    assert exit_code == 0
    data = json.loads(captured.out)
    assert data['passed'] is True
    assert data['errorCount'] == 0
    assert data['issues'] == []


# ============================================================================
# 2. Skills Validator Tests (SKL001 - SKL008)
# ============================================================================


def test_skill_skl001_missing_skill_md(tmp_path: Path) -> None:
    """SKL001: Skill directory missing SKILL.md."""
    skill_dir = tmp_path / 'skills' / 'my-skill'
    skill_dir.mkdir(parents=True)

    report = ValidationReport()
    validate_skills(tmp_path, report)
    assert any(i.code == ErrorCode.SKL001 for i in report.issues)


def test_skill_skl002_malformed_frontmatter(tmp_path: Path) -> None:
    """SKL002: Missing or malformed YAML frontmatter framing."""
    skill_dir = tmp_path / 'skills' / 'my-skill'
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / 'SKILL.md'

    # Case 1: Missing opening delimiter
    skill_md.write_text('name: my-skill\ndescription: Some valid description here\n---\nBody', encoding='utf-8')
    report = ValidationReport()
    validate_skill_directory(skill_dir, report)
    assert any(i.code == ErrorCode.SKL002 for i in report.issues)

    # Case 2: Missing closing delimiter
    skill_md.write_text('---\nname: my-skill\ndescription: Some valid description here\nBody without closing', encoding='utf-8')
    report2 = ValidationReport()
    validate_skill_directory(skill_dir, report2)
    assert any(i.code == ErrorCode.SKL002 for i in report2.issues)

    # Case 3: Invalid YAML syntax
    skill_md.write_text('---\nname: [unclosed list\n---\nBody', encoding='utf-8')
    report3 = ValidationReport()
    validate_skill_directory(skill_dir, report3)
    assert any(i.code == ErrorCode.SKL002 for i in report3.issues)


def test_skill_skl003_invalid_name(tmp_path: Path) -> None:
    """SKL003: Invalid name format or mismatch with directory name."""
    skill_dir = tmp_path / 'skills' / 'my-skill'
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / 'SKILL.md'

    # Name mismatch with folder
    skill_md.write_text(
        '---\nname: other-skill\ndescription: Valid description with at least 20 chars\n---\nBody\n',
        encoding='utf-8',
    )
    report = ValidationReport()
    validate_skill_directory(skill_dir, report)
    assert any(i.code == ErrorCode.SKL003 for i in report.issues)

    # Uppercase in name
    skill_md.write_text(
        '---\nname: My-Skill\ndescription: Valid description with at least 20 chars\n---\nBody\n',
        encoding='utf-8',
    )
    report2 = ValidationReport()
    validate_skill_directory(skill_dir, report2)
    assert any(i.code == ErrorCode.SKL003 for i in report2.issues)


def test_skill_skl004_short_description(tmp_path: Path) -> None:
    """SKL004: Description is shorter than 20 characters."""
    skill_dir = tmp_path / 'skills' / 'my-skill'
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / 'SKILL.md'

    skill_md.write_text(
        '---\nname: my-skill\ndescription: Too short\n---\nBody\n',
        encoding='utf-8',
    )
    report = ValidationReport()
    validate_skill_directory(skill_dir, report)
    assert any(i.code == ErrorCode.SKL004 for i in report.issues)


def test_skill_skl005_body_size_cap(tmp_path: Path) -> None:
    """SKL005: Markdown body exceeds 24,000 bytes hard cap."""
    skill_dir = tmp_path / 'skills' / 'my-skill'
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / 'SKILL.md'

    oversized_body = 'A' * 24_500
    skill_md.write_text(
        f'---\nname: my-skill\ndescription: Valid description with at least 20 chars\n---\n{oversized_body}\n',
        encoding='utf-8',
    )
    report = ValidationReport()
    validate_skill_directory(skill_dir, report)
    assert any(i.code == ErrorCode.SKL005 for i in report.issues)


def test_skill_skl005_exact_24000_bytes_allowed(tmp_path: Path) -> None:
    """SKL005 Boundary: Markdown body of exactly 24,000 bytes is permitted."""
    skill_dir = tmp_path / 'skills' / 'boundary-skill'
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / 'SKILL.md'

    exact_body = 'A' * 24_000
    skill_md.write_text(
        f'---\nname: boundary-skill\ndescription: Valid description with at least 20 chars\n---\n{exact_body}',
        encoding='utf-8',
    )
    report = ValidationReport()
    validate_skill_directory(skill_dir, report)
    assert not any(i.code == ErrorCode.SKL005 for i in report.issues)


def test_skill_skl005_24001_bytes_rejected(tmp_path: Path) -> None:
    """SKL005 Boundary: Markdown body of 24,001 bytes is rejected."""
    skill_dir = tmp_path / 'skills' / 'oversized-skill'
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / 'SKILL.md'

    oversized_body = 'A' * 24_001
    skill_md.write_text(
        f'---\nname: oversized-skill\ndescription: Valid description with at least 20 chars\n---\n{oversized_body}',
        encoding='utf-8',
    )
    report = ValidationReport()
    validate_skill_directory(skill_dir, report)
    assert any(i.code == ErrorCode.SKL005 for i in report.issues)


def test_skill_skl006_disallowed_folder(tmp_path: Path) -> None:
    """SKL006: Disallowed subfolder inside skill folder."""
    skill_dir = tmp_path / 'skills' / 'my-skill'
    skill_dir.mkdir(parents=True)
    (skill_dir / 'SKILL.md').write_text(
        '---\nname: my-skill\ndescription: Valid description with at least 20 chars\n---\nBody\n',
        encoding='utf-8',
    )
    (skill_dir / 'disallowed_folder').mkdir()

    report = ValidationReport()
    validate_skill_directory(skill_dir, report)
    assert any(i.code == ErrorCode.SKL006 for i in report.issues)


def test_skill_skl007_script_executable_and_fix(tmp_path: Path) -> None:
    """SKL007: Script in scripts/ lacks executable bit, and fix=True corrects it."""
    skill_dir = tmp_path / 'skills' / 'my-skill'
    scripts_dir = skill_dir / 'scripts'
    scripts_dir.mkdir(parents=True)
    (skill_dir / 'SKILL.md').write_text(
        '---\nname: my-skill\ndescription: Valid description with at least 20 chars\n---\nBody\n',
        encoding='utf-8',
    )
    helper = scripts_dir / 'helper.sh'
    helper.write_text('#!/bin/sh\necho hi\n', encoding='utf-8')
    helper.chmod(0o644)  # not executable

    # Check without fix
    report = ValidationReport()
    validate_skill_directory(skill_dir, report, fix=False)
    assert any(i.code == ErrorCode.SKL007 for i in report.issues)

    # Check with fix
    report_fix = ValidationReport()
    validate_skill_directory(skill_dir, report_fix, fix=True)
    assert os.access(helper, os.X_OK)


def test_skill_skl008_broken_relative_link(tmp_path: Path) -> None:
    """SKL008: Broken relative markdown link in SKILL.md."""
    skill_dir = tmp_path / 'skills' / 'my-skill'
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / 'SKILL.md'

    skill_md.write_text(
        '---\nname: my-skill\ndescription: Valid description with at least 20 chars\n---\nCheck [missing docs](./missing_file.md) for details.\n',
        encoding='utf-8',
    )
    report = ValidationReport()
    validate_skill_directory(skill_dir, report)
    assert any(i.code == ErrorCode.SKL008 for i in report.issues)


# ============================================================================
# 3. Rules Validator Tests (RUL001 - RUL004)
# ============================================================================


def test_rules_rul001_root_agents_md(tmp_path: Path) -> None:
    """RUL001: Top-level AGENTS.md placed at plugin root."""
    (tmp_path / 'AGENTS.md').write_text('# Workspace Rules\n', encoding='utf-8')
    report = ValidationReport()
    validate_rules(tmp_path, report)
    assert any(i.code == ErrorCode.RUL001 for i in report.issues)


def test_rules_rul002_standalone_yaml_frontmatter(tmp_path: Path) -> None:
    """RUL002: Standalone rules/AGENTS.md has disallowed YAML frontmatter."""
    rules_dir = tmp_path / 'rules'
    rules_dir.mkdir(parents=True)
    (rules_dir / 'AGENTS.md').write_text('---\ntrigger: always_on\n---\n# Rules\n', encoding='utf-8')

    report = ValidationReport()
    validate_rules(tmp_path, report)
    assert any(i.code == ErrorCode.RUL002 for i in report.issues)


def test_rules_rul003_invalid_trigger(tmp_path: Path) -> None:
    """RUL003: Invalid trigger enum in rule frontmatter."""
    agents_rules = tmp_path / '.agents' / 'rules'
    agents_rules.mkdir(parents=True)
    rule_file = agents_rules / 'my_rule.md'
    rule_file.write_text('---\ntrigger: INVALID_TRIGGER\n---\nRule content\n', encoding='utf-8')

    report = ValidationReport()
    validate_rules(tmp_path, report)
    assert any(i.code == ErrorCode.RUL003 for i in report.issues)


def test_rules_unclosed_yaml_frontmatter_rejected(tmp_path: Path) -> None:
    """RUL002: Rule file with unclosed YAML frontmatter is rejected."""
    agents_rules = tmp_path / '.agents' / 'rules'
    agents_rules.mkdir(parents=True)
    rule_file = agents_rules / 'unclosed.md'
    rule_file.write_text('---\ntrigger: always_on\nBody text without closing delimiter\n', encoding='utf-8')

    report = ValidationReport()
    validate_rules(tmp_path, report)
    assert any(i.code == ErrorCode.RUL002 for i in report.issues)


def test_rules_malformed_yaml_frontmatter_rejected(tmp_path: Path) -> None:
    """RUL002: Rule file with malformed YAML syntax in frontmatter is rejected."""
    agents_rules = tmp_path / '.agents' / 'rules'
    agents_rules.mkdir(parents=True)
    rule_file = agents_rules / 'bad_yaml.md'
    rule_file.write_text('---\n[malformed yaml : unclosed\n---\nBody text\n', encoding='utf-8')

    report = ValidationReport()
    validate_rules(tmp_path, report)
    assert any(i.code == ErrorCode.RUL002 for i in report.issues)


def test_rules_non_dict_yaml_frontmatter_rejected(tmp_path: Path) -> None:
    """RUL002: Rule file with non-dict YAML frontmatter is rejected."""
    agents_rules = tmp_path / '.agents' / 'rules'
    agents_rules.mkdir(parents=True)
    rule_file = agents_rules / 'list_fm.md'
    rule_file.write_text('---\n- list_item_1\n- list_item_2\n---\nBody text\n', encoding='utf-8')

    report = ValidationReport()
    validate_rules(tmp_path, report)
    assert any(i.code == ErrorCode.RUL002 for i in report.issues)


def test_rules_missing_trigger_rejected(tmp_path: Path) -> None:
    """RUL003: Rule file frontmatter missing 'trigger' key is rejected."""
    agents_rules = tmp_path / '.agents' / 'rules'
    agents_rules.mkdir(parents=True)
    rule_file = agents_rules / 'no_trigger.md'
    rule_file.write_text('---\nname: custom_rule\n---\nBody text\n', encoding='utf-8')

    report = ValidationReport()
    validate_rules(tmp_path, report)
    assert any(i.code == ErrorCode.RUL003 for i in report.issues)


def test_rules_rul004_size_cap_and_token_budget(tmp_path: Path) -> None:
    """RUL004: Rule file exceeds 24KB cap or always-on budget exceeds 20,000 tokens."""
    rules_dir = tmp_path / 'rules'
    rules_dir.mkdir(parents=True)
    oversized = rules_dir / 'AGENTS.md'
    oversized.write_text('A' * 25_000, encoding='utf-8')

    report = ValidationReport()
    validate_rules(tmp_path, report)
    assert any(i.code == ErrorCode.RUL004 for i in report.issues)

    # Token budget test: create rule file with 90,000 chars (> 20,000 tokens) split across files
    rule1 = rules_dir / 'rule1.md'
    rule2 = rules_dir / 'rule2.md'
    rule1.write_text('word ' * 12_000, encoding='utf-8')
    rule2.write_text('word ' * 12_000, encoding='utf-8')
    report2 = ValidationReport()
    validate_rules(tmp_path, report2)
    assert any(i.code == ErrorCode.RUL004 for i in report2.issues)


@pytest.mark.parametrize(
    'trigger',
    [
        'ALWAYS_ON',
        'MODEL_DECISION',
        'GLOB',
        'MANUAL',
        'always_on',
        'model_decision',
        'glob',
        'manual',
        'CORTEX_MEMORY_TRIGGER_ALWAYS_ON',
        'CORTEX_MEMORY_TRIGGER_MODEL_DECISION',
        'CORTEX_MEMORY_TRIGGER_GLOB',
        'CORTEX_MEMORY_TRIGGER_MANUAL',
    ],
)
def test_rules_canonical_triggers_pass(tmp_path: Path, trigger: str) -> None:
    """RUL003: All 12 canonical triggers pass cleanly with 0 issues."""
    agents_rules = tmp_path / '.agents' / 'rules'
    agents_rules.mkdir(parents=True)
    rule_file = agents_rules / f'{trigger.lower()}_rule.md'
    rule_file.write_text(f'---\ntrigger: {trigger}\n---\n# Rule content\nBody text\n', encoding='utf-8')

    report = ValidationReport()
    validate_rules(tmp_path, report)
    assert not any(i.code == ErrorCode.RUL003 for i in report.issues), f"Canonical trigger '{trigger}' unexpectedly failed with RUL003: {[i.message for i in report.issues]}"
    assert report.is_clean, f"Expected clean validation for trigger '{trigger}', got issues: {report.issues}"


@pytest.mark.parametrize(
    'invalid_trigger',
    [
        'Always_On',
        'AlwaysOn',
        'ALWAYS-ON',
        'always-on',
        'Model_Decision',
        'modelDecision',
        'Glob',
        'Manual',
        'cortex_memory_trigger_always_on',
        'INVALID_TRIGGER',
        'UNKNOWN',
        'random_trigger',
        '',
        '   ',
        '123',
    ],
)
def test_rules_invalid_or_mixed_case_triggers_rejected(tmp_path: Path, invalid_trigger: str) -> None:
    """RUL003: Verify mixed-case, hyphenated, arbitrary, or empty triggers are rejected."""
    agents_rules = tmp_path / '.agents' / 'rules'
    agents_rules.mkdir(parents=True)
    rule_file = agents_rules / 'invalid_rule.md'
    rule_file.write_text(f'---\ntrigger: {invalid_trigger}\n---\n# Rule content\nBody text\n', encoding='utf-8')

    report = ValidationReport()
    validate_rules(tmp_path, report)
    rul003_issues = [i for i in report.issues if i.code == ErrorCode.RUL003]
    assert len(rul003_issues) == 1, f"Expected exactly 1 RUL003 issue for trigger '{invalid_trigger}', got {len(rul003_issues)}"
    assert rul003_issues[0].severity == Severity.ERROR
    assert 'Must be one of' in rul003_issues[0].message
    assert rul003_issues[0].suggestion is not None


def test_cli_runner_with_uppercase_trigger_rule(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Verify CLI main entrypoint returns exit code 0 when rule uses uppercase ALWAYS_ON."""
    agents_rules = tmp_path / '.agents' / 'rules'
    agents_rules.mkdir(parents=True)
    (agents_rules / 'valid_upper.md').write_text(
        '---\ntrigger: ALWAYS_ON\n---\n# Production Rule\nEnforce strict git standards.\n',
        encoding='utf-8',
    )
    # Include mandatory discovery configs and rules/AGENTS.md for complete workspace compliance
    (tmp_path / '.agents' / 'skills.json').write_text('{"entries": []}\n', encoding='utf-8')
    (tmp_path / '.agents' / 'rules.json').write_text('{"entries": []}\n', encoding='utf-8')
    (tmp_path / 'rules').mkdir(parents=True)
    (tmp_path / 'rules' / 'AGENTS.md').write_text('# Workspace Rules\nPlain markdown rule.\n', encoding='utf-8')

    exit_code = main(['--strict', '--path', str(tmp_path), '--no-color'])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert '[PASS]' in captured.out


def test_rules_token_budget_accounting_across_trigger_types(tmp_path: Path) -> None:
    """Verify that only always_on trigger variants count against the 20,000 token limit."""
    agents_rules = tmp_path / '.agents' / 'rules'
    agents_rules.mkdir(parents=True)

    # 6 non-always-on files: 3,500 words each = ~4,375 tokens each (total ~26,250 tokens > 20,000)
    # Each file is ~17.5KB (< 24KB limit). Because they are not always_on, RUL004 must NOT be raised.
    for i in range(6):
        (agents_rules / f'non_always_{i}.md').write_text(
            f'---\ntrigger: MODEL_DECISION\n---\n{"word " * 3500}\n',
            encoding='utf-8',
        )
    report_non_always = ValidationReport()
    validate_rules(tmp_path, report_non_always)
    assert not any(i.code == ErrorCode.RUL004 for i in report_non_always.issues)

    # Now add always-on files exceeding 20,000 tokens using mixed uppercase/lowercase/protobuf triggers
    for i, t in enumerate(['ALWAYS_ON', 'always_on', 'CORTEX_MEMORY_TRIGGER_ALWAYS_ON'] * 2):
        (agents_rules / f'always_{i}.md').write_text(
            f'---\ntrigger: {t}\n---\n{"word " * 3500}\n',
            encoding='utf-8',
        )
    report_always = ValidationReport()
    validate_rules(tmp_path, report_always)
    rul004_issues = [i for i in report_always.issues if i.code == ErrorCode.RUL004]
    assert len(rul004_issues) == 1
    assert 'exceeds AntiGravity 20000 token limit' in rul004_issues[0].message


# ============================================================================
# 4. Hooks Validator Tests (HOK001 - HOK006)
# ============================================================================


def test_hooks_hok001_malformed_json(tmp_path: Path) -> None:
    """HOK001: Malformed JSON in hooks.json."""
    hooks_file = tmp_path / 'hooks.json'
    hooks_file.write_text('{ unclosed json ', encoding='utf-8')

    report = ValidationReport()
    validate_hooks_file(hooks_file, tmp_path, report)
    assert any(i.code == ErrorCode.HOK001 for i in report.issues)


def test_hooks_hok002_invalid_event_name(tmp_path: Path) -> None:
    """HOK002: Invalid lifecycle event name."""
    hooks_file = tmp_path / 'hooks.json'
    hooks_file.write_text(
        json.dumps({'guard': {'enabled': True, 'InvalidEvent': [{'command': 'echo 1'}]}}),
        encoding='utf-8',
    )

    report = ValidationReport()
    validate_hooks_file(hooks_file, tmp_path, report)
    assert any(i.code == ErrorCode.HOK002 for i in report.issues)


def test_hooks_hok003_tool_event_missing_matcher(tmp_path: Path) -> None:
    """HOK003: PreToolUse/PostToolUse missing matcher or hooks array."""
    hooks_file = tmp_path / 'hooks.json'
    hooks_file.write_text(
        json.dumps({'guard': {'enabled': True, 'PreToolUse': [{'command': 'echo 1'}]}}),
        encoding='utf-8',
    )

    report = ValidationReport()
    validate_hooks_file(hooks_file, tmp_path, report)
    assert any(i.code == ErrorCode.HOK003 for i in report.issues)


def test_hooks_hok004_missing_command(tmp_path: Path) -> None:
    """HOK004: Handler missing command string."""
    hooks_file = tmp_path / 'hooks.json'
    hooks_file.write_text(
        json.dumps({'guard': {'enabled': True, 'SessionStart': [{'timeout': 30}]}}),
        encoding='utf-8',
    )

    report = ValidationReport()
    validate_hooks_file(hooks_file, tmp_path, report)
    assert any(i.code == ErrorCode.HOK004 for i in report.issues)


def test_hooks_hok005_invalid_timeout(tmp_path: Path) -> None:
    """HOK005: Handler timeout not a positive integer."""
    hooks_file = tmp_path / 'hooks.json'
    hooks_file.write_text(
        json.dumps({'guard': {'enabled': True, 'SessionStart': [{'command': 'echo 1', 'timeout': -5}]}}),
        encoding='utf-8',
    )

    report = ValidationReport()
    validate_hooks_file(hooks_file, tmp_path, report)
    assert any(i.code == ErrorCode.HOK005 for i in report.issues)


def test_hooks_hok006_nonexistent_or_non_executable_script(tmp_path: Path) -> None:
    """HOK006: Referenced script file does not exist or lacks executable bit."""
    hooks_file = tmp_path / 'hooks.json'
    hooks_file.write_text(
        json.dumps({'guard': {'enabled': True, 'SessionStart': [{'command': 'python scripts/missing.py'}]}}),
        encoding='utf-8',
    )

    report = ValidationReport()
    validate_hooks_file(hooks_file, tmp_path, report)
    assert any(i.code == ErrorCode.HOK006 for i in report.issues)


# ============================================================================
# 5. MCP Validator Tests (MCP001 - MCP008)
# ============================================================================


def test_mcp_mcp001_malformed_json(tmp_path: Path) -> None:
    """MCP001: Malformed JSON in mcp_config.json."""
    config_file = tmp_path / 'mcp_config.json'
    config_file.write_text('{ "mcpServers": ', encoding='utf-8')

    report = ValidationReport()
    validate_mcp_config_file(config_file, report)
    assert any(i.code == ErrorCode.MCP001 for i in report.issues)


def test_mcp_mcp002_missing_servers_object(tmp_path: Path) -> None:
    """MCP002: Missing or malformed mcpServers object."""
    config_file = tmp_path / 'mcp_config.json'
    config_file.write_text(json.dumps({'servers': {}}), encoding='utf-8')

    report = ValidationReport()
    validate_mcp_config_file(config_file, report)
    assert any(i.code == ErrorCode.MCP002 for i in report.issues)


def test_mcp_mcp003_invalid_transport(tmp_path: Path) -> None:
    """MCP003: Invalid transport (missing command or url)."""
    config_file = tmp_path / 'mcp_config.json'
    config_file.write_text(
        json.dumps({'mcpServers': {'bad-server': {'args': ['test']}}}),
        encoding='utf-8',
    )

    report = ValidationReport()
    validate_mcp_config_file(config_file, report)
    assert any(i.code == ErrorCode.MCP003 for i in report.issues)


def test_mcp_mcp004_prohibited_sse_url(tmp_path: Path) -> None:
    """MCP004: Prohibited legacy SSE URL used instead of Streamable HTTP."""
    config_file = tmp_path / 'mcp_config.json'
    config_file.write_text(
        json.dumps({'mcpServers': {'remote-server': {'url': 'https://api.example.com/sse'}}}),
        encoding='utf-8',
    )

    report = ValidationReport()
    validate_mcp_config_file(config_file, report)
    assert any(i.code == ErrorCode.MCP004 for i in report.issues)


def test_mcp_mcp005_undeclared_variable(tmp_path: Path) -> None:
    """MCP005: Undeclared placeholder variable in config."""
    config_file = tmp_path / 'mcp_config.json'
    config_file.write_text(
        json.dumps({
            'mcpServers': {
                'srv': {
                    'command': 'run',
                    'env': {'TOKEN': '${SECRET_TOKEN}'},
                },
            },
        }),
        encoding='utf-8',
    )

    report = ValidationReport()
    validate_mcp_config_file(config_file, report)
    assert any(i.code == ErrorCode.MCP005 for i in report.issues)


def test_mcp_mcp006_declared_variable_not_referenced(tmp_path: Path) -> None:
    """MCP006: Declared variable in variables array not referenced."""
    config_file = tmp_path / 'mcp_config.json'
    config_file.write_text(
        json.dumps({
            'mcpServers': {
                'srv': {
                    'command': 'run',
                    'variables': [
                        {
                            'name': 'UNUSED_VAR',
                            'title': 'Unused Variable',
                            'description': 'Description here',
                        },
                    ],
                },
            },
        }),
        encoding='utf-8',
    )

    report = ValidationReport()
    validate_mcp_config_file(config_file, report)
    assert any(i.code == ErrorCode.MCP006 for i in report.issues)


def test_mcp_mcp007_missing_variable_title_or_description(tmp_path: Path) -> None:
    """MCP007: Variable missing required title or description."""
    config_file = tmp_path / 'mcp_config.json'
    config_file.write_text(
        json.dumps({
            'mcpServers': {
                'srv': {
                    'command': '${API_KEY}',
                    'variables': [{'name': 'API_KEY'}],
                },
            },
        }),
        encoding='utf-8',
    )

    report = ValidationReport()
    validate_mcp_config_file(config_file, report)
    assert any(i.code == ErrorCode.MCP007 for i in report.issues)


def test_mcp_mcp008_tool_name_length_exceeded(tmp_path: Path) -> None:
    """MCP008: Namespaced tool identifier mcp_<server>_<tool> exceeds 64 characters."""
    report = ValidationReport()
    validate_namespaced_tool_name(
        server_name='github-mcp-server',
        tool_name='manage_repository_notification_subscription',  # 65 chars total
        report=report,
        path=tmp_path / 'mcp_config.json',
    )
    assert any(i.code == ErrorCode.MCP008 for i in report.issues)


# ============================================================================
# 6. Plugin Manifest Tests (PLG001 - PLG006)
# ============================================================================


def test_plugin_plg001_malformed_json(tmp_path: Path) -> None:
    """PLG001: Malformed JSON in plugin.json."""
    plugin_file = tmp_path / 'plugin.json'
    plugin_file.write_text('{ bad json ', encoding='utf-8')

    report = ValidationReport()
    validate_plugin_manifest_file(plugin_file, tmp_path, report)
    assert any(i.code == ErrorCode.PLG001 for i in report.issues)


def test_plugin_plg002_invalid_name(tmp_path: Path) -> None:
    """PLG002: Invalid plugin name format."""
    plugin_file = tmp_path / 'plugin.json'
    plugin_file.write_text(
        json.dumps({
            'name': 'My_Plugin_123',
            'version': '1.0.0',
            'license': 'Apache-2.0',
        }),
        encoding='utf-8',
    )

    report = ValidationReport()
    validate_plugin_manifest_file(plugin_file, tmp_path, report)
    assert any(i.code == ErrorCode.PLG002 for i in report.issues)


def test_plugin_plg003_invalid_version(tmp_path: Path) -> None:
    """PLG003: Version string violates Semantic Versioning."""
    plugin_file = tmp_path / 'plugin.json'
    plugin_file.write_text(
        json.dumps({
            'name': 'valid-plugin',
            'version': 'v1.0',
            'license': 'Apache-2.0',
        }),
        encoding='utf-8',
    )

    report = ValidationReport()
    validate_plugin_manifest_file(plugin_file, tmp_path, report)
    assert any(i.code == ErrorCode.PLG003 for i in report.issues)


def test_plugin_plg004_missing_logo_file(tmp_path: Path) -> None:
    """PLG004: Logo file path does not exist on disk."""
    plugin_file = tmp_path / 'plugin.json'
    plugin_file.write_text(
        json.dumps({
            'name': 'valid-plugin',
            'version': '1.0.0',
            'license': 'Apache-2.0',
            'logo': 'assets/nonexistent_logo.svg',
        }),
        encoding='utf-8',
    )

    report = ValidationReport()
    validate_plugin_manifest_file(plugin_file, tmp_path, report)
    assert any(i.code == ErrorCode.PLG004 for i in report.issues)


def test_plugin_plg005_invalid_license(tmp_path: Path) -> None:
    """PLG005: License is not a valid SPDX identifier."""
    plugin_file = tmp_path / 'plugin.json'
    plugin_file.write_text(
        json.dumps({
            'name': 'valid-plugin',
            'version': '1.0.0',
            'license': 'Custom-Non-SPDX-License',
        }),
        encoding='utf-8',
    )

    report = ValidationReport()
    validate_plugin_manifest_file(plugin_file, tmp_path, report)
    assert any(i.code == ErrorCode.PLG005 for i in report.issues)


def test_plugin_plg006_missing_discovery_files(tmp_path: Path) -> None:
    """PLG006: Missing .agents/skills.json or .agents/rules.json discovery file."""
    report = ValidationReport()
    validate_discovery_configs(tmp_path, report)
    assert any(i.code == ErrorCode.PLG006 for i in report.issues)


# ============================================================================
# 7. Prompt & Consistency Tests (PRM001 - PRM003)
# ============================================================================


def test_prompt_prm001_dangling_skill_reference(tmp_path: Path) -> None:
    """PRM001: Cross-skill link references non-existent skill."""
    skills_dir = tmp_path / 'skills'
    skill_a = skills_dir / 'skill-a'
    skill_a.mkdir(parents=True)
    (skill_a / 'SKILL.md').write_text(
        '---\nname: skill-a\ndescription: Valid description with at least 20 chars\n---\n## Related Skills\n\n- `/skill-b`: Companion skill that does not exist\n',
        encoding='utf-8',
    )

    report = ValidationReport()
    validate_prompts(tmp_path, report)
    assert any(i.code == ErrorCode.PRM001 for i in report.issues)


def test_prompt_prm002_contradictory_merge_directives(tmp_path: Path) -> None:
    """PRM002: Contradictory PR merge directives (autonomous merge permitted)."""
    rules_dir = tmp_path / 'rules'
    rules_dir.mkdir(parents=True)
    (rules_dir / 'AGENTS.md').write_text(
        '# Rules\nAutonomous merge is permitted for approved PRs.\n',
        encoding='utf-8',
    )

    report = ValidationReport()
    validate_prompts(tmp_path, report)
    assert any(i.code == ErrorCode.PRM002 for i in report.issues)


def test_prompt_prm003_prescribing_pixi_in_uv_repo(tmp_path: Path) -> None:
    """PRM003: Prescribing pixi for commands in pure uv repo."""
    rules_dir = tmp_path / 'rules'
    rules_dir.mkdir(parents=True)
    (rules_dir / 'AGENTS.md').write_text(
        '# Rules\nRun pixi run build to compile the project.\n',
        encoding='utf-8',
    )

    report = ValidationReport()
    validate_prompts(tmp_path, report)
    assert any(i.code == ErrorCode.PRM003 for i in report.issues)


# ============================================================================
# 8. Tool Schemas Tests (TLS001 - TLS002)
# ============================================================================


def test_tool_schema_tls001_missing_valid_type() -> None:
    """TLS001: Tool schema parameter missing valid JSON Schema type."""
    schema = {
        'properties': {
            'param_no_type': {'description': 'missing type'},
            'param_bad_type': {'type': 'unknown_type', 'description': 'bad'},
        },
    }
    report = ValidationReport()
    validate_tool_parameter_schema(schema, 'test_tool', report, 'test_path')
    assert any(i.code == ErrorCode.TLS001 for i in report.issues)


def test_tool_schema_tls002_required_item_not_in_properties() -> None:
    """TLS002: Item in required array not present under properties."""
    schema = {
        'properties': {
            'valid_param': {'type': 'string', 'description': 'desc'},
        },
        'required': ['valid_param', 'missing_param'],
    }
    report = ValidationReport()
    validate_tool_parameter_schema(schema, 'test_tool', report, 'test_path')
    assert any(i.code == ErrorCode.TLS002 for i in report.issues)


# ============================================================================
# 9. Secret Hygiene Tests (SEC001 - SEC002)
# ============================================================================


def test_secret_sec001_home_path_leak(tmp_path: Path) -> None:
    """SEC001: Leaked home path in repository file."""
    bad_file = tmp_path / 'leaked.txt'
    # Split strings so test file itself is not flagged
    bad_file.write_text('Path is ' + '/Users/' + 'jamie' + '/project\n', encoding='utf-8')

    report = ValidationReport()
    validate_secret_hygiene(tmp_path, report)
    assert any(i.code == ErrorCode.SEC001 for i in report.issues)


def test_secret_sec002_token_leak(tmp_path: Path) -> None:
    """SEC002: Leaked authentication token in repository file."""
    bad_file = tmp_path / 'leaked.txt'
    bad_file.write_text('Token: ghp_' + 'A' * 30 + '\n', encoding='utf-8')

    report = ValidationReport()
    validate_secret_hygiene(tmp_path, report)
    assert any(i.code == ErrorCode.SEC002 for i in report.issues)


# ============================================================================
# 10. Reporter & Models Unit Tests
# ============================================================================


def test_models_report_counts_and_dict() -> None:
    """Verify ValidationReport counts, serialization, and strict flag behavior."""
    report = ValidationReport(strict=False)
    assert report.is_clean is True

    report.add(
        code=ErrorCode.SKL004,
        message='Warning description',
        severity=Severity.WARNING,
        path='skills/test/SKILL.md',
    )
    assert report.warning_count == 1
    assert report.error_count == 0
    assert report.is_clean is True  # non-strict mode ignores warnings

    strict_report = ValidationReport(strict=True)
    strict_report.add(
        code=ErrorCode.SKL004,
        message='Warning description',
        severity=Severity.WARNING,
        path='skills/test/SKILL.md',
    )
    assert strict_report.is_clean is False  # strict mode fails on warnings

    d = report.to_dict()
    assert d['passed'] is True
    assert d['warningCount'] == 1
    assert d['errorCount'] == 0


def test_reporter_formatting_and_render() -> None:
    """Verify format_terminal and render_report handle clean and failed reports."""
    clean_report = ValidationReport()
    term_clean = format_terminal(clean_report, use_color=False)
    assert '[PASS]' in term_clean

    fail_report = ValidationReport()
    fail_report.add_issue(
        ValidationIssue(
            code=ErrorCode.SKL001,
            message='Missing file',
            severity=Severity.ERROR,
            path='skills/test',
            line=10,
            suggestion='Create it',
        )
    )
    term_fail = format_terminal(fail_report, use_color=False)
    assert '[FAIL]' in term_fail
    assert 'SKL001' in term_fail
    assert 'Suggestion: Create it' in term_fail

    json_str = format_json(fail_report)
    parsed = json.loads(json_str)
    assert parsed['passed'] is False
    assert parsed['errorCount'] == 1


# ============================================================================
# 11. Tier 5 Adversarial Coverage & Hardening Tests (D1 - D4 & White-box gaps)
# ============================================================================


def test_hooks_hok006_cli_option_not_flagged(tmp_path: Path) -> None:
    """D1: Handler command with CLI flag option argument does not trigger false-positive HOK006."""
    scripts_dir = tmp_path / 'scripts'
    scripts_dir.mkdir(parents=True)
    guard = scripts_dir / 'guard.py'
    guard.write_text('print(1)\n', encoding='utf-8')
    guard.chmod(0o755)

    hooks_file = tmp_path / 'hooks.json'
    hooks_file.write_text(
        json.dumps({
            'guard': {
                'enabled': True,
                'SessionStart': [{'command': 'python scripts/guard.py --target=foo.py -o=output.sh'}],
            }
        }),
        encoding='utf-8',
    )
    report = ValidationReport()
    validate_hooks_file(hooks_file, tmp_path, report)
    assert not any(i.code == ErrorCode.HOK006 for i in report.issues)


def test_prompt_prm003_negative_contexts_not_flagged(tmp_path: Path) -> None:
    """D2: Prohibition contexts for pixi (e.g. 'NEVER run pixi', 'no pixi', 'do not use pixi') do not trigger PRM003."""
    rules_dir = tmp_path / 'rules'
    rules_dir.mkdir(parents=True)
    (rules_dir / 'AGENTS.md').write_text(
        "# Rules\n1. NEVER run pixi run test in this repo; use uv run pytest.\n2. No pixi add allowed.\n3. Do not use pixi run.\n4. Forbidden: pixi run build.\n5. Don't use pixi install.\n",
        encoding='utf-8',
    )
    report = ValidationReport()
    validate_prompts(tmp_path, report)
    assert not any(i.code == ErrorCode.PRM003 for i in report.issues)


def test_prompt_prm003_prescribing_pixi_flagged(tmp_path: Path) -> None:
    """D2 complementary: Actually prescribing pixi run triggers PRM003."""
    rules_dir = tmp_path / 'rules'
    rules_dir.mkdir(parents=True)
    (rules_dir / 'AGENTS.md').write_text(
        '# Rules\nAlways execute tests with `pixi run test`.\n',
        encoding='utf-8',
    )
    report = ValidationReport()
    validate_prompts(tmp_path, report)
    assert any(i.code == ErrorCode.PRM003 for i in report.issues)


def test_plugin_plg006_entries_type_check(tmp_path: Path) -> None:
    """D3: 'entries' field in discovery config must be a list, otherwise emits PLG006."""
    agents_dir = tmp_path / '.agents'
    agents_dir.mkdir(parents=True)
    (agents_dir / 'skills.json').write_text(json.dumps({'entries': 'not_a_list'}), encoding='utf-8')
    (agents_dir / 'rules.json').write_text(json.dumps({'entries': 12345}), encoding='utf-8')

    report = ValidationReport()
    validate_discovery_configs(tmp_path, report)
    plg006_issues = [i for i in report.issues if i.code == ErrorCode.PLG006]
    assert len(plg006_issues) == 2
    assert all("must be a JSON object containing an 'entries' list" in i.message for i in plg006_issues)


def test_mcp_mcp002_args_and_env_type_checks(tmp_path: Path) -> None:
    """D4: 'args' must be a list and 'env' must be a dict in MCP server configuration (MCP002)."""
    mcp_file = tmp_path / 'mcp_config.json'
    mcp_file.write_text(
        json.dumps({
            'mcpServers': {
                'srv1': {
                    'command': 'python',
                    'args': 'invalid_string_args',
                    'env': 'invalid_string_env',
                }
            }
        }),
        encoding='utf-8',
    )
    report = ValidationReport()
    validate_mcp_config_file(mcp_file, report)
    assert any(i.code == ErrorCode.MCP002 and "'args' must be a list" in i.message for i in report.issues)
    assert any(i.code == ErrorCode.MCP002 and "'env' must be a dictionary" in i.message for i in report.issues)


def test_hooks_non_dict_handler(tmp_path: Path) -> None:
    """Adversarial: Handler configured as string or number instead of dict emits HOK004."""
    hooks_file = tmp_path / 'hooks.json'
    hooks_file.write_text(
        json.dumps({'guard': {'enabled': True, 'SessionStart': ['not_a_dict']}}),
        encoding='utf-8',
    )
    report = ValidationReport()
    validate_hooks_file(hooks_file, tmp_path, report)
    assert any(i.code == ErrorCode.HOK004 and 'must be a dictionary object' in i.message for i in report.issues)


def test_hooks_shlex_quote_fallback(tmp_path: Path) -> None:
    """Adversarial: Handler command with unclosed quote falls back to split()."""
    hooks_file = tmp_path / 'hooks.json'
    hooks_file.write_text(
        json.dumps({
            'guard': {
                'enabled': True,
                'SessionStart': [{'command': 'python -c "unclosed quote scripts/non_existent.py'}],
            }
        }),
        encoding='utf-8',
    )
    report = ValidationReport()
    validate_hooks_file(hooks_file, tmp_path, report)
    assert any(i.code == ErrorCode.HOK006 for i in report.issues)


def test_hooks_executable_bit_and_fix(tmp_path: Path) -> None:
    """Adversarial: Script exists without +x bit; fix=False reports error, fix=True resolves it."""
    scripts_dir = tmp_path / 'scripts'
    scripts_dir.mkdir(parents=True)
    guard = scripts_dir / 'guard.py'
    guard.write_text('print(1)\n', encoding='utf-8')
    guard.chmod(0o644)

    hooks_file = tmp_path / 'hooks.json'
    hooks_file.write_text(
        json.dumps({'guard': {'enabled': True, 'SessionStart': [{'command': 'python scripts/guard.py'}]}}),
        encoding='utf-8',
    )

    report_nofix = ValidationReport()
    validate_hooks_file(hooks_file, tmp_path, report_nofix, fix=False)
    assert any(i.code == ErrorCode.HOK006 and 'lacks executable bit' in i.message for i in report_nofix.issues)

    report_fix = ValidationReport()
    validate_hooks_file(hooks_file, tmp_path, report_fix, fix=True)
    assert os.access(guard, os.X_OK)


def test_hooks_unreadable_file(tmp_path: Path) -> None:
    """Adversarial: Unreadable or non-UTF8 hooks.json emits HOK001."""
    hooks_file = tmp_path / 'hooks.json'
    hooks_file.write_bytes(b'\x80\x81\x82 invalid binary')
    report = ValidationReport()
    validate_hooks_file(hooks_file, tmp_path, report)
    assert any(i.code == ErrorCode.HOK001 and 'Failed to read hooks file' in i.message for i in report.issues)


def test_hooks_structural_type_mismatches(tmp_path: Path) -> None:
    """Adversarial: Structural type errors in hooks.json (root, group, enabled, tool event, flat event)."""
    hooks_file = tmp_path / 'hooks.json'
    # Root not dict
    hooks_file.write_text(json.dumps([1, 2, 3]), encoding='utf-8')
    rep1 = ValidationReport()
    validate_hooks_file(hooks_file, tmp_path, rep1)
    assert any(i.code == ErrorCode.HOK001 and 'root must be a JSON object' in i.message for i in rep1.issues)

    # Group not dict, enabled not bool, tool event not list, flat event not list
    hooks_file.write_text(
        json.dumps({
            'g1': 'not_dict',
            'g2': {
                'enabled': 'yes',
                'PreToolUse': 'not_list',
                'SessionStart': 'not_list',
            },
            'g3': {
                'enabled': True,
                'PreToolUse': [{'matcher': 'tool', 'hooks': 'not_list'}],
            },
        }),
        encoding='utf-8',
    )
    rep2 = ValidationReport()
    validate_hooks_file(hooks_file, tmp_path, rep2)
    assert any('must be an object' in i.message for i in rep2.issues)
    assert any('must be a boolean' in i.message for i in rep2.issues)
    assert any(i.code == ErrorCode.HOK003 and 'must be an array' in i.message for i in rep2.issues)
    assert any(i.code == ErrorCode.HOK004 and 'must be an array' in i.message for i in rep2.issues)


def test_hooks_discovery_in_dot_agents(tmp_path: Path) -> None:
    """Adversarial: validate_hooks discovers .agents/hooks.json."""
    ad = tmp_path / '.agents'
    ad.mkdir(parents=True)
    (ad / 'hooks.json').write_text(json.dumps({'g': {'enabled': True, 'SessionStart': []}}), encoding='utf-8')
    rep = ValidationReport()
    validate_hooks(tmp_path, rep)
    assert rep.is_clean


def test_mcp_unreadable_file(tmp_path: Path) -> None:
    """Adversarial: Unreadable or corrupt binary mcp_config.json emits MCP001."""
    config_file = tmp_path / 'mcp_config.json'
    config_file.write_bytes(b'\xfe\xff invalid binary')
    report = ValidationReport()
    validate_mcp_config_file(config_file, report)
    assert any(i.code == ErrorCode.MCP001 and 'Failed to read' in i.message for i in report.issues)


def test_mcp_structural_type_errors(tmp_path: Path) -> None:
    """Adversarial: Root not dict, spec not dict, variables not list, variable not dict/missing name."""
    config_file = tmp_path / 'mcp_config.json'
    # Root not dict
    config_file.write_text(json.dumps(['not', 'dict']), encoding='utf-8')
    rep1 = ValidationReport()
    validate_mcp_config_file(config_file, rep1)
    assert any(i.code == ErrorCode.MCP001 and 'must be a JSON object' in i.message for i in rep1.issues)

    # Server name invalid chars, server prefix >= 64, spec not dict, variables not list, var item not dict
    long_srv = 'a' * 60
    config_file.write_text(
        json.dumps({
            'mcpServers': {
                'invalid server!': {'command': 'echo'},
                long_srv: {'command': 'echo'},
                'srv_not_dict': 'string',
                'srv_vars_bad': {'command': 'echo', 'variables': 'not_list'},
                'srv_var_not_dict': {'command': 'echo', 'variables': ['not_dict']},
                'srv_tools': {'command': 'echo', 'tools': [{'name': 'tool_too_long_' + 'x' * 60}]},
            }
        }),
        encoding='utf-8',
    )
    rep2 = ValidationReport()
    validate_mcp_config_file(config_file, rep2, known_tools={'srv_tools': ['tool_too_long_' + 'x' * 60]})
    assert any(i.code == ErrorCode.MCP008 and 'invalid characters' in i.message for i in rep2.issues)
    assert any(i.code == ErrorCode.MCP008 and 'is too long' in i.message for i in rep2.issues)
    assert any(i.code == ErrorCode.MCP002 and 'must be an object' in i.message for i in rep2.issues)
    assert any(i.code == ErrorCode.MCP002 and 'must be a list of variable objects' in i.message for i in rep2.issues)
    assert any(i.code == ErrorCode.MCP007 and "must be an object with 'name'" in i.message for i in rep2.issues)
    assert any(i.code == ErrorCode.MCP008 and 'exceeds 64 characters' in i.message for i in rep2.issues)


def test_mcp_discovery_in_dot_agents(tmp_path: Path) -> None:
    """Adversarial: validate_mcp_config discovers .agents/mcp_config.json."""
    ad = tmp_path / '.agents'
    ad.mkdir(parents=True)
    (ad / 'mcp_config.json').write_text(json.dumps({'mcpServers': {'s': {'command': 'echo'}}}), encoding='utf-8')
    rep = ValidationReport()
    validate_mcp_config(tmp_path, rep)
    assert rep.is_clean


def test_plugin_unreadable_file(tmp_path: Path) -> None:
    """Adversarial: Unreadable or corrupt binary plugin.json emits PLG001."""
    plugin_file = tmp_path / 'plugin.json'
    plugin_file.write_bytes(b'\x80\x81 invalid')
    report = ValidationReport()
    validate_plugin_manifest_file(plugin_file, tmp_path, report)
    assert any(i.code == ErrorCode.PLG001 and 'Failed to read' in i.message for i in report.issues)


def test_plugin_root_not_dict(tmp_path: Path) -> None:
    """Adversarial: Root of plugin.json not an object emits PLG001."""
    plugin_file = tmp_path / 'plugin.json'
    plugin_file.write_text(json.dumps(['not', 'a', 'dict']), encoding='utf-8')
    report = ValidationReport()
    validate_plugin_manifest_file(plugin_file, tmp_path, report)
    assert any(i.code == ErrorCode.PLG001 and 'must be a JSON object' in i.message for i in report.issues)


def test_plugin_discovery_configs_corrupt_json(tmp_path: Path) -> None:
    """Adversarial: Corrupt JSON in discovery configs emits PLG006."""
    ad = tmp_path / '.agents'
    ad.mkdir(parents=True)
    (ad / 'skills.json').write_text('{ invalid json', encoding='utf-8')
    (ad / 'rules.json').write_text(json.dumps({'missing_entries': True}), encoding='utf-8')
    report = ValidationReport()
    validate_discovery_configs(tmp_path, report)
    assert any(i.code == ErrorCode.PLG006 and 'Failed to parse' in i.message for i in report.issues)
    assert any(i.code == ErrorCode.PLG006 and "must be a JSON object containing an 'entries' list" in i.message for i in report.issues)


def test_prompt_hidden_dirs_and_missing_skill_md(tmp_path: Path) -> None:
    """Adversarial: Hidden directories in skills/ and directories without SKILL.md skipped."""
    skills_dir = tmp_path / 'skills'
    (skills_dir / '.git').mkdir(parents=True)
    (skills_dir / 'empty-skill').mkdir(parents=True)
    report = ValidationReport()
    validate_prompts(tmp_path, report)
    assert report.is_clean


def test_prompt_unreadable_files(tmp_path: Path) -> None:
    """Adversarial: Unreadable SKILL.md and rules/AGENTS.md handled gracefully without crash."""
    skills_dir = tmp_path / 'skills' / 'bad-skill'
    skills_dir.mkdir(parents=True)
    (skills_dir / 'SKILL.md').write_bytes(b'\x80\x81 invalid binary')
    rules_dir = tmp_path / 'rules'
    rules_dir.mkdir(parents=True)
    (rules_dir / 'AGENTS.md').write_bytes(b'\x80\x81 invalid binary')
    report = ValidationReport()
    validate_prompts(tmp_path, report)
    assert report.is_clean


def test_rules_unreadable_rule_file(tmp_path: Path) -> None:
    """Adversarial: Unreadable rule file in rules/ emits RUL004."""
    rules_dir = tmp_path / 'rules'
    rules_dir.mkdir(parents=True)
    (rules_dir / 'bad.md').write_bytes(b'\x80\x81 invalid binary')
    report = ValidationReport()
    validate_rules(tmp_path, report)
    assert any(i.code == ErrorCode.RUL004 and 'Failed to read rule file' in i.message for i in report.issues)


def test_skills_unreadable_skill_md(tmp_path: Path) -> None:
    """Adversarial: Unreadable SKILL.md in skills/ emits SKL002."""
    skill_dir = tmp_path / 'skills' / 'bad-skill'
    skill_dir.mkdir(parents=True)
    (skill_dir / 'SKILL.md').write_bytes(b'\x80\x81 invalid binary')
    report = ValidationReport()
    validate_skill_directory(skill_dir, report)
    assert any(i.code == ErrorCode.SKL002 and 'Failed to read' in i.message for i in report.issues)


def test_skills_frontmatter_non_dict(tmp_path: Path) -> None:
    """Adversarial: Frontmatter parsed as string or list instead of dict emits SKL002."""
    skill_dir = tmp_path / 'skills' / 'bad-skill'
    skill_dir.mkdir(parents=True)
    (skill_dir / 'SKILL.md').write_text('---\n- item 1\n- item 2\n---\nBody\n', encoding='utf-8')
    report = ValidationReport()
    validate_skill_directory(skill_dir, report)
    assert any(i.code == ErrorCode.SKL002 and 'YAML frontmatter must evaluate to a dictionary' in i.message for i in report.issues)


def test_skills_chmod_os_error_handling(tmp_path: Path) -> None:
    """Adversarial: chmod raising OSError during fix=True emits SKL007 with error message."""
    skill_dir = tmp_path / 'skills' / 'my-skill'
    scripts_dir = skill_dir / 'scripts'
    scripts_dir.mkdir(parents=True)
    (skill_dir / 'SKILL.md').write_text(
        '---\nname: my-skill\ndescription: Valid skill description with 20+ chars\n---\nBody\n',
        encoding='utf-8',
    )
    helper = scripts_dir / 'helper.sh'
    helper.write_text('#!/bin/sh\necho 1\n', encoding='utf-8')
    helper.chmod(0o644)

    report = ValidationReport()
    with patch.object(Path, 'chmod', side_effect=OSError('Permission denied')):
        validate_skill_directory(skill_dir, report, fix=True)
    assert any(i.code == ErrorCode.SKL007 and 'Failed to set executable bit' in i.message for i in report.issues)


def test_tool_schema_structural_and_union_errors(tmp_path: Path) -> None:
    """Adversarial: Tool schema properties not dict, param not dict, union type invalid, required not list."""
    # properties not dict
    rep1 = ValidationReport()
    validate_tool_parameter_schema({'properties': 'not_dict'}, 't', rep1, 'p')
    assert any(i.code == ErrorCode.TLS001 and "'properties' must be a JSON object" in i.message for i in rep1.issues)

    # param not dict
    rep2 = ValidationReport()
    validate_tool_parameter_schema({'properties': {'p1': 'not_dict'}}, 't', rep2, 'p')
    assert any(i.code == ErrorCode.TLS001 and 'must be a JSON object specification' in i.message for i in rep2.issues)

    # invalid union type
    rep3 = ValidationReport()
    validate_tool_parameter_schema({'properties': {'p1': {'type': ['string', 'invalid_custom_type']}}}, 't', rep3, 'p')
    assert any(i.code == ErrorCode.TLS001 and 'has invalid union type' in i.message for i in rep3.issues)

    # type not string and not list
    rep4 = ValidationReport()
    validate_tool_parameter_schema({'properties': {'p1': {'type': 12345}}}, 't', rep4, 'p')
    assert any(i.code == ErrorCode.TLS001 and "has non-string 'type' field" in i.message for i in rep4.issues)

    # required not list
    rep5 = ValidationReport()
    validate_tool_parameter_schema({'properties': {'p1': {'type': 'string'}}, 'required': 'not_list'}, 't', rep5, 'p')
    assert any(i.code == ErrorCode.TLS002 and "'required' must be a list" in i.message for i in rep5.issues)

    # directory discovery scanner in schemas/ and resources/schemas/
    schemas_dir = tmp_path / 'schemas'
    schemas_dir.mkdir(parents=True)
    (schemas_dir / 'tool1.json').write_text(json.dumps({'properties': {'p': {'type': 'invalid'}}}), encoding='utf-8')
    (schemas_dir / 'corrupt.json').write_text('{ invalid json', encoding='utf-8')
    res_schemas_dir = tmp_path / 'resources' / 'schemas'
    res_schemas_dir.mkdir(parents=True)
    (res_schemas_dir / 'tool2.json').write_text(json.dumps({'properties': {'p': {'type': 'invalid'}}}), encoding='utf-8')
    rep6 = ValidationReport()
    validate_tool_schemas(tmp_path, rep6)
    assert len([i for i in rep6.issues if i.code == ErrorCode.TLS001]) == 2


def test_hooks_chmod_os_error_handling(tmp_path: Path) -> None:
    """Adversarial: chmod raising OSError during fix=True in hooks validator emits HOK006 with error."""
    scripts_dir = tmp_path / 'scripts'
    scripts_dir.mkdir(parents=True)
    guard = scripts_dir / 'guard.py'
    guard.write_text('print(1)\n', encoding='utf-8')
    guard.chmod(0o644)

    hooks_file = tmp_path / 'hooks.json'
    hooks_file.write_text(
        json.dumps({'guard': {'enabled': True, 'SessionStart': [{'command': 'python scripts/guard.py'}]}}),
        encoding='utf-8',
    )

    report = ValidationReport()
    with patch.object(Path, 'chmod', side_effect=OSError('Permission denied')):
        validate_hooks_file(hooks_file, tmp_path, report, fix=True)
    assert any(i.code == ErrorCode.HOK006 and 'Failed to set executable bit' in i.message for i in report.issues)


def test_secret_hygiene_binary_filter_and_unreadable(tmp_path: Path) -> None:
    """Adversarial: Secret hygiene ignores binary extensions and handles unreadable files."""
    # Binary file with fake secret pattern in bytes
    (tmp_path / 'image.jpg').write_bytes(b'fake_key_ghp_' + b'A' * 30)
    (tmp_path / 'photo.png').write_bytes(b'fake_key_AIzaSy' + b'B' * 30)
    (tmp_path / 'data.db').write_bytes(b'bearer token')
    # Unreadable non-UTF8 text file
    (tmp_path / 'bad.txt').write_bytes(b'\x80\x81 invalid binary')

    report = ValidationReport()
    validate_secret_hygiene(tmp_path, report)
    assert report.is_clean


def test_cli_flags_full_spectrum(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Adversarial: CLI options --fix, --no-color, --json, --strict, and invalid --path."""
    # Invalid path
    code_inv = main(['--path', str(tmp_path / 'non_existent_directory')])
    assert code_inv == 1

    # Create minimally valid workspace with an unexecutable script
    ad = tmp_path / '.agents'
    ad.mkdir()
    (ad / 'skills.json').write_text(json.dumps({'entries': []}))
    (ad / 'rules.json').write_text(json.dumps({'entries': []}))
    r_dir = tmp_path / 'rules'
    r_dir.mkdir()
    (r_dir / 'AGENTS.md').write_text('# Rules\nValid rule.\n')

    sk_dir = tmp_path / 'skills' / 'my-skill'
    sk_dir.mkdir(parents=True)
    (sk_dir / 'SKILL.md').write_text('---\nname: my-skill\ndescription: Valid skill description with 20+ chars\n---\nBody\n')
    s_dir = sk_dir / 'scripts'
    s_dir.mkdir()
    helper = s_dir / 'run.sh'
    helper.write_text('#!/bin/sh\necho hi\n')
    helper.chmod(0o644)

    # Without fix: fails with SKL007, exit code 1, check --no-color removes ANSI
    code = main(['--no-color', '--path', str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 1
    assert '[FAIL]' in out
    assert 'SKL007' in out
    assert '\033[' not in out

    # With fix: fixes permissions, returns 0
    code_fix = main(['--fix', '--no-color', '--path', str(tmp_path)])
    out_fix = capsys.readouterr().out
    assert code_fix == 0
    assert '[PASS]' in out_fix
    assert os.access(helper, os.X_OK)

    # Failed JSON output schema
    (r_dir / 'AGENTS.md').write_text('---\ntrigger: always_on\n---\n# Frontmatter forbidden in rules/AGENTS.md\n')
    code_json = main(['--json', '--path', str(tmp_path)])
    out_json = capsys.readouterr().out
    assert code_json == 1
    data = json.loads(out_json)
    assert data['passed'] is False
    assert data['errorCount'] >= 1
    assert any(i['code'] == 'RUL002' for i in data['issues'])


def test_local_ci_foreign_working_directory_handling() -> None:
    """Verify scripts/ci/run_local_ci.sh runs cleanly with --help from a foreign git repo."""
    ci_script = REPO_ROOT / 'scripts' / 'ci' / 'run_local_ci.sh'
    assert ci_script.is_file()
    assert os.access(ci_script, os.X_OK)

    git_bin = shutil.which('git')
    assert git_bin is not None

    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run([git_bin, 'init'], cwd=tmpdir, check=True, capture_output=True)
        res = subprocess.run(
            [str(ci_script), '--help'],
            cwd=tmpdir,
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0
        assert 'Usage:' in res.stdout


# ============================================================================
# 11. Supply-Chain & MCP Pinning Validator Tests (MCP009, SUP001 - SUP004)
# ============================================================================


def test_mcp009_rejects_unpinned_docker_uv_uvx_and_npx_servers(tmp_path: Path) -> None:
    """MCP009: Reject floating container tags, unpinned uv/uvx packages, and unpinned npx packages."""
    config_file = tmp_path / 'mcp_config.json'
    config_file.write_text(
        json.dumps({
            'mcpServers': {
                'docker-unpinned': {
                    'command': 'docker',
                    'args': ['run', '-i', '--rm', '-e', 'FOO=1', 'ghcr.io/github/github-mcp-server:v2.1.0'],
                },
                'docker-dashdash-unpinned': {
                    'command': 'docker',
                    'args': ['run', '--rm', '--', 'ghcr.io/github/github-mcp-server'],
                },
                'uv-range': {
                    'command': 'uv',
                    'args': ['run', '--with', 'mcp>=2.2.0', '--with=pyyaml>=6.0', 'python', 'srv.py'],
                },
                'uvx-unpinned': {
                    'command': 'uvx',
                    'args': ['--isolated', '--python', '3.14', '--from=mcp-arxiv', 'mcp-arxiv'],
                },
                'uvx-positional-unpinned': {
                    'command': 'uvx',
                    'args': ['mcp-server-time'],
                },
                'npx-unpinned': {
                    'command': 'npx',
                    'args': ['-y', '@cyanheads/pubmed-mcp-server@latest'],
                },
                'npx-pkg-flag-unpinned': {
                    'command': 'npx',
                    'args': ['--package=@modelcontextprotocol/server-puppeteer', '-c', 'run'],
                },
            }
        }),
        encoding='utf-8',
    )
    report = ValidationReport()
    validate_mcp_config_file(config_file, report)
    mcp009_issues = [i for i in report.issues if i.code == ErrorCode.MCP009]
    assert len(mcp009_issues) == 8


def test_mcp009_accepts_pinned_docker_uv_uvx_and_npx_servers(tmp_path: Path) -> None:
    """MCP009: Accept SHA-256 digest-pinned Docker images and exact ==/@ version pins."""
    digest = 'f' * 64
    config_file = tmp_path / 'mcp_config.json'
    config_file.write_text(
        json.dumps({
            'mcpServers': {
                'docker-pinned': {
                    'command': 'docker',
                    'args': ['run', '-i', '--rm', f'ghcr.io/github/github-mcp-server:v2.1.0@sha256:{digest}'],
                },
                'uv-pinned': {
                    'command': 'uv',
                    'args': ['run', '--with', 'mcp==2.3.0', 'python', '${PLUGIN_ROOT}/srv.py'],
                },
                'uvx-from-pinned': {
                    'command': 'uvx',
                    'args': ['--from=mcp-arxiv==0.1.0', 'mcp-arxiv'],
                },
                'npx-pinned': {
                    'command': 'npx',
                    'args': ['-y', '-p', '@cyanheads/pubmed-mcp-server@2.12.0', '--registry', 'https://registry.npmjs.org'],
                },
            }
        }),
        encoding='utf-8',
    )
    report = ValidationReport()
    validate_mcp_config_file(config_file, report)
    assert report.is_clean, f'Unexpected issues: {report.issues}'


def test_sup001_and_sup002_workflow_pinning_and_permissions(tmp_path: Path) -> None:
    """SUP001/SUP002: Reject unpinned actions, missing version comments, missing permissions, and unsafe checkout."""
    wf_dir = tmp_path / '.github' / 'workflows'
    wf_dir.mkdir(parents=True)
    bad_wf = wf_dir / 'bad.yml'
    sha = '3d3c42e5aac5ba805825da76410c181273ba90b1'
    bad_wf.write_text(
        f"""name: Bad Workflow
on: [push]
jobs:
  build:
    runs-on: ubuntu-24.04
    steps:
      - uses: ./local-action
      - uses: actions/checkout@v4
      - uses: actions/cache@{sha}
      - uses: docker://alpine:3.20
      - uses: org/no-at-sign
""",
        encoding='utf-8',
    )
    report = ValidationReport()
    validate_workflow_file(bad_wf, report)
    sup001 = [i for i in report.issues if i.code == ErrorCode.SUP001]
    sup002 = [i for i in report.issues if i.code == ErrorCode.SUP002]
    assert len(sup001) == 4  # @v4, missing # vX.Y.Z comment, unpinned docker://, missing @
    assert len(sup002) == 2  # missing permissions + checkout without persist-credentials: false


def test_sup001_malformed_and_non_mapping_workflow(tmp_path: Path) -> None:
    """SUP001: Malformed YAML or non-mapping workflow file emits SUP001."""
    bad_yaml = tmp_path / 'corrupt.yml'
    bad_yaml.write_text('jobs: [unclosed', encoding='utf-8')
    rep1 = ValidationReport()
    validate_workflow_file(bad_yaml, rep1)
    assert any(i.code == ErrorCode.SUP001 for i in rep1.issues)

    list_yaml = tmp_path / 'list.yml'
    list_yaml.write_text('- item1\n- item2\n', encoding='utf-8')
    rep2 = ValidationReport()
    validate_workflow_file(list_yaml, rep2)
    assert any(i.code == ErrorCode.SUP001 for i in rep2.issues)

    missing_wf = tmp_path / 'missing.yml'
    rep3 = ValidationReport()
    validate_workflow_file(missing_wf, rep3)
    assert any(i.code == ErrorCode.SUP001 for i in rep3.issues)


def test_sup003_pre_commit_sha_pinning_validation(tmp_path: Path) -> None:
    """SUP003: Reject mutable tags in .pre-commit-config.yaml and accept 40-char commit SHAs."""
    pc_file = tmp_path / '.pre-commit-config.yaml'
    pc_file.write_text(
        """repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: check-yaml
  - repo: local
    hooks:
      - id: ruff
        name: ruff
        entry: uv run ruff check
        language: system
""",
        encoding='utf-8',
    )
    rep_bad = ValidationReport()
    validate_pre_commit_file(pc_file, rep_bad)
    assert any(i.code == ErrorCode.SUP003 for i in rep_bad.issues)

    pc_file.write_text(
        """repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: 3e8a8703264a2f4a69428a0aa4dcb512790b2c8c # frozen: v6.0.0
    hooks:
      - id: check-yaml
""",
        encoding='utf-8',
    )
    rep_good = ValidationReport()
    validate_pre_commit_file(pc_file, rep_good)
    assert rep_good.is_clean


def test_sup004_renovate_jsonc_and_dependabot_validation(tmp_path: Path) -> None:
    """SUP004: Validate JSONC comment stripping, Renovate digest presets, and Dependabot ecosystems."""
    sample_jsonc = """{
  // Line comment with https://url.example/test
  /* Block comment
     spanning lines */
  "url": "https://docs.renovatebot.com/renovate-schema.json",
  "escaped": "value with \\"quote\\" // not a comment",
  "extends": ["config:best-practices"],
  "pre-commit": {"enabled": false}
}"""
    parsed = json.loads(strip_jsonc_comments(sample_jsonc))
    assert parsed['url'] == 'https://docs.renovatebot.com/renovate-schema.json'
    assert '// not a comment' in parsed['escaped']

    renovate_file = tmp_path / 'renovate.jsonc'
    renovate_file.write_text(sample_jsonc, encoding='utf-8')
    rep_ren = ValidationReport()
    validate_renovate_file(renovate_file, rep_ren)
    sup004_ren = [i for i in rep_ren.issues if i.code == ErrorCode.SUP004]
    assert len(sup004_ren) == 2

    dependabot_dir = tmp_path / '.github'
    dependabot_dir.mkdir(parents=True)
    dep_file = dependabot_dir / 'dependabot.yml'
    dep_file.write_text('version: 2\nupdates:\n  - package-ecosystem: "uv"\n    directory: "/"\n', encoding='utf-8')
    rep_dep = ValidationReport()
    validate_supply_chain(tmp_path, rep_dep)
    assert any(i.code == ErrorCode.SUP004 and 'github-actions' in i.message for i in rep_dep.issues)


def test_sup004_rejects_shadowing_renovate_json_alongside_renovate_jsonc(tmp_path: Path) -> None:
    """SUP004: Reject duplicate renovate.json or .renovaterc files shadowing renovate.jsonc."""
    valid_jsonc = json.dumps({
        'extends': ['config:best-practices', 'helpers:pinGitHubActionDigestsToSemver'],
        'pre-commit': {'enabled': True},
    })
    (tmp_path / 'renovate.jsonc').write_text(valid_jsonc, encoding='utf-8')
    (tmp_path / 'renovate.json').write_text('{"extends": ["config:recommended"]}\n', encoding='utf-8')
    (tmp_path / '.renovaterc').write_text('{}\n', encoding='utf-8')

    rep_bad = ValidationReport()
    validate_supply_chain(tmp_path, rep_bad)
    sup004_issues = [i for i in rep_bad.issues if i.code == ErrorCode.SUP004]
    assert len(sup004_issues) == 2
    assert any('renovate.json' in i.message for i in sup004_issues)
    assert any('.renovaterc' in i.message for i in sup004_issues)

    (tmp_path / 'renovate.json').unlink()
    (tmp_path / '.renovaterc').unlink()
    rep_good = ValidationReport()
    validate_supply_chain(tmp_path, rep_good)
    assert rep_good.is_clean


def test_sup004_renovate_runner_rule_requires_pep440_versioning(tmp_path: Path) -> None:
    """SUP004: Ensure github-runners ubuntu rule with allowedVersions specifies pep440 versioning."""
    bad_config: dict[str, Any] = {
        'extends': ['config:best-practices', 'helpers:pinGitHubActionDigestsToSemver'],
        'pre-commit': {'enabled': True},
        'packageRules': [
            {
                'matchDatasources': ['github-runners'],
                'matchPackageNames': ['ubuntu'],
                'allowedVersions': '<=24.04',
            }
        ],
    }
    renovate_file = tmp_path / 'renovate.jsonc'
    renovate_file.write_text(json.dumps(bad_config), encoding='utf-8')
    rep = ValidationReport()
    validate_renovate_file(renovate_file, rep)
    sup004 = [i for i in rep.issues if i.code == ErrorCode.SUP004]
    assert len(sup004) == 1
    assert 'versioning' in sup004[0].message
    assert 'pep440' in sup004[0].message

    # Fixing with versioning: pep440 resolves the issue
    bad_config['packageRules'][0]['versioning'] = 'pep440'
    renovate_file.write_text(json.dumps(bad_config), encoding='utf-8')
    rep_fixed = ValidationReport()
    validate_renovate_file(renovate_file, rep_fixed)
    assert rep_fixed.is_clean


def test_sup003_rejects_push_workflow_pre_commit_without_skip_no_commit_to_branch(tmp_path: Path) -> None:
    """SUP003: Reject push-to-main workflows running pre-commit without SKIP=no-commit-to-branch."""
    sha_pc = '3e8a8703264a2f4a69428a0aa4dcb512790b2c8c'
    sha_co = '3d3c42e5aac5ba805825da76410c181273ba90b1'
    (tmp_path / '.pre-commit-config.yaml').write_text(
        f"""repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: {sha_pc}
    hooks:
      - id: no-commit-to-branch
        args: [--branch, main, --branch, master]
""",
        encoding='utf-8',
    )
    wf_dir = tmp_path / '.github' / 'workflows'
    wf_dir.mkdir(parents=True)
    ci_file = wf_dir / 'ci.yml'
    ci_file.write_text(
        f"""name: CI
on:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  validate:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@{sha_co} # v7.0.1
        with:
          persist-credentials: false
      - name: Run pre-commit checks
        run: uv run pre-commit run --all-files --show-diff-on-failure
""",
        encoding='utf-8',
    )

    rep_bad = ValidationReport()
    validate_supply_chain(tmp_path, rep_bad)
    sup003_issues = [i for i in rep_bad.issues if i.code == ErrorCode.SUP003]
    assert len(sup003_issues) == 1
    assert 'no-commit-to-branch' in sup003_issues[0].message

    ci_file.write_text(
        f"""name: CI
on:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  validate:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@{sha_co} # v7.0.1
        with:
          persist-credentials: false
      - name: Run pre-commit checks
        env:
          SKIP: no-commit-to-branch
        run: uv run pre-commit run --all-files --show-diff-on-failure
""",
        encoding='utf-8',
    )
    rep_good = ValidationReport()
    validate_supply_chain(tmp_path, rep_good)
    assert rep_good.is_clean


def test_mcp008_applies_plugin_namespace_to_tool_identifiers(tmp_path: Path) -> None:
    """Regression (#24): plugin tools register as mcp_<plugin>_<server>_<tool>, so MCP008 must count the plugin prefix."""
    config_file = tmp_path / 'mcp_config.json'
    config_file.write_text(json.dumps({'mcpServers': {'github-mcp-server': {'command': 'echo'}}}), encoding='utf-8')
    tools = {'github-mcp-server': ['add_comment_to_pending_review']}

    rep_global = ValidationReport()
    validate_mcp_config_file(config_file, rep_global, known_tools=tools)
    assert not any(i.code == ErrorCode.MCP008 for i in rep_global.issues), 'mcp_github-mcp-server_add_comment_to_pending_review is 51 chars'

    rep_plugin = ValidationReport()
    validate_mcp_config_file(config_file, rep_plugin, known_tools=tools, plugin_name='mimir-agent-kit')
    assert any(i.code == ErrorCode.MCP008 and 'mcp_mimir-agent-kit_github-mcp-server_add_comment_to_pending_review' in i.message for i in rep_plugin.issues)


def test_validate_mcp_config_loads_plugin_name_and_tool_manifest(tmp_path: Path) -> None:
    """validate_mcp_config reads plugin.json for the namespace and merges scripts/validation/mcp_tool_manifest.json."""
    (tmp_path / 'plugin.json').write_text(json.dumps({'name': 'mimir-agent-kit'}), encoding='utf-8')
    (tmp_path / 'mcp_config.json').write_text(json.dumps({'mcpServers': {'workspace': {'command': 'echo'}}}), encoding='utf-8')
    manifest_dir = tmp_path / 'scripts' / 'validation'
    manifest_dir.mkdir(parents=True)
    manifest_file = manifest_dir / 'mcp_tool_manifest.json'

    # 'mcp_mimir-agent-kit_workspace_' (30) + 33 chars = 63 -> within budget.
    manifest_file.write_text(json.dumps({'workspace': ['batch_modify_gmail_message_labels']}), encoding='utf-8')
    rep_ok = ValidationReport()
    validate_mcp_config(tmp_path, rep_ok)
    assert not any(i.code == ErrorCode.MCP008 for i in rep_ok.issues)

    # Adding a tool that pushes the identifier to 66 chars must fail.
    manifest_file.write_text(json.dumps({'workspace': ['batch_modify_gmail_message_labels_xx']}), encoding='utf-8')
    rep_long = ValidationReport()
    validate_mcp_config(tmp_path, rep_long)
    assert any(i.code == ErrorCode.MCP008 and '(66 chars)' in i.message for i in rep_long.issues)

    # Explicit known_tools are merged with the manifest rather than replacing it.
    manifest_file.write_text(json.dumps({'workspace': ['short']}), encoding='utf-8')
    rep_merged = ValidationReport()
    validate_mcp_config(tmp_path, rep_merged, known_tools={'workspace': ['x' * 40]})
    assert sum(i.code == ErrorCode.MCP008 for i in rep_merged.issues) == 1


def test_load_tool_manifest_tolerates_missing_or_malformed_files(tmp_path: Path) -> None:
    """Malformed or absent manifests degrade to an empty inventory instead of crashing validation."""
    assert load_tool_manifest(tmp_path / 'absent.json') == {}
    bad = tmp_path / 'bad.json'
    bad.write_text('{not json', encoding='utf-8')
    assert load_tool_manifest(bad) == {}
    bad.write_text('[1, 2]', encoding='utf-8')
    assert load_tool_manifest(bad) == {}
    bad.write_text(json.dumps({'srv': ['a'], 'ignored': 'not-a-list'}), encoding='utf-8')
    assert load_tool_manifest(bad) == {'srv': ['a']}

    assert resolve_plugin_name(tmp_path) is None
    (tmp_path / 'plugin.json').write_text('{}', encoding='utf-8')
    assert resolve_plugin_name(tmp_path) == tmp_path.name


def test_mcp009_unwraps_sh_c_launchers_for_pinning(tmp_path: Path) -> None:
    """Regression (#24): `sh -c` credential-injecting wrappers must not bypass digest/version pinning checks."""
    digest = 'a' * 64
    preamble = 'GITHUB_PERSONAL_ACCESS_TOKEN="$(gh auth token --hostname github.com 2>/dev/null)" && [ -n "$GITHUB_PERSONAL_ACCESS_TOKEN" ] || { echo fail >&2; exit 1; }; export GITHUB_PERSONAL_ACCESS_TOKEN; '
    config_file = tmp_path / 'mcp_config.json'
    config_file.write_text(
        json.dumps({
            'mcpServers': {
                'pinned': {'command': 'sh', 'args': ['-c', f'{preamble}exec docker run -i --rm -e GITHUB_PERSONAL_ACCESS_TOKEN ghcr.io/github/github-mcp-server:v2.1.0@sha256:{digest}']},
                'unpinned_docker': {'command': '/bin/sh', 'args': ['-c', f'{preamble}exec docker run -i --rm ghcr.io/github/github-mcp-server:latest']},
                'unpinned_uvx': {'command': 'bash', 'args': ['-c', 'FOO=1 exec uvx some-mcp-server']},
                'malformed': {'command': 'sh', 'args': ['-c', 'exec docker run "unterminated']},
                'not_a_launcher': {'command': 'sh', 'args': ['-c', 'exec ./local-server --stdio']},
            }
        }),
        encoding='utf-8',
    )
    report = ValidationReport()
    validate_mcp_config_file(config_file, report)
    flagged = {i.message.split("'")[1] for i in report.issues if i.code == ErrorCode.MCP009}
    assert flagged == {'unpinned_docker', 'unpinned_uvx'}


def test_mcp009_validates_native_github_mcp_launcher_sha256_pins(tmp_path: Path) -> None:
    """MCP009 enforces exact SemVer and 4-platform 64-hex SHA-256 pins on scripts/github_mcp_launcher.py."""
    digest = 'b' * 64
    scripts_dir = tmp_path / 'scripts'
    scripts_dir.mkdir()
    launcher = scripts_dir / 'github_mcp_launcher.py'
    launcher.write_text(
        f"GITHUB_MCP_SERVER_VERSION = '2.1.0'\nPLATFORM_ARCHIVE_SPECS = {{\n    ('Linux', 'x86_64'): ('a.tar.gz', '{digest}'),\n    ('Linux', 'aarch64'): ('b.tar.gz', '{digest}'),\n    ('Darwin', 'arm64'): ('c.tar.gz', '{digest}'),\n    ('Darwin', 'x86_64'): ('d.tar.gz', '{digest}'),\n}}\n",
        encoding='utf-8',
    )
    config_file = tmp_path / 'mcp_config.json'
    config_file.write_text(
        json.dumps({
            'mcpServers': {
                'github': {
                    'command': 'uv',
                    'args': ['run', '--isolated', '--no-project', 'python', '${PLUGIN_ROOT}/scripts/github_mcp_launcher.py', '--cache-dir', '${PLUGIN_DATA}'],
                },
            },
        }),
        encoding='utf-8',
    )

    rep_ok = ValidationReport()
    validate_mcp_config_file(config_file, rep_ok)
    assert not any(i.code == ErrorCode.MCP009 for i in rep_ok.issues)

    # Drop Darwin/arm64 and SemVer pin -> must emit two MCP009 errors.
    launcher.write_text(
        f"GITHUB_MCP_SERVER_VERSION = 'latest'\nPLATFORM_ARCHIVE_SPECS = {{\n    ('Linux', 'x86_64'): ('a.tar.gz', '{digest}'),\n    ('Linux', 'aarch64'): ('b.tar.gz', '{digest}'),\n    ('Darwin', 'x86_64'): ('d.tar.gz', '{digest}'),\n}}\n",
        encoding='utf-8',
    )
    rep_bad = ValidationReport()
    validate_mcp_config_file(config_file, rep_bad)
    mcp009_msgs = [i.message for i in rep_bad.issues if i.code == ErrorCode.MCP009]
    assert len(mcp009_msgs) == 2
    assert any('SemVer' in msg for msg in mcp009_msgs)
    assert any('Darwin/arm64' in msg for msg in mcp009_msgs)

    # Missing launcher script must also fail MCP009.
    launcher.unlink()
    rep_missing = ValidationReport()
    validate_mcp_config_file(config_file, rep_missing)
    assert any(i.code == ErrorCode.MCP009 and 'missing binary launcher' in i.message for i in rep_missing.issues)
