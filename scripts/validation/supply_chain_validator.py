"""Supply-chain security & immutable SHA-pinning validator for CI, pre-commit, and Renovate/Dependabot."""

import json
import re
from typing import TYPE_CHECKING, Any

import yaml

from scripts.validation.codes import ErrorCode
from scripts.validation.models import Severity


if TYPE_CHECKING:
    from pathlib import Path

    from scripts.validation.models import ValidationReport


FULL_COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
DOCKER_ACTION_DIGEST_PATTERN = re.compile(
    r"^docker://[a-z0-9._/-]+(?::[A-Za-z0-9._-]+)?@sha256:[0-9a-f]{64}$"
)
USES_LINE_PATTERN = re.compile(
    r"^\s*(?:-\s*)?uses:\s*(?P<target>[^\s#]+)(?:\s+#\s*(?P<comment>\S.*))?\s*$",
)
VERSION_COMMENT_PATTERN = re.compile(r"^v?\d+(?:\.\d+)*")
PRE_COMMIT_RUN_PATTERN = re.compile(r"\b(?:pre-commit|prek)\s+run\b")
INLINE_SKIP_PATTERN = re.compile(r"\bSKIP=([^\s]+)")
DEPENDABOT_VERSION = 2
SHADOWING_RENOVATE_PATHS: tuple[str, ...] = (
    "renovate.json",
    "renovate.json5",
    ".renovaterc",
    ".renovaterc.json",
    ".renovaterc.jsonc",
    ".renovaterc.json5",
    ".github/renovate.json",
    ".github/renovate.jsonc",
    ".github/renovate.json5",
)


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
            elif ch == "\\":
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

        if ch == "/" and idx + 1 < length:
            nxt = raw_text[idx + 1]
            if nxt == "/":
                idx += 2
                while idx < length and raw_text[idx] != "\n":
                    idx += 1
                continue
            if nxt == "*":
                idx += 2
                while idx + 1 < length and not (
                    raw_text[idx] == "*" and raw_text[idx + 1] == "/"
                ):
                    if raw_text[idx] == "\n":
                        out.append("\n")
                    idx += 1
                idx += 2
                continue

        out.append(ch)
        idx += 1

    return "".join(out)


def validate_workflow_file(workflow_file: Path, report: ValidationReport) -> None:
    """Validate SHA-pinning, version comments, permissions, and checkout credentials in a workflow.

    Args:
        workflow_file: Path to a GitHub Actions workflow YAML file.
        report: Aggregating ValidationReport.
    """
    try:
        content = workflow_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        report.add(
            code=ErrorCode.SUP001,
            message=f"Failed to read workflow file {workflow_file.name}: {exc}",
            severity=Severity.ERROR,
            path=workflow_file,
        )
        return

    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        report.add(
            code=ErrorCode.SUP001,
            message=f"Malformed YAML in workflow {workflow_file.name}: {exc}",
            severity=Severity.ERROR,
            path=workflow_file,
        )
        return

    if not isinstance(data, dict):
        report.add(
            code=ErrorCode.SUP001,
            message=f"Workflow {workflow_file.name} must parse to a YAML mapping.",
            severity=Severity.ERROR,
            path=workflow_file,
        )
        return

    # 1. Inspect raw lines for external `uses:` SHA pinning and version comment hygiene (SUP001)
    for lineno, line in enumerate(content.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        match = USES_LINE_PATTERN.match(line)
        if not match:
            continue

        raw_target = match.group("target").strip("'\"")
        comment = (match.group("comment") or "").strip()

        if raw_target.startswith("./"):
            continue

        if raw_target.startswith("docker://"):
            if not DOCKER_ACTION_DIGEST_PATTERN.match(raw_target):
                report.add(
                    code=ErrorCode.SUP001,
                    message=f"Docker action '{raw_target}' in {workflow_file.name} is not pinned to '@sha256:<64-hex>'.",
                    severity=Severity.ERROR,
                    path=workflow_file,
                    line=lineno,
                    suggestion="Pin docker:// action references with an immutable @sha256:<64-hex> digest.",
                )
            continue

        if "@" not in raw_target:
            report.add(
                code=ErrorCode.SUP001,
                message=f"External action '{raw_target}' in {workflow_file.name} is missing '@<40-char-commit-sha>'.",
                severity=Severity.ERROR,
                path=workflow_file,
                line=lineno,
                suggestion="Pin external GitHub Actions to a full 40-character commit SHA with a # vX.Y.Z comment.",
            )
            continue

        action_slug, ref = raw_target.rsplit("@", 1)
        if not FULL_COMMIT_SHA_PATTERN.match(ref):
            report.add(
                code=ErrorCode.SUP001,
                message=(
                    f"External action '{action_slug}@{ref}' in {workflow_file.name} uses mutable ref '{ref}' instead of a 40-character commit SHA."
                ),
                severity=Severity.ERROR,
                path=workflow_file,
                line=lineno,
                suggestion=f"Resolve '{action_slug}@{ref}' to its immutable 40-char commit SHA and append '# {ref}'.",
            )
        elif not comment or not VERSION_COMMENT_PATTERN.match(comment):
            report.add(
                code=ErrorCode.SUP001,
                message=(
                    f"SHA-pinned action '{action_slug}@{ref[:12]}...' in {workflow_file.name} is missing a trailing '# vX.Y.Z' version comment."
                ),
                severity=Severity.ERROR,
                path=workflow_file,
                line=lineno,
                suggestion="Append a trailing SemVer comment such as '# v7.0.1' so Renovate/humans can audit the version.",
            )

    # 2. Verify explicit least-privilege permissions and checkout persist-credentials: false (SUP002)
    has_top_permissions = "permissions" in data and data["permissions"] is not None
    jobs = data.get("jobs", {})
    if not isinstance(jobs, dict):
        return

    all_jobs_have_permissions = bool(jobs) and all(
        isinstance(j, dict) and "permissions" in j and j["permissions"] is not None
        for j in jobs.values()
    )
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
        steps = job_cfg.get("steps", [])
        if not isinstance(steps, list):
            continue
        for step in steps:
            if not isinstance(step, dict):
                continue
            uses_val = step.get("uses")
            if isinstance(uses_val, str) and uses_val.startswith("actions/checkout@"):
                with_cfg = step.get("with")
                persist_val = (
                    with_cfg.get("persist-credentials")
                    if isinstance(with_cfg, dict)
                    else None
                )
                if persist_val is not False:
                    report.add(
                        code=ErrorCode.SUP002,
                        message=(
                            f"Step in job '{job_id}' ({workflow_file.name}) uses '{uses_val.split('@', 1)[0]}' without 'persist-credentials: false'."
                        ),
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
        content = pre_commit_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        report.add(
            code=ErrorCode.SUP003,
            message=f"Failed to read {pre_commit_file.name}: {exc}",
            severity=Severity.ERROR,
            path=pre_commit_file,
        )
        return

    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        report.add(
            code=ErrorCode.SUP003,
            message=f"Malformed YAML in {pre_commit_file.name}: {exc}",
            severity=Severity.ERROR,
            path=pre_commit_file,
        )
        return

    if not isinstance(data, dict):
        report.add(
            code=ErrorCode.SUP003,
            message=f"{pre_commit_file.name} must parse to a YAML mapping.",
            severity=Severity.ERROR,
            path=pre_commit_file,
        )
        return

    repos = data.get("repos", [])
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
        repo_url = str(repo_entry.get("repo", "")).strip()
        if not repo_url or repo_url in {"local", "meta"}:
            continue
        rev = str(repo_entry.get("rev", "")).strip()
        if not FULL_COMMIT_SHA_PATTERN.match(rev):
            report.add(
                code=ErrorCode.SUP003,
                message=(
                    f"Pre-commit external repository '{repo_url}' uses mutable rev '{rev or '<missing>'}' instead of a 40-char commit SHA."
                ),
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
        raw_text = renovate_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        report.add(
            code=ErrorCode.SUP004,
            message=f"Failed to read {renovate_file.name}: {exc}",
            severity=Severity.ERROR,
            path=renovate_file,
        )
        return

    try:
        data: Any = json.loads(strip_jsonc_comments(raw_text))
    except json.JSONDecodeError as exc:
        report.add(
            code=ErrorCode.SUP004,
            message=f"Malformed JSONC in {renovate_file.name}: {exc}",
            severity=Severity.ERROR,
            path=renovate_file,
            line=exc.lineno,
        )
        return

    if not isinstance(data, dict):
        report.add(
            code=ErrorCode.SUP004,
            message=f"Root of {renovate_file.name} must be a JSON object.",
            severity=Severity.ERROR,
            path=renovate_file,
        )
        return

    extends = data.get("extends", [])
    if (
        not isinstance(extends, list)
        or "helpers:pinGitHubActionDigestsToSemver" not in extends
    ):
        report.add(
            code=ErrorCode.SUP004,
            message=(
                f"{renovate_file.name} must extend 'helpers:pinGitHubActionDigestsToSemver' to maintain SHA-pinned GitHub Actions."
            ),
            severity=Severity.ERROR,
            path=renovate_file,
            suggestion="Add 'helpers:pinGitHubActionDigestsToSemver' to the 'extends' array in renovate.jsonc.",
        )

    pre_commit_cfg = data.get("pre-commit")
    if (
        not isinstance(pre_commit_cfg, dict)
        or pre_commit_cfg.get("enabled") is not True
    ):
        report.add(
            code=ErrorCode.SUP004,
            message=f"{renovate_file.name} must enable the 'pre-commit' manager ('\"pre-commit\": {{\"enabled\": true}}').",
            severity=Severity.ERROR,
            path=renovate_file,
            suggestion="Enable Renovate pre-commit hook digest updates in renovate.jsonc.",
        )

    # The hosted Renovate app rejects object-form `dependencyDashboard` (`{"enabled": true}`)
    # and halts all dependency PRs, while newer Renovate CLIs migrate the boolean form to an
    # object. Inherit the dashboard from `config:best-practices` / `config:recommended` instead.
    if "dependencyDashboard" in data:
        report.add(
            code=ErrorCode.SUP004,
            message=(
                f"{renovate_file.name} must not set 'dependencyDashboard' explicitly (found {json.dumps(data['dependencyDashboard'])}); its schema differs between the hosted Renovate app (boolean) and newer Renovate CLIs (object)."
            ),
            severity=Severity.ERROR,
            path=renovate_file,
            suggestion="Remove 'dependencyDashboard' and inherit it from the 'config:best-practices' preset.",
        )

    # Verify runner package rules with range filtering specify compatible versioning (pep440)
    package_rules = data.get("packageRules", [])
    if isinstance(package_rules, list):
        for rule in package_rules:
            if not isinstance(rule, dict):
                continue
            datasources = rule.get("matchDatasources", [])
            pkg_names = rule.get("matchPackageNames", [])
            if (
                "github-runners" in datasources
                and "ubuntu" in pkg_names
                and "allowedVersions" in rule
                and rule.get("versioning") != "pep440"
            ):
                report.add(
                    code=ErrorCode.SUP004,
                    message=(
                        f"{renovate_file.name} packageRule for github-runners ubuntu must specify 'versioning': 'pep440' to support '{rule.get('allowedVersions')}' range filtering."
                    ),
                    severity=Severity.ERROR,
                    path=renovate_file,
                    suggestion="Set 'versioning': 'pep440' in the github-runners ubuntu packageRule in renovate.jsonc.",
                )


def validate_dependabot_file(dependabot_file: Path, report: ValidationReport) -> None:
    """Validate .github/dependabot.yml syntax and ecosystem coverage.

    Args:
        dependabot_file: Path to .github/dependabot.yml.
        report: Aggregating ValidationReport.
    """
    try:
        content = dependabot_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        report.add(
            code=ErrorCode.SUP004,
            message=f"Failed to read {dependabot_file.name}: {exc}",
            severity=Severity.ERROR,
            path=dependabot_file,
        )
        return

    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        report.add(
            code=ErrorCode.SUP004,
            message=f"Malformed YAML in {dependabot_file.name}: {exc}",
            severity=Severity.ERROR,
            path=dependabot_file,
        )
        return

    if (
        not isinstance(data, dict)
        or data.get("version") != DEPENDABOT_VERSION
        or not isinstance(data.get("updates"), list)
    ):
        report.add(
            code=ErrorCode.SUP004,
            message=f"{dependabot_file.name} must declare 'version: 2' and a valid 'updates' list.",
            severity=Severity.ERROR,
            path=dependabot_file,
        )
        return

    ecosystems = {
        str(entry.get("package-ecosystem", ""))
        for entry in data["updates"]
        if isinstance(entry, dict)
    }
    if "github-actions" not in ecosystems:
        report.add(
            code=ErrorCode.SUP004,
            message=f"{dependabot_file.name} is missing the 'github-actions' package-ecosystem.",
            severity=Severity.ERROR,
            path=dependabot_file,
            suggestion="Configure package-ecosystem: 'github-actions' in .github/dependabot.yml.",
        )


def validate_no_conflicting_renovate_configs(
    repo_root: Path, report: ValidationReport
) -> None:
    """Reject duplicate or shadowing Renovate configuration files alongside renovate.jsonc.

    Args:
        repo_root: Root directory of repository.
        report: Aggregating ValidationReport.
    """
    canonical = repo_root / "renovate.jsonc"
    if not canonical.is_file():
        return

    for rel_path in SHADOWING_RENOVATE_PATHS:
        candidate = repo_root / rel_path
        if candidate.is_file():
            report.add(
                code=ErrorCode.SUP004,
                message=(
                    f"Conflicting Renovate configuration '{rel_path}' coexists with canonical 'renovate.jsonc' and shadows or overrides curated settings."
                ),
                severity=Severity.ERROR,
                path=candidate,
                suggestion=f"Remove '{rel_path}' so Renovate loads 'renovate.jsonc' exclusively.",
            )


def _extract_no_commit_protected_branches(pre_commit_file: Path) -> set[str]:
    """Extract branch names protected by no-commit-to-branch in .pre-commit-config.yaml.

    Args:
        pre_commit_file: Path to .pre-commit-config.yaml.

    Returns:
        Set of protected branch names, or empty set if hook is not configured.
    """
    try:
        data: Any = yaml.safe_load(pre_commit_file.read_text(encoding="utf-8"))
    except OSError, UnicodeDecodeError, yaml.YAMLError:
        return set()

    if not isinstance(data, dict):
        return set()

    repos = data.get("repos", [])
    if not isinstance(repos, list):
        return set()

    protected: set[str] = set()
    for repo_entry in repos:
        if not isinstance(repo_entry, dict):
            continue
        hooks = repo_entry.get("hooks", [])
        if not isinstance(hooks, list):
            continue
        for hook in hooks:
            if not isinstance(hook, dict) or hook.get("id") != "no-commit-to-branch":
                continue
            args = hook.get("args", [])
            if not isinstance(args, list) or not args:
                protected.update({"main", "master"})
                continue
            idx = 0
            found_explicit = False
            while idx < len(args):
                token = str(args[idx])
                if token in {"--branch", "-b"} and idx + 1 < len(args):
                    protected.add(str(args[idx + 1]))
                    found_explicit = True
                    idx += 2
                    continue
                if token.startswith("--branch="):
                    protected.add(token.split("=", 1)[1])
                    found_explicit = True
                idx += 1
            if not found_explicit:
                protected.update({"main", "master"})
    return protected


def _workflow_matches_protected_push(
    workflow_data: dict[object, Any], protected_branches: set[str]
) -> bool:
    """Determine whether a workflow triggers on push to any protected branch.

    Args:
        workflow_data: Parsed workflow YAML mapping.
        protected_branches: Set of branch names guarded by no-commit-to-branch.

    Returns:
        True if a push to a protected branch triggers this workflow.
    """
    triggers: Any = (
        workflow_data.get("on") if "on" in workflow_data else workflow_data.get(True)
    )
    if triggers == "push":
        return True
    if isinstance(triggers, list):
        return "push" in triggers
    if not isinstance(triggers, dict) or "push" not in triggers:
        return False

    push_cfg: Any = triggers["push"]
    if push_cfg is None:
        return True
    if not isinstance(push_cfg, dict):
        return False

    branches = push_cfg.get("branches")
    if isinstance(branches, list):
        branch_set = {str(b) for b in branches}
        return bool(branch_set & protected_branches) or bool(branch_set & {"*", "**"})

    return "tags" not in push_cfg


def _step_skips_hook(
    hook_id: str, wf_env: object, job_env: object, step: dict[str, Any]
) -> bool:
    """Check whether a workflow step configures SKIP containing hook_id.

    Args:
        hook_id: Pre-commit hook identifier to check (e.g., 'no-commit-to-branch').
        wf_env: Top-level workflow env mapping, if any.
        job_env: Job-level env mapping, if any.
        step: Step dictionary containing 'run' and optional 'env'.

    Returns:
        True if SKIP includes hook_id via step/job/workflow env or inline shell assignment.
    """
    for env_candidate in (step.get("env"), job_env, wf_env):
        if isinstance(env_candidate, dict) and "SKIP" in env_candidate:
            skip_items = {
                item.strip()
                for item in str(env_candidate["SKIP"]).split(",")
                if item.strip()
            }
            return hook_id in skip_items

    run_cmd = str(step.get("run", ""))
    for match in INLINE_SKIP_PATTERN.finditer(run_cmd):
        raw_val = match.group(1).strip("'\"")
        skip_items = {item.strip() for item in raw_val.split(",") if item.strip()}
        if hook_id in skip_items:
            return True
    return False


def validate_pre_commit_ci_branch_guard(
    repo_root: Path, report: ValidationReport
) -> None:
    """Verify push workflows running pre-commit skip no-commit-to-branch on protected branches.

    Args:
        repo_root: Root directory of repository.
        report: Aggregating ValidationReport.
    """
    pre_commit_file = repo_root / ".pre-commit-config.yaml"
    workflows_dir = repo_root / ".github" / "workflows"
    if not pre_commit_file.is_file() or not workflows_dir.is_dir():
        return

    protected_branches = _extract_no_commit_protected_branches(pre_commit_file)
    if not protected_branches:
        return

    workflow_files = sorted(
        p
        for p in workflows_dir.iterdir()
        if p.is_file() and p.suffix in {".yml", ".yaml"}
    )
    for wf_file in workflow_files:
        try:
            data: Any = yaml.safe_load(wf_file.read_text(encoding="utf-8"))
        except OSError, UnicodeDecodeError, yaml.YAMLError:
            continue
        if not isinstance(data, dict) or not _workflow_matches_protected_push(
            data, protected_branches
        ):
            continue

        jobs = data.get("jobs", {})
        if not isinstance(jobs, dict):
            continue
        wf_env = data.get("env")
        for job_id, job_cfg in jobs.items():
            if not isinstance(job_cfg, dict):
                continue
            steps = job_cfg.get("steps", [])
            if not isinstance(steps, list):
                continue
            job_env = job_cfg.get("env")
            for step in steps:
                if not isinstance(step, dict):
                    continue
                run_cmd = step.get("run")
                if (
                    isinstance(run_cmd, str)
                    and PRE_COMMIT_RUN_PATTERN.search(run_cmd)
                    and not _step_skips_hook(
                        "no-commit-to-branch", wf_env, job_env, step
                    )
                ):
                    report.add(
                        code=ErrorCode.SUP003,
                        message=(
                            f"Step in job '{job_id}' ({wf_file.name}) runs 'pre-commit run' / 'prek run' on push to {sorted(protected_branches)} without skipping 'no-commit-to-branch'."
                        ),
                        severity=Severity.ERROR,
                        path=wf_file,
                        suggestion="Add 'env: { SKIP: no-commit-to-branch }' to the 'prek run' / 'pre-commit run' step so post-merge branch checkouts do not fail.",
                    )


def validate_supply_chain(repo_root: Path, report: ValidationReport) -> None:
    """Validate supply-chain pinning across workflows, pre-commit, Renovate, and Dependabot.

    Args:
        repo_root: Root directory of repository.
        report: Aggregating ValidationReport.
    """
    workflows_dir = repo_root / ".github" / "workflows"
    if workflows_dir.is_dir():
        workflow_files = sorted(
            p
            for p in workflows_dir.iterdir()
            if p.is_file() and p.suffix in {".yml", ".yaml"}
        )
        for wf_file in workflow_files:
            validate_workflow_file(wf_file, report)

    pre_commit_file = repo_root / ".pre-commit-config.yaml"
    if pre_commit_file.is_file():
        validate_pre_commit_file(pre_commit_file, report)

    validate_pre_commit_ci_branch_guard(repo_root, report)

    renovate_file = repo_root / "renovate.jsonc"
    if renovate_file.is_file():
        validate_renovate_file(renovate_file, report)
        validate_no_conflicting_renovate_configs(repo_root, report)

    dependabot_file = repo_root / ".github" / "dependabot.yml"
    if dependabot_file.is_file():
        validate_dependabot_file(dependabot_file, report)
