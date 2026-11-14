# File Sets, CPS Packaging, SPDX 3.0.1 SBOM & Cross-Language Interop

Reference guide for CMake 4.4–4.5+ `FILE_SET` management, header verification, `ALIAS` target parity, GA Common Package Specification (`CPS`), GA SPDX 3.0.1 JSON-LD `SBOM` generation, and multi-language interop aligned with `/c-pro`, `/cpp-pro`, `/rust-pro`, `/ada-spark-pro`, and `/python-pro`.

---

## 1. File Sets, Header Verification & CMake 4.5 `ALIAS` Parity

### 1.1 `FILE_SET HEADERS` & `FILE_SET TYPE SOURCES` (CMake 4.4–4.5)

Use `FILE_SET HEADERS` for public/interface headers (`CMP0154` requires generated public headers to live in a `PUBLIC` or `INTERFACE` `FILE_SET HEADERS`) and CMake 4.4+ `FILE_SET TYPE SOURCES` for compilation units (`CMP0211` restricts each source file to at most one non-`HEADERS` file set per target). Always use `TARGET <tgt>`—not `TYPE`—in `set_property(FILE_SET ...)`.

```cmake
add_library(halos_core STATIC)
add_library(Halos::Core ALIAS halos_core)

target_sources(
    halos_core
    PUBLIC FILE_SET HEADERS BASE_DIRS include FILES include/halos/core/gate.hpp
    PRIVATE
        FILE_SET generated_sources
            TYPE SOURCES
            BASE_DIRS "${CMAKE_CURRENT_BINARY_DIR}/generated"
            FILES "${CMAKE_CURRENT_BINARY_DIR}/generated/lut_tables.cpp"
    PRIVATE FILE_SET sources TYPE SOURCES FILES src/gate.cpp
)

# File-set properties (note TARGET keyword in set_property)
set_property(FILE_SET generated_sources TARGET halos_core PROPERTY SKIP_LINTING ON)
set_property(FILE_SET generated_sources TARGET halos_core PROPERTY SKIP_PRECOMPILE_HEADERS ON)
set_property(FILE_SET generated_sources TARGET halos_core PROPERTY SKIP_UNITY_BUILD_INCLUSION ON)
set_property(FILE_SET generated_sources TARGET halos_core PROPERTY INDEPENDENT_FILES ON)
set_property(FILE_SET sources TARGET halos_core PROPERTY CXX_SCAN_FOR_MODULES OFF)
```

- **`SKIP_LINTING`**: Suppresses `*_CLANG_TIDY`, `*_CPPLINT`, `*_CPPCHECK`, `*_INCLUDE_WHAT_YOU_USE`, and `VERIFY_*_HEADER_SETS` on generated/third-party file sets (file-set property overrides source and target properties).
- **`INDEPENDENT_FILES`**: Requires `CMP0154=NEW`; lets Ninja skip order-only custom-command dependencies for independent generated sources (default `ON` for `CXX_MODULES`, `OFF` for `SOURCES`; never set `ON` on `HEADERS`).
- **`JOB_POOL_COMPILE` & `SOURCE_GROUP` (4.5)**: Set per-file-set Ninja compile pools (backed by global `JOB_POOLS`) and IDE folder grouping without splitting targets.

### 1.2 Header Verification (`CMAKE_VERIFY_*_HEADER_SETS`)

Keep `CMAKE_VERIFY_INTERFACE_HEADER_SETS` and `CMAKE_VERIFY_PRIVATE_HEADER_SETS` as preset/CLI/CI controls rather than hardcoding `ON` in `CMakeLists.txt`. In CMake 4.4+, targets always emit `<tgt>_verify_interface_header_sets`, `<tgt>_verify_private_header_sets`, and aggregate `all_verify_{interface,private,}_header_sets` targets for `C`/`CXX`/`OBJC`/`OBJCXX` (`CMP0209` verifies executables without `ENABLE_EXPORTS`). Filter specific sets via `INTERFACE_HEADER_SETS_TO_VERIFY` / `PRIVATE_HEADER_SETS_TO_VERIFY`, and temporarily disable verification if invoking `add_subdirectory()` on a vendored submodule:

```cmake
block(SCOPE_FOR VARIABLES)
    set(CMAKE_VERIFY_INTERFACE_HEADER_SETS OFF)
    set(CMAKE_VERIFY_PRIVATE_HEADER_SETS OFF)
    add_subdirectory(third_party/vendor_sdk EXCLUDE_FROM_ALL)
endblock()
```

### 1.3 CMake 4.5 `ALIAS` Target Parity

CMake 4.5 allows passing `ALIAS` targets directly to `target_*()`, `add_dependencies()`, `set_property()`, `set_target_properties()`, `install()`, and `export()` (`ALIASED_TARGET` remains read-only):

```cmake
set_target_properties(Halos::Core PROPERTIES EXPORT_NAME Core SPDX_LICENSE "Apache-2.0")
install(TARGETS Halos::Core EXPORT HalosTargets FILE_SET HEADERS)
```

---

## 2. Common Package Specification (CPS) & Config-File Dual Support

CMake 4.3–4.5 makes CPS (`PACKAGE_INFO`) **GA** with zero experimental feature gates—CMake 4.5 also adds header `FILE_SET` preservation in `find_package()` + `PACKAGE_INFO` and CPS `executable` components:

```cmake
project(HalosCore VERSION 1.2.0 COMPAT_VERSION 1.2.0 SPDX_LICENSE "Apache-2.0" LANGUAGES CXX C)

# Install CPS descriptor (<prefix>/lib/cps/haloscore/haloscore.cps + @<config>.cps)
# Note: DEFAULT_TARGETS takes the exported name (matching EXPORT_NAME), without Namespace::
install(PACKAGE_INFO HalosCore EXPORT HalosTargets LOWER_CASE_FILE DEFAULT_TARGETS Core)

# Optional build-tree CPS export (<build>/cps/HalosCore/haloscore.cps)
export(PACKAGE_INFO HalosCore EXPORT HalosTargets LOWER_CASE_FILE)
```

- **`project(... COMPAT_VERSION ... SPDX_LICENSE ...)`**: `COMPAT_VERSION` requires `VERSION` and sets `PROJECT_COMPAT_VERSION`. `SPDX_LICENSE` populates `PROJECT_SPDX_LICENSE`, not individual target `SPDX_LICENSE` properties.
- **`APPENDIX`**: Use `install(PACKAGE_INFO HalosCore APPENDIX Extra EXPORT ExtraTargets)` to extend an existing CPS package (forbids `PROJECT`, `VERSION`, `COMPAT_VERSION`, `VERSION_SCHEMA`, `DEFAULT_TARGETS`, `DEFAULT_CONFIGURATIONS`).
- **`find_package()` Resolution Order**: CMake searches `<PackageName>.cps`, `<lowercase>.cps`, `<lowercase>-config.cmake`, and `<PackageName>Config.cmake` inside `cps/<name>/` (or Apple `Resources/CPS/`), preferring `.cps` unless `CONFIGS` is passed, and enforces `compat_version <= requested_min <= version`.

### Legacy `CMakePackageConfigHelpers` Dual Export

Emit standard CMake config scripts alongside `PACKAGE_INFO` when downstream consumers still filter with `CONFIGS`:

```cmake
include(CMakePackageConfigHelpers)

install(EXPORT HalosTargets NAMESPACE Halos:: DESTINATION "${CMAKE_INSTALL_LIBDIR}/cmake/HalosCore")

configure_package_config_file(
    cmake/HalosCoreConfig.cmake.in
    "${CMAKE_CURRENT_BINARY_DIR}/HalosCoreConfig.cmake"
    INSTALL_DESTINATION "${CMAKE_INSTALL_LIBDIR}/cmake/HalosCore"
)
write_basic_package_version_file(
    "${CMAKE_CURRENT_BINARY_DIR}/HalosCoreConfigVersion.cmake"
    COMPATIBILITY SameMajorVersion
)
install(
    FILES
        "${CMAKE_CURRENT_BINARY_DIR}/HalosCoreConfig.cmake"
        "${CMAKE_CURRENT_BINARY_DIR}/HalosCoreConfigVersion.cmake"
    DESTINATION "${CMAKE_INSTALL_LIBDIR}/cmake/HalosCore"
)
```

---

## 3. Native SPDX 3.0.1 JSON-LD SBOM Generation (CMake 4.5 GA)

CMake 4.5 graduates native SPDX 3.0.1 JSON-LD SBOM generation to GA (`install(SBOM ...)` and `export(SBOM ...)` take **plural `EXPORTS`**; `install(PACKAGE_INFO ...)` takes **singular `EXPORT`**).

```cmake
# Wrap install(SBOM ...) in gersemi guards because gersemi 0.29.2 still carries older SBOM keywords
# gersemi: off
install(
    SBOM HalosCore
    EXPORTS HalosTargets
    FORMAT spdx-3.0.1+json
    DATA_LICENSE "CC0-1.0"
    DEFAULT_LICENSE "Apache-2.0"
    PACKAGE_URL "pkg:generic/halos-core@1.2.0"
)
# gersemi: on

# Optional build-tree SBOM (<build>/sbom/HalosCore)
# gersemi: off
export(
    SBOM HalosCore
    EXPORTS HalosTargets
    FORMAT spdx-3.0.1+json
    DATA_LICENSE "CC0-1.0"
    DEFAULT_LICENSE "Apache-2.0"
)
# gersemi: on
```

- **Preset/CLI Auto-Emission (`CMAKE_INSTALL_SBOM_FORMATS`)**: Set `"CMAKE_INSTALL_SBOM_FORMATS": "spdx-3.0.1+json"` in release presets (e.g., `dev-release`) to auto-generate SPDX 3.0.1 SBOMs under `<libdir>/sbom/<export>/` for any export not covered by an explicit `install(SBOM ...)`.
- **`$<LINK_ONLY:...>` Gotcha**: `install(SBOM ...)` and `export(SBOM ...)` evaluate `LINK_LIBRARIES` and `INTERFACE_LINK_LIBRARIES` cleanly across targets, **but fail on generator expressions unless wrapped in `$<LINK_ONLY:...>`** (e.g., `$<LINK_ONLY:$<$<PLATFORM_ID:Linux>:rt>>`).
- **Component Licenses**: Set `SPDX_LICENSE` on each target (`set_target_properties(... PROPERTIES SPDX_LICENSE "MIT")`) or supply `DEFAULT_LICENSE` at the SBOM call site.

---

## 4. Multi-Language CMake 4.5 Interop Recipes

### 4.1 ISO C23 (`/c-pro`)

Enforce pure ISO C23, probe `<stdbit.h>` (present on Linux `glibc 2.39+` / LLVM Clang 23, missing in macOS Apple Clang 21 SDKs so headers fall back to compiler builtins), and enable deterministic stack zero-init hardening on C targets:

```cmake
set(CMAKE_C_STANDARD 23)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

include(CheckIncludeFile)
check_include_file("stdbit.h" HAVE_STDBIT_H)

add_library(halos_c_kernel STATIC)
target_sources(
    halos_c_kernel
    PUBLIC FILE_SET HEADERS BASE_DIRS include FILES include/halos/c_gate.h
    PRIVATE FILE_SET sources TYPE SOURCES FILES src/c_gate.c
)
target_compile_definitions(halos_c_kernel PUBLIC $<$<BOOL:${HAVE_STDBIT_H}>:HAVE_STDBIT_H=1>)
target_compile_options(halos_c_kernel PRIVATE $<$<COMPILE_LANGUAGE:C>:-ftrivial-auto-var-init=zero>)
target_link_libraries(halos_c_kernel PRIVATE project_options project_warnings project_architecture)
```

Keep C/C++ boundary headers valid in both languages (`#pragma once`, `#include <stdint.h>`, `#ifdef __cplusplus extern "C" { #endif`, and `static_assert` layout verification). Wrap C out-pointer APIs in C++23 with `std::out_ptr` and `std::expected` per `/cpp-pro`.

### 4.2 Rust 1.99.1+ (`Cargo` + `Corrosion` + `Crubit`) (`/rust-pro`)

Native `CMAKE_EXPERIMENTAL_RUST` remains experimental in CMake 4.5. For production Linux/macOS/RISC-V builds (`x86_64-unknown-linux-gnu`, `aarch64-unknown-linux-gnu`, `aarch64-apple-darwin`, `riscv64a23-unknown-linux-gnu`), build Rust `edition = "2024"` (`#![no_std]`-capable) crates via **Corrosion** (pre-installed via `pixi` or vendored submodule—never `FetchContent`), and pair with **Crubit** (`cpp_api_from_rust`) for zero-copy C++-to-Rust bindings:

```cmake
# Prefer pre-installed or vendored Corrosion (zero FetchContent)
find_package(Corrosion CONFIG REQUIRED)
corrosion_import_crate(MANIFEST_PATH "${CMAKE_CURRENT_SOURCE_DIR}/rust/Cargo.toml")

# Option A: Crubit cpp_api_from_rust (C++23 -> Rust, requires matching toolchain/rustc-dev)
find_program(CRUBIT_CPP_API_FROM_RUST cc_bindings_from_rs)
if(CRUBIT_CPP_API_FROM_RUST)
    set(CRUBIT_GEN_HDR "${CMAKE_CURRENT_BINARY_DIR}/generated/halos_kinematics_rs_api.h")
    add_custom_command(
        OUTPUT "${CRUBIT_GEN_HDR}"
        COMMAND
            "${CRUBIT_CPP_API_FROM_RUST}" --h-out="${CRUBIT_GEN_HDR}"
            "${CMAKE_CURRENT_SOURCE_DIR}/rust/src/lib.rs" -- --crate-type=rlib --edition=2024
        DEPENDS rust/src/lib.rs
        COMMENT "Generating zero-copy Crubit C++23 bindings for Rust crate"
        VERBATIM
    )
    add_custom_target(halos_crubit_bindings DEPENDS "${CRUBIT_GEN_HDR}")
    add_dependencies(halos_core halos_crubit_bindings)
endif()

# Option B (Rust -> C++ fallback until CMake rust_api_from_cpp lands):
# Expose #[repr(C)] #[unsafe(no_mangle)] pub unsafe extern "C" fn symbols or cxx bridge,
# then link the imported Rust staticlib target directly:
target_link_libraries(halos_core PRIVATE halos_kinematics)
```

### 4.3 SPARK Ada 2022 (`cmake/SparkTargets.cmake`) (`/ada-spark-pro`)

Package formally verified SPARK Ada 2022 safety kernels (`alr 2.1.1+`, `gnat_native=16.1.0`, `gnatprove=16.1.0`) as an encapsulated Stand-Alone static library (`Library_Auto_Init "True"`, `Library_Standalone "encapsulated"` in `.gpr`), then wrap `gnatprove` + `alr build` and use CMake 4.5 `install(... BUILD_DEPENDS ...)` to guarantee install-time verification:

```cmake
# cmake/SparkTargets.cmake
find_program(ALR_EXECUTABLE alr REQUIRED)

set(SPARK_CRATE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/spark_safety_core")
set(SPARK_STATIC_LIB "${SPARK_CRATE_DIR}/lib/libhalos_spark_safety.a")

add_custom_command(
    OUTPUT "${SPARK_STATIC_LIB}"
    COMMAND "${ALR_EXECUTABLE}" -n gnatprove --level=2 --warnings=error -j0
    COMMAND "${ALR_EXECUTABLE}" -n build --release
    WORKING_DIRECTORY "${SPARK_CRATE_DIR}"
    COMMENT "Verifying SPARK contracts (gnatprove) and building encapsulated static library"
    VERBATIM
)

add_custom_target(spark_safety_build DEPENDS "${SPARK_STATIC_LIB}")

add_library(Halos::SparkSafety STATIC IMPORTED GLOBAL)
add_dependencies(Halos::SparkSafety spark_safety_build)
set_target_properties(
    Halos::SparkSafety
    PROPERTIES
        IMPORTED_LOCATION "${SPARK_STATIC_LIB}"
        INTERFACE_INCLUDE_DIRECTORIES "${SPARK_CRATE_DIR}/include"
)

# CMake 4.5 BUILD_DEPENDS ensures install rules trigger spark_safety_build first
install(FILES "${SPARK_STATIC_LIB}" TYPE LIB BUILD_DEPENDS spark_safety_build)
install(DIRECTORY "${SPARK_CRATE_DIR}/include/" TYPE INCLUDE BUILD_DEPENDS spark_safety_build)
```

### 4.4 Python 3.14.7 + `nanobind` under `pixi` (`/python-pro`)

Use `FindPython` inside an active `pixi` environment to resolve `nanobind`'s CMake package directory and compile zero-copy `nb::ndarray` extension modules. In CMake 4.5, `install(TARGETS)` no longer requires `LIBRARY DESTINATION` for `MODULE` libraries (or target `${Python_SITEARCH}` explicitly for Python packages):

```cmake
find_package(Python 3.14 COMPONENTS Interpreter Development.Module REQUIRED)

execute_process(
    COMMAND "${Python_EXECUTABLE}" -m nanobind --cmake_dir
    OUTPUT_VARIABLE nanobind_ROOT
    OUTPUT_STRIP_TRAILING_WHITESPACE
    COMMAND_ERROR_IS_FATAL ANY
)
find_package(nanobind CONFIG REQUIRED)

nanobind_add_module(_halos_py STABLE_ABI NB_DOMAIN halos src/python_bindings.cpp)
target_link_libraries(_halos_py PRIVATE Halos::Core project_options project_warnings)

# CMake 4.5 allows omitting LIBRARY DESTINATION for MODULE libraries (or pass Python_SITEARCH)
install(TARGETS _halos_py DESTINATION "${Python_SITEARCH}")
```
