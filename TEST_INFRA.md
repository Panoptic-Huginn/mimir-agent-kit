# Test Infrastructure & Opaque-Box E2E Testing Framework

**Project**: `mimir-agent-kit`  
**Target Skill**: `skills/rust-pro` (Google AntiGravity 2.29.0+ Production Skill)  
**Test Suite**: `tests/e2e/test_rust_pro_skill.py`  
**Test Framework**: `pytest>=8.3.0` under Python 3.14  
**Date**: November 2026  

---

## 1. Executive Summary & Testing Philosophy

The testing infrastructure for `skills/rust-pro` adheres to an **opaque-box end-to-end (E2E)** methodology. The test suite evaluates `skills/rust-pro/` strictly from the external boundary, testing its behavior, configuration baselines, documentation contracts, and architectural guardrails as an autonomous AntiGravity agent or human systems engineer would encounter them.

### Core Testing Invariants

1. **Opaque-Box Isolation**: Tests evaluate artifacts on disk without depending on internal implementation shortcuts or private harness hooks.
2. **Authoritative Specification Derivation**: Expected outputs and boundary thresholds are derived exclusively from authoritative sources:
   - `ORIGINAL_REQUEST.md`: Requirements R1 (Structure & AntiGravity Modularity), R2 (Toolchain, Pixi, Multi-Arch), R3 (Systems Paradigms, Safety, Google Style), R4 (Process Compliance).
   - `PROJECT.md`: Architectural specifications, sizing caps, and companion tools.
   - Google Rust Styleguide (`https://google.github.io/styleguide/rustguide.html`): Lints, imports granularity, error triad, safety justification.
   - AntiGravity 2.29.0 Specification (`scripts/validation/skills_validator.py`): Frontmatter framing, regex constraints, body size limits (< 24,000 bytes), allowed subdirectories, relative link resolution.
3. **Multi-Tier Test Architecture**: Test cases are structured across four progressive tiers ensuring depth, boundary resilience, cross-feature interaction integrity, and real-world domain viability.
4. **Zero Flakiness & Determinism**: All tests are fully self-contained, idempotent, and execute without external network calls or non-deterministic race conditions.

---

## 2. Multi-Tier Architecture & Test Counts

The test suite in `tests/e2e/test_rust_pro_skill.py` provides **74 comprehensive test cases** (exceeding the >= 65 minimum requirement):

| Tier | Focus Area | Minimum Required | Implemented Tests | Status |
|:-----|:-----------|:-----------------|:------------------|:-------|
| **Tier 1** | Feature Coverage (R1, R2, R3, R4) | $\ge 25$ | **30 tests** | Complete |
| **Tier 2** | Boundary & Corner Cases | $\ge 25$ | **26 tests** | Complete |
| **Tier 3** | Cross-Feature Interactions | $\ge 10$ | **12 tests** | Complete |
| **Tier 4** | Real-World Application Scenarios | $\ge 5$ | **6 tests** | Complete |
| **Total** | Full E2E Test Suite | $\ge 65$ | **74 tests** | **Passing / Ready** |

---

## 3. Detailed Tier Breakdown

### Tier 1: Feature Coverage (30 Tests)

Tier 1 exercises every functional requirement in isolation:

- **R1: Skill Structure & AntiGravity Conformance (11 tests)**:
  - `test_t1_r1_skill_dir_exists`: Validates presence of `skills/rust-pro/`.
  - `test_t1_r1_skill_md_exists`: Validates `skills/rust-pro/SKILL.md`.
  - `test_t1_r1_skill_frontmatter_delimiters`: Enforces opening line 1 delimiter and closing delimiter.
  - `test_t1_r1_skill_frontmatter_name`: Validates name `rust-pro` matching regex `^[a-z0-9]+(-[a-z0-9]+)*$`.
  - `test_t1_r1_skill_frontmatter_description`: Enforces description length $\ge 20$ chars.
  - `test_t1_r1_skill_frontmatter_metadata`: Validates metadata with version and publisher.
  - `test_t1_r1_skill_body_bytes_within_limit`: Enforces strictly $< 24,000$ UTF-8 bytes body size cap (`SKL005`).
  - `test_t1_r1_subdirectories_allowed`: Validates subdirectories are strictly within `{'scripts', 'examples', 'resources', 'references'}`.
  - `test_t1_r1_examples_directory_contents`: Validates all 5 configuration baselines in `examples/`.
  - `test_t1_r1_references_directory_contents`: Validates all 3 deep technical manuals in `references/`.
  - `test_t1_r1_markdown_relative_links_valid`: Verifies all relative links `[text](target)` resolve cleanly on disk.
- **R2: Toolchain, Pixi Integration & Multi-Arch (10 tests)**:
  - `test_t1_r2_pixi_toml_valid_toml`: Parses `examples/pixi.toml`.
  - `test_t1_r2_pixi_rust_version_pinned`: Validates Rust 1.99.1 dependency.
  - `test_t1_r2_pixi_conda_forge_channel`: Validates `conda-forge` channel configuration.
  - `test_t1_r2_pixi_companion_tools`: Validates `cargo-nextest`, `cargo-audit`, `cargo-deny`, `cargo-llvm-cov`, `cargo-zigbuild`.
  - `test_t1_r2_pixi_task_definitions`: Validates task workflow (`test`, `clippy`, `fmt`, `deny`).
  - `test_t1_r2_cargo_config_valid_toml`: Parses `examples/.cargo/config.toml`.
  - `test_t1_r2_cargo_config_cross_targets`: Validates Linux, macOS, and RISC-V targets.
  - `test_t1_r2_cargo_config_riscv_rva23_features`: Validates RVA23 target flags (`+rva23u64`, vector, bitmanip, atomics).
  - `test_t1_r2_cargo_config_runner_qemu`: Validates QEMU cross-execution runner.
  - `test_t1_r2_toolchain_reference_doc`: Validates technical documentation in `toolchain_and_targets.md`.
- **R3: Systems Paradigms, Safety Guardrails & Google Style (8 tests)**:
  - `test_t1_r3_systems_paradigms_doc`: Validates coverage of `std`, `no_std` embedded, and bare-metal paradigms.
  - `test_t1_r3_bare_metal_mmio_guidance`: Validates zero-allocation typestate MMIO guidance.
  - `test_t1_r3_safety_guardrails_rationale`: Enforces mandatory `// SAFETY:` rationale comments and `#![deny(unsafe_op_in_unsafe_fn)]`.
  - `test_t1_r3_halos_interceptor_pattern`: Validates NVIDIA Halos command interceptor with watchdog and finite float checks.
  - `test_t1_r3_google_style_guide_doc`: Validates Google Rust Styleguide coverage in `references/google_rust_style_guide.md`.
  - `test_t1_r3_cargo_toml_lint_table`: Validates `[lints.rust]` and `[lints.clippy]` table in `Cargo.toml`.
  - `test_t1_r3_clippy_toml_rules`: Validates cognitive complexity thresholds and disallowed methods in `clippy.toml`.
  - `test_t1_r3_rustfmt_toml_settings`: Validates `max_width = 100` and `imports_granularity = "Module"` in `rustfmt.toml`.
- **R4: Process & Repository Invariants (1 test)**:
  - `test_t1_r4_pure_uv_guardrail_in_skill`: Enforces that skill instructions maintain the repository's pure-uv boundary.

### Tier 2: Boundary & Corner Cases (26 Tests)

Tier 2 stress-tests boundary limits, corrupt inputs, threshold conditions, and validator rejection behaviors:

- `test_t2_b01_exact_24kb_limit_edge_behavior`: Verifies behavior at exactly 24,000 bytes vs 24,001 bytes.
- `test_t2_b02_empty_skill_body_validation`: Validates validator response to empty markdown body.
- `test_t2_b03_empty_frontmatter_rejected`: Rejects empty frontmatter with missing name.
- `test_t2_b04_frontmatter_missing_opening_delimiter`: Rejects missing opening `---` with `SKL002`.
- `test_t2_b05_frontmatter_missing_closing_delimiter`: Rejects unclosed frontmatter with `SKL002`.
- `test_t2_b06_frontmatter_non_mapping_yaml`: Rejects scalar/sequence YAML in frontmatter.
- `test_t2_b07_frontmatter_name_mismatch_directory`: Rejects name mismatch (`rust` vs `rust-pro`) with `SKL003`.
- `test_t2_b08_frontmatter_name_invalid_regex`: Rejects invalid characters (e.g. uppercase, underscores) with `SKL003`.
- `test_t2_b09_frontmatter_description_19_chars_rejected`: Rejects 19-char description (< 20 cap) with `SKL004`.
- `test_t2_b10_frontmatter_description_20_chars_accepted`: Accepts exactly 20-char description.
- `test_t2_b11_disallowed_subdirectory_rejected`: Flags illegal subdirectories (`src/`, `target/`) with `SKL006`.
- `test_t2_b12_missing_skill_md_rejected`: Flags missing `SKILL.md` with `SKL001`.
- `test_t2_b13_non_utf8_skill_md_rejected`: Flags non-UTF8 byte streams with `SKL002`.
- `test_t2_b14_relative_link_missing_target_detected`: Detects dangling relative links with `SKL008`.
- `test_t2_b15_relative_link_with_anchor_resolved`: Resolves markdown anchor links (`path.md#section`) to base file.
- `test_t2_b16_relative_link_url_ignored`: Verifies http/https links are excluded from local path checks.
- `test_t2_b17_prohibited_pixi_in_repo_commands_rejected`: Confirms rule validator flags `pixi` for repo tasks (`PRM003`).
- `test_t2_b18_secret_hygiene_home_path_leak_detected`: Confirms secret validator catches developer absolute home path patterns.
- `test_t2_b19_secret_hygiene_clean_in_skill_files`: Audits all `skills/rust-pro/` files for leaked home paths.
- `test_t2_b20_cargo_toml_corrupt_syntax_rejected`: Validates detection of corrupt TOML syntax.
- `test_t2_b21_pixi_toml_missing_dependencies_table`: Validates detection of missing dependencies table.
- `test_t2_b22_rustfmt_toml_invalid_width_boundary`: Validates `max_width <= 100` boundary enforcement.
- `test_t2_b23_clippy_toml_cognitive_complexity_threshold`: Validates cognitive complexity threshold $\le 25$.
- `test_t2_b24_skill_md_actual_body_size_headroom`: Asserts actual body has $\ge 500$ bytes safety headroom before 24,000 bytes.
- `test_t2_b25_reference_manuals_sizing`: Asserts each reference manual remains within 24,000 bytes.
- `test_t2_b26_empty_files_rejected`: Asserts zero empty (0-byte) files exist in the skill directory.

### Tier 3: Cross-Feature Interactions (12 Tests)

Tier 3 tests the coupling and pairwise integration between distinct features:

- `test_t3_cross_target_and_systems_paradigm_linux_std`: Linux x86_64 target with standard library threading/async.
- `test_t3_cross_target_and_systems_paradigm_linux_aarch64_embedded`: Linux aarch64 target with `no_std` embedded HAL.
- `test_t3_cross_target_and_systems_paradigm_macos_aarch64`: macOS Apple Silicon target with Pixi companion build tools.
- `test_t3_cross_target_and_systems_paradigm_riscv_rva23_baremetal`: RISC-V RVA23 target with bare-metal MMIO register drivers.
- `test_t3_cross_pixi_dependencies_and_cargo_features`: Integration of Pixi Rust 1.99.1 dependency with Cargo companion tools.
- `test_t3_cross_cargo_lints_and_google_style`: Alignment between `Cargo.toml` `[lints.clippy]` and Google Rust Styleguide rules.
- `test_t3_cross_clippy_toml_and_rustfmt_toml`: Consistency between `clippy.toml` formatting lints and `rustfmt.toml`.
- `test_t3_cross_halos_interceptor_and_c_abi_export`: Cross-language C-ABI export contract for NVIDIA Halos interceptor.
- `test_t3_cross_safety_guardrail_and_compiler_attributes`: Interaction of `// SAFETY:` proofs with `#![deny(unsafe_op_in_unsafe_fn)]`.
- `test_t3_cross_pixi_tasks_and_cargo_test_runners`: Mapping of Pixi workflow tasks (`pixi run test`) to Cargo runners.
- `test_t3_cross_error_triad_and_thiserror_anyhow`: Separation of library error enums (`thiserror`) and application errors (`anyhow`).
- `test_t3_cross_skill_prompt_references_consistency`: Cross-reference validation between `SKILL.md` and installed skills.

### Tier 4: Real-World Application Scenarios (6 Tests)

Tier 4 simulates realistic, end-to-end production scenarios:

- `test_t4_scenario_halos_robotics_interceptor_simulation`: Full simulation of NVIDIA Halos Command Interceptor (packet parsing, 5ms watchdog expiration, finite float validation, NaN/Inf torque rejection, clamped torque output, fail-safe fallback).
- `test_t4_scenario_baremetal_riscv_mmio_driver_simulation`: Full simulation of bare-metal RISC-V MMIO device register driver (volatile read/write semantics, bitmask manipulation, typestate state machine, zero dynamic heap allocation).
- `test_t4_scenario_pixi_workspace_workflow_simulation`: Full simulation of Pixi workspace configuration, dependency resolution, multi-platform targets, and task dependency graph (`ci -> [fmt, clippy, deny, test]`).
- `test_t4_scenario_full_skill_audit_via_agentic_oracle`: Complete authoritative validation pass using `oracle_validate_skill()` producing 0 errors and 0 warnings.
- `test_t4_scenario_cross_platform_cargo_build_matrix`: Complete simulation of cross-platform target matrix covering x86_64, aarch64, and RISC-V RVA23.
- `test_t4_scenario_google_styleguide_compliance_audit`: Comprehensive AST and static analysis of code templates ensuring zero glob imports, module-level granularity, and safety rationales.

---

## 4. Feature Traceability Matrix

| Requirement | Feature Description | Tier 1 Tests | Tier 2 Tests | Tier 3 Tests | Tier 4 Tests | Total Tests |
|:------------|:--------------------|:-------------|:-------------|:-------------|:-------------|:------------|
| **R1** | Skill Structure & Modularity | 11 | 16 | 2 | 2 | **31** |
| **R2** | Toolchain & Pixi Multi-Arch | 10 | 4 | 4 | 2 | **20** |
| **R3** | Systems Paradigms & Style | 8 | 4 | 5 | 2 | **19** |
| **R4** | Process Compliance & Hygiene | 1 | 2 | 1 | 0 | **4** |
| **Total** | | **30** | **26** | **12** | **6** | **74** |

---

## 5. Test Execution Instructions

### Running the Entire E2E Test Suite

```bash
uv run pytest tests/e2e/test_rust_pro_skill.py -v
```

### Running by Tier

```bash
# Tier 1: Feature Coverage
uv run pytest tests/e2e/test_rust_pro_skill.py -k "test_t1" -v

# Tier 2: Boundary & Corner Cases
uv run pytest tests/e2e/test_rust_pro_skill.py -k "test_t2" -v

# Tier 3: Cross-Feature Interactions
uv run pytest tests/e2e/test_rust_pro_skill.py -k "test_t3" -v

# Tier 4: Real-World Scenarios
uv run pytest tests/e2e/test_rust_pro_skill.py -k "test_t4" -v
```

### Running with Code Coverage

```bash
uv run pytest tests/e2e/test_rust_pro_skill.py --cov=scripts.validation --cov-report=term-missing
```

---

## 6. Verification & Quality Gates

The test infrastructure is validated through:

1. **Syntax & AST Compilation**: Clean compilation under Python 3.14.7.
2. **Linting Compliance**: Strict conformance to `ruff` rules (isort single-line, Google docstrings, single quotes).
3. **Type Checking**: Strict `mypy` validation with zero type errors.
4. **Pre-Commit Invariant**: Passing `bash scripts/ci/run_local_ci.sh` with exit code 0.
