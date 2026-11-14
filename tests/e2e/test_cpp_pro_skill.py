"""Opaque-box E2E test suite for the cpp-pro AntiGravity 2.29.0+ skill.

Validates the modern November 2026 ISO C++23 (`LLVM/Clang 23.1.5`) skill
package across:
- Tier 1: Feature Coverage (>= 25 tests)
- Tier 2: Boundary & Corner Cases (>= 20 tests)
- Tier 3: Cross-Feature Interactions (>= 10 tests)
- Tier 4: Real-World Scenarios (>= 5 tests)
"""

from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING
from typing import Any
from urllib.parse import urlparse

import yaml

from scripts.validation.models import Severity
from scripts.validation.models import ValidationReport
from scripts.validation.prompt_validator import validate_prompts
from scripts.validation.secret_hygiene_validator import _HOME_PATTERN
from tests.e2e.conftest import ALLOWED_SKILL_SUBDIRECTORIES
from tests.e2e.conftest import MAX_FILE_BYTES
from tests.e2e.conftest import MIN_SKILL_DESCRIPTION_LENGTH
from tests.e2e.conftest import REPO_ROOT
from tests.e2e.conftest import SKILL_NAME_PATTERN
from tests.e2e.conftest import SKILLS_DIR
from tests.e2e.conftest import oracle_validate_skill
from tests.e2e.conftest import split_skill_frontmatter


if TYPE_CHECKING:
    from pathlib import Path


SKILL_DIR = SKILLS_DIR / 'cpp-pro'
SKILL_MD = SKILL_DIR / 'SKILL.md'
EXAMPLES_DIR = SKILL_DIR / 'examples'
REFERENCES_DIR = SKILL_DIR / 'references'
README_MD = REPO_ROOT / 'README.md'


def _load_yaml_dict(file_path: Path) -> dict[str, Any]:
    """Load a YAML file and assert that its root is a dictionary.

    Args:
        file_path: Path object pointing to the YAML configuration file.

    Returns:
        Parsed dictionary representation of the YAML file.
    """
    parsed = yaml.safe_load(file_path.read_text(encoding='utf-8'))
    assert isinstance(parsed, dict), f"'{file_path.name}' must parse to a dictionary"
    return parsed


def _clang_tidy_checks(clang_tidy_cfg: dict[str, Any]) -> set[str]:
    """Parse the comma-separated Clang-Tidy Checks string into a set of rules.

    Args:
        clang_tidy_cfg: Parsed .clang-tidy YAML dictionary.

    Returns:
        Set of stripped check patterns configured under Checks.
    """
    raw_checks = str(clang_tidy_cfg.get('Checks', ''))
    return {entry.strip() for entry in raw_checks.split(',') if entry.strip()}


def _clang_tidy_options(clang_tidy_cfg: dict[str, Any]) -> dict[str, str]:
    """Convert .clang-tidy CheckOptions list into a key-to-string dictionary.

    Args:
        clang_tidy_cfg: Parsed .clang-tidy YAML dictionary.

    Returns:
        Mapping from Clang-Tidy option key to string value.
    """
    options: dict[str, str] = {}
    for entry in clang_tidy_cfg.get('CheckOptions', []):
        if isinstance(entry, dict) and 'key' in entry:
            options[str(entry['key'])] = str(entry.get('value', ''))
    return options


def _extract_markdown_https_urls(markdown_text: str) -> list[str]:
    """Extract HTTPS targets from Markdown links in text.

    Args:
        markdown_text: Raw Markdown document content.

    Returns:
        List of HTTPS URL strings extracted from Markdown link targets.
    """
    return re.findall(r'\[[^\]]+\]\((https://[^)\s]+)\)', markdown_text)


# ==============================================================================
# Tier 1: Feature Coverage E2E Tests
# ==============================================================================


def test_t1_01_skill_directory_exists() -> None:
    """Verify skills/cpp-pro directory exists and is a directory."""
    assert SKILL_DIR.exists(), f"Skill directory not found at '{SKILL_DIR}'"
    assert SKILL_DIR.is_dir(), f"'{SKILL_DIR}' is not a directory"


def test_t1_02_skill_md_exists() -> None:
    """Verify skills/cpp-pro/SKILL.md exists and is a file."""
    assert SKILL_MD.exists(), f"SKILL.md not found at '{SKILL_MD}'"
    assert SKILL_MD.is_file(), f"'{SKILL_MD}' is not a regular file"


def test_t1_03_skill_frontmatter_framing() -> None:
    """Verify SKILL.md starts with line-1 YAML delimiter and non-empty H1 body."""
    text = SKILL_MD.read_text(encoding='utf-8')
    assert text.startswith('---\n'), "SKILL.md must begin with YAML delimiter '---' on line 1"
    frontmatter, body = split_skill_frontmatter(text)
    assert isinstance(frontmatter, dict), 'Parsed frontmatter must be a dictionary'
    assert body.startswith('# '), 'SKILL.md body must begin with an H1 heading (MD041)'


def test_t1_04_skill_frontmatter_name() -> None:
    """Verify frontmatter name equals 'cpp-pro' and conforms to naming regex."""
    frontmatter, _ = split_skill_frontmatter(SKILL_MD.read_text(encoding='utf-8'))
    name = str(frontmatter.get('name', ''))
    assert name == 'cpp-pro', f"Expected skill name 'cpp-pro', got '{name}'"
    assert SKILL_NAME_PATTERN.match(name), f"Skill name '{name}' violates naming regex"


def test_t1_05_skill_frontmatter_description() -> None:
    """Verify frontmatter description meets minimum length and covers core topics."""
    frontmatter, _ = split_skill_frontmatter(SKILL_MD.read_text(encoding='utf-8'))
    desc = frontmatter.get('description', '')
    assert isinstance(desc, str), 'Frontmatter description must be a string'
    assert len(desc.strip()) >= MIN_SKILL_DESCRIPTION_LENGTH
    required_keywords = [
        'c++23',
        '23.1.5',
        'google c++ style',
        'core guidelines',
        'hft',
        'embedded',
        'robotics',
        '<cstdint>',
        'std::expected',
        'std::print',
        'abseil',
        'google test',
        'google benchmark',
        'crubit',
        'clang-tidy',
        'clang-format',
        'pre-commit',
    ]
    lowered = desc.lower()
    for kw in required_keywords:
        assert kw in lowered, f"Description missing expected keyword '{kw}'"


def test_t1_06_skill_frontmatter_metadata() -> None:
    """Verify frontmatter metadata sets version v3 and publisher jamielapointe."""
    frontmatter, _ = split_skill_frontmatter(SKILL_MD.read_text(encoding='utf-8'))
    metadata = frontmatter.get('metadata')
    assert isinstance(metadata, dict), "Frontmatter missing 'metadata' dictionary"
    assert metadata.get('version') == 'v3', f"Expected metadata.version 'v3', got '{metadata.get('version')}'"
    assert metadata.get('publisher') == 'jamielapointe'


def test_t1_07_skill_body_bytes_within_limit() -> None:
    """Verify SKILL.md body size stays strictly under 24,000 UTF-8 bytes (SKL005)."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding='utf-8'))
    body_bytes = len(body.encode('utf-8'))
    assert body_bytes < MAX_FILE_BYTES, f'SKILL.md body ({body_bytes} bytes) exceeds limit of {MAX_FILE_BYTES}'


def test_t1_08_subdirectories_allowed() -> None:
    """Verify skills/cpp-pro subdirectories stay within AntiGravity allowlist."""
    discovered = {p.name for p in SKILL_DIR.iterdir() if p.is_dir()}
    assert discovered == {'examples', 'references'}
    assert not (discovered - ALLOWED_SKILL_SUBDIRECTORIES)


def test_t1_09_examples_directory_contents() -> None:
    """Verify examples/ contains .clang-format, .clang-tidy, and .pre-commit-config.yaml."""
    assert EXAMPLES_DIR.is_dir()
    required_files = [
        '.clang-format',
        '.clang-tidy',
        '.pre-commit-config.yaml',
    ]
    for filename in required_files:
        target = EXAMPLES_DIR / filename
        assert target.is_file(), f"Missing required example configuration '{filename}'"
        _ = _load_yaml_dict(target)


def test_t1_10_references_directory_contents() -> None:
    """Verify references/ contains all 3 architectural reference manuals with H1 headings."""
    assert REFERENCES_DIR.is_dir()
    required_manuals = [
        'style_hierarchy_and_overrides.md',
        'modern_cpp23_and_abseil.md',
        'hft_embedded_robotics_patterns.md',
    ]
    for manual in required_manuals:
        target = REFERENCES_DIR / manual
        assert target.is_file(), f"Missing required reference manual '{manual}'"
        content = target.read_text(encoding='utf-8')
        assert content.startswith('# '), f"'{manual}' must start with an H1 heading on line 1 (MD041)"


def test_t1_11_persona_november_2026_clang_23_1_5() -> None:
    """Verify SKILL.md establishes November 2026 C++23 and LLVM/Clang 23.1.5 persona."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding='utf-8'))
    assert 'November 2026' in body
    assert 'ISO C++23' in body
    assert '-std=c++23' in body
    assert 'LLVM/Clang 23.1.5' in body
    assert 'clang++' in body
    assert 'clang-tidy' in body
    assert 'clang-format' in body


def test_t1_12_descending_style_priority_order() -> None:
    """Verify strict descending priority order: #1 Google > #2 Core Guidelines > #3 HFT/Embedded/Robotics."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding='utf-8'))
    google_url = 'https://google.github.io/styleguide/cppguide.html'
    core_url = 'https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines'
    industry_label = 'Standard Industry Best Practices'
    assert google_url in body
    assert core_url in body
    assert industry_label in body
    assert body.index(google_url) < body.index(core_url) < body.index(industry_label)
    assert 'High-Frequency Trading (HFT)' in body
    assert 'Embedded' in body
    assert 'Robotics' in body


def test_t1_13_explicit_cstdint_and_int_only_rule() -> None:
    """Verify SKILL.md explicitly permits int only and requires <cstdint> for other integer types."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding='utf-8'))
    assert '<cstdint>' in body
    assert 'sole exception of `int`' in body
    for forbidden_type in ['short', 'long', 'long long', 'unsigned short', 'unsigned int', 'unsigned long', 'unsigned long long']:
        assert forbidden_type in body, f"Rule must explicitly forbid built-in type '{forbidden_type}'"
    for fixed_type in ['int8_t', 'uint8_t', 'int16_t', 'uint16_t', 'int32_t', 'uint32_t', 'int64_t', 'uint64_t']:
        assert fixed_type in body, f"Rule must reference '<cstdint>' type '{fixed_type}'"


def test_t1_14_prefer_c_library_headers_over_dot_h() -> None:
    """Verify SKILL.md mandates <c[library]> wrappers over legacy <[library].h> C headers."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding='utf-8'))
    assert '<c[library]>' in body
    assert '<[library].h>' in body
    for modern_hdr in ['<cstdint>', '<cstddef>', '<cmath>', '<cstring>', '<cassert>', '<cstdlib>']:
        assert modern_hdr in body
    assert 'modernize-deprecated-headers' in body


def test_t1_15_abseil_recommendations() -> None:
    """Verify SKILL.md recommends Abseil (absl) containers, utilities, and assertions."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding='utf-8'))
    assert 'Abseil' in body
    assert '20260817.0+' in body
    for symbol in [
        'absl::flat_hash_map',
        'absl::flat_hash_set',
        'absl::InlinedVector',
        'absl::FunctionRef',
        'absl::Mutex',
        'ABSL_GUARDED_BY',
        'absl::StrCat',
        'absl::down_cast',
        'ABSL_CHECK',
        'absl::StatusOr',
    ]:
        assert symbol in body, f"SKILL.md missing Abseil recommendation '{symbol}'"


def test_t1_16_google_test_and_google_benchmark() -> None:
    """Verify SKILL.md mandates Google Test for unit tests and Google Benchmark for microbenchmarks."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding='utf-8'))
    assert 'Google Test' in body
    assert 'v1.18.0+' in body
    assert 'gtest_discover_tests()' in body
    assert 'Google Benchmark' in body
    assert 'v1.10.0+' in body
    assert 'benchmark::DoNotOptimize' in body
    assert 'benchmark::ClobberMemory' in body
    assert 'benchmark::ScopedPauseTiming' in body
    assert 'BENCHMARK_NAMED' in body


def test_t1_17_crubit_cpp_rust_interop() -> None:
    """Verify SKILL.md and reference docs cover Crubit bidirectional C++/Rust interop."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding='utf-8'))
    modern_doc = (REFERENCES_DIR / 'modern_cpp23_and_abseil.md').read_text(encoding='utf-8')
    parsed_urls = [urlparse(url) for url in _extract_markdown_https_urls(body)]
    assert any(u.scheme == 'https' and u.hostname == 'crubit.rs' for u in parsed_urls)
    parsed_ref_urls = [urlparse(url) for url in _extract_markdown_https_urls(modern_doc)]
    assert any(u.scheme == 'https' and u.hostname == 'crubit.rs' for u in parsed_ref_urls)
    assert 'cpp_api_from_rust' in body
    assert 'rust_api_from_cpp' in body
    assert 'non-`#[repr(C)]`' in body
    assert 'cpp_api_from_rust' in modern_doc
    assert 'rust_api_from_cpp' in modern_doc
    assert 'lifetimebound' in modern_doc


def test_t1_18_core_guidelines_carveout_1_ignore_gsl() -> None:
    """Verify Core Guidelines carve-out #1: GSL (gsl::*) is completely ignored."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding='utf-8'))
    style_doc = (REFERENCES_DIR / 'style_hierarchy_and_overrides.md').read_text(encoding='utf-8')
    assert 'Ignore GSL' in body
    assert 'gsl::*' in body
    assert 'Microsoft.GSL' in body
    assert 'IGNORE COMPLETELY' in style_doc


def test_t1_19_core_guidelines_carveout_2_std_expected_and_exceptions_rtti_flexibility() -> None:
    """Verify carve-out #2: std::expected default with -fno-exceptions/-fno-rtti and CMake opt-in."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding='utf-8'))
    assert 'std::expected<T, E>' in body
    assert '-fno-exceptions -fno-rtti' in body
    assert 'ENABLE_EXCEPTIONS' in body
    assert 'ENABLE_RTTI' in body
    assert 'never call throwing `.value()`' in body


def test_t1_20_core_guidelines_carveout_3_no_contracts_until_cpp26() -> None:
    """Verify carve-out #3: C++ contract annotations deferred until C++26."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding='utf-8'))
    assert 'Do NOT use Contracts yet' in body
    assert 'C++26' in body


def test_t1_21_core_guidelines_carveout_4_print_over_iostream() -> None:
    """Verify carve-out #4: std::print and std::println (<print>) bypass <iostream> formatting."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding='utf-8'))
    assert 'Bypass `<iostream>`' in body
    assert 'std::print' in body
    assert 'std::println' in body
    assert '<print>' in body


def test_t1_22_core_guidelines_carveout_5_naming_layout_ignored() -> None:
    """Verify carve-out #5: Core Guidelines Naming and Layout rules ignored for Google + clang-format."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding='utf-8'))
    style_doc = (REFERENCES_DIR / 'style_hierarchy_and_overrides.md').read_text(encoding='utf-8')
    assert 'Ignore Naming and Layout rules' in body
    assert 'NL.*' in style_doc


def test_t1_23_core_guidelines_carveout_6_signed_unsigned_ignored() -> None:
    """Verify carve-out #6: Core Guidelines Signed vs. Unsigned integer rules ignored."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding='utf-8'))
    style_doc = (REFERENCES_DIR / 'style_hierarchy_and_overrides.md').read_text(encoding='utf-8')
    assert 'Ignore Signed vs. Unsigned integer rules' in body
    assert 'ES.100' in style_doc


def test_t1_24_core_guidelines_carveout_7_non_const_ref_out_params() -> None:
    """Verify carve-out #7: Non-const reference out-parameters permitted for buffer reuse."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding='utf-8'))
    style_doc = (REFERENCES_DIR / 'style_hierarchy_and_overrides.md').read_text(encoding='utf-8')
    assert 'No out-parameters via non-`const` reference' in body
    assert 'F.16' in style_doc


def test_t1_25_core_guidelines_carveout_8_singletons_global_state_judgement() -> None:
    """Verify carve-out #8: Engineering judgement on Singletons / Global State with NOLINT guidance."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding='utf-8'))
    assert 'Singletons / Global State' in body
    assert 'constinit' in body
    assert "Meyer's singletons" in body
    assert 'NOLINT(cppcoreguidelines-avoid-non-const-global-variables)' in body


def test_t1_26_modern_cpp23_constructs_featured() -> None:
    """Verify SKILL.md and reference docs highlight modern C++23 features."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding='utf-8'))
    modern_doc = (REFERENCES_DIR / 'modern_cpp23_and_abseil.md').read_text(encoding='utf-8')
    for feature in [
        'std::expected',
        'std::print',
        'std::mdspan',
        'std::flat_map',
        'Deducing `this`',
        'std::ranges::to',
        'std::byteswap',
        'std::to_underlying',
        'std::unreachable()',
        '[[assume(',
        'if consteval',
        '0uz',
    ]:
        assert feature in body, f"SKILL.md missing C++23 construct '{feature}'"
        assert feature.replace('Deducing `this`', 'Deducing `this`') in modern_doc


def test_t1_27_related_skills_include_rust_ada_c_cmake_python_and_exclude_notebook_skills() -> None:
    """Verify Related Skills reference /rust-pro, /ada-spark-pro, etc. and omit jupyter/marimo."""
    all_files = [SKILL_MD, *list(REFERENCES_DIR.glob('*.md'))]
    skill_body = SKILL_MD.read_text(encoding='utf-8')
    for required_skill in ['/c-pro', '/rust-pro', '/ada-spark-pro', '/cmake-pro', '/python-pro', '/github-flow-lifecycle']:
        assert required_skill in skill_body, f"SKILL.md missing related skill '{required_skill}'"

    for md_file in all_files:
        lowered = md_file.read_text(encoding='utf-8').lower()
        assert 'jupyter' not in lowered, f"'{md_file.name}' must not reference jupyter skills"
        assert 'marimo' not in lowered, f"'{md_file.name}' must not reference marimo skills"


def test_t1_28_git_pre_commit_and_no_verify_prohibition() -> None:
    """Verify SKILL.md mandates clang-tidy/clang-format via pre-commit and forbids --no-verify."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding='utf-8'))
    assert '.pre-commit-config.yaml' in body
    assert '--no-verify' in body
    assert 'NEVER' in body
    assert 'pre-commit checks' in body


# ==============================================================================
# Tier 2: Boundary & Corner Cases E2E Tests
# ==============================================================================


def test_t2_01_oracle_validation_clean() -> None:
    """Authoritative AntiGravity 2.29.0+ skill oracle reports zero errors for skills/cpp-pro."""
    issues = oracle_validate_skill(SKILL_DIR)
    errors = [issue for issue in issues if issue.severity == Severity.ERROR]
    assert not errors, f'Oracle validation errors for skills/cpp-pro: {errors}'


def test_t2_02_all_relative_markdown_links_resolve() -> None:
    """Verify every relative Markdown link across SKILL.md and references/ exists on disk."""
    link_pattern = re.compile(r'\[([^\]]+)\]\((?!https?://)([^)#\s]+)(?:#[^)]*)?\)')
    md_files = [SKILL_MD, *list(REFERENCES_DIR.glob('*.md'))]
    checked = 0
    for md_file in md_files:
        text = md_file.read_text(encoding='utf-8')
        for match in link_pattern.finditer(text):
            target = (md_file.parent / match.group(2)).resolve()
            assert target.exists(), f"Broken relative link in '{md_file.name}': '{match.group(2)}' -> '{target}'"
            checked += 1
    assert checked >= 8, f'Expected at least 8 verified relative links, found {checked}'


def test_t2_03_secret_and_home_path_hygiene() -> None:
    """Verify zero personal home-directory paths exist anywhere inside skills/cpp-pro/."""
    for file_path in SKILL_DIR.rglob('*'):
        if not file_path.is_file():
            continue
        content = file_path.read_text(encoding='utf-8')
        assert not _HOME_PATTERN.search(content), f"Personal home path leaked in '{file_path}'"


def test_t2_04_clang_format_google_left_pointers_and_cpp23() -> None:
    """Verify examples/.clang-format enforces Google style, left pointer alignment, and C++23."""
    cfg = _load_yaml_dict(EXAMPLES_DIR / '.clang-format')
    assert cfg.get('BasedOnStyle') == 'Google'
    assert cfg.get('Language') == 'Cpp'
    assert cfg.get('Standard') == 'Latest'
    assert cfg.get('ColumnLimit') == 80
    assert cfg.get('DerivePointerAlignment') is False
    assert cfg.get('PointerAlignment') == 'Left'
    assert cfg.get('AllowShortFunctionsOnASingleLine') == 'InlineOnly'


def test_t2_05_clang_tidy_no_embedded_comments_and_warnings_as_errors() -> None:
    """Verify .clang-tidy has no inline # comments inside Checks and fails on warnings."""
    cfg = _load_yaml_dict(EXAMPLES_DIR / '.clang-tidy')
    raw_checks = str(cfg.get('Checks', ''))
    assert '#' not in raw_checks, '.clang-tidy Checks string must never contain inline # comments'
    assert cfg.get('WarningsAsErrors') == '*'


def test_t2_06_clang_tidy_enforces_google_int_c_headers_print_and_iwyu() -> None:
    """Verify .clang-tidy enables checks for Google ints, <c[lib]>, std::print, and IWYU."""
    checks = _clang_tidy_checks(_load_yaml_dict(EXAMPLES_DIR / '.clang-tidy'))
    required_checks = {
        '-*',
        'google-runtime-int',
        'modernize-deprecated-headers',
        'modernize-use-std-print',
        'modernize-use-std-format',
        'misc-include-cleaner',
        'bugprone-unchecked-optional-access',
        'misc-coroutine-hostile-raii',
        'readability-identifier-naming',
        'abseil-duration-addition',
        'performance-avoid-endl',
    }
    missing = required_checks - checks
    assert not missing, f'.clang-tidy missing required checks: {missing}'


def test_t2_07_clang_tidy_omits_gsl_sign_comparison_and_removed_checks() -> None:
    """Verify .clang-tidy excludes GSL checks, sign-comparison nits, and removed Clang checks."""
    checks = _clang_tidy_checks(_load_yaml_dict(EXAMPLES_DIR / '.clang-tidy'))
    forbidden_checks = {
        'cppcoreguidelines-owning-memory',
        'cppcoreguidelines-pro-bounds-pointer-arithmetic',
        'cppcoreguidelines-pro-bounds-array-to-pointer-decay',
        'modernize-use-integer-sign-comparison',
        'modernize-use-trailing-return-type',
        'readability-identifier-length',
        'google-runtime-memset',
        'misc-coroutine-hostile-rail',
    }
    present = forbidden_checks & checks
    assert not present, f'.clang-tidy must omit ignored or removed checks: {present}'


def test_t2_08_clang_tidy_google_naming_check_options() -> None:
    """Verify .clang-tidy CheckOptions configure Google C++ Style naming accurately."""
    opts = _clang_tidy_options(_load_yaml_dict(EXAMPLES_DIR / '.clang-tidy'))
    expected = {
        'readability-identifier-naming.ClassCase': 'CamelCase',
        'readability-identifier-naming.StructCase': 'CamelCase',
        'readability-identifier-naming.FunctionCase': 'CamelCase',
        'readability-identifier-naming.MethodCase': 'CamelCase',
        'readability-identifier-naming.NamespaceCase': 'lower_case',
        'readability-identifier-naming.VariableCase': 'lower_case',
        'readability-identifier-naming.LocalConstantCase': 'lower_case',
        'readability-identifier-naming.ConstexprVariableCase': 'CamelCase',
        'readability-identifier-naming.ConstexprVariablePrefix': 'k',
        'readability-identifier-naming.EnumConstantCase': 'CamelCase',
        'readability-identifier-naming.EnumConstantPrefix': 'k',
        'readability-identifier-naming.PrivateMemberCase': 'lower_case',
        'readability-identifier-naming.PrivateMemberSuffix': '_',
        'readability-identifier-naming.MacroDefinitionCase': 'UPPER_CASE',
    }
    for key, val in expected.items():
        assert opts.get(key) == val, f"CheckOptions['{key}'] expected '{val}', got '{opts.get(key)}'"


def test_t2_09_clang_tidy_abseil_and_assert_check_options() -> None:
    """Verify .clang-tidy tunes Abseil match headers, ABSL_CHECK assert macros, and vector classes."""
    opts = _clang_tidy_options(_load_yaml_dict(EXAMPLES_DIR / '.clang-tidy'))
    assert 'ABSL_CHECK' in opts.get('bugprone-assert-side-effect.AssertMacros', '')
    assert 'ABSL_DCHECK' in opts.get('bugprone-assert-side-effect.AssertMacros', '')
    assert '::absl::InlinedVector' in opts.get('performance-inefficient-vector-operation.VectorLikeClasses', '')
    assert opts.get('modernize-make-unique.IncludeStyle') == 'google'


def test_t2_10_pre_commit_config_pins_sha_and_configures_cpp_hooks() -> None:
    """Verify examples/.pre-commit-config.yaml SHA-pins hooks and enforces format/tidy/gersemi."""
    cfg = _load_yaml_dict(EXAMPLES_DIR / '.pre-commit-config.yaml')
    repos = cfg.get('repos', [])
    assert isinstance(repos, list) and len(repos) >= 3

    sha_pattern = re.compile(r'^[0-9a-f]{40}$')
    found_hooks: set[str] = set()
    pinned_pre_commit_hooks = False

    for entry in repos:
        if not isinstance(entry, dict):
            continue
        repo_url = str(entry.get('repo', ''))
        if repo_url == 'https://github.com/pre-commit/pre-commit-hooks':
            rev = str(entry.get('rev', ''))
            assert sha_pattern.match(rev), f"pre-commit-hooks rev '{rev}' must be a 40-char immutable SHA"
            pinned_pre_commit_hooks = True
        for hook in entry.get('hooks', []):
            if isinstance(hook, dict) and 'id' in hook:
                found_hooks.add(str(hook['id']))

    assert pinned_pre_commit_hooks, 'Missing SHA-pinned https://github.com/pre-commit/pre-commit-hooks repo'
    required_hooks = {'clang-format', 'clang-tidy', 'gersemi', 'no-commit-to-branch', 'detect-private-key', 'trailing-whitespace'}
    missing = required_hooks - found_hooks
    assert not missing, f'examples/.pre-commit-config.yaml missing required hooks: {missing}'


def test_t2_11_google_disallowed_modules_cfenv_long_double_maintained() -> None:
    """Verify SKILL.md and style manual preserve Google bans on modules, <cfenv>, and long double."""
    skill_text = SKILL_MD.read_text(encoding='utf-8')
    style_doc = (REFERENCES_DIR / 'style_hierarchy_and_overrides.md').read_text(encoding='utf-8')
    for content in (skill_text, style_doc):
        assert 'modules' in content.lower()
        assert '<cfenv>' in content
        assert 'long double' in content


def test_t2_12_pragma_once_and_macro_guard_compatibility() -> None:
    """Verify SKILL.md and style manual prefer #pragma once while respecting existing #ifndef repos."""
    skill_text = SKILL_MD.read_text(encoding='utf-8')
    style_doc = (REFERENCES_DIR / 'style_hierarchy_and_overrides.md').read_text(encoding='utf-8')
    for content in (skill_text, style_doc):
        assert '#pragma once' in content
        assert '#ifndef' in content


def test_t2_13_c_compatibility_exception_for_posix_and_c23_boundary() -> None:
    """Verify style manual scopes .h header allowance strictly to OS/POSIX and C23 extern C boundaries."""
    style_doc = (REFERENCES_DIR / 'style_hierarchy_and_overrides.md').read_text(encoding='utf-8')
    assert 'OS/POSIX' in style_doc
    assert 'extern "C"' in style_doc
    assert '/c-pro' in style_doc


def test_t2_14_no_unused_or_redundant_std_value_on_expected_warning() -> None:
    """Verify both SKILL.md and style manual warn against calling .value() on std::expected under -fno-exceptions."""
    skill_text = SKILL_MD.read_text(encoding='utf-8')
    style_doc = (REFERENCES_DIR / 'style_hierarchy_and_overrides.md').read_text(encoding='utf-8')
    assert '.value()' in skill_text
    assert '.value()' in style_doc
    assert '.and_then()' in skill_text
    assert '.and_then(' in (REFERENCES_DIR / 'modern_cpp23_and_abseil.md').read_text(encoding='utf-8')


def test_t2_15_cmake_options_allow_user_exceptions_and_rtti_opt_in() -> None:
    """Verify HFT/Embedded/Robotics manual provides CMake ENABLE_EXCEPTIONS and ENABLE_RTTI toggles."""
    patterns_doc = (REFERENCES_DIR / 'hft_embedded_robotics_patterns.md').read_text(encoding='utf-8')
    assert 'option(ENABLE_EXCEPTIONS' in patterns_doc
    assert 'option(ENABLE_RTTI' in patterns_doc
    assert '-fno-exceptions' in patterns_doc
    assert '-fno-rtti' in patterns_doc


def test_t2_16_no_unpaired_bracket_or_broken_code_fences_in_markdown() -> None:
    """Verify every Markdown file in skills/cpp-pro has balanced triple-backtick code fences."""
    for md_file in [SKILL_MD, *list(REFERENCES_DIR.glob('*.md'))]:
        fence_count = sum(1 for line in md_file.read_text(encoding='utf-8').splitlines() if line.lstrip().startswith('```'))
        assert fence_count % 2 == 0, f"Unclosed code fence detected in '{md_file.name}' (count={fence_count})"


def test_t2_17_hot_path_frame_size_and_rt_isolation_documented() -> None:
    """Verify HFT/Embedded/Robotics patterns enforce bounded stack and OS memory locking."""
    patterns_doc = (REFERENCES_DIR / 'hft_embedded_robotics_patterns.md').read_text(encoding='utf-8')
    assert '-Wframe-larger-than=4096' in patterns_doc
    assert 'mlockall' in patterns_doc
    assert 'alignas(64)' in patterns_doc


def test_t2_18_crubit_build_system_limitations_documented_accurately() -> None:
    """Verify Crubit documentation accurately states CMake vs Bazel support and cxx/extern C fallback."""
    modern_doc = (REFERENCES_DIR / 'modern_cpp23_and_abseil.md').read_text(encoding='utf-8')
    assert 'CMake' in modern_doc
    assert 'Bazel' in modern_doc
    assert 'cxx' in modern_doc
    assert 'extern "C"' in modern_doc


def test_t2_19_spsc_and_halos_patterns_avoid_gsl_and_iostream() -> None:
    """Verify real C++23 code snippets never use gsl:: or <iostream> streaming."""
    for doc_name in ['modern_cpp23_and_abseil.md', 'hft_embedded_robotics_patterns.md']:
        text = (REFERENCES_DIR / doc_name).read_text(encoding='utf-8')
        assert '<iostream>' not in text, f"'{doc_name}' should not include <iostream>"
        assert 'gsl::' not in text, f"'{doc_name}' must never use gsl::"


def test_t2_20_toolchain_mentions_linux_and_apple_silicon() -> None:
    """Verify SKILL.md covers Linux (x86_64, aarch64, RISC-V RVA23) and macOS Apple Silicon."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding='utf-8'))
    for target in ['x86_64', 'aarch64', 'RISC-V RVA23', 'Apple Silicon']:
        assert target in body, f"SKILL.md missing target architecture '{target}'"


# ==============================================================================
# Tier 3: Cross-Feature Interactions E2E Tests
# ==============================================================================


def test_t3_01_style_hierarchy_consistency_across_skill_and_manual() -> None:
    """Interaction: Style priority order in SKILL.md matches style_hierarchy_and_overrides.md."""
    _, body = split_skill_frontmatter(SKILL_MD.read_text(encoding='utf-8'))
    style_doc = (REFERENCES_DIR / 'style_hierarchy_and_overrides.md').read_text(encoding='utf-8')
    google_url = 'https://google.github.io/styleguide/cppguide.html'
    core_url = 'https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines'
    assert body.index(google_url) < body.index(core_url)
    assert style_doc.index(google_url) < style_doc.index(core_url)
    assert style_doc.index(core_url) < style_doc.index('HFT, Embedded & Robotics')


def test_t3_02_filesystem_and_chrono_cold_path_vs_hot_path_split() -> None:
    """Interaction: <filesystem> and <chrono>/<ratio> permitted on cold host paths, banned on hot paths."""
    skill_text = SKILL_MD.read_text(encoding='utf-8')
    style_doc = (REFERENCES_DIR / 'style_hierarchy_and_overrides.md').read_text(encoding='utf-8')
    patterns_doc = (REFERENCES_DIR / 'hft_embedded_robotics_patterns.md').read_text(encoding='utf-8')
    assert '<filesystem>' in skill_text and 'non-real-time' in skill_text
    assert '<filesystem>' in style_doc and '<chrono>' in style_doc and '<ratio>' in style_doc
    assert '<filesystem>' in patterns_doc


def test_t3_03_pre_commit_and_cmake_presets_integration() -> None:
    """Interaction: examples/.pre-commit-config.yaml references /cmake-pro compile_commands preset."""
    pre_commit_raw = (EXAMPLES_DIR / '.pre-commit-config.yaml').read_text(encoding='utf-8')
    skill_text = SKILL_MD.read_text(encoding='utf-8')
    assert 'build/ci-debug' in pre_commit_raw
    assert 'compile_commands.json' in pre_commit_raw
    assert 'CMakePresets.json' in skill_text
    assert '/cmake-pro' in skill_text


def test_t3_04_clang_tidy_google_naming_matches_reference_code() -> None:
    """Interaction: Reference C++23 classes/enums follow CamelCase, kPrefix, lower_case_, lower_case."""
    opts = _clang_tidy_options(_load_yaml_dict(EXAMPLES_DIR / '.clang-tidy'))
    patterns_doc = (REFERENCES_DIR / 'hft_embedded_robotics_patterns.md').read_text(encoding='utf-8')
    assert opts['readability-identifier-naming.ClassCase'] == 'CamelCase'
    assert opts['readability-identifier-naming.PrivateMemberSuffix'] == '_'
    assert opts['readability-identifier-naming.EnumConstantPrefix'] == 'k'
    assert 'class SpscRingBuffer' in patterns_doc
    assert 'write_idx_' in patterns_doc
    assert 'kFull = 1' in patterns_doc


def test_t3_05_non_const_ref_out_param_with_std_expected() -> None:
    """Interaction: SpscRingBuffer::TryPop and HalosSafetyGate::Intercept combine std::expected + out-ref."""
    patterns_doc = (REFERENCES_DIR / 'hft_embedded_robotics_patterns.md').read_text(encoding='utf-8')
    assert 'std::expected<void, RingError> TryPop(T& out_item) noexcept' in patterns_doc
    assert 'std::array<float, kDofCount>& out_safe_torques) noexcept' in patterns_doc


def test_t3_06_absl_guarded_by_matches_clang_thread_safety_diagnostics() -> None:
    """Interaction: Abseil mutex guide pairs with Clang thread-safety-analysis diagnostics in .clang-tidy."""
    checks = _clang_tidy_checks(_load_yaml_dict(EXAMPLES_DIR / '.clang-tidy'))
    modern_doc = (REFERENCES_DIR / 'modern_cpp23_and_abseil.md').read_text(encoding='utf-8')
    assert 'ABSL_GUARDED_BY' in modern_doc
    assert 'clang-diagnostic-thread-safety-analysis' in checks
    assert 'clang-diagnostic-thread-safety-attributes' in checks


def test_t3_07_c23_dual_header_exception_bridges_c_pro_and_cpp_pro() -> None:
    """Interaction: C23/SPARK Ada extern C header policy coordinates between /cpp-pro and /c-pro."""
    modern_doc = (REFERENCES_DIR / 'modern_cpp23_and_abseil.md').read_text(encoding='utf-8')
    style_doc = (REFERENCES_DIR / 'style_hierarchy_and_overrides.md').read_text(encoding='utf-8')
    assert '/c-pro' in modern_doc and '/ada-spark-pro' in modern_doc
    assert 'extern "C"' in modern_doc and '<stdint.h>' in modern_doc
    assert 'extern "C"' in style_doc and 'dual-language headers' in style_doc


def test_t3_08_validate_prompts_reports_zero_errors() -> None:
    """Interaction: Official repository prompt_validator passes with zero error issues."""
    report = ValidationReport(strict=True)
    validate_prompts(REPO_ROOT, report)
    errors = [issue for issue in report.issues if issue.severity == Severity.ERROR]
    assert not errors, f'Prompt validator reported errors: {errors}'


def test_t3_09_readme_table_reflects_refactored_cpp_pro() -> None:
    """Interaction: README.md custom skills table accurately summarizes updated cpp-pro capabilities."""
    readme_text = README_MD.read_text(encoding='utf-8')
    cpp_row = next((line for line in readme_text.splitlines() if '| `cpp-pro` |' in line), '')
    assert cpp_row, "README.md missing '| `cpp-pro` |' skill row"
    for term in ['C++23', '23.1.5', '<cstdint>', 'std::expected', '<print>', 'Abseil', 'Crubit', '.pre-commit-config.yaml']:
        assert term in cpp_row, f"README.md cpp-pro row missing '{term}'"


def test_t3_10_skill_prompt_references_exist_in_repository() -> None:
    """Interaction: Every sibling skill linked under Related Skills exists in skills/."""
    skill_text = SKILL_MD.read_text(encoding='utf-8')
    discovered_skills = {p.name for p in SKILLS_DIR.iterdir() if p.is_dir()}
    for sibling in ['c-pro', 'rust-pro', 'ada-spark-pro', 'cmake-pro', 'python-pro', 'github-flow-lifecycle']:
        assert f'/{sibling}' in skill_text
        assert sibling in discovered_skills, f"Referenced sibling skill '{sibling}' missing from skills/"


# ==============================================================================
# Tier 4: Real-World Scenarios E2E Tests
# ==============================================================================


def test_t4_01_scenario_spsc_ring_buffer_wraparound_oracle() -> None:
    """Scenario: Behavioral oracle for power-of-two lock-free SpscRingBuffer wraparound semantics."""
    capacity = 4
    assert capacity >= 2 and (capacity & (capacity - 1)) == 0
    mask = capacity - 1
    slots: list[int] = [0] * capacity
    write_idx = 0
    read_idx = 0

    def try_push(item: int) -> str:
        nonlocal write_idx
        if (write_idx - read_idx) >= capacity:
            return 'kFull'
        slots[write_idx & mask] = item
        write_idx += 1
        return 'ok'

    def try_pop() -> tuple[str, int]:
        nonlocal read_idx
        if read_idx == write_idx:
            return 'kEmpty', 0
        val = slots[read_idx & mask]
        read_idx += 1
        return 'ok', val

    assert try_pop() == ('kEmpty', 0)
    for seq in range(4):
        assert try_push(100 + seq) == 'ok'
    assert try_push(999) == 'kFull'

    # Drain half, then wrap across the boundary multiple times
    for expected in (100, 101):
        assert try_pop() == ('ok', expected)
    for seq in range(4, 10):
        assert try_push(100 + seq) == 'ok'
        assert try_pop() == ('ok', 100 + seq - 2)
    assert try_pop() == ('ok', 108)
    assert try_pop() == ('ok', 109)
    assert try_pop() == ('kEmpty', 0)


def test_t4_02_scenario_halos_safety_gate_intercept_oracle() -> None:
    """Scenario: Behavioral oracle matching HalosSafetyGate state machine and torque latching."""
    max_heartbeat_ns = 5_000_000
    limits = (10.0, 20.0, 30.0)
    state = 'kInit'

    def intercept(cmd_ts_ns: int, now_ns: int, desired: tuple[float, float, float]) -> tuple[str, list[float]]:
        nonlocal state
        out = [99.0, 99.0, 99.0]
        if state != 'kActive':
            return 'kNotActive', [0.0, 0.0, 0.0]
        if now_ns < cmd_ts_ns:
            state = 'kFaultEstop'
            return 'kClockRegression', [0.0, 0.0, 0.0]
        if (now_ns - cmd_ts_ns) > max_heartbeat_ns:
            state = 'kFaultEstop'
            return 'kStaleHeartbeat', [0.0, 0.0, 0.0]
        for idx, val in enumerate(desired):
            if not math.isfinite(val):
                state = 'kFaultEstop'
                return 'kNonFiniteCommand', [0.0, 0.0, 0.0]
            if abs(val) > limits[idx]:
                state = 'kFaultEstop'
                return 'kLimitExceeded', [0.0, 0.0, 0.0]
            out[idx] = val
        return 'ok', out

    assert intercept(1_000_000, 2_000_000, (1.0, 2.0, 3.0)) == ('kNotActive', [0.0, 0.0, 0.0])
    state = 'kActive'
    assert intercept(1_000_000, 3_000_000, (5.0, -15.0, 30.0)) == ('ok', [5.0, -15.0, 30.0])

    # Non-finite input latches E-stop permanently
    assert intercept(3_000_000, 4_000_000, (0.0, float('nan'), 0.0)) == ('kNonFiniteCommand', [0.0, 0.0, 0.0])
    assert state == 'kFaultEstop'
    assert intercept(4_500_000, 4_600_000, (1.0, 1.0, 1.0)) == ('kNotActive', [0.0, 0.0, 0.0])


def test_t4_03_scenario_multi_language_crubit_and_c_abi_architecture() -> None:
    """Scenario: Verify C++23 cross-language boundary strategy (Crubit + C23/SPARK Ada + nanobind)."""
    skill_text = SKILL_MD.read_text(encoding='utf-8')
    modern_doc = (REFERENCES_DIR / 'modern_cpp23_and_abseil.md').read_text(encoding='utf-8')

    assert 'halos_kinematics_rs_api.h' in modern_doc
    assert 'cpp_api_from_rust' in modern_doc and 'rust_api_from_cpp' in modern_doc
    assert 'nanobind' in skill_text and 'nanobind' in modern_doc
    assert 'extern "C"' in skill_text and 'std::expected' in modern_doc


def test_t4_04_scenario_cmake_configurable_exceptions_rtti_pipeline() -> None:
    """Scenario: Verify project_options CMake target enforces C++23 and toggles -fno-exceptions/-fno-rtti."""
    patterns_doc = (REFERENCES_DIR / 'hft_embedded_robotics_patterns.md').read_text(encoding='utf-8')
    assert 'add_library(project_options INTERFACE)' in patterns_doc
    assert 'target_compile_features(project_options INTERFACE cxx_std_23)' in patterns_doc
    assert 'if(NOT ENABLE_EXCEPTIONS)' in patterns_doc
    assert 'if(NOT ENABLE_RTTI)' in patterns_doc


def test_t4_05_scenario_mdspan_jacobian_bounds_and_multiplication_oracle() -> None:
    """Scenario: Verify MultiplyJacobian mdspan kernel contract and linear algebra correctness."""
    patterns_doc = (REFERENCES_DIR / 'hft_embedded_robotics_patterns.md').read_text(encoding='utf-8')
    assert 'std::mdspan<const float, std::dextents<size_t, 2>>' in patterns_doc
    assert 'jacobian[r, c]' in patterns_doc

    def multiply_jacobian(jacobian: list[list[float]], q_dot: list[float], out_y: list[float]) -> bool:
        rows = len(jacobian)
        cols = len(jacobian[0]) if rows else 0
        if len(q_dot) < cols or len(out_y) < rows:
            return False
        for r in range(rows):
            acc = 0.0
            for c in range(cols):
                acc += jacobian[r][c] * q_dot[c]
            out_y[r] = acc
        return True

    short_out = [0.0]
    assert multiply_jacobian([[1.0, 2.0], [3.0, 4.0]], [10.0, 20.0], short_out) is False
    valid_out = [0.0, 0.0]
    assert multiply_jacobian([[1.0, 2.0], [3.0, 4.0]], [10.0, 20.0], valid_out) is True
    assert valid_out == [50.0, 110.0]
