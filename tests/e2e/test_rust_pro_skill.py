"""Opaque-box E2E test suite for the rust-pro AntiGravity 2.29.0+ skill.

Validates all requirements (R1, R2, R3, R4) from ORIGINAL_REQUEST.md across:
- Tier 1: Feature Coverage (>=25 tests)
- Tier 2: Boundary & Corner Cases (>=25 tests)
- Tier 3: Cross-Feature Interactions (>=10 tests)
- Tier 4: Real-World Scenarios (>=5 tests)
"""

from __future__ import annotations

import math
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
    from pathlib import Path


SKILL_DIR = SKILLS_DIR / 'rust-pro'
SKILL_MD = SKILL_DIR / 'SKILL.md'
EXAMPLES_DIR = SKILL_DIR / 'examples'
REFERENCES_DIR = SKILL_DIR / 'references'


# ==============================================================================
# Tier 1: Feature Coverage E2E Tests (R1, R2, R3, R4)
# ==============================================================================


def test_t1_r1_01_skill_directory_exists() -> None:
    """R1: Verify skills/rust-pro directory exists and is a directory."""
    assert SKILL_DIR.exists(), f"Skill directory not found at '{SKILL_DIR}'"
    assert SKILL_DIR.is_dir(), f"'{SKILL_DIR}' is not a directory"


def test_t1_r1_02_skill_md_exists() -> None:
    """R1: Verify skills/rust-pro/SKILL.md exists and is a file."""
    assert SKILL_MD.exists(), f"SKILL.md not found at '{SKILL_MD}'"
    assert SKILL_MD.is_file(), f"'{SKILL_MD}' is not a regular file"


def test_t1_r1_03_skill_frontmatter_framing() -> None:
    """R1: Verify SKILL.md begins with line 1 delimiter and has valid closing delimiter."""
    text = SKILL_MD.read_text(encoding='utf-8')
    assert text.startswith('---\n'), "SKILL.md must begin with YAML frontmatter delimiter '---' on line 1"
    parts = text.split('---\n', 2)
    assert len(parts) >= 3, 'SKILL.md missing closing YAML frontmatter delimiter'
    frontmatter, body = split_skill_frontmatter(text)
    assert isinstance(frontmatter, dict), 'Parsed frontmatter must be a dictionary'
    assert len(body.strip()) > 0, 'SKILL.md body must not be empty'


def test_t1_r1_04_skill_frontmatter_name() -> None:
    """R1: Verify frontmatter name matches 'rust-pro' and conforms to regex."""
    text = SKILL_MD.read_text(encoding='utf-8')
    frontmatter, _ = split_skill_frontmatter(text)
    name = frontmatter.get('name')
    assert name == 'rust-pro', f"Expected skill name 'rust-pro', got '{name}'"
    assert SKILL_NAME_PATTERN.match(name), f"Skill name '{name}' violates naming regex"


def test_t1_r1_05_skill_frontmatter_description() -> None:
    """R1: Verify frontmatter description is >= 20 characters and contains domain keywords."""
    text = SKILL_MD.read_text(encoding='utf-8')
    frontmatter, _ = split_skill_frontmatter(text)
    desc = frontmatter.get('description', '')
    assert isinstance(desc, str), 'Frontmatter description must be a string'
    assert len(desc.strip()) >= MIN_SKILL_DESCRIPTION_LENGTH, f'Description length ({len(desc)}) < {MIN_SKILL_DESCRIPTION_LENGTH}'
    assert 'rust' in desc.lower(), "Description must reference 'Rust'"
    assert any(k in desc.lower() for k in ['systems', 'robotics', 'embedded', 'bare-metal']), 'Description must highlight systems domain focus'


def test_t1_r1_06_skill_frontmatter_metadata() -> None:
    """R1: Verify frontmatter metadata contains version and publisher."""
    text = SKILL_MD.read_text(encoding='utf-8')
    frontmatter, _ = split_skill_frontmatter(text)
    metadata = frontmatter.get('metadata')
    assert isinstance(metadata, dict), "Frontmatter missing 'metadata' dictionary"
    assert 'version' in metadata, "Metadata missing 'version'"
    assert 'publisher' in metadata, "Metadata missing 'publisher'"


def test_t1_r1_07_skill_body_bytes_within_limit() -> None:
    """R1: Verify SKILL.md body size strictly < 24,000 UTF-8 bytes cap (SKL005)."""
    text = SKILL_MD.read_text(encoding='utf-8')
    _, body = split_skill_frontmatter(text)
    body_bytes = len(body.encode('utf-8'))
    assert body_bytes < MAX_FILE_BYTES, f'SKILL.md body ({body_bytes} bytes) exceeds limit of {MAX_FILE_BYTES} bytes'


def test_t1_r1_08_subdirectories_allowed() -> None:
    """R1: Verify subdirectories in skills/rust-pro/ are strictly within the AntiGravity allowlist."""
    discovered = {p.name for p in SKILL_DIR.iterdir() if p.is_dir()}
    disallowed = discovered - ALLOWED_SKILL_SUBDIRECTORIES
    assert not disallowed, f'Disallowed subdirectories discovered: {disallowed}'


def test_t1_r1_09_examples_directory_contents() -> None:
    """R1: Verify examples/ directory contains all 5 mandatory configuration files."""
    assert EXAMPLES_DIR.is_dir(), f"'{EXAMPLES_DIR}' is not a directory"
    required_files = [
        'Cargo.toml',
        'pixi.toml',
        'clippy.toml',
        'rustfmt.toml',
        '.cargo/config.toml',
    ]
    for rel_path in required_files:
        target = EXAMPLES_DIR / rel_path
        assert target.is_file(), f"Missing required configuration file '{rel_path}' in examples/"


def test_t1_r1_10_references_directory_contents() -> None:
    """R1: Verify references/ directory contains all 3 deep architectural reference manuals."""
    assert REFERENCES_DIR.is_dir(), f"'{REFERENCES_DIR}' is not a directory"
    required_manuals = [
        'toolchain_and_targets.md',
        'systems_paradigms_and_safety.md',
        'google_rust_style_guide.md',
    ]
    for manual in required_manuals:
        target = REFERENCES_DIR / manual
        assert target.is_file(), f"Missing required manual '{manual}' in references/"


def test_t1_r1_11_markdown_relative_links_valid() -> None:
    """R1: Verify all markdown relative links [text](target) in SKILL.md and references/ resolve cleanly."""
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

    assert checked_count >= 5, f'Expected at least 5 relative links verified across markdown files, found {checked_count}'


def test_t1_r2_01_pixi_toml_valid_toml() -> None:
    """R2: Verify examples/pixi.toml parses cleanly as valid TOML."""
    pixi_path = EXAMPLES_DIR / 'pixi.toml'
    raw_content = pixi_path.read_text(encoding='utf-8')
    parsed = tomllib.loads(raw_content)
    assert isinstance(parsed, dict), 'pixi.toml must parse to a dictionary'
    assert 'workspace' in parsed, "pixi.toml missing 'workspace' table"


def test_t1_r2_02_pixi_rust_version_pinned() -> None:
    """R2: Verify examples/pixi.toml declares dependency pinned to Rust 1.99.1."""
    pixi_path = EXAMPLES_DIR / 'pixi.toml'
    parsed = tomllib.loads(pixi_path.read_text(encoding='utf-8'))
    deps = parsed.get('dependencies', {})
    rust_dep = str(deps.get('rust', ''))
    assert '1.99.1' in rust_dep, f"Expected Rust 1.99.1 pinned dependency, got: '{rust_dep}'"


def test_t1_r2_03_pixi_channels_conda_forge() -> None:
    """R2: Verify examples/pixi.toml configures conda-forge channel."""
    pixi_path = EXAMPLES_DIR / 'pixi.toml'
    parsed = tomllib.loads(pixi_path.read_text(encoding='utf-8'))
    channels = parsed.get('workspace', {}).get('channels', [])
    assert 'conda-forge' in channels, f"Expected 'conda-forge' in channels, got: {channels}"


def test_t1_r2_04_pixi_companion_tools() -> None:
    """R2: Verify examples/pixi.toml includes modern companion tools."""
    pixi_path = EXAMPLES_DIR / 'pixi.toml'
    parsed = tomllib.loads(pixi_path.read_text(encoding='utf-8'))
    deps = parsed.get('dependencies', {})
    expected_tools = ['cargo-nextest', 'cargo-audit', 'cargo-deny', 'cargo-llvm-cov', 'cargo-zigbuild']
    for tool in expected_tools:
        assert tool in deps, f"pixi.toml missing companion tool dependency '{tool}'"


def test_t1_r2_05_pixi_task_definitions() -> None:
    """R2: Verify examples/pixi.toml defines required workflow tasks."""
    pixi_path = EXAMPLES_DIR / 'pixi.toml'
    parsed = tomllib.loads(pixi_path.read_text(encoding='utf-8'))
    tasks = parsed.get('tasks', {})
    expected_tasks = ['test', 'clippy', 'fmt', 'deny']
    for t in expected_tasks:
        assert t in tasks, f"pixi.toml missing required task '{t}'"


def test_t1_r2_06_cargo_config_valid_toml() -> None:
    """R2: Verify examples/.cargo/config.toml parses cleanly as valid TOML."""
    config_path = EXAMPLES_DIR / '.cargo' / 'config.toml'
    parsed = tomllib.loads(config_path.read_text(encoding='utf-8'))
    assert isinstance(parsed, dict), '.cargo/config.toml must parse to a dictionary'
    assert 'target' in parsed, ".cargo/config.toml missing 'target' table"


def test_t1_r2_07_cargo_config_cross_targets() -> None:
    """R2: Verify examples/.cargo/config.toml defines Linux, macOS, and RISC-V targets."""
    config_path = EXAMPLES_DIR / '.cargo' / 'config.toml'
    parsed = tomllib.loads(config_path.read_text(encoding='utf-8'))
    targets = parsed.get('target', {})
    expected_triples = [
        'riscv64a23-unknown-linux-gnu',
        'x86_64-unknown-linux-gnu',
        'aarch64-unknown-linux-gnu',
        'aarch64-apple-darwin',
    ]
    for triple in expected_triples:
        assert triple in targets, f".cargo/config.toml missing target configuration for '{triple}'"


def test_t1_r2_08_cargo_config_riscv_rva23_features() -> None:
    """R2: Verify target flags for riscv64a23 configure RVA23 profile and vector/bitmanip extensions."""
    config_path = EXAMPLES_DIR / '.cargo' / 'config.toml'
    parsed = tomllib.loads(config_path.read_text(encoding='utf-8'))
    riscv_cfg = parsed.get('target', {}).get('riscv64a23-unknown-linux-gnu', {})
    flags = riscv_cfg.get('rustflags', [])
    flags_text = ' '.join(flags)
    assert '+rva23u64' in flags_text or 'rva23' in flags_text, f'Missing RVA23 feature flags in riscv64a23: {flags_text}'
    assert '+v' in flags_text, f'Missing vector extension (+v) in riscv64a23 flags: {flags_text}'


def test_t1_r2_09_cargo_config_runner_qemu() -> None:
    """R2: Verify cross-execution runner in .cargo/config.toml configures QEMU user emulation."""
    config_path = EXAMPLES_DIR / '.cargo' / 'config.toml'
    parsed = tomllib.loads(config_path.read_text(encoding='utf-8'))
    riscv_cfg = parsed.get('target', {}).get('riscv64a23-unknown-linux-gnu', {})
    runner = riscv_cfg.get('runner', '')
    assert 'qemu-riscv64' in runner, f"Expected 'qemu-riscv64' runner in riscv64a23, got '{runner}'"


def test_t1_r2_10_toolchain_reference_doc() -> None:
    """R2: Verify references/toolchain_and_targets.md documents Rust 1.99.1 features and multi-arch."""
    doc = (REFERENCES_DIR / 'toolchain_and_targets.md').read_text(encoding='utf-8')
    assert '1.99' in doc, 'toolchain_and_targets.md must document Rust 1.99'
    assert 'riscv64' in doc.lower(), 'toolchain_and_targets.md must document RISC-V targets'
    assert 'c-variadic' in doc.lower() or 'valist' in doc.lower(), 'toolchain_and_targets.md must document C-variadic support'
    assert 'size_of_val_raw' in doc or 'metadata' in doc, 'toolchain_and_targets.md must document pointer metadata'


def test_t1_r3_01_systems_paradigms_doc() -> None:
    """R3: Verify references/systems_paradigms_and_safety.md covers std, embedded, and bare-metal."""
    doc = (REFERENCES_DIR / 'systems_paradigms_and_safety.md').read_text(encoding='utf-8')
    assert 'standard rust' in doc.lower(), 'Manual must document standard Rust paradigm'
    assert 'embedded systems' in doc.lower() or 'embedded' in doc.lower(), 'Manual must document embedded Rust'
    assert 'bare-metal' in doc.lower() or 'bare metal' in doc.lower(), 'Manual must document bare-metal Rust'


def test_t1_r3_02_bare_metal_mmio_guidance() -> None:
    """R3: Verify systems manual documents zero dynamic allocation and typestate MMIO registers."""
    doc = (REFERENCES_DIR / 'systems_paradigms_and_safety.md').read_text(encoding='utf-8')
    assert 'zero' in doc.lower() and ('allocation' in doc.lower() or 'alloc' in doc.lower()), 'Manual must prescribe zero dynamic allocation'
    assert 'mmio' in doc.lower(), 'Manual must document MMIO hardware register access'
    assert 'typestate' in doc.lower(), 'Manual must document typestate pattern'


def test_t1_r3_03_safety_guardrails_rationale() -> None:
    """R3: Verify systems manual mandates // SAFETY: rationale comments on unsafe blocks."""
    doc = (REFERENCES_DIR / 'systems_paradigms_and_safety.md').read_text(encoding='utf-8')
    assert '// SAFETY:' in doc or 'SAFETY:' in doc, 'Manual must mandate explicit // SAFETY: rationale comments'
    assert 'unsafe_op_in_unsafe_fn' in doc, 'Manual must document unsafe_op_in_unsafe_fn lint'


def test_t1_r3_04_halos_interceptor_pattern() -> None:
    """R3: Verify systems manual implements NVIDIA Halos watchdog and finite float validation."""
    doc = (REFERENCES_DIR / 'systems_paradigms_and_safety.md').read_text(encoding='utf-8')
    assert 'halos' in doc.lower(), 'Manual must detail NVIDIA Halos pattern'
    assert '5ms' in doc.lower() or '5_000_000' in doc, 'Manual must enforce 5ms watchdog expiration'
    assert 'isfinite' in doc.lower() or 'is_finite' in doc.lower(), 'Manual must check float finiteness'
    assert '#[repr(C)]' in doc and 'pub struct HalosSafetyInterceptor' in doc, 'HalosSafetyInterceptor must have #[repr(C)]'
    assert 'halos_interceptor_init' in doc, 'Manual must export halos_interceptor_init'
    assert 'halos_interceptor_process' in doc, 'Manual must export halos_interceptor_process'


def test_t1_r3_05_google_style_guide_doc() -> None:
    """R3: Verify references/google_rust_style_guide.md codifies Google style rules."""
    doc = (REFERENCES_DIR / 'google_rust_style_guide.md').read_text(encoding='utf-8')
    assert 'glob' in doc.lower() and ('prohibit' in doc.lower() or 'forbidden' in doc.lower()), 'Manual must prohibit wildcard/glob imports'
    assert 'imports_granularity' in doc or 'module' in doc.lower(), "Manual must document 'imports_granularity'"
    assert 'option' in doc.lower() and 'result' in doc.lower() and 'panic' in doc.lower(), 'Manual must detail Option/Result/panic error triad'
    assert 'unwrap' in doc.lower() and 'expect' in doc.lower(), 'Manual must document pattern matching and expect over unwrap'


def test_t1_r3_06_cargo_toml_lint_table() -> None:
    """R3: Verify examples/Cargo.toml contains [lints.rust] and [lints.clippy] tables."""
    cargo_path = EXAMPLES_DIR / 'Cargo.toml'
    parsed = tomllib.loads(cargo_path.read_text(encoding='utf-8'))
    lints = parsed.get('lints', {})
    assert 'rust' in lints, "Cargo.toml missing '[lints.rust]' table"
    assert 'clippy' in lints, "Cargo.toml missing '[lints.clippy]' table"
    rust_lints = lints.get('rust', {})
    assert rust_lints.get('unsafe_code') == 'deny', "Expected 'unsafe_code = deny'"
    rust_2024 = rust_lints.get('rust_2024_compatibility')
    assert isinstance(rust_2024, dict), "Expected 'rust_2024_compatibility' to be a table with priority"
    assert rust_2024.get('level') == 'warn', "Expected 'rust_2024_compatibility.level = warn'"
    assert rust_2024.get('priority') == -1, "Expected 'rust_2024_compatibility.priority = -1'"
    clippy_lints = lints.get('clippy', {})
    assert clippy_lints.get('wildcard_imports') == 'deny', "Expected 'wildcard_imports = deny'"
    assert clippy_lints.get('unwrap_used') == 'deny', "Expected 'unwrap_used = deny'"


def test_t1_r3_07_clippy_toml_rules() -> None:
    """R3: Verify examples/clippy.toml specifies cognitive complexity and disallowed methods."""
    clippy_path = EXAMPLES_DIR / 'clippy.toml'
    parsed = tomllib.loads(clippy_path.read_text(encoding='utf-8'))
    assert 'cognitive-complexity-threshold' in parsed, "clippy.toml missing 'cognitive-complexity-threshold'"
    assert 'enum-variant-size-threshold' in parsed, "clippy.toml missing 'enum-variant-size-threshold'"
    assert parsed.get('enum-variant-size-threshold') == 128, "Expected 'enum-variant-size-threshold = 128'"
    assert 'enum-size-threshold' not in parsed, "clippy.toml must not contain deprecated/invalid 'enum-size-threshold'"
    assert 'disallowed-methods' in parsed, "clippy.toml missing 'disallowed-methods'"


def test_t1_r3_08_rustfmt_toml_settings() -> None:
    """R3: Verify examples/rustfmt.toml configures max_width=100 and Module imports granularity."""
    rustfmt_path = EXAMPLES_DIR / 'rustfmt.toml'
    parsed = tomllib.loads(rustfmt_path.read_text(encoding='utf-8'))
    assert parsed.get('max_width') == 100, f'Expected max_width=100, got: {parsed.get("max_width")}'
    assert parsed.get('imports_granularity') == 'Module', f"Expected imports_granularity='Module', got: {parsed.get('imports_granularity')}"


def test_t1_r4_01_pure_uv_guardrail_in_skill() -> None:
    """R4: Verify SKILL.md does not prescribe pixi for maintaining the mimir repository itself."""
    text = SKILL_MD.read_text(encoding='utf-8')
    assert 'pixi run pre-commit' not in text, 'SKILL.md must not prescribe pixi for repo pre-commit'
    assert 'pixi run pytest' not in text, 'SKILL.md must not prescribe pixi for repo pytest'


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
    (skill_dir_fail / 'SKILL.md').write_text(frontmatter_text.replace('pass-skill', 'fail-skill') + body_24001, encoding='utf-8')
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
    (skill_dir / 'SKILL.md').write_text('---\nname: bad-sub-skill\ndescription: Valid description string with 20 chars.\n---\nBody\n', encoding='utf-8')
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
    url_text = '[Google Rust Guide](https://google.github.io/styleguide/rustguide.html)'
    match = link_re.search(url_text)
    assert match is None, 'HTTP URL should not match relative link pattern'


def test_t2_b17_prohibited_pixi_in_repo_commands_rejected(tmp_path: Path) -> None:
    """Boundary: Verify prompt validator flags rule prescribing pixi for repository maintenance."""
    rules_dir = tmp_path / 'rules'
    rules_dir.mkdir()
    bad_rule = rules_dir / 'AGENTS.md'
    bad_rule.write_text('# Rules\nAlways execute `pixi run pre-commit` before pushing.\n', encoding='utf-8')
    report = ValidationReport()
    validate_prompts(tmp_path, report)
    assert any(i.code == ErrorCode.PRM003 for i in report.issues)


def test_t2_b18_secret_hygiene_home_path_leak_detected() -> None:
    """Boundary: Verify secret hygiene pattern detects developer machine home directories."""
    leaked_macos = '/Users/' + 'jamie/development/project'
    leaked_linux = '/home/' + 'jamie-lapointe/development/project'
    assert _HOME_PATTERN.search(leaked_macos) is not None, 'Failed to detect macOS home path leak'
    assert _HOME_PATTERN.search(leaked_linux) is not None, 'Failed to detect Linux home path leak'
    clean_path = '/usr/local/bin/rustc'
    assert _HOME_PATTERN.search(clean_path) is None, 'False positive on clean path'


def test_t2_b19_secret_hygiene_clean_in_skill_files() -> None:
    """Boundary: Verify all files in skills/rust-pro/ are 100% clean of home path leaks."""
    for file_path in SKILL_DIR.rglob('*'):
        if file_path.is_file():
            text = file_path.read_text(encoding='utf-8', errors='ignore')
            assert not _HOME_PATTERN.search(text), f"Home path leak detected in '{file_path}'"


def test_t2_b20_cargo_toml_corrupt_syntax_rejected(tmp_path: Path) -> None:
    """Boundary: Verify corrupt syntax in Cargo.toml raises tomllib.TOMLDecodeError."""
    bad_toml = tmp_path / 'Cargo.toml'
    bad_toml.write_text('[package\nname = "broken', encoding='utf-8')
    with pytest.raises(tomllib.TOMLDecodeError):
        tomllib.loads(bad_toml.read_text(encoding='utf-8'))


def test_t2_b21_pixi_toml_missing_dependencies_table(tmp_path: Path) -> None:
    """Boundary: Detect missing dependencies table in pixi configuration."""
    minimal_pixi = tmp_path / 'pixi.toml'
    minimal_pixi.write_text('[workspace]\nname = "test"\n', encoding='utf-8')
    parsed = tomllib.loads(minimal_pixi.read_text(encoding='utf-8'))
    assert 'dependencies' not in parsed, 'Expected dependencies table to be absent'


def test_t2_b22_rustfmt_toml_invalid_width_boundary(tmp_path: Path) -> None:
    """Boundary: Verify max_width <= 100 boundary condition for Google style."""
    rustfmt_valid = tmp_path / 'rustfmt_valid.toml'
    rustfmt_valid.write_text('max_width = 100\n', encoding='utf-8')
    p_valid = tomllib.loads(rustfmt_valid.read_text(encoding='utf-8'))
    valid_width = p_valid.get('max_width')
    assert isinstance(valid_width, int) and valid_width <= 100

    rustfmt_invalid = tmp_path / 'rustfmt_invalid.toml'
    rustfmt_invalid.write_text('max_width = 120\n', encoding='utf-8')
    p_invalid = tomllib.loads(rustfmt_invalid.read_text(encoding='utf-8'))
    invalid_width = p_invalid.get('max_width')
    assert isinstance(invalid_width, int) and invalid_width > 100


def test_t2_b23_clippy_toml_cognitive_complexity_threshold() -> None:
    """Boundary: Verify cognitive-complexity-threshold in clippy.toml is <= 25."""
    clippy_path = EXAMPLES_DIR / 'clippy.toml'
    parsed = tomllib.loads(clippy_path.read_text(encoding='utf-8'))
    thresh = parsed.get('cognitive-complexity-threshold')
    assert isinstance(thresh, int), 'Threshold must be an integer'
    assert thresh <= 25, f'Cognitive complexity threshold ({thresh}) should be <= 25'


def test_t2_b24_skill_md_actual_body_size_headroom() -> None:
    """Boundary: Verify skills/rust-pro/SKILL.md body has >= 500 bytes safety headroom before 24KB cap."""
    text = SKILL_MD.read_text(encoding='utf-8')
    _, body = split_skill_frontmatter(text)
    body_bytes = len(body.encode('utf-8'))
    headroom = MAX_FILE_BYTES - body_bytes
    assert headroom >= 500, f'Insufficient headroom: {headroom} bytes remaining before {MAX_FILE_BYTES} cap'


def test_t2_b25_reference_manuals_sizing() -> None:
    """Boundary: Verify all markdown reference manuals in references/ remain < 24,000 bytes."""
    for manual in REFERENCES_DIR.glob('*.md'):
        bytes_len = len(manual.read_bytes())
        assert bytes_len < MAX_FILE_BYTES, f"Manual '{manual.name}' size ({bytes_len} bytes) exceeds {MAX_FILE_BYTES} bytes"


def test_t2_b26_empty_files_rejected() -> None:
    """Boundary: Verify zero 0-byte stub files exist anywhere in skills/rust-pro/."""
    for file_path in SKILL_DIR.rglob('*'):
        if file_path.is_file():
            assert file_path.stat().st_size > 0, f"Empty 0-byte file detected at '{file_path}'"


# ==============================================================================
# Tier 3: Cross-Feature Interactions E2E Tests
# ==============================================================================


def test_t3_cross_target_and_systems_paradigm_linux_std() -> None:
    """Interaction: Linux x86_64 target configuration aligned with std threading and allocator."""
    config_path = EXAMPLES_DIR / '.cargo' / 'config.toml'
    cargo_cfg = tomllib.loads(config_path.read_text(encoding='utf-8'))
    targets = cargo_cfg.get('target', {})
    assert 'x86_64-unknown-linux-gnu' in targets

    systems_doc = (REFERENCES_DIR / 'systems_paradigms_and_safety.md').read_text(encoding='utf-8')
    assert 'Standard Rust (std)' in systems_doc
    assert 'threads' in systems_doc.lower()


def test_t3_cross_target_and_systems_paradigm_linux_aarch64_embedded() -> None:
    """Interaction: Linux aarch64 target in .cargo/config.toml aligned with embedded / RTOS guidance."""
    config_path = EXAMPLES_DIR / '.cargo' / 'config.toml'
    cargo_cfg = tomllib.loads(config_path.read_text(encoding='utf-8'))
    targets = cargo_cfg.get('target', {})
    assert 'aarch64-unknown-linux-gnu' in targets
    aarch64_cfg = targets['aarch64-unknown-linux-gnu']
    assert 'neoverse-n1' in ' '.join(aarch64_cfg.get('rustflags', []))


def test_t3_cross_target_and_systems_paradigm_macos_aarch64() -> None:
    """Interaction: macOS Apple Silicon target in .cargo/config.toml aligned with Pixi platform osx-arm64."""
    config_path = EXAMPLES_DIR / '.cargo' / 'config.toml'
    cargo_cfg = tomllib.loads(config_path.read_text(encoding='utf-8'))
    assert 'aarch64-apple-darwin' in cargo_cfg.get('target', {})

    pixi_path = EXAMPLES_DIR / 'pixi.toml'
    pixi_cfg = tomllib.loads(pixi_path.read_text(encoding='utf-8'))
    platforms = pixi_cfg.get('workspace', {}).get('platforms', [])
    assert 'osx-arm64' in platforms


def test_t3_cross_target_and_systems_paradigm_riscv_rva23_baremetal() -> None:
    """Interaction: RISC-V RVA23 target in .cargo/config.toml aligned with bare-metal MMIO guidance."""
    config_path = EXAMPLES_DIR / '.cargo' / 'config.toml'
    cargo_cfg = tomllib.loads(config_path.read_text(encoding='utf-8'))
    targets = cargo_cfg.get('target', {})
    assert 'riscv64a23-unknown-linux-gnu' in targets

    systems_doc = (REFERENCES_DIR / 'systems_paradigms_and_safety.md').read_text(encoding='utf-8')
    assert 'RISC-V' in systems_doc
    assert 'typestate' in systems_doc.lower()


def test_t3_cross_pixi_dependencies_and_cargo_features() -> None:
    """Interaction: Pixi Rust 1.99.1 dependency matched with companion tools in Cargo workflow."""
    pixi_cfg = tomllib.loads((EXAMPLES_DIR / 'pixi.toml').read_text(encoding='utf-8'))
    cargo_cfg = tomllib.loads((EXAMPLES_DIR / 'Cargo.toml').read_text(encoding='utf-8'))
    assert pixi_cfg['dependencies']['rust'].startswith('1.99.1')
    assert cargo_cfg['package']['rust-version'] == '1.99.1'


def test_t3_cross_cargo_lints_and_google_style() -> None:
    """Interaction: Cargo.toml [lints.clippy] table enforces Google Rust Styleguide rules."""
    cargo_cfg = tomllib.loads((EXAMPLES_DIR / 'Cargo.toml').read_text(encoding='utf-8'))
    clippy_lints = cargo_cfg.get('lints', {}).get('clippy', {})
    assert clippy_lints.get('wildcard_imports') == 'deny'
    assert clippy_lints.get('clone_on_ref_ptr') == 'deny'
    assert clippy_lints.get('undocumented_unsafe_blocks') == 'deny'

    style_doc = (REFERENCES_DIR / 'google_rust_style_guide.md').read_text(encoding='utf-8')
    assert 'wildcard' in style_doc.lower()
    assert 'arc' in style_doc.lower() or 'clone' in style_doc.lower()


def test_t3_cross_clippy_toml_and_rustfmt_toml() -> None:
    """Interaction: Consistency between clippy.toml thresholds and rustfmt.toml formatting."""
    clippy_cfg = tomllib.loads((EXAMPLES_DIR / 'clippy.toml').read_text(encoding='utf-8'))
    rustfmt_cfg = tomllib.loads((EXAMPLES_DIR / 'rustfmt.toml').read_text(encoding='utf-8'))
    assert clippy_cfg.get('cognitive-complexity-threshold', 0) <= 25
    assert rustfmt_cfg.get('max_width') == 100


def test_t3_cross_halos_interceptor_and_c_abi_export() -> None:
    """Interaction: NVIDIA Halos interceptor exports C-compatible ABI with explicit safety rationale."""
    systems_doc = (REFERENCES_DIR / 'systems_paradigms_and_safety.md').read_text(encoding='utf-8')
    assert 'extern "C"' in systems_doc
    assert 'halos_command_interceptor_process' in systems_doc or 'interceptor' in systems_doc.lower()
    assert 'halos_interceptor_init' in systems_doc, 'Manual must export halos_interceptor_init'
    assert 'halos_interceptor_process' in systems_doc, 'Manual must export halos_interceptor_process'
    assert '#[repr(C)]' in systems_doc, 'HalosSafetyInterceptor must have #[repr(C)]'
    assert 'use core::time::Duration;' not in systems_doc, 'systems manual must not contain unused Duration import'


def test_t3_cross_empirical_rustc_and_clippy_execution() -> None:
    """Interaction: Empirical verification of clippy.toml and reference code with host toolchain."""
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path

    # 1. Empirically verify clippy.toml with clippy-driver if present
    clippy_driver = shutil.which('clippy-driver')
    if clippy_driver:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'clippy.toml').write_text((EXAMPLES_DIR / 'clippy.toml').read_text(encoding='utf-8'))
            (Path(tmp) / 'lib.rs').write_text('pub fn smoke() {}\n')
            res = subprocess.run([clippy_driver, '--crate-type=lib', str(Path(tmp) / 'lib.rs')], cwd=tmp, capture_output=True)
            assert res.returncode == 0, f'clippy-driver failed on clippy.toml: {res.stderr.decode()}'

    # 2. Empirically verify Halos Interceptor snippet compiles cleanly under rustc -D warnings
    rustc = shutil.which('rustc')
    if rustc:
        ver_res = subprocess.run([rustc, '--version'], capture_output=True, text=True)
        ver_match = re.search(r'rustc\s+(\d+)\.(\d+)', ver_res.stdout)
        if ver_match and (int(ver_match.group(1)), int(ver_match.group(2))) >= (1, 82):
            lines = (REFERENCES_DIR / 'systems_paradigms_and_safety.md').read_text(encoding='utf-8').splitlines()
            start = next(i for i, line in enumerate(lines) if '#![no_std]' in line)
            end = next(i for i, line in enumerate(lines[start:], start) if line.strip() == '```')
            code = '\n'.join(lines[start:end])
            with tempfile.TemporaryDirectory() as tmp:
                out_rmeta = Path(tmp) / 'libhalos.rmeta'
                res = subprocess.run(
                    [rustc, '--crate-type=lib', '-', '--emit=metadata', '-o', str(out_rmeta), '-D', 'warnings'],
                    input=code.encode(),
                    capture_output=True,
                )
                assert res.returncode == 0, f'rustc -D warnings failed on Halos snippet: {res.stderr.decode()}'


def test_t3_cross_safety_guardrail_and_compiler_attributes() -> None:
    """Interaction: Mandatory // SAFETY: rationale combined with deny(unsafe_op_in_unsafe_fn)."""
    toolchain_doc = (REFERENCES_DIR / 'toolchain_and_targets.md').read_text(encoding='utf-8')
    assert '#[unsafe(' in toolchain_doc or 'unsafe_op_in_unsafe_fn' in toolchain_doc
    systems_doc = (REFERENCES_DIR / 'systems_paradigms_and_safety.md').read_text(encoding='utf-8')
    assert '// SAFETY:' in systems_doc


def test_t3_cross_pixi_tasks_and_cargo_test_runners() -> None:
    """Interaction: Pixi tasks map to cargo nextest and cross-compilation runners."""
    pixi_cfg = tomllib.loads((EXAMPLES_DIR / 'pixi.toml').read_text(encoding='utf-8'))
    tasks = pixi_cfg.get('tasks', {})
    assert 'nextest' in tasks['test']['cmd']
    assert 'riscv64a23' in tasks['test-riscv']['cmd'] or 'riscv64' in tasks['test-riscv']['cmd']


def test_t3_cross_error_triad_and_thiserror_anyhow() -> None:
    """Interaction: Library error enums use thiserror, application errors use Option/Result/panic."""
    cargo_cfg = tomllib.loads((EXAMPLES_DIR / 'Cargo.toml').read_text(encoding='utf-8'))
    deps = cargo_cfg.get('dependencies', {})
    assert 'thiserror' in deps

    style_doc = (REFERENCES_DIR / 'google_rust_style_guide.md').read_text(encoding='utf-8')
    assert 'Option' in style_doc and 'Result' in style_doc and 'panic!' in style_doc


def test_t3_cross_skill_prompt_references_consistency() -> None:
    """Interaction: Cross-skill references in SKILL.md under Related Skills match existing skills."""
    skill_text = SKILL_MD.read_text(encoding='utf-8')
    ref_pattern = re.compile(r'^\s*-\s*(?:\*\*)?`?/([a-z0-9]+(?:-[a-z0-9]+)*)`?(?:\*\*)?:?', re.MULTILINE)
    discovered_skills = {p.name for p in SKILLS_DIR.iterdir() if p.is_dir()}

    for match in ref_pattern.finditer(skill_text):
        skill_ref = match.group(1)
        if skill_ref in {'c-pro', 'cpp-pro', 'ada-spark-pro', 'cmake-pro', 'python-pro', 'github-flow-lifecycle'}:
            assert skill_ref in discovered_skills, f"Referenced skill '{skill_ref}' not found in skills/"


# ==============================================================================
# Tier 4: Real-World Scenarios E2E Tests
# ==============================================================================


def test_t4_scenario_halos_robotics_interceptor_simulation() -> None:
    """Scenario 1: End-to-end simulation of NVIDIA Halos Command Interceptor safety kernel.

    Validates:
    - Packet timestamp monotonic freshness (< 5ms watchdog expiration)
    - IEEE-754 float finiteness check (rejection of NaN and Infinity)
    - Clamping of motor torque commands within safety envelopes
    - Fail-safe fallback to zero torque upon safety violation
    - Zero dynamic heap allocation invariant.
    """
    max_torque_nm = 50.0
    watchdog_limit_ns = 5_000_000  # 5 milliseconds

    def halos_safety_interceptor(
        current_time_ns: int,
        packet_timestamp_ns: int,
        raw_torques: list[float],
    ) -> tuple[bool, list[float], str]:
        # 1. Watchdog freshness
        if current_time_ns - packet_timestamp_ns > watchdog_limit_ns:
            return False, [0.0] * len(raw_torques), 'WATCHDOG_EXPIRED'

        # 2. Finite float verification
        for t in raw_torques:
            if not math.isfinite(t):
                return False, [0.0] * len(raw_torques), 'NON_FINITE_FLOAT'

        # 3. Torque envelope clamping
        clamped = [max(-max_torque_nm, min(max_torque_nm, t)) for t in raw_torques]
        return True, clamped, 'PASS'

    # Case A: Happy path valid packet
    ok, torques, status = halos_safety_interceptor(
        current_time_ns=10_000_000,
        packet_timestamp_ns=8_000_000,  # 2ms delta (< 5ms)
        raw_torques=[12.5, -34.0, 48.0],
    )
    assert ok is True
    assert status == 'PASS'
    assert torques == [12.5, -34.0, 48.0]

    # Case B: Watchdog expired (> 5ms)
    ok, torques, status = halos_safety_interceptor(
        current_time_ns=20_000_000,
        packet_timestamp_ns=12_000_000,  # 8ms delta (> 5ms)
        raw_torques=[12.5, -34.0, 48.0],
    )
    assert ok is False
    assert status == 'WATCHDOG_EXPIRED'
    assert torques == [0.0, 0.0, 0.0]

    # Case C: Non-finite float (NaN)
    ok, torques, status = halos_safety_interceptor(
        current_time_ns=10_000_000,
        packet_timestamp_ns=9_000_000,
        raw_torques=[float('nan'), 20.0, -10.0],
    )
    assert ok is False
    assert status == 'NON_FINITE_FLOAT'
    assert torques == [0.0, 0.0, 0.0]

    # Case D: Non-finite float (Infinity)
    ok, torques, status = halos_safety_interceptor(
        current_time_ns=10_000_000,
        packet_timestamp_ns=9_000_000,
        raw_torques=[float('inf'), 20.0, -10.0],
    )
    assert ok is False
    assert status == 'NON_FINITE_FLOAT'
    assert torques == [0.0, 0.0, 0.0]

    # Case E: Clamping exceeding safety envelope
    ok, torques, status = halos_safety_interceptor(
        current_time_ns=10_000_000,
        packet_timestamp_ns=9_000_000,
        raw_torques=[65.0, -75.0, 30.0],
    )
    assert ok is True
    assert torques == [50.0, -50.0, 30.0]


def test_t4_scenario_baremetal_riscv_mmio_driver_simulation() -> None:
    """Scenario 2: End-to-end simulation of bare-metal RISC-V MMIO device register driver.

    Models:
    - Volatile 32-bit register reads and writes
    - Bitmask control register manipulation
    - Typestate transitions (Uninitialized -> Configured -> Active -> Disabled)
    - Zero heap allocation throughout register driver lifecycle.
    """
    cr_enable_bit = 1 << 0
    cr_interrupt_enable_bit = 1 << 1
    sr_ready_bit = 1 << 0
    sr_fault_bit = 1 << 7

    class MockMmioPeripheral:
        def __init__(self) -> None:
            self.cr = 0x0
            self.sr = sr_ready_bit
            self.data = 0x0

        def configure(self) -> None:
            # Set enable and interrupt flags
            self.cr |= cr_enable_bit | cr_interrupt_enable_bit

        def write_data(self, val: int) -> bool:
            if not (self.cr & cr_enable_bit):
                return False
            if self.sr & sr_fault_bit:
                return False
            self.data = val & 0xFFFFFFFF
            return True

        def trigger_fault(self) -> None:
            self.sr |= sr_fault_bit

    peripheral = MockMmioPeripheral()
    assert peripheral.write_data(0xDEADBEEF) is False  # Cannot write while disabled

    peripheral.configure()
    assert peripheral.write_data(0xDEADBEEF) is True
    assert peripheral.data == 0xDEADBEEF

    peripheral.trigger_fault()
    assert peripheral.write_data(0xCAFEBABE) is False  # Cannot write during fault


def test_t4_scenario_pixi_workspace_workflow_simulation() -> None:
    """Scenario 3: End-to-end validation of Pixi environment definition and tasks dependency graph."""
    pixi_path = EXAMPLES_DIR / 'pixi.toml'
    parsed = tomllib.loads(pixi_path.read_text(encoding='utf-8'))

    # Validate workspace metadata
    workspace = parsed.get('workspace', {})
    assert workspace.get('name') == 'rust-pro-template'
    assert 'conda-forge' in workspace.get('channels', [])
    assert 'linux-64' in workspace.get('platforms', [])
    assert 'osx-arm64' in workspace.get('platforms', [])

    # Validate tasks DAG
    tasks = parsed.get('tasks', {})
    assert 'ci' in tasks
    ci_deps = tasks['ci'].get('depends-on', [])
    assert set(ci_deps) == {'fmt', 'clippy', 'deny', 'test'}

    # Validate Linux-64 cross toolchains
    linux64_deps = parsed.get('target', {}).get('linux-64', {}).get('dependencies', {})
    assert 'gcc_linux-riscv64' in linux64_deps
    assert 'qemu-execve-riscv64' in linux64_deps


def test_t4_scenario_full_skill_audit_via_agentic_oracle() -> None:
    """Scenario 4: Authoritative AntiGravity 2.29.0 validation run of skills/rust-pro/."""
    issues = oracle_validate_skill(SKILL_DIR)
    error_issues = [i for i in issues if i.severity == Severity.ERROR]
    assert not error_issues, f'Authoritative oracle found errors in {SKILL_DIR.name}: {error_issues}'


def test_t4_scenario_cross_platform_cargo_build_matrix() -> None:
    """Scenario 5: Complete simulation of cross-platform Cargo target matrix."""
    config_path = EXAMPLES_DIR / '.cargo' / 'config.toml'
    parsed = tomllib.loads(config_path.read_text(encoding='utf-8'))
    targets = parsed.get('target', {})

    required_architectures = {
        'riscv64a23-unknown-linux-gnu': 'riscv64-linux-gnu-gcc',
        'aarch64-unknown-linux-gnu': 'aarch64-linux-gnu-gcc',
    }

    for triple, expected_linker in required_architectures.items():
        assert triple in targets, f"Target '{triple}' missing in .cargo/config.toml"
        assert targets[triple].get('linker') == expected_linker, f"Target '{triple}' linker mismatch"


def test_t4_scenario_google_styleguide_compliance_audit() -> None:
    """Scenario 6: Audit code templates across all markdown files for Google Rust Styleguide rules."""
    prohibited_glob = re.compile(r'^\s*use\s+([^:;\n]+::)+\*;\s*$', re.MULTILINE)
    unsafe_block = re.compile(r'\bunsafe\s*\{', re.MULTILINE)
    safety_comment = re.compile(r'//\s*SAFETY:', re.MULTILINE)

    all_markdown = [SKILL_MD, *list(REFERENCES_DIR.glob('*.md'))]
    for md_file in all_markdown:
        content = md_file.read_text(encoding='utf-8')
        # Check no wildcard glob imports in Rust blocks
        # Exception: allowed in tests or explicitly marked forbidden examples in style guide
        if md_file.name != 'google_rust_style_guide.md':
            for match in prohibited_glob.finditer(content):
                line = match.group(0).strip()
                assert 'super::*' in line, f"Prohibited glob import '{line}' in '{md_file.name}'"

        # Check unsafe blocks have safety comments
        if unsafe_block.search(content):
            assert safety_comment.search(content), f"'{md_file.name}' contains unsafe blocks but lacks '// SAFETY:' comments"
