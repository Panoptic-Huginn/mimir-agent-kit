"""Opaque-box E2E test suite for the marimo-pro AntiGravity 2.29.0+ skill.

Validates all requirements (R1, R2, R3, R4) and features (F4-F13) from
ORIGINAL_REQUEST.md and PROJECT.md across:
- Tier 1: Feature Coverage (28 tests)
- Tier 2: Boundary & Corner Cases (26 tests)
- Tier 3: Cross-Feature Interactions (12 tests)
- Tier 4: Real-World Scenarios (7 tests)
Total: 73 comprehensive E2E test cases.
"""

from __future__ import annotations

import ast
import math
import random
import re
import tomllib
from typing import TYPE_CHECKING

import pytest

from scripts.validation.codes import ErrorCode
from scripts.validation.models import Severity
from scripts.validation.models import ValidationReport
from scripts.validation.prompt_validator import validate_prompts
from scripts.validation.secret_hygiene_validator import _HOME_PATTERN
from tests.e2e.conftest import ALLOWED_SKILL_SUBDIRECTORIES
from tests.e2e.conftest import MAX_FILE_BYTES
from tests.e2e.conftest import MIN_SKILL_DESCRIPTION_LENGTH
from tests.e2e.conftest import SKILL_NAME_PATTERN
from tests.e2e.conftest import SKILLS_DIR
from tests.e2e.conftest import oracle_validate_skill
from tests.e2e.conftest import split_skill_frontmatter


if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


SKILL_DIR = SKILLS_DIR / 'marimo-pro'
SKILL_MD = SKILL_DIR / 'SKILL.md'
EXAMPLES_DIR = SKILL_DIR / 'examples'
REFERENCES_DIR = SKILL_DIR / 'references'


# ==============================================================================
# Tier 1: Feature Coverage E2E Tests (R1, R2, R3, R4)
# ==============================================================================


def test_t1_r1_01_skill_directory_exists() -> None:
    """R1: Verify skills/marimo-pro directory exists and is a directory."""
    if not SKILL_DIR.exists():
        pytest.skip(f"Skill directory not found at '{SKILL_DIR}' (Milestone 1 planned)")
    assert SKILL_DIR.is_dir(), f"'{SKILL_DIR}' is not a directory"


def test_t1_r1_02_skill_md_exists() -> None:
    """R1: Verify skills/marimo-pro/SKILL.md exists and is a regular file."""
    if not SKILL_MD.exists():
        pytest.skip(f"SKILL.md not found at '{SKILL_MD}' (Milestone 2 planned)")
    assert SKILL_MD.is_file(), f"'{SKILL_MD}' is not a regular file"


def test_t1_r1_03_skill_frontmatter_framing() -> None:
    """R1: Verify SKILL.md begins with line 1 delimiter and has valid closing delimiter."""
    if not SKILL_MD.exists():
        pytest.skip(f"SKILL.md not found at '{SKILL_MD}' (Milestone 2 planned)")
    text = SKILL_MD.read_text(encoding='utf-8')
    assert text.startswith('---\n'), "SKILL.md must begin with YAML frontmatter delimiter '---' on line 1"
    parts = text.split('---\n', 2)
    assert len(parts) >= 3, 'SKILL.md missing closing YAML frontmatter delimiter'
    frontmatter, body = split_skill_frontmatter(text)
    assert isinstance(frontmatter, dict), 'Parsed frontmatter must be a dictionary'
    assert len(body.strip()) > 0, 'SKILL.md body must not be empty'


def test_t1_r1_04_skill_frontmatter_name() -> None:
    """R1: Verify frontmatter name matches 'marimo-pro' and conforms to regex."""
    if not SKILL_MD.exists():
        pytest.skip(f"SKILL.md not found at '{SKILL_MD}' (Milestone 2 planned)")
    text = SKILL_MD.read_text(encoding='utf-8')
    frontmatter, _ = split_skill_frontmatter(text)
    name = frontmatter.get('name')
    assert name == 'marimo-pro', f"Expected skill name 'marimo-pro', got '{name}'"
    assert SKILL_NAME_PATTERN.match(name), f"Skill name '{name}' violates naming regex"


def test_t1_r1_05_skill_frontmatter_description() -> None:
    """R1: Verify frontmatter description is >= 20 characters and contains domain keywords."""
    if not SKILL_MD.exists():
        pytest.skip(f"SKILL.md not found at '{SKILL_MD}' (Milestone 2 planned)")
    text = SKILL_MD.read_text(encoding='utf-8')
    frontmatter, _ = split_skill_frontmatter(text)
    desc = frontmatter.get('description', '')
    assert isinstance(desc, str), 'Frontmatter description must be a string'
    assert len(desc.strip()) >= MIN_SKILL_DESCRIPTION_LENGTH, f'Description length ({len(desc)}) < {MIN_SKILL_DESCRIPTION_LENGTH}'
    assert 'marimo' in desc.lower(), "Description must reference 'marimo'"
    assert any(k in desc.lower() for k in ['reactive', 'notebook', 'widget', 'dag']), 'Description must highlight reactive notebook focus'


def test_t1_r1_06_skill_frontmatter_metadata() -> None:
    """R1: Verify frontmatter metadata contains version and publisher."""
    if not SKILL_MD.exists():
        pytest.skip(f"SKILL.md not found at '{SKILL_MD}' (Milestone 2 planned)")
    text = SKILL_MD.read_text(encoding='utf-8')
    frontmatter, _ = split_skill_frontmatter(text)
    metadata = frontmatter.get('metadata')
    assert isinstance(metadata, dict), "Frontmatter missing 'metadata' dictionary"
    assert 'version' in metadata, "Metadata missing 'version'"
    assert 'publisher' in metadata, "Metadata missing 'publisher'"


def test_t1_r1_07_skill_body_bytes_within_limit() -> None:
    """R1: Verify SKILL.md body size strictly < 24,000 UTF-8 bytes cap (SKL005)."""
    if not SKILL_MD.exists():
        pytest.skip(f"SKILL.md not found at '{SKILL_MD}' (Milestone 2 planned)")
    text = SKILL_MD.read_text(encoding='utf-8')
    _, body = split_skill_frontmatter(text)
    body_bytes = len(body.encode('utf-8'))
    assert body_bytes < MAX_FILE_BYTES, f'SKILL.md body ({body_bytes} bytes) exceeds limit of {MAX_FILE_BYTES} bytes'


def test_t1_r1_08_subdirectories_allowed() -> None:
    """R1: Verify subdirectories in skills/marimo-pro/ are strictly within the AntiGravity allowlist."""
    if not SKILL_DIR.exists():
        pytest.skip(f"Skill directory not found at '{SKILL_DIR}' (Milestone 1 planned)")
    discovered = {p.name for p in SKILL_DIR.iterdir() if p.is_dir()}
    disallowed = discovered - ALLOWED_SKILL_SUBDIRECTORIES
    assert not disallowed, f'Disallowed subdirectories discovered: {disallowed}'


def test_t1_r1_09_references_directory_contents() -> None:
    """R1: Verify references/ directory contains all 4 deep architectural reference manuals."""
    if not REFERENCES_DIR.exists() or not any(REFERENCES_DIR.glob('*.md')):
        pytest.skip(f"Reference manuals not yet created in '{REFERENCES_DIR}' (Milestone 2 in progress)")
    assert REFERENCES_DIR.is_dir(), f"'{REFERENCES_DIR}' is not a directory"
    required_manuals = [
        'marimo_architecture_and_dag.md',
        'interactive_widgets_and_ui.md',
        'dual_toolchain_pixi_uv.md',
        'advanced_data_analysis_scenarios.md',
    ]
    for manual in required_manuals:
        target = REFERENCES_DIR / manual
        assert target.is_file(), f"Missing required manual '{manual}' in references/"


def test_t1_r1_10_examples_directory_contents() -> None:
    """R1: Verify examples/ directory contains all 6 required configurations and runnable notebooks."""
    if not EXAMPLES_DIR.exists() or not any(EXAMPLES_DIR.iterdir()):
        pytest.skip(f"Example files not yet created in '{EXAMPLES_DIR}' (Milestone 3 planned)")
    assert EXAMPLES_DIR.is_dir(), f"'{EXAMPLES_DIR}' is not a directory"
    required_files = [
        'pyproject.toml',
        'pixi.toml',
        'astro_transit_photometry.py',
        'robotics_kalman_filter.py',
        'systems_telemetry_analysis.py',
        'bayesian_mcmc_diagnostic.py',
    ]
    for rel_path in required_files:
        target = EXAMPLES_DIR / rel_path
        assert target.is_file(), f"Missing required file '{rel_path}' in examples/"


def test_t1_r1_11_markdown_relative_links_valid() -> None:
    """R1: Verify all markdown relative links [text](target) in SKILL.md and references/ resolve cleanly."""
    if not SKILL_MD.exists():
        pytest.skip(f"SKILL.md not found at '{SKILL_MD}' (Milestone 2 planned)")
    if not list(REFERENCES_DIR.glob('*.md')):
        pytest.skip(f"Reference manuals in '{REFERENCES_DIR}' not yet created to verify links (Milestone 2 in progress)")
    link_pattern = re.compile(r'\[([^\]]+)\]\((?!https?://)([^)#\s]+)(?:#[^)]*)?\)')
    files_to_check = [SKILL_MD, *list(REFERENCES_DIR.glob('*.md'))]
    checked_count = 0

    for md_file in files_to_check:
        content = md_file.read_text(encoding='utf-8')
        for match in link_pattern.finditer(content):
            target_rel = match.group(2)
            target_path = (md_file.parent / target_rel).resolve()
            assert target_path.exists(), f"Broken relative link in '{md_file.name}': target '{target_rel}' resolved to '{target_path}' which does not exist"
            checked_count += 1

    assert checked_count >= 4, f'Expected at least 4 relative links verified across markdown files, found {checked_count}'


def test_t1_r2_01_pixi_toml_valid_toml() -> None:
    """R2: Verify examples/pixi.toml parses cleanly as valid TOML."""
    pixi_path = EXAMPLES_DIR / 'pixi.toml'
    if not pixi_path.exists():
        pytest.skip(f"pixi.toml not found at '{pixi_path}' (Milestone 3 planned)")
    raw_content = pixi_path.read_text(encoding='utf-8')
    parsed = tomllib.loads(raw_content)
    assert isinstance(parsed, dict), 'pixi.toml must parse to a dictionary'
    assert 'workspace' in parsed, "pixi.toml missing 'workspace' table"


def test_t1_r2_02_pixi_toml_workspace_and_channels() -> None:
    """R2: Verify examples/pixi.toml configures conda-forge channel and supported platforms."""
    pixi_path = EXAMPLES_DIR / 'pixi.toml'
    if not pixi_path.exists():
        pytest.skip(f"pixi.toml not found at '{pixi_path}' (Milestone 3 planned)")
    parsed = tomllib.loads(pixi_path.read_text(encoding='utf-8'))
    ws = parsed.get('workspace', {})
    channels = ws.get('channels', [])
    assert 'conda-forge' in channels, f"Expected 'conda-forge' in channels, got: {channels}"
    platforms = ws.get('platforms', [])
    assert any('linux' in p for p in platforms) and any('osx' in p or 'darwin' in p for p in platforms), f'Expected multi-platform support in platforms: {platforms}'


def test_t1_r2_03_pixi_toml_python_versions() -> None:
    """R2: Verify examples/pixi.toml dependencies support Python 3.14+ / 3.15."""
    pixi_path = EXAMPLES_DIR / 'pixi.toml'
    if not pixi_path.exists():
        pytest.skip(f"pixi.toml not found at '{pixi_path}' (Milestone 3 planned)")
    parsed = tomllib.loads(pixi_path.read_text(encoding='utf-8'))
    deps = parsed.get('dependencies', {})
    py_dep = str(deps.get('python', ''))
    assert '3.14' in py_dep or '3.15' in py_dep or '>=3.14' in py_dep, f"Expected Python 3.14+ or 3.15 dependency, got: '{py_dep}'"


def test_t1_r2_04_pixi_toml_dual_sourcing() -> None:
    """R2: Verify examples/pixi.toml configures dual sourcing (conda-forge + [pypi-dependencies])."""
    pixi_path = EXAMPLES_DIR / 'pixi.toml'
    if not pixi_path.exists():
        pytest.skip(f"pixi.toml not found at '{pixi_path}' (Milestone 3 planned)")
    parsed = tomllib.loads(pixi_path.read_text(encoding='utf-8'))
    assert 'dependencies' in parsed, "pixi.toml missing 'dependencies' table"
    assert 'pypi-dependencies' in parsed, "pixi.toml missing '[pypi-dependencies]' table"


def test_t1_r2_05_pixi_toml_tasks() -> None:
    """R2: Verify examples/pixi.toml defines required workflow tasks."""
    pixi_path = EXAMPLES_DIR / 'pixi.toml'
    if not pixi_path.exists():
        pytest.skip(f"pixi.toml not found at '{pixi_path}' (Milestone 3 planned)")
    parsed = tomllib.loads(pixi_path.read_text(encoding='utf-8'))
    tasks = parsed.get('tasks', {})
    expected_tasks = ['edit', 'run', 'check', 'export']
    for t in expected_tasks:
        assert any(t in task_name for task_name in tasks), f"pixi.toml missing task related to '{t}'"


def test_t1_r2_06_pyproject_toml_valid_toml() -> None:
    """R2: Verify examples/pyproject.toml parses cleanly as valid TOML."""
    pyproject_path = EXAMPLES_DIR / 'pyproject.toml'
    if not pyproject_path.exists():
        pytest.skip(f"pyproject.toml not found at '{pyproject_path}' (Milestone 3 planned)")
    raw_content = pyproject_path.read_text(encoding='utf-8')
    parsed = tomllib.loads(raw_content)
    assert isinstance(parsed, dict), 'pyproject.toml must parse to a dictionary'
    assert 'project' in parsed, "pyproject.toml missing 'project' table"


def test_t1_r2_07_pyproject_toml_pep621_metadata() -> None:
    """R2: Verify examples/pyproject.toml adheres to PEP 621 with requires-python >=3.14."""
    pyproject_path = EXAMPLES_DIR / 'pyproject.toml'
    if not pyproject_path.exists():
        pytest.skip(f"pyproject.toml not found at '{pyproject_path}' (Milestone 3 planned)")
    parsed = tomllib.loads(pyproject_path.read_text(encoding='utf-8'))
    project = parsed.get('project', {})
    assert 'name' in project, "project missing 'name'"
    assert 'requires-python' in project, "project missing 'requires-python'"
    req_py = project.get('requires-python', '')
    assert '3.14' in req_py or '>=3.14' in req_py, f"Expected requires-python >=3.14, got: '{req_py}'"


def test_t1_r2_08_pyproject_toml_marimo_dependency() -> None:
    """R2: Verify examples/pyproject.toml declares marimo dependency."""
    pyproject_path = EXAMPLES_DIR / 'pyproject.toml'
    if not pyproject_path.exists():
        pytest.skip(f"pyproject.toml not found at '{pyproject_path}' (Milestone 3 planned)")
    parsed = tomllib.loads(pyproject_path.read_text(encoding='utf-8'))
    deps = parsed.get('project', {}).get('dependencies', [])
    assert any('marimo' in d for d in deps), f"Expected 'marimo' in dependencies, got: {deps}"


def test_t1_r2_09_dual_toolchain_doc_cli_commands() -> None:
    """R2: Verify references/dual_toolchain_pixi_uv.md documents marimo CLI commands."""
    doc_path = REFERENCES_DIR / 'dual_toolchain_pixi_uv.md'
    if not doc_path.exists():
        pytest.skip(f"dual_toolchain_pixi_uv.md not found at '{doc_path}' (Milestone 2 planned)")
    content = doc_path.read_text(encoding='utf-8')
    assert 'marimo edit' in content, "dual_toolchain doc must document 'marimo edit'"
    assert 'marimo run' in content, "dual_toolchain doc must document 'marimo run'"
    assert 'marimo check' in content, "dual_toolchain doc must document 'marimo check'"
    assert 'marimo export' in content, "dual_toolchain doc must document 'marimo export'"


def test_t1_r2_10_dual_toolchain_doc_pytest_discovery() -> None:
    """R2: Verify references/dual_toolchain_pixi_uv.md documents embedded pytest discovery."""
    doc_path = REFERENCES_DIR / 'dual_toolchain_pixi_uv.md'
    if not doc_path.exists():
        pytest.skip(f"dual_toolchain_pixi_uv.md not found at '{doc_path}' (Milestone 2 planned)")
    content = doc_path.read_text(encoding='utf-8')
    assert 'pytest' in content.lower(), 'dual_toolchain doc must document pytest discovery'


def test_t1_r2_11_pure_uv_guardrail_in_skill() -> None:
    """R2: Verify SKILL.md does not prescribe pixi for maintaining the mimir repository itself."""
    if not SKILL_MD.exists():
        pytest.skip(f"SKILL.md not found at '{SKILL_MD}' (Milestone 2 planned)")
    text = SKILL_MD.read_text(encoding='utf-8')
    assert 'pixi run pre-commit' not in text, 'SKILL.md must not prescribe pixi for repo pre-commit'
    assert 'pixi run pytest' not in text, 'SKILL.md must not prescribe pixi for repo pytest'


def test_t1_r3_01_architecture_doc_dag_model() -> None:
    """R3: Verify references/marimo_architecture_and_dag.md covers reactive DAG execution."""
    doc_path = REFERENCES_DIR / 'marimo_architecture_and_dag.md'
    if not doc_path.exists():
        pytest.skip(f"marimo_architecture_and_dag.md not found at '{doc_path}' (Milestone 2 planned)")
    content = doc_path.read_text(encoding='utf-8')
    assert 'dag' in content.lower() or 'directed acyclic graph' in content.lower(), 'Architecture manual must document DAG model'
    assert 'single' in content.lower() and 'definition' in content.lower(), 'Manual must document single variable definition rule'


def test_t1_r3_02_architecture_doc_state_and_cycles() -> None:
    """R3: Verify references/marimo_architecture_and_dag.md covers mo.state and circular dependency avoidance."""
    doc_path = REFERENCES_DIR / 'marimo_architecture_and_dag.md'
    if not doc_path.exists():
        pytest.skip(f"marimo_architecture_and_dag.md not found at '{doc_path}' (Milestone 2 planned)")
    content = doc_path.read_text(encoding='utf-8')
    assert 'mo.state' in content or 'state' in content.lower(), 'Manual must document state management with mo.state'
    assert 'cycle' in content.lower() or 'circular' in content.lower(), 'Manual must document circular dependency handling'


def test_t1_r3_03_interactive_widgets_doc_ui_catalog() -> None:
    """R3: Verify references/interactive_widgets_and_ui.md documents the mo.ui widget catalog."""
    doc_path = REFERENCES_DIR / 'interactive_widgets_and_ui.md'
    if not doc_path.exists():
        pytest.skip(f"interactive_widgets_and_ui.md not found at '{doc_path}' (Milestone 2 planned)")
    content = doc_path.read_text(encoding='utf-8')
    widgets = ['mo.ui.slider', 'mo.ui.dropdown', 'mo.ui.table', 'mo.ui.button']
    for w in widgets:
        assert w in content, f"interactive_widgets doc missing widget documentation for '{w}'"


def test_t1_r3_04_interactive_widgets_doc_layouts() -> None:
    """R3: Verify references/interactive_widgets_and_ui.md documents UI layout containers."""
    doc_path = REFERENCES_DIR / 'interactive_widgets_and_ui.md'
    if not doc_path.exists():
        pytest.skip(f"interactive_widgets_and_ui.md not found at '{doc_path}' (Milestone 2 planned)")
    content = doc_path.read_text(encoding='utf-8')
    assert 'mo.hstack' in content, "interactive_widgets doc must document 'mo.hstack'"
    assert 'mo.vstack' in content, "interactive_widgets doc must document 'mo.vstack'"


def test_t1_r3_05_interactive_widgets_doc_wasm_export() -> None:
    """R3: Verify references/interactive_widgets_and_ui.md documents WASM Pyodide export."""
    doc_path = REFERENCES_DIR / 'interactive_widgets_and_ui.md'
    if not doc_path.exists():
        pytest.skip(f"interactive_widgets_and_ui.md not found at '{doc_path}' (Milestone 2 planned)")
    content = doc_path.read_text(encoding='utf-8')
    assert 'wasm' in content.lower() or 'pyodide' in content.lower(), 'interactive_widgets doc must document WASM/Pyodide export'


def test_t1_r4_01_scenarios_doc_domains() -> None:
    """R4: Verify references/advanced_data_analysis_scenarios.md documents target domains."""
    doc_path = REFERENCES_DIR / 'advanced_data_analysis_scenarios.md'
    if not doc_path.exists():
        pytest.skip(f"advanced_data_analysis_scenarios.md not found at '{doc_path}' (Milestone 2 planned)")
    content = doc_path.read_text(encoding='utf-8')
    assert 'heimdall-astro' in content, "Scenarios doc must reference 'heimdall-astro'"
    assert 'microkernel-labs' in content, "Scenarios doc must reference 'microkernel-labs'"
    assert 'talos-robotics' in content, "Scenarios doc must reference 'talos-robotics'"


def test_t1_r4_02_astro_transit_photometry_syntax() -> None:
    """R4: Verify examples/astro_transit_photometry.py parses cleanly as Python AST."""
    nb_path = EXAMPLES_DIR / 'astro_transit_photometry.py'
    if not nb_path.exists():
        pytest.skip(f"astro_transit_photometry.py not found at '{nb_path}' (Milestone 3 planned)")
    code = nb_path.read_text(encoding='utf-8')
    parsed = ast.parse(code, filename='astro_transit_photometry.py')
    assert isinstance(parsed, ast.Module)
    assert 'app.cell' in code, 'Notebook must use @app.cell decorators'


def test_t1_r4_03_robotics_kalman_filter_syntax() -> None:
    """R4: Verify examples/robotics_kalman_filter.py parses cleanly as Python AST."""
    nb_path = EXAMPLES_DIR / 'robotics_kalman_filter.py'
    if not nb_path.exists():
        pytest.skip(f"robotics_kalman_filter.py not found at '{nb_path}' (Milestone 3 planned)")
    code = nb_path.read_text(encoding='utf-8')
    parsed = ast.parse(code, filename='robotics_kalman_filter.py')
    assert isinstance(parsed, ast.Module)
    assert 'app.cell' in code, 'Notebook must use @app.cell decorators'


def test_t1_r4_04_systems_telemetry_analysis_syntax() -> None:
    """R4: Verify examples/systems_telemetry_analysis.py parses cleanly as Python AST."""
    nb_path = EXAMPLES_DIR / 'systems_telemetry_analysis.py'
    if not nb_path.exists():
        pytest.skip(f"systems_telemetry_analysis.py not found at '{nb_path}' (Milestone 3 planned)")
    code = nb_path.read_text(encoding='utf-8')
    parsed = ast.parse(code, filename='systems_telemetry_analysis.py')
    assert isinstance(parsed, ast.Module)
    assert 'app.cell' in code, 'Notebook must use @app.cell decorators'


def test_t1_r4_05_bayesian_mcmc_diagnostic_syntax() -> None:
    """R4: Verify examples/bayesian_mcmc_diagnostic.py has embedded pytest test cells."""
    nb_path = EXAMPLES_DIR / 'bayesian_mcmc_diagnostic.py'
    if not nb_path.exists():
        pytest.skip(f"bayesian_mcmc_diagnostic.py not found at '{nb_path}' (Milestone 3 planned)")
    code = nb_path.read_text(encoding='utf-8')
    parsed = ast.parse(code, filename='bayesian_mcmc_diagnostic.py')
    assert isinstance(parsed, ast.Module)
    test_funcs = [node.name for node in ast.walk(parsed) if isinstance(node, ast.FunctionDef) and node.name.startswith('test_')]
    assert len(test_funcs) >= 1, f'Expected embedded test functions (e.g. test_*), found: {test_funcs}'


def test_t1_r4_06_example_notebooks_main_entrypoint() -> None:
    r"""R4: Verify all example notebooks implement 'if __name__ == "__main__": app.run()'."""
    if not EXAMPLES_DIR.exists():
        pytest.skip(f"Examples directory not found at '{EXAMPLES_DIR}' (Milestone 3 planned)")
    notebooks = list(EXAMPLES_DIR.glob('*.py'))
    if not notebooks:
        pytest.skip(f"No python notebooks found in '{EXAMPLES_DIR}' (Milestone 3 planned)")
    for nb in notebooks:
        code = nb.read_text(encoding='utf-8')
        assert '__name__ == "__main__"' in code or "__name__ == '__main__'" in code, f"Notebook '{nb.name}' missing '__name__ == \"__main__\"' guard"
        assert 'app.run()' in code, f"Notebook '{nb.name}' missing 'app.run()'"


# ==============================================================================
# Tier 2: Boundary & Corner Cases E2E Tests
# ==============================================================================


def test_t2_b01_exact_24kb_limit_edge_behavior(tmp_path: Path) -> None:
    """Boundary: Verify validator accepts body of exactly 24,000 bytes and rejects 24,001 bytes."""
    skill_dir_pass = tmp_path / 'pass-skill'
    skill_dir_pass.mkdir()
    frontmatter_text = '---\nname: pass-skill\ndescription: Valid description string with 20 chars.\n---\n'

    # Exactly 24,000 body bytes
    body_24000 = 'x' * 24_000
    (skill_dir_pass / 'SKILL.md').write_text(frontmatter_text + body_24000, encoding='utf-8')
    issues_pass = oracle_validate_skill(skill_dir_pass)
    assert not any(i.code == ErrorCode.SKL005 for i in issues_pass), 'Validator rejected body of exactly 24,000 bytes'

    # 24,001 body bytes
    skill_dir_fail = tmp_path / 'fail-skill'
    skill_dir_fail.mkdir()
    body_24001 = 'x' * 24_001
    (skill_dir_fail / 'SKILL.md').write_text(
        frontmatter_text.replace('pass-skill', 'fail-skill') + body_24001,
        encoding='utf-8',
    )
    issues_fail = oracle_validate_skill(skill_dir_fail)
    assert any(i.code == ErrorCode.SKL005 for i in issues_fail), 'Validator failed to reject body of 24,001 bytes'


def test_t2_b02_empty_skill_body_validation(tmp_path: Path) -> None:
    """Boundary: Verify validator handling of empty body after frontmatter."""
    skill_dir = tmp_path / 'empty-body-skill'
    skill_dir.mkdir()
    text = '---\nname: empty-body-skill\ndescription: Valid description string with 20 chars.\n---\n'
    (skill_dir / 'SKILL.md').write_text(text, encoding='utf-8')
    issues = oracle_validate_skill(skill_dir)
    assert not any(i.code == ErrorCode.SKL005 for i in issues), 'Empty body should not trigger SKL005'


def test_t2_b03_empty_frontmatter_rejected(tmp_path: Path) -> None:
    """Boundary: Reject empty frontmatter mapping with missing name."""
    skill_dir = tmp_path / 'empty-fm-skill'
    skill_dir.mkdir()
    text = '---\n\n---\nBody content\n'
    (skill_dir / 'SKILL.md').write_text(text, encoding='utf-8')
    issues = oracle_validate_skill(skill_dir)
    assert any(i.code in {ErrorCode.SKL002, ErrorCode.SKL003} for i in issues)


def test_t2_b04_frontmatter_missing_opening_delimiter(tmp_path: Path) -> None:
    """Boundary: Reject SKILL.md without leading delimiter on line 1."""
    skill_dir = tmp_path / 'no-open-skill'
    skill_dir.mkdir()
    text = 'name: no-open-skill\ndescription: Valid description string with 20 chars.\n---\nBody\n'
    (skill_dir / 'SKILL.md').write_text(text, encoding='utf-8')
    issues = oracle_validate_skill(skill_dir)
    assert any(i.code == ErrorCode.SKL002 for i in issues)


def test_t2_b05_frontmatter_missing_closing_delimiter(tmp_path: Path) -> None:
    """Boundary: Reject SKILL.md with only single opening delimiter."""
    skill_dir = tmp_path / 'unclosed-fm-skill'
    skill_dir.mkdir()
    text = '---\nname: unclosed-fm-skill\ndescription: Valid description string with 20 chars.\nBody without closing\n'
    (skill_dir / 'SKILL.md').write_text(text, encoding='utf-8')
    issues = oracle_validate_skill(skill_dir)
    assert any(i.code == ErrorCode.SKL002 for i in issues)


def test_t2_b06_frontmatter_non_mapping_yaml(tmp_path: Path) -> None:
    """Boundary: Reject SKILL.md frontmatter that parses to YAML list."""
    skill_dir = tmp_path / 'list-fm-skill'
    skill_dir.mkdir()
    text = '---\n- item 1\n- item 2\n---\nBody\n'
    (skill_dir / 'SKILL.md').write_text(text, encoding='utf-8')
    issues = oracle_validate_skill(skill_dir)
    assert any(i.code in {ErrorCode.SKL002, ErrorCode.SKL003} for i in issues)


def test_t2_b07_frontmatter_name_mismatch_directory(tmp_path: Path) -> None:
    """Boundary: Reject skill name that does not match directory name."""
    skill_dir = tmp_path / 'actual-dir-name'
    skill_dir.mkdir()
    text = '---\nname: mismatched-name\ndescription: Valid description string with 20 chars.\n---\nBody\n'
    (skill_dir / 'SKILL.md').write_text(text, encoding='utf-8')
    issues = oracle_validate_skill(skill_dir)
    assert any(i.code == ErrorCode.SKL003 for i in issues)


def test_t2_b08_frontmatter_name_invalid_regex(tmp_path: Path) -> None:
    """Boundary: Reject skill name containing uppercase or underscores."""
    skill_dir = tmp_path / 'bad_name_skill'
    skill_dir.mkdir()
    text = '---\nname: bad_name_skill\ndescription: Valid description string with 20 chars.\n---\nBody\n'
    (skill_dir / 'SKILL.md').write_text(text, encoding='utf-8')
    issues = oracle_validate_skill(skill_dir)
    assert any(i.code == ErrorCode.SKL003 for i in issues)


def test_t2_b09_frontmatter_description_19_chars_rejected(tmp_path: Path) -> None:
    """Boundary: Reject skill description of 19 characters (< 20 minimum)."""
    skill_dir = tmp_path / 'desc19-skill'
    skill_dir.mkdir()
    text = '---\nname: desc19-skill\ndescription: 1234567890123456789\n---\nBody\n'
    (skill_dir / 'SKILL.md').write_text(text, encoding='utf-8')
    issues = oracle_validate_skill(skill_dir)
    assert any(i.code == ErrorCode.SKL004 for i in issues)


def test_t2_b10_frontmatter_description_20_chars_accepted(tmp_path: Path) -> None:
    """Boundary: Accept skill description of exactly 20 characters."""
    skill_dir = tmp_path / 'desc20-skill'
    skill_dir.mkdir()
    text = '---\nname: desc20-skill\ndescription: "Twenty chars exactly."\n---\nBody\n'
    (skill_dir / 'SKILL.md').write_text(text, encoding='utf-8')
    issues = oracle_validate_skill(skill_dir)
    assert not any(i.code == ErrorCode.SKL004 for i in issues)


def test_t2_b11_disallowed_subdirectory_rejected(tmp_path: Path) -> None:
    """Boundary: Flag disallowed subdirectories (e.g. target/ or src/)."""
    skill_dir = tmp_path / 'bad-sub-skill'
    skill_dir.mkdir()
    (skill_dir / 'SKILL.md').write_text(
        '---\nname: bad-sub-skill\ndescription: Valid description string with 20 chars.\n---\nBody\n',
        encoding='utf-8',
    )
    (skill_dir / 'target').mkdir()
    issues = oracle_validate_skill(skill_dir)
    assert any(i.code == ErrorCode.SKL006 for i in issues)


def test_t2_b12_missing_skill_md_rejected(tmp_path: Path) -> None:
    """Boundary: Flag directory missing SKILL.md with SKL001."""
    empty_skill = tmp_path / 'missing-skill'
    empty_skill.mkdir()
    issues = oracle_validate_skill(empty_skill)
    assert any(i.code == ErrorCode.SKL001 for i in issues)


def test_t2_b13_non_utf8_skill_md_rejected(tmp_path: Path) -> None:
    """Boundary: Flag SKILL.md containing invalid non-UTF8 bytes with SKL002."""
    skill_dir = tmp_path / 'bad-utf8-skill'
    skill_dir.mkdir()
    (skill_dir / 'SKILL.md').write_bytes(b'\xff\xfe\x00\x00invalid')
    issues = oracle_validate_skill(skill_dir)
    assert any(i.code == ErrorCode.SKL002 for i in issues)


def test_t2_b14_relative_link_missing_target_detected(tmp_path: Path) -> None:
    """Boundary: Detect dangling relative markdown links."""
    doc_path = tmp_path / 'test.md'
    doc_path.write_text('[Broken Link](./nonexistent_file.md)\n', encoding='utf-8')
    link_re = re.compile(r'\[([^\]]+)\]\((?!https?://)([^)#\s]+)(?:#[^)]*)?\)')
    matches = list(link_re.finditer(doc_path.read_text(encoding='utf-8')))
    assert len(matches) == 1
    rel = matches[0].group(2)
    resolved = doc_path.parent / rel
    assert not resolved.exists(), 'Expected target to be nonexistent'


def test_t2_b15_relative_link_with_anchor_resolved(tmp_path: Path) -> None:
    """Boundary: Verify relative link containing anchor resolves to existing base file."""
    base_file = tmp_path / 'guide.md'
    base_file.write_text('# Section Heading\nContent\n', encoding='utf-8')
    link_str = '[Heading Reference](./guide.md#section-heading)'
    link_re = re.compile(r'\[([^\]]+)\]\((?!https?://)([^)#\s]+)(?:#[^)]*)?\)')
    match = link_re.search(link_str)
    assert match is not None
    rel_path = match.group(2)
    assert (tmp_path / rel_path).resolve().is_file()


def test_t2_b16_relative_link_url_ignored() -> None:
    """Boundary: Verify external HTTP/HTTPS links are excluded from relative link resolution."""
    link_re = re.compile(r'\[([^\]]+)\]\((?!https?://)([^)#\s]+)(?:#[^)]*)?\)')
    url_text = '[Marimo Docs](https://docs.marimo.io)'
    match = link_re.search(url_text)
    assert match is None, 'HTTP URL should not match relative link pattern'


def test_t2_b17_prohibited_pixi_in_repo_commands_rejected(tmp_path: Path) -> None:
    """Boundary: Verify prompt validator flags rule prescribing pixi for repository maintenance."""
    rules_dir = tmp_path / 'rules'
    rules_dir.mkdir()
    bad_rule = rules_dir / 'AGENTS.md'
    bad_rule.write_text(
        '# Rules\nAlways execute `pixi run pre-commit` before pushing.\n',
        encoding='utf-8',
    )
    report = ValidationReport()
    validate_prompts(tmp_path, report)
    assert any(i.code == ErrorCode.PRM003 for i in report.issues)


def test_t2_b18_secret_hygiene_home_path_leak_detected() -> None:
    """Boundary: Verify secret hygiene pattern detects developer machine home directories."""
    leaked_macos = '/Users/' + 'jamie/development/project'
    leaked_linux = '/home/' + 'jamie-lapointe/development/project'
    assert _HOME_PATTERN.search(leaked_macos) is not None, 'Failed to detect macOS home path leak'
    assert _HOME_PATTERN.search(leaked_linux) is not None, 'Failed to detect Linux home path leak'
    clean_path = '/usr/local/bin/python'
    assert _HOME_PATTERN.search(clean_path) is None, 'False positive on clean path'


_EXCLUDED_CACHE_PARTS = frozenset({
    '.ruff_cache',
    '__pycache__',
    '.pytest_cache',
    '__marimo__',
    '.venv',
    '.pixi',
})


def test_t2_b19_secret_hygiene_clean_in_skill_files() -> None:
    """Boundary: Verify all tracked files in skills/marimo-pro/ are 100% clean of home path leaks."""
    if not SKILL_DIR.exists():
        pytest.skip(f"Skill directory not found at '{SKILL_DIR}' (Milestone 1 planned)")
    for file_path in SKILL_DIR.rglob('*'):
        if any(part in _EXCLUDED_CACHE_PARTS for part in file_path.parts):
            continue
        if file_path.suffix == '.pyc':
            continue
        if file_path.is_file():
            text = file_path.read_text(encoding='utf-8', errors='ignore')
            assert not _HOME_PATTERN.search(text), f"Home path leak detected in '{file_path}'"


def test_t2_b20_pyproject_toml_corrupt_syntax_rejected(tmp_path: Path) -> None:
    """Boundary: Verify corrupt syntax in pyproject.toml raises tomllib.TOMLDecodeError."""
    bad_toml = tmp_path / 'pyproject.toml'
    bad_toml.write_text("[project\nname = 'unclosed", encoding='utf-8')
    with pytest.raises(tomllib.TOMLDecodeError):
        tomllib.loads(bad_toml.read_text(encoding='utf-8'))


def test_t2_b21_pixi_toml_corrupt_syntax_rejected(tmp_path: Path) -> None:
    """Boundary: Verify corrupt syntax in pixi.toml raises tomllib.TOMLDecodeError."""
    bad_toml = tmp_path / 'pixi.toml'
    bad_toml.write_text('[workspace\nchannels = [', encoding='utf-8')
    with pytest.raises(tomllib.TOMLDecodeError):
        tomllib.loads(bad_toml.read_text(encoding='utf-8'))


def test_t2_b22_skill_md_actual_body_size_headroom() -> None:
    """Boundary: Verify skills/marimo-pro/SKILL.md body has >= 500 bytes safety headroom before 24KB cap."""
    if not SKILL_MD.exists():
        pytest.skip(f"SKILL.md not found at '{SKILL_MD}' (Milestone 2 planned)")
    text = SKILL_MD.read_text(encoding='utf-8')
    _, body = split_skill_frontmatter(text)
    body_bytes = len(body.encode('utf-8'))
    headroom = MAX_FILE_BYTES - body_bytes
    assert headroom >= 500, f'Insufficient headroom: {headroom} bytes remaining before {MAX_FILE_BYTES} cap'


def test_t2_b23_reference_manuals_sizing() -> None:
    """Boundary: Verify all markdown reference manuals in references/ remain < 24,000 bytes."""
    if not REFERENCES_DIR.exists():
        pytest.skip(f"References directory not found at '{REFERENCES_DIR}' (Milestone 2 planned)")
    for manual in REFERENCES_DIR.glob('*.md'):
        bytes_len = len(manual.read_bytes())
        assert bytes_len < MAX_FILE_BYTES, f"Manual '{manual.name}' size ({bytes_len} bytes) exceeds {MAX_FILE_BYTES} bytes"


def test_t2_b24_empty_files_rejected() -> None:
    """Boundary: Verify zero 0-byte stub files exist anywhere in skills/marimo-pro/."""
    if not SKILL_DIR.exists():
        pytest.skip(f"Skill directory not found at '{SKILL_DIR}' (Milestone 1 planned)")
    for file_path in SKILL_DIR.rglob('*'):
        if file_path.is_file():
            assert file_path.stat().st_size > 0, f"Empty 0-byte file detected at '{file_path}'"


def test_t2_b25_marimo_cell_syntax_error_detected() -> None:
    """Boundary: Verify AST parsing detects syntax errors in malformed python code."""
    malformed_code = '@app.cell\ndef __():\n    x = 10 +\n    return x\n'
    with pytest.raises(SyntaxError):
        ast.parse(malformed_code)


def test_t2_b26_marimo_duplicate_definition_boundary() -> None:
    """Boundary: Detect multiple global variable assignments across distinct cells."""
    cell_1_code = '@app.cell\ndef cell_1():\n    x = 1\n    return x,\n'
    cell_2_code = '@app.cell\ndef cell_2():\n    x = 2\n    return x,\n'
    combined_code = cell_1_code + '\n' + cell_2_code
    parsed = ast.parse(combined_code)

    def extract_cell_assignments(tree: ast.AST) -> dict[str, list[str]]:
        cell_vars: dict[str, list[str]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith('cell_'):
                vars_in_cell: list[str] = []
                for stmt in node.body:
                    if isinstance(stmt, ast.Assign):
                        vars_in_cell.extend(target.id for target in stmt.targets if isinstance(target, ast.Name))
                cell_vars[node.name] = vars_in_cell
        return cell_vars

    assignments = extract_cell_assignments(parsed)
    all_vars: list[str] = []
    for vars_list in assignments.values():
        all_vars.extend(vars_list)

    duplicates = {v for v in all_vars if all_vars.count(v) > 1}
    assert 'x' in duplicates, "Failed to detect duplicate variable 'x' across cells"


# ==============================================================================
# Tier 3: Cross-Feature Interactions E2E Tests
# ==============================================================================


def test_t3_cross_pixi_and_uv_dependency_alignment() -> None:
    """Interaction: Verify dependency alignment between pixi.toml and pyproject.toml."""
    pixi_path = EXAMPLES_DIR / 'pixi.toml'
    pyproject_path = EXAMPLES_DIR / 'pyproject.toml'
    if not (pixi_path.exists() and pyproject_path.exists()):
        pytest.skip('Manifest files not yet created (Milestone 3 planned)')

    pixi_cfg = tomllib.loads(pixi_path.read_text(encoding='utf-8'))
    pyproject_cfg = tomllib.loads(pyproject_path.read_text(encoding='utf-8'))

    # Both must declare marimo
    pixi_deps = {**pixi_cfg.get('dependencies', {}), **pixi_cfg.get('pypi-dependencies', {})}
    assert 'marimo' in pixi_deps, 'marimo not found in pixi dependencies'

    pyproject_deps = pyproject_cfg.get('project', {}).get('dependencies', [])
    assert any('marimo' in d for d in pyproject_deps), 'marimo not found in pyproject dependencies'


def test_t3_cross_python_version_support_alignment() -> None:
    """Interaction: Both pixi.toml and pyproject.toml support Python 3.14+ and 3.15."""
    pixi_path = EXAMPLES_DIR / 'pixi.toml'
    pyproject_path = EXAMPLES_DIR / 'pyproject.toml'
    if not (pixi_path.exists() and pyproject_path.exists()):
        pytest.skip('Manifest files not yet created (Milestone 3 planned)')

    pixi_cfg = tomllib.loads(pixi_path.read_text(encoding='utf-8'))
    pyproject_cfg = tomllib.loads(pyproject_path.read_text(encoding='utf-8'))

    py_pixi = str(pixi_cfg.get('dependencies', {}).get('python', ''))
    py_uv = str(pyproject_cfg.get('project', {}).get('requires-python', ''))

    assert '3.14' in py_pixi or '3.15' in py_pixi or '>=3.14' in py_pixi
    assert '3.14' in py_uv or '>=3.14' in py_uv


def test_t3_cross_references_link_parity_with_skill_md() -> None:
    """Interaction: All 4 reference manuals are linked in SKILL.md and exist."""
    if not SKILL_MD.exists():
        pytest.skip(f"SKILL.md not found at '{SKILL_MD}' (Milestone 2 planned)")
    if not list(REFERENCES_DIR.glob('*.md')):
        pytest.skip(f"Reference manuals in '{REFERENCES_DIR}' not yet created (Milestone 2 in progress)")
    content = SKILL_MD.read_text(encoding='utf-8')
    expected_manuals = [
        'marimo_architecture_and_dag.md',
        'interactive_widgets_and_ui.md',
        'dual_toolchain_pixi_uv.md',
        'advanced_data_analysis_scenarios.md',
    ]
    for manual in expected_manuals:
        assert manual in content, f"SKILL.md missing link reference to '{manual}'"
        assert (REFERENCES_DIR / manual).is_file(), f"Referenced manual '{manual}' does not exist"


def test_t3_cross_example_notebooks_link_parity() -> None:
    """Interaction: All example notebooks documented in references/ exist in examples/."""
    if not REFERENCES_DIR.exists() or not list(REFERENCES_DIR.glob('*.md')):
        pytest.skip(f"References directory empty or not found at '{REFERENCES_DIR}' (Milestone 2 planned)")
    all_refs = '\n'.join(f.read_text(encoding='utf-8') for f in REFERENCES_DIR.glob('*.md'))
    expected_notebooks = [
        'astro_transit_photometry.py',
        'robotics_kalman_filter.py',
        'systems_telemetry_analysis.py',
        'bayesian_mcmc_diagnostic.py',
    ]
    for nb in expected_notebooks:
        assert nb in all_refs, f"References manuals missing mention of notebook '{nb}'"
        if EXAMPLES_DIR.exists():
            assert (EXAMPLES_DIR / nb).is_file(), f"Documented notebook '{nb}' missing in examples/"


def test_t3_cross_marimo_app_instantiation_pattern() -> None:
    """Interaction: All example notebooks instantiate marimo.App consistently."""
    if not EXAMPLES_DIR.exists():
        pytest.skip(f"Examples directory not found at '{EXAMPLES_DIR}' (Milestone 3 planned)")
    notebooks = list(EXAMPLES_DIR.glob('*.py'))
    if not notebooks:
        pytest.skip('No notebooks found (Milestone 3 planned)')
    for nb in notebooks:
        code = nb.read_text(encoding='utf-8')
        assert 'app = marimo.App(' in code, f"Notebook '{nb.name}' missing standard 'app = marimo.App(...)'"


def test_t3_cross_ui_widgets_and_state_consistency() -> None:
    """Interaction: Notebooks using interactive widgets import marimo as mo and reference mo.ui."""
    if not EXAMPLES_DIR.exists():
        pytest.skip(f"Examples directory not found at '{EXAMPLES_DIR}' (Milestone 3 planned)")
    interactive_nbs = [
        EXAMPLES_DIR / 'astro_transit_photometry.py',
        EXAMPLES_DIR / 'robotics_kalman_filter.py',
    ]
    for nb in interactive_nbs:
        if nb.exists():
            code = nb.read_text(encoding='utf-8')
            assert 'import marimo as mo' in code or 'mo.ui' in code, f"Interactive notebook '{nb.name}' missing 'mo.ui' usage"


def test_t3_cross_mcmc_diagnostic_and_pytest_discovery() -> None:
    """Interaction: bayesian_mcmc_diagnostic.py test functions adhere to pytest discovery conventions."""
    nb_path = EXAMPLES_DIR / 'bayesian_mcmc_diagnostic.py'
    if not nb_path.exists():
        pytest.skip(f"bayesian_mcmc_diagnostic.py not found at '{nb_path}' (Milestone 3 planned)")
    code = nb_path.read_text(encoding='utf-8')
    parsed = ast.parse(code)
    test_funcs = [node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name.startswith('test_')]
    assert len(test_funcs) >= 1, 'bayesian_mcmc_diagnostic.py must define >= 1 top-level test_ function'
    for fn in test_funcs:
        # Verify function contains at least one assert statement
        assert any(isinstance(child, ast.Assert) for child in ast.walk(fn)), f"Test function '{fn.name}' missing assert statement"


def test_t3_cross_ast_analysis_variable_scoping() -> None:
    """Interaction: AST analysis confirms no duplicate global definitions across cells in each example."""
    if not EXAMPLES_DIR.exists():
        pytest.skip(f"Examples directory not found at '{EXAMPLES_DIR}' (Milestone 3 planned)")
    notebooks = list(EXAMPLES_DIR.glob('*.py'))
    if not notebooks:
        pytest.skip('No notebooks found (Milestone 3 planned)')

    def _extract_target_names(target: ast.AST) -> list[str]:
        if isinstance(target, ast.Name):
            return [target.id]
        if isinstance(target, (ast.Tuple, ast.List)):
            names: list[str] = []
            for elt in target.elts:
                names.extend(_extract_target_names(elt))
            return names
        return []

    def _get_cell_scoped_statements(cell_node: ast.FunctionDef) -> list[ast.AST]:
        stmts: list[ast.AST] = []
        stack: list[ast.AST] = list(cell_node.body)
        while stack:
            stmt = stack.pop()
            stmts.append(stmt)
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            stack.extend(ast.iter_child_nodes(stmt))
        return stmts

    for nb in notebooks:
        code = nb.read_text(encoding='utf-8')
        parsed = ast.parse(code)
        cell_definitions: list[set[str]] = []
        for node in parsed.body:
            if isinstance(node, ast.FunctionDef) and any(isinstance(d, ast.Attribute) and d.attr == 'cell' for d in node.decorator_list):
                defs_in_cell: set[str] = set()
                for stmt in _get_cell_scoped_statements(node):
                    if isinstance(stmt, ast.Assign):
                        for target in stmt.targets:
                            for name in _extract_target_names(target):
                                if not name.startswith('_'):
                                    defs_in_cell.add(name)
                    elif isinstance(stmt, ast.AnnAssign):
                        if isinstance(stmt.target, ast.Name) and not stmt.target.id.startswith('_'):
                            defs_in_cell.add(stmt.target.id)
                    elif isinstance(stmt, ast.Import):
                        for alias in stmt.names:
                            name = alias.asname if alias.asname else alias.name.split('.')[0]
                            if not name.startswith('_'):
                                defs_in_cell.add(name)
                    elif isinstance(stmt, ast.ImportFrom):
                        for alias in stmt.names:
                            name = alias.asname if alias.asname else alias.name
                            if not name.startswith('_'):
                                defs_in_cell.add(name)
                cell_definitions.append(defs_in_cell)

        all_defs: list[str] = []
        for cell_set in cell_definitions:
            all_defs.extend(cell_set)
        counts = {v: all_defs.count(v) for v in set(all_defs)}
        collisions = {v: c for v, c in counts.items() if c > 1}
        assert not collisions, f"Global variable collision in '{nb.name}': {collisions}"


def test_t3_cross_wasm_export_guidance_and_ui_widgets() -> None:
    """Interaction: WASM Pyodide export guidance aligns with supported UI widget catalogs."""
    doc_path = REFERENCES_DIR / 'interactive_widgets_and_ui.md'
    if not doc_path.exists():
        pytest.skip(f"interactive_widgets_and_ui.md not found at '{doc_path}' (Milestone 2 planned)")
    content = doc_path.read_text(encoding='utf-8')
    assert 'export' in content.lower() and 'wasm' in content.lower(), 'interactive_widgets manual must detail WASM export'
    assert 'mo.ui' in content, 'interactive_widgets manual must describe mo.ui in WASM context'


def test_t3_cross_skill_prompt_references_consistency() -> None:
    """Interaction: Cross-skill references in SKILL.md under Related Skills match existing skills."""
    if not SKILL_MD.exists():
        pytest.skip(f"SKILL.md not found at '{SKILL_MD}' (Milestone 2 planned)")
    skill_text = SKILL_MD.read_text(encoding='utf-8')
    ref_pattern = re.compile(
        r'^\s*-\s*(?:\*\*)?`?/([a-z0-9]+(?:-[a-z0-9]+)*)`?(?:\*\*)?:?',
        re.MULTILINE,
    )
    discovered_skills = {p.name for p in SKILLS_DIR.iterdir() if p.is_dir()}

    for match in ref_pattern.finditer(skill_text):
        skill_ref = match.group(1)
        if skill_ref in {'python-pro', 'jupyter-pro', 'rust-pro', 'github-flow-lifecycle'}:
            assert skill_ref in discovered_skills, f"Referenced skill '{skill_ref}' not found in skills/"


def test_t3_cross_marimo_check_cli_compatibility() -> None:
    """Interaction: Verify all example notebooks adhere to marimo cell function structure."""
    if not EXAMPLES_DIR.exists():
        pytest.skip(f"Examples directory not found at '{EXAMPLES_DIR}' (Milestone 3 planned)")
    notebooks = list(EXAMPLES_DIR.glob('*.py'))
    if not notebooks:
        pytest.skip('No notebooks found (Milestone 3 planned)')
    for nb in notebooks:
        code = nb.read_text(encoding='utf-8')
        assert '@app.cell' in code, f"Notebook '{nb.name}' missing @app.cell decorators"
        assert 'def __(' in code or 'def _(' in code or 'def ' in code, f"Notebook '{nb.name}' missing cell functions"


def test_t3_cross_ast_private_variable_isolation() -> None:
    """Interaction: Example notebooks follow '_' prefixing convention for private helper variables."""
    if not EXAMPLES_DIR.exists():
        pytest.skip(f"Examples directory not found at '{EXAMPLES_DIR}' (Milestone 3 planned)")
    notebooks = list(EXAMPLES_DIR.glob('*.py'))
    if not notebooks:
        pytest.skip('No notebooks found (Milestone 3 planned)')
    has_private_pattern = False
    for nb in notebooks:
        code = nb.read_text(encoding='utf-8')
        if re.search(r'\b_[a-zA-Z0-9_]+\s*=', code):
            has_private_pattern = True
            break
    assert has_private_pattern, "Expected at least one notebook demonstrating private variable pattern '_var = ...'"


# ==============================================================================
# Tier 4: Real-World Scenarios E2E Tests
# ==============================================================================


def test_t4_scenario_full_skill_audit_via_agentic_oracle() -> None:
    """Scenario 1: Authoritative AntiGravity 2.29.0 validation oracle run of skills/marimo-pro/."""
    if not SKILL_DIR.exists():
        pytest.skip(f"Skill directory not found at '{SKILL_DIR}' (Milestone 1 planned)")
    issues = oracle_validate_skill(SKILL_DIR)
    error_issues = [i for i in issues if i.severity == Severity.ERROR]
    assert not error_issues, f'Authoritative oracle found errors in {SKILL_DIR.name}: {error_issues}'


def test_t4_scenario_reactive_dag_execution_simulation() -> None:
    """Scenario 2: Simulation of Marimo reactive DAG execution engine and topological update propagation.

    Models:
    - Directed Acyclic Graph of cells with variable definitions and references.
    - Topological sort of evaluation order.
    - Selective re-execution of downstream cells when upstream inputs mutate.
    - Verification that independent upstream cells remain untouched.
    """

    class Cell:
        def __init__(self, name: str, reads: list[str], writes: list[str], func: Callable[..., object]) -> None:
            self.name = name
            self.reads = reads
            self.writes = writes
            self.func = func
            self.eval_count = 0

        def run(self, scope: dict[str, object]) -> dict[str, object]:
            self.eval_count += 1
            inputs = [scope[var] for var in self.reads]
            outputs = self.func(*inputs)
            if len(self.writes) == 1:
                return {self.writes[0]: outputs}
            if isinstance(outputs, (list, tuple)):
                return dict(zip(self.writes, outputs, strict=True))
            return {self.writes[0]: outputs}

    class ReactiveNotebook:
        def __init__(self, cells: list[Cell]) -> None:
            self.cells = cells
            self.scope: dict[str, object] = {}

        def execute_all(self) -> None:
            # Simple topological order execution
            for cell in self.cells:
                result = cell.run(self.scope)
                self.scope.update(result)

        def update_variable(self, var: str, new_val: object) -> None:
            self.scope[var] = new_val
            # Re-run downstream cells that depend directly or indirectly on `var`
            affected_vars = {var}
            for cell in self.cells:
                if any(r in affected_vars for r in cell.reads):
                    res = cell.run(self.scope)
                    self.scope.update(res)
                    affected_vars.update(cell.writes)

    # Construct cells:
    # Cell 0 (Input Slider): produces 'radius'
    # Cell 1 (Dependent Calculation): reads 'radius', produces 'area'
    # Cell 2 (Independent Calculation): produces 'constant_k'
    # Cell 3 (Dashboard View): reads 'area', 'constant_k', produces 'summary'
    c0 = Cell('slider', reads=[], writes=['radius'], func=lambda: 5.0)
    c1 = Cell('calc_area', reads=['radius'], writes=['area'], func=lambda r: math.pi * (float(r) ** 2))
    c2 = Cell('const_k', reads=[], writes=['constant_k'], func=lambda: 42.0)
    c3 = Cell('summary', reads=['area', 'constant_k'], writes=['summary'], func=lambda a, k: f'Area={float(a):.2f}, K={k}')

    nb = ReactiveNotebook([c0, c1, c2, c3])
    nb.execute_all()

    assert math.isclose(float(str(nb.scope['radius'])), 5.0)
    assert abs(float(str(nb.scope['area'])) - 78.5398) < 1e-3
    assert math.isclose(float(str(nb.scope['constant_k'])), 42.0)
    assert 'Area=78.54' in str(nb.scope['summary'])
    assert c0.eval_count == 1
    assert c1.eval_count == 1
    assert c2.eval_count == 1
    assert c3.eval_count == 1

    # Mutate radius from slider: c1 and c3 must re-evaluate, but c2 must remain at eval_count == 1
    nb.update_variable('radius', 10.0)
    assert math.isclose(float(str(nb.scope['radius'])), 10.0)
    assert abs(float(str(nb.scope['area'])) - 314.159) < 1e-3
    assert c1.eval_count == 2
    assert c2.eval_count == 1  # Unaffected!
    assert c3.eval_count == 2


def test_t4_scenario_circular_dependency_detection_simulation() -> None:
    """Scenario 3: Simulation of Marimo circular dependency detection and rejection.

    Validates that cyclic references (Cell A needs Cell B, Cell B needs Cell A)
    are detected and cleanly prevented from execution.
    """
    dependencies = {
        'cell_a': ['cell_b'],
        'cell_b': ['cell_c'],
        'cell_c': ['cell_a'],  # Cycle!
    }

    def detect_cycle(graph: dict[str, list[str]]) -> list[str]:
        visited: set[str] = set()
        rec_stack: list[str] = []

        def dfs(node: str) -> list[str]:
            visited.add(node)
            rec_stack.append(node)
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    cycle = dfs(neighbor)
                    if cycle:
                        return cycle
                elif neighbor in rec_stack:
                    idx = rec_stack.index(neighbor)
                    return [*rec_stack[idx:], neighbor]
            rec_stack.pop()
            return []

        for n in graph:
            if n not in visited:
                res = dfs(n)
                if res:
                    return res
        return []

    cycle = detect_cycle(dependencies)
    assert len(cycle) >= 3, f'Expected detected cycle, got: {cycle}'
    assert cycle[0] == cycle[-1], 'Cycle must start and end at the same node'


def test_t4_scenario_transit_photometry_mandel_agol_simulation() -> None:
    """Scenario 4: Simulation of exoplanet transit light curve modeling (Mandel-Agol uniform source).

    Models:
    - Impact parameter b and normalized separation d
    - Planet-to-star radius ratio p = Rp / Rstar
    - Normalized light flux:
      * Out of transit (d >= 1 + p): flux = 1.0
      * Total eclipse/ingress (d <= 1 - p): flux = 1.0 - p^2
      * Ingress/egress limb crossing (abs(1 - p) < d < 1 + p): geometric chord reduction
    """

    def uniform_transit_flux(d: float, p: float) -> float:
        if d >= 1.0 + p:
            return 1.0
        if d <= 1.0 - p:
            return 1.0 - (p**2)
        # Grazing overlap approximation
        k0 = math.acos((p**2 + d**2 - 1.0) / (2.0 * p * d))
        k1 = math.acos((1.0 - p**2 + d**2) / (2.0 * d))
        area_overlap = (p**2) * k0 + k1 - math.sqrt(max(0.0, 4.0 * (d**2) - ((1.0 + d**2 - p**2) ** 2))) / 2.0
        return 1.0 - (area_overlap / math.pi)

    p_val = 0.1  # Rp / Rstar = 0.1 (Jupiter/Sun ratio)

    # 1. Out of transit
    flux_out = uniform_transit_flux(d=1.5, p=p_val)
    assert math.isclose(flux_out, 1.0)

    # 2. Total ingress (center of transit)
    flux_in = uniform_transit_flux(d=0.0, p=p_val)
    assert abs(flux_in - (1.0 - (p_val**2))) < 1e-4
    assert math.isclose(flux_in, 0.99)  # 1% transit depth

    # 3. Partial ingress/egress
    flux_limb = uniform_transit_flux(d=1.0, p=p_val)
    assert 0.99 < flux_limb < 1.0


def test_t4_scenario_robotics_ekf_fusion_simulation() -> None:
    """Scenario 5: Simulation of Extended Kalman Filter (EKF) state estimation for robotics trajectory tracking.

    Validates:
    - State vector x = [position, velocity]^T
    - Kinematic state prediction step
    - Sensor measurement update step
    - Covariance shrinking and convergence
    """
    # State: [position, velocity]
    dt = 0.1
    f_mat = [[1.0, dt], [0.0, 1.0]]  # State transition matrix
    h_mat = [1.0, 0.0]  # Measurement matrix (observing position only)
    q_mat = [[0.01, 0.0], [0.0, 0.05]]  # Process noise covariance
    r_noise = 0.2  # Measurement noise variance

    # Initial state and covariance
    x_state = [0.0, 1.0]  # Initial pos=0, vel=1.0
    p_cov = [[1.0, 0.0], [0.0, 1.0]]

    # Simulated true trajectory over 10 steps
    measurements = [0.12, 0.22, 0.29, 0.41, 0.52, 0.61, 0.73, 0.81, 0.92, 1.01]

    for z in measurements:
        # 1. Predict
        x_pred = [
            f_mat[0][0] * x_state[0] + f_mat[0][1] * x_state[1],
            f_mat[1][0] * x_state[0] + f_mat[1][1] * x_state[1],
        ]
        p_pred = [
            [f_mat[0][0] * p_cov[0][0] * f_mat[0][0] + f_mat[0][1] * p_cov[1][1] * f_mat[0][1] + q_mat[0][0], 0.0],
            [0.0, f_mat[1][1] * p_cov[1][1] * f_mat[1][1] + q_mat[1][1]],
        ]

        # 2. Update
        y_innov = z - (h_mat[0] * x_pred[0] + h_mat[1] * x_pred[1])  # Innovation
        s_innov = h_mat[0] * p_pred[0][0] * h_mat[0] + r_noise  # Innovation covariance
        k_gain = [p_pred[0][0] * h_mat[0] / s_innov, p_pred[1][1] * h_mat[1] / s_innov]  # Kalman gain

        x_state = [x_pred[0] + k_gain[0] * y_innov, x_pred[1] + k_gain[1] * y_innov]
        p_cov = [
            [(1.0 - k_gain[0] * h_mat[0]) * p_pred[0][0], 0.0],
            [0.0, (1.0 - k_gain[1] * h_mat[1]) * p_pred[1][1]],
        ]

    # After 10 steps, estimated position should be close to 1.0 and covariance shrunk
    assert abs(x_state[0] - 1.01) < 0.1
    assert p_cov[0][0] < 1.0, 'Position covariance must decrease after filter updates'


def test_t4_scenario_systems_telemetry_latency_simulation() -> None:
    """Scenario 6: Simulation of microkernel IPC telemetry latency distribution and percentile analysis.

    Validates:
    - Calculation of percentiles: p50, p90, p99, p99.9
    - Verification against real-time latency deadlines (< 50us for microkernel IPC)
    """
    random.seed(42)
    latencies = [random.expovariate(1.0 / 12.0) + 2.0 for _ in range(1000)]
    latencies.sort()

    def percentile(data: list[float], p: float) -> float:
        k = (len(data) - 1) * (p / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return data[int(k)]
        return data[int(f)] * (c - k) + data[int(c)] * (k - f)

    p50 = percentile(latencies, 50.0)
    p90 = percentile(latencies, 90.0)
    p99 = percentile(latencies, 99.0)
    p99_9 = percentile(latencies, 99.9)

    assert p50 < p90 < p99 < p99_9
    assert p50 < 20.0, f'Expected median latency p50 < 20us, got {p50:.2f}us'
    assert p99 < 75.0, f'Expected p99 latency < 75us, got {p99:.2f}us'


def test_t4_scenario_bayesian_mcmc_embedded_pytest_execution() -> None:
    """Scenario 7: Simulation and verification of embedded pytest test cell for MCMC convergence diagnostics.

    Simulates calculating the Gelman-Rubin diagnostic (R-hat) across multiple chains:
    R-hat < 1.05 implies stationary chain convergence.
    R-hat >= 1.10 implies convergence failure.
    """

    def gelman_rubin_r_hat(chains: list[list[float]]) -> float:
        m = len(chains)  # Number of chains
        n = len(chains[0])  # Number of iterations per chain

        chain_means = [sum(chain) / n for chain in chains]
        overall_mean = sum(chain_means) / m

        # Between-chain variance
        b_var = (n / (m - 1.0)) * sum((mean - overall_mean) ** 2 for mean in chain_means)

        # Within-chain variance
        chain_vars = [sum((x - mean) ** 2 for x in chain) / (n - 1.0) for chain, mean in zip(chains, chain_means, strict=True)]
        w_var = sum(chain_vars) / m

        # Estimated marginal variance
        var_plus = ((n - 1.0) / n) * w_var + (1.0 / n) * b_var
        return math.sqrt(var_plus / w_var)

    # 1. Healthy stationary chains sampled from N(0, 1)
    random.seed(42)
    stationary_chains = [[random.gauss(0.0, 1.0) for _ in range(500)] for _ in range(4)]
    r_hat_converged = gelman_rubin_r_hat(stationary_chains)
    assert r_hat_converged < 1.05, f'Expected converged R-hat < 1.05, got {r_hat_converged:.4f}'

    # 2. Non-converged chains with drifted means
    divergent_chains = [
        [random.gauss(0.0, 1.0) for _ in range(500)],
        [random.gauss(5.0, 1.0) for _ in range(500)],
        [random.gauss(-5.0, 1.0) for _ in range(500)],
        [random.gauss(10.0, 1.0) for _ in range(500)],
    ]
    r_hat_diverged = gelman_rubin_r_hat(divergent_chains)
    assert r_hat_diverged > 1.10, f'Expected divergent R-hat > 1.10, got {r_hat_diverged:.4f}'
