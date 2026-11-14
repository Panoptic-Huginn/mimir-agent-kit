"""Opaque-box E2E test suite for the marimo-pair AntiGravity 2.29.0+ skill.

Validates all requirements and interface contracts from ORIGINAL_REQUEST.md,
PROJECT.md, and ARCHITECTURAL_DECISION.md across:
- Tier 1: Feature Coverage & Structure (15 tests)
- Tier 2: Boundary & Corner Cases (15 tests)
- Tier 3: Cross-Feature Integration (8 tests)
- Tier 4: Real-World Antigravity Protocol Semantics & Live Subprocess Streaming
Total: 106 test items covering static contracts, code mode transactions, and live subprocess execution.
"""

import ast
import http.server
import json
import math
import os
import re
import shutil
import subprocess
import textwrap
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

from scripts.validation.codes import ErrorCode
from scripts.validation.models import Severity
from tests.e2e.conftest import (
    ALLOWED_SKILL_SUBDIRECTORIES,
    MAX_FILE_BYTES,
    MIN_SKILL_DESCRIPTION_LENGTH,
    SKILL_NAME_PATTERN,
    SKILLS_DIR,
    oracle_validate_mcp_config,
    oracle_validate_skill,
    split_skill_frontmatter,
)
from tests.test_plugin_integrity import EXPECTED_SKILLS, MAX_PLUGIN_SKILL_BODY_BYTES


if TYPE_CHECKING:
    from pathlib import Path


SKILL_DIR = SKILLS_DIR / "marimo-pair"
SKILL_MD = SKILL_DIR / "SKILL.md"
SCRIPTS_DIR = SKILL_DIR / "scripts"
REFERENCES_DIR = SKILL_DIR / "references"
MARIMO_PRO_DIR = SKILLS_DIR / "marimo-pro"
MARIMO_PRO_MD = MARIMO_PRO_DIR / "SKILL.md"
BASH_BIN = shutil.which("bash") or "/bin/bash"

REQUIRED_SKILL_FILES: list[str] = [
    "SKILL.md",
    "scripts/discover-servers.sh",
    "scripts/execute-code.sh",
    "references/code_mode_api.md",
    "references/mcp_bridge_configuration.md",
    "references/session_targeting_troubleshooting.md",
]

MCP_TOOLS_EXPECTED: list[str] = [
    "GetMarimoRules",
    "GetActiveNotebooks",
    "GetLightweightCellMap",
    "GetCellRuntimeData",
    "GetCellOutputs",
    "GetCellDependencyGraph",
    "GetTablesAndVariables",
    "GetDatabaseTables",
    "GetNotebookErrors",
    "LintNotebook",
]


# ==============================================================================
# Tier 1: Feature Coverage & Structure Tests
# ==============================================================================


def test_t1_f1_skill_directory_exists() -> None:
    """Tier 1: Verify skills/marimo-pair directory exists and is a directory."""
    assert SKILL_DIR.exists(), f"Directory not found: '{SKILL_DIR}'"
    assert SKILL_DIR.is_dir(), f"'{SKILL_DIR}' is not a directory"


def test_t1_f2_skill_md_exists() -> None:
    """Tier 1: Verify skills/marimo-pair/SKILL.md exists and is a regular file."""
    assert SKILL_MD.exists(), f"File not found: '{SKILL_MD}'"
    assert SKILL_MD.is_file(), f"'{SKILL_MD}' is not a regular file"


def test_t1_f3_skill_frontmatter_framing() -> None:
    """Tier 1: Verify SKILL.md begins with line 1 delimiter and has valid YAML frontmatter."""
    content = SKILL_MD.read_text(encoding="utf-8")
    assert content.startswith("---\n"), (
        "SKILL.md must begin with YAML frontmatter delimiter '---' on line 1"
    )
    parts = content.split("---\n", 2)
    assert len(parts) >= 3, "SKILL.md missing closing YAML frontmatter delimiter"
    frontmatter, body = split_skill_frontmatter(content)
    assert isinstance(frontmatter, dict), "Parsed frontmatter must be a dictionary"
    assert len(body.strip()) > 0, "SKILL.md body must not be empty"


def test_t1_f4_skill_frontmatter_name() -> None:
    """Tier 1: Verify frontmatter name matches 'marimo-pair' and conforms to regex."""
    content = SKILL_MD.read_text(encoding="utf-8")
    frontmatter, _ = split_skill_frontmatter(content)
    name = frontmatter.get("name")
    assert name == "marimo-pair", f"Expected skill name 'marimo-pair', got '{name}'"
    assert SKILL_NAME_PATTERN.match(str(name)), (
        f"Skill name '{name}' violates naming regex"
    )


def test_t1_f5_skill_frontmatter_description() -> None:
    """Tier 1: Verify frontmatter description is >= 20 characters and contains domain keywords."""
    content = SKILL_MD.read_text(encoding="utf-8")
    frontmatter, _ = split_skill_frontmatter(content)
    desc = frontmatter.get("description", "")
    assert isinstance(desc, str), "Frontmatter description must be a string"
    assert len(desc.strip()) >= MIN_SKILL_DESCRIPTION_LENGTH, (
        f"Description length ({len(desc)}) < {MIN_SKILL_DESCRIPTION_LENGTH}"
    )
    assert "marimo" in desc.lower(), "Description must reference 'marimo'"
    assert any(
        k in desc.lower()
        for k in ["pair", "reactive", "scratchpad", "kernel", "interactive"]
    ), "Description must highlight live pairing or interactive notebook capabilities"


def test_t1_f6_skill_frontmatter_metadata() -> None:
    """Tier 1: Verify frontmatter metadata contains version and publisher."""
    content = SKILL_MD.read_text(encoding="utf-8")
    frontmatter, _ = split_skill_frontmatter(content)
    metadata = frontmatter.get("metadata")
    assert isinstance(metadata, dict), "Frontmatter missing 'metadata' dictionary"
    assert "version" in metadata, "Metadata missing 'version'"
    assert "publisher" in metadata, "Metadata missing 'publisher'"


def test_t1_f7_skill_body_bytes_within_limit() -> None:
    """Tier 1: Verify SKILL.md body size is strictly <= 24,000 UTF-8 bytes cap."""
    content = SKILL_MD.read_text(encoding="utf-8")
    _, body = split_skill_frontmatter(content)
    body_bytes = len(body.encode("utf-8"))
    assert body_bytes <= MAX_PLUGIN_SKILL_BODY_BYTES, (
        f"SKILL.md body ({body_bytes} bytes) exceeds limit of {MAX_PLUGIN_SKILL_BODY_BYTES} bytes"
    )
    assert body_bytes <= MAX_FILE_BYTES, (
        f"SKILL.md body ({body_bytes} bytes) exceeds limit of {MAX_FILE_BYTES} bytes"
    )


def test_t1_f8_allowed_subdirectories() -> None:
    """Tier 1: Verify subdirectories in skills/marimo-pair are strictly within allowlist."""
    discovered = {p.name for p in SKILL_DIR.iterdir() if p.is_dir()}
    disallowed = discovered - ALLOWED_SKILL_SUBDIRECTORIES
    assert not disallowed, f"Disallowed subdirectories discovered: {disallowed}"


def test_t1_f9_subdirectories_exact_structure() -> None:
    """Tier 1: Verify skills/marimo-pair contains exactly 'scripts' and 'references' subdirectories."""
    discovered = {p.name for p in SKILL_DIR.iterdir() if p.is_dir()}
    assert discovered == {"scripts", "references"}, (
        f"Unexpected subdirectories: {discovered}"
    )


def test_t1_f10_scripts_directory_contents() -> None:
    """Tier 1: Verify scripts/ directory contains discover-servers.sh and execute-code.sh."""
    assert SCRIPTS_DIR.is_dir(), f"'{SCRIPTS_DIR}' is not a directory"
    assert (SCRIPTS_DIR / "discover-servers.sh").is_file()
    assert (SCRIPTS_DIR / "execute-code.sh").is_file()


def test_t1_f11_references_directory_contents() -> None:
    """Tier 1: Verify references/ directory contains all 3 required reference manuals."""
    assert REFERENCES_DIR.is_dir(), f"'{REFERENCES_DIR}' is not a directory"
    expected_manuals = [
        "code_mode_api.md",
        "mcp_bridge_configuration.md",
        "session_targeting_troubleshooting.md",
    ]
    for manual in expected_manuals:
        target = REFERENCES_DIR / manual
        assert target.is_file(), (
            f"Missing required reference manual '{manual}' in references/"
        )


@pytest.mark.parametrize("rel_path", REQUIRED_SKILL_FILES)
def test_t1_f12_all_required_files_exist_and_non_empty(rel_path: str) -> None:
    """Tier 1: Verify every required skill file exists and has non-zero byte size.

    Args:
        rel_path: Relative file path under skills/marimo-pair/.
    """
    target = SKILL_DIR / rel_path
    assert target.is_file(), f"Required file '{rel_path}' does not exist"
    assert target.stat().st_size > 0, f"Required file '{rel_path}' is empty"


@pytest.mark.parametrize(
    "manual_name",
    [
        "code_mode_api.md",
        "mcp_bridge_configuration.md",
        "session_targeting_troubleshooting.md",
    ],
)
def test_t1_f13_reference_manuals_have_level1_heading(manual_name: str) -> None:
    """Tier 1: Verify each reference manual begins with a level 1 markdown heading.

    Args:
        manual_name: Name of the reference manual file.
    """
    target = REFERENCES_DIR / manual_name
    lines = [
        line.strip()
        for line in target.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert lines, f"'{manual_name}' has no non-empty lines"
    assert lines[0].startswith("# "), (
        f"'{manual_name}' does not begin with level 1 heading '# '"
    )


@pytest.mark.parametrize("script_name", ["discover-servers.sh", "execute-code.sh"])
def test_t1_f14_scripts_have_bash_shebang(script_name: str) -> None:
    """Tier 1: Verify bundled scripts start with an appropriate bash shebang.

    Args:
        script_name: Name of the script to inspect.
    """
    target = SCRIPTS_DIR / script_name
    first_line = target.read_text(encoding="utf-8").splitlines()[0]
    assert first_line in {"#!/usr/bin/env bash", "#!/bin/bash"}, (
        f"Invalid shebang '{first_line}' in '{script_name}'"
    )


@pytest.mark.parametrize("script_name", ["discover-servers.sh", "execute-code.sh"])
def test_t1_f15_scripts_have_strict_mode(script_name: str) -> None:
    """Tier 1: Verify bundled scripts set strict error handling flags (set -euo pipefail).

    Args:
        script_name: Name of the script to inspect.
    """
    target = SCRIPTS_DIR / script_name
    content = target.read_text(encoding="utf-8")
    assert "set -euo pipefail" in content, (
        f"Script '{script_name}' missing 'set -euo pipefail'"
    )


# ==============================================================================
# Tier 2: Boundary & Corner Cases Tests
# ==============================================================================


@pytest.mark.parametrize("script_name", ["discover-servers.sh", "execute-code.sh"])
def test_t2_b01_scripts_executable_permissions(script_name: str) -> None:
    """Tier 2: Verify shell scripts have executable permissions (os.X_OK) set.

    Args:
        script_name: Name of the script to verify.
    """
    target = SCRIPTS_DIR / script_name
    assert os.access(target, os.X_OK), (
        f"Script '{target}' is not executable (missing chmod +x)"
    )


def test_t2_b02_markdown_relative_links_resolve() -> None:
    """Tier 2: Verify every relative markdown link in SKILL.md and references/ resolves cleanly."""
    link_pattern = re.compile(r"\[([^\]]*)\]\((?!https?://)([^)#\s]+)(?:#[^)]*)?\)")
    files_to_check = [SKILL_MD, *list(REFERENCES_DIR.glob("*.md"))]
    checked_count = 0

    for md_file in files_to_check:
        content = md_file.read_text(encoding="utf-8")
        for match in link_pattern.finditer(content):
            target_rel = match.group(2)
            target_path = (md_file.parent / target_rel).resolve()
            assert target_path.exists(), (
                f"Broken relative link in '{md_file.name}': target '{target_rel}' resolved to '{target_path}' which does not exist"
            )
            assert target_path.is_file(), f"Target '{target_path}' is not a file"
            checked_count += 1

    assert checked_count >= 5, (
        f"Expected at least 5 relative links verified, found {checked_count}"
    )


@pytest.mark.parametrize("script_name", ["discover-servers.sh", "execute-code.sh"])
def test_t2_b03_no_trailing_whitespace_in_scripts(script_name: str) -> None:
    """Tier 2: Verify bundled shell scripts contain zero trailing whitespace on any line.

    Args:
        script_name: Name of the script to inspect.
    """
    target = SCRIPTS_DIR / script_name
    for idx, line in enumerate(target.read_text(encoding="utf-8").splitlines(), 1):
        assert line == line.rstrip(), (
            f"Trailing whitespace in '{script_name}' on line {idx}: {line!r}"
        )


@pytest.mark.parametrize(
    "md_rel_path",
    [
        "SKILL.md",
        "references/code_mode_api.md",
        "references/mcp_bridge_configuration.md",
        "references/session_targeting_troubleshooting.md",
    ],
)
def test_t2_b04_markdown_linebreaks_conformance(md_rel_path: str) -> None:
    """Tier 2: Verify markdown files adhere to pre-commit linebreak hygiene.

    Lines with trailing whitespace must strictly use two spaces ('  ') for markdown hard
    line breaks as permitted by pre-commit trailing-whitespace --markdown-linebreak-ext=md.
    No tabs or arbitrary trailing whitespace are allowed.

    Args:
        md_rel_path: Relative path to the markdown file.
    """
    target = SKILL_DIR / md_rel_path
    for idx, line in enumerate(target.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.rstrip()
        trailing = line[len(stripped) :]
        if trailing:
            assert trailing == "  ", (
                f"Invalid trailing whitespace in '{md_rel_path}' on line {idx}: {trailing!r} (expected exact '  ')"
            )


def test_t2_b05_all_skill_files_utf8_decodable() -> None:
    """Tier 2: Verify every file in skills/marimo-pair can be decoded strictly as UTF-8."""
    for path in SKILL_DIR.rglob("*"):
        if path.is_file():
            try:
                path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                pytest.fail(f"File '{path}' is not valid UTF-8: {exc}")


def test_t2_b06_all_skill_files_unix_line_endings() -> None:
    """Tier 2: Verify no files in skills/marimo-pair contain Windows CRLF line endings."""
    for path in SKILL_DIR.rglob("*"):
        if path.is_file():
            raw_bytes = path.read_bytes()
            assert b"\r\n" not in raw_bytes, (
                f"File '{path}' contains Windows CRLF line endings"
            )


def test_t2_b07_no_forbidden_subdirectory_names() -> None:
    """Tier 2: Verify no forbidden subdirectories exist (e.g. singular 'reference', 'tests', 'src')."""
    forbidden_names = {"reference", "test", "tests", "src", "docs", "lib", "build"}
    existing_dirs = {p.name for p in SKILL_DIR.iterdir() if p.is_dir()}
    violations = existing_dirs.intersection(forbidden_names)
    assert not violations, f"Forbidden subdirectory names discovered: {violations}"


def test_t2_b08_oracle_skill_validator_passes() -> None:
    """Tier 2: Verify authoritative oracle validator produces zero ERROR issues for marimo-pair."""
    issues = oracle_validate_skill(SKILL_DIR)
    errors = [issue for issue in issues if issue.severity == Severity.ERROR]
    assert not errors, f"Oracle validator reported errors: {errors}"


def test_t2_b09_boundary_description_under_20_chars_rejected(tmp_path: Path) -> None:
    """Tier 2 Boundary: Oracle validator rejects description of 19 characters (< 20 minimum).

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()
    text = "---\nname: test-skill\ndescription: 1234567890123456789\n---\nBody\n"
    (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")
    issues = oracle_validate_skill(skill_dir)
    assert any(i.code == ErrorCode.SKL004 for i in issues)


def test_t2_b10_boundary_description_20_chars_accepted(tmp_path: Path) -> None:
    """Tier 2 Boundary: Oracle validator accepts description of exactly 20 characters.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()
    text = '---\nname: test-skill\ndescription: "Twenty chars exactly."\n---\nBody\n'
    (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")
    issues = oracle_validate_skill(skill_dir)
    assert not any(i.code == ErrorCode.SKL004 for i in issues)


def test_t2_b11_boundary_name_mismatch_rejected(tmp_path: Path) -> None:
    """Tier 2 Boundary: Oracle validator rejects skill name that does not match directory name.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    skill_dir = tmp_path / "actual-name"
    skill_dir.mkdir()
    text = "---\nname: different-name\ndescription: Valid description string with 20 chars.\n---\nBody\n"
    (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")
    issues = oracle_validate_skill(skill_dir)
    assert any(i.code == ErrorCode.SKL003 for i in issues)


def test_t2_b12_boundary_disallowed_singular_reference_rejected(tmp_path: Path) -> None:
    """Tier 2 Boundary: Oracle validator rejects singular 'reference' directory with SKL006.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    skill_dir = tmp_path / "ref-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: ref-skill\ndescription: Valid description string with 20 chars.\n---\nBody\n",
        encoding="utf-8",
    )
    (skill_dir / "reference").mkdir()
    issues = oracle_validate_skill(skill_dir)
    assert any(i.code == ErrorCode.SKL006 for i in issues)


def test_t2_b13_boundary_broken_relative_link_detected(tmp_path: Path) -> None:
    """Tier 2 Boundary: Verify relative link validator catches nonexistent targets.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    doc_path = tmp_path / "guide.md"
    doc_path.write_text("[Dangling Link](./missing_target.md)\n", encoding="utf-8")
    link_re = re.compile(r"\[([^\]]*)\]\((?!https?://)([^)#\s]+)(?:#[^)]*)?\)")
    matches = list(link_re.finditer(doc_path.read_text(encoding="utf-8")))
    assert len(matches) == 1
    rel = matches[0].group(2)
    resolved = (doc_path.parent / rel).resolve()
    assert not resolved.exists(), "Target was expected to not exist"


def test_t2_b14_boundary_individual_file_sizes_under_max_limit() -> None:
    """Tier 2 Boundary: Verify all markdown and script files in marimo-pair are <= 24,000 bytes."""
    for path in SKILL_DIR.rglob("*"):
        if path.is_file():
            size = path.stat().st_size
            assert size <= MAX_FILE_BYTES, (
                f"File '{path}' size ({size} bytes) exceeds {MAX_FILE_BYTES} bytes"
            )


def test_t2_b15_references_python_code_blocks_ast_syntax_valid() -> None:
    """Tier 2: Parse all fenced Python code blocks in references/*.md via ast.parse for syntax validity.

    Guarantees that every code snippet in the reference manuals is syntactically valid Python
    and does not introduce regression syntax errors (such as type annotations in call expressions).
    """
    md_files = sorted(REFERENCES_DIR.glob("*.md"))
    assert md_files, f"No reference markdown files found in '{REFERENCES_DIR}'"

    total_blocks_checked = 0

    for md_file in md_files:
        lines = md_file.read_text(encoding="utf-8").splitlines()
        in_code_block = False
        code_block_lines: list[str] = []
        block_start_line = 0

        for line_no, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not in_code_block:
                if stripped.startswith("```") and stripped[3:].strip().lower() in {
                    "python",
                    "py",
                }:
                    in_code_block = True
                    block_start_line = line_no
                    code_block_lines = []
            elif stripped == "```":
                in_code_block = False
                total_blocks_checked += 1
                raw_code = "\n".join(code_block_lines)
                dedented_code = textwrap.dedent(raw_code)
                try:
                    ast.parse(dedented_code, filename=str(md_file))
                except SyntaxError as exc:
                    pytest.fail(
                        f"Python SyntaxError in '{md_file.name}' starting at line {block_start_line}: {exc.msg} (line {exc.lineno}):\n{exc.text}"
                    )
                code_block_lines = []
            else:
                code_block_lines.append(line)

    assert total_blocks_checked >= 15, (
        f"Expected at least 15 Python code blocks to be validated across references, found {total_blocks_checked}"
    )


# ==============================================================================
# Tier 3: Cross-Feature Integration Tests
# ==============================================================================


def test_t3_cross_marimo_pro_related_skills_contains_marimo_pair() -> None:
    """Tier 3: Verify skills/marimo-pro/SKILL.md references /marimo-pair under Related Skills."""
    content = MARIMO_PRO_MD.read_text(encoding="utf-8")
    assert "/marimo-pair" in content, (
        "marimo-pro/SKILL.md missing reference to '/marimo-pair'"
    )
    assert re.search(r"^\s*-\s*\*\*`?/marimo-pair`?\*\*", content, re.MULTILINE), (
        "marimo-pro/SKILL.md missing formatted bullet point for '/marimo-pair' under Related Skills"
    )


def test_t3_cross_marimo_pro_runtime_source_of_truth_guardrail() -> None:
    """Tier 3: Verify skills/marimo-pro/SKILL.md contains Runtime Source of Truth Guardrail."""
    content = MARIMO_PRO_MD.read_text(encoding="utf-8")
    assert "Runtime Source of Truth Guardrail" in content
    assert "CRITICAL RUNTIME INVARIANT" in content
    assert "replace_file_content" in content
    assert "write_to_file" in content
    assert "/marimo-pair" in content


def test_t3_cross_marimo_pro_operational_boundaries_demarcated() -> None:
    """Tier 3: Verify marimo-pro demarcates static authoring vs live kernel pairing."""
    content = MARIMO_PRO_MD.read_text(encoding="utf-8")
    assert "Do not use this skill when" in content
    assert "Interactively pairing with a live, running marimo kernel" in content


def test_t3_cross_marimo_pro_body_size_preserved_under_limit() -> None:
    """Tier 3: Verify skills/marimo-pro/SKILL.md body size remains <= 24,000 bytes after pairing edits."""
    content = MARIMO_PRO_MD.read_text(encoding="utf-8")
    _, body = split_skill_frontmatter(content)
    body_bytes = len(body.encode("utf-8"))
    assert body_bytes <= MAX_PLUGIN_SKILL_BODY_BYTES, (
        f"marimo-pro SKILL.md body ({body_bytes} bytes) exceeds limit of {MAX_PLUGIN_SKILL_BODY_BYTES} bytes"
    )


def test_t3_cross_plugin_integrity_expected_skills_contains_marimo_pair() -> None:
    """Tier 3: Verify tests/test_plugin_integrity.py EXPECTED_SKILLS set includes 'marimo-pair'."""
    assert "marimo-pair" in EXPECTED_SKILLS, (
        "'marimo-pair' not registered in EXPECTED_SKILLS"
    )


def test_t3_cross_marimo_pair_related_skills_cross_references() -> None:
    """Tier 3: Verify skills/marimo-pair/SKILL.md cross-references /marimo-pro and related skills."""
    content = SKILL_MD.read_text(encoding="utf-8")
    assert "/marimo-pro" in content
    assert "/python-pro" in content
    assert "/github-flow-lifecycle" in content


def test_t3_cross_marimo_pair_operational_boundaries_demarcated() -> None:
    """Tier 3: Verify skills/marimo-pair/SKILL.md instructs agents when to use /marimo-pro instead."""
    content = SKILL_MD.read_text(encoding="utf-8")
    assert "Do not use this skill when" in content
    assert "/marimo-pro" in content
    assert "from scratch" in content


def test_t3_cross_marimo_pair_runtime_cardinal_rule_prominence() -> None:
    """Tier 3: Verify skills/marimo-pair/SKILL.md features the active kernel cardinal rule."""
    content = SKILL_MD.read_text(encoding="utf-8")
    assert "Operational Cardinal Rule: Active Kernel is the Source of Truth" in content
    assert "CRITICAL RUNTIME INVARIANT" in content
    assert "marimo._code_mode" in content


# ==============================================================================
# Tier 4: Real-World Antigravity Protocol Semantics Tests
# ==============================================================================


def test_t4_semantics_discover_servers_xdg_state_directory() -> None:
    """Tier 4: Verify discover-servers.sh scans XDG_STATE_HOME and fallback state path."""
    content = (SCRIPTS_DIR / "discover-servers.sh").read_text(encoding="utf-8")
    assert "XDG_STATE_HOME" in content
    assert "marimo/servers" in content
    assert ".local/state" in content


def test_t4_semantics_discover_servers_cli_flags() -> None:
    """Tier 4: Verify discover-servers.sh supports all specified CLI options."""
    content = (SCRIPTS_DIR / "discover-servers.sh").read_text(encoding="utf-8")
    for flag in ["--json", "--text", "--clean-stale", "--help"]:
        assert flag in content, f"discover-servers.sh missing flag option '{flag}'"


def test_t4_semantics_discover_servers_health_and_session_queries() -> None:
    """Tier 4: Verify discover-servers.sh queries /health and /api/sessions."""
    content = (SCRIPTS_DIR / "discover-servers.sh").read_text(encoding="utf-8")
    assert "/health" in content
    assert "/api/sessions" in content


def test_t4_semantics_discover_servers_dependency_validation() -> None:
    """Tier 4: Verify discover-servers.sh verifies curl and jq dependencies."""
    content = (SCRIPTS_DIR / "discover-servers.sh").read_text(encoding="utf-8")
    assert "curl" in content
    assert "jq" in content


def test_t4_semantics_execute_code_sse_and_endpoint() -> None:
    """Tier 4: Verify execute-code.sh targets /api/kernel/execute and handles SSE streaming."""
    content = (SCRIPTS_DIR / "execute-code.sh").read_text(encoding="utf-8")
    assert "/api/kernel/execute" in content
    # Script handles Server-Sent Events (SSE) streaming protocol
    assert "event:" in content
    assert "data:" in content
    assert "SSE" in content or "text/event-stream" in content


def test_t4_semantics_execute_code_cli_options() -> None:
    """Tier 4: Verify execute-code.sh supports all parameter flags."""
    content = (SCRIPTS_DIR / "execute-code.sh").read_text(encoding="utf-8")
    for flag in ["--url", "--session", "--file", "--token", "--code", "--code-file"]:
        assert flag in content, f"execute-code.sh missing flag option '{flag}'"


def test_t4_semantics_execute_code_stdin_dash_support() -> None:
    """Tier 4: Verify execute-code.sh supports reading code from standard input via '-'."""
    content = (SCRIPTS_DIR / "execute-code.sh").read_text(encoding="utf-8")
    assert (
        "READ_STDIN=true" in content or "'-'" in content or "stdin" in content.lower()
    )


def test_t4_semantics_code_mode_context_manager_surface() -> None:
    """Tier 4: Verify references/code_mode_api.md documents the full ctx API surface."""
    content = (REFERENCES_DIR / "code_mode_api.md").read_text(encoding="utf-8")
    required_symbols = [
        "cm.get_context()",
        "ctx.cells",
        "ctx.graph",
        "ctx.globals",
        "ctx.create_cell",
        "ctx.edit_cell",
        "ctx.delete_cell",
        "ctx.move_cell",
        "ctx.run_cell",
    ]
    for sym in required_symbols:
        assert sym in content, (
            f"code_mode_api.md missing documentation for symbol '{sym}'"
        )


def test_t4_semantics_code_mode_stale_cell_error() -> None:
    """Tier 4: Verify code mode API documents StaleCellError and skip_staleness_check."""
    content = (REFERENCES_DIR / "code_mode_api.md").read_text(encoding="utf-8")
    assert "StaleCellError" in content
    assert "skip_staleness_check" in content


def test_t4_semantics_code_mode_scratchpad_only_rule() -> None:
    """Tier 4: Verify code mode reference strictly mandates scratchpad-only imports."""
    content = (REFERENCES_DIR / "code_mode_api.md").read_text(encoding="utf-8")
    assert "Scratchpad-Only Import Rule" in content
    assert "import marimo._code_mode" in content


def test_t4_semantics_code_mode_ast_safety_gate_rules() -> None:
    """Tier 4: Verify code mode reference and SKILL.md document compile-time AST validation rules."""
    content = (REFERENCES_DIR / "code_mode_api.md").read_text(encoding="utf-8")
    skill_content = SKILL_MD.read_text(encoding="utf-8")
    assert (
        "Single Variable Definition Rule" in content
        or "Single Definition Rule" in skill_content
    )
    assert "Cycle Prevention" in content or "No Cycles" in skill_content
    assert "Delete-and-Create" in content
    assert "No Wildcard Imports" in skill_content


def test_t4_semantics_mcp_bridge_endpoint_and_transport() -> None:
    """Tier 4: Verify MCP reference specifies endpoint, port 2718, and SSE transport."""
    content = (REFERENCES_DIR / "mcp_bridge_configuration.md").read_text(
        encoding="utf-8"
    )
    assert "/mcp/server" in content
    assert "2718" in content
    assert "transport" in content
    assert "sse" in content


@pytest.mark.parametrize("tool_name", MCP_TOOLS_EXPECTED)
def test_t4_semantics_mcp_tools_specification(tool_name: str) -> None:
    """Tier 4: Verify all 10 MCP tools are specified in mcp_bridge_configuration.md.

    Args:
        tool_name: Name of the MCP tool to check.
    """
    content = (REFERENCES_DIR / "mcp_bridge_configuration.md").read_text(
        encoding="utf-8"
    )
    assert tool_name in content, (
        f"Tool '{tool_name}' missing from mcp_bridge_configuration.md"
    )


def test_t4_semantics_mcp_prompts_specification() -> None:
    """Tier 4: Verify MCP prompts ActiveNotebooks and ErrorsSummary are documented."""
    content = (REFERENCES_DIR / "mcp_bridge_configuration.md").read_text(
        encoding="utf-8"
    )
    assert "ActiveNotebooks" in content
    assert "ErrorsSummary" in content


def test_t4_semantics_session_targeting_no_token_auto_registration() -> None:
    """Tier 4: Verify session targeting manual details --no-token state file publishing."""
    content = (REFERENCES_DIR / "session_targeting_troubleshooting.md").read_text(
        encoding="utf-8"
    )
    assert "--no-token" in content
    assert "marimo/servers" in content
    assert "Local Server Registration" in content


def test_t4_semantics_session_targeting_sandbox_pep723() -> None:
    """Tier 4: Verify session targeting manual details PEP 723 sandboxing mechanics."""
    content = (REFERENCES_DIR / "session_targeting_troubleshooting.md").read_text(
        encoding="utf-8"
    )
    assert "--sandbox" in content
    assert "PEP 723" in content


def test_t4_semantics_troubleshooting_disk_edit_desync() -> None:
    """Tier 4: Verify troubleshooting guide documents disk-edit desync recovery."""
    content = (REFERENCES_DIR / "session_targeting_troubleshooting.md").read_text(
        encoding="utf-8"
    )
    assert "Disk-Edit Desynchronization" in content
    assert "overwritten" in content


def test_t4_semantics_simulation_sse_event_stream_parsing() -> None:
    """Tier 4 Simulation: Parse simulated Server-Sent Events stream as executed by execute-code.sh.

    Simulates the SSE response from POST /api/kernel/execute, parsing event boundaries,
    JSON data payloads, stdout chunks, cell execution statuses, and error envelopes.
    """
    raw_sse_stream = 'event: cell-op\ndata: {"cell_id": "c_init", "status": "running"}\n\nevent: stdout\ndata: {"cell_id": "c_init", "text": "Loading dataset...\\n"}\n\nevent: stdout\ndata: {"cell_id": "c_init", "text": "Dataset loaded: shape=(1000, 4)\\n"}\n\nevent: cell-op\ndata: {"cell_id": "c_init", "status": "completed", "duration_ms": 42.5}\n\n'

    events: list[dict[str, Any]] = []
    current_event_type = "message"
    current_data_lines: list[str] = []

    for line in raw_sse_stream.splitlines():
        if line.startswith("event: "):
            current_event_type = line[len("event: ") :].strip()
        elif line.startswith("data: "):
            current_data_lines.append(line[len("data: ") :])
        elif not line and current_data_lines:
            payload = json.loads("\n".join(current_data_lines))
            events.append({"event": current_event_type, "data": payload})
            current_event_type = "message"
            current_data_lines = []

    assert len(events) == 4
    assert events[0]["event"] == "cell-op"
    assert events[0]["data"]["status"] == "running"
    stdout_text = "".join(e["data"]["text"] for e in events if e["event"] == "stdout")
    assert "Loading dataset..." in stdout_text
    assert "shape=(1000, 4)" in stdout_text
    assert events[3]["data"]["status"] == "completed"
    assert math.isclose(float(events[3]["data"]["duration_ms"]), 42.5)


def test_t4_semantics_simulation_code_mode_transaction_lifecycle() -> None:
    """Tier 4 Simulation: Model transactional code mode staging, validation, and commit.

    Simulates cm.get_context() lifecycle:
    1. Stages new cell definitions in a proposed DAG.
    2. Enforces Single Definition Rule (rejects duplicate public variables).
    3. Detects cyclic dependencies between proposed cells.
    4. Automatically commits on valid exit or rolls back cleanly on exception.
    """

    class ProposedCell:
        def __init__(self, cell_id: str, code: str) -> None:
            self.cell_id = cell_id
            self.code = code
            self.defs: set[str] = set()
            self.refs: set[str] = set()
            self._parse_symbols()

        def _parse_symbols(self) -> None:
            tree = ast.parse(self.code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            self.defs.add(target.id)
                elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    self.refs.add(node.id)

    class TransactionalCodeModeContext:
        def __init__(self, existing_cells: dict[str, ProposedCell]) -> None:
            self.committed_cells = existing_cells
            self.staged_cells = dict(existing_cells)

        def create_cell(self, cell_id: str, code: str) -> str:
            self.staged_cells[cell_id] = ProposedCell(cell_id, code)
            return cell_id

        def commit(self) -> None:
            # 1. Enforce Single Definition Rule (public variables without leading _)
            all_defs: list[str] = []
            for cell in self.staged_cells.values():
                public_defs = [d for d in cell.defs if not d.startswith("_")]
                all_defs.extend(public_defs)
            duplicates = {d for d in all_defs if all_defs.count(d) > 1}
            if duplicates:
                raise ValueError(
                    f"MultipleDefinitionError: Variables defined multiple times: {duplicates}"
                )

            # 2. Cycle detection
            graph: dict[str, set[str]] = {cid: set() for cid in self.staged_cells}
            for cid, cell in self.staged_cells.items():
                for other_id, other_cell in self.staged_cells.items():
                    if cid != other_id and any(
                        ref in other_cell.defs for ref in cell.refs
                    ):
                        graph[cid].add(other_id)

            visited: set[str] = set()
            path: set[str] = set()

            def has_cycle(node: str) -> bool:
                visited.add(node)
                path.add(node)
                for neighbor in graph[node]:
                    if neighbor in path or (
                        neighbor not in visited and has_cycle(neighbor)
                    ):
                        return True
                path.remove(node)
                return False

            if any(has_cycle(node) for node in graph if node not in visited):
                raise ValueError(
                    "CycleError: Circular dependency detected in reactive cell graph"
                )

            # Commit successful
            self.committed_cells = dict(self.staged_cells)

    # Valid transaction
    base_cells = {"c1": ProposedCell("c1", "x = 10")}
    ctx = TransactionalCodeModeContext(base_cells)
    ctx.create_cell("c2", "y = x + 5")
    ctx.commit()
    assert "c2" in ctx.committed_cells
    assert ctx.committed_cells["c2"].defs == {"y"}

    # Collision transaction (MultipleDefinitionError)
    ctx_dup = TransactionalCodeModeContext(ctx.committed_cells)
    ctx_dup.create_cell("c3", "x = 99")  # Duplicate x!
    with pytest.raises(ValueError, match="MultipleDefinitionError"):
        ctx_dup.commit()
    # Prior state intact
    assert "c3" not in ctx_dup.committed_cells

    # Cycle transaction (CycleError)
    ctx_cyc = TransactionalCodeModeContext({"a": ProposedCell("a", "alpha = beta")})
    ctx_cyc.create_cell("b", "beta = alpha")  # Circular!
    with pytest.raises(ValueError, match="CycleError"):
        ctx_cyc.commit()
    assert "b" not in ctx_cyc.committed_cells


def test_t4_semantics_simulation_stale_cell_conflict_resolution() -> None:
    """Tier 4 Simulation: Model StaleCellError detection during concurrent edits.

    Validates that when a cell's in-memory generation hash diverges between
    the agent's inspection read and staged write, StaleCellError is raised to
    prevent silent UI overwrites unless explicitly skipped.
    """

    class StaleCellError(RuntimeError):
        """Raised when a cell source was modified after context acquisition."""

    @dataclass
    class CellState:
        cell_id: str
        code: str
        version: int

    live_kernel_cells: dict[str, CellState] = {
        "c100": CellState("c100", "df = load_data()", version=1),
    }

    def attempt_agent_edit(
        target_id: str,
        expected_version: int,
        new_code: str,
        skip_staleness_check: bool = False,
    ) -> None:
        current = live_kernel_cells[target_id]
        if not skip_staleness_check and current.version != expected_version:
            raise StaleCellError(
                f"Cell '{target_id}' was modified by user (expected v{expected_version}, found v{current.version})"
            )
        current.code = new_code
        current.version += 1

    # Agent acquires v1
    agent_expected_version = live_kernel_cells["c100"].version

    # User modifies cell in browser before agent edit commits -> version bumped to 2
    live_kernel_cells["c100"].code = "df = load_data_from_cache()"
    live_kernel_cells["c100"].version = 2

    # Agent edit attempt must fail with StaleCellError
    with pytest.raises(StaleCellError, match=r"Cell.*was modified by user"):
        attempt_agent_edit(
            target_id="c100",
            expected_version=agent_expected_version,
            new_code="df = load_data_with_polars()",
            skip_staleness_check=False,
        )

    # Forced overwrite bypasses check
    attempt_agent_edit(
        target_id="c100",
        expected_version=agent_expected_version,
        new_code="df = load_data_with_polars()",
        skip_staleness_check=True,
    )
    assert live_kernel_cells["c100"].code == "df = load_data_with_polars()"
    assert live_kernel_cells["c100"].version == 3


# ==============================================================================
# Tier 4: Subprocess Execution Tests for Bundled Shell Scripts
# ==============================================================================


def test_t4_subprocess_discover_servers_help() -> None:
    """Tier 4 Subprocess: discover-servers.sh --help exits with 0 and prints CLI help text."""
    script_path = SCRIPTS_DIR / "discover-servers.sh"
    result = subprocess.run(
        [BASH_BIN, str(script_path), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"Expected returncode 0, got {result.returncode}. Stderr: {result.stderr}"
    )
    assert "Usage: discover-servers.sh" in result.stdout
    assert "--json" in result.stdout
    assert "--text" in result.stdout
    assert "--clean-stale" in result.stdout


def test_t4_subprocess_discover_servers_json_empty_registry(tmp_path: Path) -> None:
    """Tier 4 Subprocess: discover-servers.sh --json in clean environment exits 0 with empty JSON list."""
    script_path = SCRIPTS_DIR / "discover-servers.sh"
    clean_env = {
        **os.environ,
        "XDG_STATE_HOME": str(tmp_path / "state"),
        "HOME": str(tmp_path / "home"),
    }
    result = subprocess.run(
        [BASH_BIN, str(script_path), "--json"],
        capture_output=True,
        text=True,
        env=clean_env,
        check=False,
    )
    assert result.returncode == 0, (
        f"Expected returncode 0, got {result.returncode}. Stderr: {result.stderr}"
    )
    assert "unbound variable" not in result.stderr
    parsed = json.loads(result.stdout)
    assert parsed == [], f"Expected empty list '[]', got: {parsed}"


def test_t4_subprocess_discover_servers_text_empty_registry(tmp_path: Path) -> None:
    """Tier 4 Subprocess: discover-servers.sh --text in clean environment exits 0 with friendly message."""
    script_path = SCRIPTS_DIR / "discover-servers.sh"
    clean_env = {
        **os.environ,
        "XDG_STATE_HOME": str(tmp_path / "state"),
        "HOME": str(tmp_path / "home"),
    }
    result = subprocess.run(
        [BASH_BIN, str(script_path), "--text"],
        capture_output=True,
        text=True,
        env=clean_env,
        check=False,
    )
    assert result.returncode == 0, (
        f"Expected returncode 0, got {result.returncode}. Stderr: {result.stderr}"
    )
    assert "unbound variable" not in result.stderr
    assert (
        "Found 0 active marimo server" in result.stdout
        or "No active marimo notebook servers found" in result.stdout
    ), f"Expected friendly 0-server message, got: {result.stdout}"


def test_t4_subprocess_execute_code_help() -> None:
    """Tier 4 Subprocess: execute-code.sh --help exits 0 and prints usage text."""
    script_path = SCRIPTS_DIR / "execute-code.sh"
    result = subprocess.run(
        [BASH_BIN, str(script_path), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"Expected returncode 0, got {result.returncode}. Stderr: {result.stderr}"
    )
    assert "Usage: execute-code.sh" in result.stdout
    assert "--url" in result.stdout
    assert "--session" in result.stdout
    assert "--code" in result.stdout
    assert "--code-file" in result.stdout


@pytest.mark.parametrize(
    ("args", "expected_code", "expected_stderr_snippet"),
    [
        ([], 2, "No Python code provided for execution"),
        (["-c", "print(1)", "--unknown-flag"], 2, "Unexpected option: --unknown-flag"),
        (["-c", "print(1)", "extra_arg"], 2, "Unexpected argument: extra_arg"),
        (
            ["--url", "http://127.0.0.1:59999", "-c", "print(1)"],
            1,
            "Could not retrieve sessions",
        ),
    ],
)
def test_t4_subprocess_execute_code_graceful_rejection(
    args: list[str],
    expected_code: int,
    expected_stderr_snippet: str,
) -> None:
    """Tier 4 Subprocess: execute-code.sh gracefully rejects invalid inputs with nonzero exit code."""
    script_path = SCRIPTS_DIR / "execute-code.sh"
    result = subprocess.run(
        [BASH_BIN, str(script_path), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == expected_code, (
        f"Expected exit code {expected_code}, got {result.returncode}. Stdout: {result.stdout!r}, Stderr: {result.stderr!r}"
    )
    assert "unbound variable" not in result.stderr
    assert expected_stderr_snippet in result.stderr


@pytest.mark.parametrize(
    "flag",
    ["--url", "--session", "--file", "--token", "-c", "--code", "--code-file"],
)
def test_t4_subprocess_execute_code_missing_option_arg(flag: str) -> None:
    """Tier 4 Subprocess: execute-code.sh exits with code 2 on missing option argument without unbound variable error."""
    script_path = SCRIPTS_DIR / "execute-code.sh"
    result = subprocess.run(
        [BASH_BIN, str(script_path), flag],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2, (
        f"Expected exit code 2, got {result.returncode}. Stderr: {result.stderr}"
    )
    assert "unbound variable" not in result.stderr
    assert f"Error: Option '{flag}' requires an argument." in result.stderr


@pytest.mark.parametrize(
    "option",
    ["--unknown-flag", "-z", "--bogus-option"],
)
def test_t4_subprocess_execute_code_unexpected_option(option: str) -> None:
    """Tier 4 Subprocess: execute-code.sh exits with code 2 when encountering an unexpected option."""
    script_path = SCRIPTS_DIR / "execute-code.sh"
    result = subprocess.run(
        [BASH_BIN, str(script_path), option],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2, (
        f"Expected exit code 2, got {result.returncode}. Stderr: {result.stderr}"
    )
    assert "unbound variable" not in result.stderr
    assert f"Error: Unexpected option: {option}" in result.stderr
    assert "Usage: execute-code.sh" in result.stderr


def test_t4_subprocess_execute_code_dead_endpoint_with_session() -> None:
    """Tier 4 Subprocess: execute-code.sh exits with code 1 when target server is dead even if --session is specified."""
    script_path = SCRIPTS_DIR / "execute-code.sh"
    result = subprocess.run(
        [
            BASH_BIN,
            str(script_path),
            "--url",
            "http://127.0.0.1:59999",
            "--session",
            "s_dead",
            "-c",
            "print(1)",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, (
        f"Expected exit code 1, got {result.returncode}. Stderr: {result.stderr}"
    )
    assert "unbound variable" not in result.stderr
    assert any(
        err in result.stderr
        for err in ["Failed to connect", "Couldn't connect", "Connection refused"]
    ), f"Expected curl connection failure in stderr, got: {result.stderr}"


def test_t4_subprocess_discover_servers_unset_home_and_xdg() -> None:
    """Tier 4 Subprocess: discover-servers.sh executes cleanly under set -u when HOME and XDG_STATE_HOME are unset."""
    script_path = SCRIPTS_DIR / "discover-servers.sh"
    clean_env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"HOME", "XDG_STATE_HOME", "USERPROFILE"}
    }
    result = subprocess.run(
        [BASH_BIN, str(script_path), "--json"],
        capture_output=True,
        text=True,
        env=clean_env,
        check=False,
    )
    assert result.returncode == 0, (
        f"Expected returncode 0, got {result.returncode}. Stderr: {result.stderr}"
    )
    assert "unbound variable" not in result.stderr
    parsed = json.loads(result.stdout)
    assert parsed == []


class _MockMarimoServer:
    def __init__(self, handler_cls: type[http.server.BaseHTTPRequestHandler]) -> None:
        self.server = http.server.HTTPServer(("127.0.0.1", 0), handler_cls)
        self.port = self.server.server_port
        self.url = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.daemon = True

    def start(self) -> _MockMarimoServer:
        self.thread.start()
        return self

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2.0)


def test_t4_subprocess_execute_code_sse_streaming_success() -> None:
    """Tier 4 Subprocess: execute-code.sh streams real SSE stdout and exits 0 on success."""

    class SSEHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if self.path == "/api/kernel/execute":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                p1 = json.dumps({"data": "Hello from marimo kernel!\n"})
                p2 = json.dumps({"success": True, "output": {"data": "42"}})
                self.wfile.write(
                    f"event: stdout\ndata: {p1}\n\nevent: done\ndata: {p2}\n\n".encode()
                )
                self.wfile.flush()
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = _MockMarimoServer(SSEHandler).start()
    try:
        script_path = SCRIPTS_DIR / "execute-code.sh"
        result = subprocess.run(
            [
                BASH_BIN,
                str(script_path),
                "--url",
                server.url,
                "--session",
                "s_test",
                "-c",
                "print(42)",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"Expected returncode 0, got {result.returncode}. Stderr: {result.stderr}"
        )
        assert "unbound variable" not in result.stderr
        assert "Hello from marimo kernel!" in result.stdout
        assert "42" in result.stdout
    finally:
        server.stop()


def test_t4_subprocess_execute_code_sse_streaming_error() -> None:
    """Tier 4 Subprocess: execute-code.sh forwards SSE stderr and exits 1 on kernel failure."""

    class SSEErrorHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if self.path == "/api/kernel/execute":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                p1 = json.dumps({"data": "ZeroDivisionError: division by zero\n"})
                p2 = json.dumps({"success": False})
                self.wfile.write(
                    f"event: stderr\ndata: {p1}\n\nevent: done\ndata: {p2}\n\n".encode()
                )
                self.wfile.flush()
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = _MockMarimoServer(SSEErrorHandler).start()
    try:
        script_path = SCRIPTS_DIR / "execute-code.sh"
        result = subprocess.run(
            [
                BASH_BIN,
                str(script_path),
                "--url",
                server.url,
                "--session",
                "s_test",
                "-c",
                "1/0",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 1, (
            f"Expected returncode 1, got {result.returncode}. Stderr: {result.stderr}"
        )
        assert "unbound variable" not in result.stderr
        assert "ZeroDivisionError: division by zero" in result.stderr
    finally:
        server.stop()


@pytest.mark.parametrize(
    ("status_code", "response_body", "expected_msg"),
    [
        (401, json.dumps({"detail": "Unauthorized token"}), "Unauthorized token"),
        (500, "Internal Server Error in session", "Internal Server Error in session"),
    ],
)
def test_t4_subprocess_execute_code_http_errors_with_session(
    status_code: int,
    response_body: str,
    expected_msg: str,
) -> None:
    """Tier 4 Subprocess: execute-code.sh exits 1 when server returns HTTP 4xx/5xx under --session."""

    class ErrorHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if self.path == "/api/kernel/execute":
                self.send_response(status_code)
                self.send_header(
                    "Content-Type",
                    "application/json" if status_code == 401 else "text/plain",
                )
                self.end_headers()
                self.wfile.write(response_body.encode())
                self.wfile.flush()
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = _MockMarimoServer(ErrorHandler).start()
    try:
        script_path = SCRIPTS_DIR / "execute-code.sh"
        result = subprocess.run(
            [
                BASH_BIN,
                str(script_path),
                "--url",
                server.url,
                "--session",
                "s_err",
                "-c",
                "print(1)",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 1, (
            f"Expected returncode 1, got {result.returncode}. Stderr: {result.stderr}"
        )
        assert "unbound variable" not in result.stderr
        assert expected_msg in result.stderr or str(status_code) in result.stderr
    finally:
        server.stop()


def test_t4_subprocess_discover_servers_live_mock_and_stale_cleanup(
    tmp_path: Path,
) -> None:
    """Tier 4 Subprocess: discover-servers.sh discovers healthy server and removes stale entry with --clean-stale."""

    class MarimoRegistryHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"healthy": true}\n')
            elif self.path == "/api/sessions":
                auth_header = self.headers.get("Authorization", "")
                if auth_header == "Bearer valid_mock_token":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(
                        json.dumps([
                            {"session_id": "sess_live", "path": "/workspace/nb.py"}
                        ]).encode()
                    )
                else:
                    self.send_response(401)
                    self.end_headers()
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = _MockMarimoServer(MarimoRegistryHandler).start()
    try:
        state_dir = tmp_path / "state" / "marimo" / "servers"
        state_dir.mkdir(parents=True)

        # 1. Active server state file
        active_state = {
            "pid": os.getpid(),  # Alive current process
            "port": server.port,
            "host": "127.0.0.1",
            "token": "valid_mock_token",
            "version": "0.10.19",
            "started_at": 1700000000,
        }
        active_file = state_dir / "server-active.json"
        active_file.write_text(json.dumps(active_state))

        # 2. Stale server state file (dead PID & dead port)
        stale_state = {
            "pid": 9999999,  # Non-existent PID
            "port": 59998,
            "host": "127.0.0.1",
            "token": "stale_token",
            "version": "0.10.0",
            "started_at": 1600000000,
        }
        stale_file = state_dir / "server-stale.json"
        stale_file.write_text(json.dumps(stale_state))

        env = {
            **os.environ,
            "XDG_STATE_HOME": str(tmp_path / "state"),
            "HOME": str(tmp_path / "home"),
        }
        script_path = SCRIPTS_DIR / "discover-servers.sh"

        # Run with --clean-stale
        result = subprocess.run(
            [BASH_BIN, str(script_path), "--json", "--clean-stale"],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        assert result.returncode == 0, (
            f"Expected 0, got {result.returncode}. Stderr: {result.stderr}"
        )
        assert "unbound variable" not in result.stderr

        discovered = json.loads(result.stdout)
        assert len(discovered) == 1, f"Expected 1 active server, got: {discovered}"
        assert discovered[0]["port"] == server.port
        assert discovered[0]["version"] == "0.10.19"
        assert discovered[0]["sessions"] == [
            {"session_id": "sess_live", "path": "/workspace/nb.py"}
        ]

        # Confirm stale state file was deleted
        assert not stale_file.exists(), (
            "Expected stale file to be deleted by --clean-stale"
        )
        assert active_file.exists(), "Active server file should not be deleted"
    finally:
        server.stop()


def test_t4_semantics_mcp_json_blocks_pass_oracle_validator() -> None:
    """Tier 4: Verify all JSON mcpServers configs in mcp_bridge_configuration.md pass oracle validation."""
    doc_path = REFERENCES_DIR / "mcp_bridge_configuration.md"
    content = doc_path.read_text(encoding="utf-8")
    json_blocks = re.findall(r"```json\n(.*?)```", content, re.DOTALL)
    assert len(json_blocks) >= 2, (
        f"Expected at least 2 JSON config blocks, found {len(json_blocks)}"
    )
    for idx, block in enumerate(json_blocks, start=1):
        cfg = json.loads(block)
        assert isinstance(cfg, dict), f"JSON block {idx} must be a dict"
        assert "mcpServers" in cfg, f"JSON block {idx} missing mcpServers"
        marimo_entry = cfg["mcpServers"].get("marimo", {})
        assert "transport" not in marimo_entry, (
            f"JSON block {idx} must not contain legacy transport field"
        )
        issues = oracle_validate_mcp_config(cfg, doc_path)
        errors = [i for i in issues if i.severity == Severity.ERROR]
        assert not errors, (
            f"JSON block {idx} failed oracle_validate_mcp_config: {errors}"
        )


def test_t4_subprocess_discover_servers_nested_session_object_and_token_file(
    tmp_path: Path,
) -> None:
    """Tier 4 Subprocess: Verify nested object /api/sessions normalization and --token-file authentication."""

    class NestedSessionHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/health":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"healthy": true}\n')
            elif self.path == "/api/sessions":
                if self.headers.get("Authorization", "") == "Bearer file_secret_token":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    payload = {
                        "sess_nested": {
                            "path": "/workspace/nested_nb.py",
                            "filename": "nested_nb.py",
                        }
                    }
                    self.wfile.write(json.dumps(payload).encode())
                else:
                    self.send_response(401)
                    self.end_headers()
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self) -> None:
            if (
                self.path == "/api/kernel/execute"
                and self.headers.get("Authorization", "") == "Bearer file_secret_token"
            ):
                content_length = int(self.headers.get("Content-Length", "0"))
                _ = self.rfile.read(content_length)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(
                    b'data: {"stdout": "token-file-ok\\n", "status": "idle"}\n\n'
                )
                self.wfile.flush()
            else:
                self.send_response(401)
                self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = _MockMarimoServer(NestedSessionHandler).start()
    try:
        state_dir = tmp_path / "state" / "marimo" / "servers"
        state_dir.mkdir(parents=True)
        (state_dir / "server-nested.json").write_text(
            json.dumps({
                "pid": os.getpid(),
                "port": server.port,
                "host": "127.0.0.1",
                "token": "file_secret_token",
                "version": "0.25.2",
                "started_at": 1700000000,
            }),
            encoding="utf-8",
        )
        token_file = tmp_path / "marimo.token"
        token_file.write_text("file_secret_token\n", encoding="utf-8")
        env = {
            **os.environ,
            "XDG_STATE_HOME": str(tmp_path / "state"),
            "HOME": str(tmp_path / "home"),
        }

        disc = subprocess.run(
            [BASH_BIN, str(SCRIPTS_DIR / "discover-servers.sh"), "--json"],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        assert disc.returncode == 0, f"discover-servers.sh failed: {disc.stderr}"
        discovered = json.loads(disc.stdout)
        assert len(discovered) == 1
        assert discovered[0]["sessions"] == [
            {"session_id": "sess_nested", "path": "/workspace/nested_nb.py"}
        ]

        exec_res = subprocess.run(
            [
                BASH_BIN,
                str(SCRIPTS_DIR / "execute-code.sh"),
                "--url",
                server.url,
                "--token-file",
                str(token_file),
                "--file",
                "nested_nb.py",
                "-c",
                "print(1)",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert exec_res.returncode == 0, f"execute-code.sh failed: {exec_res.stderr}"
        assert "token-file-ok" in exec_res.stdout
    finally:
        server.stop()
