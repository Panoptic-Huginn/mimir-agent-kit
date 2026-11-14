# `CMakePresets.json` v13, Toolchains, Pixi & Build Instrumentation

Reference guide for driving CMake 4.5+ builds on Linux (`linux-64`, `linux-aarch64`, `riscv64` RVA23) and macOS (`osx-arm64`) through `CMakePresets.json` Schema v13, hermetic `pixi 0.84.2+` workspaces, air-gapped sysroots, cross-compilation toolchains, and build instrumentation.

---

## 1. `CMakePresets.json` Schema v13 Architecture

Schema v13 (introduced in CMake 4.5) adds `strict` and `nonTargetDirective` diagnostic controls alongside `${configurePresetName}` macro expansion:

- **Schema & Minimum Version**: Set `"version": 13` and `"cmakeMinimumRequired": { "major": 4, "minor": 5, "patch": 0 }`.
- **`warnings` & `errors` on `configurePresets`**:
  - Available keys: `author` (v12+), `deprecated`, `experimental` (v12+), `installAbsoluteDestination` (v12+, `CMD_INSTALL_ABSOLUTE_DESTINATION`), `nonTargetDirective` (v13, `CMD_NON_TARGET_DIRECTIVE`), `policy` (v12+), `strict` (v13, `CMD_STRICT`), `uninitialized`, `unusedCli`, plus `systemVars` (in `warnings` only).
  - **Breaking v12+ removal**: `warnings.dev` and `errors.dev` were removed (`until: 12`); including `"dev"` in Schema v13 fails preset parsing.
  - **`errors.unusedCli` pitfall**: Setting `"errors": { "unusedCli": true }` in shared base presets aborts configure whenever a downstream project omits one cached variable (note `CMAKE_PREFIX_PATH` does not trigger `unusedCli`). Keep `"warnings": { "unusedCli": true }` in shared presets and reserve `"errors": { "unusedCli": true }` for project-specific presets.
- **Macros**:
  - **`${configurePresetName}`** (v13): Expands to `${presetName}` in `configurePresets`, and to `configurePreset` in `buildPresets`, `testPresets`, and `packagePresets`. **Never** use `${configurePresetName}` inside `workflowPresets`—`workflowPresets[].steps[].name` performs no macro expansion and fails validation.
  - **`${fileDir}`** (v12+): Consistently resolves to the directory of the presets file containing `${fileDir}`, governed by that file's `version` even when inherited across directories.
- **Test Passthrough (`testPresets[].execution.testPassthroughArguments`)**: Added in v12 to forward extra CLI flags (e.g., `["--gtest_brief=1"]`) before any arguments passed after `--` on the `ctest` command line.
- **CLI Flags (CMake 4.4–4.5)**:
  - `--presets-file <file>` (4.4+): Selects an alternate preset file instead of `CMakePresets.json` / `CMakeUserPresets.json`. Mode flags (`--build`, `--workflow`, `--install`) must precede `--presets-file`.
  - `--list-presets=all-defined` (4.5+, alongside `defined` / `<type>-defined`): Lists unavailable presets and shows how a failed `configurePreset` condition disables dependent `buildPresets`, `testPresets`, and `workflowPresets`.

```json
{
  "version": 13,
  "cmakeMinimumRequired": {
    "major": 4,
    "minor": 5,
    "patch": 0
  },
  "configurePresets": [
    {
      "name": "base",
      "hidden": true,
      "generator": "Ninja",
      "binaryDir": "${sourceDir}/build/${presetName}",
      "warnings": {
        "author": true,
        "deprecated": true,
        "policy": true,
        "strict": true,
        "nonTargetDirective": true,
        "installAbsoluteDestination": true,
        "uninitialized": true,
        "unusedCli": true
      },
      "errors": {
        "deprecated": true,
        "nonTargetDirective": true
      },
      "cacheVariables": {
        "CMAKE_EXPORT_COMPILE_COMMANDS": "ON",
        "CMAKE_CXX_SCAN_FOR_MODULES": "OFF",
        "CMAKE_VERIFY_INTERFACE_HEADER_SETS": "ON"
      }
    },
    {
      "name": "pixi-base",
      "hidden": true,
      "inherits": "base",
      "condition": {
        "type": "notEquals",
        "lhs": "$env{CONDA_PREFIX}",
        "rhs": ""
      },
      "cacheVariables": {
        "CMAKE_C_COMPILER": "clang",
        "CMAKE_CXX_COMPILER": "clang++",
        "CMAKE_PREFIX_PATH": "$env{CONDA_PREFIX}"
      }
    },
    {
      "name": "ci-debug",
      "inherits": "pixi-base",
      "displayName": "CI Debug (ASan + UBSan)",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Debug",
        "ENABLE_SANITIZER_ADDRESS": "ON",
        "ENABLE_SANITIZER_UNDEFINED": "ON",
        "BUILD_TESTING": "ON",
        "WARNINGS_AS_ERRORS": "ON"
      }
    },
    {
      "name": "sysroot-release",
      "inherits": "base",
      "displayName": "Air-Gapped Sysroot Release",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Release",
        "ENABLE_IPO": "ON",
        "BUILD_TESTING": "OFF"
      }
    },
    {
      "name": "cross-riscv64",
      "inherits": "pixi-base",
      "displayName": "Cross RISC-V RVA23",
      "toolchainFile": "${fileDir}/cmake/toolchains/riscv64-linux-gnu.cmake",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Release",
        "BUILD_TESTING": "ON"
      }
    }
  ],
  "buildPresets": [
    {
      "name": "ci-debug",
      "configurePreset": "ci-debug",
      "displayName": "Build CI Debug"
    },
    {
      "name": "sysroot-release",
      "configurePreset": "sysroot-release",
      "displayName": "Build Air-Gapped Sysroot Release"
    },
    {
      "name": "cross-riscv64",
      "configurePreset": "cross-riscv64",
      "displayName": "Build Cross RISC-V RVA23"
    }
  ],
  "testPresets": [
    {
      "name": "ci-debug",
      "configurePreset": "ci-debug",
      "displayName": "Test CI Debug",
      "environment": {
        "LLVM_PROFILE_FILE": "${sourceDir}/build/${configurePresetName}/coverage/default-%p.profraw"
      },
      "output": {
        "outputOnFailure": true
      },
      "execution": {
        "noTestsAction": "error",
        "stopOnFailure": false,
        "testPassthroughArguments": ["--gtest_brief=1"]
      }
    }
  ],
  "workflowPresets": [
    {
      "name": "ci-debug",
      "displayName": "CI Debug Workflow",
      "steps": [
        { "type": "configure", "name": "ci-debug" },
        { "type": "build", "name": "ci-debug" },
        { "type": "test", "name": "ci-debug" }
      ]
    }
  ]
}
```

---

## 2. Hermetic `pixi 0.84.2+` & Platform-Native Stdlib ABI

Manage compilers, CMake 4.5+, build tools, and C/C++ libraries via **`pixi`** (`requires-pixi = ">=0.84.2"`) and `conda-forge`:

```toml
[workspace]
name = "modern-cmake-project"
version = "0.1.0"
requires-pixi = ">=0.84.2"
channels = ["conda-forge"]
platforms = ["linux-64", "linux-aarch64", "osx-arm64"]

[dependencies]
cmake = ">=4.5.0"
ninja = ">=1.12.0"
clangxx = ">=23.1.5"
clang-tools = ">=23.1.5"
lld = ">=23.1.5"
ccache = ">=4.10.0"
libabseil = ">=20260817.0"
gtest = ">=1.18.0"
benchmark = ">=1.10.0"
gersemi = ">=0.19.2"
pre-commit = ">=4.6.0"

[target.linux-64.dependencies]
# Retain native Linux libstdc++ ABI used by conda-forge C++ libraries.

[target.linux-aarch64.dependencies]
# Retain native Linux aarch64 libstdc++ ABI (e.g., NVIDIA IGX Thor / Orin).

[target.osx-arm64.dependencies]
# Retain native macOS libc++ ABI.
libcxx = ">=23.1.5"
```

### Critical `pixi` + `CMakePresets.json` Rules

1. **`libabseil` vs. `abseil-cpp` on `conda-forge`**: Use **`libabseil >= 20260817.0`** (`include/` + `lib/cmake/absl/abslConfig.cmake`). The legacy `abseil-cpp` package on `conda-forge` stops at `20220623.0` and fails `pixi lock` for `>= 20260817.0`.
2. **Explicit `clang` / `clang++` in `pixi-base`**: `conda-forge` `clangxx` installs compiler `.cfg` files rather than exporting `CC` / `CXX` in `activate.d` on Linux. Setting `"CMAKE_C_COMPILER": "clang"` and `"CMAKE_CXX_COMPILER": "clang++"` inside `pixi-base` prevents CMake from falling back to host `g++`.
3. **Platform-Native Stdlib ABI (aligned with `/cpp-pro` & `/python-pro`)**:
   - **Linux (`linux-64`, `linux-aarch64`)**: Link against **`libstdc++`** (`conda-forge` `clangxx` pairs with `libstdcxx-devel_linux-*` and `libstdcxx >= 15`). Never force `-stdlib=libc++` on Linux when linking `conda-forge` packages.
   - **macOS (`osx-arm64`)**: Link against **`libc++`** (`libcxx >= 23.1.5`).
4. **`ci-debug` Parity Across All 4 Preset Arrays**: Define `ci-debug` in `configurePresets`, `buildPresets`, `testPresets`, and `workflowPresets` with `"binaryDir": "${sourceDir}/build/${presetName}"` so `build/ci-debug/compile_commands.json` matches `/cpp-pro` `.pre-commit-config.yaml` (`clang-tidy -p build/ci-debug --warnings-as-errors=*`).
5. **`CMAKE_SYSTEM_ENVIRONMENT_ID` Pitfall**: Setting `CMAKE_SYSTEM_ENVIRONMENT_ID` inside a preset's `"environment"` block is ignored by CMake (and skipped for `project(... NONE)`). Export it under `[activation.env]` in `pixi.toml` if pairing with `CMAKE_SYSTEM_ENVIRONMENT_ACTION=REFRESH`.

---

## 3. Air-Gapped & Bare-Metal SDKs (`sysroot-release`)

In air-gapped networks or bare-metal firmware environments without `pixi`, **`sysroot-release` must inherit `base`—never `pixi-base`**:

- When `$env{CONDA_PREFIX}` is empty, `pixi-base` and all presets inheriting it are marked unavailable, while `sysroot-release` remains active in `cmake --list-presets=all-defined`.
- `sysroot-release` omits `$env{CONDA_PREFIX}` and resolves pre-installed libraries via `find_package(<Pkg> CONFIG REQUIRED)` against system paths or a vendor `CMAKE_SYSROOT` / `CMAKE_PREFIX_PATH` passed via CLI or a local `CMakeUserPresets.json`.

---

## 4. Cross-Compilation Toolchains (AArch64 & RISC-V RVA23)

Always follow these `cmake-toolchains(7)` invariants:

- Resolve relative paths inside toolchain files with **`${CMAKE_CURRENT_LIST_DIR}`**—never `CMAKE_SOURCE_DIR` or `CMAKE_BINARY_DIR` (toolchains run inside `try_compile()` sub-projects).
- Use `CMAKE_STAGING_PREFIX` for staging cross-installed artifacts locally while keeping `CMAKE_INSTALL_PREFIX` as the target device runtime path.
- Enforce `CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER` and `CMAKE_FIND_ROOT_PATH_MODE_{LIBRARY,INCLUDE,PACKAGE} ONLY` so host `$CONDA_PREFIX` headers and libraries never leak into target sysroot lookups.
- Set `CMAKE_<LANG>_LINK_FLAGS` (CMake 4.3+, policy `CMP0210` `NEW`) to apply language-specific linker flags across executables, shared libraries, and module libraries.
- For bare-metal targets lacking a hosted `libc` at configure time, set `set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)`.

On `conda-forge`, cross toolchains and user-mode emulators are available via `clangxx_linux-aarch64 >= 23.1`, `clangxx_linux-riscv64 >= 23.1`, `qemu-execve-aarch64`, and `qemu-execve-riscv64`.

### `cmake/toolchains/aarch64-linux-gnu.cmake` (NVIDIA IGX Thor / Orin)

```cmake
# cmake/toolchains/aarch64-linux-gnu.cmake

if(POLICY CMP0210)
    cmake_policy(SET CMP0210 NEW)
endif()

set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)

set(CMAKE_C_COMPILER clang)
set(CMAKE_CXX_COMPILER clang++)
set(CMAKE_C_COMPILER_TARGET aarch64-linux-gnu)
set(CMAKE_CXX_COMPILER_TARGET aarch64-linux-gnu)

if(DEFINED ENV{SYSROOT_AARCH64})
    set(CMAKE_SYSROOT "$ENV{SYSROOT_AARCH64}")
    set(CMAKE_FIND_ROOT_PATH "$ENV{SYSROOT_AARCH64}")
endif()

if(DEFINED ENV{STAGING_PREFIX_AARCH64})
    set(CMAKE_STAGING_PREFIX "$ENV{STAGING_PREFIX_AARCH64}")
endif()

if(EXISTS "${CMAKE_CURRENT_LIST_DIR}/aarch64-extra.cmake")
    include("${CMAKE_CURRENT_LIST_DIR}/aarch64-extra.cmake")
endif()

set(CMAKE_CXX_LINK_FLAGS "-fuse-ld=lld")

find_program(_qemu_aarch64 NAMES qemu-aarch64 qemu-execve-aarch64)
if(_qemu_aarch64)
    if(DEFINED ENV{SYSROOT_AARCH64})
        set(CMAKE_CROSSCOMPILING_EMULATOR "${_qemu_aarch64};-L;$ENV{SYSROOT_AARCH64}")
    else()
        set(CMAKE_CROSSCOMPILING_EMULATOR "${_qemu_aarch64}")
    endif()
endif()

set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
```

### `cmake/toolchains/riscv64-linux-gnu.cmake` (RISC-V RVA23 + QEMU)

```cmake
# cmake/toolchains/riscv64-linux-gnu.cmake

if(POLICY CMP0210)
    cmake_policy(SET CMP0210 NEW)
endif()

set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR riscv64)

set(CMAKE_C_COMPILER clang)
set(CMAKE_CXX_COMPILER clang++)
set(CMAKE_C_COMPILER_TARGET riscv64-linux-gnu)
set(CMAKE_CXX_COMPILER_TARGET riscv64-linux-gnu)

set(CMAKE_C_FLAGS_INIT "-march=rva23u64")
set(CMAKE_CXX_FLAGS_INIT "-march=rva23u64")

if(DEFINED ENV{SYSROOT_RISCV64})
    set(CMAKE_SYSROOT "$ENV{SYSROOT_RISCV64}")
    set(CMAKE_FIND_ROOT_PATH "$ENV{SYSROOT_RISCV64}")
endif()

if(DEFINED ENV{STAGING_PREFIX_RISCV64})
    set(CMAKE_STAGING_PREFIX "$ENV{STAGING_PREFIX_RISCV64}")
endif()

set(CMAKE_C_LINK_FLAGS "-fuse-ld=lld")
set(CMAKE_CXX_LINK_FLAGS "-fuse-ld=lld")

find_program(_qemu_riscv64 NAMES qemu-riscv64 qemu-execve-riscv64)
if(_qemu_riscv64)
    if(DEFINED ENV{SYSROOT_RISCV64})
        set(CMAKE_CROSSCOMPILING_EMULATOR "${_qemu_riscv64};-L;$ENV{SYSROOT_RISCV64}")
    else()
        set(CMAKE_CROSSCOMPILING_EMULATOR "${_qemu_riscv64}")
    endif()
endif()

set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
```

---

## 5. CMake 4.3–4.5 Build Instrumentation & Introspection

### `cmake_instrumentation()` (API v1 / Data v1.2)

Available on `Ninja`, `Ninja Multi-Config`, `Unix Makefiles`, and `FASTBuild` generators. Data v1.2 adds `processMetrics` (`maxRSS` KiB, `userTime`, `systemTime`) and `interruptSignal`, while `compileTrace` captures Clang `-ftime-trace` profiles and `trace` keeps Google Trace Event JSON in `<build>/.cmake/instrumentation/v1/data/trace/`.

```cmake
# Gate build instrumentation via preset or CLI so default builds stay lightweight
option(ENABLE_BUILD_INSTRUMENTATION "Enable CMake build telemetry and Chrome trace export" OFF)
if(ENABLE_BUILD_INSTRUMENTATION)
    cmake_instrumentation(
        API_VERSION 1
        DATA_VERSION 1.2
        HOOKS postGenerate postCMakeBuild postCMakeInstall postCMakeWorkflow postCTest
        OPTIONS
            staticSystemInformation
            dynamicSystemInformation
            captureOutput
            compileTrace
            processMetrics
            trace
        CUSTOM_CONTENT project_preset STRING "${CMAKE_BUILD_TYPE}"
    )
endif()
```

Collect and inspect CTest instrumentation data in CI with `ctest --collect-instrumentation <build-dir>` or set `CTEST_USE_INSTRUMENTATION=1` in the environment.

### `cmake_language(PRINT_*)` Debugging (CMake 4.5)

CMake 4.5 replaces legacy `CMakePrintHelpers` (`cmake_print_properties` / `cmake_print_variables`) with native `cmake_language()` subcommands supporting `REGEX` filtering, `DEFERRED` generation-time evaluation, and transitive `FOLLOW_DEPENDENCIES` walks:

```cmake
# Inspect non-imported targets and cache variables matching a prefix
cmake_language(PRINT_TARGETS REGEX "^halos_" NO_IMPORTED)
cmake_language(PRINT_VARIABLES ALL NAME_REGEX "^(ENABLE_|CMAKE_LINKER_TYPE)")

# Print final target properties at generation time across all reachable link dependencies
# gersemi: off
cmake_language(
    PRINT_PROPERTIES
    TARGETS halos_core
    FOLLOW_DEPENDENCIES
    NAMED LINK_LIBRARIES INTERFACE_INCLUDE_DIRECTORIES CXX_SCAN_FOR_MODULES
)
# gersemi: on
```
