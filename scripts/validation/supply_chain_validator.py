"""Supply-chain security & immutable SHA-pinning validator for CI, pre-commit, and Renovate/Dependabot."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING
from typing import Any

import yaml

from scripts.validation.codes import ErrorCode
from scripts.validation.models import Severity


if TYPE_CHECKING:
    from pathlib import Path

    from scripts.validation.models import ValidationReport


FULL_COMMIT_SHA_PATTERN = re.compile(r'^[0-9a-f]{40}$')
DOCKER_ACTION_DIGEST_PATTERN = re.compile(r'^docker://[a-z0-9._/-]+(?::[A-Za-z0-9._-]+)?@sha256:[0-9a-f]{64}$')
USES_LINE_PATTERN = re.compile(
    r'^\s*(?:-\s*)?uses:\s*(?P<target>[^\s#]+)(?:\s+#\s*(?P<comment>\S.*))?\s*$',
)
VERSION_COMMENT_PATTERN = re.compile(r'^v?\d+(?:\.\d+)*')


def strip_jsonc_comments(raw_text: str) -> str:
    """Strip // line comments and /* ... */ block comments outside JSON string literals.

    Args:
        raw_text: Raw UTF-8 JSONC document contents.

    Returns:
        Comment-free JSON text suitable for json.loads().
    """
    out: list[str] = []
    in_string = False
    escaped = False
    idx = 0
    length = len(raw_text)

    while idx < length:
        ch = raw_text[idx]
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == '"':
                in_string = False
            idx += 1
            continue

        if ch == '"':
            in_string = True
            out.append(ch)
            idx += 1
            continue

        if ch == '/' and idx + 1 < length:
            nxt = raw_text[idx + 1]
            if nxt == '/':
                idx += 2
                while idx < length and raw_text[idx] != '\n':
                    idx += 1
                continue
            if nxt == '*':
                idx += 2
                while idx + 1 < length and not (raw_text[idx] == '*' and raw_text[idx + 1] == '/'):
                    if raw_text[idx] == '\n':
                        out.append('\n')
                    idx += 1
                idx += 2
                continue

        out.append(ch)
        idx += 1

    return ''.join(out)


def validate_workflow_file(workflow_file: Path, report: ValidationReport) -> None:
    """Validate SHA-pinning, version comments, permissions, and checkout credentials in a workflow.

    Args:
        workflow_file: Path to a GitHub Actions workflow YAML file.
        report: Aggregating ValidationReport.
    """
    try:
        content = workflow_file.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as exc:
        report.add(
            code=ErrorCode.SUP001,
            message=f'Failed to read workflow file {workflow_file.name}: {exc}',
            severity=Severity.ERROR,
            path=workflow_file,
        )
        return

    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        report.add(
            code=ErrorCode.SUP001,
            message=f'Malformed YAML in workflow {workflow_file.name}: {exc}',
            severity=Severity.ERROR,
            path=workflow_file,
        )
        return

    if not isinstance(data, dict):
        report.add(
            code=ErrorCode.SUP001,
            message=f'Workflow {workflow_file.name} must parse to a YAML mapping.',
            severity=Severity.ERROR,
            path=workflow_file,
        )
        return

    # 1. Inspect raw lines for external `uses:` SHA pinning and version comment hygiene (SUP001)
    for lineno, line in enumerate(content.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith('#'):
            continue
        match = USES_LINE_PATTERN.match(line)
        if not match:
            continue

        raw_target = match.group('target').strip('\'"')
        comment = (match.group('comment') or '').strip()

        if raw_target.startswith('./'):
            continue

        if raw_target.startswith('docker://'):
            if not DOCKER_ACTION_DIGEST_PATTERN.match(raw_target):
                report.add(
                    code=ErrorCode.SUP001,
                    message=f"Docker action '{raw_target}' in {workflow_file.name} is not pinned to '@sha256:<64-hex>'.",
                    severity=Severity.ERROR,
                    path=workflow_file,
                    line=lineno,
                    suggestion='Pin docker:// action references with an immutable @sha256:<64-hex> digest.',
                )
            continue

        if '@' not in raw_target:
            report.add(
                code=ErrorCode.SUP001,
                message=f"External action '{raw_target}' in {workflow_file.name} is missing '@<40-char-commit-sha>'.",
                severity=Severity.ERROR,
                path=workflow_file,
                line=lineno,
                suggestion='Pin external GitHub Actions to a full 40-character commit SHA with a # vX.Y.Z comment.',
            )
            continue

        action_slug, ref = raw_target.rsplit('@', 1)
        if not FULL_COMMIT_SHA_PATTERN.match(ref):
            report.add(
                code=ErrorCode.SUP001,
                message=(f"External action '{action_slug}@{ref}' in {workflow_file.name} uses mutable ref '{ref}' instead of a 40-character commit SHA."),
                severity=Severity.ERROR,
                path=workflow_file,
                line=lineno,
                suggestion=f"Resolve '{action_slug}@{ref}' to its immutable 40-char commit SHA and append '# {ref}'.",
            )
        elif not comment or not VERSION_COMMENT_PATTERN.match(comment):
            report.add(
                code=ErrorCode.SUP001,
                message=(f"SHA-pinned action '{action_slug}@{ref[:12]}...' in {workflow_file.name} is missing a trailing '# vX.Y.Z' version comment."),
                severity=Severity.ERROR,
                path=workflow_file,
                line=lineno,
                suggestion="Append a trailing SemVer comment such as '# v7.0.1' so Renovate/humans can audit the version.",
            )

    # 2. Verify explicit least-privilege permissions and checkout persist-credentials: false (SUP002)
    has_top_permissions = 'permissions' in data and data['permissions'] is not None
    jobs = data.get('jobs', {})
    if not isinstance(jobs, dict):
        return

    all_jobs_have_permissions = bool(jobs) and all(isinstance(j, dict) and 'permissions' in j and j['permissions'] is not None for j in jobs.values())
    if not has_top_permissions and not all_jobs_have_permissions:
        report.add(
            code=ErrorCode.SUP002,
            message=f"Workflow '{workflow_file.name}' lacks explicit top-level or per-job 'permissions' block.",
            severity=Severity.ERROR,
            path=workflow_file,
            suggestion="Declare explicit least-privilege 'permissions: { contents: read }' at workflow or job scope.",
        )

    for job_id, job_cfg in jobs.items():
        if not isinstance(job_cfg, dict):
            continue
        steps = job_cfg.get('steps', [])
        if not isinstance(steps, list):
            continue
        for step in steps:
            if not isinstance(step, dict):
                continue
            uses_val = step.get('uses')
            if isinstance(uses_val, str) and uses_val.startswith('actions/checkout@'):
                with_cfg = step.get('with')
                persist_val = with_cfg.get('persist-credentials') if isinstance(with_cfg, dict) else None
                if persist_val is not False:
                    report.add(
                        code=ErrorCode.SUP002,
                        message=(f"Step in job '{job_id}' ({workflow_file.name}) uses '{uses_val.split('@', 1)[0]}' without 'persist-credentials: false'."),
                        severity=Severity.ERROR,
                        path=workflow_file,
                        suggestion="Add 'with: { persist-credentials: false }' to every actions/checkout step.",
                    )


def validate_pre_commit_file(pre_commit_file: Path, report: ValidationReport) -> None:
    """Validate that external pre-commit hook repositories pin rev to a 40-char commit SHA.

    Args:
        pre_commit_file: Path to .pre-commit-config.yaml.
        report: Aggregating ValidationReport.
    """
    try:
        content = pre_commit_file.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as exc:
        report.add(
            code=ErrorCode.SUP003,
            message=f'Failed to read {pre_commit_file.name}: {exc}',
            severity=Severity.ERROR,
            path=pre_commit_file,
        )
        return

    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        report.add(
            code=ErrorCode.SUP003,
            message=f'Malformed YAML in {pre_commit_file.name}: {exc}',
            severity=Severity.ERROR,
            path=pre_commit_file,
        )
        return

    if not isinstance(data, dict):
        report.add(
            code=ErrorCode.SUP003,
            message=f'{pre_commit_file.name} must parse to a YAML mapping.',
            severity=Severity.ERROR,
            path=pre_commit_file,
        )
        return

    repos = data.get('repos', [])
    if not isinstance(repos, list):
        report.add(
            code=ErrorCode.SUP003,
            message=f"'{pre_commit_file.name}' 'repos' field must be a list.",
            severity=Severity.ERROR,
            path=pre_commit_file,
        )
        return

    for repo_entry in repos:
        if not isinstance(repo_entry, dict):
            continue
        repo_url = str(repo_entry.get('repo', '')).strip()
        if not repo_url or repo_url in {'local', 'meta'}:
            continue
        rev = str(repo_entry.get('rev', '')).strip()
        if not FULL_COMMIT_SHA_PATTERN.match(rev):
            report.add(
                code=ErrorCode.SUP003,
                message=(f"Pre-commit external repository '{repo_url}' uses mutable rev '{rev or '<missing>'}' instead of a 40-char commit SHA."),
                severity=Severity.ERROR,
                path=pre_commit_file,
                suggestion="Run 'uv run pre-commit autoupdate --freeze' to pin external repos to full 40-char commit SHAs.",
            )


def validate_renovate_file(renovate_file: Path, report: ValidationReport) -> None:
    """Validate renovate.jsonc syntax and SHA-digest pinning rules.

    Args:
        renovate_file: Path to renovate.jsonc.
        report: Aggregating ValidationReport.
    """
    try:
        raw_text = renovate_file.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as exc:
        report.add(
            code=ErrorCode.SUP004,
            message=f'Failed to read {renovate_file.name}: {exc}',
            severity=Severity.ERROR,
            path=renovate_file,
        )
        return

    try:
        data: Any = json.loads(strip_jsonc_comments(raw_text))
    except json.JSONDecodeError as exc:
        report.add(
            code=ErrorCode.SUP004,
            message=f'Malformed JSONC in {renovate_file.name}: {exc}',
            severity=Severity.ERROR,
            path=renovate_file,
            line=exc.lineno,
        )
        return

    if not isinstance(data, dict):
        report.add(
            code=ErrorCode.SUP004,
            message=f'Root of {renovate_file.name} must be a JSON object.',
            severity=Severity.ERROR,
            path=renovate_file,
        )
        return

    extends = data.get('extends', [])
    if not isinstance(extends, list) or 'helpers:pinGitHubActionDigestsToSemver' not in extends:
        report.add(
            code=ErrorCode.SUP004,
            message=(f"{renovate_file.name} must extend 'helpers:pinGitHubActionDigestsToSemver' to maintain SHA-pinned GitHub Actions."),
            severity=Severity.ERROR,
            path=renovate_file,
            suggestion="Add 'helpers:pinGitHubActionDigestsToSemver' to the 'extends' array in renovate.jsonc.",
        )

    pre_commit_cfg = data.get('pre-commit')
    if not isinstance(pre_commit_cfg, dict) or pre_commit_cfg.get('enabled') is not True:
        report.add(
            code=ErrorCode.SUP004,
            message=f'{renovate_file.name} must enable the \'pre-commit\' manager (\'"pre-commit": {{"enabled": true}}\').',
            severity=Severity.ERROR,
            path=renovate_file,
            suggestion='Enable Renovate pre-commit hook digest updates in renovate.jsonc.',
        )


def validate_dependabot_file(dependabot_file: Path, report: ValidationReport) -> None:
    """Validate .github/dependabot.yml syntax and ecosystem coverage.

    Args:
        dependabot_file: Path to .github/dependabot.yml.
        report: Aggregating ValidationReport.
    """
    try:
        content = dependabot_file.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as exc:
        report.add(
            code=ErrorCode.SUP004,
            message=f'Failed to read {dependabot_file.name}: {exc}',
            severity=Severity.ERROR,
            path=dependabot_file,
        )
        return

    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        report.add(
            code=ErrorCode.SUP004,
            message=f'Malformed YAML in {dependabot_file.name}: {exc}',
            severity=Severity.ERROR,
            path=dependabot_file,
        )
        return

    if not isinstance(data, dict) or data.get('version') != 2 or not isinstance(data.get('updates'), list):
        report.add(
            code=ErrorCode.SUP004,
            message=f"{dependabot_file.name} must declare 'version: 2' and a valid 'updates' list.",
            severity=Severity.ERROR,
            path=dependabot_file,
        )
        return

    ecosystems = {str(entry.get('package-ecosystem', '')) for entry in data['updates'] if isinstance(entry, dict)}
    if 'github-actions' not in ecosystems:
        report.add(
            code=ErrorCode.SUP004,
            message=f"{dependabot_file.name} is missing the 'github-actions' package-ecosystem.",
            severity=Severity.ERROR,
            path=dependabot_file,
            suggestion="Configure package-ecosystem: 'github-actions' in .github/dependabot.yml.",
        )


def validate_supply_chain(repo_root: Path, report: ValidationReport) -> None:
    """Validate supply-chain pinning across workflows, pre-commit, Renovate, and Dependabot.

    Args:
        repo_root: Root directory of repository.
        report: Aggregating ValidationReport.
    """
    workflows_dir = repo_root / '.github' / 'workflows'
    if workflows_dir.is_dir():
        workflow_files = sorted(p for p in workflows_dir.iterdir() if p.is_file() and p.suffix in {'.yml', '.yaml'})
        for wf_file in workflow_files:
            validate_workflow_file(wf_file, report)

    pre_commit_file = repo_root / '.pre-commit-config.yaml'
    if pre_commit_file.is_file():
        validate_pre_commit_file(pre_commit_file, report)

    renovate_file = repo_root / 'renovate.jsonc'
    if renovate_file.is_file():
        validate_renovate_file(renovate_file, report)

    dependabot_file = repo_root / '.github' / 'dependabot.yml'
    if dependabot_file.is_file():
        validate_dependabot_file(dependabot_file, report)
