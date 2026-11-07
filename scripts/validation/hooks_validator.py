"""Validator for AntiGravity 2.29.0 lifecycle hooks (hooks.json)."""

from __future__ import annotations

import json
import os
import shlex
from typing import TYPE_CHECKING

from scripts.validation.codes import ErrorCode
from scripts.validation.models import Severity


if TYPE_CHECKING:
    from pathlib import Path

    from scripts.validation.models import ValidationReport


VALID_LIFECYCLE_EVENTS = frozenset({
    'SessionStart',
    'PreToolUse',
    'PostToolUse',
    'PreInvocation',
    'PostInvocation',
    'Stop',
})

TOOL_LIFECYCLE_EVENTS = frozenset({'PreToolUse', 'PostToolUse'})
FLAT_LIFECYCLE_EVENTS = frozenset({'SessionStart', 'PreInvocation', 'PostInvocation', 'Stop'})


def _validate_handler(
    handler: object,
    event_name: str,
    hooks_file: Path,
    repo_root: Path,
    report: ValidationReport,
    fix: bool = False,
) -> None:
    """Validate a single hook handler specification.

    Args:
        handler: Hook handler object.
        event_name: Name of lifecycle event.
        hooks_file: Path to hooks.json.
        repo_root: Root of repository.
        report: Aggregating ValidationReport.
        fix: If True, fix script permissions.
    """
    if not isinstance(handler, dict):
        report.add(
            code=ErrorCode.HOK004,
            message=f"Handler in event '{event_name}' must be a dictionary object.",
            severity=Severity.ERROR,
            path=hooks_file,
        )
        return

    # Check HOK004: command string
    command = handler.get('command')
    if not isinstance(command, str) or not command.strip():
        report.add(
            code=ErrorCode.HOK004,
            message=f"Handler in event '{event_name}' is missing a valid 'command' string.",
            severity=Severity.ERROR,
            path=hooks_file,
            suggestion="Specify a non-empty 'command' string for the hook handler.",
        )
        return

    # Check HOK005: timeout positive integer
    if 'timeout' in handler:
        timeout = handler['timeout']
        if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
            report.add(
                code=ErrorCode.HOK005,
                message=f"Handler timeout in event '{event_name}' must be a positive integer (got {timeout!r}).",
                severity=Severity.ERROR,
                path=hooks_file,
                suggestion="Set 'timeout' to a positive integer number of seconds (e.g. 10, 30).",
            )

    # Check HOK006: referenced script file existence and executable bit
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    for token in tokens:
        if token.startswith('-'):
            continue
        # Check if token looks like a script path
        if token.endswith(('.py', '.sh', '.bash', '.js', '.mjs', '.ts', '.rb')) or token.startswith(('./', 'scripts/')):
            script_path = (repo_root / token).resolve()
            # If path points inside repository
            if repo_root in script_path.parents or script_path.parent == repo_root:
                if not script_path.is_file():
                    report.add(
                        code=ErrorCode.HOK006,
                        message=f"Handler command references non-existent script file '{token}' in event '{event_name}'.",
                        severity=Severity.ERROR,
                        path=hooks_file,
                        suggestion=f"Ensure script file '{token}' exists at {script_path}.",
                    )
                elif not os.access(script_path, os.X_OK):
                    if fix:
                        try:
                            script_path.chmod(script_path.stat().st_mode | 0o755)
                        except OSError as exc:
                            report.add(
                                code=ErrorCode.HOK006,
                                message=f'Failed to set executable bit on {script_path}: {exc}',
                                severity=Severity.ERROR,
                                path=script_path,
                                suggestion=f'Run chmod +x {script_path}',
                            )
                    else:
                        report.add(
                            code=ErrorCode.HOK006,
                            message=f"Handler script '{token}' lacks executable bit (+x) in event '{event_name}'.",
                            severity=Severity.ERROR,
                            path=script_path,
                            suggestion=f'Run chmod +x {script_path}',
                        )


def validate_hooks_file(
    hooks_file: Path,
    repo_root: Path,
    report: ValidationReport,
    fix: bool = False,
) -> None:
    """Validate a hooks.json file against AntiGravity 2.29.0 schema.

    Args:
        hooks_file: Path to hooks.json.
        repo_root: Root directory of repository.
        report: Aggregating ValidationReport.
        fix: If True, fix script permissions.
    """
    try:
        content = hooks_file.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as exc:
        report.add(
            code=ErrorCode.HOK001,
            message=f'Failed to read hooks file: {exc}',
            severity=Severity.ERROR,
            path=hooks_file,
        )
        return

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        report.add(
            code=ErrorCode.HOK001,
            message=f'Malformed JSON in hooks.json: {exc}',
            severity=Severity.ERROR,
            path=hooks_file,
            line=exc.lineno,
            suggestion='Ensure hooks.json contains valid JSON syntax.',
        )
        return

    if not isinstance(data, dict):
        report.add(
            code=ErrorCode.HOK001,
            message='hooks.json root must be a JSON object mapping hook group names to event configurations.',
            severity=Severity.ERROR,
            path=hooks_file,
            suggestion='Define hook groups as top-level keys.',
        )
        return

    for group_name, group_cfg in data.items():
        if not isinstance(group_cfg, dict):
            report.add(
                code=ErrorCode.HOK001,
                message=f"Hook group '{group_name}' configuration must be an object.",
                severity=Severity.ERROR,
                path=hooks_file,
            )
            continue

        for key, val in group_cfg.items():
            if key == 'enabled':
                if not isinstance(val, bool):
                    report.add(
                        code=ErrorCode.HOK001,
                        message=f"'enabled' flag in group '{group_name}' must be a boolean.",
                        severity=Severity.ERROR,
                        path=hooks_file,
                    )
                continue

            if key not in VALID_LIFECYCLE_EVENTS:
                report.add(
                    code=ErrorCode.HOK002,
                    message=(f"Invalid lifecycle event name '{key}' in hook group '{group_name}'. Valid events are: {', '.join(sorted(VALID_LIFECYCLE_EVENTS))}"),
                    severity=Severity.ERROR,
                    path=hooks_file,
                    suggestion=f'Use a valid event name: {", ".join(sorted(VALID_LIFECYCLE_EVENTS))}',
                )
                continue

            if key in TOOL_LIFECYCLE_EVENTS:
                if not isinstance(val, list):
                    report.add(
                        code=ErrorCode.HOK003,
                        message=f"Tool event '{key}' in group '{group_name}' must be an array of matcher objects.",
                        severity=Severity.ERROR,
                        path=hooks_file,
                    )
                    continue

                for item in val:
                    if not isinstance(item, dict) or 'matcher' not in item or 'hooks' not in item:
                        report.add(
                            code=ErrorCode.HOK003,
                            message=(f"Tool event '{key}' entry must be an object containing 'matcher' (regex string) and 'hooks' (array of handlers)."),
                            severity=Severity.ERROR,
                            path=hooks_file,
                            suggestion="Wrap tool handlers in {'matcher': '<regex>', 'hooks': [...]}.",
                        )
                        continue

                    if not isinstance(item['hooks'], list):
                        report.add(
                            code=ErrorCode.HOK003,
                            message=f"'hooks' field in '{key}' matcher must be an array of handlers.",
                            severity=Severity.ERROR,
                            path=hooks_file,
                        )
                        continue

                    for handler in item['hooks']:
                        _validate_handler(handler, key, hooks_file, repo_root, report, fix=fix)

            elif key in FLAT_LIFECYCLE_EVENTS:
                if not isinstance(val, list):
                    report.add(
                        code=ErrorCode.HOK004,
                        message=f"Lifecycle event '{key}' in group '{group_name}' must be an array of handlers.",
                        severity=Severity.ERROR,
                        path=hooks_file,
                    )
                    continue

                for handler in val:
                    _validate_handler(handler, key, hooks_file, repo_root, report, fix=fix)


def validate_hooks(
    repo_root: Path,
    report: ValidationReport,
    fix: bool = False,
) -> None:
    """Validate all hooks files in the repository.

    Args:
        repo_root: Root path of the repository.
        report: Aggregating ValidationReport.
        fix: If True, fix script permissions.
    """
    hooks_file = repo_root / 'hooks.json'
    if hooks_file.is_file():
        validate_hooks_file(hooks_file, repo_root, report, fix=fix)

    agents_hooks = repo_root / '.agents' / 'hooks.json'
    if agents_hooks.is_file():
        validate_hooks_file(agents_hooks, repo_root, report, fix=fix)
