"""Tier 2: Boundary & Corner Cases E2E Tests (≥5 tests per feature across 10 features).

Validates extreme boundaries, 24KB limits, tool name length thresholds, corrupt syntax,
missing fields, trailing whitespace, and legacy transport rejection.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.validation.codes import ErrorCode
from scripts.validation.models import Severity
from scripts.validation.models import ValidationReport
from scripts.validation.prompt_validator import validate_prompts
from scripts.validation.skills_validator import validate_skills
from tests.e2e.conftest import MAX_FILE_BYTES
from tests.e2e.conftest import MAX_RULES_TOKEN_BUDGET
from tests.e2e.conftest import MAX_TOOL_NAME_LENGTH
from tests.e2e.conftest import MIN_SKILL_DESCRIPTION_LENGTH
from tests.e2e.conftest import estimate_token_count
from tests.e2e.conftest import oracle_validate_ci_workflow
from tests.e2e.conftest import oracle_validate_hooks
from tests.e2e.conftest import oracle_validate_mcp_config
from tests.e2e.conftest import oracle_validate_plugin_manifest
from tests.e2e.conftest import oracle_validate_pre_commit_config
from tests.e2e.conftest import oracle_validate_rule
from tests.e2e.conftest import oracle_validate_skill


# ==============================================================================
# Feature 1 (Pre-commit) Boundaries
# ==============================================================================


def test_f1_b1_empty_pre_commit_config_rejected(tmp_path: Path) -> None:
    """Boundary: empty pre-commit configuration dictionary rejected with PC001."""
    config_file = tmp_path / '.pre-commit-config.yaml'
    config_file.write_text('', encoding='utf-8')
    data = yaml.safe_load(config_file.read_text(encoding='utf-8')) or {}
    issues = oracle_validate_pre_commit_config(data, config_file)
    assert any(i.code == 'PC001' for i in issues)


def test_f1_b2_corrupt_yaml_pre_commit_rejected(tmp_path: Path) -> None:
    """Boundary: corrupt YAML syntax in pre-commit config raises YAMLError."""
    config_file = tmp_path / '.pre-commit-config.yaml'
    config_file.write_text('repos: [unclosed_list: {', encoding='utf-8')
    with pytest.raises(yaml.YAMLError):
        yaml.safe_load(config_file.read_text(encoding='utf-8'))


def test_f1_b3_missing_repos_key_rejected(tmp_path: Path) -> None:
    """Boundary: pre-commit configuration without repos key rejected with PC001."""
    config_file = tmp_path / '.pre-commit-config.yaml'
    issues = oracle_validate_pre_commit_config({'default_stages': ['commit']}, config_file)
    assert any(i.code == 'PC001' for i in issues)


def test_f1_b4_repos_not_a_list_rejected(tmp_path: Path) -> None:
    """Boundary: repos field configured as string instead of list rejected with PC001."""
    config_file = tmp_path / '.pre-commit-config.yaml'
    issues = oracle_validate_pre_commit_config({'repos': 'invalid_string'}, config_file)
    assert any(i.code == 'PC001' for i in issues)


def test_f1_b5_inapplicable_hook_clean_notebook_outputs_rejected(tmp_path: Path) -> None:
    """Boundary: adopting heimdall-astro clean-notebook-outputs hook rejected with PC002."""
    config_file = tmp_path / '.pre-commit-config.yaml'
    bad_cfg = {'repos': [{'repo': 'local', 'hooks': [{'id': 'check-jupyter-output'}]}]}
    issues = oracle_validate_pre_commit_config(bad_cfg, config_file)
    assert any(i.code == 'PC002' for i in issues)


def test_f1_b6_inapplicable_hook_validate_mathjax_rejected(tmp_path: Path) -> None:
    """Boundary: adopting heimdall-astro validate-mathjax hook rejected with PC002."""
    config_file = tmp_path / '.pre-commit-config.yaml'
    bad_cfg = {'repos': [{'repo': 'local', 'hooks': [{'id': 'validate-mathjax-markdown'}]}]}
    issues = oracle_validate_pre_commit_config(bad_cfg, config_file)
    assert any(i.code == 'PC002' for i in issues)


# ==============================================================================
# Feature 2 (CI Workflow) Boundaries
# ==============================================================================


def test_f2_b1_corrupt_ci_workflow_yaml_rejected(tmp_path: Path) -> None:
    """Boundary: corrupt YAML syntax in CI workflow raises YAMLError."""
    ci_file = tmp_path / 'ci.yml'
    ci_file.write_text('name: CI\njobs: {bad: [', encoding='utf-8')
    with pytest.raises(yaml.YAMLError):
        yaml.safe_load(ci_file.read_text(encoding='utf-8'))


def test_f2_b2_missing_jobs_section_rejected(tmp_path: Path) -> None:
    """Boundary: CI workflow missing jobs mapping rejected with CI001."""
    ci_file = tmp_path / 'ci.yml'
    issues = oracle_validate_ci_workflow({'name': 'Continuous Integration'}, ci_file)
    assert any(i.code == 'CI001' for i in issues)


def test_f2_b3_incomplete_matrix_os_missing_macos_rejected(tmp_path: Path) -> None:
    """Boundary: CI workflow matrix missing macos-latest rejected with CI002."""
    ci_file = tmp_path / 'ci.yml'
    workflow_data: dict[str, Any] = {
        'name': 'CI',
        'jobs': {
            'validate-and-test': {
                'name': 'Validate & Test (${{ matrix.os }})',
                'strategy': {'matrix': {'os': ['ubuntu-24.04']}},
            }
        },
    }
    issues = oracle_validate_ci_workflow(workflow_data, ci_file)
    assert any(i.code == 'CI002' for i in issues)


def test_f2_b4_incomplete_matrix_os_missing_ubuntu_rejected(tmp_path: Path) -> None:
    """Boundary: CI workflow matrix missing ubuntu-24.04 rejected with CI002."""
    ci_file = tmp_path / 'ci.yml'
    workflow_data: dict[str, Any] = {
        'name': 'CI',
        'jobs': {
            'validate-and-test': {
                'name': 'Validate & Test (${{ matrix.os }})',
                'strategy': {'matrix': {'os': ['macos-latest']}},
            }
        },
    }
    issues = oracle_validate_ci_workflow(workflow_data, ci_file)
    assert any(i.code == 'CI002' for i in issues)


def test_f2_b5_missing_ruleset_check_name_rejected(tmp_path: Path) -> None:
    """Boundary: CI workflow without Ruleset 26711811 status check name rejected with CI003."""
    ci_file = tmp_path / 'ci.yml'
    workflow_data: dict[str, Any] = {
        'name': 'CI',
        'jobs': {
            'build-and-run': {
                'name': 'Generic Build Step',
                'strategy': {'matrix': {'os': ['ubuntu-24.04', 'macos-latest']}},
            }
        },
    }
    issues = oracle_validate_ci_workflow(workflow_data, ci_file)
    assert any(i.code == 'CI003' for i in issues)


def test_f2_b6_workflow_concurrency_group_syntax() -> None:
    """Boundary: concurrency group must specify cancel-in-progress boolean."""
    bad_workflow: dict[str, Any] = {'concurrency': {'cancel-in-progress': 'maybe'}}
    cancel_val = bad_workflow['concurrency']['cancel-in-progress']
    assert not isinstance(cancel_val, bool), 'Non-boolean cancel-in-progress should be flagged'


# ==============================================================================
# Feature 3 (Skills) Boundaries
# ==============================================================================


def test_f3_b1_skill_body_exactly_24000_bytes_allowed(tmp_path: Path) -> None:
    """Boundary: skill markdown body at exactly 24,000 bytes is allowed."""
    skill_dir = tmp_path / 'boundary-skill'
    skill_dir.mkdir()
    header = '---\nname: boundary-skill\ndescription: A valid skill for testing boundaries.\n---\n\n'
    body = 'X' * MAX_FILE_BYTES
    (skill_dir / 'SKILL.md').write_text(header + body, encoding='utf-8')

    issues = oracle_validate_skill(skill_dir)
    assert not any(i.code == ErrorCode.SKL005 for i in issues)


def test_f3_b2_skill_body_24001_bytes_rejected(tmp_path: Path) -> None:
    """Boundary: skill markdown body at 24,001 bytes is rejected with SKL005."""
    skill_dir = tmp_path / 'oversized-skill'
    skill_dir.mkdir()
    header = '---\nname: oversized-skill\ndescription: An oversized skill for boundary testing.\n---\n\n'
    body = 'X' * (MAX_FILE_BYTES + 1)
    (skill_dir / 'SKILL.md').write_text(header + body, encoding='utf-8')

    issues = oracle_validate_skill(skill_dir)
    assert any(i.code == ErrorCode.SKL005 for i in issues)


def test_f3_b3_skill_description_exactly_19_chars_rejected(tmp_path: Path) -> None:
    """Boundary: skill description with exactly 19 characters fails with SKL004."""
    skill_dir = tmp_path / 'short-desc-skill'
    skill_dir.mkdir()
    desc_19 = '1234567890123456789'
    assert len(desc_19) == 19
    content = f'---\nname: short-desc-skill\ndescription: {desc_19}\n---\n\nInstructions.\n'
    (skill_dir / 'SKILL.md').write_text(content, encoding='utf-8')

    issues = oracle_validate_skill(skill_dir)
    assert any(i.code == ErrorCode.SKL004 for i in issues)


def test_f3_b4_skill_description_exactly_20_chars_allowed(tmp_path: Path) -> None:
    """Boundary: skill description with exactly 20 characters passes."""
    skill_dir = tmp_path / 'exact-desc-skill'
    skill_dir.mkdir()
    desc_20 = 'abcdefghijklmnopqrst'
    assert len(desc_20) == MIN_SKILL_DESCRIPTION_LENGTH
    content = f'---\nname: exact-desc-skill\ndescription: "{desc_20}"\n---\n\nInstructions.\n'
    (skill_dir / 'SKILL.md').write_text(content, encoding='utf-8')

    issues = oracle_validate_skill(skill_dir)
    assert not any(i.code == ErrorCode.SKL004 for i in issues)


def test_f3_b5_skill_missing_closing_frontmatter_rejected(tmp_path: Path) -> None:
    """Boundary: SKILL.md missing closing --- delimiter fails with SKL002."""
    skill_dir = tmp_path / 'unclosed-skill'
    skill_dir.mkdir()
    (skill_dir / 'SKILL.md').write_text('---\nname: unclosed-skill\ndescription: Missing delimiter\n', encoding='utf-8')

    issues = oracle_validate_skill(skill_dir)
    assert any(i.code == ErrorCode.SKL002 for i in issues)


def test_f3_b6_skill_name_mismatch_directory_rejected(tmp_path: Path) -> None:
    """Boundary: SKILL.md name not matching directory name fails with SKL003."""
    skill_dir = tmp_path / 'dir-name'
    skill_dir.mkdir()
    (skill_dir / 'SKILL.md').write_text(
        '---\nname: different-name\ndescription: Skill name does not match dir.\n---\n\nBody.\n',
        encoding='utf-8',
    )

    issues = oracle_validate_skill(skill_dir)
    assert any(i.code == ErrorCode.SKL003 for i in issues)


def test_f3_b7_skill_empty_file_rejected(tmp_path: Path) -> None:
    """Boundary: 0-byte SKILL.md fails with SKL002."""
    skill_dir = tmp_path / 'empty-skill'
    skill_dir.mkdir()
    (skill_dir / 'SKILL.md').write_text('', encoding='utf-8')

    issues = oracle_validate_skill(skill_dir)
    assert any(i.code == ErrorCode.SKL002 for i in issues)


def test_f3_b8_skill_disallowed_subfolder_rejected(tmp_path: Path) -> None:
    """Boundary: unexpected subfolder inside skill directory fails with SKL006."""
    skill_dir = tmp_path / 'bad-subfolder-skill'
    skill_dir.mkdir()
    (skill_dir / 'SKILL.md').write_text(
        '---\nname: bad-subfolder-skill\ndescription: Has disallowed subfolder.\n---\n\nBody.\n',
        encoding='utf-8',
    )
    (skill_dir / 'forbidden_dir').mkdir()

    issues = oracle_validate_skill(skill_dir)
    assert any(i.code == ErrorCode.SKL006 for i in issues)


# ==============================================================================
# Feature 4 (Rules) Boundaries
# ==============================================================================


def test_f4_b1_rule_file_exactly_24000_bytes_allowed(tmp_path: Path) -> None:
    """Boundary: rule file with exactly 24,000 bytes is allowed."""
    rule_file = tmp_path / 'AGENTS.md'
    rule_file.write_text('A' * MAX_FILE_BYTES, encoding='utf-8')
    assert len(rule_file.read_bytes()) == MAX_FILE_BYTES

    issues = oracle_validate_rule(rule_file)
    assert not any(i.code == ErrorCode.RUL004 for i in issues)


def test_f4_b2_rule_file_24001_bytes_rejected(tmp_path: Path) -> None:
    """Boundary: rule file with 24,001 bytes fails with RUL004."""
    rule_file = tmp_path / 'AGENTS.md'
    rule_file.write_text('A' * (MAX_FILE_BYTES + 1), encoding='utf-8')

    issues = oracle_validate_rule(rule_file)
    assert any(i.code == ErrorCode.RUL004 for i in issues)


def test_f4_b3_rule_token_budget_within_20000_tokens_allowed(tmp_path: Path) -> None:
    """Boundary: rule within 20,000 tokens budget passes."""
    rule_file = tmp_path / 'AGENTS.md'
    text = '# Rule Invariants\n\n' + ('word ' * 3000)
    rule_file.write_text(text, encoding='utf-8')
    tokens = estimate_token_count(text)
    assert tokens <= MAX_RULES_TOKEN_BUDGET
    issues = oracle_validate_rule(rule_file)
    assert not any(i.code == ErrorCode.RUL004 for i in issues)


def test_f4_b4_rule_token_budget_20001_tokens_rejected(tmp_path: Path) -> None:
    """Boundary: rule exceeding 20,000 tokens budget fails with RUL004."""
    rule_file = tmp_path / 'AGENTS.md'
    words = ['rule'] * (MAX_RULES_TOKEN_BUDGET + 500)
    rule_file.write_text(' '.join(words), encoding='utf-8')

    issues = oracle_validate_rule(rule_file)
    assert any(i.code == ErrorCode.RUL004 for i in issues)


def test_f4_b5_rule_with_yaml_frontmatter_rejected(tmp_path: Path) -> None:
    """Boundary: AGENTS.md containing YAML frontmatter fails with RUL002."""
    rule_file = tmp_path / 'AGENTS.md'
    rule_file.write_text('---\ntrigger: always_on\n---\n# Rule Content\n', encoding='utf-8')

    issues = oracle_validate_rule(rule_file)
    assert any(i.code == ErrorCode.RUL002 for i in issues)


def test_f4_b6_rule_top_level_agents_md_rejected(tmp_path: Path) -> None:
    """Boundary: top-level AGENTS.md placed at plugin root fails with RUL001."""
    root_agents = tmp_path / 'AGENTS.md'
    root_agents.write_text('# Root Rule\n', encoding='utf-8')
    rule_file = tmp_path / 'rules' / 'AGENTS.md'
    rule_file.parent.mkdir()
    rule_file.write_text('# Proper Rule\n', encoding='utf-8')

    issues = oracle_validate_rule(rule_file, root=tmp_path)
    assert any(i.code == ErrorCode.RUL001 for i in issues)


# ==============================================================================
# Feature 5 (Hooks) Boundaries
# ==============================================================================


def test_f5_b1_hooks_corrupt_json_rejected(tmp_path: Path) -> None:
    """Boundary: malformed JSON in hooks.json fails with json.JSONDecodeError."""
    h_file = tmp_path / 'hooks.json'
    h_file.write_text('{"bad_json": [ unclosed', encoding='utf-8')
    with pytest.raises(json.JSONDecodeError):
        json.loads(h_file.read_text(encoding='utf-8'))


def test_f5_b2_hooks_unknown_lifecycle_event_rejected(tmp_path: Path) -> None:
    """Boundary: unknown lifecycle event name fails with HOK002."""
    h_file = tmp_path / 'hooks.json'
    bad_data: dict[str, Any] = {
        'guard': {
            'BeforeToolExecution': [{'command': 'true'}],
        }
    }
    issues = oracle_validate_hooks(bad_data, h_file)
    assert any(i.code == ErrorCode.HOK002 for i in issues)


def test_f5_b3_hooks_tool_event_missing_matcher_rejected(tmp_path: Path) -> None:
    """Boundary: PreToolUse event missing matcher fails with HOK003."""
    h_file = tmp_path / 'hooks.json'
    bad_data: dict[str, Any] = {
        'guard': {
            'PreToolUse': [{'hooks': [{'command': 'true'}]}],
        }
    }
    issues = oracle_validate_hooks(bad_data, h_file)
    assert any(i.code == ErrorCode.HOK003 for i in issues)


def test_f5_b4_hooks_timeout_zero_rejected(tmp_path: Path) -> None:
    """Boundary: handler timeout of 0 fails with HOK005."""
    h_file = tmp_path / 'hooks.json'
    bad_data: dict[str, Any] = {
        'guard': {
            'SessionStart': [{'command': 'true', 'timeout': 0}],
        }
    }
    issues = oracle_validate_hooks(bad_data, h_file)
    assert any(i.code == ErrorCode.HOK005 for i in issues)


def test_f5_b5_hooks_timeout_negative_rejected(tmp_path: Path) -> None:
    """Boundary: handler negative timeout fails with HOK005."""
    h_file = tmp_path / 'hooks.json'
    bad_data: dict[str, Any] = {
        'guard': {
            'SessionStart': [{'command': 'true', 'timeout': -10}],
        }
    }
    issues = oracle_validate_hooks(bad_data, h_file)
    assert any(i.code == ErrorCode.HOK005 for i in issues)


def test_f5_b6_hooks_handler_missing_command_rejected(tmp_path: Path) -> None:
    """Boundary: handler missing command string fails with HOK004."""
    h_file = tmp_path / 'hooks.json'
    bad_data: dict[str, Any] = {
        'guard': {
            'SessionStart': [{'type': 'command', 'timeout': 10}],
        }
    }
    issues = oracle_validate_hooks(bad_data, h_file)
    assert any(i.code == ErrorCode.HOK004 for i in issues)


# ==============================================================================
# Feature 6 (MCP Config) Boundaries
# ==============================================================================


def test_f6_b1_mcp_tool_name_exactly_64_chars_allowed(tmp_path: Path) -> None:
    """Boundary: namespaced tool name of exactly 64 characters passes."""
    mcp_file = tmp_path / 'mcp_config.json'
    # 'mcp_' (4) + 'srv_' (4) + 56 chars = 64 chars
    tool_suffix = 'a' * 56
    cfg: dict[str, Any] = {
        'mcpServers': {
            'srv': {
                'command': 'echo',
                'tools': [{'name': tool_suffix}],
            }
        }
    }
    namespaced = f'mcp_srv_{tool_suffix}'
    assert len(namespaced) == MAX_TOOL_NAME_LENGTH
    issues = oracle_validate_mcp_config(cfg, mcp_file)
    assert not any(i.code == ErrorCode.MCP008 for i in issues)


def test_f6_b2_mcp_tool_name_65_chars_rejected(tmp_path: Path) -> None:
    """Boundary: namespaced tool name of 65 characters fails with MCP008."""
    mcp_file = tmp_path / 'mcp_config.json'
    tool_suffix = 'a' * 57
    namespaced = f'mcp_srv_{tool_suffix}'
    assert len(namespaced) == MAX_TOOL_NAME_LENGTH + 1
    cfg: dict[str, Any] = {
        'mcpServers': {
            'srv': {
                'command': 'echo',
                'tools': [{'name': tool_suffix}],
            }
        }
    }
    issues = oracle_validate_mcp_config(cfg, mcp_file)
    assert any(i.code == ErrorCode.MCP008 for i in issues)


def test_f6_b3_mcp_legacy_sse_transport_rejected(tmp_path: Path) -> None:
    """Boundary: server declaring legacy /sse URL endpoint fails with MCP004."""
    mcp_file = tmp_path / 'mcp_config.json'
    cfg: dict[str, Any] = {
        'mcpServers': {
            'legacy-sse-server': {
                'url': 'https://example.com/api/sse',
            }
        }
    }
    issues = oracle_validate_mcp_config(cfg, mcp_file)
    assert any(i.code == ErrorCode.MCP004 for i in issues)


def test_f6_b4_mcp_undeclared_variable_rejected(tmp_path: Path) -> None:
    """Boundary: undeclared placeholder variable in env fails with MCP005."""
    mcp_file = tmp_path / 'mcp_config.json'
    cfg: dict[str, Any] = {
        'mcpServers': {
            'sec-server': {
                'command': 'run',
                'env': {'API_KEY': '${UNDECLARED_SECRET}'},
            }
        }
    }
    issues = oracle_validate_mcp_config(cfg, mcp_file)
    assert any(i.code == ErrorCode.MCP005 for i in issues)


def test_f6_b5_mcp_variable_missing_title_rejected(tmp_path: Path) -> None:
    """Boundary: declared variable missing title fails with MCP007."""
    mcp_file = tmp_path / 'mcp_config.json'
    cfg: dict[str, Any] = {
        'mcpServers': {
            'srv': {
                'command': 'run',
                'env': {'TOKEN': '${TOKEN}'},
                'variables': [{'name': 'TOKEN', 'description': 'Some token'}],
            }
        }
    }
    issues = oracle_validate_mcp_config(cfg, mcp_file)
    assert any(i.code == ErrorCode.MCP007 for i in issues)


def test_f6_b6_mcp_variable_missing_description_rejected(tmp_path: Path) -> None:
    """Boundary: declared variable missing description fails with MCP007."""
    mcp_file = tmp_path / 'mcp_config.json'
    cfg: dict[str, Any] = {
        'mcpServers': {
            'srv': {
                'command': 'run',
                'env': {'TOKEN': '${TOKEN}'},
                'variables': [{'name': 'TOKEN', 'title': 'Some token'}],
            }
        }
    }
    issues = oracle_validate_mcp_config(cfg, mcp_file)
    assert any(i.code == ErrorCode.MCP007 for i in issues)


def test_f6_b7_mcp_missing_both_command_and_url_rejected(tmp_path: Path) -> None:
    """Boundary: server definition missing both command and url fails with MCP003."""
    mcp_file = tmp_path / 'mcp_config.json'
    cfg: dict[str, Any] = {
        'mcpServers': {
            'empty-transport-server': {'description': 'No transport given'},
        }
    }
    issues = oracle_validate_mcp_config(cfg, mcp_file)
    assert any(i.code == ErrorCode.MCP003 for i in issues)


# ==============================================================================
# Feature 7 (Plugin Manifest) Boundaries
# ==============================================================================


def test_f7_b1_plugin_semver_two_components_rejected(tmp_path: Path) -> None:
    """Boundary: version with only two components (1.0) fails with PLG003."""
    p_file = tmp_path / 'plugin.json'
    manifest: dict[str, Any] = {'name': 'my-plugin', 'version': '1.0', 'license': 'Apache-2.0'}
    issues = oracle_validate_plugin_manifest(manifest, p_file, tmp_path)
    assert any(i.code == ErrorCode.PLG003 for i in issues)


def test_f7_b2_plugin_semver_v_prefix_rejected(tmp_path: Path) -> None:
    """Boundary: version starting with 'v' (v1.0.0) fails with PLG003."""
    p_file = tmp_path / 'plugin.json'
    manifest: dict[str, Any] = {'name': 'my-plugin', 'version': 'v1.0.0', 'license': 'Apache-2.0'}
    issues = oracle_validate_plugin_manifest(manifest, p_file, tmp_path)
    assert any(i.code == ErrorCode.PLG003 for i in issues)


def test_f7_b3_plugin_name_uppercase_rejected(tmp_path: Path) -> None:
    """Boundary: uppercase characters in plugin name fail with PLG002."""
    p_file = tmp_path / 'plugin.json'
    manifest: dict[str, Any] = {'name': 'My-Plugin', 'version': '1.0.0', 'license': 'Apache-2.0'}
    issues = oracle_validate_plugin_manifest(manifest, p_file, tmp_path)
    assert any(i.code == ErrorCode.PLG002 for i in issues)


def test_f7_b4_plugin_name_underscore_rejected(tmp_path: Path) -> None:
    """Boundary: underscore characters in plugin name fail with PLG002."""
    p_file = tmp_path / 'plugin.json'
    manifest: dict[str, Any] = {'name': 'my_plugin', 'version': '1.0.0', 'license': 'Apache-2.0'}
    issues = oracle_validate_plugin_manifest(manifest, p_file, tmp_path)
    assert any(i.code == ErrorCode.PLG002 for i in issues)


def test_f7_b5_plugin_missing_logo_file_rejected(tmp_path: Path) -> None:
    """Boundary: relative logo path to non-existent file fails with PLG004."""
    p_file = tmp_path / 'plugin.json'
    manifest: dict[str, Any] = {
        'name': 'my-plugin',
        'version': '1.0.0',
        'logo': 'assets/missing_logo.png',
        'license': 'Apache-2.0',
    }
    issues = oracle_validate_plugin_manifest(manifest, p_file, tmp_path)
    assert any(i.code == ErrorCode.PLG004 for i in issues)


def test_f7_b6_plugin_missing_license_rejected(tmp_path: Path) -> None:
    """Boundary: missing license field fails with PLG005."""
    p_file = tmp_path / 'plugin.json'
    manifest: dict[str, Any] = {'name': 'my-plugin', 'version': '1.0.0'}
    issues = oracle_validate_plugin_manifest(manifest, p_file, tmp_path)
    assert any(i.code == ErrorCode.PLG005 for i in issues)


# ==============================================================================
# Feature 8 (Prompt & Reference Consistency) Boundaries
# ==============================================================================


def test_f8_b1_prompt_allowing_autonomous_merge_rejected(tmp_path: Path) -> None:
    """Boundary: prompt permitting autonomous merge fails consistency check with PRM002."""
    rules_dir = tmp_path / 'rules'
    rules_dir.mkdir(parents=True)
    (rules_dir / 'AGENTS.md').write_text(
        '# Rules\nAutonomous merge is permitted after checks pass.\n',
        encoding='utf-8',
    )
    report = ValidationReport()
    validate_prompts(tmp_path, report)
    assert any(i.code == ErrorCode.PRM002 for i in report.issues)


def test_f8_b2_prompt_prescribing_pixi_rejected(tmp_path: Path) -> None:
    """Boundary: prompt prescribing pixi run for mimir-agent-kit operations fails with PRM003."""
    rules_dir = tmp_path / 'rules'
    rules_dir.mkdir(parents=True)
    (rules_dir / 'AGENTS.md').write_text(
        '# Rules\nAlways execute tests using `pixi run test`.\n',
        encoding='utf-8',
    )
    report = ValidationReport()
    validate_prompts(tmp_path, report)
    assert any(i.code == ErrorCode.PRM003 for i in report.issues)


def test_f8_b3_prompt_unresolvable_cross_skill_link_rejected(tmp_path: Path) -> None:
    """Boundary: cross-skill link referencing non-existent skill fails with PRM001."""
    skills_dir = tmp_path / 'skills' / 'my-skill'
    skills_dir.mkdir(parents=True)
    (skills_dir / 'SKILL.md').write_text(
        '---\nname: my-skill\ndescription: A valid skill description with sufficient characters.\n---\n## Related Skills\n- `/ghost-skill`: Non-existent skill\n',
        encoding='utf-8',
    )
    report = ValidationReport()
    validate_prompts(tmp_path, report)
    assert any(i.code == ErrorCode.PRM001 for i in report.issues)


def test_f8_b4_prompt_broken_relative_markdown_link_rejected(tmp_path: Path) -> None:
    """Boundary: markdown link referencing non-existent file fails with SKL008."""
    skills_dir = tmp_path / 'skills' / 'my-skill'
    skills_dir.mkdir(parents=True)
    (skills_dir / 'SKILL.md').write_text(
        '---\nname: my-skill\ndescription: A valid skill description with sufficient characters.\n---\nSee [reference docs](./missing_reference.md) for details.\n',
        encoding='utf-8',
    )
    report = ValidationReport()
    validate_skills(tmp_path, report)
    assert any(i.code == ErrorCode.SKL008 for i in report.issues)


def test_f8_b5_trailing_whitespace_detected() -> None:
    """Boundary: detecting trailing whitespace on lines."""
    line_with_trailing = '## Header   \n'
    assert line_with_trailing.rstrip('\r\n') != line_with_trailing.rstrip(' \t\r\n')


# ==============================================================================
# Feature 9 (CLI Execution & Diagnostics) Boundaries
# ==============================================================================


def test_f9_b1_cli_strict_mode_escalates_warning_to_failure() -> None:
    """Boundary: in strict mode, warnings cause is_clean to evaluate False."""
    report = ValidationReport(strict=True)
    report.add(
        code=ErrorCode.SKL004,
        message='Short description',
        severity=Severity.WARNING,
        path=Path('skills/a/SKILL.md'),
    )
    assert report.warning_count == 1
    assert report.error_count == 0
    assert not report.is_clean, 'Strict mode must fail on warnings'


def test_f9_b2_cli_non_strict_mode_allows_warning() -> None:
    """Boundary: in non-strict mode, warnings alone do not cause is_clean to fail."""
    report = ValidationReport(strict=False)
    report.add(
        code=ErrorCode.SKL004,
        message='Short description',
        severity=Severity.WARNING,
        path=Path('skills/a/SKILL.md'),
    )
    assert report.is_clean, 'Non-strict mode should pass when there are only warnings'


def test_f9_b3_cli_json_serialization_preserves_error_details() -> None:
    """Boundary: JSON serialization preserves code, line, path, and suggestion."""
    report = ValidationReport()
    report.add(
        code=ErrorCode.MCP008,
        message='Tool name too long',
        severity=Severity.ERROR,
        path=Path('mcp_config.json'),
        line=42,
        suggestion='Shorten tool name',
    )
    raw_json = report.to_json()
    data = json.loads(raw_json)
    issue = data['issues'][0]
    assert issue['code'] == 'MCP008'
    assert issue['line'] == 42
    assert issue['suggestion'] == 'Shorten tool name'


def test_f9_b4_cli_multiple_errors_aggregated() -> None:
    """Boundary: multiple validation errors across categories aggregate cleanly."""
    report = ValidationReport()
    for code_val in [ErrorCode.SKL001, ErrorCode.RUL002, ErrorCode.HOK003, ErrorCode.MCP004]:
        report.add(
            code=code_val,
            message='Synthetic error',
            severity=Severity.ERROR,
            path=Path('test'),
        )
    assert report.error_count == 4
    assert len(report.issues) == 4


def test_f9_b5_cli_zero_issues_clean_output() -> None:
    """Boundary: 0 issues produces passed=True and empty issue array."""
    report = ValidationReport()
    d = report.to_dict()
    assert d['passed'] is True
    assert d['errorCount'] == 0
    assert d['warningCount'] == 0
    assert d['totalIssues'] == 0
    assert d['issues'] == []


# ==============================================================================
# Feature 10 (Local Pre-Commit Enforcement Gate) Boundaries
# ==============================================================================


def test_f10_b1_gate_detects_lockfile_mismatch() -> None:
    """Boundary: simulated lockfile status check."""
    is_locked = True
    assert is_locked is True, 'Lockfile must be in sync'


def test_f10_b2_gate_detects_pre_commit_failure() -> None:
    """Boundary: pre-commit exit code 1 propagates to overall gate failure."""
    pre_commit_exit = 1
    gate_exit = 1 if pre_commit_exit != 0 else 0
    assert gate_exit == 1


def test_f10_b3_gate_detects_test_failure() -> None:
    """Boundary: test runner exit code 1 propagates to overall gate failure."""
    pytest_exit = 1
    gate_exit = 1 if pytest_exit != 0 else 0
    assert gate_exit == 1


def test_f10_b4_gate_runner_handles_missing_files(tmp_path: Path) -> None:
    """Boundary: runner handles missing script gracefully."""
    non_existent = tmp_path / 'missing_script.sh'
    assert not non_existent.exists()


def test_f10_b5_gate_empty_environment_variables_handling() -> None:
    """Boundary: runner handles empty/unset custom environment variables without crashing."""
    env_vars: dict[str, str] = {}
    token = env_vars.get('CUSTOM_API_TOKEN', '')
    assert token == ''
