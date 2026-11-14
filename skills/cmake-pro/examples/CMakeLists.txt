cmake_minimum_required(VERSION 4.5)

project(
    ModernCMakeTemplate
    VERSION 1.0.0
    COMPAT_VERSION 1.0.0
    SPDX_LICENSE "Apache-2.0"
    DESCRIPTION "Modern CMake 4.5+ modular template for Linux and macOS"
    LANGUAGES CXX C
)

if(PROJECT_SOURCE_DIR STREQUAL PROJECT_BINARY_DIR)
    message(FATAL_ERROR "In-source builds are forbidden. Use `cmake --preset <name>` instead.")
endif()

# Enforce target-based commands (rejects include_directories, add_compile_options, etc.)
cmake_diagnostic(SET CMD_NON_TARGET_DIRECTIVE SEND_ERROR)

# Default C++20/23 module scanning OFF per /cpp-pro for ccache & clang-tidy determinism;
# opt in explicitly for standalone CMake 4.5 GA `import std` projects.
option(ENABLE_CXX_MODULES "Enable C++20/23 module scanning and GA import std" OFF)
if(NOT ENABLE_CXX_MODULES)
    set(CMAKE_CXX_SCAN_FOR_MODULES OFF)
else()
    set(CMAKE_CXX_SCAN_FOR_MODULES ON)
endif()

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_C_STANDARD 23)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Guard modular cmake/ includes so this root template also validates standalone.
list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake")
block(SCOPE_FOR POLICIES DIAGNOSTICS)
    foreach(
        _module
        IN
        ITEMS ProjectOptions CompilerWarnings Sanitizers Architecture Dependencies
    )
        if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/cmake/${_module}.cmake")
            include(${_module})
        endif()
    endforeach()
endblock()

include(GNUInstallDirs)

if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/src/CMakeLists.txt")
    add_subdirectory(src)
elseif(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/src/core.cpp")
    add_library(modern_core)
    add_library(ModernCMakeTemplate::Core ALIAS modern_core)

    target_sources(
        modern_core
        PUBLIC FILE_SET HEADERS BASE_DIRS include FILES include/modern/core.hpp
        PRIVATE FILE_SET core_sources TYPE SOURCES BASE_DIRS src FILES src/core.cpp
    )

    foreach(
        _iface
        IN
        ITEMS project_options project_warnings project_sanitizers project_architecture
    )
        if(TARGET ${_iface})
            target_link_libraries(ModernCMakeTemplate::Core PRIVATE ${_iface})
        endif()
    endforeach()

    set_target_properties(
        ModernCMakeTemplate::Core
        PROPERTIES
            SPDX_LICENSE "${PROJECT_SPDX_LICENSE}"
            VERSION "${PROJECT_VERSION}"
            SOVERSION "${PROJECT_VERSION_MAJOR}"
    )

    install(
        TARGETS ModernCMakeTemplate::Core
        EXPORT ModernCMakeTemplateTargets
        ARCHIVE DESTINATION "${CMAKE_INSTALL_LIBDIR}"
        LIBRARY DESTINATION "${CMAKE_INSTALL_LIBDIR}"
        RUNTIME DESTINATION "${CMAKE_INSTALL_BINDIR}"
        FILE_SET HEADERS
    )

    install(
        PACKAGE_INFO ModernCMakeTemplate
        EXPORT ModernCMakeTemplateTargets
        LOWER_CASE_FILE
        DEFAULT_TARGETS modern_core
    )

    # Guard install(SBOM ...) with gersemi off/on until gersemi updates 4.5 GA keywords.
    # gersemi: off
    install(
        SBOM ModernCMakeTemplate
        EXPORTS ModernCMakeTemplateTargets
        DATA_LICENSE "CC0-1.0"
        DEFAULT_LICENSE "${PROJECT_SPDX_LICENSE}"
        FORMAT spdx-3.0.1+json
    )
    # gersemi: on
endif()

include(CTest)
if(BUILD_TESTING AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/tests/CMakeLists.txt")
    if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/cmake/Testing.cmake")
        include(Testing)
    endif()
    add_subdirectory(tests)
endif()
