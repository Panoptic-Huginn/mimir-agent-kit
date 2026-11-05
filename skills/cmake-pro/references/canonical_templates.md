# Canonical CMake 4.4.3+ Reference Implementations

Complete reference templates for the modular `cmake-pro` project architecture (`CMakeLists.txt`, `cmake/*.cmake`, `CMakePresets.json` v10+, and cross-compilation toolchains).

---

## 1. Root `CMakeLists.txt`

```cmake
cmake_minimum_required(VERSION 4.4.3)

project(
  MyProject
  VERSION 1.0.0
  DESCRIPTION "High-performance modern C++ project"
  LANGUAGES CXX C
)

# Enforce modern C++ standard
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Export compilation database for clangd and language tools
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Register modular cmake/ directory
list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake")

# Include modular configuration components
include(ProjectOptions)
include(CompilerWarnings)
include(Sanitizers)
include(Architecture)
include(Dependencies)

# Add subdirectories
add_subdirectory(src)

# Testing (conditioned on standard BUILD_TESTING or non-cross-compiling)
include(CTest)
if(BUILD_TESTING)
  include(Testing)
  add_subdirectory(tests)
endif()
```

---

## 2. `cmake/ProjectOptions.cmake` (Launchers, Linkers & Options)

```cmake
# cmake/ProjectOptions.cmake

# Common interface library for shared options
add_library(project_options INTERFACE)

# Compiler Launcher (ccache)
find_program(CCACHE_PROGRAM ccache)
if(CCACHE_PROGRAM)
  message(STATUS "Compiler launcher found: ${CCACHE_PROGRAM}")
  set(CMAKE_CXX_COMPILER_LAUNCHER "${CCACHE_PROGRAM}")
  set(CMAKE_C_COMPILER_LAUNCHER "${CCACHE_PROGRAM}")
endif()

# Static Analysis (clang-tidy)
option(ENABLE_CLANG_TIDY "Enable clang-tidy static analysis during compilation" OFF)
if(ENABLE_CLANG_TIDY)
  find_program(CLANG_TIDY_PROGRAM clang-tidy)
  if(CLANG_TIDY_PROGRAM)
    message(STATUS "clang-tidy enabled: ${CLANG_TIDY_PROGRAM}")
    set(CMAKE_CXX_CLANG_TIDY "${CLANG_TIDY_PROGRAM}")
  else()
    message(WARNING "ENABLE_CLANG_TIDY is ON but clang-tidy executable was not found.")
  endif()
endif()

# Native Linker Selection (LLD, MOLD, GOLD)
if(NOT DEFINED CMAKE_LINKER_TYPE AND NOT WIN32)
  find_program(LLD_PROGRAM ld.lld)
  if(LLD_PROGRAM)
    set(CMAKE_LINKER_TYPE "LLD" CACHE STRING "Linker type" FORCE)
    message(STATUS "Defaulting linker to LLD: ${LLD_PROGRAM}")
  endif()
endif()

# Position Independent Code
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# Output Directories
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib")
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib")

# Interprocedural Optimization (LTO)
option(ENABLE_IPO "Enable Interprocedural Optimization (LTO)" OFF)
if(ENABLE_IPO)
  include(CheckIPOSupported)
  check_ipo_supported(RESULT ipo_supported OUTPUT ipo_error)
  if(ipo_supported)
    set(CMAKE_INTERPROCEDURAL_OPTIMIZATION ON)
    message(STATUS "Interprocedural Optimization (IPO/LTO) enabled")
  else()
    message(WARNING "IPO requested but not supported: ${ipo_error}")
  endif()
endif()
```

---

## 3. `cmake/CompilerWarnings.cmake` (Strict & Safe Flags)

```cmake
# cmake/CompilerWarnings.cmake

add_library(project_warnings INTERFACE)

set(MSVC_WARNINGS
    /W4 # Baseline reasonable warnings
    /w14242 # Conversion possible loss of data
    /w14254 # Conversion larger to smaller type
    /w14263 # Member function does not override any base class
    /w14265 # Class has virtual functions, but destructor is not virtual
    /w14287 # Unsigned/negative constant mismatch
    /we4289 # Nonstandard extension used: loop control variable
    /w14296 # Expression is always true/false
    /w14311 # Pointer truncation
    /w14545 # Expression before comma has no effect
    /w14546 # Function call before comma missing argument list
    /w14547 # Operator before comma has no effect
    /w14549 # Operator before comma has no effect
    /w14555 # Expression has no effect
    /w14619 # Pragma warning: there is no warning number
    /w14640 # Enable warning on thread un-safe static member initialization
    /w14826 # Conversion is sign-extended
    /w14905 # Wide string literal cast to LPSTR
    /w14906 # String literal cast to LPWSTR
    /w14928 # Illegal copy-initialization
    /permissive- # Standards conformance mode
)

set(CLANG_GCC_WARNINGS
    -Wall
    -Wextra
    -Wpedantic
    -Wshadow
    -Wnon-virtual-dtor
    -Wold-style-cast
    -Wcast-align
    -Wunused
    -Woverloaded-virtual
    -Wconversion
    -Wsign-conversion
    -Wnull-dereference
    -Wdouble-promotion
    -Wformat=2
    -Wimplicit-fallthrough
)

option(WARNINGS_AS_ERRORS "Treat compiler warnings as errors" ON)
if(WARNINGS_AS_ERRORS)
  set(CLANG_GCC_WARNINGS ${CLANG_GCC_WARNINGS} -Werror)
  set(MSVC_WARNINGS ${MSVC_WARNINGS} /WX)
endif()

if(MSVC)
  target_compile_options(project_warnings INTERFACE ${MSVC_WARNINGS})
elseif(CMAKE_CXX_COMPILER_ID MATCHES ".*Clang" OR CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
  target_compile_options(project_warnings INTERFACE ${CLANG_GCC_WARNINGS})
endif()
```

---

## 4. `cmake/Sanitizers.cmake` (Dynamic Sanitizer Detection)

```cmake
# cmake/Sanitizers.cmake

include(CheckCXXSourceCompiles)
include(CMakePushCheckState)

add_library(project_sanitizers INTERFACE)

option(ENABLE_SANITIZER_ADDRESS "Enable AddressSanitizer (ASan)" OFF)
option(ENABLE_SANITIZER_UNDEFINED "Enable UndefinedBehaviorSanitizer (UBSan)" OFF)
option(ENABLE_SANITIZER_THREAD "Enable ThreadSanitizer (TSan)" OFF)
option(ENABLE_SANITIZER_MEMORY "Enable MemorySanitizer (MSan)" OFF)

if(CMAKE_CXX_COMPILER_ID MATCHES ".*Clang" OR CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
  set(SANITIZER_FLAGS "")

  if(ENABLE_SANITIZER_ADDRESS)
    list(APPEND SANITIZER_FLAGS "-fsanitize=address" "-fno-omit-frame-pointer")
  endif()

  if(ENABLE_SANITIZER_UNDEFINED)
    list(APPEND SANITIZER_FLAGS "-fsanitize=undefined")
  endif()

  if(ENABLE_SANITIZER_THREAD)
    if(ENABLE_SANITIZER_ADDRESS OR ENABLE_SANITIZER_MEMORY)
      message(FATAL_ERROR "ThreadSanitizer cannot be combined with AddressSanitizer or MemorySanitizer")
    endif()
    list(APPEND SANITIZER_FLAGS "-fsanitize=thread")
  endif()

  if(ENABLE_SANITIZER_MEMORY)
    list(APPEND SANITIZER_FLAGS "-fsanitize=memory" "-fno-omit-frame-pointer")
  endif()

  if(SANITIZER_FLAGS)
    # Test if compiler and linker support the requested sanitizers
    cmake_push_check_state()
    set(CMAKE_REQUIRED_FLAGS "${SANITIZER_FLAGS}")
    set(CMAKE_REQUIRED_LINK_OPTIONS "${SANITIZER_FLAGS}")
    check_cxx_source_compiles("int main() { return 0; }" COMPILER_SUPPORTS_SANITIZERS)
    cmake_pop_check_state()

    if(COMPILER_SUPPORTS_SANITIZERS)
      target_compile_options(project_sanitizers INTERFACE ${SANITIZER_FLAGS})
      target_link_options(project_sanitizers INTERFACE ${SANITIZER_FLAGS})
      message(STATUS "Sanitizers enabled: ${SANITIZER_FLAGS}")
    else()
      message(FATAL_ERROR "Requested sanitizers are not supported by the current compiler: ${SANITIZER_FLAGS}")
    endif()
  endif()
endif()
```

---

## 5. `cmake/Architecture.cmake` (Generic Dynamic CPU & SIMD Detection)

```cmake
# cmake/Architecture.cmake

include(CheckCXXSourceCompiles)
include(CMakePushCheckState)

add_library(project_architecture INTERFACE)

# Detect Target Architecture Family
if(CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|amd64|AMD64")
  set(TARGET_ARCH_FAMILY "X86_64")
elseif(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64|arm64|ARM64")
  set(TARGET_ARCH_FAMILY "ARM64")
elseif(CMAKE_SYSTEM_PROCESSOR MATCHES "riscv64")
  set(TARGET_ARCH_FAMILY "RISCV64")
else()
  set(TARGET_ARCH_FAMILY "GENERIC")
endif()

target_compile_definitions(project_architecture INTERFACE "ARCH_FAMILY_${TARGET_ARCH_FAMILY}=1")

# Dynamic Native Optimization Probe
option(ENABLE_NATIVE_OPTIMIZATION "Build with native host optimizations (-march=native)" OFF)
if(ENABLE_NATIVE_OPTIMIZATION AND NOT CMAKE_CROSSCOMPILING)
  target_compile_options(project_architecture INTERFACE "-march=native")
endif()

# Dynamic SIMD Feature Checks (x86_64)
if(TARGET_ARCH_FAMILY STREQUAL "X86_64" AND (CMAKE_CXX_COMPILER_ID MATCHES ".*Clang|GNU"))
  # Check AVX2 & FMA
  cmake_push_check_state()
  set(CMAKE_REQUIRED_FLAGS "-mavx2 -mfma")
  check_cxx_source_compiles("
    #include <immintrin.h>
    int main() {
      __m256 a = _mm256_set1_ps(1.0f);
      __m256 b = _mm256_fmadd_ps(a, a, a);
      return static_cast<int>(_mm256_cvtss_f32(b));
    }
  " COMPILER_SUPPORTS_AVX2)
  cmake_pop_check_state()

  if(COMPILER_SUPPORTS_AVX2)
    target_compile_definitions(project_architecture INTERFACE HAVE_AVX2=1 HAVE_FMA=1)
    message(STATUS "Hardware/Compiler SIMD capability: AVX2 + FMA detected")
  endif()

  # Check AVX-512 (Foundation + Vector Length)
  cmake_push_check_state()
  set(CMAKE_REQUIRED_FLAGS "-mavx512f -mavx512vl -mavx512dq -mavx512bw")
  check_cxx_source_compiles("
    #include <immintrin.h>
    int main() {
      __m512 a = _mm512_set1_ps(1.0f);
      __m512 b = _mm512_fmadd_ps(a, a, a);
      return static_cast<int>(_mm512_cvtss_f32(b));
    }
  " COMPILER_SUPPORTS_AVX512)
  cmake_pop_check_state()

  if(COMPILER_SUPPORTS_AVX512)
    target_compile_definitions(project_architecture INTERFACE HAVE_AVX512=1)
    message(STATUS "Hardware/Compiler SIMD capability: AVX-512 detected")
  endif()

# Dynamic SIMD Feature Checks (ARM64)
elseif(TARGET_ARCH_FAMILY STREQUAL "ARM64" AND (CMAKE_CXX_COMPILER_ID MATCHES ".*Clang|GNU"))
  # Check NEON
  cmake_push_check_state()
  set(CMAKE_REQUIRED_FLAGS "")
  check_cxx_source_compiles("
    #include <arm_neon.h>
    int main() {
      float32x4_t a = vdupq_n_f32(1.0f);
      float32x4_t b = vaddq_f32(a, a);
      return static_cast<int>(vgetq_lane_f32(b, 0));
    }
  " COMPILER_SUPPORTS_NEON)
  cmake_pop_check_state()

  if(COMPILER_SUPPORTS_NEON)
    target_compile_definitions(project_architecture INTERFACE HAVE_NEON=1)
    message(STATUS "Hardware/Compiler SIMD capability: ARM NEON (ASIMD) detected")
  endif()

  # Check SVE
  cmake_push_check_state()
  set(CMAKE_REQUIRED_FLAGS "-march=armv8-a+sve")
  check_cxx_source_compiles("
    #include <arm_sve.h>
    int main() {
      svfloat32_t a = svdup_f32(1.0f);
      svfloat32_t b = svadd_f32_z(svptrue_b32(), a, a);
      return (int)svcntb();
    }
  " COMPILER_SUPPORTS_SVE)
  cmake_pop_check_state()

  if(COMPILER_SUPPORTS_SVE)
    target_compile_definitions(project_architecture INTERFACE HAVE_SVE=1)
    message(STATUS "Hardware/Compiler SIMD capability: ARM SVE detected")
  endif()
endif()
```

---

## 6. `cmake/Testing.cmake` (CTest & GoogleTest Discovery)

```cmake
# cmake/Testing.cmake

enable_testing()
find_package(GTest CONFIG QUIET)

if(NOT GTest_FOUND)
  find_package(GTest REQUIRED)
endif()

include(GoogleTest)

# Helper function to register unit test targets cleanly
function(add_project_test TEST_TARGET)
  cmake_parse_arguments(ARG "" "" "SOURCES;LIBS" ${ARGN})

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
      PROPERTIES TIMEOUT 60
    )
  endif()
endfunction()
```

---

## 7. Modern `CMakePresets.json` (Schema v10+)

```json
{
  "version": 10,
  "cmakeMinimumRequired": {
    "major": 4,
    "minor": 4,
    "patch": 3
  },
  "configurePresets": [
    {
      "name": "base",
      "hidden": true,
      "generator": "Ninja",
      "binaryDir": "${sourceDir}/build/${presetName}",
      "cacheVariables": {
        "CMAKE_EXPORT_COMPILE_COMMANDS": "ON",
        "CMAKE_TOOLCHAIN_FILE": "$env{VCPKG_ROOT}/scripts/buildsystems/vcpkg.cmake",
        "VCPKG_MANIFEST_MODE": "ON"
      }
    },
    {
      "name": "dev-debug",
      "inherits": "base",
      "displayName": "Developer Debug (ASan + UBSan)",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Debug",
        "ENABLE_SANITIZER_ADDRESS": "ON",
        "ENABLE_SANITIZER_UNDEFINED": "ON",
        "BUILD_TESTING": "ON",
        "WARNINGS_AS_ERRORS": "ON"
      }
    },
    {
      "name": "dev-release",
      "inherits": "base",
      "displayName": "Developer Release (Optimized)",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Release",
        "ENABLE_IPO": "ON",
        "BUILD_TESTING": "ON"
      }
    },
    {
      "name": "cross-aarch64",
      "inherits": "base",
      "displayName": "Cross-compile AArch64",
      "toolchainFile": "${sourceDir}/cmake/toolchains/aarch64-linux-gnu.cmake",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Release",
        "BUILD_TESTING": "OFF"
      }
    }
  ],
  "buildPresets": [
    {
      "name": "dev-debug",
      "configurePreset": "dev-debug",
      "displayName": "Build Debug"
    },
    {
      "name": "dev-release",
      "configurePreset": "dev-release",
      "displayName": "Build Release"
    },
    {
      "name": "cross-aarch64",
      "configurePreset": "cross-aarch64",
      "displayName": "Build Cross AArch64"
    }
  ],
  "testPresets": [
    {
      "name": "dev-debug",
      "configurePreset": "dev-debug",
      "displayName": "Run Tests (Debug)",
      "output": {
        "outputOnFailure": true
      },
      "execution": {
        "noTestsAction": "error",
        "stopOnFailure": false
      }
    }
  ],
  "workflowPresets": [
    {
      "name": "ci-debug",
      "displayName": "CI Debug Workflow",
      "steps": [
        {
          "type": "configure",
          "name": "dev-debug"
        },
        {
          "type": "build",
          "name": "dev-debug"
        },
        {
          "type": "test",
          "name": "dev-debug"
        }
      ]
    }
  ]
}
```

---

## 8. Cross-Compilation Toolchain Example (`cmake/toolchains/aarch64-linux-gnu.cmake`)

```cmake
# cmake/toolchains/aarch64-linux-gnu.cmake

set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)

# Specify cross compilers
set(CMAKE_C_COMPILER aarch64-linux-gnu-gcc)
set(CMAKE_CXX_COMPILER aarch64-linux-gnu-g++)
set(CMAKE_AR aarch64-linux-gnu-ar)
set(CMAKE_RANLIB aarch64-linux-gnu-ranlib)

# Optional Sysroot Configuration
if(DEFINED ENV{SYSROOT_AARCH64})
  set(CMAKE_SYSROOT "$ENV{SYSROOT_AARCH64}")
  set(CMAKE_FIND_ROOT_PATH "$ENV{SYSROOT_AARCH64}")
endif()

# Search policies: find tools on host, packages/libraries/headers in target sysroot
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
```
