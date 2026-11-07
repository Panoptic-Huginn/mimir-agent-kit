"""Data models and report structures for AntiGravity 2.29.0 validation."""

from __future__ import annotations

import enum
import json
from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING
from typing import Any


if TYPE_CHECKING:
    from pathlib import Path

    from scripts.validation.codes import ErrorCode


class Severity(enum.StrEnum):
    """Validation issue severity level."""

    ERROR = 'ERROR'
    WARNING = 'WARNING'


@dataclass(frozen=True)
class ValidationIssue:
    """Represents a single validation issue found during repository audit.

    Attributes:
        code: Canonical error code (e.g., ErrorCode.SKL001).
        message: Descriptive explanation of the issue.
        severity: Issue severity (ERROR or WARNING).
        path: Path to the affected file or directory.
        line: Optional 1-based line number where the issue occurs.
        suggestion: Optional actionable fix suggestion.
    """

    code: ErrorCode | str
    message: str
    severity: Severity
    path: Path | str
    line: int | None = None
    suggestion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert issue to a JSON-serializable dictionary.

        Returns:
            Dictionary containing issue attributes.
        """
        return {
            'code': str(self.code),
            'message': self.message,
            'severity': self.severity.value,
            'path': str(self.path),
            'line': self.line,
            'suggestion': self.suggestion,
        }


@dataclass
class ValidationReport:
    """Aggregate report containing all issues collected across validators.

    Attributes:
        strict: When True, warnings are treated as failures.
        issues: List of discovered ValidationIssue objects.
    """

    strict: bool = False
    issues: list[ValidationIssue] = field(default_factory=list)

    def add(
        self,
        code: ErrorCode | str,
        message: str,
        severity: Severity,
        path: Path | str,
        line: int | None = None,
        suggestion: str | None = None,
    ) -> None:
        """Construct and append a ValidationIssue to the report.

        Args:
            code: Canonical error code.
            message: Descriptive message.
            severity: Severity level (ERROR or WARNING).
            path: Target file or directory path.
            line: Optional line number.
            suggestion: Optional remediation advice.
        """
        self.issues.append(
            ValidationIssue(
                code=code,
                message=message,
                severity=severity,
                path=path,
                line=line,
                suggestion=suggestion,
            )
        )

    def add_issue(self, issue: ValidationIssue) -> None:
        """Append an existing ValidationIssue to the report.

        Args:
            issue: ValidationIssue to append.
        """
        self.issues.append(issue)

    @property
    def error_count(self) -> int:
        """Total number of issues with ERROR severity."""
        return sum(1 for i in self.issues if i.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        """Total number of issues with WARNING severity."""
        return sum(1 for i in self.issues if i.severity == Severity.WARNING)

    @property
    def is_clean(self) -> bool:
        """Check whether the validation passed.

        Returns:
            True if 0 errors (or 0 issues in strict mode), False otherwise.
        """
        if self.strict:
            return len(self.issues) == 0
        return self.error_count == 0

    def to_dict(self) -> dict[str, Any]:
        """Convert report to a JSON-serializable dictionary.

        Returns:
            Dictionary with report summary and issue list.
        """
        return {
            'passed': self.is_clean,
            'strict': self.strict,
            'errorCount': self.error_count,
            'warningCount': self.warning_count,
            'totalIssues': len(self.issues),
            'issues': [i.to_dict() for i in self.issues],
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize report to a formatted JSON string.

        Args:
            indent: JSON indentation spaces.

        Returns:
            Formatted JSON string.
        """
        return json.dumps(self.to_dict(), indent=indent)
