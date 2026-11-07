#!/usr/bin/env python3
"""CLI runner for AntiGravity 2.29.0 agentic settings validation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.validation.engine import validate_all  # ruff: ignore[module-import-not-at-top-of-file]
from scripts.validation.reporter import render_report  # ruff: ignore[module-import-not-at-top-of-file]


def build_parser() -> argparse.ArgumentParser:
    """Construct command-line argument parser.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        prog='validate_agentic_settings',
        description='Validate AntiGravity 2.29.0 agentic settings, skills, rules, hooks, and MCP configs.',
    )
    parser.add_argument(
        '--path',
        type=Path,
        default=None,
        help='Target repository root directory (defaults to current working directory).',
    )
    parser.add_argument(
        '--strict',
        action='store_true',
        help='Treat warnings as validation failures (exit non-zero on any issue).',
    )
    parser.add_argument(
        '--check',
        action='store_true',
        default=True,
        help='Run in verification check mode without making modifications (default behavior).',
    )
    parser.add_argument(
        '--fix',
        action='store_true',
        help='Automatically apply safe remediations (e.g., chmod +x on scripts).',
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output validation report in machine-readable JSON format.',
    )
    parser.add_argument(
        '--no-color',
        action='store_true',
        help='Disable ANSI color escape sequences in terminal output.',
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Execute AntiGravity 2.29.0 validation suite.

    Args:
        argv: Optional command-line arguments (defaults to sys.argv[1:]).

    Returns:
        Exit code: 0 if validation passed, 1 if validation failed.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    repo_root = args.path.resolve() if args.path is not None else Path.cwd().resolve()
    report = validate_all(
        repo_root=repo_root,
        strict=args.strict,
        fix=args.fix,
    )

    return render_report(
        report,
        as_json=args.json,
        use_color=not args.no_color,
    )


if __name__ == '__main__':
    sys.exit(main())
