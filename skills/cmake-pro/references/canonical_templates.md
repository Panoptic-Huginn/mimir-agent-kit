# Canonical CMake 4.5+ Modular Templates

Copy-ready `cmake/` modules for Modern CMake 4.5+ (`cmake_minimum_required(VERSION 4.5)`) on Linux (`linux-64`, `linux-aarch64`, `riscv64` RVA23) and macOS (`osx-arm64`) using LLVM/Clang 23.1.5+ and GCC 15+. All CMake snippets follow `gersemi` formatting (`line_length: 100`, `indent: 4`, `list_expansion: favour-inlining`).

---

## 1. `cmake/ProjectOptions.cmake`

Encapsulates project-wide build options, `ccache` compiler launchers, `clang-tidy` wiring, validated `CMAKE_LINKER_TYPE` selection (`LLD`, `MOLD`, `WILD`), IPO/LTO checks, C++-guarded `-fno-exceptions -fno-rtti` defaults (matching `/cpp-pro`), and non-cache C++20/23 module scanning defaults.

```cmake
# cmake/ProjectOptions.cmake

add_library(project_options INTERFACE)
target_compile_features(project_options INTERFACE cxx_std_23)

set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib")
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib")

# Compiler launcher (ccache)
find_program(CCACHE_PROGRAM ccache)
if(CCACHE_PROGRAM)
    message(STATUS "Compiler launcher: ${CCACHE_PROGRAM}")
    set(CMAKE_C_COMPILER_LAUNCHER "${CCACHE_PROGRAM}")
    set(CMAKE_CXX_COMPILER_LAUNCHER "${CCACHE_PROGRAM}")
endif()

# Static analysis (clang-tidy)
option(ENABLE_CLANG_TIDY "Enable clang-tidy static analysis during compilation" OFF)
if(ENABLE_CLANG_TIDY)
    find_program(CLANG_TIDY_PROGRAM clang-tidy)
    if(CLANG_TIDY_PROGRAM)
        message(STATUS "clang-tidy enabled: ${CLANG_TIDY_PROGRAM}")
        set(CMAKE_C_CLANG_TIDY "${CLANG_TIDY_PROGRAM}")
        set(CMAKE_CXX_CLANG_TIDY "${CLANG_TIDY_PROGRAM}")
    else()
        message(WARNING "ENABLE_CLANG_TIDY is ON but clang-tidy was not found")
    endif()
endif()

# Validated linker selection (CMAKE_LINKER_TYPE also governs try_compile())
if(NOT DEFINED CMAKE_LINKER_TYPE)
    block(SCOPE_FOR VARIABLES POLICIES DIAGNOSTICS)
        include(CheckLinkerFlag)
        if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
            check_linker_flag(CXX "-fuse-ld=lld" _has_lld_linker)
            if(_has_lld_linker)
                set(CMAKE_LINKER_TYPE "LLD" CACHE STRING "CMake linker type")
            else()
                check_linker_flag(CXX "-fuse-ld=mold" _has_mold_linker)
                if(_has_mold_linker)
                    set(CMAKE_LINKER_TYPE "MOLD" CACHE STRING "CMake linker type")
                else()
                    if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
                        set(_wild_flag "--ld-path=wild")
                    else()
                        set(_wild_flag "-fuse-ld=wild")
                    endif()
                    check_linker_flag(CXX "${_wild_flag}" _has_wild_linker)
                    if(_has_wild_linker)
                        set(CMAKE_LINKER_TYPE "WILD" CACHE STRING "CMake linker type")
                    endif()
                endif()
            endif()
        elseif(APPLE)
            # Keep native ld_prime (SYSTEM) on macOS unless LLD/SOLD is explicitly chosen
            set(CMAKE_LINKER_TYPE "SYSTEM" CACHE STRING "CMake linker type")
        endif()
    endblock()
endif()

# Interprocedural Optimization (LTO)
option(ENABLE_IPO "Enable Interprocedural Optimization (LTO)" OFF)
if(ENABLE_IPO)
    include(CheckIPOSupported)
    check_ipo_supported(RESULT _ipo_supported OUTPUT _ipo_error)
    if(_ipo_supported)
        set(CMAKE_INTERPROCEDURAL_OPTIMIZATION ON)
        message(STATUS "IPO/LTO enabled")
    else()
        message(WARNING "IPO requested but unsupported: ${_ipo_error}")
    endif()
endif()

# Deterministic embedded/HFT defaults: guard C++-only flags so C23 targets stay clean
option(ENABLE_EXCEPTIONS "Enable C++ exceptions" OFF)
option(ENABLE_RTTI "Enable C++ RTTI" OFF)
if(NOT ENABLE_EXCEPTIONS)
    target_compile_options(project_options INTERFACE $<$<COMPILE_LANGUAGE:CXX>:-fno-exceptions>)
endif()
if(NOT ENABLE_RTTI)
    target_compile_options(project_options INTERFACE $<$<COMPILE_LANGUAGE:CXX>:-fno-rtti>)
endif()

# Disable C++20/23 module scanning by default (non-cache per cmake-cxxmodules(7))
option(ENABLE_CXX_MODULES "Enable C++20/23 module scanning and GA import std" OFF)
if(ENABLE_CXX_MODULES)
    set(CMAKE_CXX_SCAN_FOR_MODULES ON)
elseif(NOT DEFINED CMAKE_CXX_SCAN_FOR_MODULES)
    set(CMAKE_CXX_SCAN_FOR_MODULES OFF)
endif()
```

**CMake 4.5 GA `import std` Note:** CMake 4.5 graduates `import std` and `import std.compat` to GA and removes the experimental `CMAKE_EXPERIMENTAL_CXX_IMPORT_STD` UUIDs and `CXX_MODULE_STD` target property. When `ENABLE_CXX_MODULES` is `ON` under `Ninja` (`>= 1.11`) with Clang `>= 18.1.2` (`libc++` or `libstdc++`) or GCC `>= 15` (Linux) / `>= 16` (macOS), CMake automatically synthesizes `@cmake_cxx_std` for C++20+ targets. If the compiler cannot auto-locate `{libc++,libstdc++}.modules.json`, set `CMAKE_CXX_STDLIB_MODULES_JSON` in a preset or before `project()`.

---

## 2. `cmake/CompilerWarnings.cmake`

Provides strict C23 and C++23 warnings across Clang 23.1.5+, Apple Clang 21+, and GCC 15+. Language-specific flags use `$<$<COMPILE_LANGUAGE:...>:...>` so mixed C/C++ builds never leak C-only or C++-only flags across targets.

```cmake
# cmake/CompilerWarnings.cmake

add_library(project_warnings INTERFACE)

option(WARNINGS_AS_ERRORS "Treat compiler warnings as errors" ON)

set(_common_warnings
    -Wall
    -Wextra
    -Wpedantic
    -Wshadow
    -Wcast-align
    -Wcast-qual
    -Wunused
    -Wconversion
    -Wsign-conversion
    -Wnull-dereference
    -Wdouble-promotion
    -Wformat=2
    -Wformat-security
    -Wimplicit-fallthrough
    -Wundef
    -Wswitch-enum
)

set(_cxx_warnings -Wnon-virtual-dtor -Wold-style-cast -Woverloaded-virtual)

set(_c_warnings
    -Wstrict-prototypes
    -Wmissing-prototypes
    -Wmissing-declarations
    -Wold-style-definition
    -Wbad-function-cast
    -Wwrite-strings
    -Wvla
)

set(_gcc_common_warnings
    -Wmisleading-indentation
    -Wduplicated-cond
    -Wduplicated-branches
    -Wlogical-op
)

set(_gcc_cxx_warnings -Wuseless-cast -Wnrvo)

if(WARNINGS_AS_ERRORS)
    list(APPEND _common_warnings -Werror)
endif()

foreach(_lang IN ITEMS C CXX)
    if(
        DEFINED CMAKE_${_lang}_COMPILER_ID
        AND NOT CMAKE_${_lang}_COMPILER_ID MATCHES "^(Clang|AppleClang|GNU)$"
    )
        message(FATAL_ERROR "Unsupported ${_lang} compiler: ${CMAKE_${_lang}_COMPILER_ID}")
    endif()
endforeach()

target_compile_options(
    project_warnings
    INTERFACE
        ${_common_warnings}
        $<$<COMPILE_LANGUAGE:C>:${_c_warnings}>
        $<$<COMPILE_LANGUAGE:CXX>:${_cxx_warnings}>
        $<$<AND:$<COMPILE_LANGUAGE:C>,$<C_COMPILER_ID:GNU>>:${_gcc_common_warnings}>
        $<$<AND:$<COMPILE_LANGUAGE:CXX>,$<CXX_COMPILER_ID:GNU>>:${_gcc_common_warnings};${_gcc_cxx_warnings}>
)
```

---

## 3. `cmake/Sanitizers.cmake`

Wraps sanitizer conflict validation and compile/link probing in `block(SCOPE_FOR VARIABLES POLICIES DIAGNOSTICS)` and `cmake_push_check_state()` so helper state never escapes to parent scopes. Note that `CMAKE_REQUIRED_FLAGS` takes a space-joined string while `CMAKE_REQUIRED_LINK_OPTIONS` takes a CMake list.

```cmake
# cmake/Sanitizers.cmake

add_library(project_sanitizers INTERFACE)

option(ENABLE_SANITIZER_ADDRESS "Enable AddressSanitizer (ASan)" OFF)
option(ENABLE_SANITIZER_UNDEFINED "Enable UndefinedBehaviorSanitizer (UBSan)" OFF)
option(ENABLE_SANITIZER_THREAD "Enable ThreadSanitizer (TSan)" OFF)
option(ENABLE_SANITIZER_MEMORY "Enable MemorySanitizer (MSan, Clang + Linux only)" OFF)
option(ENABLE_SANITIZER_LEAK "Enable LeakSanitizer (LSan)" OFF)

block(SCOPE_FOR VARIABLES POLICIES DIAGNOSTICS)
    include(CheckCXXSourceCompiles)
    include(CMakePushCheckState)

    if(
        ENABLE_SANITIZER_THREAD
        AND (ENABLE_SANITIZER_ADDRESS OR ENABLE_SANITIZER_MEMORY OR ENABLE_SANITIZER_LEAK)
    )
        message(FATAL_ERROR "TSan cannot be combined with ASan, MSan, or LSan")
    endif()

    if(
        ENABLE_SANITIZER_MEMORY
        AND (ENABLE_SANITIZER_ADDRESS OR ENABLE_SANITIZER_THREAD OR ENABLE_SANITIZER_LEAK)
    )
        message(FATAL_ERROR "MSan cannot be combined with ASan, TSan, or LSan")
    endif()

    if(ENABLE_SANITIZER_LEAK AND ENABLE_SANITIZER_ADDRESS)
        message(
            FATAL_ERROR
            "ASan already includes LSan on Linux/macOS; disable ENABLE_SANITIZER_LEAK"
        )
    endif()

    if(
        ENABLE_SANITIZER_MEMORY
        AND (NOT CMAKE_SYSTEM_NAME STREQUAL "Linux" OR NOT CMAKE_CXX_COMPILER_ID MATCHES "Clang")
    )
        message(FATAL_ERROR "MemorySanitizer requires LLVM Clang on Linux")
    endif()

    set(_sanitizer_flags "")
    if(ENABLE_SANITIZER_ADDRESS)
        list(APPEND _sanitizer_flags "-fsanitize=address" "-fno-omit-frame-pointer")
    endif()
    if(ENABLE_SANITIZER_UNDEFINED)
        list(APPEND _sanitizer_flags "-fsanitize=undefined" "-fno-sanitize-recover=all")
    endif()
    if(ENABLE_SANITIZER_THREAD)
        list(APPEND _sanitizer_flags "-fsanitize=thread")
    endif()
    if(ENABLE_SANITIZER_MEMORY)
        list(
            APPEND _sanitizer_flags
            "-fsanitize=memory"
            "-fsanitize-memory-track-origins=2"
            "-fno-omit-frame-pointer"
        )
    endif()
    if(ENABLE_SANITIZER_LEAK)
        list(APPEND _sanitizer_flags "-fsanitize=leak")
    endif()

    if(_sanitizer_flags)
        string(JOIN " " _sanitizer_flags_str ${_sanitizer_flags})
        cmake_push_check_state(RESET)
        set(CMAKE_REQUIRED_FLAGS "${_sanitizer_flags_str}")
        set(CMAKE_REQUIRED_LINK_OPTIONS "${_sanitizer_flags}")
        check_cxx_source_compiles("int main() { return 0; }" _compiler_supports_sanitizers)
        cmake_pop_check_state()

        if(NOT _compiler_supports_sanitizers)
            message(FATAL_ERROR "Requested sanitizers unsupported: ${_sanitizer_flags_str}")
        endif()

        target_compile_options(project_sanitizers INTERFACE ${_sanitizer_flags})
        target_link_options(project_sanitizers INTERFACE ${_sanitizer_flags})
        message(STATUS "Sanitizers enabled: ${_sanitizer_flags_str}")
    endif()
endblock()
```

---

## 4. `cmake/Architecture.cmake`

Normalizes the target ISA family (`X86_64`, `ARM64`, `RISCV64`, `GENERIC`), exports `TARGET_CACHE_LINE_BYTES` (`128` on `ARM64` to match Apple Silicon L2 coherency granules, `64` on `X86_64` and `RISCV64` RVA23 `Zic64b`), probes `-march=native` when not cross-compiling, and compile-tests SIMD intrinsics. Defining `HAVE_*=1` signals intrinsic availability without blindly baking AVX-512 or SVE instructions into baseline translation units—attach ISA flags to runtime-dispatched targets or `FILE_SET` `COMPILE_OPTIONS`, or set baseline `-march=` in a cross-toolchain file.

```cmake
# cmake/Architecture.cmake

add_library(project_architecture INTERFACE)

option(ENABLE_NATIVE_OPTIMIZATION "Enable host -march=native when not cross-compiling" OFF)

block(SCOPE_FOR VARIABLES POLICIES DIAGNOSTICS)
    include(CheckCXXCompilerFlag)
    include(CheckCXXSourceCompiles)
    include(CMakePushCheckState)

    if(CMAKE_SYSTEM_PROCESSOR MATCHES "^(x86_64|amd64|AMD64)$")
        set(_arch_family "X86_64")
        set(_cache_line_bytes 64)
    elseif(CMAKE_SYSTEM_PROCESSOR MATCHES "^(aarch64|arm64|ARM64)$")
        set(_arch_family "ARM64")
        set(_cache_line_bytes 128)
    elseif(CMAKE_SYSTEM_PROCESSOR MATCHES "^riscv64")
        set(_arch_family "RISCV64")
        set(_cache_line_bytes 64)
    else()
        set(_arch_family "GENERIC")
        set(_cache_line_bytes 64)
    endif()

    target_compile_definitions(
        project_architecture
        INTERFACE "ARCH_FAMILY_${_arch_family}=1" "TARGET_CACHE_LINE_BYTES=${_cache_line_bytes}"
    )

    if(ENABLE_NATIVE_OPTIMIZATION AND NOT CMAKE_CROSSCOMPILING)
        check_cxx_compiler_flag("-march=native" _has_march_native)
        if(_has_march_native)
            target_compile_options(project_architecture INTERFACE "-march=native")
        else()
            message(WARNING "ENABLE_NATIVE_OPTIMIZATION requested but -march=native failed")
        endif()
    endif()

    if(_arch_family STREQUAL "X86_64")
        cmake_push_check_state(RESET)
        set(CMAKE_REQUIRED_FLAGS "-mavx2 -mfma")
        check_cxx_source_compiles(
            "
            #include <immintrin.h>
            int main() {
                __m256 a = _mm256_set1_ps(1.0F);
                __m256 b = _mm256_fmadd_ps(a, a, a);
                return static_cast<int>(_mm256_cvtss_f32(b));
            }
        "
            _has_avx2_fma
        )
        cmake_pop_check_state()
        if(_has_avx2_fma)
            target_compile_definitions(project_architecture INTERFACE HAVE_AVX2=1 HAVE_FMA=1)
        endif()

        cmake_push_check_state(RESET)
        set(CMAKE_REQUIRED_FLAGS "-mavx512f -mavx512vl -mavx512dq -mavx512bw")
        check_cxx_source_compiles(
            "
            #include <immintrin.h>
            int main() {
                __m512 a = _mm512_set1_ps(1.0F);
                __m512 b = _mm512_fmadd_ps(a, a, a);
                return static_cast<int>(_mm512_cvtss_f32(b));
            }
        "
            _has_avx512
        )
        cmake_pop_check_state()
        if(_has_avx512)
            target_compile_definitions(project_architecture INTERFACE HAVE_AVX512=1)
        endif()
    elseif(_arch_family STREQUAL "ARM64")
        cmake_push_check_state(RESET)
        check_cxx_source_compiles(
            "
            #include <arm_neon.h>
            int main() {
                float32x4_t a = vdupq_n_f32(1.0F);
                float32x4_t b = vaddq_f32(a, a);
                return static_cast<int>(vgetq_lane_f32(b, 0));
            }
        "
            _has_neon
        )
        cmake_pop_check_state()
        if(_has_neon)
            target_compile_definitions(project_architecture INTERFACE HAVE_NEON=1)
        endif()

        cmake_push_check_state(RESET)
        set(CMAKE_REQUIRED_FLAGS "-march=armv8-a+sve")
        check_cxx_source_compiles(
            "
            #include <arm_sve.h>
            int main() {
                svfloat32_t a = svdup_f32(1.0F);
                svfloat32_t b = svadd_f32_z(svptrue_b32(), a, a);
                return static_cast<int>(svcntb()) + static_cast<int>(svlen_f32(b) > 0);
            }
        "
            _has_sve
        )
        cmake_pop_check_state()
        if(_has_sve)
            target_compile_definitions(project_architecture INTERFACE HAVE_SVE=1)
        endif()
    elseif(_arch_family STREQUAL "RISCV64")
        set(_rvv_code
            "
            #include <riscv_vector.h>
            #if !defined(__riscv_v_intrinsic) || (__riscv_v_intrinsic < 1000000)
            #error \"RVV 1.0 intrinsics required\"
            #endif
            int main() {
                size_t vl = __riscv_vsetvl_e32m1(4);
                vfloat32m1_t a = __riscv_vfmv_v_f_f32m1(1.0F, vl);
                vfloat32m1_t b = __riscv_vfadd_vv_f32m1(a, a, vl);
                return static_cast<int>(__riscv_vfmv_f_s_f32m1_f32(b));
            }
        "
        )
        cmake_push_check_state(RESET)
        set(CMAKE_REQUIRED_FLAGS "-march=rva23u64")
        check_cxx_source_compiles("${_rvv_code}" _has_rvv_rva23)
        cmake_pop_check_state()

        if(NOT _has_rvv_rva23)
            cmake_push_check_state(RESET)
            set(CMAKE_REQUIRED_FLAGS "-march=rv64gcv")
            check_cxx_source_compiles("${_rvv_code}" _has_rvv_gcv)
            cmake_pop_check_state()
        endif()

        if(_has_rvv_rva23 OR _has_rvv_gcv)
            target_compile_definitions(project_architecture INTERFACE HAVE_RVV_1_0=1)
        endif()
    endif()
endblock()
```

---

## 5. `cmake/Dependencies.cmake`

Enforces centralized, hermetic dependency discovery via `find_package(<Pkg> CONFIG REQUIRED)` against `pixi` (`CMAKE_PREFIX_PATH="$CONDA_PREFIX"`) or an air-gapped `CMAKE_SYSROOT`. `FetchContent` and `ExternalProject_Add` are strictly banned so builds remain offline-reproducible, lockfile-pinned, and SBOM-traceable.

```cmake
# cmake/Dependencies.cmake

# Core C++23 packages installed by pixi (conda-forge libabseil, gtest, benchmark)
find_package(absl CONFIG REQUIRED)
find_package(benchmark CONFIG REQUIRED)
if(BUILD_TESTING)
    find_package(GTest CONFIG REQUIRED)
endif()

# Wrap a legacy/vendor SDK dependency lacking upstream CMake targets in INTERFACE IMPORTED
find_path(HALOS_TELEMETRY_INCLUDE_DIR NAMES halos_telemetry.h)
find_library(HALOS_TELEMETRY_LIBRARY NAMES halos_telemetry)
if(HALOS_TELEMETRY_INCLUDE_DIR AND HALOS_TELEMETRY_LIBRARY AND NOT TARGET Halos::Telemetry)
    add_library(Halos::Telemetry INTERFACE IMPORTED)
    set_target_properties(
        Halos::Telemetry
        PROPERTIES
            INTERFACE_INCLUDE_DIRECTORIES "${HALOS_TELEMETRY_INCLUDE_DIR}"
            INTERFACE_LINK_LIBRARIES "${HALOS_TELEMETRY_LIBRARY}"
    )
endif()
```

---

## 6. `cmake/Testing.cmake` & `cmake/Coverage.cmake`

### `cmake/Testing.cmake`

Combines `gtest_discover_tests()` (`POST_BUILD` natively, switching to `PRE_TEST` when cross-compiling with `CMAKE_CROSSCOMPILING_EMULATOR`) with CMake 4.4+ `discover_tests()` for generic regex test-time discovery, CMake 4.5 `BUILD_DEPENDS` (`ctest --out-of-date` / `test_prep/all`), and `CMP0224` (`AROUND_EACH_REPEAT` fixture repeats).

```cmake
# cmake/Testing.cmake

enable_testing()
find_package(GTest CONFIG REQUIRED)
include(GoogleTest)

if(POLICY CMP0224)
    cmake_policy(SET CMP0224 NEW)
endif()

function(add_project_test TEST_TARGET)
    cmake_parse_arguments(ARG "" "" "SOURCES;LIBS;EXTRA_ARGS" ${ARGN})

    add_executable(${TEST_TARGET} ${ARG_SOURCES})
    target_link_libraries(
        ${TEST_TARGET}
        PRIVATE
            ${ARG_LIBS}
            GTest::gtest_main
            GTest::gmock
            project_options
            project_warnings
            project_sanitizers
            project_architecture
    )

    if(NOT CMAKE_CROSSCOMPILING)
        gtest_discover_tests(
            ${TEST_TARGET}
            DISCOVERY_MODE POST_BUILD
            EXTRA_ARGS ${ARG_EXTRA_ARGS}
            PROPERTIES TIMEOUT 60
        )
    elseif(CMAKE_CROSSCOMPILING_EMULATOR)
        gtest_discover_tests(
            ${TEST_TARGET}
            DISCOVERY_MODE PRE_TEST
            EXTRA_ARGS ${ARG_EXTRA_ARGS}
            PROPERTIES TIMEOUT 120
        )
    else()
        message(STATUS "Skipping host test discovery for cross target ${TEST_TARGET}")
    endif()
endfunction()
```

For non-GTest harnesses (benchmarks, Rust/SPARK test runners, or custom CLI binaries), use CMake 4.4+ `discover_tests()` with CMake 4.5 `BUILD_DEPENDS` and `FIXTURE_REPEAT_MODE`:

```cmake
# CMake 4.5 test-time regex discovery with BUILD_DEPENDS and fixture repeat semantics
# gersemi: off
discover_tests(
    COMMAND custom_test_runner --manifest $<TARGET_FILE:custom_test_runner>
    DISCOVERY_ARGS --list
    DISCOVERY_MATCH "^([^:]+)::([A-Za-z0-9_]+)$"
    TEST_NAME "${PROJECT_NAME}.\\1.\\2"
    TEST_ARGS --case "\\1::\\2"
    TEST_PROPERTIES
        LABELS "\\1"
        FIXTURES_REQUIRED "hw_sim"
        FIXTURE_REPEAT_MODE "AROUND_EACH_REPEAT"
    BUILD_DEPENDS custom_test_runner
)
# gersemi: on
```

### `cmake/Coverage.cmake`

Configures LLVM/Clang source-based code coverage (`-fprofile-instr-generate -fcoverage-mapping`) with a `coverage-report` target driven by `llvm-profdata` and `llvm-cov`.

```cmake
# cmake/Coverage.cmake

add_library(project_coverage INTERFACE)

option(ENABLE_COVERAGE "Enable LLVM source-based code coverage" OFF)
if(ENABLE_COVERAGE)
    if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
        target_compile_options(
            project_coverage
            INTERFACE -fprofile-instr-generate -fcoverage-mapping -O0 -g
        )
        target_link_options(project_coverage INTERFACE -fprofile-instr-generate)

        find_program(LLVM_PROFDATA_PROGRAM llvm-profdata REQUIRED)
        find_program(LLVM_COV_PROGRAM llvm-cov REQUIRED)
        add_custom_target(
            coverage-report
            COMMAND ${CMAKE_COMMAND} -E make_directory "${CMAKE_BINARY_DIR}/coverage"
            COMMAND
                ${CMAKE_COMMAND} -E env
                "LLVM_PROFILE_FILE=${CMAKE_BINARY_DIR}/coverage/default-%p.profraw"
                ${CMAKE_CTEST_COMMAND} --output-on-failure
            COMMAND
                sh -c
                "\"${LLVM_PROFDATA_PROGRAM}\" merge -sparse \"${CMAKE_BINARY_DIR}\"/coverage/default-*.profraw -o \"${CMAKE_BINARY_DIR}/coverage/merged.profdata\" && \"${LLVM_COV_PROGRAM}\" export \"$<TARGET_FILE:core_tests>\" -instr-profile=\"${CMAKE_BINARY_DIR}/coverage/merged.profdata\" -format=lcov > \"${CMAKE_BINARY_DIR}/coverage/coverage.info\" && \"${LLVM_COV_PROGRAM}\" report \"$<TARGET_FILE:core_tests>\" -instr-profile=\"${CMAKE_BINARY_DIR}/coverage/merged.profdata\""
            WORKING_DIRECTORY "${CMAKE_BINARY_DIR}"
            COMMENT "Generating LLVM coverage report and LCOV export"
            VERBATIM
        )
    elseif(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
        target_compile_options(project_coverage INTERFACE --coverage -O0 -g)
        target_link_options(project_coverage INTERFACE --coverage)
    endif()
endif()
```
