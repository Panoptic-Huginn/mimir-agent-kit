"""Opaque-box E2E test suite for the cmake-pro AntiGravity 2.29.0+ skill.

Validates the modern November 2026 CMake 4.5+ & Pixi 0.84.2+ skill package across:
- Tier 1: Feature Coverage (>= 25 tests)
- Tier 2: Boundary & Corner Cases (>= 20 tests)
- Tier 3: Cross-Feature & Sibling Interactions (>= 12 tests)
- Tier 4: Real-World Scenarios & Live Tooling (>= 6 tests)
"""

import json
import os
import re
import shutil
import subprocess
import tomllib
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import pytest
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
from tests.e2e.conftest import (
    ALLOWED_SKILL_SUBDIRECTORIES,
    MAX_FILE_BYTES,
    MIN_SKILL_DESCRIPTION_LENGTH,
    REPO_ROOT,
    SKILL_NAME_PATTERN,
    SKILLS_DIR,
    oracle_validate_skill,
    split_skill_frontmatter,
)


if TYPE_CHECKING:
    from pathlib import Path


SKILL_DIR = SKILLS_DIR / "cmake-pro"
SKILL_MD = SKILL_DIR / "SKILL.md"
EXAMPLES_DIR = SKILL_DIR / "examples"
REFERENCES_DIR = SKILL_DIR / "references"
README_MD = REPO_ROOT / "README.md"
ROOT_PRE_COMMIT = REPO_ROOT / ".pre-commit-config.yaml"

BANNED_NON_TARGET_COMMANDS: tuple[str, ...] = (
    "include_directories",
    "link_libraries",
    "link_directories",
    "add_definitions",
    "add_compile_definitions",
    "add_compile_options",
    "add_link_options",
)


def _load_yaml_dict(file_path: Path) -> dict[str, Any]:
    """Load a YAML file and assert that its root is a dictionary.

    Args:
        file_path: Path object pointing to the YAML configuration file.

    Returns:
        Parsed dictionary representation of the YAML file.
    """
    parsed: Any = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict), f"'{file_path.name}' must parse to a dictionary"
    return parsed


def _load_toml_dict(file_path: Path) -> dict[str, Any]:
    """Load a TOML file and assert that its root is a dictionary.

    Args:
        file_path: Path object pointing to the TOML configuration file.

    Returns:
        Parsed dictionary representation of the TOML file.
    """
    parsed = tomllib.loads(file_path.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict), f"'{file_path.name}' must parse to a dictionary"
    return parsed


def _load_json_dict(file_path: Path) -> dict[str, Any]:
    """Load a JSON file and assert that its root is a dictionary.

    Args:
        file_path: Path object pointing to the JSON configuration file.

    Returns:
        Parsed dictionary representation of the JSON file.
    """
    parsed: Any = json.loads(file_path.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict), f"'{file_path.name}' must parse to a dictionary"
    return parsed


def _all_skill_files() -> list[Path]:
    """Return sorted regular files under skills/cmake-pro including dotfiles.

    Returns:
        Sorted list of regular file paths inside SKILL_DIR.
    """
    return sorted(p for p in SKILL_DIR.rglob("*") if p.is_file())


def _all_markdown_files() -> list[Path]:
    """Return SKILL.md and all reference Markdown files under skills/cmake-pro.

    Returns:
        List of Markdown file paths belonging to the cmake-pro skill.
    """
    return [SKILL_MD, *sorted(REFERENCES_DIR.glob("*.md"))]


def _extract_fenced_blocks(markdown_text: str, language: str) -> list[str]:
    """Extract fenced code blocks matching a specific language tag.

    Args:
        markdown_text: Raw Markdown document content.
        language: Fence language tag such as 'json', 'toml', or 'cmake'.

    Returns:
        List of inner code block bodies matching the requested language.
    """
    pattern = re.compile(
        rf"^```{re.escape(language)}\n(.*?)\n```$", re.MULTILINE | re.DOTALL
    )
    return pattern.findall(markdown_text)


def _resolve_configure_preset(
    presets_by_name: dict[str, dict[str, Any]], preset_name: str
) -> dict[str, Any]:
    """Resolve an inherited CMake configurePreset dictionary bottom-up.

    Args:
        presets_by_name: Mapping from configurePreset name to preset definition.
        preset_name: Name of the configurePreset to resolve.

    Returns:
        Merged preset dictionary including inherited scalar fields, warnings,
        errors, and cacheVariables.
    """
    raw = presets_by_name[preset_name]
    inherits_raw = raw.get("inherits", [])
    parents: list[str] = (
        [inherits_raw]
        if isinstance(inherits_raw, str)
        else [str(p) for p in inherits_raw]
    )

    merged: dict[str, Any] = {}
    merged_warnings: dict[str, Any] = {}
    merged_errors: dict[str, Any] = {}
    merged_cache: dict[str, Any] = {}

    for parent_name in parents:
        parent_resolved = _resolve_configure_preset(presets_by_name, parent_name)
        merged.update({
            k: v
            for k, v in parent_resolved.items()
            if k
            not in {
                "warnings",
                "errors",
                "cacheVariables",
                "hidden",
                "name",
                "inherits",
            }
        })
        merged_warnings.update(parent_resolved.get("warnings", {}))
        merged_errors.update(parent_resolved.get("errors", {}))
        merged_cache.update(parent_resolved.get("cacheVariables", {}))

    merged.update({
        k: v
        for k, v in raw.items()
        if k not in {"warnings", "errors", "cacheVariables"}
    })
    if isinstance(raw.get("warnings"), dict):
        merged_warnings.update(raw["warnings"])
    if isinstance(raw.get("errors"), dict):
        merged_errors.update(raw["errors"])
    if isinstance(raw.get("cacheVariables"), dict):
        merged_cache.update(raw["cacheVariables"])

    merged["warnings"] = merged_warnings
    merged["errors"] = merged_errors
    merged["cacheVariables"] = merged_cache
    return merged


def _require_cmake_4_5() -> str:
    """Locate a CMake >= 4.5 executable or skip the live-tooling test cleanly.

    Returns:
        Absolute path to a CMake >= 4.5 executable.
    """
    cmake_exe = shutil.which("cmake")
    if cmake_exe is None:
        pytest.skip("cmake executable not found on PATH")
    result = subprocess.run(
        [cmake_exe, "--version"], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        pytest.skip(f"cmake --version failed with exit code {result.returncode}")
    match = re.search(r"cmake version (\d+)\.(\d+)\.(\d+)", result.stdout)
    if match is None:
        pytest.skip(f"Unable to parse cmake --version output: {result.stdout!r}")
    version_tuple = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    if version_tuple < (4, 5, 0):
        pytest.skip(
            f"CMake >= 4.5.0 required for live v13/diagnostic tests, found {version_tuple}"
        )
    return cmake_exe


# ==============================================================================
# Tier 1: Feature Coverage E2E Tests (>= 25 tests)
# ==============================================================================


def test_t1_01_skill_directory_exists() -> None:
    """Verify skills/cmake-pro directory exists and is a directory."""
    assert SKILL_DIR.exists(), f"Skill directory not found at '{SKILL_DIR}'"
    assert SKILL_DIR.is_dir(), f"'{SKILL_DIR}' is not a directory"


def test_t1_02_skill_md_exists() -> None:
    """Verify skills/cmake-pro/SKILL.md exists and is a regular file."""
    assert SKILL_MD.exists(), f"SKILL.md not found at '{SKILL_MD}'"
    assert SKILL_MD.is_file(), f"'{SKILL_MD}' is not a regular file"


def test_t1_03_skill_frontmatter_framing() -> None:
    """Verify SKILL.md starts with YAML delimiter and an H1 Markdown body."""
    text = SKILL_MD.read_text(encoding="utf-8")
    assert text.startswith("---\n"), (
        "SKILL.md must begin with YAML delimiter '---' on line 1"
    )
    frontmatter, body = split_skill_frontmatter(text)
    assert isinstance(frontmatter, dict), "Parsed frontmatter must be a dictionary"
    assert body.startswith("# "), "SKILL.md body must begin with an H1 heading (MD041)"


def test_t1_04_skill_frontmatter_name() -> None:
    """Verify frontmatter name equals 'cmake-pro' and conforms to naming regex."""
    frontmatter, _ = split_skill_frontmatter(SKILL_MD.read_text(encoding="utf-8"))
    name = str(frontmatter.get("name", ""))
    assert name == "cmake-pro", f"Expected skill name 'cmake-pro', got '{name}'"
    assert SKILL_NAME_PATTERN.match(name), f"Skill name '{name}' violates naming regex"


def test_t1_05_skill_frontmatter_metadata() -> None:
    """Verify frontmatter metadata sets version v3 and publisher jamielapointe."""
    frontmatter, _ = split_skill_frontmatter(SKILL_MD.read_text(encoding="utf-8"))
    metadata = frontmatter.get("metadata")
    assert isinstance(metadata, dict), "Frontmatter missing 'metadata' dictionary"
    assert metadata.get("version") == "v3", (
        f"Expected metadata.version 'v3', got '{metadata.get('version')}'"
    )
    assert metadata.get("publisher") == "jamielapointe"


def test_t1_06_skill_frontmatter_description() -> None:
    """Verify description covers CMake 4.5, pixi, v13, FILE_SET, CPS/SBOM, gersemi, and omits vcpkg/msvc."""
    frontmatter, _ = split_skill_frontmatter(SKILL_MD.read_text(encoding="utf-8"))
    desc = frontmatter.get("description", "")
    assert isinstance(desc, str), "Frontmatter description must be a string"
    assert len(desc.strip()) >= MIN_SKILL_DESCRIPTION_LENGTH
    lowered = desc.lower()
    required_keywords = [
        "cmake 4.5",
        "linux",
        "macos",
        "pixi",
        "0.84.2+",
        "conda-forge",
        "cmakepresets.json",
        "schema v13",
        "file_set",
        "headers",
        "sources",
        "cmake_diagnostic()",
        "cmd_non_target_directive",
        "cps",
        "package_info",
        "spdx 3.0.1",
        "sbom",
        "isa/simd",
        "cross-compilation",
        "ctest",
        "gtest",
        "discover_tests()",
        "gersemi",
    ]
    for kw in required_keywords:
        assert kw in lowered, f"Description missing expected keyword '{kw}'"
    assert "vcpkg" not in lowered
    assert "msvc" not in lowered


def test_t1_07_subdirectories_allowed() -> None:
    """Verify skills/cmake-pro subdirectories stay strictly within the AntiGravity allowlist."""
    discovered = {p.name for p in SKILL_DIR.iterdir() if p.is_dir()}
    assert discovered == {"examples", "references"}
    assert not (discovered - ALLOWED_SKILL_SUBDIRECTORIES)


def test_t1_08_examples_directory_contents() -> None:
    """Verify examples/ contains all 5 turnkey configurations and parses cleanly."""
    assert EXAMPLES_DIR.is_dir()
    expected_files = {
        "pixi.toml",
        "CMakePresets.json",
        "CMakeLists.txt",
        ".gersemirc",
        ".pre-commit-config.yaml",
    }
    actual_files = {p.name for p in EXAMPLES_DIR.iterdir() if p.is_file()}
    assert actual_files == expected_files
    _ = _load_toml_dict(EXAMPLES_DIR / "pixi.toml")
    _ = _load_json_dict(EXAMPLES_DIR / "CMakePresets.json")
    _ = _load_yaml_dict(EXAMPLES_DIR / ".gersemirc")
    _ = _load_yaml_dict(EXAMPLES_DIR / ".pre-commit-config.yaml")
    assert (EXAMPLES_DIR / "CMakeLists.txt").read_text(encoding="utf-8").strip()


def test_t1_09_references_directory_contents() -> None:
    """Verify references/ contains all 3 architectural manuals starting with H1 headings."""
    assert REFERENCES_DIR.is_dir()
    required_manuals = {
        "canonical_templates.md",
        "presets_toolchains_and_pixi.md",
        "packaging_cps_sbom_and_interop.md",
    }
    actual_manuals = {p.name for p in REFERENCES_DIR.glob("*.md")}
    assert actual_manuals == required_manuals
    for manual in required_manuals:
        content = (REFERENCES_DIR / manual).read_text(encoding="utf-8")
        assert content.startswith("# "), (
            f"'{manual}' must start with an H1 heading on line 1 (MD041)"
        )


def test_t1_10_zero_vcpkg_anywhere_in_skill_and_readme_row() -> None:
    """Verify zero vcpkg/vcpkg.json/VCPKG_ROOT/VCPKG_MANIFEST_MODE in skills/cmake-pro and README row."""
    forbidden_terms = ("vcpkg", "vcpkg.json", "vcpkg_root", "vcpkg_manifest_mode")
    for file_path in _all_skill_files():
        lowered = file_path.read_text(encoding="utf-8").lower()
        for term in forbidden_terms:
            assert term not in lowered, (
                f"Forbidden '{term}' reference found in '{file_path}'"
            )

    readme_text = README_MD.read_text(encoding="utf-8")
    cmake_row = next(
        (line for line in readme_text.splitlines() if "| `cmake-pro` |" in line), ""
    )
    assert cmake_row, "README.md missing '| `cmake-pro` |' row"
    for term in forbidden_terms:
        assert term not in cmake_row.lower(), (
            f"README.md cmake-pro row must not mention '{term}'"
        )


def test_t1_11_zero_windows_or_msvc_anywhere_in_skill() -> None:
    """Verify zero Windows/MSVC references or MSVC flags anywhere inside skills/cmake-pro/**."""
    case_insensitive_banned = ("msvc", "win32", "win-64", "/permissive-")
    exact_banned = ("/W4", "/WX")
    for file_path in _all_skill_files():
        text = file_path.read_text(encoding="utf-8")
        lowered = text.lower()
        for term in case_insensitive_banned:
            assert term not in lowered, (
                f"Forbidden Windows/MSVC term '{term}' found in '{file_path}'"
            )
        for flag in exact_banned:
            assert flag not in text, (
                f"Forbidden MSVC compiler flag '{flag}' found in '{file_path}'"
            )


def test_t1_12_pixi_conda_forge_abi_and_cross_references() -> None:
    """Verify pixi 0.84.2+, conda-forge, $CONDA_PREFIX, native stdlib ABI rule, and /python-pro & /cpp-pro links."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding="utf-8"))
    presets_doc = (REFERENCES_DIR / "presets_toolchains_and_pixi.md").read_text(
        encoding="utf-8"
    )

    for doc in (body, presets_doc):
        assert "0.84.2+" in doc
        assert 'requires-pixi = ">=0.84.2"' in doc
        assert "conda-forge" in doc
        assert "$env{CONDA_PREFIX}" in doc
        assert "CMAKE_PREFIX_PATH" in doc
        assert "libstdc++" in doc
        assert "libc++" in doc
        assert "/python-pro" in doc
        assert "/cpp-pro" in doc
        assert "CMAKE_SYSTEM_ENVIRONMENT_ID" in doc
        assert "[activation.env]" in doc
        assert "CMAKE_SYSTEM_ENVIRONMENT_ACTION=REFRESH" in doc


def test_t1_13_airgapped_sysroot_fallback_and_fetchcontent_ban() -> None:
    """Verify air-gapped sysroot find_package fallback and strict ban on FetchContent/ExternalProject_Add."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding="utf-8"))
    templates_doc = (REFERENCES_DIR / "canonical_templates.md").read_text(
        encoding="utf-8"
    )
    presets_doc = (REFERENCES_DIR / "presets_toolchains_and_pixi.md").read_text(
        encoding="utf-8"
    )

    assert "FetchContent" in body
    assert "ExternalProject_Add" in body
    assert "strictly forbidden" in body
    assert "FetchContent" in templates_doc
    assert "ExternalProject_Add" in templates_doc
    assert "strictly banned" in templates_doc
    assert "find_package(<Pkg> CONFIG REQUIRED)" in body
    assert "find_package(<Pkg> CONFIG REQUIRED)" in templates_doc
    assert "find_package(<Pkg> CONFIG REQUIRED)" in presets_doc
    assert "CMAKE_FIND_ROOT_PATH_MODE_{LIBRARY,INCLUDE,PACKAGE}=ONLY" in body
    assert "CMAKE_FIND_ROOT_PATH_MODE_{LIBRARY,INCLUDE,PACKAGE} ONLY" in presets_doc

    for file_path in _all_skill_files():
        text = file_path.read_text(encoding="utf-8")
        assert "include(FetchContent)" not in text, (
            f"Forbidden include(FetchContent) in '{file_path}'"
        )
        assert "FetchContent_Declare(" not in text, (
            f"Forbidden FetchContent_Declare in '{file_path}'"
        )
        assert "FetchContent_MakeAvailable(" not in text, (
            f"Forbidden FetchContent_MakeAvailable in '{file_path}'"
        )
        assert "ExternalProject_Add(" not in text, (
            f"Forbidden ExternalProject_Add invocation in '{file_path}'"
        )


def test_t1_14_cmake_minimum_4_5_and_diagnostic_controls() -> None:
    """Verify cmake_minimum_required(VERSION 4.5), cmake_diagnostic(), CMD_NON_TARGET_DIRECTIVE, and CMD_STRICT."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding="utf-8"))
    cmakelists_text = (EXAMPLES_DIR / "CMakeLists.txt").read_text(encoding="utf-8")
    presets_doc = (REFERENCES_DIR / "presets_toolchains_and_pixi.md").read_text(
        encoding="utf-8"
    )

    assert "cmake_minimum_required(VERSION 4.5)" in body
    assert "cmake_minimum_required(VERSION 4.5)" in cmakelists_text
    assert "cmake_diagnostic(SET CMD_NON_TARGET_DIRECTIVE SEND_ERROR)" in body
    assert (
        "cmake_diagnostic(SET CMD_NON_TARGET_DIRECTIVE SEND_ERROR)" in cmakelists_text
    )
    for action in ("IGNORE", "WARN", "SEND_ERROR", "FATAL_ERROR"):
        assert action in body, (
            f"SKILL.md missing valid cmake_diagnostic action '{action}'"
        )
    assert "`ERROR` is invalid" in body
    assert "CMD_STRICT" in presets_doc
    assert "CMD_NON_TARGET_DIRECTIVE" in presets_doc
    assert "CMD_INSTALL_ABSOLUTE_DESTINATION" in presets_doc


def test_t1_15_modular_cmake_architecture_and_block_scoping() -> None:
    """Verify declarative root CMakeLists, out-of-source guard, INTERFACE targets, and block() scoping."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding="utf-8"))
    cmakelists_text = (EXAMPLES_DIR / "CMakeLists.txt").read_text(encoding="utf-8")
    templates_doc = (REFERENCES_DIR / "canonical_templates.md").read_text(
        encoding="utf-8"
    )

    assert "PROJECT_SOURCE_DIR STREQUAL PROJECT_BINARY_DIR" in body
    assert "PROJECT_SOURCE_DIR STREQUAL PROJECT_BINARY_DIR" in cmakelists_text
    assert "CMAKE_MODULE_PATH" in body
    assert "CMAKE_MODULE_PATH" in cmakelists_text
    assert "block(SCOPE_FOR VARIABLES POLICIES DIAGNOSTICS)" in body
    assert "block(SCOPE_FOR VARIABLES POLICIES DIAGNOSTICS)" in templates_doc
    assert "block(SCOPE_FOR POLICIES DIAGNOSTICS)" in cmakelists_text
    for iface in (
        "project_options",
        "project_warnings",
        "project_sanitizers",
        "project_architecture",
    ):
        assert iface in body
        assert iface in cmakelists_text
        assert f"add_library({iface} INTERFACE)" in templates_doc


def test_t1_16_file_sets_properties_and_header_verification() -> None:
    """Verify FILE_SET HEADERS & TYPE SOURCES, file-set properties, and CMAKE_VERIFY_*_HEADER_SETS controls."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding="utf-8"))
    cmakelists_text = (EXAMPLES_DIR / "CMakeLists.txt").read_text(encoding="utf-8")
    pkg_doc = (REFERENCES_DIR / "packaging_cps_sbom_and_interop.md").read_text(
        encoding="utf-8"
    )

    assert "FILE_SET HEADERS" in body
    assert "FILE_SET HEADERS" in cmakelists_text
    assert "FILE_SET HEADERS" in pkg_doc
    assert "TYPE SOURCES" in body
    assert "TYPE SOURCES" in cmakelists_text
    assert "TYPE SOURCES" in pkg_doc
    for prop in (
        "SKIP_LINTING",
        "SKIP_PRECOMPILE_HEADERS",
        "SKIP_UNITY_BUILD_INCLUSION",
        "CXX_SCAN_FOR_MODULES",
        "INDEPENDENT_FILES",
        "JOB_POOL_COMPILE",
    ):
        assert prop in body, f"SKILL.md missing file-set property '{prop}'"
        assert prop in pkg_doc, (
            f"packaging_cps_sbom_and_interop.md missing file-set property '{prop}'"
        )

    for verify_var in (
        "CMAKE_VERIFY_INTERFACE_HEADER_SETS",
        "CMAKE_VERIFY_PRIVATE_HEADER_SETS",
        "INTERFACE_HEADER_SETS_TO_VERIFY",
        "PRIVATE_HEADER_SETS_TO_VERIFY",
    ):
        assert verify_var in pkg_doc
    assert "CMAKE_VERIFY_INTERFACE_HEADER_SETS" in body
    assert "CMAKE_VERIFY_PRIVATE_HEADER_SETS" in body
    assert "{INTERFACE,PRIVATE}_HEADER_SETS_TO_VERIFY" in body


def test_t1_17_cxx_module_scanning_off_default_and_ga_import_std() -> None:
    """Verify CMAKE_CXX_SCAN_FOR_MODULES OFF default, ENABLE_CXX_MODULES opt-in, and GA import std."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding="utf-8"))
    cmakelists_text = (EXAMPLES_DIR / "CMakeLists.txt").read_text(encoding="utf-8")
    templates_doc = (REFERENCES_DIR / "canonical_templates.md").read_text(
        encoding="utf-8"
    )

    for doc in (body, cmakelists_text, templates_doc):
        assert "ENABLE_CXX_MODULES" in doc
        assert "set(CMAKE_CXX_SCAN_FOR_MODULES OFF)" in doc
        assert "import std" in doc

    assert "import std.compat" in body
    assert "import std.compat" in templates_doc
    assert "CMAKE_CXX_STDLIB_MODULES_JSON" in body
    assert "CMAKE_CXX_STDLIB_MODULES_JSON" in templates_doc
    assert "CMAKE_EXPERIMENTAL_CXX_IMPORT_STD" in body
    assert "CMAKE_EXPERIMENTAL_CXX_IMPORT_STD" in templates_doc
    assert "CXX_MODULE_STD" in body
    assert "CXX_MODULE_STD" in templates_doc


def test_t1_18_alias_target_parity_in_cmake_4_5() -> None:
    """Verify CMake 4.5 direct ALIAS target parity for set_target_properties, install, and export."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding="utf-8"))
    cmakelists_text = (EXAMPLES_DIR / "CMakeLists.txt").read_text(encoding="utf-8")
    pkg_doc = (REFERENCES_DIR / "packaging_cps_sbom_and_interop.md").read_text(
        encoding="utf-8"
    )

    assert "ALIAS" in body
    assert "ALIASED_TARGET" in body
    assert "ALIAS" in pkg_doc
    assert "ALIASED_TARGET" in pkg_doc
    assert "add_library(ModernCMakeTemplate::Core ALIAS modern_core)" in cmakelists_text
    assert (
        "set_target_properties(\n        ModernCMakeTemplate::Core" in cmakelists_text
    )
    assert "install(\n        TARGETS ModernCMakeTemplate::Core" in cmakelists_text
    assert "set_target_properties(Halos::Core" in pkg_doc
    assert "install(TARGETS Halos::Core" in pkg_doc


def test_t1_19_project_compat_version_spdx_license_and_ga_cps() -> None:
    """Verify project(COMPAT_VERSION SPDX_LICENSE) and GA CPS install/export(PACKAGE_INFO)."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding="utf-8"))
    cmakelists_text = (EXAMPLES_DIR / "CMakeLists.txt").read_text(encoding="utf-8")
    pkg_doc = (REFERENCES_DIR / "packaging_cps_sbom_and_interop.md").read_text(
        encoding="utf-8"
    )

    for doc in (body, cmakelists_text, pkg_doc):
        assert "COMPAT_VERSION" in doc
        assert "SPDX_LICENSE" in doc
        assert "PACKAGE_INFO" in doc
        assert "LOWER_CASE_FILE" in doc

    assert "PROJECT_COMPAT_VERSION" in pkg_doc
    assert "PROJECT_SPDX_LICENSE" in pkg_doc
    assert "export(PACKAGE_INFO" in pkg_doc
    assert "APPENDIX" in pkg_doc
    assert ".cps" in body
    assert ".cps" in pkg_doc


def test_t1_20_ga_spdx_3_0_1_sbom_and_link_only_guard() -> None:
    """Verify GA SPDX 3.0.1 install/export(SBOM), CMAKE_INSTALL_SBOM_FORMATS, and $<LINK_ONLY:...>."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding="utf-8"))
    cmakelists_text = (EXAMPLES_DIR / "CMakeLists.txt").read_text(encoding="utf-8")
    pkg_doc = (REFERENCES_DIR / "packaging_cps_sbom_and_interop.md").read_text(
        encoding="utf-8"
    )

    for doc in (body, cmakelists_text, pkg_doc):
        assert "spdx-3.0.1+json" in doc
        assert "EXPORTS" in doc
        assert 'DATA_LICENSE "CC0-1.0"' in doc
        assert "DEFAULT_LICENSE" in doc

    assert "CMAKE_INSTALL_SBOM_FORMATS" in body
    assert "CMAKE_INSTALL_SBOM_FORMATS" in pkg_doc
    assert "$<LINK_ONLY:...>" in body
    assert "$<LINK_ONLY:...>" in pkg_doc
    assert "export(\n    SBOM" in pkg_doc


def test_t1_21_cmake_presets_v13_features_and_cli_flags() -> None:
    """Verify Schema v13 macros (${configurePresetName}, ${fileDir}), CLI flags, and testPassthroughArguments."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding="utf-8"))
    presets_doc = (REFERENCES_DIR / "presets_toolchains_and_pixi.md").read_text(
        encoding="utf-8"
    )

    for token in (
        "${configurePresetName}",
        "${fileDir}",
        "--presets-file",
        "--list-presets=all-defined",
        "testPassthroughArguments",
        "workflowPresets",
    ):
        assert token in body, f"SKILL.md missing preset feature '{token}'"
        assert token in presets_doc, (
            f"presets_toolchains_and_pixi.md missing preset feature '{token}'"
        )


def test_t1_22_testing_gtest_and_cmake_4_5_discover_tests() -> None:
    """Verify gtest_discover_tests(), CMake 4.4-4.5 discover_tests(), BUILD_DEPENDS, and CMP0224."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding="utf-8"))
    templates_doc = (REFERENCES_DIR / "canonical_templates.md").read_text(
        encoding="utf-8"
    )

    for token in (
        "gtest_discover_tests(",
        "POST_BUILD",
        "PRE_TEST",
        "CMAKE_CROSSCOMPILING_EMULATOR",
        "discover_tests(",
        "DISCOVERY_MATCH",
        "BUILD_DEPENDS",
        "ctest --out-of-date",
        "CMP0224",
        "AROUND_EACH_REPEAT",
        "FIXTURE_REPEAT_MODE",
    ):
        assert token in body, f"SKILL.md missing testing token '{token}'"
        assert token in templates_doc, (
            f"canonical_templates.md missing testing token '{token}'"
        )


def test_t1_23_cmake_instrumentation_and_language_print_introspection() -> None:
    """Verify cmake_instrumentation(API_VERSION 1 DATA_VERSION 1.2) and cmake_language(PRINT_*)."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding="utf-8"))
    presets_doc = (REFERENCES_DIR / "presets_toolchains_and_pixi.md").read_text(
        encoding="utf-8"
    )

    for token in (
        "cmake_instrumentation(",
        "API_VERSION 1",
        "DATA_VERSION 1.2",
        "compileTrace",
        "processMetrics",
        "trace",
        "ctest --collect-instrumentation",
        "cmake_language(",
        "PRINT_TARGETS",
        "PRINT_PROPERTIES",
        "PRINT_VARIABLES",
        "CMakePrintHelpers",
    ):
        assert token in body, f"SKILL.md missing introspection token '{token}'"
        assert token in presets_doc, (
            f"presets_toolchains_and_pixi.md missing introspection token '{token}'"
        )


def test_t1_24_linker_types_ccache_and_clang_tidy_wiring() -> None:
    """Verify CMAKE_LINKER_TYPE (LLD/MOLD/WILD/SYSTEM), check_linker_flag(), ccache, and clang-tidy."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding="utf-8"))
    templates_doc = (REFERENCES_DIR / "canonical_templates.md").read_text(
        encoding="utf-8"
    )

    for token in (
        "CMAKE_LINKER_TYPE",
        "LLD",
        "MOLD",
        "WILD",
        "SYSTEM",
        "check_linker_flag()",
        "ccache",
        "CMAKE_CXX_CLANG_TIDY",
        "CMAKE_EXPORT_COMPILE_COMMANDS",
    ):
        assert token in body, f"SKILL.md missing tooling token '{token}'"
    assert "CMAKE_LINKER_TYPE" in templates_doc
    assert "check_linker_flag(" in templates_doc
    assert "CMAKE_CXX_COMPILER_LAUNCHER" in templates_doc


def test_t1_25_exceptions_rtti_defaults_warnings_and_sanitizers() -> None:
    """Verify -fno-exceptions/-fno-rtti defaults, Clang/GCC warnings, and sanitizer mutual exclusions."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding="utf-8"))
    templates_doc = (REFERENCES_DIR / "canonical_templates.md").read_text(
        encoding="utf-8"
    )

    for token in (
        "-fno-exceptions -fno-rtti",
        "ENABLE_EXCEPTIONS",
        "ENABLE_RTTI",
        "$<$<COMPILE_LANGUAGE:CXX>:",
        "WARNINGS_AS_ERRORS",
        "-Werror",
        "-fsanitize=undefined",
        "-fno-sanitize-recover=all",
    ):
        assert token in body, f"SKILL.md missing compiler/sanitizer token '{token}'"

    for tmpl_token in (
        "option(ENABLE_EXCEPTIONS",
        "option(ENABLE_RTTI",
        "$<$<COMPILE_LANGUAGE:CXX>:-fno-exceptions>",
        "$<$<COMPILE_LANGUAGE:CXX>:-fno-rtti>",
        "ENABLE_SANITIZER_ADDRESS",
        "ENABLE_SANITIZER_UNDEFINED",
        "ENABLE_SANITIZER_THREAD",
        "ENABLE_SANITIZER_MEMORY",
        "ENABLE_SANITIZER_LEAK",
        "CMAKE_REQUIRED_FLAGS",
        "CMAKE_REQUIRED_LINK_OPTIONS",
    ):
        assert tmpl_token in templates_doc, (
            f"canonical_templates.md missing '{tmpl_token}'"
        )


def test_t1_26_isa_simd_probes_x86_arm64_and_riscv64_rva23() -> None:
    """Verify dynamic X86_64, ARM64, and RISCV64 RVA23 RVV 1.0 SIMD probes and cache-line constants."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding="utf-8"))
    templates_doc = (REFERENCES_DIR / "canonical_templates.md").read_text(
        encoding="utf-8"
    )

    for token in (
        "X86_64",
        "ARM64",
        "RISCV64",
        "RVA23",
        "-mavx2 -mfma",
        "-mavx512f -mavx512vl -mavx512dq -mavx512bw",
        "-march=armv8-a+sve",
        "-march=rva23u64",
        "-march=rv64gcv",
        "<riscv_vector.h>",
        "__riscv_v_intrinsic",
        "1000000",
        "__riscv_vsetvl_e32m1",
        "TARGET_CACHE_LINE_BYTES",
        "ENABLE_NATIVE_OPTIMIZATION",
        "NOT CMAKE_CROSSCOMPILING",
    ):
        assert token in body, f"SKILL.md missing ISA probe token '{token}'"
        assert token in templates_doc, (
            f"canonical_templates.md missing ISA probe token '{token}'"
        )
    assert "__riscv_v_intrinsic >= 1000000" in body
    assert "__riscv_v_intrinsic < 1000000" in templates_doc


def test_t1_27_llvm_coverage_integration() -> None:
    """Verify Coverage.cmake configures llvm-cov and llvm-profdata coverage reporting."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding="utf-8"))
    templates_doc = (REFERENCES_DIR / "canonical_templates.md").read_text(
        encoding="utf-8"
    )

    assert "Coverage.cmake" in body
    assert "llvm-cov" in body
    assert "llvm-profdata" in body
    for token in (
        "option(ENABLE_COVERAGE",
        "-fprofile-instr-generate",
        "-fcoverage-mapping",
        "coverage-report",
        "llvm-profdata",
        "llvm-cov",
    ):
        assert token in templates_doc, (
            f"canonical_templates.md missing coverage token '{token}'"
        )


def test_t1_28_gersemi_0_19_2_plus_formatting_and_pre_commit() -> None:
    """Verify gersemi 0.19.2+ rules, # gersemi: off/on guards, and no --no-verify bypasses."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding="utf-8"))
    assert "gersemi" in body
    assert "0.19.2+" in body
    assert "line_length: 100" in body
    assert "indent: 4" in body
    assert "list_expansion: favour-inlining" in body
    assert "# gersemi: off" in body
    assert "# gersemi: on" in body
    assert "\\\\1.\\\\2" in body
    assert "gersemi --check" in body
    assert "--no-verify" in body


def test_t1_29_all_six_related_skills_and_no_notebook_skills() -> None:
    """Verify SKILL.md links all 6 required sibling skills and omits jupyter/marimo skills."""
    text = SKILL_MD.read_text(encoding="utf-8")
    required_siblings = (
        "/ada-spark-pro",
        "/c-pro",
        "/cpp-pro",
        "/rust-pro",
        "/python-pro",
        "/github-flow-lifecycle",
    )
    for sibling in required_siblings:
        assert sibling in text, f"SKILL.md missing related skill '{sibling}'"

    for md_file in _all_markdown_files():
        lowered = md_file.read_text(encoding="utf-8").lower()
        assert "jupyter" not in lowered, (
            f"'{md_file.name}' must not reference jupyter skills"
        )
        assert "marimo" not in lowered, (
            f"'{md_file.name}' must not reference marimo skills"
        )


def test_t1_30_behavioral_guardrails_and_decision_trees() -> None:
    """Verify SKILL.md contains Decision Trees and Behavioral Guardrails for fail-fast CMake."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding="utf-8"))
    for heading in (
        "## Decision Trees",
        "### Dependency, Toolchain & Preset Routing",
        "### Cross-Language CMake 4.5 Integration",
        "### Packaging Metadata & Module Scanning",
        "## Behavioral Guardrails",
        "message(FATAL_ERROR",
    ):
        assert heading in body, f"SKILL.md missing section or guardrail '{heading}'"


# ==============================================================================
# Tier 2: Boundary & Corner Cases E2E Tests (>= 20 tests)
# ==============================================================================


def test_t2_01_skill_body_bytes_under_limit_with_headroom() -> None:
    """Verify SKILL.md body size stays under 24,000 UTF-8 bytes with >= 500 B headroom."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding="utf-8"))
    body_bytes = len(body.encode("utf-8"))
    assert body_bytes < MAX_FILE_BYTES, (
        f"SKILL.md body ({body_bytes} B) exceeds {MAX_FILE_BYTES} B"
    )
    headroom = MAX_FILE_BYTES - body_bytes
    assert headroom >= 500, (
        f"SKILL.md body headroom ({headroom} B) is below required 500 B margin"
    )


def test_t2_02_all_reference_manuals_under_max_file_bytes() -> None:
    """Verify every reference manual under references/ stays strictly below MAX_FILE_BYTES."""
    ref_files = sorted(REFERENCES_DIR.glob("*.md"))
    assert len(ref_files) == 3
    for ref_file in ref_files:
        size_bytes = len(ref_file.read_bytes())
        assert size_bytes < MAX_FILE_BYTES, (
            f"'{ref_file.name}' ({size_bytes} B) exceeds {MAX_FILE_BYTES} B"
        )


def test_t2_03_oracle_validate_skill_zero_issues() -> None:
    """Verify authoritative AntiGravity 2.29.0+ skill oracle reports zero issues for cmake-pro."""
    issues = oracle_validate_skill(SKILL_DIR)
    assert not issues, (
        f"Oracle validation returned issues for skills/cmake-pro: {issues}"
    )


def test_t2_04_validate_prompts_zero_errors() -> None:
    """Verify repository prompt_validator passes strictly with zero errors."""
    report = ValidationReport(strict=True)
    validate_prompts(REPO_ROOT, report)
    errors = [issue for issue in report.issues if issue.severity == Severity.ERROR]
    assert not errors, f"prompt_validator reported errors: {errors}"


def test_t2_05_secret_and_home_path_hygiene() -> None:
    """Verify zero personal home paths, Drive mounts, or API tokens leak inside skills/cmake-pro/**."""
    for file_path in _all_skill_files():
        content = file_path.read_text(encoding="utf-8")
        assert not HOME_PATTERN.search(content), (
            f"Personal home path leaked in '{file_path}'"
        )
        assert not DRIVE_PATTERN.search(content), (
            f"Google Drive mount leaked in '{file_path}'"
        )
        for token_re in TOKEN_PATTERNS:
            assert not token_re.search(content), (
                f"Plaintext token leaked in '{file_path}'"
            )


def test_t2_06_all_relative_markdown_links_resolve() -> None:
    """Verify every relative Markdown link in SKILL.md and references/ resolves on disk."""
    link_pattern = re.compile(r"\[([^\]]+)\]\((?!https?://)([^)#\s]+)(?:#[^)]*)?\)")
    checked = 0
    for md_file in _all_markdown_files():
        text = md_file.read_text(encoding="utf-8")
        for match in link_pattern.finditer(text):
            target = (md_file.parent / match.group(2)).resolve()
            assert target.exists(), (
                f"Broken relative link in '{md_file.name}': '{match.group(2)}' -> '{target}'"
            )
            checked += 1
    assert checked >= 8, f"Expected at least 8 verified relative links, found {checked}"


def test_t2_07_balanced_markdown_code_fences_and_eof_hygiene() -> None:
    """Verify balanced code fences in Markdown and clean LF EOF/trailing-whitespace across all skill files."""
    for md_file in _all_markdown_files():
        lines = md_file.read_text(encoding="utf-8").splitlines()
        fence_count = sum(1 for line in lines if line.lstrip().startswith("```"))
        assert fence_count % 2 == 0, (
            f"Unclosed code fence in '{md_file.name}' (count={fence_count})"
        )

    for file_path in _all_skill_files():
        raw = file_path.read_text(encoding="utf-8")
        assert "\r\n" not in raw, f"CRLF line ending found in '{file_path}'"
        assert raw.endswith("\n"), f"Missing trailing newline in '{file_path}'"
        for idx, line in enumerate(raw.splitlines(), start=1):
            assert not line.endswith((" ", "\t")), (
                f"Trailing whitespace in '{file_path}:{idx}'"
            )


def test_t2_08_examples_pixi_toml_workspace_platforms_and_version() -> None:
    """Verify examples/pixi.toml configures requires-pixi >=0.84.2, conda-forge, and Linux/macOS only."""
    cfg = _load_toml_dict(EXAMPLES_DIR / "pixi.toml")
    ws = cfg.get("workspace", {})
    assert isinstance(ws, dict)
    assert ws.get("requires-pixi") == ">=0.84.2"
    assert ws.get("channels") == ["conda-forge"]
    platforms = ws.get("platforms", [])
    assert platforms == ["linux-64", "linux-aarch64", "osx-arm64"]
    assert "win-64" not in platforms


def test_t2_09_examples_pixi_toml_dependencies_and_libabseil_libcxx() -> None:
    """Verify examples/pixi.toml pins CMake >=4.5.0, gersemi >=0.19.2, libabseil, and macOS-only libcxx."""
    cfg = _load_toml_dict(EXAMPLES_DIR / "pixi.toml")
    deps = cfg.get("dependencies", {})
    assert isinstance(deps, dict)
    expected_versions = {
        "cmake": ">=4.5.0",
        "gersemi": ">=0.19.2",
        "clangxx": ">=23.1.5",
        "clang-tools": ">=23.1.5",
        "lld": ">=23.1.5",
        "ninja": ">=1.12.0",
        "ccache": ">=4.10.0",
        "libabseil": ">=20260817.0",
        "gtest": ">=1.18.0",
        "benchmark": ">=1.10.0",
        "pre-commit": ">=4.6.0",
    }
    for pkg, spec in expected_versions.items():
        assert deps.get(pkg) == spec, (
            f"Expected dependency '{pkg} = {spec}', got '{deps.get(pkg)}'"
        )
    assert "abseil-cpp" not in deps, (
        "Must use conda-forge libabseil, not broken abseil-cpp >2022"
    )
    assert "libcxx" not in deps, (
        "libcxx must NOT be placed in global cross-platform [dependencies]"
    )

    target = cfg.get("target", {})
    assert isinstance(target, dict)
    osx_deps = target.get("osx-arm64", {}).get("dependencies", {})
    linux64_deps = target.get("linux-64", {}).get("dependencies", {})
    linux_arm_deps = target.get("linux-aarch64", {}).get("dependencies", {})
    assert osx_deps.get("libcxx") == ">=23.1.5"
    assert "libcxx" not in linux64_deps
    assert "libcxx" not in linux_arm_deps


def test_t2_10_examples_pixi_toml_tasks_complete() -> None:
    """Verify examples/pixi.toml exposes turnkey preset, build, test, lint, format, and CI tasks."""
    cfg = _load_toml_dict(EXAMPLES_DIR / "pixi.toml")
    tasks = cfg.get("tasks", {})
    assert isinstance(tasks, dict)
    expected_tasks = {
        "presets",
        "configure",
        "build",
        "test",
        "workflow",
        "cmake-fmt",
        "cmake-fmt-fix",
        "lint",
        "ci",
    }
    assert expected_tasks.issubset(set(tasks.keys()))
    assert "--list-presets=all-defined" in str(tasks["presets"].get("cmd", ""))
    assert "cmake --workflow --preset ci-debug" in str(tasks["workflow"].get("cmd", ""))
    assert "gersemi --check" in str(tasks["cmake-fmt"].get("cmd", ""))
    ci_deps = set(tasks["ci"].get("depends-on", []))
    assert {"configure", "build", "lint", "test", "cmake-fmt"}.issubset(ci_deps)


def test_t2_11_examples_cmake_presets_schema_v13_and_no_dev_diagnostics() -> None:
    """Verify examples/CMakePresets.json uses Schema v13, CMake 4.5.0, no warnings.dev, and strict errors."""
    cfg = _load_json_dict(EXAMPLES_DIR / "CMakePresets.json")
    assert cfg.get("version") == 13
    assert cfg.get("cmakeMinimumRequired") == {"major": 4, "minor": 5, "patch": 0}

    configure_presets = cfg.get("configurePresets", [])
    assert isinstance(configure_presets, list)
    for preset in configure_presets:
        assert isinstance(preset, dict)
        warnings_cfg = preset.get("warnings", {})
        errors_cfg = preset.get("errors", {})
        assert "dev" not in warnings_cfg, (
            f"Removed Schema <12 'warnings.dev' found in '{preset.get('name')}'"
        )
        assert "dev" not in errors_cfg, (
            f"Removed Schema <12 'errors.dev' found in '{preset.get('name')}'"
        )

    base = next(p for p in configure_presets if p.get("name") == "base")
    assert base["generator"] == "Ninja"
    assert base["binaryDir"] == "${sourceDir}/build/${presetName}"
    assert base["warnings"]["strict"] is True
    assert base["warnings"]["nonTargetDirective"] is True
    assert base["warnings"]["installAbsoluteDestination"] is True
    assert base["warnings"]["unusedCli"] is True
    assert base["errors"]["nonTargetDirective"] is True
    assert base["errors"]["deprecated"] is True
    assert base["errors"].get("unusedCli") is not True


def test_t2_12_examples_cmake_presets_no_configure_preset_name_in_workflows() -> None:
    """Verify ${configurePresetName} is used in build/test presets and excluded from workflowPresets."""
    cfg = _load_json_dict(EXAMPLES_DIR / "CMakePresets.json")

    build_presets = cfg.get("buildPresets", [])
    test_presets = cfg.get("testPresets", [])
    workflow_presets = cfg.get("workflowPresets", [])

    assert any(
        "${configurePresetName}" in str(bp.get("description", ""))
        for bp in build_presets
    )
    assert any(
        "${configurePresetName}" in str(tp.get("output", {}).get("outputJUnitFile", ""))
        for tp in test_presets
    )
    workflow_serialized = json.dumps(workflow_presets)
    assert "${configurePresetName}" not in workflow_serialized, (
        "${configurePresetName} is forbidden inside workflowPresets"
    )


def test_t2_13_examples_cmake_presets_sysroot_and_cross_do_not_inherit_pixi_base() -> (
    None
):
    """Verify sysroot-release and cross presets inherit base (not pixi-base) and use ${fileDir}."""
    cfg = _load_json_dict(EXAMPLES_DIR / "CMakePresets.json")
    by_name = {str(p["name"]): p for p in cfg["configurePresets"]}

    pixi_base = by_name["pixi-base"]
    assert pixi_base["hidden"] is True
    assert pixi_base["inherits"] == "base"
    assert pixi_base["condition"] == {
        "type": "notEquals",
        "lhs": "$env{CONDA_PREFIX}",
        "rhs": "",
    }
    assert pixi_base["cacheVariables"]["CMAKE_PREFIX_PATH"] == "$env{CONDA_PREFIX}"

    for standalone in ("sysroot-release", "cross-aarch64", "cross-riscv64"):
        preset = by_name[standalone]
        assert preset.get("inherits") == "base", (
            f"'{standalone}' must inherit 'base', not 'pixi-base'"
        )
        assert "condition" not in preset, (
            f"'{standalone}' must not depend on $CONDA_PREFIX"
        )

    assert (
        by_name["cross-aarch64"]["toolchainFile"]
        == "${fileDir}/cmake/toolchains/aarch64-linux-gnu.cmake"
    )
    assert (
        by_name["cross-riscv64"]["toolchainFile"]
        == "${fileDir}/cmake/toolchains/riscv64-linux-gnu.cmake"
    )
    assert by_name["cross-aarch64"]["cacheVariables"]["BUILD_TESTING"] == "OFF"
    assert by_name["cross-riscv64"]["cacheVariables"]["BUILD_TESTING"] == "OFF"


def test_t2_14_examples_cmake_presets_ci_debug_in_all_four_arrays() -> None:
    """Verify ci-debug exists across all 4 preset arrays with build/ci-debug binaryDir and passthrough args."""
    cfg = _load_json_dict(EXAMPLES_DIR / "CMakePresets.json")
    for array_key in (
        "configurePresets",
        "buildPresets",
        "testPresets",
        "workflowPresets",
    ):
        names = {str(item["name"]) for item in cfg[array_key]}
        assert "ci-debug" in names, f"'ci-debug' missing from '{array_key}'"

    by_name = {str(p["name"]): p for p in cfg["configurePresets"]}
    ci_resolved = _resolve_configure_preset(by_name, "ci-debug")
    assert ci_resolved["binaryDir"] == "${sourceDir}/build/${presetName}"
    assert ci_resolved["cacheVariables"]["CMAKE_EXPORT_COMPILE_COMMANDS"] == "ON"
    assert ci_resolved["cacheVariables"]["ENABLE_SANITIZER_ADDRESS"] == "ON"
    assert ci_resolved["cacheVariables"]["ENABLE_SANITIZER_UNDEFINED"] == "ON"

    ci_test = next(tp for tp in cfg["testPresets"] if tp["name"] == "ci-debug")
    assert ci_test["execution"]["testPassthroughArguments"] == ["--gtest_brief=1"]


def test_t2_15_examples_cmake_presets_referential_integrity() -> None:
    """Verify all inherits, configurePreset, and workflowPresets step references are valid and non-hidden."""
    cfg = _load_json_dict(EXAMPLES_DIR / "CMakePresets.json")
    cfg_by_name = {str(p["name"]): p for p in cfg["configurePresets"]}
    build_by_name = {str(p["name"]): p for p in cfg["buildPresets"]}
    test_by_name = {str(p["name"]): p for p in cfg["testPresets"]}

    for name, preset in cfg_by_name.items():
        inherits = preset.get("inherits")
        if isinstance(inherits, str):
            assert inherits in cfg_by_name, (
                f"'{name}' inherits missing preset '{inherits}'"
            )
        elif isinstance(inherits, list):
            for parent in inherits:
                assert parent in cfg_by_name, (
                    f"'{name}' inherits missing preset '{parent}'"
                )

    for bp in cfg["buildPresets"]:
        target = str(bp["configurePreset"])
        assert target in cfg_by_name
        assert not cfg_by_name[target].get("hidden", False)

    for tp in cfg["testPresets"]:
        target = str(tp["configurePreset"])
        assert target in cfg_by_name
        assert not cfg_by_name[target].get("hidden", False)

    step_maps = {"configure": cfg_by_name, "build": build_by_name, "test": test_by_name}
    for wp in cfg["workflowPresets"]:
        for step in wp["steps"]:
            step_type = str(step["type"])
            step_name = str(step["name"])
            assert step_name in step_maps[step_type], (
                f"Workflow '{wp['name']}' references unknown {step_type} preset '{step_name}'"
            )


def test_t2_16_reference_embedded_presets_json_and_pixi_toml_parse_cleanly() -> None:
    """Verify JSON and TOML code fences in presets_toolchains_and_pixi.md parse and follow v13/pixi rules."""
    presets_doc = (REFERENCES_DIR / "presets_toolchains_and_pixi.md").read_text(
        encoding="utf-8"
    )
    json_blocks = _extract_fenced_blocks(presets_doc, "json")
    toml_blocks = _extract_fenced_blocks(presets_doc, "toml")
    assert len(json_blocks) == 1
    assert len(toml_blocks) == 1

    preset_data: Any = json.loads(json_blocks[0])
    assert isinstance(preset_data, dict)
    assert preset_data["version"] == 13
    assert preset_data["cmakeMinimumRequired"] == {"major": 4, "minor": 5, "patch": 0}
    for cfg_preset in preset_data["configurePresets"]:
        assert "dev" not in cfg_preset.get("warnings", {})
        assert "dev" not in cfg_preset.get("errors", {})
    assert "${configurePresetName}" not in json.dumps(preset_data["workflowPresets"])

    pixi_data = tomllib.loads(toml_blocks[0])
    assert pixi_data["workspace"]["requires-pixi"] == ">=0.84.2"
    assert pixi_data["workspace"]["platforms"] == [
        "linux-64",
        "linux-aarch64",
        "osx-arm64",
    ]
    assert "libabseil" in pixi_data["dependencies"]
    assert "libcxx" not in pixi_data["dependencies"]
    assert "libcxx" in pixi_data["target"]["osx-arm64"]["dependencies"]


def test_t2_17_examples_gersemirc_valid_and_codeql_safe_schema_url() -> None:
    """Verify examples/.gersemirc enforces deterministic settings and a valid HTTPS schema URL."""
    gersemirc_path = EXAMPLES_DIR / ".gersemirc"
    cfg = _load_yaml_dict(gersemirc_path)
    assert cfg.get("indent") == 4
    assert cfg.get("line_length") == 100
    assert cfg.get("list_expansion") == "favour-inlining"
    assert cfg.get("warn_about_unknown_commands") is False

    raw_text = gersemirc_path.read_text(encoding="utf-8")
    match = re.search(r"\$schema=(https://\S+)", raw_text)
    assert match is not None, ".gersemirc missing yaml-language-server $schema header"
    parsed = urlparse(match.group(1))
    assert parsed.scheme == "https"
    assert parsed.hostname == "raw.githubusercontent.com"
    assert parsed.path.endswith("/gersemi/configuration.schema.json")


def test_t2_18_examples_pre_commit_config_sha_pinned_and_codeql_safe_urls() -> None:
    """Verify examples/.pre-commit-config.yaml SHA-pins hooks, excludes .pixi/, and validates URLs via urlparse."""
    cfg = _load_yaml_dict(EXAMPLES_DIR / ".pre-commit-config.yaml")
    exclude_regex = str(cfg.get("exclude", ""))
    assert r"^\.pixi/" in exclude_regex
    assert r"^build/" in exclude_regex

    repos = cfg.get("repos", [])
    assert isinstance(repos, list)
    assert len(repos) >= 3

    sha_pattern = re.compile(r"^[0-9a-f]{40}$")
    pinned_pre_commit_hooks = False
    hooks_by_id: dict[str, dict[str, Any]] = {}

    for repo_entry in repos:
        if not isinstance(repo_entry, dict):
            continue
        repo_value = str(repo_entry.get("repo", ""))
        if repo_value != "local":
            parsed_repo = urlparse(repo_value)
            assert parsed_repo.scheme == "https"
            assert parsed_repo.hostname == "github.com"
            assert parsed_repo.path == "/pre-commit/pre-commit-hooks"
            rev = str(repo_entry.get("rev", ""))
            assert sha_pattern.match(rev), (
                f"pre-commit-hooks rev '{rev}' must be a 40-char immutable SHA"
            )
            pinned_pre_commit_hooks = True
        for hook in repo_entry.get("hooks", []):
            if isinstance(hook, dict) and "id" in hook:
                hooks_by_id[str(hook["id"])] = hook

    assert pinned_pre_commit_hooks
    required_ids = {
        "trailing-whitespace",
        "end-of-file-fixer",
        "check-yaml",
        "check-toml",
        "check-json",
        "detect-private-key",
        "no-commit-to-branch",
        "gersemi",
        "clang-format",
        "clang-tidy",
    }
    assert not (required_ids - set(hooks_by_id.keys()))
    assert hooks_by_id["gersemi"]["entry"] == "gersemi --check"
    assert hooks_by_id["clang-format"]["entry"] == "clang-format --dry-run --Werror"
    assert (
        hooks_by_id["clang-tidy"]["entry"]
        == "clang-tidy -p build/ci-debug --warnings-as-errors=*"
    )
    assert hooks_by_id["clang-tidy"]["require_serial"] is True


def test_t2_19_examples_cmakelists_rejects_non_target_directives_and_hardcoded_verify() -> (
    None
):
    """Verify examples/CMakeLists.txt omits all 7 legacy non-target commands and hardcoded header-verify ON."""
    text = (EXAMPLES_DIR / "CMakeLists.txt").read_text(encoding="utf-8")
    for cmd in BANNED_NON_TARGET_COMMANDS:
        assert not re.search(rf"(?m)^\s*{cmd}\s*\(", text), (
            f"Banned non-target command '{cmd}()' in examples/CMakeLists.txt"
        )

    assert "CMAKE_VERIFY_INTERFACE_HEADER_SETS" not in text
    assert "CMAKE_VERIFY_PRIVATE_HEADER_SETS" not in text
    assert not re.search(r"set\(\s*CMAKE_CXX_SCAN_FOR_MODULES\b[^)]*\bCACHE\b", text)
    assert "# gersemi: off" in text
    assert "# gersemi: on" in text
    assert (
        text.index("# gersemi: off")
        < text.index("install(\n        SBOM")
        < text.index("# gersemi: on")
    )


def test_t2_20_cps_singular_export_vs_sbom_plural_exports_invariant() -> None:
    """Verify PACKAGE_INFO uses singular EXPORT while SBOM uses plural EXPORTS across templates and docs."""
    cmakelists_text = (EXAMPLES_DIR / "CMakeLists.txt").read_text(encoding="utf-8")
    pkg_doc = (REFERENCES_DIR / "packaging_cps_sbom_and_interop.md").read_text(
        encoding="utf-8"
    )
    pkg_cmake = "\n".join(_extract_fenced_blocks(pkg_doc, "cmake"))

    for raw_text in (cmakelists_text, pkg_cmake):
        text = re.sub(r"(?m)#.*$", "", raw_text)
        pkg_info_calls = re.findall(
            r"(?:install|export)\(\s*PACKAGE_INFO\b[^)]+\)", text, flags=re.DOTALL
        )
        assert pkg_info_calls
        for call in pkg_info_calls:
            assert re.search(r"\bEXPORT\b", call), (
                f"PACKAGE_INFO must use singular EXPORT: {call}"
            )
            assert not re.search(r"\bEXPORTS\b", call), (
                f"PACKAGE_INFO must not use plural EXPORTS: {call}"
            )

        sbom_calls = re.findall(
            r"(?:install|export)\(\s*SBOM\b[^)]+\)", text, flags=re.DOTALL
        )
        assert sbom_calls
        for call in sbom_calls:
            assert re.search(r"\bEXPORTS\b", call), (
                f"SBOM must use plural EXPORTS: {call}"
            )


def test_t2_21_file_set_set_property_uses_target_not_type_and_valid_diagnostic_actions() -> (
    None
):
    """Verify set_property(FILE_SET ...) uses TARGET (never TYPE) and cmake_diagnostic never uses ERROR."""
    pkg_doc = (REFERENCES_DIR / "packaging_cps_sbom_and_interop.md").read_text(
        encoding="utf-8"
    )
    pkg_cmake = "\n".join(_extract_fenced_blocks(pkg_doc, "cmake"))
    set_prop_calls = re.findall(r"set_property\(\s*FILE_SET\b[^)]+\)", pkg_cmake)
    assert len(set_prop_calls) >= 4
    for call in set_prop_calls:
        assert re.search(r"\bTARGET\b", call), (
            f"set_property(FILE_SET ...) must specify TARGET: {call}"
        )
        assert not re.search(r"\bTYPE\b", call), (
            f"set_property(FILE_SET ...) must not use TYPE: {call}"
        )

    for md_file in _all_markdown_files():
        text = md_file.read_text(encoding="utf-8")
        assert not re.search(r"cmake_diagnostic\(\s*SET\s+\S+\s+ERROR\s*\)", text), (
            f"Invalid cmake_diagnostic action 'ERROR' in '{md_file.name}'"
        )


def test_t2_22_toolchain_files_use_cmake_current_list_dir_not_source_or_binary_dir() -> (
    None
):
    """Verify cross-compilation toolchain blocks use CMAKE_CURRENT_LIST_DIR instead of source/binary dirs."""
    presets_doc = (REFERENCES_DIR / "presets_toolchains_and_pixi.md").read_text(
        encoding="utf-8"
    )
    cmake_blocks = _extract_fenced_blocks(presets_doc, "cmake")
    toolchain_blocks = [b for b in cmake_blocks if "set(CMAKE_SYSTEM_PROCESSOR" in b]
    assert len(toolchain_blocks) == 2
    assert "CMAKE_CURRENT_LIST_DIR" in toolchain_blocks[0]
    for block in toolchain_blocks:
        assert "CMAKE_SOURCE_DIR" not in block
        assert "CMAKE_BINARY_DIR" not in block
        assert "CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER" in block
        assert "CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY" in block
        assert "CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY" in block
        assert "CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY" in block


# ==============================================================================
# Tier 3: Cross-Feature & Sibling Interactions E2E Tests (>= 12 tests)
# ==============================================================================


def test_t3_01_ci_debug_binary_dir_matches_cpp_pro_pre_commit() -> None:
    """Interaction: cmake-pro ci-debug binaryDir (build/ci-debug) matches cpp-pro clang-tidy & pixi hooks."""
    cmake_presets = _load_json_dict(EXAMPLES_DIR / "CMakePresets.json")
    by_name = {str(p["name"]): p for p in cmake_presets["configurePresets"]}
    ci_resolved = _resolve_configure_preset(by_name, "ci-debug")
    assert ci_resolved["binaryDir"] == "${sourceDir}/build/${presetName}"
    assert ci_resolved["cacheVariables"]["CMAKE_EXPORT_COMPILE_COMMANDS"] == "ON"

    cmake_pre_commit = _load_yaml_dict(EXAMPLES_DIR / ".pre-commit-config.yaml")
    cpp_pre_commit = _load_yaml_dict(
        SKILLS_DIR / "cpp-pro" / "examples" / ".pre-commit-config.yaml"
    )
    cpp_pixi = _load_toml_dict(SKILLS_DIR / "cpp-pro" / "examples" / "pixi.toml")

    def _find_hook_entry(cfg: dict[str, Any], hook_id: str) -> str:
        for repo in cfg.get("repos", []):
            for hook in repo.get("hooks", []):
                if isinstance(hook, dict) and hook.get("id") == hook_id:
                    return str(hook.get("entry", ""))
        return ""

    assert "-p build/ci-debug" in _find_hook_entry(cmake_pre_commit, "clang-tidy")
    assert "-p build/ci-debug" in _find_hook_entry(cpp_pre_commit, "clang-tidy")
    assert "cmake --preset ci-debug" in str(cpp_pixi["tasks"]["configure"]["cmd"])


def test_t3_02_pre_commit_hooks_sha_matches_repo_and_cpp_pro() -> None:
    """Interaction: pre-commit-hooks SHA pin aligns across cmake-pro, cpp-pro, and repository root."""
    configs = [
        _load_yaml_dict(EXAMPLES_DIR / ".pre-commit-config.yaml"),
        _load_yaml_dict(
            SKILLS_DIR / "cpp-pro" / "examples" / ".pre-commit-config.yaml"
        ),
        _load_yaml_dict(ROOT_PRE_COMMIT),
    ]
    revs: list[str] = []
    for cfg in configs:
        for repo in cfg.get("repos", []):
            repo_val = str(repo.get("repo", ""))
            if repo_val == "local":
                continue
            parsed = urlparse(repo_val)
            if (
                parsed.scheme == "https"
                and parsed.hostname == "github.com"
                and parsed.path == "/pre-commit/pre-commit-hooks"
            ):
                revs.append(str(repo.get("rev", "")))

    assert len(revs) == 3
    assert len(set(revs)) == 1, f"pre-commit-hooks revisions diverged: {revs}"
    assert re.match(r"^[0-9a-f]{40}$", revs[0])


def test_t3_03_all_six_sibling_skills_reference_cmake_4_5_and_v13() -> None:
    """Interaction: All 6 sibling skills reference CMake 4.5 and v13 with zero stale 4.4.3 or v10+."""
    siblings = (
        "cpp-pro",
        "c-pro",
        "rust-pro",
        "ada-spark-pro",
        "github-flow-lifecycle",
        "github-ops",
    )
    for sibling in siblings:
        sibling_dir = SKILLS_DIR / sibling
        skill_text = (sibling_dir / "SKILL.md").read_text(encoding="utf-8")
        assert "CMake 4.5" in skill_text, (
            f"'{sibling}/SKILL.md' missing 'CMake 4.5' reference"
        )
        assert "v13" in skill_text, (
            f"'{sibling}/SKILL.md' missing Schema 'v13' reference"
        )
        for file_path in sibling_dir.rglob("*"):
            if not file_path.is_file():
                continue
            content = file_path.read_text(encoding="utf-8")
            assert "4.4.3" not in content, f"Stale CMake '4.4.3' found in '{file_path}'"
            assert "v10+" not in content, f"Stale preset 'v10+' found in '{file_path}'"


def test_t3_04_bidirectional_slash_references_across_skills() -> None:
    """Interaction: All 6 related skills exist in skills/ and cross-link bidirectionally with /cmake-pro."""
    cmake_skill = SKILL_MD.read_text(encoding="utf-8")
    discovered_skills = {
        p.name
        for p in SKILLS_DIR.iterdir()
        if p.is_dir() and (p / "SKILL.md").is_file()
    }

    for sibling in (
        "ada-spark-pro",
        "c-pro",
        "cpp-pro",
        "rust-pro",
        "python-pro",
        "github-flow-lifecycle",
    ):
        assert f"/{sibling}" in cmake_skill
        assert sibling in discovered_skills, (
            f"Related skill '{sibling}' missing from skills/"
        )

    for caller in (
        "cpp-pro",
        "c-pro",
        "rust-pro",
        "ada-spark-pro",
        "github-flow-lifecycle",
        "github-ops",
    ):
        caller_text = (SKILLS_DIR / caller / "SKILL.md").read_text(encoding="utf-8")
        assert "/cmake-pro" in caller_text, (
            f"'{caller}/SKILL.md' missing '/cmake-pro' cross-reference"
        )


def test_t3_05_readme_cmake_pro_row_links_all_examples_and_references() -> None:
    """Interaction: README.md cmake-pro row lists all 5 examples/* + references/, pixi, CMake 4.5+, and zero vcpkg."""
    readme_text = README_MD.read_text(encoding="utf-8")
    cmake_row = next(
        (line for line in readme_text.splitlines() if "| `cmake-pro` |" in line), ""
    )
    assert cmake_row, "README.md missing '| `cmake-pro` |' row"
    for expected in (
        "CMake 4.5+",
        "pixi",
        "conda-forge",
        "FILE_SETs",
        "CPS",
        "SBOM",
        "CMakePresets.json",
        "v13",
        "gersemi",
        "pixi.toml",
        "CMakeLists.txt",
        ".gersemirc",
        ".pre-commit-config.yaml",
        "references/",
    ):
        assert expected in cmake_row, f"README.md cmake-pro row missing '{expected}'"
    assert "vcpkg" not in cmake_row.lower()


def test_t3_06_multi_language_interop_c_pro() -> None:
    """Interaction: packaging_cps_sbom_and_interop.md C23 section aligns with c-pro/SKILL.md (<stdbit.h>)."""
    pkg_doc = (REFERENCES_DIR / "packaging_cps_sbom_and_interop.md").read_text(
        encoding="utf-8"
    )
    c_skill = (SKILLS_DIR / "c-pro" / "SKILL.md").read_text(encoding="utf-8")

    for token in (
        "CMAKE_C_STANDARD 23",
        'check_include_file("stdbit.h" HAVE_STDBIT_H)',
        "-ftrivial-auto-var-init=zero",
    ):
        assert token in pkg_doc, (
            f"packaging_cps_sbom_and_interop.md missing C23 token '{token}'"
        )
        assert token in c_skill, f"c-pro/SKILL.md missing C23 token '{token}'"
    assert "/c-pro" in pkg_doc
    assert 'extern "C"' in pkg_doc
    assert "std::out_ptr" in pkg_doc


def test_t3_07_multi_language_interop_rust_pro() -> None:
    """Interaction: packaging_cps_sbom_and_interop.md Rust interop aligns with rust-pro & Crubit."""
    pkg_doc = (REFERENCES_DIR / "packaging_cps_sbom_and_interop.md").read_text(
        encoding="utf-8"
    )
    rust_skill = (SKILLS_DIR / "rust-pro" / "SKILL.md").read_text(encoding="utf-8")

    assert "/rust-pro" in pkg_doc
    assert "Cargo" in pkg_doc
    assert "Corrosion" in pkg_doc
    assert "Crubit" in pkg_doc
    assert "corrosion_import_crate" in pkg_doc
    assert "cpp_api_from_rust" in pkg_doc
    assert "cc_bindings_from_rs" in pkg_doc
    assert "CMAKE_EXPERIMENTAL_RUST" in pkg_doc
    assert 'edition = "2024"' in pkg_doc
    assert "#![no_std]" in pkg_doc
    assert "#![no_std]" in rust_skill


def test_t3_08_multi_language_interop_ada_spark_pro() -> None:
    """Interaction: packaging_cps_sbom_and_interop.md SPARK Ada recipe aligns with ada-spark-pro."""
    pkg_doc = (REFERENCES_DIR / "packaging_cps_sbom_and_interop.md").read_text(
        encoding="utf-8"
    )
    ada_patterns = (
        SKILLS_DIR / "ada-spark-pro" / "references" / "canonical_patterns.md"
    ).read_text(encoding="utf-8")

    assert "/ada-spark-pro" in pkg_doc
    for shared_token in (
        "SparkTargets.cmake",
        "Halos::SparkSafety",
        "alr",
        "gnatprove",
        "spark_safety_build",
    ):
        assert shared_token in pkg_doc, (
            f"packaging_cps_sbom_and_interop.md missing SPARK token '{shared_token}'"
        )
        assert shared_token in ada_patterns, (
            f"ada-spark-pro/references/canonical_patterns.md missing '{shared_token}'"
        )
    assert 'Library_Standalone "encapsulated"' in pkg_doc
    assert "BUILD_DEPENDS spark_safety_build" in pkg_doc


def test_t3_09_multi_language_interop_python_pro_nanobind() -> None:
    """Interaction: packaging_cps_sbom_and_interop.md nanobind recipe aligns with /python-pro and /cpp-pro."""
    pkg_doc = (REFERENCES_DIR / "packaging_cps_sbom_and_interop.md").read_text(
        encoding="utf-8"
    )
    cpp_skill = (SKILLS_DIR / "cpp-pro" / "SKILL.md").read_text(encoding="utf-8")

    assert "/python-pro" in pkg_doc
    assert (
        "find_package(Python 3.14 COMPONENTS Interpreter Development.Module REQUIRED)"
        in pkg_doc
    )
    assert "nanobind --cmake_dir" in pkg_doc
    assert "find_package(nanobind CONFIG REQUIRED)" in pkg_doc
    assert "nanobind_add_module" in pkg_doc
    assert "Python_SITEARCH" in pkg_doc
    assert "LIBRARY DESTINATION" in pkg_doc
    assert "nanobind" in cpp_skill


def test_t3_10_stdlib_abi_rule_consistent_across_cmake_pro_and_cpp_pro() -> None:
    """Interaction: Platform-native Linux libstdc++ vs macOS libc++ ABI rule matches across cmake-pro and cpp-pro."""
    cmake_skill = SKILL_MD.read_text(encoding="utf-8")
    presets_doc = (REFERENCES_DIR / "presets_toolchains_and_pixi.md").read_text(
        encoding="utf-8"
    )
    cpp_skill = (SKILLS_DIR / "cpp-pro" / "SKILL.md").read_text(encoding="utf-8")
    cpp_style = (
        SKILLS_DIR / "cpp-pro" / "references" / "style_hierarchy_and_overrides.md"
    ).read_text(encoding="utf-8")

    for doc in (cmake_skill, presets_doc, cpp_skill, cpp_style):
        assert "libstdc++" in doc
        assert "libc++" in doc
        assert "-stdlib=libc++" in doc

    cmake_pixi = _load_toml_dict(EXAMPLES_DIR / "pixi.toml")
    cpp_pixi = _load_toml_dict(SKILLS_DIR / "cpp-pro" / "examples" / "pixi.toml")
    assert cmake_pixi["workspace"]["platforms"] == cpp_pixi["workspace"]["platforms"]
    assert "libcxx" in cmake_pixi["target"]["osx-arm64"]["dependencies"]
    assert "libcxx" in cpp_pixi["target"]["osx-arm64"]["dependencies"]


def test_t3_11_exceptions_rtti_and_modules_ban_consistent_with_cpp_pro() -> None:
    """Interaction: -fno-exceptions/-fno-rtti and C++ modules OFF defaults align between cmake-pro and cpp-pro."""
    cmake_templates = (REFERENCES_DIR / "canonical_templates.md").read_text(
        encoding="utf-8"
    )
    cpp_patterns = (
        SKILLS_DIR / "cpp-pro" / "references" / "hft_embedded_robotics_patterns.md"
    ).read_text(encoding="utf-8")
    cpp_skill = (SKILLS_DIR / "cpp-pro" / "SKILL.md").read_text(encoding="utf-8")

    for opt in (
        "option(ENABLE_EXCEPTIONS",
        "option(ENABLE_RTTI",
        "-fno-exceptions",
        "-fno-rtti",
    ):
        assert opt in cmake_templates
        assert opt in cpp_patterns

    presets = _load_json_dict(EXAMPLES_DIR / "CMakePresets.json")
    base_preset = next(p for p in presets["configurePresets"] if p["name"] == "base")
    assert base_preset["cacheVariables"]["CMAKE_CXX_SCAN_FOR_MODULES"] == "OFF"
    assert "modules" in cpp_skill.lower()


def test_t3_12_cache_line_alignment_constants_consistent_across_cmake_and_cpp() -> None:
    """Interaction: Architecture.cmake TARGET_CACHE_LINE_BYTES (128 ARM64 / 64 X86_64) matches cpp-pro."""
    cmake_templates = (REFERENCES_DIR / "canonical_templates.md").read_text(
        encoding="utf-8"
    )
    cpp_patterns = (
        SKILLS_DIR / "cpp-pro" / "references" / "hft_embedded_robotics_patterns.md"
    ).read_text(encoding="utf-8")

    assert "set(_cache_line_bytes 64)" in cmake_templates
    assert "set(_cache_line_bytes 128)" in cmake_templates
    assert "TARGET_CACHE_LINE_BYTES=${_cache_line_bytes}" in cmake_templates
    assert "128uz" in cpp_patterns
    assert "64uz" in cpp_patterns


def test_t3_13_github_flow_local_ci_matrix_matches_cmake_pro_workflow() -> None:
    """Interaction: github-flow-lifecycle local-ci-matrix.md prescribes cmake-pro's exact CI gate commands."""
    ci_matrix = (
        SKILLS_DIR / "github-flow-lifecycle" / "references" / "local-ci-matrix.md"
    ).read_text(encoding="utf-8")
    assert "/cmake-pro" in ci_matrix
    assert "gersemi --check" in ci_matrix
    assert "clang-format --dry-run --Werror" in ci_matrix
    assert "clang-tidy" in ci_matrix
    assert "cmake --workflow --preset" in ci_matrix


def test_t3_14_repo_validators_and_discovery_clean_for_cmake_pro() -> None:
    """Interaction: skills_validator, prompt_validator, secret_hygiene_validator, and .agents/skills.json pass."""
    skills_cfg = _load_json_dict(REPO_ROOT / ".agents" / "skills.json")
    entries = skills_cfg.get("entries", [])
    assert any(isinstance(e, dict) and e.get("path") == "skills" for e in entries)

    report = ValidationReport(strict=True)
    validate_skills(REPO_ROOT, report, fix=False)
    validate_prompts(REPO_ROOT, report)
    validate_secret_hygiene(REPO_ROOT, report)
    cmake_issues = [i for i in report.issues if "cmake-pro" in str(i.path)]
    assert not cmake_issues, f"Validators reported cmake-pro issues: {cmake_issues}"
    assert report.is_clean, f"Repository validation failed: {report.issues}"


# ==============================================================================
# Tier 4: Real-World Scenarios & Live Tooling E2E Tests (>= 6 tests)
# ==============================================================================


def test_t4_01_scenario_pixi_developer_preset_and_ci_chain() -> None:
    """Scenario: End-to-end trace of Pixi developer workflow -> CMakePresets v13 -> compile_commands -> pre-commit."""
    pixi = _load_toml_dict(EXAMPLES_DIR / "pixi.toml")
    presets = _load_json_dict(EXAMPLES_DIR / "CMakePresets.json")
    pre_commit = _load_yaml_dict(EXAMPLES_DIR / ".pre-commit-config.yaml")

    by_name = {str(p["name"]): p for p in presets["configurePresets"]}
    for dev_preset in ("ci-debug", "dev-debug", "dev-release", "ci-tsan"):
        resolved = _resolve_configure_preset(by_name, dev_preset)
        assert resolved["generator"] == "Ninja"
        assert resolved["binaryDir"] == "${sourceDir}/build/${presetName}"
        assert resolved["condition"] == {
            "type": "notEquals",
            "lhs": "$env{CONDA_PREFIX}",
            "rhs": "",
        }
        assert resolved["cacheVariables"]["CMAKE_C_COMPILER"] == "clang"
        assert resolved["cacheVariables"]["CMAKE_CXX_COMPILER"] == "clang++"
        assert resolved["cacheVariables"]["CMAKE_PREFIX_PATH"] == "$env{CONDA_PREFIX}"
        assert resolved["cacheVariables"]["CMAKE_EXPORT_COMPILE_COMMANDS"] == "ON"

    assert "cmake --preset ci-debug" in str(pixi["tasks"]["configure"]["cmd"])
    assert "cmake --build --preset ci-debug" in str(pixi["tasks"]["build"]["cmd"])
    assert "ctest --preset ci-debug" in str(pixi["tasks"]["test"]["cmd"])
    assert "cmake --workflow --preset ci-debug" in str(pixi["tasks"]["workflow"]["cmd"])
    assert "pre-commit run clang-tidy" in str(pixi["tasks"]["lint"]["cmd"])

    tidy_hook = next(
        h
        for r in pre_commit["repos"]
        for h in r.get("hooks", [])
        if isinstance(h, dict) and h.get("id") == "clang-tidy"
    )
    assert "-p build/ci-debug" in str(tidy_hook["entry"])


def test_t4_02_scenario_airgapped_sysroot_release_chain() -> None:
    """Scenario: End-to-end trace of air-gapped sysroot-release preset without $CONDA_PREFIX or FetchContent."""
    presets = _load_json_dict(EXAMPLES_DIR / "CMakePresets.json")
    by_name = {str(p["name"]): p for p in presets["configurePresets"]}
    sysroot_resolved = _resolve_configure_preset(by_name, "sysroot-release")

    assert sysroot_resolved["generator"] == "Ninja"
    assert "condition" not in sysroot_resolved
    assert "CMAKE_PREFIX_PATH" not in sysroot_resolved["cacheVariables"]
    assert sysroot_resolved["cacheVariables"]["CMAKE_BUILD_TYPE"] == "Release"
    assert sysroot_resolved["cacheVariables"]["ENABLE_IPO"] == "ON"
    assert sysroot_resolved["cacheVariables"]["CMAKE_CXX_SCAN_FOR_MODULES"] == "OFF"
    assert (
        sysroot_resolved["cacheVariables"]["CMAKE_VERIFY_INTERFACE_HEADER_SETS"] == "ON"
    )
    assert (
        sysroot_resolved["cacheVariables"]["CMAKE_INSTALL_SBOM_FORMATS"]
        == "spdx-3.0.1+json"
    )

    build_names = {str(bp["name"]): bp for bp in presets["buildPresets"]}
    assert build_names["sysroot-release"]["configurePreset"] == "sysroot-release"

    templates_doc = (REFERENCES_DIR / "canonical_templates.md").read_text(
        encoding="utf-8"
    )
    assert "find_package(absl CONFIG REQUIRED)" in templates_doc
    assert "CMAKE_SYSROOT" in templates_doc


def test_t4_03_scenario_riscv64_rva23_and_aarch64_cross_compilation_chain() -> None:
    """Scenario: End-to-end trace of RISC-V RVA23 & AArch64 cross presets, toolchains, emulator tests, and SIMD probes."""
    presets = _load_json_dict(EXAMPLES_DIR / "CMakePresets.json")
    by_name = {str(p["name"]): p for p in presets["configurePresets"]}
    riscv_resolved = _resolve_configure_preset(by_name, "cross-riscv64")
    arm_resolved = _resolve_configure_preset(by_name, "cross-aarch64")

    assert "condition" not in riscv_resolved
    assert "condition" not in arm_resolved
    assert (
        riscv_resolved["toolchainFile"]
        == "${fileDir}/cmake/toolchains/riscv64-linux-gnu.cmake"
    )
    assert (
        arm_resolved["toolchainFile"]
        == "${fileDir}/cmake/toolchains/aarch64-linux-gnu.cmake"
    )

    presets_doc = (REFERENCES_DIR / "presets_toolchains_and_pixi.md").read_text(
        encoding="utf-8"
    )
    templates_doc = (REFERENCES_DIR / "canonical_templates.md").read_text(
        encoding="utf-8"
    )

    assert "set(CMAKE_SYSTEM_PROCESSOR riscv64)" in presets_doc
    assert 'set(CMAKE_C_FLAGS_INIT "-march=rva23u64")' in presets_doc
    assert 'set(CMAKE_CXX_FLAGS_INIT "-march=rva23u64")' in presets_doc
    assert "qemu-riscv64" in presets_doc
    assert "qemu-aarch64" in presets_doc
    assert "elseif(CMAKE_CROSSCOMPILING_EMULATOR)" in templates_doc
    assert "DISCOVERY_MODE PRE_TEST" in templates_doc
    assert (
        "if(ENABLE_NATIVE_OPTIMIZATION AND NOT CMAKE_CROSSCOMPILING)" in templates_doc
    )
    assert "HAVE_RVV_1_0=1" in templates_doc
    assert "HAVE_SVE=1" in templates_doc


def test_t4_04_scenario_cps_and_spdx_sbom_packaging_pipeline() -> None:
    """Scenario: End-to-end trace of project() metadata, ALIAS install, GA CPS, and gersemi-guarded SPDX 3.0.1 SBOM."""
    cmakelists = (EXAMPLES_DIR / "CMakeLists.txt").read_text(encoding="utf-8")
    presets = _load_json_dict(EXAMPLES_DIR / "CMakePresets.json")
    gersemirc = _load_yaml_dict(EXAMPLES_DIR / ".gersemirc")
    pkg_doc = (REFERENCES_DIR / "packaging_cps_sbom_and_interop.md").read_text(
        encoding="utf-8"
    )

    assert "COMPAT_VERSION 1.0.0" in cmakelists
    assert 'SPDX_LICENSE "Apache-2.0"' in cmakelists
    assert "install(\n        TARGETS ModernCMakeTemplate::Core" in cmakelists
    assert (
        "install(\n        PACKAGE_INFO ModernCMakeTemplate\n        EXPORT ModernCMakeTemplateTargets\n        LOWER_CASE_FILE"
        in cmakelists
    )
    assert "# gersemi: off" in cmakelists
    assert "# gersemi: on" in cmakelists
    assert "FORMAT spdx-3.0.1+json" in cmakelists
    assert gersemirc["warn_about_unknown_commands"] is False

    by_name = {str(p["name"]): p for p in presets["configurePresets"]}
    for release_preset in ("dev-release", "sysroot-release"):
        resolved = _resolve_configure_preset(by_name, release_preset)
        assert (
            resolved["cacheVariables"]["CMAKE_INSTALL_SBOM_FORMATS"]
            == "spdx-3.0.1+json"
        )

    assert "$<LINK_ONLY:...>" in pkg_doc


def test_t4_05_scenario_live_cmake_list_presets_without_conda_prefix() -> None:
    """Scenario: Live cmake --list-presets=all-defined hides pixi presets and keeps sysroot/cross active."""
    cmake_exe = _require_cmake_4_5()
    env = os.environ.copy()
    env.pop("CONDA_PREFIX", None)

    result = subprocess.run(
        [cmake_exe, "-S", str(EXAMPLES_DIR), "--list-presets=all-defined"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"cmake --list-presets failed: {result.stderr}"
    stdout = result.stdout

    for pixi_preset in ("ci-debug", "dev-debug", "dev-release", "ci-tsan"):
        assert f'"{pixi_preset}"' in stdout
    assert "Unavailable: condition evaluated to false" in stdout
    assert "$env{CONDA_PREFIX}" in stdout

    # Standalone sysroot & cross configure presets must remain available (no Unavailable line after them)
    configure_section = stdout.split("Defined build presets:")[0]
    for standalone in ("sysroot-release", "cross-aarch64", "cross-riscv64"):
        lines = configure_section.splitlines()
        idx = next(i for i, line in enumerate(lines) if f'"{standalone}"' in line)
        next_line = lines[idx + 1] if idx + 1 < len(lines) else ""
        assert "Unavailable:" not in next_line, (
            f"'{standalone}' unexpectedly marked unavailable without CONDA_PREFIX"
        )


def test_t4_06_scenario_live_cmake_list_presets_with_conda_prefix(
    tmp_path: Path,
) -> None:
    """Scenario: Live cmake --list-presets=all-defined activates every preset when CONDA_PREFIX is set."""
    cmake_exe = _require_cmake_4_5()
    fake_conda_prefix = tmp_path / "pixi-env"
    fake_conda_prefix.mkdir()
    env = os.environ.copy()
    env["CONDA_PREFIX"] = str(fake_conda_prefix)

    result = subprocess.run(
        [cmake_exe, "-S", str(EXAMPLES_DIR), "--list-presets=all-defined"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"cmake --list-presets failed: {result.stderr}"
    assert "Unavailable:" not in result.stdout
    for preset_name in (
        "ci-debug",
        "dev-debug",
        "dev-release",
        "ci-tsan",
        "sysroot-release",
        "cross-aarch64",
        "cross-riscv64",
        "ci-release",
    ):
        assert f'"{preset_name}"' in result.stdout


def test_t4_07_scenario_live_cmake_presets_file_out_of_tree(tmp_path: Path) -> None:
    """Scenario: Live cmake --presets-file loads Schema v13 presets from an out-of-tree path."""
    cmake_exe = _require_cmake_4_5()
    proj_dir = tmp_path / "project"
    proj_dir.mkdir()
    (proj_dir / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 4.5)\nproject(OutOfTree LANGUAGES NONE)\n",
        encoding="utf-8",
    )

    external_dir = tmp_path / "external_presets"
    external_dir.mkdir()
    custom_presets = external_dir / "custom-v13.json"
    custom_presets.write_text(
        (EXAMPLES_DIR / "CMakePresets.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["CONDA_PREFIX"] = str(tmp_path / "pixi-env")
    result = subprocess.run(
        [
            cmake_exe,
            "-S",
            str(proj_dir),
            "--presets-file",
            str(custom_presets),
            "--list-presets=all-defined",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"cmake --presets-file failed: {result.stderr}"
    assert '"ci-debug"' in result.stdout
    assert "Unavailable:" not in result.stdout


def test_t4_08_scenario_live_cmake_diagnostic_and_file_set_configure(
    tmp_path: Path,
) -> None:
    """Scenario: Live CMake 4.5 rejects legacy include_directories() and accepts scoped FILE_SET + ALIAS targets."""
    cmake_exe = _require_cmake_4_5()

    bad_src = tmp_path / "bad_proj"
    bad_src.mkdir()
    bad_cmake = "\n".join([
        "cmake_minimum_required(VERSION 4.5)",
        "project(BadDiag LANGUAGES NONE)",
        "cmake_diagnostic(SET CMD_NON_TARGET_DIRECTIVE SEND_ERROR)",
        "include_directories(include)",
        "",
    ])
    (bad_src / "CMakeLists.txt").write_text(bad_cmake, encoding="utf-8")
    bad_result = subprocess.run(
        [cmake_exe, "-S", str(bad_src), "-B", str(bad_src / "build")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert bad_result.returncode != 0
    assert "non-target-directive" in bad_result.stderr

    good_src = tmp_path / "good_proj"
    (good_src / "include").mkdir(parents=True)
    (good_src / "include" / "core.hpp").write_text("#pragma once\n", encoding="utf-8")
    good_cmake = "\n".join([
        "cmake_minimum_required(VERSION 4.5)",
        'project(GoodProject VERSION 1.0.0 COMPAT_VERSION 1.0.0 SPDX_LICENSE "Apache-2.0" LANGUAGES NONE)',
        "cmake_diagnostic(SET CMD_NON_TARGET_DIRECTIVE SEND_ERROR)",
        "block(SCOPE_FOR VARIABLES POLICIES DIAGNOSTICS)",
        "    set(_probe_temp 1)",
        "endblock()",
        "add_library(modern_core INTERFACE)",
        "add_library(GoodProject::Core ALIAS modern_core)",
        "target_sources(modern_core INTERFACE FILE_SET HEADERS BASE_DIRS include FILES include/core.hpp)",
        'cmake_language(PRINT_TARGETS REGEX "^modern_core$")',
        "",
    ])
    (good_src / "CMakeLists.txt").write_text(good_cmake, encoding="utf-8")
    good_result = subprocess.run(
        [cmake_exe, "-S", str(good_src), "-B", str(good_src / "build")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert good_result.returncode == 0, (
        f"Compliant CMake 4.5 configure failed: {good_result.stderr}"
    )
    assert "modern_core (INTERFACE_LIBRARY)" in good_result.stdout
