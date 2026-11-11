"""Tier 4: Real-World Application Scenarios E2E Tests (≥5 comprehensive workload tests).

Validates end-to-end operational workflows:
- Clean repository checkout full verification
- Rejection of oversized skill injection with actionable diagnostic remediation
- Rejection of 65-character MCP tool injection per AntiGravity 2.29.0 protobuf spec
- Rejection of broken rule trigger and YAML frontmatter injection
- Full simulated CI pipeline execution across all stages
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import TYPE_CHECKING
from typing import Any

import yaml


if TYPE_CHECKING:
    from pathlib import Path

from scripts.validation.codes import ErrorCode
from scripts.validation.models import Severity
from scripts.validation.models import ValidationReport
from tests.e2e.conftest import CI_WORKFLOW_FILE
from tests.e2e.conftest import HOOKS_FILE
from tests.e2e.conftest import MCP_CONFIG_FILE
from tests.e2e.conftest import PLUGIN_FILE
from tests.e2e.conftest import REPO_ROOT
from tests.e2e.conftest import RULES_DIR
from tests.e2e.conftest import SKILLS_DIR
from tests.e2e.conftest import oracle_validate_ci_workflow
from tests.e2e.conftest import oracle_validate_hooks
from tests.e2e.conftest import oracle_validate_mcp_config
from tests.e2e.conftest import oracle_validate_plugin_manifest
from tests.e2e.conftest import oracle_validate_rule
from tests.e2e.conftest import oracle_validate_skill


def test_t4_clean_repo_checkout_full_verification() -> None:
    """Scenario 1: Clean repository checkout full audit across all 10 features."""
    report = ValidationReport(strict=True)

    # 1. Audit skills
    for s_dir in SKILLS_DIR.iterdir():
        if s_dir.is_dir():
            for issue in oracle_validate_skill(s_dir):
                report.add_issue(issue)

    # 2. Audit rules
    for issue in oracle_validate_rule(RULES_DIR / 'AGENTS.md', root=REPO_ROOT):
        report.add_issue(issue)

    # 3. Audit hooks
    if HOOKS_FILE.is_file():
        hooks_data = json.loads(HOOKS_FILE.read_text(encoding='utf-8'))
        for issue in oracle_validate_hooks(hooks_data, HOOKS_FILE):
            report.add_issue(issue)

    # 4. Audit MCP config
    mcp_data = json.loads(MCP_CONFIG_FILE.read_text(encoding='utf-8'))
    for issue in oracle_validate_mcp_config(mcp_data, MCP_CONFIG_FILE):
        report.add_issue(issue)

    # 5. Audit plugin manifest
    plugin_data = json.loads(PLUGIN_FILE.read_text(encoding='utf-8'))
    for issue in oracle_validate_plugin_manifest(plugin_data, PLUGIN_FILE, REPO_ROOT):
        report.add_issue(issue)

    # 6. Audit CI workflow
    ci_data = yaml.safe_load(CI_WORKFLOW_FILE.read_text(encoding='utf-8'))
    for issue in oracle_validate_ci_workflow(ci_data, CI_WORKFLOW_FILE):
        report.add_issue(issue)

    assert report.is_clean, f'Clean repo audit failed: {report.to_json()}'
    assert report.error_count == 0
    assert report.warning_count == 0


def test_t4_oversized_skill_injection_rejection(tmp_path: Path) -> None:
    """Scenario 2: Rejection of oversized skill (>24,000 bytes) with actionable remediation."""
    target_skill_dir = tmp_path / 'skills' / 'oversized-skill'
    target_skill_dir.mkdir(parents=True)

    # Inject an oversized skill body (25,000 bytes)
    header = '---\nname: oversized-skill\ndescription: A comprehensive guide exceeding size limit.\n---\n\n# Overview\n'
    oversized_body = 'Important documentation line.\n' * 850
    assert len(oversized_body.encode('utf-8')) > 24_000

    (target_skill_dir / 'SKILL.md').write_text(header + oversized_body, encoding='utf-8')

    issues = oracle_validate_skill(target_skill_dir)
    oversized_issues = [i for i in issues if i.code == ErrorCode.SKL005]
    assert len(oversized_issues) == 1
    issue = oversized_issues[0]
    assert issue.severity == Severity.ERROR
    assert 'exceeds limit of 24000 bytes' in issue.message


def test_t4_oversized_mcp_tool_injection_rejection(tmp_path: Path) -> None:
    """Scenario 3: Rejection of 65-char MCP tool injection per AntiGravity 2.29.0 spec."""
    mcp_path = tmp_path / 'mcp_config.json'
    # 'mcp_' (4) + 'github-mcp-server_' (18) + 'manage_repository_notification_subscription' (43) = 65 chars
    server_name = 'github-mcp-server'
    tool_name = 'manage_repository_notification_subscription'
    full_tool_identifier = f'mcp_{server_name}_{tool_name}'
    assert len(full_tool_identifier) == 65

    mcp_cfg: dict[str, Any] = {
        'mcpServers': {
            server_name: {
                'command': 'docker',
                'args': ['run', 'ghcr.io/github/github-mcp-server'],
                'tools': [{'name': tool_name}],
            }
        }
    }
    mcp_path.write_text(json.dumps(mcp_cfg, indent=2), encoding='utf-8')

    issues = oracle_validate_mcp_config(mcp_cfg, mcp_path)
    tool_issues = [i for i in issues if i.code == ErrorCode.MCP008]
    assert len(tool_issues) == 1
    issue = tool_issues[0]
    assert issue.severity == Severity.ERROR
    assert '64' in issue.message


def test_t4_corrupt_rule_trigger_injection_rejection(tmp_path: Path) -> None:
    """Scenario 4: Rejection of rule with disallowed YAML frontmatter."""
    rules_dir = tmp_path / 'rules'
    rules_dir.mkdir()
    corrupt_rule = rules_dir / 'AGENTS.md'
    corrupt_rule.write_text(
        '---\ntrigger: ALWAYS_ON\n---\n# Corrupted Rule\nDisallowed YAML frontmatter in standalone rule.\n',
        encoding='utf-8',
    )

    issues = oracle_validate_rule(corrupt_rule, root=tmp_path)
    frontmatter_issues = [i for i in issues if i.code == ErrorCode.RUL002]
    assert len(frontmatter_issues) == 1
    assert frontmatter_issues[0].severity == Severity.ERROR


def test_t4_full_simulated_ci_pipeline_execution() -> None:
    """Scenario 5: Full simulated CI pipeline execution across all verification gates."""
    uv_bin = shutil.which('uv')
    assert uv_bin is not None, 'uv executable not found in PATH'

    pipeline_stages: list[tuple[str, list[str]]] = [
        ('1. Lockfile synchronization check', [uv_bin, 'lock', '--check']),
        ('2. Ruff linter check', [uv_bin, 'run', 'ruff', 'check', '.']),
        ('3. Ruff format check', [uv_bin, 'run', 'ruff', 'format', '--check', '.']),
        ('4. Strict Mypy type check', [uv_bin, 'run', 'mypy']),
    ]

    for stage_name, cmd in pipeline_stages:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            check=False,
        )
        assert res.returncode == 0, f'Pipeline stage {stage_name} failed: {res.stderr}\n{res.stdout}'

    # Stage 5: Comprehensive unit test suite execution
    pytest_bin = shutil.which('pytest')
    assert pytest_bin is not None, 'pytest executable not found in PATH'
    test_res = subprocess.run(
        [
            pytest_bin,
            'tests/test_plugin_integrity.py',
            'tests/test_academic_mcp_server.py',
            '-v',
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
    )
    assert test_res.returncode == 0, f'Unit test execution failed: {test_res.stderr}\n{test_res.stdout}'
