"""Report formatting and terminal rendering for AntiGravity validation."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from scripts.validation.models import ValidationReport


# ANSI color codes
_RESET = '\033[0m'
_BOLD = '\033[1m'
_RED = '\033[31m'
_GREEN = '\033[32m'
_YELLOW = '\033[33m'
_CYAN = '\033[36m'
_GRAY = '\033[90m'


def format_terminal(report: ValidationReport, use_color: bool = True) -> str:
    """Format a ValidationReport into human-readable terminal output.

    Args:
        report: ValidationReport to format.
        use_color: Whether to include ANSI color escapes.

    Returns:
        Formatted multi-line report string.
    """
    lines: list[str] = []

    bold = _BOLD if use_color else ''
    red = _RED if use_color else ''
    green = _GREEN if use_color else ''
    yellow = _YELLOW if use_color else ''
    cyan = _CYAN if use_color else ''
    gray = _GRAY if use_color else ''
    reset = _RESET if use_color else ''

    if report.is_clean:
        lines.append(f'{bold}{green}[PASS]{reset} AntiGravity 2.29.0 Agentic Settings Validation: all checks passed cleanly.')
        return '\n'.join(lines)

    total_issues = len(report.issues)
    header = f'{bold}{red}[FAIL]{reset} AntiGravity 2.29.0 Agentic Settings Validation ({total_issues} issue{"s" if total_issues != 1 else ""} found: {report.error_count} error{"s" if report.error_count != 1 else ""}, {report.warning_count} warning{"s" if report.warning_count != 1 else ""})'
    lines.append(header)
    lines.append('')

    for issue in report.issues:
        sev_color = red if issue.severity.value == 'ERROR' else yellow
        sev_label = f'{sev_color}[{issue.severity.value}]{reset}'
        code_label = f'{bold}{cyan}[{issue.code}]{reset}'
        line_info = f':{issue.line}' if issue.line is not None else ''
        path_str = f'{gray}{issue.path}{line_info}{reset}'

        lines.append(f'  {sev_label} {code_label} {path_str}')
        lines.append(f'    {issue.message}')
        if issue.suggestion:
            lines.append(f'    {gray}Suggestion: {issue.suggestion}{reset}')
        lines.append('')

    lines.append(f'{bold}Result:{reset} Validation FAILED ({report.error_count} errors, {report.warning_count} warnings).')
    return '\n'.join(lines)


def format_json(report: ValidationReport) -> str:
    """Serialize ValidationReport to formatted JSON.

    Args:
        report: ValidationReport to serialize.

    Returns:
        Formatted JSON string.
    """
    return report.to_json(indent=2)


def render_report(
    report: ValidationReport,
    as_json: bool = False,
    use_color: bool = True,
) -> int:
    """Render report to stdout and return the appropriate process exit code.

    Args:
        report: ValidationReport to render.
        as_json: If True, output pure JSON.
        use_color: If True, use ANSI color sequences for terminal output.

    Returns:
        0 if report passed, 1 if validation failed.
    """
    if as_json:
        sys.stdout.write(format_json(report) + '\n')
    else:
        # Check if stdout is an interactive terminal
        supports_color = use_color and sys.stdout.isatty()
        sys.stdout.write(format_terminal(report, use_color=supports_color) + '\n')

    return 0 if report.is_clean else 1
