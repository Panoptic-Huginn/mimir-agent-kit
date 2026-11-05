---
name: cmake-pro
description: Master Modern CMake 4.4.3+ (2026) with target-based design, modular cmake/ architecture, feature auto-detection, CMakePresets (v10+), toolchains, cross-compilation, CTest/GTest, and gersemi.
metadata:
  version: v2
  publisher: jamielapointe
---

## 🔗 Related Skills

- **spark-pro**: Formally verified SPARK Ada 2022 (`GNAT 16.1+`, `gnatprove 16.1+`, `alr 2.1+`) safety-critical robotics kernels and hybrid CMake + Alire/GPRbuild static library targets.
- **c-pro**: Modern ISO C23 (`-std=c23`, LLVM Clang 23.1+ & Apple Clang 21.0+) systems programming, real-time robotics OS safety kernels (NVIDIA Halos), and CERT C / MISRA C compliance.
- **cpp-pro**: Modern C++ standards (C++23/C++26), memory safety, template metaprogramming, and performance optimization.
- **python-pro**: Tooling, benchmark analysis scripts, and Python orchestration.
- **github-flow-lifecycle**: End-to-end Git and GitHub Flow lifecycle protocol (`github-mcp-server` issue/PR management, branch isolation, `CMakePresets.json` pre-commit local CI gates, and remote CI self-healing).

---

## Use this skill when

- Designing, writing, reviewing, or refactoring CMake build systems (`CMakeLists.txt`, `*.cmake`, `CMakePresets.json`).
- Architecting modular CMake projects using a dedicated `cmake/` helper module directory.
- Implementing dynamic hardware, CPU architecture, SIMD, and compiler capability auto-detection.
- Configuring modern target-based compile options, definitions, include directories, and dependencies.
- Setting up multi-platform builds, toolchains, and cross-compilation (e.g., embedded Linux, aarch64, RISC-V).
- Configuring `CMakePresets.json` (v10+) for configure, build, test, package, and workflow pipelines.
- Integrating sanitizers (ASan, TSan, UBSan, MSan), static analysis (`clang-tidy`), compiler launchers (`ccache`), or modern linkers (`LLD`, `MOLD`).
- Integrating automated testing with CTest and Google Test (`gtest_discover_tests`), or Google Benchmark.
- Formatting and linting CMake files with `gersemi` (formatter; it has no separate linter).

## Do not use this skill when

- Working on projects using alternative build systems (Makefiles-only, Meson, Bazel, Cargo) without intending to migrate or interface with CMake.
- General C++ coding tasks that do not involve build system configuration (use `cpp-pro` instead).

---

## Core Requirements & Golden Rules

1. **Target-Based CMake Only**:
   - Everything revolves around CMake targets (`add_library`, `add_executable`, `add_custom_target`).
   - **NEVER** use legacy global or directory-scoped commands like `include_directories()`, `link_libraries()`, `add_definitions()`, or `add_compile_options()`.
   - **ALWAYS** use target-specific commands:
     - `target_include_directories(<target> <INTERFACE|PUBLIC|PRIVATE> ...)`
     - `target_link_libraries(<target> <INTERFACE|PUBLIC|PRIVATE> ...)`
     - `target_compile_definitions(<target> <INTERFACE|PUBLIC|PRIVATE> ...)`
     - `target_compile_options(<target> <INTERFACE|PUBLIC|PRIVATE> ...)`
     - `target_sources(<target> <INTERFACE|PUBLIC|PRIVATE> ...)`
     - `target_compile_features(<target> <INTERFACE|PUBLIC|PRIVATE> ...)`

2. **Modular Architecture via `cmake/` Subfolder**:
   - Keep the root `CMakeLists.txt` clean, declarative, and focused on project definition and high-level structure.
   - Place all reusable build logic, compiler settings, sanitizer checks, platform detection, and dependency resolution into modular `.cmake` files inside a `cmake/` folder.
   - Register the folder at the root: `list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake")`.

3. **Dynamic Feature Auto-Detection over Hardcoding**:
   - Dynamically probe compiler flags, language features, and hardware support using:
     - `include(CheckCXXSourceCompiles)` / `include(CheckCSourceCompiles)`
     - `include(CheckCXXCompilerFlag)` / `include(CheckCCompilerFlag)`
     - `include(CMakePushCheckState)` to isolate test compiler/linker flags
     - `cmake_host_system_information()` for runtime host environment introspection
   - Avoid hardcoding architecture flags; verify that the compiler can actually compile and assemble the targeted instructions before enabling them.

4. **Encapsulate Settings in Interface Libraries**:
   - Encapsulate common compilation options, warning flags, definitions, and sanitizers in an interface target (e.g. `project_options` or `project_warnings`).
   - Propagate these to other project targets cleanly with `target_link_libraries(<target> PRIVATE project_options)`.

5. **CMakePresets as the Primary Workflow Interface**:
   - **EMPHASIS**: `CMakePresets.json` is the sole interface for driving CMake (schema version 10+ for modern CMake 4.4.3+).
   - Any agent calling CMake to configure, build, or test **shall** go through `CMakePresets.json` (e.g., `cmake --preset <preset_name>`, `cmake --build --preset <preset_name>`, `ctest --preset <preset_name>`).
   - If an agent is executing the entire lifecycle (configure, build, test), it **should use the workflow command**: `cmake --workflow --preset <workflow_preset_name>`.
   - Define clear `configurePresets`, `buildPresets`, `testPresets`, and unified `workflowPresets`.
   - Use standard build directories like `${sourceDir}/build/${presetName}`.

6. **Modern Tooling & Linker Integration (CMake 4.4.3+)**:
   - Utilize `CMAKE_LINKER_TYPE` (e.g., `LLD`, `MOLD`, `GOLD`, `BFD`) rather than raw flag injection.
   - Support `CMAKE_CXX_COMPILER_LAUNCHER` for `ccache` / `sccache` acceleration.
   - Integrate `CMAKE_CXX_CLANG_TIDY` directly for unified static analysis.
   - Always enable `set(CMAKE_EXPORT_COMPILE_COMMANDS ON)` for LSP (`clangd`) support.

7. **Proper Dependency Handling (Vcpkg Manifest Mode)**:
   - **Strict Vcpkg Integration**: All external dependencies must be managed via `vcpkg.json` (manifest mode).
   - **NO FetchContent**: `FetchContent` and `ExternalProject_Add` are strictly prohibited to ensure a centralized, cacheable dependency graph.
   - **Preset Toolchain Injection**: Never configure `CMAKE_TOOLCHAIN_FILE` inside `CMakeLists.txt`. It must be injected via `CMakePresets.json` using environment variables (e.g., `"CMAKE_TOOLCHAIN_FILE": "$env{VCPKG_ROOT}/scripts/buildsystems/vcpkg.cmake"`).
   - Prefer `find_package(<PackageName> CONFIG REQUIRED)` or standard find modules.
   - Always link to namespaced imported targets (`Package::Target`).
   - If an external package does not provide imported targets, wrap it in an `INTERFACE IMPORTED` target in a dedicated module.

8. **CMake Code Formatting & Style**:
   - Command names must be **lowercase** (`add_library`, `target_link_libraries`, `set`).
   - Keywords and built-in variables must be **UPPERCASE** (`PRIVATE`, `PUBLIC`, `INTERFACE`, `CMAKE_BUILD_TYPE`).
   - Agents should automatically run `gersemi -i` on generated CMake code (and `gersemi --check` in CI) to keep formatting consistent.

---

## Standard Modular Project Layout

```text
my_project/
├── CMakeLists.txt              # Top-level declarative configuration
├── CMakePresets.json           # Presets for configure, build, test, workflow
├── .gersemirc                  # Formatting rules for gersemi
├── cmake/                      # Modular helper modules
│   ├── ProjectOptions.cmake    # Optimization levels, compile flags, launchers
│   ├── CompilerWarnings.cmake  # Strict warning sets per compiler
│   ├── Sanitizers.cmake        # Dynamic ASan, TSan, UBSan detection
│   ├── Architecture.cmake      # Dynamic CPU, SIMD, and ISA detection
│   ├── Dependencies.cmake      # find_package and imported targets
│   ├── Testing.cmake           # CTest and GoogleTest integration
│   ├── Coverage.cmake          # Code coverage flags and custom targets
│   └── toolchains/             # Cross-compilation toolchains
│       └── aarch64-linux-gnu.cmake
├── src/
│   ├── CMakeLists.txt
│   └── ...
├── tests/
│   ├── CMakeLists.txt
│   └── ...
├── benchmarks/
│   ├── CMakeLists.txt
│   └── ...
└── tools/
    ├── CMakeLists.txt (optional)
    └── ...
```

---

## Canonical Reference Implementations

Complete, copy-ready CMake 4.4.3+ templates are stored in [references/canonical_templates.md](./references/canonical_templates.md) (read on demand when scaffolding or refactoring CMake build files):

1. **Root `CMakeLists.txt`**: Declarative C++23 setup, `CMAKE_EXPORT_COMPILE_COMMANDS`, `cmake/` module path registration, and `CTest` gating.
2. **`cmake/ProjectOptions.cmake`**: `project_options` interface target, `ccache` launcher detection, `CMAKE_CXX_CLANG_TIDY`, native `LLD` linker selection, and `CheckIPOSupported` LTO.
3. **`cmake/CompilerWarnings.cmake`**: `project_warnings` interface target with strict Clang/GCC and MSVC warning flags plus `WARNINGS_AS_ERRORS`.
4. **`cmake/Sanitizers.cmake`**: `project_sanitizers` interface target with `CheckCXXSourceCompiles` probing for ASan, UBSan, TSan, and MSan.
5. **`cmake/Architecture.cmake`**: `project_architecture` interface target with dynamic ISA detection (`X86_64`, `ARM64`, `RISCV64`) and compile-tested AVX2/AVX-512/NEON/SVE probes.
6. **`cmake/Testing.cmake`**: `add_project_test()` helper with `GTest` (`gtest_discover_tests` `POST_BUILD` discovery).
7. **Modern `CMakePresets.json` (Schema v10+)**: Vcpkg manifest toolchain injection, `dev-debug`, `dev-release`, `cross-aarch64`, and `ci-debug` workflow presets.
8. **Cross-Compilation Toolchain (`cmake/toolchains/aarch64-linux-gnu.cmake`)**: Sysroot-aware AArch64 cross-toolchain configuration.

---

## Code Formatting with `gersemi`

Agents and developers should actively run `gersemi` on all `CMakeLists.txt` and `.cmake` files. It is deterministic, has
a small config surface, and is distributed on PyPI (add it as a Pixi/PyPI dependency rather than installing globally):

```bash
# In-place format single file
gersemi -i CMakeLists.txt

# In-place format all CMake files in the project
gersemi -i CMakeLists.txt cmake src test

# CI / pre-commit check (non-zero exit when a file would change)
gersemi --check CMakeLists.txt cmake src test
```

Keep a `.gersemirc` (YAML) in the repository root, for example:

```yaml
line_length: 100
indent: 4
warn_about_unknown_commands: false
```

### Best Practices

- **Single source of truth**: let `gersemi` own layout, and keep naming conventions in code review (functions and
  macros `snake_case`, public variables `UPPER_CASE`, private variables prefixed with `_`).
- **Complexity**: `gersemi` does not lint, so keep functions short and push logic into small `cmake/*.cmake` modules.
- **CI / Pre-commit Integration**: run `gersemi --check` (or a local `pixi run gersemi -i` pre-commit hook) so formatting
  drift is caught early.

---

## Behavioral Traits & Standards

- **Declarative & Predictable**: Avoid deep macro nesting, implicit side effects, and global variable leaking.
- **Fail Fast & Explicitly**: Use `message(FATAL_ERROR "...")` when required tools, dependencies, or ISA checks fail.
- **Out-of-Source Builds Only**: Prevent in-source builds by checking `CMAKE_CURRENT_SOURCE_DIR` vs `CMAKE_CURRENT_BINARY_DIR`.
- **Comprehensive Documentation**: Document every custom module, interface target, and configurable `option()`.
- **Preset-First Workflow**: Agents and users must test and execute builds using `cmake --workflow --preset <name>` for end-to-end cycles, or `cmake --preset <name>` / `cmake --build --preset <name>` for specific stages.

---

## Limitations

- Use this skill exclusively for CMake build system design, configuration, and maintenance.
- Do not bypass hardware checks without verifying toolchain and emulator support in CI environments.
