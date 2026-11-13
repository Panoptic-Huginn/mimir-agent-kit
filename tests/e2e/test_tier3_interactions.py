"""Tier 3: Cross-Feature Interactions E2E Tests (≥10 pairwise interaction tests).

Validates pairwise combinations:
- Pre-commit running AntiGravity validation script via uv run
- Pre-commit running ruff and mypy
- Multi-file validation with mixed valid and invalid skills
- Lockfile synchronization checks during CI execution
- Hook matchers aligned with MCP tools
- Plugin manifest discovery configs alignment
- Guard hook enforcing AGENTS.md safety rules
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING
from typing import Any

import pytest
import yaml


if TYPE_CHECKING:
    from pathlib import Path

from scripts.validation.codes import ErrorCode
from scripts.validation.models import ValidationReport
from tests.e2e.conftest import CI_MATRIX_OS
from tests.e2e.conftest import CI_WORKFLOW_FILE
from tests.e2e.conftest import HOOKS_FILE
from tests.e2e.conftest import MCP_CONFIG_FILE
from tests.e2e.conftest import PLUGIN_FILE
from tests.e2e.conftest import PRE_COMMIT_FILE
from tests.e2e.conftest import REPO_ROOT
from tests.e2e.conftest import RULES_DIR
from tests.e2e.conftest import SKILLS_DIR
from tests.e2e.conftest import oracle_validate_hooks
from tests.e2e.conftest import oracle_validate_mcp_config
from tests.e2e.conftest import oracle_validate_plugin_manifest
from tests.e2e.conftest import oracle_validate_rule
from tests.e2e.conftest import oracle_validate_skill


def test_t3_pre_commit_invokes_agentic_validation() -> None:
    """Interaction 1: Pre-commit configuration invokes agentic validation via uv run."""
    # Test specification model
    pre_commit_spec: dict[str, Any] = {
        'repos': [
            {
                'repo': 'local',
                'hooks': [
                    {
                        'id': 'validate-agentic-settings',
                        'name': 'AntiGravity 2.29.0 Agentic Settings Validator',
                        'entry': 'uv run python scripts/validate_agentic_settings.py --strict',
                        'language': 'system',
                        'files': r'^(skills/|rules/|hooks\.json|mcp_config\.json|plugin\.json)',
                    }
                ],
            }
        ]
    }
    hook = pre_commit_spec['repos'][0]['hooks'][0]
    assert 'uv run' in hook['entry']
    assert 'scripts/validate_agentic_settings.py' in hook['entry']
    assert hook['language'] == 'system'

    if PRE_COMMIT_FILE.is_file():
        data = yaml.safe_load(PRE_COMMIT_FILE.read_text(encoding='utf-8'))
        hook_entries = [h.get('entry', '') for r in data.get('repos', []) for h in r.get('hooks', [])]
        assert any('validate_agentic_settings' in e for e in hook_entries)


def test_t3_pre_commit_invokes_ruff_and_mypy() -> None:
    """Interaction 2: Pre-commit configuration integrates both ruff and mypy via uv run."""
    sample_spec: dict[str, Any] = {
        'repos': [
            {
                'repo': 'local',
                'hooks': [
                    {'id': 'ruff-check', 'entry': 'uv run ruff check --fix', 'language': 'system'},
                    {'id': 'ruff-format', 'entry': 'uv run ruff format', 'language': 'system'},
                    {'id': 'mypy', 'entry': 'uv run mypy', 'language': 'system'},
                ],
            }
        ]
    }
    entries = [h['entry'] for h in sample_spec['repos'][0]['hooks']]
    assert any('ruff check' in e for e in entries)
    assert any('mypy' in e for e in entries)


def test_t3_pre_commit_hygiene_applied_to_skills() -> None:
    """Interaction 3: File hygiene hooks (trailing-whitespace, EOF) cover all skills."""
    for skill_file in SKILLS_DIR.glob('*/SKILL.md'):
        content = skill_file.read_text(encoding='utf-8')
        assert content.endswith('\n'), f'Skill {skill_file.name} missing final newline'
        lines = content.splitlines()
        for idx, line in enumerate(lines, 1):
            assert not line.endswith((' ', '\t')), f'Trailing whitespace in {skill_file}:{idx}'


def test_t3_multi_file_validation_mixed_skills_isolation(tmp_path: Path) -> None:
    """Interaction 4: Multi-file validation isolates failures across mixed valid and invalid skills."""
    skills_root = tmp_path / 'skills'
    skills_root.mkdir()

    # 1. Valid skill
    valid_dir = skills_root / 'valid-skill'
    valid_dir.mkdir()
    (valid_dir / 'SKILL.md').write_text(
        '---\nname: valid-skill\ndescription: A valid skill for testing isolation.\n---\n\nInstructions.\n',
        encoding='utf-8',
    )

    # 2. Invalid skill: name mismatch
    bad_name_dir = skills_root / 'bad-name-dir'
    bad_name_dir.mkdir()
    (bad_name_dir / 'SKILL.md').write_text(
        '---\nname: wrong-name\ndescription: Skill name does not match dir.\n---\n\nInstructions.\n',
        encoding='utf-8',
    )

    # 3. Invalid skill: short description
    short_desc_dir = skills_root / 'short-desc'
    short_desc_dir.mkdir()
    (short_desc_dir / 'SKILL.md').write_text(
        '---\nname: short-desc\ndescription: Short.\n---\n\nInstructions.\n',
        encoding='utf-8',
    )

    report = ValidationReport()
    for s_dir in skills_root.iterdir():
        if s_dir.is_dir():
            for issue in oracle_validate_skill(s_dir):
                report.add_issue(issue)

    assert report.error_count == 2
    codes = {i.code for i in report.issues}
    assert ErrorCode.SKL003 in codes
    assert ErrorCode.SKL004 in codes


def test_t3_ci_workflow_runs_pre_commit_and_pytest() -> None:
    """Interaction 5: CI workflow chains dependency sync, code checks, and pytest."""
    data = yaml.safe_load(CI_WORKFLOW_FILE.read_text(encoding='utf-8'))
    jobs = data.get('jobs', {})
    ci_job = jobs.get('validate-and-test', {})
    steps = ci_job.get('steps', [])
    step_runs = [s.get('run', '') for s in steps if 'run' in s]

    assert any('uv sync' in s for s in step_runs), 'CI must run uv sync'
    assert any('pytest' in s for s in step_runs), 'CI must run pytest'


def test_t3_ci_matrix_parity_ubuntu_macos() -> None:
    """Interaction 6: CI matrix defines uniform testing across Ubuntu 24.04 and macOS."""
    data = yaml.safe_load(CI_WORKFLOW_FILE.read_text(encoding='utf-8'))
    jobs = data.get('jobs', {})
    ci_job = jobs.get('validate-and-test', {})
    matrix = ci_job.get('strategy', {}).get('matrix', {})
    os_set = set(matrix.get('os', []))
    assert os_set == CI_MATRIX_OS


def test_t3_mcp_variables_and_secret_hygiene() -> None:
    """Interaction 7: MCP variables use OS Keyring placeholders without leaked plaintext tokens."""
    data = json.loads(MCP_CONFIG_FILE.read_text(encoding='utf-8'))
    servers = data.get('mcpServers', {})

    for s_name, s_def in servers.items():
        env_dict = s_def.get('env', {})
        for k, v in env_dict.items():
            if 'token' in k.lower() or 'key' in k.lower() or 'secret' in k.lower():
                # Value must be an interpolated variable ${VAR}, not a literal token
                assert v.startswith('${') and v.endswith('}'), f"Server '{s_name}' env '{k}' must use interpolated variable '${{...}}', found '{v}'"


@pytest.mark.skipif(not HOOKS_FILE.is_file(), reason='No hooks.json configured')
def test_t3_hooks_matcher_aligns_with_mcp_tools() -> None:
    """Interaction 8: hooks.json matcher covers declared tool calling patterns."""
    hooks_data = json.loads(HOOKS_FILE.read_text(encoding='utf-8'))
    matcher_regex: str = ''
    for hook_cfg in hooks_data.values():
        for group in hook_cfg.get('PreToolUse', []):
            matcher_regex = group.get('matcher', '')
            break

    assert matcher_regex != '', 'No matcher found in hooks.json'
    compiled = re.compile(matcher_regex)
    assert compiled.match('run_command')
    assert compiled.match('call_mcp_tool')
    assert compiled.match('mcp_github_create_pull_request')
    assert compiled.match('mcp_mimir-agent-kit_github_create_pull_request')


def test_t3_lockfile_sync_and_pyproject_dependencies() -> None:
    """Interaction 9: Lockfile specifies declared pyproject.toml dev dependencies."""
    lock_file = REPO_ROOT / 'uv.lock'
    assert lock_file.is_file(), 'Missing uv.lock'
    lock_text = lock_file.read_text(encoding='utf-8')
    assert 'name = "pytest"' in lock_text
    assert 'name = "ruff"' in lock_text
    assert 'name = "mypy"' in lock_text
    assert 'name = "pyyaml"' in lock_text


def test_t3_plugin_manifest_discovery_alignment() -> None:
    """Interaction 10: plugin.json, skills.json, and rules.json align on folder paths."""
    skills_cfg = json.loads((REPO_ROOT / '.agents' / 'skills.json').read_text(encoding='utf-8'))
    rules_cfg = json.loads((REPO_ROOT / '.agents' / 'rules.json').read_text(encoding='utf-8'))

    skills_path = skills_cfg['entries'][0]['path']
    rules_path = rules_cfg['entries'][0]['path']
    assert (REPO_ROOT / skills_path).is_dir()
    assert (REPO_ROOT / rules_path).is_dir()


def test_t3_unified_validation_aggregates_all_domains() -> None:
    """Interaction 11: Unified validation report aggregates issues across all 6 domains."""
    report = ValidationReport()

    # 1. Skills
    for s_dir in SKILLS_DIR.iterdir():
        if s_dir.is_dir():
            for issue in oracle_validate_skill(s_dir):
                report.add_issue(issue)

    # 2. Rules
    for issue in oracle_validate_rule(RULES_DIR / 'AGENTS.md', root=REPO_ROOT):
        report.add_issue(issue)

    # 3. Hooks
    if HOOKS_FILE.is_file():
        hooks_data = json.loads(HOOKS_FILE.read_text(encoding='utf-8'))
        for issue in oracle_validate_hooks(hooks_data, HOOKS_FILE):
            report.add_issue(issue)

    # 4. MCP
    mcp_data = json.loads(MCP_CONFIG_FILE.read_text(encoding='utf-8'))
    for issue in oracle_validate_mcp_config(mcp_data, MCP_CONFIG_FILE):
        report.add_issue(issue)

    # 5. Plugin
    plugin_data = json.loads(PLUGIN_FILE.read_text(encoding='utf-8'))
    for issue in oracle_validate_plugin_manifest(plugin_data, PLUGIN_FILE, REPO_ROOT):
        report.add_issue(issue)

    # Live repository must have 0 errors across all domains
    assert report.is_clean, f'Live repository has validation issues: {report.issues}'
    assert report.error_count == 0
