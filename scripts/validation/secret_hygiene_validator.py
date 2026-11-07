"""Validator for secret hygiene and workspace isolation (SEC001-SEC002)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from scripts.validation.codes import ErrorCode
from scripts.validation.models import Severity


if TYPE_CHECKING:
    from pathlib import Path

    from scripts.validation.models import ValidationReport


EXCLUDED_DIRS = frozenset({
    '.agents',
    '.agents/teamwork',
    '.git',
    '.mypy_cache',
    '.pytest_cache',
    '.ruff_cache',
    '.rumdl_cache',
    '.venv',
    '__pycache__',
})

# Split strings so validator file does not trigger false positives
_HOME_PATTERN = re.compile(r'/home/' + r'jamie-lapointe|/Users/' + r'jamie')
_DRIVE_PATTERN = re.compile(r'Google' + r'Drive/agents')
_TOKEN_PATTERNS = [
    re.compile(r'\bghp_[A-Za-z0-9]{20,}'),
    re.compile(r'\bgho_[A-Za-z0-9]{20,}'),
    re.compile(r'\bgithub_pat_[A-Za-z0-9_]{20,}'),
    re.compile(r'\bGOCSPX-[A-Za-z0-9_-]{15,}'),
    re.compile(r'\bAIzaSy[A-Za-z0-9_-]{25,}'),
]


def validate_secret_hygiene(
    repo_root: Path,
    report: ValidationReport,
) -> None:
    """Scan repository files for leaked home paths or credentials.

    Args:
        repo_root: Root path of repository.
        report: Aggregating ValidationReport.
    """
    for path in repo_root.rglob('*'):
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        try:
            rel = str(path.relative_to(repo_root))
            if any(rel.startswith(d) for d in EXCLUDED_DIRS):
                continue
        except ValueError:
            pass

        if not path.is_file():
            continue

        if path.name.startswith('.coverage') or path.suffix in {'.png', '.jpg', '.jpeg', '.webp', '.ico', '.db', '.pyc'}:
            continue

        try:
            content = path.read_text(encoding='utf-8')
        except OSError, UnicodeDecodeError:
            continue

        # Check SEC001: Leaked home paths or drive mounts
        for line_idx, line in enumerate(content.splitlines(), start=1):
            if _HOME_PATTERN.search(line) or _DRIVE_PATTERN.search(line):
                report.add(
                    code=ErrorCode.SEC001,
                    message='Leaked absolute home path or Google Drive mount found in repository file.',
                    severity=Severity.ERROR,
                    path=path,
                    line=line_idx,
                    suggestion='Replace hardcoded machine paths with ${PLUGIN_ROOT} or relative paths.',
                )
                break

            # Check SEC002: Leaked authentication tokens
            for token_re in _TOKEN_PATTERNS:
                if token_re.search(line):
                    report.add(
                        code=ErrorCode.SEC002,
                        message='Leaked plaintext authentication token or API key found in repository file.',
                        severity=Severity.ERROR,
                        path=path,
                        line=line_idx,
                        suggestion='Store authentication tokens in OS Keyring and reference via variable placeholders.',
                    )
                    break
