"""Validator for AntiGravity 2.29.0 plugin manifest (plugin.json) and discovery configs."""

import json
import re
from typing import TYPE_CHECKING

from scripts.validation.codes import ErrorCode
from scripts.validation.models import Severity


if TYPE_CHECKING:
    from pathlib import Path

    from scripts.validation.models import ValidationReport


PLUGIN_NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)

COMMON_SPDX_LICENSES = frozenset({
    "0BSD",
    "AFL-3.0",
    "AGPL-3.0-only",
    "AGPL-3.0-or-later",
    "Apache-2.0",
    "Artistic-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "BSD-3-Clause-Clear",
    "BSD-4-Clause",
    "BSL-1.0",
    "CC0-1.0",
    "CC-BY-4.0",
    "CC-BY-SA-4.0",
    "EPL-1.0",
    "EPL-2.0",
    "EUPL-1.2",
    "GPL-2.0-only",
    "GPL-2.0-or-later",
    "GPL-3.0-only",
    "GPL-3.0-or-later",
    "ISC",
    "LGPL-2.1-only",
    "LGPL-2.1-or-later",
    "LGPL-3.0-only",
    "LGPL-3.0-or-later",
    "MIT",
    "MPL-2.0",
    "MS-PL",
    "MS-RL",
    "PostgreSQL",
    "Python-2.0",
    "UPL-1.0",
    "Unlicense",
    "WTFPL",
    "Zlib",
})


def validate_plugin_manifest_file(
    plugin_file: Path,
    repo_root: Path,
    report: ValidationReport,
) -> None:
    """Validate plugin.json file.

    Args:
        plugin_file: Path to plugin.json.
        repo_root: Root of repository.
        report: Aggregating ValidationReport.
    """
    try:
        content = plugin_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        report.add(
            code=ErrorCode.PLG001,
            message=f"Failed to read plugin.json: {exc}",
            severity=Severity.ERROR,
            path=plugin_file,
        )
        return

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        report.add(
            code=ErrorCode.PLG001,
            message=f"Malformed JSON in plugin.json: {exc}",
            severity=Severity.ERROR,
            path=plugin_file,
            line=exc.lineno,
            suggestion="Ensure plugin.json contains valid JSON syntax.",
        )
        return

    if not isinstance(data, dict):
        report.add(
            code=ErrorCode.PLG001,
            message="Root of plugin.json must be a JSON object.",
            severity=Severity.ERROR,
            path=plugin_file,
        )
        return

    # Check name (PLG002)
    name = data.get("name")
    if not isinstance(name, str) or not PLUGIN_NAME_PATTERN.match(name):
        report.add(
            code=ErrorCode.PLG002,
            message=f"Plugin name '{name}' is invalid. Must match ^[a-z0-9]+(-[a-z0-9]+)*$.",
            severity=Severity.ERROR,
            path=plugin_file,
            suggestion="Use a lowercase hyphenated plugin name.",
        )

    # Check version (PLG003)
    version = data.get("version")
    if not isinstance(version, str) or not SEMVER_PATTERN.match(version):
        report.add(
            code=ErrorCode.PLG003,
            message=f"Plugin version '{version}' violates Semantic Versioning (X.Y.Z).",
            severity=Severity.ERROR,
            path=plugin_file,
            suggestion="Specify version in standard SemVer format (e.g. 1.0.0).",
        )

    # Check logo (PLG004)
    logo = data.get("logo")
    if isinstance(logo, str) and not logo.startswith(("http://", "https://")):
        logo_path = (repo_root / logo).resolve()
        if not logo_path.is_file():
            report.add(
                code=ErrorCode.PLG004,
                message=f"Plugin logo file path does not exist on disk: '{logo}'",
                severity=Severity.ERROR,
                path=plugin_file,
                suggestion=f"Ensure logo asset exists at {logo_path}.",
            )

    # Check license (PLG005)
    license_val = data.get("license")
    if not isinstance(license_val, str) or license_val not in COMMON_SPDX_LICENSES:
        report.add(
            code=ErrorCode.PLG005,
            message=f"Plugin license '{license_val}' is not a recognized valid SPDX identifier.",
            severity=Severity.ERROR,
            path=plugin_file,
            suggestion="Use a valid SPDX license identifier like Apache-2.0, MIT, BSD-3-Clause.",
        )


def validate_discovery_configs(
    repo_root: Path,
    report: ValidationReport,
) -> None:
    """Validate .agents/skills.json and .agents/rules.json discovery configurations.

    Args:
        repo_root: Root of repository.
        report: Aggregating ValidationReport.
    """
    agents_dir = repo_root / ".agents"
    skills_json = agents_dir / "skills.json"
    rules_json = agents_dir / "rules.json"

    for disc_file, name in ((skills_json, "skills.json"), (rules_json, "rules.json")):
        if not disc_file.is_file():
            report.add(
                code=ErrorCode.PLG006,
                message=f"Missing required discovery configuration file .agents/{name}.",
                severity=Severity.ERROR,
                path=disc_file,
                suggestion=f"Create .agents/{name} with entry mapping to corresponding folder.",
            )
            continue

        try:
            content = disc_file.read_text(encoding="utf-8")
            parsed = json.loads(content)
            if (
                not isinstance(parsed, dict)
                or "entries" not in parsed
                or not isinstance(parsed["entries"], list)
            ):
                report.add(
                    code=ErrorCode.PLG006,
                    message=f".agents/{name} must be a JSON object containing an 'entries' list.",
                    severity=Severity.ERROR,
                    path=disc_file,
                )
        except (OSError, json.JSONDecodeError) as exc:
            report.add(
                code=ErrorCode.PLG006,
                message=f"Failed to parse .agents/{name}: {exc}",
                severity=Severity.ERROR,
                path=disc_file,
            )


def validate_plugin(
    repo_root: Path,
    report: ValidationReport,
) -> None:
    """Validate plugin.json and discovery configs.

    Args:
        repo_root: Root path of the repository.
        report: Aggregating ValidationReport.
    """
    plugin_file = repo_root / "plugin.json"
    if plugin_file.is_file():
        validate_plugin_manifest_file(plugin_file, repo_root, report)
    validate_discovery_configs(repo_root, report)
