"""Validator for AntiGravity 2.29.0 skills (skills/ directory)."""

import os
import re
from typing import TYPE_CHECKING, Any

import yaml

from scripts.validation.codes import ErrorCode
from scripts.validation.models import Severity


if TYPE_CHECKING:
    from pathlib import Path

    from scripts.validation.models import ValidationReport


MAX_SKILL_BODY_BYTES = 24_000
MIN_DESCRIPTION_LENGTH = 20
FRONTMATTER_SPLIT_PARTS = 3
ALLOWED_SKILL_SUBDIRS = frozenset({
    "scripts",
    "examples",
    "resources",
    "references",
    "__pycache__",
})
NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]*)\]\(([^)#\s]+)(?:#[^)]*)?\)")


def validate_skill_file(
    skill_file: Path,
    expected_name: str,
    report: ValidationReport,
) -> tuple[dict[str, Any] | None, str | None]:
    """Validate a single SKILL.md file against AntiGravity 2.29.0 specifications.

    Args:
        skill_file: Path to the SKILL.md file.
        expected_name: Directory name that skill name must match.
        report: Aggregating ValidationReport.

    Returns:
        Tuple of (parsed_frontmatter, markdown_body) if valid, or (None, None).
    """
    try:
        content = skill_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        report.add(
            code=ErrorCode.SKL002,
            message=f"Failed to read SKILL.md: {exc}",
            severity=Severity.ERROR,
            path=skill_file,
            suggestion="Ensure file is valid UTF-8 text.",
        )
        return None, None

    if not content.startswith("---\n"):
        report.add(
            code=ErrorCode.SKL002,
            message="SKILL.md must begin with YAML frontmatter delimiter (---) on line 1.",
            severity=Severity.ERROR,
            path=skill_file,
            line=1,
            suggestion="Add opening YAML frontmatter delimiter (---) on line 1.",
        )
        return None, None

    parts = content.split("---\n", 2)
    if len(parts) < FRONTMATTER_SPLIT_PARTS:
        report.add(
            code=ErrorCode.SKL002,
            message="SKILL.md missing closing YAML frontmatter delimiter (---).",
            severity=Severity.ERROR,
            path=skill_file,
            suggestion="Ensure YAML frontmatter is closed with a newline and delimiter (---).",
        )
        return None, None

    raw_yaml = parts[1]
    body = parts[2].lstrip("\n")

    try:
        frontmatter = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:
        report.add(
            code=ErrorCode.SKL002,
            message=f"Malformed YAML in frontmatter: {exc}",
            severity=Severity.ERROR,
            path=skill_file,
            suggestion="Fix YAML syntax errors in frontmatter.",
        )
        return None, None

    if not isinstance(frontmatter, dict):
        report.add(
            code=ErrorCode.SKL002,
            message="YAML frontmatter must evaluate to a dictionary/mapping.",
            severity=Severity.ERROR,
            path=skill_file,
            suggestion="Structure frontmatter as key-value pairs.",
        )
        return None, None

    # Validate skill name (SKL003)
    name = frontmatter.get("name")
    if (
        not isinstance(name, str)
        or not NAME_PATTERN.match(name)
        or name != expected_name
    ):
        report.add(
            code=ErrorCode.SKL003,
            message=(
                f"Skill name '{name}' is invalid or does not match directory '{expected_name}'. Must be lowercase alphanumeric with hyphens."
            ),
            severity=Severity.ERROR,
            path=skill_file,
            suggestion=f"Update frontmatter 'name' to exactly match directory name '{expected_name}'.",
        )

    # Validate description (SKL004)
    description = str(frontmatter.get("description", "")).strip()
    if len(description) < MIN_DESCRIPTION_LENGTH:
        report.add(
            code=ErrorCode.SKL004,
            message=(
                f"Skill description is insufficient ({len(description)} chars). Must be at least {MIN_DESCRIPTION_LENGTH} characters."
            ),
            severity=Severity.ERROR,
            path=skill_file,
            suggestion="Provide a detailed third-person description stating what the skill does and when to use it.",
        )

    # Validate body size hard cap (SKL005)
    body_bytes = len(body.encode("utf-8"))
    if body_bytes > MAX_SKILL_BODY_BYTES:
        report.add(
            code=ErrorCode.SKL005,
            message=(
                f"Markdown body size ({body_bytes} bytes) exceeds AntiGravity {MAX_SKILL_BODY_BYTES} byte hard cap."
            ),
            severity=Severity.ERROR,
            path=skill_file,
            suggestion="Move extensive manuals or reference tables into references/ subfolder.",
        )

    return frontmatter, body


def validate_skill_links(md_file: Path, report: ValidationReport) -> None:
    """Validate relative markdown links inside a skill documentation file.

    Args:
        md_file: Path to markdown file.
        report: Aggregating ValidationReport.
    """
    try:
        content = md_file.read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return

    for line_idx, line in enumerate(content.splitlines(), start=1):
        for match in MARKDOWN_LINK_PATTERN.finditer(line):
            target = match.group(2)
            if target.startswith(("http://", "https://", "mailto:", "ftp:", "#")):
                continue

            resolved = (md_file.parent / target).resolve()
            if not resolved.exists():
                report.add(
                    code=ErrorCode.SKL008,
                    message=f"Broken relative markdown link: {target}",
                    severity=Severity.ERROR,
                    path=md_file,
                    line=line_idx,
                    suggestion=f"Fix path '{target}' or create missing referenced target.",
                )


def validate_skill_directory(
    skill_dir: Path,
    report: ValidationReport,
    fix: bool = False,
) -> None:
    """Validate an individual skill directory.

    Args:
        skill_dir: Skill directory path.
        report: Aggregating ValidationReport.
        fix: If True, automatically correct fixable issues like script permissions.
    """
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.is_file():
        report.add(
            code=ErrorCode.SKL001,
            message=f"Missing mandatory SKILL.md in skill directory '{skill_dir.name}'.",
            severity=Severity.ERROR,
            path=skill_dir,
            suggestion="Create SKILL.md entrypoint with YAML frontmatter.",
        )
        return

    # Check top-level folder names inside skill directory (SKL006)
    for entry in skill_dir.iterdir():
        if (
            entry.is_dir()
            and not entry.name.startswith(".")
            and entry.name not in ALLOWED_SKILL_SUBDIRS
        ):
            report.add(
                code=ErrorCode.SKL006,
                message=f"Disallowed top-level folder '{entry.name}' in skill directory '{skill_dir.name}'.",
                severity=Severity.ERROR,
                path=entry,
                suggestion=f"Allowed subfolders are: {', '.join(sorted(ALLOWED_SKILL_SUBDIRS))}",
            )

    # Validate SKILL.md frontmatter and content
    _, _ = validate_skill_file(skill_file, skill_dir.name, report)

    # Validate links in SKILL.md and references/
    validate_skill_links(skill_file, report)
    references_dir = skill_dir / "references"
    if references_dir.is_dir():
        for ref_file in references_dir.glob("**/*.md"):
            validate_skill_links(ref_file, report)

    # Check executable bit on scripts in scripts/ (SKL007)
    scripts_dir = skill_dir / "scripts"
    if scripts_dir.is_dir():
        for script_file in scripts_dir.iterdir():
            if (
                script_file.is_file()
                and not script_file.name.startswith(".")
                and not os.access(script_file, os.X_OK)
            ):
                if fix:
                    try:
                        script_file.chmod(script_file.stat().st_mode | 0o755)
                    except OSError as exc:
                        report.add(
                            code=ErrorCode.SKL007,
                            message=f"Failed to set executable bit on {script_file}: {exc}",
                            severity=Severity.ERROR,
                            path=script_file,
                            suggestion=f"Run chmod +x {script_file}",
                        )
                else:
                    report.add(
                        code=ErrorCode.SKL007,
                        message=f"Helper script inside scripts/ lacks executable bit (+x): {script_file.name}",
                        severity=Severity.ERROR,
                        path=script_file,
                        suggestion=f"Run chmod +x {script_file}",
                    )


def validate_skills(
    repo_root: Path,
    report: ValidationReport,
    fix: bool = False,
) -> None:
    """Validate all skill directories under repo_root/skills.

    Args:
        repo_root: Root path of the repository or plugin.
        report: Aggregating ValidationReport.
        fix: If True, automatically correct fixable issues like script permissions.
    """
    skills_dir = repo_root / "skills"
    if not skills_dir.is_dir():
        return

    for entry in sorted(skills_dir.iterdir()):
        if entry.is_dir() and not entry.name.startswith("."):
            validate_skill_directory(entry, report, fix=fix)
