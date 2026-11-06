"""Validator for AntiGravity 2.29.0 workspace and plugin rules (rules/ directory)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import yaml

from scripts.validation.codes import ErrorCode
from scripts.validation.models import Severity


if TYPE_CHECKING:
    from pathlib import Path

    from scripts.validation.models import ValidationReport


MAX_RULE_FILE_BYTES = 24_000
MAX_ALWAYS_ON_TOKENS = 20_000

VALID_TRIGGERS = frozenset({
    'always_on',
    'model_decision',
    'glob',
    'manual',
    'ALWAYS_ON',
    'MODEL_DECISION',
    'GLOB',
    'MANUAL',
    'CORTEX_MEMORY_TRIGGER_ALWAYS_ON',
    'CORTEX_MEMORY_TRIGGER_MODEL_DECISION',
    'CORTEX_MEMORY_TRIGGER_GLOB',
    'CORTEX_MEMORY_TRIGGER_MANUAL',
})

ALWAYS_ON_TRIGGERS = frozenset({
    'always_on',
    'ALWAYS_ON',
    'CORTEX_MEMORY_TRIGGER_ALWAYS_ON',
})


def estimate_tokens(text: str) -> int:
    """Estimate token count for a text string using 4-chars-per-token heuristic.

    Args:
        text: Input text.

    Returns:
        Estimated token count.
    """
    return max(1, len(text) // 4) if text else 0


def validate_rules(
    repo_root: Path,
    report: ValidationReport,
) -> None:
    """Validate repository and plugin rules against AntiGravity 2.29.0 specifications.

    Args:
        repo_root: Root path of repository or plugin.
        report: Aggregating ValidationReport.
    """
    # Check RUL001: Top-level AGENTS.md placed at plugin root
    root_agents_md = repo_root / 'AGENTS.md'
    if root_agents_md.is_file():
        report.add(
            code=ErrorCode.RUL001,
            message=('Top-level AGENTS.md placed at plugin root is ignored by AntiGravity plugin runtime. Must be located at rules/AGENTS.md.'),
            severity=Severity.ERROR,
            path=root_agents_md,
            suggestion='Move AGENTS.md into rules/AGENTS.md.',
        )

    # Inspect rules/ directory
    rules_dir = repo_root / 'rules'
    rules_files: list[Path] = []
    if rules_dir.is_dir():
        rules_files.extend([p for p in rules_dir.glob('**/*.md') if p.is_file()])

    # Inspect .agents/rules directory if present
    agents_rules_dir = repo_root / '.agents' / 'rules'
    if agents_rules_dir.is_dir():
        rules_files.extend([p for p in agents_rules_dir.glob('**/*.md') if p.is_file()])

    total_always_on_tokens = 0

    for rule_file in rules_files:
        try:
            content = rule_file.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError) as exc:
            report.add(
                code=ErrorCode.RUL004,
                message=f'Failed to read rule file {rule_file.name}: {exc}',
                severity=Severity.ERROR,
                path=rule_file,
            )
            continue

        file_bytes = len(content.encode('utf-8'))
        if file_bytes > MAX_RULE_FILE_BYTES:
            report.add(
                code=ErrorCode.RUL004,
                message=(f"Rule file '{rule_file.name}' is {file_bytes} bytes, exceeding AntiGravity {MAX_RULE_FILE_BYTES} byte hard cap."),
                severity=Severity.ERROR,
                path=rule_file,
                suggestion='Refactor or modularize rules to stay within 24,000 bytes per file.',
            )

        # Check RUL002: Standalone rules/AGENTS.md must NOT have YAML frontmatter
        if rule_file.name in {'AGENTS.md', 'GEMINI.md'} and rule_file.parent == rules_dir:
            if content.startswith('---\n'):
                report.add(
                    code=ErrorCode.RUL002,
                    message='Plugin rules/AGENTS.md must be plain Markdown without YAML frontmatter.',
                    severity=Severity.ERROR,
                    path=rule_file,
                    line=1,
                    suggestion='Remove YAML frontmatter from rules/AGENTS.md.',
                )
            # Default trigger for rules/AGENTS.md in plugins is always_on
            total_always_on_tokens += estimate_tokens(content)
            continue

        # Check frontmatter and trigger for other rule files (e.g., .agents/rules/*.md)
        if content.startswith('---\n'):
            parts = content.split('---\n', 2)
            if len(parts) < 3:
                report.add(
                    code=ErrorCode.RUL002,
                    message=f"Rule file '{rule_file.name}' missing closing YAML frontmatter delimiter (---).",
                    severity=Severity.ERROR,
                    path=rule_file,
                    line=1,
                    suggestion='Ensure YAML frontmatter is closed with a newline and delimiter (---).',
                )
                continue

            raw_yaml = parts[1]
            try:
                fm = yaml.safe_load(raw_yaml)
            except yaml.YAMLError as exc:
                report.add(
                    code=ErrorCode.RUL002,
                    message=f"Malformed YAML frontmatter in rule file '{rule_file.name}': {exc}",
                    severity=Severity.ERROR,
                    path=rule_file,
                    suggestion='Fix YAML syntax errors in rule frontmatter.',
                )
                continue

            if not isinstance(fm, dict):
                report.add(
                    code=ErrorCode.RUL002,
                    message=f"YAML frontmatter in rule file '{rule_file.name}' must evaluate to a dictionary/mapping.",
                    severity=Severity.ERROR,
                    path=rule_file,
                    suggestion='Structure frontmatter as key-value pairs (e.g. trigger: always_on).',
                )
                continue

            if 'trigger' not in fm:
                report.add(
                    code=ErrorCode.RUL003,
                    message=f"Missing 'trigger' enum in rule frontmatter in {rule_file.name}.",
                    severity=Severity.ERROR,
                    path=rule_file,
                    suggestion='Specify a valid trigger enum in frontmatter.',
                )
            else:
                trigger_val = str(fm['trigger']).strip()
                if trigger_val not in VALID_TRIGGERS:
                    report.add(
                        code=ErrorCode.RUL003,
                        message=(f"Invalid rule trigger '{trigger_val}' in {rule_file.name}. Must be one of: {', '.join(sorted(VALID_TRIGGERS))}"),
                        severity=Severity.ERROR,
                        path=rule_file,
                        suggestion='Use a valid trigger enum (always_on, model_decision, glob, manual).',
                    )
                elif trigger_val in ALWAYS_ON_TRIGGERS:
                    body_content = parts[2]
                    total_always_on_tokens += estimate_tokens(body_content)
        else:
            # Plain markdown rule without frontmatter defaults to always_on
            total_always_on_tokens += estimate_tokens(content)

    if total_always_on_tokens > MAX_ALWAYS_ON_TOKENS:
        report.add(
            code=ErrorCode.RUL004,
            message=(f'Aggregate always-on rules budget ({total_always_on_tokens} estimated tokens) exceeds AntiGravity {MAX_ALWAYS_ON_TOKENS} token limit.'),
            severity=Severity.ERROR,
            path=rules_dir if rules_dir.is_dir() else repo_root,
            suggestion='Reduce always-on rules content or convert rules to model_decision/glob triggers.',
        )
