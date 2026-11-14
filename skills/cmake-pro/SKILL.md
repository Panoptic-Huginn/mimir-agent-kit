---
name: cmake-pro
description: Masters Modern CMake 4.5+ (November 2026) on Linux and macOS with target-based design, modular cmake/ architecture, pixi 0.84.2+ (conda-forge) dependencies, CMakePresets.json (Schema v13), FILE_SET (HEADERS and SOURCES), cmake_diagnostic() (CMD_NON_TARGET_DIRECTIVE), CPS (PACKAGE_INFO) and SPDX 3.0.1 SBOM packaging, ISA/SIMD probes, cross-compilation, CTest/GTest/discover_tests(), and gersemi formatting.
metadata:
  version: v3
  publisher: jamielapointe
---

# Modern CMake 4.5+ Systems & Build Engineering

Build deterministic, target-based **CMake 4.5+** (November 2026) software systems exclusively for **Linux** (`linux-64`, `linux-aarch64`, and `riscv64` RVA23 cross-compilation) and **macOS** (`osx-arm64`) using **LLVM/Clang 23.1.5+**, **Ninja**, and **Pixi 0.84.2+** (`conda-forge`)—with GCC supported strictly for sysroot or cross-compilation toolchains.

## Related Skills

- **`/ada-spark-pro`**: Formally verified SPARK Ada 2022 (`alr 2.1.1+`, `gnat_native=16.1.0`, `gnatprove=16.1.0`) encapsulated static libraries via `cmake/SparkTargets.cmake` and `install(... BUILD_DEPENDS ...)`.
- **`/c-pro`**: Modern ISO C23 (`CMAKE_C_STANDARD 23`, `<stdbit.h>` probes, dual-language `extern "C"` ABI headers) for real-time OS and safety kernels.
- **`/cpp-pro`**: Modern ISO C++23 (`LLVM/Clang 23.1.5`), `-fno-exceptions -fno-rtti` defaults, C++ modules ban for determinism, and the Linux `libstdc++` vs. macOS `libc++` native standard library ABI rule.
- **`/rust-pro`**: Rust 1.99.1+ (`edition = "2024"`, `#![no_std]` capable) via Cargo, Corrosion, and Crubit `cpp_api_from_rust` / C ABI interop (`CMAKE_EXPERIMENTAL_RUST` remains experimental in CMake 4.5).
- **`/python-pro`**: Python 3.14.7 + `nanobind` CMake module targets and canonical **`pixi` 0.84.2+** workspace/environment workflows.
- **`/github-flow-lifecycle`**: 6-stage Git/GitHub Flow protocol enforcing branch isolation, local `CMakePresets.json` pre-commit CI gates, and remote Actions self-healing.

---

## Use this skill when

- Architecting, reviewing, or refactoring `CMakeLists.txt`, `cmake/*.cmake`, `CMakePresets.json` (v13), `pixi.toml`, `.gersemirc`, or `.pre-commit-config.yaml` on Linux or macOS.
- Enforcing strict target encapsulation, `FILE_SET` (`HEADERS`/`SOURCES`), `cmake_diagnostic()` rules, sanitizers, or hardware ISA/SIMD feature probes.
- Packaging artifacts with CMake 4.3–4.5 GA Common Package Specification (**CPS** via `PACKAGE_INFO`) and native **SPDX 3.0.1** JSON-LD **SBOM** generation (`install(SBOM ...)`).
- Configuring cross-compilation toolchains (`aarch64-linux-gnu`, `riscv64-linux-gnu` RVA23), `cmake_instrumentation()`, or `CTest` + Google Test / `discover_tests()`.

## Do not use this skill when

- Maintaining pure Makefile, Meson, Bazel, or standalone Cargo builds without CMake integration.
- Authoring application logic without build-system changes (use `/c-pro`, `/cpp-pro`, `/rust-pro`, or `/ada-spark-pro`).

---

## Core Requirements & 8 Golden Rules

1. **Target-Based CMake, File Sets & Strict Diagnostics (CMake 4.5+)**:
   - Declare `cmake_minimum_required(VERSION 4.5)` and `cmake_diagnostic(SET CMD_NON_TARGET_DIRECTIVE SEND_ERROR)` at the root to hard-reject all 7 legacy non-target commands (`include_directories`, `link_libraries`, `link_directories`, `add_definitions`, `add_compile_definitions`, `add_compile_options`, `add_link_options`). Valid `cmake_diagnostic()` actions are `IGNORE`, `WARN`, `SEND_ERROR`, and `FATAL_ERROR` (`ERROR` is invalid).
   - Register headers and sources with `target_sources(<tgt> {PUBLIC|PRIVATE|INTERFACE} FILE_SET <name> [TYPE <HEADERS|SOURCES>] BASE_DIRS ... FILES ...)` (omit `TYPE` when `<name>` matches `HEADERS` or `SOURCES`). Apply fine-grained properties with `set_property(FILE_SET <name> TARGET <tgt> PROPERTY <PROP> <val>)` using CMake 4.4–4.5 properties: `SKIP_LINTING`, `SKIP_PRECOMPILE_HEADERS`, `SKIP_UNITY_BUILD_INCLUSION`, `CXX_SCAN_FOR_MODULES`, `INDEPENDENT_FILES`, and `JOB_POOL_COMPILE`.
   - Keep `CMAKE_VERIFY_INTERFACE_HEADER_SETS` and `CMAKE_VERIFY_PRIVATE_HEADER_SETS` as preset/CI controls rather than hardcoding `ON` in `CMakeLists.txt`; filter targets via `{INTERFACE,PRIVATE}_HEADER_SETS_TO_VERIFY`.
   - Take advantage of **CMake 4.5 `ALIAS` parity**: `target_*()`, `add_dependencies()`, `set_property()`, `set_target_properties()`, `install()`, and `export()` accept `ALIAS` targets directly (`ALIASED_TARGET` remains read-only).

2. **Modular `cmake/` Architecture & Scoped Isolation**:
   - Keep root `CMakeLists.txt` strictly declarative, guard against in-source builds (`PROJECT_SOURCE_DIR STREQUAL PROJECT_BINARY_DIR`), and register `list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake")`.
   - Isolate variable, policy, and diagnostic mutations using `block(SCOPE_FOR VARIABLES POLICIES DIAGNOSTICS)` inside helper modules (`Sanitizers.cmake`, `Architecture.cmake`) so temporary probe variables never leak. When including `ProjectOptions.cmake`, scope only `POLICIES DIAGNOSTICS` (or `PROPAGATE`) so launcher/linker cache and directory variables apply globally.

3. **Dynamic ISA, SIMD & Compiler Feature Probing**:
   - Never hardcode `-march` or `-m*` flags unconditionally. Probe capabilities inside `cmake_push_check_state()` + `check_cxx_source_compiles()` / `check_c_source_compiles()` / `check_cxx_compiler_flag()`:
     - **`X86_64`**: Probe AVX2+FMA (`-mavx2 -mfma`) and AVX-512 (`-mavx512f -mavx512vl -mavx512dq -mavx512bw`).
     - **`ARM64`**: Enable baseline NEON and probe SVE (`-march=armv8-a+sve`).
     - **`RISCV64` (RVA23)**: Probe RVV 1.0 (`-march=rva23u64`, fallback `-march=rv64gcv`) compiling `<riscv_vector.h>` (`__riscv_v_intrinsic >= 1000000`, `__riscv_vsetvl_e32m1`).
   - Normalize `ARCH_FAMILY_<X>` and define `TARGET_CACHE_LINE_BYTES` (`128` on `ARM64` vs. `64` on `X86_64`/`RISCV64`). Gate `ENABLE_NATIVE_OPTIMIZATION` (`-march=native`) strictly with `if(NOT CMAKE_CROSSCOMPILING)` and compile verification.

4. **Interface Target Encapsulation, Exceptions/RTTI & Module-Scanning Discipline**:
   - Encapsulate compiler policy inside `INTERFACE` targets (`project_options`, `project_warnings`, `project_sanitizers`, `project_architecture`) linked via `PRIVATE`.
   - Match `/cpp-pro`: default **`-fno-exceptions -fno-rtti`** on `project_options` guarded by `$<$<COMPILE_LANGUAGE:CXX>:...>` (so mixed C23 targets never receive C++-only flags), exposing `ENABLE_EXCEPTIONS` and `ENABLE_RTTI` options (`OFF` by default).
   - Default C++20/23 module scanning **`OFF`** via **non-cache** `set(CMAKE_CXX_SCAN_FOR_MODULES OFF)` gated by `option(ENABLE_CXX_MODULES "..." OFF)` so `ccache`, `clang-tidy`, and `misc-include-cleaner` stay deterministic. When `ENABLE_CXX_MODULES=ON` for standalone C++23 `import std` projects on Ninja (`>= 1.11`), CMake 4.5 treats `import std` and `import std.compat` as **GA** (do **not** use obsolete `CMAKE_EXPERIMENTAL_CXX_IMPORT_STD` UUIDs or `CXX_MODULE_STD`; override `CMAKE_CXX_STDLIB_MODULES_JSON` before `project()` only if compiler auto-discovery fails).
   - Enforce Clang 23.1+ and GCC strict C23/C++23 warnings in `CompilerWarnings.cmake` (`WARNINGS_AS_ERRORS` -> `-Werror`), and probe ASan, UBSan (`-fsanitize=undefined -fno-sanitize-recover=all`), TSan, and MSan (Clang+Linux only) with mutual exclusions in `Sanitizers.cmake`.

5. **`CMakePresets.json` Schema v13 as the Sole Workflow Interface**:
   - Standardize on `"version": 13` and `"cmakeMinimumRequired": {"major": 4, "minor": 5, "patch": 0}` with `"binaryDir": "${sourceDir}/build/${presetName}"`.
   - Enable v12–v13 strict diagnostics in `"base"`: `warnings` (`author`, `deprecated`, `policy`, `strict`, `nonTargetDirective`, `installAbsoluteDestination`, `uninitialized`, `unusedCli`) and `errors` (`nonTargetDirective`, `deprecated`). **Never** emit `warnings.dev` or `errors.dev`—they were removed in Schema v12 and error in v13! Reserve `errors.unusedCli: true` for project-final presets rather than shared bases.
   - Use `${configurePresetName}` (v13) in `buildPresets`/`testPresets`/`packagePresets` fields that support macro expansion (e.g., `outputJUnitFile`, `environment`) and optionally in `description`—**never** inside `workflowPresets` (macros do not expand in workflow steps) and note `displayName` renders literals verbatim. Use `${fileDir}` (v12+ file-local semantics) for cross-file toolchain paths.
   - Use `--presets-file <file>` (4.4+) for out-of-tree presets, `--list-presets=all-defined` (4.5+) to inspect every defined preset and unavailability reasons, `execution.testPassthroughArguments` (v12+, e.g., `["--gtest_brief=1"]`), and `cmake --workflow --preset <name>` for full pipelines.

6. **Modern Tooling, Instrumentation, Introspection & Testing**:
   - **Linkers & Launchers**: Default `CMAKE_LINKER_TYPE` (`LLD`, `MOLD`, `WILD` on Linux; `SYSTEM` `ld_prime` or probed `LLD` on Apple) inside `if(NOT DEFINED CMAKE_LINKER_TYPE)` only after `check_linker_flag()` validation. Wire `ccache`/`sccache` via `CMAKE_<LANG>_COMPILER_LAUNCHER`, `CMAKE_CXX_CLANG_TIDY`, and `CMAKE_EXPORT_COMPILE_COMMANDS ON`.
   - **Instrumentation & Debugging**: Collect Ninja/Make build telemetry with `cmake_instrumentation(API_VERSION 1 DATA_VERSION 1.2 HOOKS ... OPTIONS compileTrace processMetrics trace)` and `ctest --collect-instrumentation`. Inspect targets and properties with `cmake_language(PRINT_TARGETS / PRINT_PROPERTIES / PRINT_VARIABLES)` instead of legacy `CMakePrintHelpers`.
   - **Testing**: Use `gtest_discover_tests(... DISCOVERY_MODE POST_BUILD)` (switching to `PRE_TEST` when `CMAKE_CROSSCOMPILING` + `CMAKE_CROSSCOMPILING_EMULATOR` is set) and CMake 4.4–4.5 `discover_tests(... DISCOVERY_MATCH ... BUILD_DEPENDS ...)` (feeding `ctest --out-of-date`), honoring `CMP0224` (`AROUND_EACH_REPEAT` / `FIXTURE_REPEAT_MODE`).

7. **Hermetic `pixi` 0.84.2+ Dependencies, ABI Rules, CPS & SPDX 3.0.1 SBOM**:
   - **Pixi + `conda-forge` Primary**: Manage compilers, CMake 4.5+, Ninja, `gersemi`, `pre-commit`, and libraries (`libabseil`—never broken legacy `abseil-cpp >=20260817.0`—`gtest`, `benchmark`) via `pixi.toml` (`requires-pixi = ">=0.84.2"`, `platforms = ["linux-64", "linux-aarch64", "osx-arm64"]`). Gate `pixi-base` in `CMakePresets.json` on non-empty `$env{CONDA_PREFIX}`, setting `CMAKE_C_COMPILER: "clang"`, `CMAKE_CXX_COMPILER: "clang++"`, and `CMAKE_PREFIX_PATH: "$env{CONDA_PREFIX}"`. Consult `/python-pro` for `pixi` CLI workflows and `/cpp-pro` for stdlib ABI discipline.
   - **Platform-Native Stdlib ABI Rule**: Preserve Linux **`libstdc++`** and macOS **`libc++`** (`libcxx` in `[target.osx-arm64.dependencies]`); never force `-stdlib=libc++` on Linux against `conda-forge` libraries.
   - **No `FetchContent` / Air-Gapped Fallback**: `FetchContent` and `ExternalProject_Add` are strictly forbidden. For air-gapped or embedded SDK builds without Pixi, inherit `"base"` directly (`sysroot-release`) and use `find_package(<Pkg> CONFIG REQUIRED)` with `CMAKE_FIND_ROOT_PATH_MODE_{LIBRARY,INCLUDE,PACKAGE}=ONLY`. Export `CMAKE_SYSTEM_ENVIRONMENT_ID` in `pixi.toml` `[activation.env]` (not preset `environment`) when using `CMAKE_SYSTEM_ENVIRONMENT_ACTION=REFRESH`.
   - **GA CPS (`PACKAGE_INFO`) & SPDX 3.0.1 `SBOM`**: Set `COMPAT_VERSION` and `SPDX_LICENSE` in `project()`. Export packages via `install(PACKAGE_INFO <Pkg> EXPORT <Exp> LOWER_CASE_FILE)` (`find_package()` resolves `.cps` natively) and emit compliance artifacts via `install(SBOM <Name> EXPORTS <Exp>... DATA_LICENSE "CC0-1.0" DEFAULT_LICENSE "${PROJECT_SPDX_LICENSE}" FORMAT spdx-3.0.1+json)` or preset `CMAKE_INSTALL_SBOM_FORMATS`. Wrap generator expressions in `LINK_LIBRARIES` inside `$<LINK_ONLY:...>` so `SBOM` export succeeds cleanly.

8. **Deterministic `gersemi` (`0.19.2+`) Formatting & Pre-Commit Enforcement**:
   - Lowercase commands (`add_library`, `target_sources`), UPPERCASE keywords/variables (`PUBLIC`, `FILE_SET`, `CMAKE_BUILD_TYPE`), `line_length: 100`, `indent: 4`, `list_expansion: favour-inlining`.
   - Wrap `install(SBOM ... EXPORTS ...)` in `# gersemi: off` / `# gersemi: on` when running `gersemi 0.29.2` (whose built-in command table still carries pre-4.5 SBOM keywords), and double-escape regex backreferences (`\\1.\\2`) inside `discover_tests()`.
   - Gate commits with `gersemi --check`, `clang-format --dry-run --Werror`, and `clang-tidy -p build/ci-debug --warnings-as-errors=*` in `.pre-commit-config.yaml` (matching `ci-debug` binary directory `build/ci-debug`).

---

## Standard Modular Project Layout

```text
my_project/
├── pixi.toml                   # Hermetic conda-forge workspace (Linux + macOS)
├── CMakeLists.txt              # Declarative CMake 4.5+ root (CPS + SPDX SBOM)
├── CMakePresets.json           # Schema v13 configure, build, test, workflow presets
├── .gersemirc                  # Deterministic gersemi 0.19.2+ formatting rules
├── .pre-commit-config.yaml     # SHA-frozen hygiene + gersemi + clang-format/tidy
├── cmake/
│   ├── ProjectOptions.cmake    # project_options, ccache, clang-tidy, CMAKE_LINKER_TYPE, IPO
│   ├── CompilerWarnings.cmake  # project_warnings (Clang 23.1+ & GCC strict flags)
│   ├── Sanitizers.cmake        # project_sanitizers (block-scoped ASan/UBSan/TSan/MSan)
│   ├── Architecture.cmake      # project_architecture (X86_64/ARM64/RISCV64 RVA23 probes)
│   ├── Dependencies.cmake      # find_package(CONFIG REQUIRED) & IMPORTED wrappers
│   ├── Testing.cmake           # gtest_discover_tests + CMake 4.5 discover_tests()
│   ├── Coverage.cmake          # llvm-cov / llvm-profdata target integration
│   ├── SparkTargets.cmake      # Optional Alire/GPRbuild SPARK Ada static targets
│   └── toolchains/
│       ├── aarch64-linux-gnu.cmake
│       └── riscv64-linux-gnu.cmake
├── include/<pkg>/              # Public headers (FILE_SET HEADERS)
├── src/                        # Implementation units (FILE_SET TYPE SOURCES)
└── tests/                      # Hermetic unit tests
```

---

## Decision Trees

### Dependency, Toolchain & Preset Routing

```text
Configuring a CMake 4.5+ build environment?
├── Standard Linux (x86_64/aarch64) or macOS (osx-arm64) workstation/CI?
│   └── Activate Pixi (`pixi run configure` / `pixi run workflow`) -> inherits `pixi-base`
│       (requires `$env{CONDA_PREFIX}`, sets Clang + `$env{CONDA_PREFIX}`, preserves Linux libstdc++ / macOS libc++).
├── Air-gapped host or bare-metal SDK without Pixi?
│   └── Use `sysroot-release` (inherits `base`, NOT `pixi-base`) + `find_package(<Pkg> CONFIG REQUIRED)`.
└── Targeting AArch64 or RISC-V RVA23 Linux from host?
    └── Use `cross-aarch64` or `cross-riscv64` (`toolchainFile: "${fileDir}/cmake/toolchains/..."`,
        `CMAKE_FIND_ROOT_PATH_MODE_* = ONLY`, `BUILD_TESTING = OFF` unless QEMU emulator wired).
```

### Cross-Language CMake 4.5 Integration

```text
Integrating non-C++ targets into CMake 4.5?
├── ISO C23 (/c-pro) --------------> `CMAKE_C_STANDARD 23`, probe `<stdbit.h>`, dual `extern "C"` headers.
├── Rust 1.99.1+ (/rust-pro) ------> Cargo + Corrosion + Crubit `cpp_api_from_rust` (or `cxx`/`extern "C"`).
├── SPARK Ada 2022 (/ada-spark-pro)> `cmake/SparkTargets.cmake` (`alr -n gnatprove` + `install(... BUILD_DEPENDS)`).
└── Python 3.14.7 (/python-pro) ---> `find_package(Python 3.14 ...)` + `nanobind_add_module` (no `LIBRARY DESTINATION`).
```

### Packaging Metadata & Module Scanning

```text
Publishing libraries or enabling C++23 modules?
├── Packaging reusable C/C++ libraries?
│   └── Always emit CPS (`install(PACKAGE_INFO ... LOWER_CASE_FILE)`) + SPDX 3.0.1 SBOM (`install(SBOM ...)`),
│       wrapping conditional link dependencies in `$<LINK_ONLY:...>`.
└── Should C++20/23 module scanning be enabled?
    ├── Normal multi-tool project (`ccache`, `clang-tidy`, `misc-include-cleaner`) -> Keep `ENABLE_CXX_MODULES=OFF` (`set(CMAKE_CXX_SCAN_FOR_MODULES OFF)`).
    └── Standalone Ninja (`>= 1.11`) `import std` target -> Opt in via `-DENABLE_CXX_MODULES=ON` (GA in CMake 4.5, no experimental UUIDs).
```

---

## Examples & References Index

- **Turnkey Examples (`examples/`)**:
  - [examples/pixi.toml](./examples/pixi.toml): Hermetic Linux (`linux-64`, `linux-aarch64`) and macOS (`osx-arm64`) `conda-forge` workspace (`cmake >=4.5.0`, `clangxx >=23.1.5`, `libabseil`, `gtest`, `benchmark`, `gersemi`, `pre-commit`).
  - [examples/CMakePresets.json](./examples/CMakePresets.json): Schema v13 presets (`base`, `pixi-base`, `ci-debug`, `dev-debug`, `dev-release`, `ci-tsan`, `sysroot-release`, `cross-aarch64`, `cross-riscv64`, plus matching build/test/workflow presets).
  - [examples/CMakeLists.txt](./examples/CMakeLists.txt): Validated CMake 4.5 root template with `CMD_NON_TARGET_DIRECTIVE`, `ENABLE_CXX_MODULES`, `FILE_SET HEADERS`/`SOURCES`, `ALIAS` install/export parity, CPS `PACKAGE_INFO`, and `# gersemi: off`/`on` SPDX 3.0.1 `SBOM`.
  - [examples/.gersemirc](./examples/.gersemirc): Deterministic `gersemi` (`0.19.2+` / `0.29.2`) formatting configuration.
  - [examples/.pre-commit-config.yaml](./examples/.pre-commit-config.yaml): SHA-frozen `pre-commit` hygiene plus `gersemi --check`, `clang-format`, and `clang-tidy -p build/ci-debug`.
- **Deep-Dive Reference Manuals (`references/`)**:
  - [references/canonical_templates.md](./references/canonical_templates.md): Complete `cmake/*.cmake` modules (`ProjectOptions`, `CompilerWarnings`, `Sanitizers`, `Architecture` with RVA23 RVV 1.0 probes, `Dependencies`, `Testing` with `discover_tests()`, and `Coverage`).
  - [references/presets_toolchains_and_pixi.md](./references/presets_toolchains_and_pixi.md): Schema v13 rules, `pixi 0.84.2+` `$env{CONDA_PREFIX}` wiring, air-gapped sysroot builds, AArch64/RISC-V RVA23 toolchains, `cmake_instrumentation()`, and `cmake_language(PRINT_*)`.
  - [references/packaging_cps_sbom_and_interop.md](./references/packaging_cps_sbom_and_interop.md): `FILE_SET` properties, header verification, GA CPS (`PACKAGE_INFO`), GA SPDX 3.0.1 `SBOM`, CMake 4.5 `ALIAS` parity, and C23 / Rust / SPARK Ada / `nanobind` interop recipes.

---

## Behavioral Guardrails

- **Out-of-Source & Preset-First**: Reject in-source builds immediately and drive configure/build/test through `CMakePresets.json` (`cmake --workflow --preset ci-debug` or `pixi run ci`).
- **Fail Fast**: Use `message(FATAL_ERROR "...")` when required compilers, linkers, sysroots, or ISA probes fail.
- **No Hook Bypasses**: Never pass `--no-verify` or bypass pre-commit hooks; satisfy `gersemi --check`, `clang-format`, and `clang-tidy` before committing (`/github-flow-lifecycle`).
