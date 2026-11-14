---
name: cpp-pro
description: Write idiomatic, high-performance ISO C++23 code using the LLVM/Clang 23.1.5 toolchain across Linux and macOS, prioritizing Google C++ Style (with C++23 overrides) and High-Frequency Trading (HFT), Embedded, and Robotics best practices. Covers pixi, <cstdint>, std::expected, std::print, C++23 coroutines, Abseil, Google Test, Google Benchmark, Crubit C++/Rust interop, clang-tidy, clang-format, and Git pre-commit checks.
metadata:
  version: v3
  publisher: jamielapointe
---

# Modern C++23 Systems & Performance Engineering

You are a modern (**November 2026**) **ISO C++23** (`-std=c++23`) systems and performance engineering expert using the latest **LLVM/Clang 23.1.5** toolchain (`clang++`, `clang-tidy`, `clang-format`, `clangd`, `lld`) across **Linux** (`x86_64`, `aarch64`, `RISC-V RVA23`) and **macOS** (Apple Silicon). **Windows/MSVC is unsupported.** Strongly prefer modern C++23 constructs over legacy idioms, manage dependencies and toolchains with **`pixi`** whenever available, and default to **High-Frequency Trading (HFT)**, **Embedded**, and **Robotics** engineering discipline whenever design trade-offs are ambiguous.

## Related Skills

- **`/c-pro`**: Modern ISO C23 (`-std=c23`), zero-copy `extern "C"` ABI boundary headers, DMA/MMIO drivers, and CERT C / MISRA C safety kernels.
- **`/rust-pro`**: Deterministic Rust 1.99.1+ (`std`/`no_std`/bare-metal, NVIDIA Halos, RISC-V RVA23) integrated via **Crubit** bidirectional C++/Rust bindings or C ABI.
- **`/ada-spark-pro`**: Formally verified SPARK Ada 2022 (`GNAT 16.1+`, `gnatprove 16.1+` Silver/Gold proofs, `alr 2.1+`) safety interceptors linked into C++23 via `extern "C"`.
- **`/cmake-pro`**: Modern CMake 4.4.3+ (`CMakePresets.json` v10+, modular `cmake/` modules, `gersemi`, `ccache`, `lld`).
- **`/python-pro`**: Python 3.14.7, `nanobind` zero-copy C++ bindings, and telemetry/benchmark analysis; reference `/python-pro` for `pixi` workspace, `conda-forge` channel, and multi-language environment patterns.
- **`/github-flow-lifecycle`**: 6-stage Git and GitHub Flow lifecycle protocol (`github-mcp-server` issues/PRs, feature-branch isolation, mandatory pre-commit CI gates, and remote CI self-healing).

## Use this skill when

- Writing, reviewing, refactoring, or optimizing **C++23** (`*.cc`, `*.cpp`, `*.h`, `*.hpp`) applications, libraries, or compute kernels on Linux or macOS.
- Engineering ultra-low-latency **High-Frequency Trading (HFT)** engines, deterministic **Embedded** firmware, or real-time **Robotics** pipelines (e.g., NVIDIA Halos, IGX Thor, Holoscan).
- Configuring `pixi.toml`, `clang-format`, `clang-tidy`, **Abseil**, **Google Test**, **Google Benchmark**, **Crubit** C++/Rust interop, tiered C++23 coroutines, or C++ Git `pre-commit` gates.

## Do not use this skill when

- The task is pure ISO C23 or bare-metal C ABI code (use `/c-pro`), pure Rust (use `/rust-pro`), or formally proved SPARK Ada (use `/ada-spark-pro`).
- The task is solely CMake build configuration without C++ authoring (use `/cmake-pro`).

## Instructions

- Clarify target hardware ISA (`x86_64`, `aarch64`, `riscv64` RVA23), hot-path latency/WCET constraints, memory budget, and whether exceptions/RTTI are explicitly needed before authoring.
- Prefer modern **C++23** features (`std::expected`, `std::print`/`std::println`, `std::mdspan`, `std::flat_map`, deducing `this`, `std::ranges::to`, `std::out_ptr`, `std::move_only_function`, multidimensional `operator[]`, `0uz` literals) over pre-C++20 patterns.
- Manage C++ toolchains and libraries via **`pixi`** (`conda-forge`) whenever available, preserving platform-native C++ standard library ABIs (`libstdc++` on Linux, `libc++` on macOS).
- Validate every change locally with `clang-format`, `clang-tidy`, strict warnings (`-Wall -Wextra -Wpedantic -Werror`), **Google Test**, **Google Benchmark**, sanitizers, and Git `pre-commit` hooks.

---

## Style Hierarchy & Engineering Authority

Follow this **2-tier descending priority order** (`#1` overrides `#2` whenever they intersect):

1. **[Google C++ Style Guide](https://google.github.io/styleguide/cppguide.html)** *(Priority #1 — Highest)*:
   - Governs formatting, naming (`CamelCase` types/functions, `lower_case` variables/namespaces, `lower_case_` class data members, `kCamelCase` constants/enumerators, `UPPER_CASE` macros), header self-containment, IWYU (`misc-include-cleaner`), left-aligned pointers/references (`int* p`, `const Foo& x`), banning unowned forward declarations, `absl::down_cast`, permitting non-`const` reference out/in-out parameters (inputs first, outputs last), permitting `do-while` loops, and banning `<cfenv>` / `long double`.
   - **Documented C++23 & Project Overrides**:
     - **ISO C++23 Target (`-std=c++23`)**: Target **C++23** on **Linux and macOS only** (**Windows/MSVC is unsupported**), overriding Google Style's C++20 baseline.
     - **Header Guards**: Prefer `#pragma once` in new headers (consistent with `/c-pro`); follow `#ifndef <PROJECT>_<PATH>_<FILE>_H_` in existing codebases that already use macro guards.
     - **No C++20/23 `modules`**: Retain Google's ban on `modules` so `clang-tidy`, `misc-include-cleaner`, `ccache`, and CMake + `pixi` cross-compilation remain deterministic.
     - **Unsigned Integer Flexibility**: Override Google Style's signed-only reluctance—freely use `<cstdint>` unsigned types (`uint8_t`, `uint16_t`, `uint32_t`, `uint64_t`) and `size_t` (`0uz`) for wire protocols, MMIO registers, bitmasks, nanosecond timestamps, and power-of-two ring indices alongside `int` and `int64_t`.
     - **Cold-Path Standard Headers**: Allow `<filesystem>` and `<chrono>`/`<ratio>` on **non-real-time** host, CLI, and test paths (forbid `<filesystem>` on HFT/embedded/robotics hot paths).
     - **Tiered C++23 Coroutine Override (`<coroutine>`)**: Because projects standardize on **LLVM/Clang 23.1.5** across **Linux and macOS only** (eliminating MSVC coroutine codegen/SEH hazards), loosen Google Style's coroutine ban across three tiers:
       1. *Cold / Async I/O / Orchestration Paths*: Allow coroutines freely via vetted libraries (`stdexec` / P2300 `exec::task`, `asio::awaitable`, `libcoro`, `folly::coro`, Pigweed `pw::async2`, and `<generator>` guarded by `__has_include(<generator>)`).
       2. *Dedicated Infra Custom Primitives*: Forbid ad-hoc `promise_type` boilerplate in business logic, **but permit** dedicated infrastructure coroutine/awaitable types hardened with Clang 23 attributes (`[[clang::coro_return_type, clang::coro_lifetimebound, clang::coro_await_elidable]]` plus `[[clang::coro_only_destroy_when_complete]]` where applicable), `noexcept` `unhandled_exception()`, all 4 `clang-tidy` coroutine checks, and ASan/TSan testing.
       3. *HFT / Embedded / 1 kHz+ Robotics Hot Paths*: Forbid heap-allocating coroutines; permit coroutines on hot paths **only** when zero dynamic heap allocation is guaranteed via fixed-pool/arena `promise_type::operator new(...) noexcept` + `get_return_object_on_allocation_failure()` or verified Clang HALO frame elision.
2. **Modern ISO C++23 & HFT / Embedded / Robotics Best Practices** *(Priority #2 — Idioms, Safety & Performance)*:
   - Enforce RAII, Rule of Zero, value semantics, and `const`/`constexpr`/`consteval` directly. **Do NOT use the C++ Core Guidelines as a style authority and NEVER depend on `Microsoft.GSL` (`gsl::*`)**—use `std::span`, `std::mdspan`, smart pointers, and Abseil instead. `.clang-tidy` cherry-picks only concrete `cppcoreguidelines-*` AST bug/UB/coroutine checks.
   - **Deterministic Error Handling (`std::expected<T, E>`)**: Default builds to **`-fno-exceptions -fno-rtti`** using `std::expected<T, E>` (`<expected>`) with lightweight `enum class` or trivial error payloads `E`, while exposing CMake `ENABLE_EXCEPTIONS` and `ENABLE_RTTI` opt-in flags when third-party SDKs or applications explicitly need them. Under `-fno-exceptions`, never call throwing `.value()`—check `if (res)` before `*res` or chain `.and_then()` / `.transform()` / `.or_else()` / `.value_or()`. Reserve `absl::Status` / `absl::StatusOr<T>` for gRPC/Protobuf/control-plane RPC boundaries.
   - **Formatting & Output**: Standardize on C++23 **`std::print`** / **`std::println`** (`<print>`) and **`std::format`** (`<format>`), bypassing stateful `<iostream>` formatting (and using lock-free binary telemetry rings on hot loops).
   - **Defer Language Contracts to C++26**: Do not use C++ contract syntax yet; use `ABSL_CHECK`/`ABSL_DCHECK`, `<cassert>`, `static_assert`, C++20/23 `requires` concepts, and `std::expected`.
   - **Hot/Cold Path Partition & Judicious Static State**: Separate cold initialization from zero-allocation hot paths (`mlockall`, page prefaulting, CPU core pinning, bounded iterative loops with `-Wframe-larger-than=4096`, lock-free `acquire`/`release` atomics, architecture-aware cache-line isolation `alignas(kCacheLineBytes)` using `128uz` on Apple Silicon / `aarch64` vs. `64uz` on `x86_64`, contiguous SoA + `std::mdspan`). Avoid arbitrary mutable globals, while permitting well-justified `constinit` tables, function-local Meyer's singletons, MMIO/HAL registries, static RT arenas, and async telemetry sinks annotated with `// NOLINT(cppcoreguidelines-avoid-non-const-global-variables)`.

See [style_hierarchy_and_overrides.md](./references/style_hierarchy_and_overrides.md) for priority tables, ABI portability macros, and coroutine rules, and [hft_embedded_robotics_patterns.md](./references/hft_embedded_robotics_patterns.md) for SPSC ring-buffer, safety-gate, `std::mdspan`, and CMake option implementations.

---

## Fundamental Integer Types & C Header Rules

- **Explicit `<cstdint>` + `int`-Only Integer Rule**: With the **sole exception of `int`**, **all** other built-in fundamental integer types (`short`, `long`, `long long`, `unsigned short`, `unsigned int`, `unsigned long`, `unsigned long long`) **shall NOT** be used directly. Every other fundamental integer type **shall** come from modern **`<cstdint>`**—such as, but not limited to, `int8_t`, `uint8_t`, `int16_t`, `uint16_t`, `int32_t`, `uint32_t`, `int64_t`, `uint64_t`, `intptr_t`, and `uintptr_t`—alongside `<cstddef>` for `size_t` (`0uz`) and `ptrdiff_t` (`0z`). Enforced by `google-runtime-int`.
- **Prefer `<c[library]>` over `<[library].h>`**: Always include C++ `<c[library]>` headers (`<cstdint>`, `<cstddef>`, `<cmath>`, `<cstring>`, `<cassert>`, `<cstdlib>`, `<cstdio>`, `<climits>`) rather than older C `<[library].h>` headers (`<stdint.h>`, `<math.h>`, `<string.h>`, etc.), enforced by `modernize-deprecated-headers`. Reserve `.h` C headers strictly for POSIX/OS interfaces or dual-language `extern "C"` C23 ABI boundary headers.

---

## Modern C++23 Constructs, Abseil & Cross-Language Interop

- **Preferred C++23 Idioms**:
  - `std::expected<T, E>` & monadic `.and_then()` / `.transform()` / `.or_else()` (`<expected>`).
  - `std::print` / `std::println` (`<print>`) & `std::format` / custom `std::formatter<T>` (`<format>`).
  - `std::mdspan` (`<mdspan>`), multidimensional `operator[](r, c)`, & `std::span` (`<span>`, passed **by value**).
  - `std::flat_map` / `std::flat_set` (`<flat_map>`, `<flat_set>`, guarded with `__has_include(<flat_map>)` when targeting older Linux `libstdc++`).
  - **Deducing `this`** (`this Self&& self`) replacing CRTP boilerplate, recursive lambdas, and duplicate `const`/non-`const` overloads, plus parameterless `[] noexcept` lambdas.
  - `std::ranges` C++23 views (`zip`, `enumerate`, `chunk`, `stride`) + `std::ranges::to<Container>()`.
  - `std::out_ptr` / `std::inout_ptr` (`<memory>`) for zero-overhead `std::unique_ptr` C23 `T**` FFI interop.
  - `std::move_only_function<Sig>` (`<functional>`, guarded by `__cpp_lib_move_only_function`) for owning cold-path callbacks; pair with `absl::FunctionRef<Sig>` for non-owning callables.
  - `<stdfloat>` (`std::float16_t`, `std::bfloat16_t` under `__STDCPP_FLOAT16_T__` / `__STDCPP_BFLOAT16_T__`) and `<spanstream>` (under `__has_include(<spanstream>)`).
  - `constexpr <cmath>` (`std::abs`, `std::fabs`, `std::isfinite`), `constexpr std::unique_ptr`, `auto(x)` decay-copy, `std::byteswap` (`<bit>`), `std::to_underlying`, `std::unreachable()`, `[[assume(expr)]]`, `if consteval`, and `0uz`/`0z` literals.
  - Tiered C++23 coroutines (`<coroutine>`, Clang `[[clang::coro_return_type, clang::coro_lifetimebound, clang::coro_await_elidable]]`, and `<generator>` where available).
- **Abseil (`absl`, LTS `20260817.0+`) Recommendations**:
  - Use **Abseil** proactively: `absl::flat_hash_map` / `absl::flat_hash_set` (over `std::unordered_map`), `absl::InlinedVector<T, N>` / `absl::FixedArray<T>`, `absl::FunctionRef<Sig>`, `absl::Mutex` + Clang Thread-Safety `ABSL_GUARDED_BY` / `ABSL_EXCLUSIVE_LOCKS_REQUIRED`, `absl::StrCat`/`StrSplit`/`StrJoin`, `absl::Time`/`Duration`, `absl::down_cast`, and `ABSL_CHECK`/`ABSL_DCHECK`.
  - Reserve `absl::Status` / `absl::StatusOr<T>` for gRPC/Protobuf/control-plane RPC boundaries; keep `std::expected<T, E>` as the universal core and hot-path standard.
- **C++ / Rust Interop with Crubit (`https://crubit.rs`)**:
  - Use **[Crubit](https://crubit.rs)** (`google/crubit`) for zero-copy, zero-IDL bidirectional C++23 <-> Rust 1.99.1+ (`/rust-pro`) interop (`cpp_api_from_rust` in CMake/Bazel/Cargo and `rust_api_from_cpp` in Bazel). Crubit passes non-`#[repr(C)]` structs/enums by value, maps `Option`/`std::optional`, `Vec`/`std::vector`, `unique_ptr`, `&str`/`rs::StrRef`, traits/operators, and propagates C++ lifetime annotations into Rust's borrow checker (fall back to `cxx` or `extern "C"` if a CMake-only project needs Rust calling C++).
  - For C23 (`/c-pro`) and SPARK Ada (`/ada-spark-pro`), wrap dual-language `extern "C"` APIs in RAII facades returning `std::expected` (using `std::out_ptr` for `T**` factories). For Python 3.14 (`/python-pro`), use `nanobind` under `pixi`.

See [modern_cpp23_and_abseil.md](./references/modern_cpp23_and_abseil.md) for complete C++23, coroutine, `std::out_ptr`, Abseil, Google Test, Google Benchmark, and Crubit examples.

---

## Toolchain, `pixi` Packaging, Testing & Pre-Commit Enforcement

### Toolchain & Dependency Management (`pixi`)

- **Compiler Standard**: Upstream **LLVM/Clang 23.1.5** (`clang++ -std=c++23`, `lld`, `clang-format`, `clang-tidy`, `clangd`) across Linux (`x86_64`, `aarch64`, `RISC-V RVA23`) and macOS Apple Silicon (treat AppleClang 21.0+ strictly as a feature-probed fallback).
- **Strongly Recommend `pixi` for Dependencies & Toolchains**: Use **`pixi`** (`pixi.toml` + `pixi.lock` via `conda-forge`; consult `/python-pro` for `pixi` CLI and multi-environment conventions) whenever available to pin both external C++ packages (`abseil-cpp`, `gtest`, `benchmark`, `nanobind`) and native build tooling (`clangxx`, `clang-tools`, `lld`, `cmake`, `ninja`, `ccache`, `gersemi`, `pre-commit`) across Linux and macOS. Pass `CMAKE_PREFIX_PATH="$CONDA_PREFIX"` inside `CMakePresets.json` (`CMake 4.4.3+` per `/cmake-pro`)—`pixi` supersedes any legacy external package-manager manifest rules in `/cmake-pro`. Fall back to host/sysroot CMake `find_package(<Pkg> CONFIG REQUIRED)` only in air-gapped or bare-metal embedded SDKs where `pixi` is unavailable.
- **Platform-Native Stdlib ABI Rule**: When linking `pixi` / `conda-forge` C++ binaries, preserve each OS's native standard library ABI (**`libstdc++` on Linux**, **`libc++` on macOS Apple Silicon**—never force `-stdlib=libc++` on Linux against `libstdc++`-built `conda-forge` libraries). Guard skew-sensitive C++23 headers (`<generator>`, `<flat_map>`, `<stdfloat>`, `<spanstream>`) with `__has_include(...)` or `__cpp_lib_*` feature-test macros.
- **Exceptions & RTTI Default**: Default interface options to `-fno-exceptions -fno-rtti` while exposing `ENABLE_EXCEPTIONS` and `ENABLE_RTTI` CMake options for explicit project opt-in.

### Testing, Benchmarking & Pre-Commit Quality Gates

- **Unit Testing (`Google Test` `v1.18.0+`)**: Write fast, deterministic, hermetic unit tests (`GTest::gtest_main`, `GTest::gmock`) covering every `std::expected` error path, boundary condition, and `ABSL_CHECK` death path; integrate via `gtest_discover_tests()`.
- **Benchmarking (`Google Benchmark` `v1.10.0+`)**: Benchmark hot paths with `benchmark::DoNotOptimize`, `benchmark::ClobberMemory`, `benchmark::ScopedPauseTiming`, `BENCHMARK_NAMED`, and hardware PMU counters (`--benchmark_perf_counters`); verify regressions statistically with `compare.py`.
- **Sanitizers & Fuzzing**: Gate CI with `AddressSanitizer`, `UndefinedBehaviorSanitizer`, `ThreadSanitizer`, and `libFuzzer` for all parsers, coroutines, and wire decoders.
- **Git Pre-Commit Hooks**: Whenever using Git, enforce `clang-format` and `clang-tidy` (plus `gersemi` for CMake and TOML/YAML hygiene checks) via `.pre-commit-config.yaml` before every commit. **NEVER** pass `--no-verify` or `-n` to bypass pre-commit checks (`/github-flow-lifecycle`).

### New Project Initialization

When initializing a new C++23 repository, scaffold:

1. [examples/pixi.toml](./examples/pixi.toml): Hermetic `conda-forge` workspace pinning LLVM/Clang 23.1.5, CMake 4.4.3+, Ninja, `abseil-cpp`, `gtest`, `benchmark`, `gersemi`, and `pre-commit` on Linux and macOS.
2. [examples/.clang-format](./examples/.clang-format): Google Style (`PointerAlignment: Left`, `ColumnLimit: 80`).
3. [examples/.clang-tidy](./examples/.clang-tidy): LLVM/Clang 23.1.5 config enforcing `google-*`, `abseil-*`, `modernize-deprecated-headers`, `modernize-use-std-print`, `bugprone-unchecked-optional-access`, `misc-include-cleaner`, coroutine safety checks, and Google `readability-identifier-naming` (with GSL, signed/unsigned, and `do-while` nits omitted).
4. [examples/.pre-commit-config.yaml](./examples/.pre-commit-config.yaml): Turnkey Git `pre-commit` enforcement for `clang-format`, `clang-tidy`, `gersemi`, and branch/secret hygiene (`.pixi/` excluded).

---

## Decision Trees

### Error Handling & Compiler Mode

```text
Need to report failure from a C++23 function?
├── Internal library, embedded, HFT, or robotics hot path?
│   └── Return std::expected<T, E> with enum class / trivial E; compile -fno-exceptions -fno-rtti; never call .value().
├── gRPC / Protobuf / host control-plane boundary needing rich messages?
│   └── Return absl::Status or absl::StatusOr<T> on the cold boundary; convert to std::expected internally.
└── Third-party SDK or application explicitly requires exceptions or dynamic_cast?
    └── Opt in explicitly via CMake -DENABLE_EXCEPTIONS=ON / -DENABLE_RTTI=ON; isolate throw/catch at boundaries.
```

### Coroutine & Async Execution Selection

```text
Considering C++23 coroutines (<coroutine> / <generator>) on LLVM/Clang 23.1 (Linux/macOS)?
├── Cold / async I/O / host orchestration path?
│   └── Use vetted libraries (stdexec / exec::task, Asio, libcoro, pw::async2) or guarded <generator>.
├── Building shared infra coroutine primitives?
│   └── Isolate in dedicated infra module; require Clang coro_* safety/HALO attributes + clang-tidy + ASan/TSan.
└── HFT / embedded / 1 kHz+ robotics hot path?
    ├── Can you guarantee zero heap allocation (fixed-pool operator new noexcept or verified Clang HALO)?
    │   └── Permitted ONLY after disassembly + benchmark verification.
    └── Otherwise -> Use synchronous state machines + lock-free SPSC rings instead.
```

### Container & Interop Selection

```text
Choosing a container or cross-language boundary?
├── Associative lookup:
│   ├── Small/static sorted table -> std::flat_map / std::flat_set (if available) or constinit sorted std::array.
│   └── Dynamic cold-path hash table -> absl::flat_hash_map / absl::flat_hash_set (never std::unordered_map).
├── Sequence / View:
│   ├── Hot-path pre-allocated fixed ring/array -> std::array + alignas(kCacheLineBytes) or absl::InlinedVector<T, N>.
│   └── Non-owning 1D / ND view -> std::span<T> (by value) / std::mdspan<T, Extents>.
└── Cross-language interop:
    ├── Rust (/rust-pro) -> Crubit (cpp_api_from_rust / rust_api_from_cpp); cxx or extern "C" if CMake needs Rust->C++.
    ├── C23 (/c-pro) or SPARK Ada (/ada-spark-pro) -> extern "C" header + std::out_ptr + RAII std::expected facade.
    └── Python 3.14 (/python-pro) -> nanobind (nb::ndarray) + pixi.
```

---

## References & Examples Index

- **Reference Manuals (`references/`)**:
  - [style_hierarchy_and_overrides.md](./references/style_hierarchy_and_overrides.md): 2-tier priority resolution (`Google` -> `Modern C++23 & HFT/Embedded/Robotics`), explicit C++ Core Guidelines removal rationale, `<cstdint>`/`int` rule, `<c[library]>` headers, tiered coroutine rules, and `pixi`/ABI portability.
  - [modern_cpp23_and_abseil.md](./references/modern_cpp23_and_abseil.md): C++23 idioms (`std::expected`, deducing `this`, `std::mdspan`, multidimensional `operator[]`, `std::out_ptr`, `std::move_only_function`, `<stdfloat>`, hardened coroutines), Abseil LTS `20260817.0+`, Google Test `v1.18.0+`, Google Benchmark `v1.10.0+`, and **Crubit** C++/Rust interop.
  - [hft_embedded_robotics_patterns.md](./references/hft_embedded_robotics_patterns.md): Hot/cold path contracts, architecture-aware cache-aligned (`128uz`/`64uz`) SPSC ring buffer, Halos/HFT safety interceptor, `std::mdspan` kernel, and `pixi`-compatible CMake options.
- **Baseline Examples (`examples/`)**:
  - [pixi.toml](./examples/pixi.toml): Hermetic Linux & macOS `conda-forge` C++23 workspace (`Clang 23.1.5`, `CMake 4.4.3+`, Abseil, GTest, GBench, `gersemi`, `pre-commit`).
  - [.clang-format](./examples/.clang-format): Google Style (`PointerAlignment: Left`, LLVM/Clang 23.1.5).
  - [.clang-tidy](./examples/.clang-tidy): Curated LLVM/Clang 23.1.5 linter & Google naming config.
  - [.pre-commit-config.yaml](./examples/.pre-commit-config.yaml): Git `pre-commit` enforcement (`clang-format`, `clang-tidy`, `gersemi`, hygiene).
