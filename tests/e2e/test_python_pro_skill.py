"""Opaque-box E2E test suite for the refactored python-pro skill (Issue #32).

Validates the modern Python 3.15/3.14 skill bundle, sibling skill alignment,
repository-wide dogfooding across pyproject/hooks/CI/Renovate/Dependabot, and
live execution of Ruff, Basedpyright, Ty, uv PEP 723 scripts, actionlint,
zizmor, rumdl, and pytest 9+ across four tiers:
- Tier 1: Feature Coverage (33 tests)
- Tier 2: Boundary & Corner Cases (20 tests)
- Tier 3: Cross-Feature Interactions (14 tests)
- Tier 4: Real-World Subprocess Scenarios (11 tests)
Total: 78 E2E tests.
"""

import ast
import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import yaml

from scripts.validation.models import Severity, ValidationReport
from scripts.validation.prompt_validator import validate_prompts
from scripts.validation.secret_hygiene_validator import (
    DRIVE_PATTERN,
    HOME_PATTERN,
    TOKEN_PATTERNS,
    validate_secret_hygiene,
)
from scripts.validation.skills_validator import validate_skills
from scripts.validation.supply_chain_validator import (
    strip_jsonc_comments,
    validate_pre_commit_ci_branch_guard,
    validate_pre_commit_file,
    validate_workflow_file,
)
from tests.e2e.conftest import (
    ALLOWED_SKILL_SUBDIRECTORIES,
    CI_MATRIX_OS,
    CI_WORKFLOW_FILE,
    MAX_FILE_BYTES,
    MIN_SKILL_DESCRIPTION_LENGTH,
    PRE_COMMIT_FILE,
    REPO_ROOT,
    RULESET_STATUS_CHECK_NAME,
    RUN_LOCAL_CI_FILE,
    SKILL_NAME_PATTERN,
    SKILLS_DIR,
    estimate_token_count,
    oracle_validate_ci_workflow,
    oracle_validate_pre_commit_config,
    oracle_validate_skill,
    split_skill_frontmatter,
)


SKILL_DIR = SKILLS_DIR / "python-pro"
SKILL_MD = SKILL_DIR / "SKILL.md"
REFERENCES_DIR = SKILL_DIR / "references"
EXAMPLES_DIR = SKILL_DIR / "examples"

ROOT_PYPROJECT = REPO_ROOT / "pyproject.toml"
ROOT_RENOVATE = REPO_ROOT / "renovate.jsonc"
ROOT_DEPENDABOT = REPO_ROOT / ".github" / "dependabot.yml"
ROOT_README = REPO_ROOT / "README.md"

EXPECTED_RUFF_FAMILIES: set[str] = {
    "E",
    "F",
    "W",
    "I",
    "N",
    "D",
    "DOC",
    "UP",
    "B",
    "SIM",
    "C4",
    "DTZ",
    "PT",
    "RUF",
    "PERF",
    "FURB",
    "S",
    "ANN",
    "ASYNC",
    "PTH",
    "TID",
    "TC",
    "PL",
}

EXPECTED_REFERENCES: tuple[str, ...] = (
    "python_314_315_and_typing.md",
    "packaging_uv_pixi_and_interop.md",
    "style_ruff_testing_and_ci.md",
)

EXPECTED_EXAMPLES: tuple[str, ...] = (
    "pyproject.toml",
    "pixi.toml",
    ".pre-commit-config.yaml",
    "ci.yml",
    "pep723_script.py",
)

RAW_RUFF_CODE_RE = re.compile(r"^[A-Z]+\d+$")
EXPECTED_PRE_COMMIT_SHA = "3e8a8703264a2f4a69428a0aa4dcb512790b2c8c"
HEADROOM_BYTES = 1_000


def _tool_bin(tool_name: str) -> str:
    """Resolve executable path inside the active virtual environment or PATH.

    Args:
        tool_name: Binary name to resolve.

    Returns:
        Absolute executable path for subprocess invocation.
    """
    venv_candidate = Path(sys.executable).with_name(tool_name)
    if venv_candidate.exists():
        return str(venv_candidate)
    resolved = shutil.which(tool_name)
    assert resolved is not None, f"Required CLI tool '{tool_name}' not found in PATH"
    return resolved


def _all_skill_files(directory: Path) -> list[Path]:
    """Return sorted regular files under a skill directory, ignoring caches.

    Args:
        directory: Target directory to traverse.

    Returns:
        Sorted list of regular file paths excluding build/lint caches.
    """
    return sorted(
        p
        for p in directory.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and ".ruff_cache" not in p.parts
    )


def _load_toml(path: Path) -> dict[str, Any]:
    """Load and parse a TOML file into a typed dictionary.

    Args:
        path: Path to the TOML file.

    Returns:
        Parsed top-level TOML table as a dictionary.
    """
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load and parse a YAML mapping file into a typed dictionary.

    Args:
        path: Path to the YAML file.

    Returns:
        Parsed top-level YAML mapping as a dictionary.
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _combined_skill_and_ref_text() -> str:
    """Read SKILL.md and all three reference documents as a combined text view.

    Returns:
        Concatenated UTF-8 contents of SKILL.md and reference documents.
    """
    parts = [SKILL_MD.read_text(encoding="utf-8")]
    parts.extend(
        (REFERENCES_DIR / ref_name).read_text(encoding="utf-8")
        for ref_name in EXPECTED_REFERENCES
    )
    return "\n".join(parts)


# ==============================================================================
# Tier 1: Feature Coverage E2E Tests (33 tests)
# ==============================================================================


def test_t1_01_skill_directory_and_layout() -> None:
    """Verify skills/python-pro directory layout contains allowed entries only."""
    assert SKILL_DIR.is_dir()
    assert SKILL_MD.is_file()
    assert REFERENCES_DIR.is_dir()
    assert EXAMPLES_DIR.is_dir()
    subdirs = {entry.name for entry in SKILL_DIR.iterdir() if entry.is_dir()}
    assert subdirs <= ALLOWED_SKILL_SUBDIRECTORIES
    assert subdirs == {"references", "examples"}
    for forbidden in (".ruff_cache", "__pycache__", "scripts"):
        assert not (SKILL_DIR / forbidden).exists()
    assert not list(SKILL_DIR.rglob("*.ipynb"))


def test_t1_02_skill_frontmatter_v3_and_size() -> None:
    """Verify SKILL.md YAML frontmatter v3, MD041 H1 opener, and byte budget."""
    raw = SKILL_MD.read_text(encoding="utf-8")
    assert raw.startswith("---\n")
    frontmatter, body = split_skill_frontmatter(raw)
    name = frontmatter.get("name")
    description = frontmatter.get("description")
    metadata = frontmatter.get("metadata")
    assert isinstance(name, str)
    assert name == "python-pro"
    assert SKILL_NAME_PATTERN.match(name) is not None
    assert isinstance(metadata, dict)
    assert metadata.get("version") == "v3"
    assert isinstance(description, str)
    assert len(description.strip()) >= MIN_SKILL_DESCRIPTION_LENGTH
    assert body.lstrip().startswith("# ")
    assert len(raw.encode("utf-8")) < MAX_FILE_BYTES - HEADROOM_BYTES


def test_t1_03_skill_python_315_default_and_peps() -> None:
    """Verify SKILL.md specifies Python 3.15 default and covers 3.15 PEPs."""
    text = SKILL_MD.read_text(encoding="utf-8")
    for token in (
        "3.15",
        ">=3.15",
        ">=3.14",
        "PEP 810",
        "lazy import",
        "PEP 814",
        "frozendict",
        "PEP 661",
        "sentinel",
        "PEP 798",
        "PEP 686",
        "PEP 799",
        "profiling.sampling",
        "Tachyon",
    ):
        assert token in text, f"Expected Python 3.15 concept '{token}' in SKILL.md"


def test_t1_04_skill_python_314_floor_peps() -> None:
    """Verify Python 3.14 floor PEPs and native deferred annotation guidance."""
    combined = _combined_skill_and_ref_text()
    for token in (
        "PEP 649",
        "PEP 749",
        "annotationlib",
        "PEP 695",
        "PEP 696",
        "PEP 750",
        't"',
        "PEP 784",
        "compression.zstd",
        "PEP 779",
        "3.14t",
        "3.15t",
        "from __future__ import annotations",
    ):
        assert token in combined, f"Expected Python 3.14 floor feature '{token}'"


def test_t1_05_skill_uv_vs_pixi_decision_criteria() -> None:
    """Verify uv vs pixi matrix covers all six criteria and manifest rule."""
    skill_text = SKILL_MD.read_text(encoding="utf-8")
    pack_ref = (REFERENCES_DIR / "packaging_uv_pixi_and_interop.md").read_text(
        encoding="utf-8"
    )
    combined = f"{skill_text}\n{pack_ref}"
    for term in (
        "uv",
        "pixi",
        "conda-forge",
        "CUDA",
        "pyproject.toml",
        "pixi.toml",
        "uv.lock",
        "pixi.lock",
        "C23",
        "C++23",
        "Rust",
        "SPARK Ada",
    ):
        assert term in combined, f"Missing uv/pixi criterion term '{term}'"
    assert "[tool.pixi.*]" in combined


def test_t1_06_skill_packaging_peps_and_layout() -> None:
    """Verify src layout, py.typed, modern build backends, and PEPs 735/723/751."""
    combined = _combined_skill_and_ref_text()
    for term in (
        "src/",
        "py.typed",
        "uv_build",
        "scikit-build-core",
        "maturin",
        "PEP 735",
        "PEP 723",
        "PEP 751",
        "pylock.toml",
    ):
        assert term in combined, f"Missing packaging requirement '{term}'"


def test_t1_07_skill_marimo_default_and_jupyter_boundary() -> None:
    """Verify Marimo .py default and strict boundary against legacy Jupyter."""
    text = SKILL_MD.read_text(encoding="utf-8")
    assert "marimo" in text.lower()
    assert "/marimo-pro" in text
    assert "/marimo-pair" in text
    assert "/jupyter-pro" in text
    assert ".ipynb" in text
    assert "marimo convert" in text


def test_t1_08_skill_google_style_and_overrides() -> None:
    """Verify Google Python Style Guide baseline with November 2026 overrides."""
    combined = _combined_skill_and_ref_text()
    for token in (
        "Google Python Style Guide",
        "88",
        "double",
        "docstring-code-format = true",
        "grouped",
    ):
        assert token in combined, f"Missing style override token '{token}'"


def test_t1_09_skill_ruff_23_families_and_ruf201() -> None:
    """Verify documentation of all 23 Ruff families, TID251/252, and RUF201."""
    combined = _combined_skill_and_ref_text()
    for family in EXPECTED_RUFF_FAMILIES:
        assert re.search(rf"\b{re.escape(family)}\b", combined) is not None
    assert "TID251" in combined
    assert "TID252" in combined
    assert "ban-relative-imports" in combined
    assert "RUF201" in combined


def test_t1_10_skill_basedpyright_and_ty_replace_mypy() -> None:
    """Verify basedpyright strict + ty check guidance and typing idioms."""
    combined = _combined_skill_and_ref_text()
    for term in (
        "basedpyright",
        "ty check",
        "TypeIs",
        "ReadOnly",
        "TypedDict",
        "@override",
        "@dataclass",
        "slots=True",
        "TaskGroup",
    ):
        assert term in combined, f"Missing typing tool/idiom '{term}'"


def test_t1_11_skill_prek_pytest9_and_supply_chain() -> None:
    """Verify prek, pytest 9+ native config, deptry, pip-audit, zizmor, PEP 740."""
    combined = _combined_skill_and_ref_text()
    for term in (
        "prek",
        "pytest",
        "[tool.pytest]",
        "--doctest-modules",
        "pytest-cov",
        "pytest-randomly",
        "hypothesis",
        "deptry",
        "pip-audit",
        "actionlint",
        "zizmor",
        "OIDC",
        "PEP 740",
    ):
        assert term in combined, f"Missing quality/CI requirement '{term}'"


def test_t1_12_skill_nov2026_ecosystem_and_verification_directive() -> None:
    """Verify November 2026 ecosystem libraries and evergreen verification rule."""
    combined = _combined_skill_and_ref_text()
    for pkg in (
        "polars",
        "duckdb",
        "pyarrow",
        "narwhals",
        "obstore",
        "pydantic",
        "msgspec",
        "httpx",
        "typer",
        "cyclopts",
        "fastapi",
        "jax",
        "equinox",
        "diffrax",
        "nanobind",
        "pyo3",
        "cffi",
        "ctypes",
    ):
        assert pkg in combined.lower(), f"Missing Nov 2026 package '{pkg}'"
    lower = combined.lower()
    assert "verify" in lower
    assert "pypi" in lower


def test_t1_13_references_exist_and_are_well_formed() -> None:
    """Verify all three expected reference documents exist and respect size caps."""
    actual = sorted(p.name for p in REFERENCES_DIR.glob("*.md"))
    assert actual == sorted(EXPECTED_REFERENCES)
    for ref_name in EXPECTED_REFERENCES:
        path = REFERENCES_DIR / ref_name
        content = path.read_text(encoding="utf-8")
        assert len(content.encode("utf-8")) > 500
        assert len(content.encode("utf-8")) < MAX_FILE_BYTES
        assert content.startswith("# ")


def test_t1_14_references_cover_deep_technical_details() -> None:
    """Verify each reference document provides substantive depth for its domain."""
    typing_ref = (REFERENCES_DIR / "python_314_315_and_typing.md").read_text(
        encoding="utf-8"
    )
    pack_ref = (REFERENCES_DIR / "packaging_uv_pixi_and_interop.md").read_text(
        encoding="utf-8"
    )
    style_ref = (REFERENCES_DIR / "style_ruff_testing_and_ci.md").read_text(
        encoding="utf-8"
    )
    assert "annotationlib.get_annotations" in typing_ref
    assert "Format.FORWARDREF" in typing_ref
    assert "RingBuffer" in typing_ref
    assert "Template" in typing_ref
    assert "compression.zstd" in typing_ref
    assert "nanobind" in pack_ref
    assert "pyo3" in pack_ref.lower()
    assert "uv_build" in pack_ref
    assert "pylock.toml" in pack_ref
    assert "RUF201" in style_ref
    assert "prek" in style_ref
    assert 'minversion = "9.0"' in style_ref


def test_t1_15_examples_pyproject_toml_valid_and_315_default() -> None:
    """Verify examples/pyproject.toml parses and defaults to Python 3.15 + uv_build."""
    pyproject_path = EXAMPLES_DIR / "pyproject.toml"
    assert pyproject_path in _all_skill_files(EXAMPLES_DIR)
    data = _load_toml(pyproject_path)
    project = data["project"]
    build_sys = data["build-system"]
    dep_groups = data["dependency-groups"]
    assert isinstance(project, dict)
    assert isinstance(build_sys, dict)
    assert isinstance(dep_groups, dict)
    assert project["requires-python"] == ">=3.15"
    assert "optional-dependencies" not in project
    assert build_sys["build-backend"] == "uv_build"
    all_group_items: list[str] = []
    for group_list in dep_groups.values():
        if isinstance(group_list, list):
            all_group_items.extend(str(item) for item in group_list)
    dev_joined = "\n".join(all_group_items).lower()
    assert "basedpyright" in dev_joined
    assert "ty>=" in dev_joined
    assert "prek" in dev_joined
    assert "pytest>=9" in dev_joined
    assert "mypy" not in dev_joined
    assert "pre-commit" not in dev_joined


def test_t1_16_examples_pyproject_ruff_23_families_and_ruf201() -> None:
    """Verify examples/pyproject.toml Ruff table covers 23 families and RUF201."""
    data = _load_toml(EXAMPLES_DIR / "pyproject.toml")
    ruff = data["tool"]["ruff"]
    lint = ruff["lint"]
    fmt = ruff["format"]
    tidy = lint["flake8-tidy-imports"]
    banned = tidy["banned-api"]
    assert ruff["line-length"] == 88
    assert ruff["target-version"] == "py315"
    assert fmt["quote-style"] == "double"
    assert fmt["docstring-code-format"] is True
    assert set(lint["select"]) == EXPECTED_RUFF_FAMILIES
    assert tidy["ban-relative-imports"] == "all"
    assert "__future__.annotations" in banned
    assert lint["ignore"]
    for selector in lint["ignore"]:
        assert not RAW_RUFF_CODE_RE.match(selector)


def test_t1_17_examples_pyproject_basedpyright_ty_pytest_deptry() -> None:
    """Verify basedpyright, ty, native pytest 9+, coverage, and deptry tables."""
    data = _load_toml(EXAMPLES_DIR / "pyproject.toml")
    tool = data["tool"]
    bp = tool["basedpyright"]
    ty = tool["ty"]
    pt = tool["pytest"]
    cov_run = tool["coverage"]["run"]
    assert bp["typeCheckingMode"] == "strict"
    assert bp["pythonVersion"] == "3.15"
    assert ty["environment"]["python-version"] == "3.15"
    assert pt["minversion"] == "9.0"
    assert pt["strict"] is True
    assert "--doctest-modules" in pt["addopts"]
    assert "--cov=src" in pt["addopts"]
    assert "--cov-branch" in pt["addopts"]
    assert cov_run["branch"] is True
    assert "deptry" in tool
    assert "mypy" not in tool


def test_t1_18_examples_pixi_toml_valid_schema() -> None:
    """Verify examples/pixi.toml parses cleanly and configures Conda + FFI stack."""
    data = _load_toml(EXAMPLES_DIR / "pixi.toml")
    workspace = data["workspace"]
    deps = data["dependencies"]
    tasks = data["tasks"]
    assert workspace["requires-pixi"] == ">=0.84.2"
    assert "conda-forge" in workspace["channels"]
    assert set(workspace["platforms"]) == {"linux-64", "linux-aarch64", "osx-arm64"}
    assert deps["python"] == ">=3.15,<3.16"
    for pkg in ("nanobind", "clang", "clangxx", "cmake", "ninja"):
        assert pkg in deps, f"Missing native/FFI package '{pkg}' in examples/pixi.toml"
    assert "test" in tasks
    assert "lint" in tasks


def test_t1_19_examples_pre_commit_yaml_valid() -> None:
    """Verify examples/.pre-commit-config.yaml configures SHA hooks and uv local hooks."""
    pre_commit_path = EXAMPLES_DIR / ".pre-commit-config.yaml"
    raw = pre_commit_path.read_text(encoding="utf-8")
    assert "pixi" not in raw.lower()
    assert "mypy" not in raw.lower()
    data = _load_yaml(pre_commit_path)
    repos = data["repos"]
    assert isinstance(repos, list)
    hook_ids: list[str] = []
    pinned_rev = None
    for entry in repos:
        assert isinstance(entry, dict)
        if entry.get("repo") == "https://github.com/pre-commit/pre-commit-hooks":
            pinned_rev = entry.get("rev")
        hook_ids.extend(str(hook["id"]) for hook in entry.get("hooks", []))
    assert pinned_rev == EXPECTED_PRE_COMMIT_SHA
    for required_id in (
        "ruff-check",
        "ruff-format",
        "basedpyright",
        "ty",
        "marimo-check",
        "rumdl",
        "actionlint",
        "zizmor",
    ):
        assert required_id in hook_ids


def test_t1_20_examples_ci_yml_valid_matrix() -> None:
    """Verify examples/ci.yml runs locked 3.14/3.15 Ubuntu/macOS prek+QA+pytest."""
    ci_path = EXAMPLES_DIR / "ci.yml"
    raw = ci_path.read_text(encoding="utf-8")
    data = _load_yaml(ci_path)
    assert data["permissions"] == {"contents": "read"}
    job = data["jobs"]["validate-and-test"]
    matrix = job["strategy"]["matrix"]
    assert set(matrix["os"]) == CI_MATRIX_OS
    assert matrix["python-version"] == ["3.14", "3.15"]
    for cmd in (
        "uv lock --check",
        "uv run prek run",
        "uv run ruff check .",
        "uv run basedpyright",
        "uv run ty check",
        "uv run deptry .",
        "uv run pip-audit",
        "uv run pytest",
    ):
        assert cmd in raw


def test_t1_21_examples_pep723_script_metadata_and_ast() -> None:
    """Verify examples/pep723_script.py parses cleanly and showcases 3.14+/3.15 APIs."""
    script_path = EXAMPLES_DIR / "pep723_script.py"
    raw = script_path.read_text(encoding="utf-8")
    assert raw.startswith("#!/usr/bin/env -S uv run --script\n")
    assert "# /// script\n" in raw
    assert '# requires-python = ">=3.14"\n' in raw
    tree = ast.parse(raw, filename=str(script_path))
    assert ast.get_docstring(tree) is not None
    for marker in (
        "__lazy_modules__",
        "SampleBuffer",
        "TypeIs",
        "ReadOnly",
        "Template",
        "compression.zstd",
        "datetime.UTC",
    ):
        assert marker in raw, f"Missing modern Python construct '{marker}'"


def test_t1_22_skill_markdown_links_resolve() -> None:
    """Verify every relative markdown link in SKILL.md resolves to a skill file."""
    raw = SKILL_MD.read_text(encoding="utf-8")
    stripped = re.sub(r"`[^`]+`", "", raw)
    links = re.findall(r"\[[^\]]+\]\(([^)\s]+)\)", stripped)
    local_targets = [
        target
        for target in links
        if not target.startswith(("http://", "https://", "mailto:", "#"))
    ]
    assert len(local_targets) >= len(EXPECTED_REFERENCES) + len(EXPECTED_EXAMPLES)
    for target in local_targets:
        rel_path = target.split("#", 1)[0]
        resolved = (SKILL_DIR / rel_path).resolve()
        assert resolved.is_relative_to(SKILL_DIR.resolve())
        assert resolved.exists(), f"Broken local link in SKILL.md: {target}"


def test_t1_23_root_pyproject_dogfooded_314_and_23_ruff() -> None:
    """Verify root pyproject.toml dogfoods Python >=3.14, 23 Ruff families, ty, prek."""
    data = _load_toml(ROOT_PYPROJECT)
    project = data["project"]
    tool = data["tool"]
    ruff = tool["ruff"]
    lint = ruff["lint"]
    dev_deps = data["dependency-groups"]["dev"]
    dev_str = "\n".join(str(item) for item in dev_deps).lower()
    assert project["requires-python"] == ">=3.14"
    assert ruff["target-version"] == "py314"
    assert set(lint["select"]) == EXPECTED_RUFF_FAMILIES
    assert "__future__.annotations" in lint["flake8-tidy-imports"]["banned-api"]
    assert tool["basedpyright"]["typeCheckingMode"] == "strict"
    assert "ty" in tool
    assert tool["pytest"]["minversion"] == "9.0"
    assert tool["pytest"]["strict"] is True
    assert "mypy" not in dev_str
    assert "pre-commit" not in dev_str
    for pkg in ("basedpyright", "ty>=", "prek", "deptry", "pip-audit", "hypothesis"):
        assert pkg in dev_str


def test_t1_24_root_pre_commit_dogfooded_prek() -> None:
    """Verify root .pre-commit-config.yaml and .prekignore replace mypy cleanly."""
    prekignore = REPO_ROOT / ".prekignore"
    assert prekignore.is_file()
    assert "skills/**/examples/" in prekignore.read_text(encoding="utf-8")
    raw = PRE_COMMIT_FILE.read_text(encoding="utf-8")
    assert "mypy" not in raw.lower()
    data = _load_yaml(PRE_COMMIT_FILE)
    hook_ids: set[str] = set()
    for repo in data["repos"]:
        assert isinstance(repo, dict)
        hook_ids.update(str(hook["id"]) for hook in repo.get("hooks", []))
    for expected in (
        "ruff-check",
        "ruff-format",
        "basedpyright",
        "ty",
        "rumdl",
        "actionlint",
        "zizmor",
        "agentic-settings-validation",
    ):
        assert expected in hook_ids


def test_t1_25_root_local_ci_script_five_gates() -> None:
    """Verify scripts/ci/run_local_ci.sh executes all five dogfooded CI gates."""
    raw = RUN_LOCAL_CI_FILE.read_text(encoding="utf-8")
    for gate in (
        "uv lock --check",
        "uv run prek run",
        "uv run deptry .",
        "uv run pip-audit",
        "uv run pytest",
    ):
        assert gate in raw
    assert "uv run mypy" not in raw
    assert "pre-commit run" not in raw


def test_t1_26_root_ci_workflow_preserves_ruleset_and_adds_315() -> None:
    """Verify root CI workflow preserves ruleset job on 3.14 and adds Python 3.15."""
    raw = CI_WORKFLOW_FILE.read_text(encoding="utf-8")
    data = _load_yaml(CI_WORKFLOW_FILE)
    jobs = data["jobs"]
    assert jobs["validate-and-test"]["name"] == RULESET_STATUS_CHECK_NAME
    assert set(jobs["validate-and-test"]["strategy"]["matrix"]["os"]) == CI_MATRIX_OS
    assert "python-315-matrix" in jobs
    py315_job = jobs["python-315-matrix"]
    assert set(py315_job["strategy"]["matrix"]["os"]) == CI_MATRIX_OS
    assert py315_job["name"] == "Python 3.15 Matrix (${{ matrix.os }})"
    for check in (
        "uv run prek run",
        "basedpyright",
        "ty check",
        "uv run deptry .",
        "uv run pip-audit",
        "uv run --python 3.15 basedpyright",
        "uv run --python 3.15 ty check",
    ):
        assert check in raw


def test_t1_27_root_renovate_and_dependabot_dogfooded() -> None:
    """Verify renovate.jsonc allows >=3.14 <3.16 and dependabot tracks new dev tools."""
    renovate_raw = ROOT_RENOVATE.read_text(encoding="utf-8")
    renovate_data = json.loads(strip_jsonc_comments(renovate_raw))
    assert isinstance(renovate_data, dict)
    allowed_versions = [
        rule.get("allowedVersions")
        for rule in renovate_data.get("packageRules", [])
        if isinstance(rule, dict) and "allowedVersions" in rule
    ]
    assert ">=3.14 <3.16" in allowed_versions

    dependabot_data = _load_yaml(ROOT_DEPENDABOT)
    uv_updates = [
        u for u in dependabot_data["updates"] if u.get("package-ecosystem") == "uv"
    ]
    assert len(uv_updates) == 1
    patterns: list[str] = []
    for group in uv_updates[0]["groups"].values():
        patterns.extend(group.get("patterns", []))
    for dep in ("basedpyright", "ty", "prek", "deptry", "pip-audit", "hypothesis"):
        assert any(p.startswith(dep) for p in patterns), (
            f"Missing '{dep}*' pattern in dependabot uv groups"
        )
    assert all(not p.startswith("mypy") for p in patterns)


def test_t1_28_secret_hygiene_validator_exposes_public_patterns() -> None:
    """Verify public HOME_PATTERN, DRIVE_PATTERN, and TOKEN_PATTERNS contracts."""
    assert isinstance(HOME_PATTERN, re.Pattern)
    assert isinstance(DRIVE_PATTERN, re.Pattern)
    assert isinstance(TOKEN_PATTERNS, (list, tuple))
    assert len(TOKEN_PATTERNS) >= 1
    assert "home" in HOME_PATTERN.pattern
    assert "Users" in HOME_PATTERN.pattern
    assert DRIVE_PATTERN.search("Google" + "Drive/agents/workspace") is not None


def test_t1_29_skill_never_endorses_legacy_tools_for_greenfield() -> None:
    """Verify skill and templates never endorse mypy or pre-commit CLI as primary."""
    for file_path in (
        SKILL_MD,
        EXAMPLES_DIR / "pyproject.toml",
        EXAMPLES_DIR / ".pre-commit-config.yaml",
        EXAMPLES_DIR / "ci.yml",
    ):
        text = file_path.read_text(encoding="utf-8")
        assert "mypy" not in text.lower() or "replaces" in text.lower()
        assert "pre-commit run" not in text


def test_t1_30_skill_decision_trees_runtime_toolchain_notebook_routing() -> None:
    """Verify SKILL.md provides crisp runtime, toolchain, and notebook decision trees."""
    text = SKILL_MD.read_text(encoding="utf-8")
    for token in (
        "Runtime Target Decision Tree",
        'requires-python = ">=3.15"',
        'target-version = "py315"',
        'requires-python = ">=3.14"',
        "sys.version_info >= (3, 15)",
        "PYTHON_GIL=0",
        "Py_MOD_GIL_NOT_USED",
        "Toolchain & Packaging Decision Tree",
        "NEVER mix uv.lock and pixi.lock",
        "examples/pep723_script.py",
        "examples/pyproject.toml",
        "examples/pixi.toml",
        "Interactive Notebook & Skill Routing Decision Tree",
        "marimo._code_mode",
        "uvx marimo convert",
        "/cpp-pro",
        "/rust-pro",
        "/c-pro",
        "/ada-spark-pro",
        "/cmake-pro",
        "/github-flow-lifecycle",
        "/github-ops",
    ):
        assert token in text, f"Missing decision-tree token '{token}' in SKILL.md"


def test_t1_31_three_tier_style_authority_hierarchy() -> None:
    """Verify SKILL.md and style reference define the 3-tier Google style hierarchy."""
    skill_text = SKILL_MD.read_text(encoding="utf-8")
    style_text = (REFERENCES_DIR / "style_ruff_testing_and_ci.md").read_text(
        encoding="utf-8"
    )
    for doc_name, text in (
        ("SKILL.md", skill_text),
        ("style_ruff_testing_and_ci.md", style_text),
    ):
        for marker in (
            "Tier 1",
            "Tier 2",
            "Tier 3",
            "Google Python Style Guide",
            "88",
            "double",
            "grouped",
            "PEP 649",
            "TID251",
            "RUF201",
        ):
            assert marker in text, f"Missing '{marker}' in {doc_name}"


def test_t1_32_references_dual_version_gating_marimo_and_oidc_pep740() -> None:
    """Verify reference docs cover 3.14/3.15 gating, Marimo workflow, and OIDC PEP 740."""
    typing_ref = (REFERENCES_DIR / "python_314_315_and_typing.md").read_text(
        encoding="utf-8"
    )
    pack_ref = (REFERENCES_DIR / "packaging_uv_pixi_and_interop.md").read_text(
        encoding="utf-8"
    )
    style_ref = (REFERENCES_DIR / "style_ruff_testing_and_ci.md").read_text(
        encoding="utf-8"
    )
    for token in (
        "Dual 3.14 / 3.15 Compatibility",
        "sys.version_info >= (3, 15)",
        "__lazy_modules__",
        "MappingProxyType",
        "enum.Enum",
        "sys._is_gil_enabled()",
        "PYTHON_GIL=0",
        "Self",
        "Final",
        "NewType",
    ):
        assert token in typing_ref, f"Missing '{token}' in typing reference"
    for token in (
        "[tool.pixi.workspace]",
        "[tool.pixi.dependencies]",
        "pixi.lock ONLY",
        "scikit_build_core.build",
        "maturin",
        "Marimo-First Notebook Workflows",
        "marimo edit --sandbox",
        "@app.function",
        "uv run marimo check notebooks/",
        "uvx marimo convert",
    ):
        assert token in pack_ref, f"Missing '{token}' in packaging reference"
    for token in (
        "@pytest.mark.unit",
        "@given",
        "PYTHON_GIL=0",
        "3.15t",
        "id-token: write",
        "pypa/gh-action-pypi-publish",
        "attestations: true",
        "PEP 740",
    ):
        assert token in style_ref, f"Missing '{token}' in style/CI reference"


def test_t1_33_examples_refined_contracts() -> None:
    """Verify refined contracts across all five bundled template files."""
    pyproject_raw = (EXAMPLES_DIR / "pyproject.toml").read_text(encoding="utf-8")
    pyproject_data = _load_toml(EXAMPLES_DIR / "pyproject.toml")
    assert "urls" in pyproject_data["project"]
    security_group = "\n".join(pyproject_data["dependency-groups"]["security"])
    assert "actionlint-py>=1.7.12.25" in security_group
    assert "# [tool.pixi.workspace]" in pyproject_raw

    pixi_data = _load_toml(EXAMPLES_DIR / "pixi.toml")
    assert "marimo" in pixi_data["pypi-dependencies"]
    assert "rumdl" in pixi_data["pypi-dependencies"]
    assert pixi_data["tasks"]["notebook-check"] == "marimo check notebooks/"
    assert "markdown-check" in pixi_data["tasks"]

    pre_commit_data = _load_yaml(EXAMPLES_DIR / ".pre-commit-config.yaml")
    hook_entries = [
        hook for repo in pre_commit_data["repos"] for hook in repo.get("hooks", [])
    ]
    deptry_hooks = [h for h in hook_entries if h.get("id") == "deptry"]
    assert len(deptry_hooks) == 1
    assert deptry_hooks[0]["entry"] == "uv run deptry ."

    ci_raw = (EXAMPLES_DIR / "ci.yml").read_text(encoding="utf-8")
    assert "if [ -d notebooks ]; then uv run marimo check notebooks/; fi" in ci_raw
    assert "if [ -d src ]; then uv build --no-sources; fi" in ci_raw

    script_raw = (EXAMPLES_DIR / "pep723_script.py").read_text(encoding="utf-8")
    assert "Self" in script_raw
    assert "def with_payload(self, payload: T) -> Self:" in script_raw
    assert "def runtime_profile() -> dict[str, object]:" in script_raw
    assert "sys.version_info >= (3, 15)" in script_raw


# ==============================================================================
# Tier 2: Boundary & Corner Cases (20 tests)
# ==============================================================================


def test_t2_01_oracle_validate_skill_zero_issues() -> None:
    """Verify independent oracle validator reports zero issues for python-pro."""
    issues = oracle_validate_skill(SKILL_DIR)
    assert issues == []


def test_t2_02_production_validate_skills_zero_issues() -> None:
    """Verify production skill validator passes cleanly on skills/python-pro."""
    report = ValidationReport()
    validate_skills(REPO_ROOT, report)
    relevant = [
        issue
        for issue in report.issues
        if "python-pro" in str(issue.path) and issue.severity <= Severity.WARNING
    ]
    assert relevant == []


def test_t2_03_validate_example_pre_commit_config() -> None:
    """Verify production and oracle validators both accept examples/.pre-commit-config.yaml."""
    example_pc = EXAMPLES_DIR / ".pre-commit-config.yaml"
    assert oracle_validate_pre_commit_config(_load_yaml(example_pc), example_pc) == []
    report = ValidationReport()
    validate_pre_commit_file(example_pc, report)
    errors_or_warnings = [i for i in report.issues if i.severity <= Severity.WARNING]
    assert errors_or_warnings == []


def test_t2_04_validate_example_ci_workflow() -> None:
    """Verify production and oracle validators accept examples/ci.yml supply chain."""
    example_ci = EXAMPLES_DIR / "ci.yml"
    assert oracle_validate_ci_workflow(_load_yaml(example_ci), example_ci) == []
    report = ValidationReport()
    validate_workflow_file(example_ci, report)
    errors_or_warnings = [i for i in report.issues if i.severity <= Severity.WARNING]
    assert errors_or_warnings == []


def test_t2_05_examples_pre_commit_has_zero_pixi_references() -> None:
    """Verify bundled example pre-commit config stays pure uv without pixi."""
    raw = (EXAMPLES_DIR / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "pixi" not in raw.lower()


def test_t2_06_zero_future_annotations_across_repo_python() -> None:
    """Verify zero Python files across scripts, tests, and example script import __future__.annotations."""
    candidates = [
        EXAMPLES_DIR / "pep723_script.py",
        *(REPO_ROOT / "scripts").rglob("*.py"),
        *(REPO_ROOT / "tests").rglob("*.py"),
    ]
    offenders: list[str] = []
    for py_file in candidates:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "__future__":
                offenders.extend(
                    str(py_file.relative_to(REPO_ROOT))
                    for alias in node.names
                    if alias.name == "annotations"
                )
    assert offenders == []


def test_t2_07_live_ruff_rejects_future_annotations(tmp_path: Path) -> None:
    """Verify example Ruff config actively rejects from __future__ import annotations (TID251).

    Args:
        tmp_path: Ephemeral test directory managed by pytest.
    """
    bad_file = tmp_path / "src" / "pkg" / "bad_future.py"
    bad_file.parent.mkdir(parents=True)
    bad_file.write_text(
        '"""Trigger banned future import."""\n\n'
        "from __future__ import annotations\n\n\n"
        "def echo(value: str) -> str:\n"
        '    """Return input text."""\n'
        "    return value\n",
        encoding="utf-8",
    )
    res = subprocess.run(
        [
            _tool_bin("ruff"),
            "check",
            "--output-format=json",
            "--config",
            str(EXAMPLES_DIR / "pyproject.toml"),
            str(bad_file),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode != 0
    diagnostics = json.loads(res.stdout)
    assert "TID251" in {item["code"] for item in diagnostics}


def test_t2_08_live_ruff_rejects_relative_imports(tmp_path: Path) -> None:
    """Verify example Ruff config rejects relative imports (TID252).

    Args:
        tmp_path: Ephemeral test directory managed by pytest.
    """
    pkg_dir = tmp_path / "src" / "pkg"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "__init__.py").write_text('"""Package."""\n', encoding="utf-8")
    (pkg_dir / "helper.py").write_text('"""Helper."""\n\nX = 1\n', encoding="utf-8")
    mod = pkg_dir / "consumer.py"
    mod.write_text(
        '"""Trigger banned relative import."""\n\n'
        "from . import helper\n\n"
        "VALUE = helper.X\n",
        encoding="utf-8",
    )
    res = subprocess.run(
        [
            _tool_bin("ruff"),
            "check",
            "--output-format=json",
            "--config",
            str(EXAMPLES_DIR / "pyproject.toml"),
            str(mod),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode != 0
    diagnostics = json.loads(res.stdout)
    assert "TID252" in {item["code"] for item in diagnostics}


def test_t2_09_live_ruff_rejects_production_assert(tmp_path: Path) -> None:
    """Verify example Ruff config forbids runtime assert in production src code (S101).

    Args:
        tmp_path: Ephemeral test directory managed by pytest.
    """
    src_file = tmp_path / "src" / "pkg" / "guard.py"
    src_file.parent.mkdir(parents=True)
    src_file.write_text(
        '"""Trigger S101 in non-test code."""\n\n\n'
        "def check_positive(num: int) -> int:\n"
        '    """Validate input is positive.\n\n'
        "    Args:\n"
        "        num: Positive number.\n\n"
        "    Returns:\n"
        "        Validated integer.\n"
        '    """\n'
        "    assert num > 0\n"
        "    return num\n",
        encoding="utf-8",
    )
    res = subprocess.run(
        [
            _tool_bin("ruff"),
            "check",
            "--output-format=json",
            "--config",
            str(EXAMPLES_DIR / "pyproject.toml"),
            str(src_file),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode != 0
    diagnostics = json.loads(res.stdout)
    assert "S101" in {item["code"] for item in diagnostics}


def test_t2_10_live_ruff_accepts_python315_frozendict_and_tstrings(
    tmp_path: Path,
) -> None:
    """Verify example Ruff config accepts Python 3.15 lazy import, frozendict, t-strings, PEP 696.

    Args:
        tmp_path: Ephemeral test directory managed by pytest.
    """
    good_file = tmp_path / "src" / "modern_demo.py"
    good_file.parent.mkdir(parents=True)
    good_file.write_text(
        '"""Verify Python 3.15 features lint cleanly under py315 Ruff rules."""\n\n'
        "from typing import TYPE_CHECKING\n"
        "lazy import json\n\n\n"
        "if TYPE_CHECKING:\n"
        "    from string.templatelib import Template\n\n\n"
        "class Holder[T = str]:\n"
        '    """Generic container with PEP 696 default."""\n\n'
        "    def __init__(self, item: T) -> None:\n"
        '        """Initialize container."""\n'
        "        self.item = item\n\n\n"
        "def make_greeting(user: str) -> tuple[Template, object, str]:\n"
        '    """Return a PEP 750 template, PEP 814 frozendict, and lazy JSON string."""\n'
        '    tmpl = t"Hello, {user}"\n'
        '    meta = frozendict({"user": user})\n'
        '    encoded = json.dumps({"user": user})\n'
        "    return tmpl, meta, encoded\n",
        encoding="utf-8",
    )
    res = subprocess.run(
        [
            _tool_bin("ruff"),
            "check",
            "--config",
            str(EXAMPLES_DIR / "pyproject.toml"),
            str(good_file),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr


def test_t2_11_secret_hygiene_and_personal_path_scan() -> None:
    """Verify zero leaked tokens, OS home paths, or drive paths across python-pro."""
    for file_path in _all_skill_files(SKILL_DIR):
        content = file_path.read_text(encoding="utf-8")
        assert HOME_PATTERN.search(content) is None, f"Home path in {file_path}"
        assert DRIVE_PATTERN.search(content) is None, f"Drive path in {file_path}"
        for pattern in TOKEN_PATTERNS:
            assert pattern.search(content) is None, f"Token pattern in {file_path}"
    report = ValidationReport()
    validate_secret_hygiene(REPO_ROOT, report)
    python_skill_hits = [
        issue
        for issue in report.issues
        if "python-pro" in str(issue.path) and issue.severity <= Severity.WARNING
    ]
    assert python_skill_hits == []


def test_t2_12_lf_line_endings_and_trailing_newline() -> None:
    """Verify all files in skills/python-pro use LF line endings and non-zero size."""
    files = _all_skill_files(SKILL_DIR)
    assert len(files) == 1 + len(EXPECTED_REFERENCES) + len(EXPECTED_EXAMPLES)
    for file_path in files:
        raw_bytes = file_path.read_bytes()
        assert len(raw_bytes) > 0
        assert b"\r" not in raw_bytes, f"CR byte found in {file_path}"
        assert raw_bytes.endswith(b"\n"), f"Missing trailing newline in {file_path}"


def test_t2_13_skill_md_token_headroom() -> None:
    """Verify SKILL.md stays compact in bytes and token budget."""
    text = SKILL_MD.read_text(encoding="utf-8")
    byte_len = len(text.encode("utf-8"))
    tokens = estimate_token_count(text)
    assert byte_len < MAX_FILE_BYTES - HEADROOM_BYTES
    assert tokens < 6_000


def test_t2_14_markdown_heading_and_fence_balance() -> None:
    """Verify H1 top-level headings and balanced code fences across python-pro docs."""
    docs = [SKILL_MD, *(REFERENCES_DIR / name for name in EXPECTED_REFERENCES)]
    for doc in docs:
        text = doc.read_text(encoding="utf-8")
        if doc == SKILL_MD:
            _, body = split_skill_frontmatter(text)
        else:
            body = text
        non_empty = [line for line in body.splitlines() if line.strip()]
        assert non_empty[0].startswith("# "), f"Missing MD041 H1 in {doc.name}"
        fence_count = sum(
            1 for line in body.splitlines() if line.lstrip().startswith("```")
        )
        assert fence_count % 2 == 0, f"Unbalanced code fences in {doc.name}"


def test_t2_15_ruff_ignores_strictly_follow_ruf201_full_names() -> None:
    """Verify both root and example pyproject.toml avoid raw alphanumeric ignore codes."""
    for toml_path in (ROOT_PYPROJECT, EXAMPLES_DIR / "pyproject.toml"):
        lint = _load_toml(toml_path)["tool"]["ruff"]["lint"]
        for selector in lint.get("ignore", []):
            assert RAW_RUFF_CODE_RE.match(selector) is None, (
                f"Raw Ruff code '{selector}' in {toml_path} ignore"
            )
        for pattern, selectors in lint.get("per-file-ignores", {}).items():
            for selector in selectors:
                assert RAW_RUFF_CODE_RE.match(selector) is None, (
                    f"Raw Ruff code '{selector}' under '{pattern}' in {toml_path}"
                )


def test_t2_16_examples_pyproject_uses_pep735_not_optional_dev_extras() -> None:
    """Verify examples/pyproject.toml uses PEP 735 dependency-groups over extras."""
    data = _load_toml(EXAMPLES_DIR / "pyproject.toml")
    project = data["project"]
    groups = data["dependency-groups"]
    assert "optional-dependencies" not in project
    assert "dev" in groups


def test_t2_17_secret_hygiene_skips_basedpyright_and_ty_caches(tmp_path: Path) -> None:
    """Verify secret hygiene ignores .basedpyright and .ty_cache cache directories.

    Args:
        tmp_path: Ephemeral workspace copy for cache-exclusion verification.
    """
    for cache_dir in (".basedpyright", ".ty_cache"):
        target = tmp_path / cache_dir / "state.json"
        target.parent.mkdir(parents=True)
        target.write_text('{"path": "/Users/secretuser/work"}\n', encoding="utf-8")
    report = ValidationReport()
    validate_secret_hygiene(tmp_path, report)
    assert report.issues == []


def test_t2_18_supply_chain_sup003_accepts_prek_and_flags_missing(
    tmp_path: Path,
) -> None:
    """Verify SUP003 validator enforces SKIP: no-commit-to-branch for prek on main.

    Args:
        tmp_path: Ephemeral workspace root holding sample CI workflow.
    """
    pre_commit = tmp_path / ".pre-commit-config.yaml"
    pre_commit.write_text(
        "repos:\n"
        "  - repo: https://github.com/pre-commit/pre-commit-hooks\n"
        "    rev: 3e8a8703264a2f4a69428a0aa4dcb512790b2c8c\n"
        "    hooks:\n"
        "      - id: no-commit-to-branch\n"
        "        args: [--branch, main]\n",
        encoding="utf-8",
    )
    wf = tmp_path / ".github" / "workflows" / "ci.yml"
    wf.parent.mkdir(parents=True)
    wf.write_text(
        "name: CI\n"
        "on:\n"
        "  push:\n"
        "    branches:\n"
        "      - main\n"
        "permissions:\n"
        "  contents: read\n"
        "jobs:\n"
        "  lint:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1\n"
        "        with:\n"
        "          persist-credentials: false\n"
        "      - env:\n"
        "          SKIP: no-commit-to-branch\n"
        "        run: uv run prek run --all-files\n",
        encoding="utf-8",
    )
    report_ok = ValidationReport()
    validate_pre_commit_ci_branch_guard(tmp_path, report_ok)
    assert [i for i in report_ok.issues if str(i.code) == "SUP003"] == []

    wf.write_text(
        wf.read_text(encoding="utf-8").replace(
            "env:\n          SKIP: no-commit-to-branch\n        ", ""
        ),
        encoding="utf-8",
    )
    report_missing = ValidationReport()
    validate_pre_commit_ci_branch_guard(tmp_path, report_missing)
    assert len([i for i in report_missing.issues if str(i.code) == "SUP003"]) == 1


def test_t2_19_references_markdown_links_and_byte_headroom() -> None:
    """Verify reference docs preserve byte headroom and resolve all relative links."""
    local_link_count = 0
    for ref_name in EXPECTED_REFERENCES:
        ref_path = REFERENCES_DIR / ref_name
        raw = ref_path.read_text(encoding="utf-8")
        assert len(raw.encode("utf-8")) < MAX_FILE_BYTES - HEADROOM_BYTES
        assert estimate_token_count(raw) < 6_000
        no_fences = re.sub(r"```.*?```", "", raw, flags=re.DOTALL)
        stripped = re.sub(r"`[^`\n]+`", "", no_fences)
        links = re.findall(r"\[[^\]]+\]\(([^)\s]+)\)", stripped)
        for target in links:
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            rel_path = target.split("#", 1)[0]
            resolved = (ref_path.parent / rel_path).resolve()
            assert resolved.is_relative_to(SKILL_DIR.resolve())
            assert resolved.exists(), f"Broken local link in {ref_name}: {target}"
            local_link_count += 1
    assert local_link_count >= len(EXPECTED_EXAMPLES)


def test_t2_20_example_pyproject_keeps_existing_include_dirs_and_single_lockfile() -> (
    None
):
    """Verify example pyproject avoids nonexistent typecheck dirs and active pixi tables."""
    data = _load_toml(EXAMPLES_DIR / "pyproject.toml")
    tool = data["tool"]
    assert tool["basedpyright"]["include"] == ["src", "tests"]
    assert tool["ty"]["src"]["include"] == ["src", "tests"]
    assert "pixi" not in tool
    pixi_raw = (EXAMPLES_DIR / "pixi.toml").read_text(encoding="utf-8")
    assert "never mix uv.lock and pixi.lock" in pixi_raw


# ==============================================================================
# Tier 3: Cross-Feature Interactions (14 tests)
# ==============================================================================


def test_t3_01_jupyter_pro_skill_v3_scope_and_validation() -> None:
    """Verify jupyter-pro is scoped strictly to legacy .ipynb/Colab and passes oracle."""
    jup_dir = SKILLS_DIR / "jupyter-pro"
    jup_md = jup_dir / "SKILL.md"
    raw = jup_md.read_text(encoding="utf-8")
    frontmatter, body = split_skill_frontmatter(raw)
    metadata = frontmatter.get("metadata")
    assert isinstance(metadata, dict)
    assert metadata.get("version") == "v3"
    assert len(raw.encode("utf-8")) < MAX_FILE_BYTES
    assert oracle_validate_skill(jup_dir) == []
    assert body.lstrip().startswith("# ")
    for term in (
        "/python-pro",
        "/marimo-pro",
        "/marimo-pair",
        ".ipynb",
        "Colab",
        "marimo convert",
        "pip",
        "uv run",
    ):
        assert term in raw


def test_t3_02_marimo_pro_and_marimo_pair_bidirectional_links() -> None:
    """Verify bidirectional references between python-pro and marimo skills."""
    py_text = SKILL_MD.read_text(encoding="utf-8")
    marimo_text = (SKILLS_DIR / "marimo-pro" / "SKILL.md").read_text(encoding="utf-8")
    assert "/marimo-pro" in py_text
    assert "/marimo-pair" in py_text
    assert "/python-pro" in marimo_text


def test_t3_03_ffi_sibling_skills_alignment() -> None:
    """Verify systems and build sibling skills align with modern python-pro FFI."""
    for skill_name in (
        "cpp-pro",
        "rust-pro",
        "c-pro",
        "ada-spark-pro",
        "cmake-pro",
    ):
        sibling_text = (SKILLS_DIR / skill_name / "SKILL.md").read_text(
            encoding="utf-8"
        )
        assert "/python-pro" in sibling_text or "python-pro" in sibling_text, (
            f"Missing /python-pro link in {skill_name}"
        )


def test_t3_04_github_flow_and_ops_skills_alignment() -> None:
    """Verify github-flow-lifecycle and github-ops reference prek/basedpyright/ty."""
    flow_text = (SKILLS_DIR / "github-flow-lifecycle" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    matrix_text = (
        SKILLS_DIR / "github-flow-lifecycle" / "references" / "local-ci-matrix.md"
    ).read_text(encoding="utf-8")
    ops_text = (SKILLS_DIR / "github-ops" / "SKILL.md").read_text(encoding="utf-8")
    assert "prek" in flow_text
    assert "basedpyright" in flow_text
    assert "ty check" in flow_text
    assert "prek" in matrix_text
    assert "basedpyright" in matrix_text
    assert "ty" in matrix_text
    assert "mypy" not in flow_text.lower()
    assert "mypy" not in matrix_text.lower()
    assert "python-pro" in ops_text


def test_t3_05_readme_reflects_python_pro_and_local_ci() -> None:
    """Verify root README reflects refactored python-pro, jupyter-pro, and prek CI."""
    readme = ROOT_README.read_text(encoding="utf-8")
    assert "python-pro" in readme
    assert "3.15" in readme
    assert "basedpyright" in readme
    assert "prek" in readme
    assert "jupyter-pro" in readme


def test_t3_06_validate_prompts_across_python_and_jupyter_skills() -> None:
    """Verify prompt validator finds zero errors or warnings on python-pro/jupyter-pro."""
    report = ValidationReport()
    validate_prompts(REPO_ROOT, report)
    flagged = [
        issue
        for issue in report.issues
        if ("python-pro" in str(issue.path) or "jupyter-pro" in str(issue.path))
        and issue.severity <= Severity.WARNING
    ]
    assert flagged == []


def test_t3_07_cross_file_consistency_ruff_root_vs_example() -> None:
    """Verify root pyproject.toml and example template share identical Ruff baselines."""
    root_ruff = _load_toml(ROOT_PYPROJECT)["tool"]["ruff"]
    ex_ruff = _load_toml(EXAMPLES_DIR / "pyproject.toml")["tool"]["ruff"]
    assert root_ruff["line-length"] == ex_ruff["line-length"] == 88
    assert root_ruff["format"]["quote-style"] == ex_ruff["format"]["quote-style"]
    assert (
        root_ruff["format"]["docstring-code-format"]
        == ex_ruff["format"]["docstring-code-format"]
        is True
    )
    assert set(root_ruff["lint"]["select"]) == set(ex_ruff["lint"]["select"])
    assert (
        root_ruff["lint"]["flake8-tidy-imports"]["ban-relative-imports"]
        == ex_ruff["lint"]["flake8-tidy-imports"]["ban-relative-imports"]
        == "all"
    )


def test_t3_08_cross_file_consistency_python_floor_vs_ci_and_renovate() -> None:
    """Verify root >=3.14 floor harmonizes with CI 3.14/3.15 jobs and Renovate range."""
    root_req = _load_toml(ROOT_PYPROJECT)["project"]["requires-python"]
    ex_req = _load_toml(EXAMPLES_DIR / "pyproject.toml")["project"]["requires-python"]
    ci_raw = CI_WORKFLOW_FILE.read_text(encoding="utf-8")
    renovate_raw = ROOT_RENOVATE.read_text(encoding="utf-8")
    assert root_req == ">=3.14"
    assert ex_req == ">=3.15"
    assert "3.14" in ci_raw
    assert "3.15" in ci_raw
    assert ">=3.14 <3.16" in renovate_raw


def test_t3_09_cross_file_consistency_hooks_vs_ci_commands() -> None:
    """Verify both root and example hook configs pair with matching CI commands."""
    ex_pc = (EXAMPLES_DIR / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    ex_ci = (EXAMPLES_DIR / "ci.yml").read_text(encoding="utf-8")
    root_pc = PRE_COMMIT_FILE.read_text(encoding="utf-8")
    root_ci = CI_WORKFLOW_FILE.read_text(encoding="utf-8")
    for tool in ("basedpyright", "ty check", "ruff check", "actionlint", "zizmor"):
        assert tool in ex_pc
        assert tool in root_pc
    assert "prek run" in ex_ci
    assert "prek run" in root_ci


def test_t3_10_pixi_toml_cross_skill_toolchain_parity() -> None:
    """Verify examples/pixi.toml matches mimir-agent-kit Pixi 0.84.2+/clang conventions."""
    pixi = _load_toml(EXAMPLES_DIR / "pixi.toml")
    assert pixi["workspace"]["requires-pixi"] == ">=0.84.2"
    assert "conda-forge" in pixi["workspace"]["channels"]
    assert "nanobind" in pixi["dependencies"]
    assert "clang" in pixi["dependencies"]
    assert "cmake" in pixi["dependencies"]


def test_t3_11_example_pep723_script_aligns_with_skill_rules() -> None:
    """Verify example PEP 723 script uses zero banned imports and modern stdlib APIs."""
    script_raw = (EXAMPLES_DIR / "pep723_script.py").read_text(encoding="utf-8")
    tree = ast.parse(script_raw)
    future_imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "__future__"
    ]
    assert future_imports == []
    assert 'encoding="utf-8"' in script_raw
    assert "datetime.UTC" in script_raw
    assert "t'" in script_raw or 't"' in script_raw
    assert "compression.zstd" in script_raw
    assert "TypeIs" in script_raw
    assert "ReadOnly" in script_raw


def test_t3_12_full_repo_plugin_validators_clean() -> None:
    """Verify full-repo skills and secret hygiene validators report zero issues."""
    report = ValidationReport()
    validate_skills(REPO_ROOT, report)
    validate_secret_hygiene(REPO_ROOT, report)
    errors_or_warnings = [i for i in report.issues if i.severity <= Severity.WARNING]
    assert errors_or_warnings == []


def test_t3_13_cross_file_style_hierarchy_alignment() -> None:
    """Verify 3-tier style hierarchy rules match across docs, example, and root configs."""
    style_text = (REFERENCES_DIR / "style_ruff_testing_and_ci.md").read_text(
        encoding="utf-8"
    )
    assert "lines-after-imports = 2" in style_text
    assert 'convention = "google"' in SKILL_MD.read_text(encoding="utf-8")
    for toml_path in (ROOT_PYPROJECT, EXAMPLES_DIR / "pyproject.toml"):
        ruff = _load_toml(toml_path)["tool"]["ruff"]
        lint = ruff["lint"]
        assert ruff["line-length"] == 88
        assert ruff["format"]["quote-style"] == "double"
        assert ruff["format"]["docstring-code-format"] is True
        assert lint["isort"]["lines-after-imports"] == 2
        assert lint["pydocstyle"]["convention"] == "google"
        assert lint["flake8-tidy-imports"]["ban-relative-imports"] == "all"
        assert "__future__.annotations" in lint["flake8-tidy-imports"]["banned-api"]


def test_t3_14_cross_file_examples_ci_hooks_and_pixi_task_parity() -> None:
    """Verify examples/ci.yml, .pre-commit-config.yaml, and pixi.toml share QA gates."""
    ex_ci = (EXAMPLES_DIR / "ci.yml").read_text(encoding="utf-8")
    ex_pc = (EXAMPLES_DIR / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    ex_pixi = _load_toml(EXAMPLES_DIR / "pixi.toml")
    pixi_tasks = "\n".join(str(val) for val in ex_pixi["tasks"].values())
    for tool in ("ruff check", "basedpyright", "ty check", "deptry", "marimo check"):
        assert tool in ex_ci
        assert tool in ex_pc
        assert tool in pixi_tasks
    for audit_tool in ("pip-audit", "pytest"):
        assert audit_tool in ex_ci
        assert audit_tool in pixi_tasks
    assert "rumdl" in ex_pc
    assert "rumdl" in pixi_tasks


# ==============================================================================
# Tier 4: Real-World Subprocess Scenarios (11 tests)
# ==============================================================================


def test_t4_01_live_ruff_check_and_format_on_pep723_script() -> None:
    """Run live ruff check and format check on pep723_script.py via example config."""
    ruff_bin = _tool_bin("ruff")
    config = str(EXAMPLES_DIR / "pyproject.toml")
    script = str(EXAMPLES_DIR / "pep723_script.py")
    check_res = subprocess.run(
        [ruff_bin, "check", "--config", config, script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert check_res.returncode == 0, check_res.stdout + check_res.stderr
    fmt_res = subprocess.run(
        [ruff_bin, "format", "--check", "--config", config, script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert fmt_res.returncode == 0, fmt_res.stdout + fmt_res.stderr


def test_t4_02_live_basedpyright_on_pep723_script() -> None:
    """Run live strict basedpyright analysis on examples/pep723_script.py."""
    res = subprocess.run(
        [_tool_bin("basedpyright"), str(EXAMPLES_DIR / "pep723_script.py")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert "0 errors" in res.stdout


def test_t4_03_live_ty_check_on_pep723_script() -> None:
    """Run live Astral ty type check on examples/pep723_script.py."""
    res = subprocess.run(
        [_tool_bin("ty"), "check", str(EXAMPLES_DIR / "pep723_script.py")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr


def test_t4_04_live_pep723_script_self_test_and_json_output(tmp_path: Path) -> None:
    """Execute examples/pep723_script.py via uv --script --self-test and verify JSON.

    Args:
        tmp_path: Ephemeral directory for JSON audit output verification.
    """
    out_file = tmp_path / "audit.json"
    res = subprocess.run(
        [
            _tool_bin("uv"),
            "run",
            "--offline",
            "--script",
            str(EXAMPLES_DIR / "pep723_script.py"),
            "--self-test",
            "--output",
            str(out_file),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert out_file.is_file()
    payload = json.loads(out_file.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    assert payload["event_id"] == "telemetry-01"
    assert isinstance(payload["bytes_compressed"], int)
    assert payload["bytes_compressed"] > 0
    assert "+00:00" in payload["recorded_utc"] or payload["recorded_utc"].endswith("Z")


def test_t4_05_live_actionlint_and_zizmor_on_example_ci() -> None:
    """Run live actionlint and zizmor workflow audits on examples/ci.yml."""
    ci_str = str(EXAMPLES_DIR / "ci.yml")
    al_res = subprocess.run(
        [_tool_bin("actionlint"), ci_str],
        capture_output=True,
        text=True,
        check=False,
    )
    assert al_res.returncode == 0, al_res.stdout + al_res.stderr
    zm_res = subprocess.run(
        [_tool_bin("zizmor"), "--strict-collection", "--min-severity=low", ci_str],
        capture_output=True,
        text=True,
        check=False,
    )
    assert zm_res.returncode == 0, zm_res.stdout + zm_res.stderr


def test_t4_06_live_rumdl_markdown_lint_on_refactored_skills() -> None:
    """Run live rumdl markdown linter without exclusions on python-pro and jupyter-pro."""
    res = subprocess.run(
        [
            _tool_bin("rumdl"),
            "check",
            "--no-exclude",
            str(SKILL_DIR),
            str(SKILLS_DIR / "jupyter-pro"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr


def test_t4_07_live_materialized_project_ruff_types_pytest9_cov_doctest(
    tmp_path: Path,
) -> None:
    """Materialize a minimal src/ project from example pyproject and run full QA.

    Args:
        tmp_path: Ephemeral workspace root holding materialized src package and tests.
    """
    ex_pyproject = (EXAMPLES_DIR / "pyproject.toml").read_text(encoding="utf-8")
    adapted = ex_pyproject.replace('>=3.15"', '>=3.14"').replace('"py315"', '"py314"')
    adapted = adapted.replace('pythonVersion = "3.15"', 'pythonVersion = "3.14"')
    adapted = adapted.replace('python-version = "3.15"', 'python-version = "3.14"')
    (tmp_path / "pyproject.toml").write_text(adapted, encoding="utf-8")

    pkg_dir = tmp_path / "src" / "example_pkg"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "py.typed").write_text("", encoding="utf-8")
    (pkg_dir / "__init__.py").write_text(
        '"""Example modern package."""\n\n'
        "from example_pkg.core import scale_value\n\n\n"
        '__all__ = ["scale_value"]\n',
        encoding="utf-8",
    )
    (pkg_dir / "core.py").write_text(
        '"""Core calculation module with passing doctest."""\n\n\n'
        "def scale_value(value: int, factor: int = 2) -> int:\n"
        '    """Scale an integer by a positive factor.\n\n'
        "    Args:\n"
        "        value: Input integer.\n"
        "        factor: Multiplication factor.\n\n"
        "    Returns:\n"
        "        Scaled integer value.\n\n"
        "    Examples:\n"
        "        >>> scale_value(3, 4)\n"
        "        12\n"
        '    """\n'
        "    return value * factor\n",
        encoding="utf-8",
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_core.py").write_text(
        '"""Unit tests for example_pkg."""\n\n'
        "from example_pkg import scale_value\n\n\n"
        "def test_scale_value_default() -> None:\n"
        '    """Verify default doubling behavior."""\n'
        "    assert scale_value(5) == 10\n",
        encoding="utf-8",
    )

    for cmd in (
        [_tool_bin("ruff"), "check", "."],
        [_tool_bin("basedpyright")],
        [_tool_bin("ty"), "check"],
        [_tool_bin("pytest"), "-p", "no:cacheprovider"],
    ):
        res = subprocess.run(
            cmd,
            cwd=tmp_path,
            env={"PATH": str(Path(sys.executable).parent), "PYTHONPATH": "src"},
            capture_output=True,
            text=True,
            check=False,
        )
        assert res.returncode == 0, f"{cmd} failed:\n{res.stdout}\n{res.stderr}"


def test_t4_08_live_uv_lock_check_clean() -> None:
    """Verify repository uv.lock is synchronized cleanly with pyproject.toml."""
    res = subprocess.run(
        [_tool_bin("uv"), "lock", "--check", "--offline"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr


def test_t4_09_live_validate_agentic_settings_strict() -> None:
    """Execute strict agentic settings CLI across entire repository."""
    res = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "validate_agentic_settings.py"),
            "--strict",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr


def test_t4_10_live_ruff_format_check_on_skill_and_reference_markdown() -> None:
    """Run live ruff format --check on SKILL.md and reference Markdown code fences."""
    targets = [
        str(SKILL_MD),
        *(str(REFERENCES_DIR / ref_name) for ref_name in EXPECTED_REFERENCES),
    ]
    res = subprocess.run(
        [
            _tool_bin("ruff"),
            "format",
            "--check",
            "--config",
            str(ROOT_PYPROJECT),
            *targets,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr


def test_t4_11_live_actionlint_and_zizmor_on_reference_release_workflow(
    tmp_path: Path,
) -> None:
    """Run live actionlint and zizmor on the PyPI OIDC PEP 740 workflow snippet.

    Args:
        tmp_path: Ephemeral directory holding extracted workflow YAML.
    """
    style_text = (REFERENCES_DIR / "style_ruff_testing_and_ci.md").read_text(
        encoding="utf-8"
    )
    yaml_blocks = re.findall(r"```yaml\n(.*?)```", style_text, flags=re.DOTALL)
    release_blocks = [b for b in yaml_blocks if "name: Release to PyPI" in b]
    assert len(release_blocks) == 1
    wf_path = tmp_path / "release.yml"
    wf_path.write_text(release_blocks[0], encoding="utf-8")

    al_res = subprocess.run(
        [_tool_bin("actionlint"), str(wf_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert al_res.returncode == 0, al_res.stdout + al_res.stderr
    zm_res = subprocess.run(
        [
            _tool_bin("zizmor"),
            "--strict-collection",
            "--min-severity=low",
            str(wf_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert zm_res.returncode == 0, zm_res.stdout + zm_res.stderr
