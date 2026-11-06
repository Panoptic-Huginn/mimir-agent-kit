"""Validator for prompt consistency and cross-skill references."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from scripts.validation.codes import ErrorCode
from scripts.validation.models import Severity


if TYPE_CHECKING:
    from pathlib import Path

    from scripts.validation.models import ValidationReport


RELATED_SKILL_PATTERN = re.compile(r'^\s*-\s*(?:\*\*)?`?/([a-z0-9]+(?:-[a-z0-9]+)*)`?(?:\*\*)?:?')
AUTONOMOUS_MERGE_PERMITTED_PATTERN = re.compile(
    r'\b(?:autonomous\s+merge\s+(?:is\s+)?(?:permitted|allowed|enabled)|auto-merge\s+(?:is\s+)?(?:permitted|allowed|enabled)|(?:permit|allow|enable)(?:s|ed)?\s+(?:autonomous\s+)?merge)\b',
    re.IGNORECASE,
)
PIXI_IN_MIMIR_PATTERN = re.compile(
    r'\b(?:pixi\s+(?:run|add|install|sync))\b',
    re.IGNORECASE,
)


def validate_prompts(
    repo_root: Path,
    report: ValidationReport,
) -> None:
    """Validate prompt consistency, cross-skill links, and contradictory directives.

    Args:
        repo_root: Root of repository.
        report: Aggregating ValidationReport.
    """
    skills_dir = repo_root / 'skills'
    existing_skills: set[str] = set()
    if skills_dir.is_dir():
        existing_skills = {p.name for p in skills_dir.iterdir() if p.is_dir() and not p.name.startswith('.') and (p / 'SKILL.md').is_file()}

    # 1. Check cross-skill references under '## Related Skills' in all SKILL.md files (PRM001)
    if skills_dir.is_dir():
        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir() or skill_dir.name.startswith('.'):
                continue
            skill_file = skill_dir / 'SKILL.md'
            if not skill_file.is_file():
                continue

            try:
                content = skill_file.read_text(encoding='utf-8')
            except OSError, UnicodeDecodeError:
                continue

            in_related_skills_section = False
            for line_idx, line in enumerate(content.splitlines(), start=1):
                stripped = line.strip()
                if stripped.startswith('## Related Skills'):
                    in_related_skills_section = True
                    continue
                if in_related_skills_section:
                    if stripped.startswith('## ') or stripped.startswith('---'):
                        in_related_skills_section = False
                        continue
                    match = RELATED_SKILL_PATTERN.match(stripped)
                    if match:
                        ref_skill = match.group(1)
                        if ref_skill not in existing_skills:
                            report.add(
                                code=ErrorCode.PRM001,
                                message=(f"Cross-skill reference '/{ref_skill}' in '{skill_dir.name}' references non-existent skill. Available skills: {', '.join(sorted(existing_skills))}"),
                                severity=Severity.ERROR,
                                path=skill_file,
                                line=line_idx,
                                suggestion=f"Remove or fix reference to '/{ref_skill}'.",
                            )

    # 2. Check rules/AGENTS.md for PRM001, PRM002, PRM003
    rules_agents = repo_root / 'rules' / 'AGENTS.md'
    if rules_agents.is_file():
        try:
            content = rules_agents.read_text(encoding='utf-8')
            for line_idx, line in enumerate(content.splitlines(), start=1):
                # Check PRM002: Contradictory PR merge directives
                if AUTONOMOUS_MERGE_PERMITTED_PATTERN.search(line) and not re.search(r'\b(?:no|never|forbidden|prohibit(?:ed)?)\b', line, re.IGNORECASE):
                    report.add(
                        code=ErrorCode.PRM002,
                        message='Contradictory PR merge directive: autonomous PR merging is strictly prohibited.',
                        severity=Severity.ERROR,
                        path=rules_agents,
                        line=line_idx,
                        suggestion='Ensure prompts and rules mandate human review and prohibit autonomous PR merges.',
                    )

                # Check PRM003: Prescribing pixi for commands in pure uv repo
                if PIXI_IN_MIMIR_PATTERN.search(line) and 'pixi to uv' not in line.lower() and not re.search(r'\b(?:no|never|forbidden|prohibit(?:ed)?|do\s+not|don\'?t)\b', line, re.IGNORECASE):
                    report.add(
                        code=ErrorCode.PRM003,
                        message='Rule prescribes pixi for repo commands in pure uv repository.',
                        severity=Severity.ERROR,
                        path=rules_agents,
                        line=line_idx,
                        suggestion='Translate command from pixi to uv.',
                    )
        except OSError, UnicodeDecodeError:
            pass
