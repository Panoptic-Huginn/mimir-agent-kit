# Style Hierarchy, Project Overrides, Coroutines & ABI Portability

This manual defines the exact 2-tier authority precedence rules, Google C++ Style overrides, tiered C++23 coroutine rules, and `pixi`/standard-library ABI guidelines enforced by `/cpp-pro` for modern (November 2026) **ISO C++23** engineering on **LLVM/Clang 23.1.5** across **Linux** and **macOS** (**Windows/MSVC is unsupported**).

---

## 1. Descending 2-Tier Priority Order (Conflict Resolution)

When two guidelines intersect, resolve the disagreement strictly in descending order (`#1` overrides `#2`):

| Priority | Authority | Role & Scope | Explicit Project Overrides |
| :--- | :--- | :--- | :--- |
| **1 (Highest)** | [Google C++ Style Guide](https://google.github.io/styleguide/cppguide.html) | Formatting, naming, header hygiene, scoping, integer type policy, Abseil preference, RTTI/exceptions discipline, non-`const` ref out-params, `do-while` allowance, modern ownership | Target **ISO C++23 (`-std=c++23`)** on Linux & macOS only; prefer `#pragma once` in new headers; use `<c[library]>` over `<[library].h>`; ignore signed-only integer reluctance (`uint*_t`/`size_t`); allow `<filesystem>` & `<chrono>`/`<ratio>` on non-RT cold paths; apply tiered C++23 coroutine override |
| **2** | **Modern ISO C++23 & HFT / Embedded / Robotics Best Practices** | RAII, Rule of Zero, value semantics, `const`/`constexpr`/`consteval`, hot/cold separation, zero-alloc loops, lock-free concurrency, `128uz`/`64uz` cache alignment, bounded WCET, `std::expected`, `<print>`, SIMD/`std::mdspan` | Governs idioms, safety, and performance whenever `#1` leaves multiple valid designs (e.g., `std::flat_map` vs. `absl::flat_hash_map`, static arenas vs. heap containers, `std::out_ptr` C23 wrappers, hot-path zero-alloc gates) |

### Why C++ Core Guidelines Is Excluded as a Style Authority

`/cpp-pro` intentionally **removes** the [C++ Core Guidelines](https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines) as a governing style authority (retaining only cherry-picked AST safety/UB/coroutine checks in `.clang-tidy`):

- **C++17/C++20 Anchor (`v0.8`)**: Even in 2026, the Core Guidelines still targets C++17/C++20 with zero coverage of C++23 `<expected>`, `<print>`, `<format>`, `<mdspan>`, or `std::out_ptr`.
- **Conflict Density**: Its core pillars conflict directly with Google C++ Style and deterministic HFT/Embedded/Robotics engineering across too many areas:
  1. **Banned `Microsoft.GSL` (`gsl::*`)**: Never depend on `Microsoft.GSL` or use `gsl::span`, `gsl::not_null`, `gsl::owner`, or `gsl::narrow`. Use `std::span`, `std::mdspan`, smart pointers, `absl::Span`, and `absl::Cleanup`.
  2. **Exceptions (`E.*`)**: `/cpp-pro` standardizes on **`std::expected<T, E>`** with `-fno-exceptions -fno-rtti` by default (plus explicit CMake `ENABLE_EXCEPTIONS` / `ENABLE_RTTI` opt-in flags) rather than throwing exceptions for recoverable errors.
  3. **Contracts (`I.6`–`I.8`)**: `Expects()`/`Ensures()` macros are rejected; defer language contracts until **C++26** and use `ABSL_CHECK`/`ABSL_DCHECK`, `<cassert>`, `static_assert`, `requires` concepts, and `std::expected`.
  4. **`<iostream>` (`SL.io.*`)**: Stream formatting is bypassed in favor of C++23 **`std::print`** / **`std::println`** (`<print>`) and **`std::format`** (`<format>`) on cold paths and binary SPSC rings on hot loops.
  5. **Naming, Signed/Unsigned, Out-Params & `do-while` (`NL.*`, `ES.*`, `F.*`)**: Google Style already governs naming, permits non-`const` ref out/in-out parameters for zero-allocation buffer reuse, permits `do-while`, and `/cpp-pro` explicitly allows `<cstdint>` unsigned arithmetic.
  6. **Judicious Static/Global Handles (`I.2`, `I.3`)**: Avoid arbitrary mutable globals, while permitting intentional `constinit` lookup tables, function-local Meyer's singletons, MMIO/HAL registries, pre-allocated static arenas, calibrated clock anchors, and async telemetry sinks annotated with `// NOLINT(cppcoreguidelines-avoid-non-const-global-variables)`.

---

## 2. Google C++ Style Guide (#1) Mandates & Modern C++23 Overrides

### 2.1 Fundamental Integer Types (`<cstdint>` + `int`-Only Rule)

With the **sole exception of `int`**, **all** other built-in fundamental integer types (`short`, `long`, `long long`, `unsigned short`, `unsigned int`, `unsigned long`, `unsigned long long`) are prohibited. Every other fundamental integer type **shall** come from modern `<cstdint>` (such as `int8_t`, `uint8_t`, `int16_t`, `uint16_t`, `int32_t`, `uint32_t`, `int64_t`, `uint64_t`, `intptr_t`, `uintptr_t`), alongside `<cstddef>` for `size_t` (`0uz`) and `ptrdiff_t` (`0z`).

- **Qualification**: Unqualified `<cstdint>` names (`int16_t`, `uint32_t`, `int64_t`) are standard per Google Style; `std::int16_t` / `std::uint32_t` is also acceptable when a codebase mandates explicit `std::` qualification consistently.
- **Linter Enforcement**: Enable `google-runtime-int` in `.clang-tidy` to catch every stray `short`, `long`, or `unsigned` keyword automatically.
- **Unsigned Usage Override**: Unlike Google Style's general reluctance toward unsigned types, `/cpp-pro` freely uses `uint8_t`, `uint16_t`, `uint32_t`, `uint64_t`, and `size_t` (`0uz`) for wire protocols, MMIO registers, bitmasks, nanosecond timestamps, and power-of-two ring-buffer wraparound arithmetic.

### 2.2 C Standard Library Headers (`<c[library]>` over `<[library].h>`)

Always use C++ `<c[library]>` wrapper headers instead of legacy C `<[library].h>` headers:

- Use `<cstdint>`, `<cstddef>`, `<cmath>`, `<cstring>`, `<cassert>`, `<cstdlib>`, `<cstdio>`, `<climits>`, `<cerrno>`.
- Never include `<stdint.h>`, `<stddef.h>`, `<math.h>`, `<string.h>`, `<assert.h>`, `<stdlib.h>`, `<stdio.h>` in `.cc` or C++-only `.h` files.
- **Exceptions**: OS/POSIX headers (`<unistd.h>`, `<sys/mman.h>`, `<pthread.h>`) and shared C23/C++23 `extern "C"` ABI boundary headers maintained under `/c-pro` keep `.h` compatibility headers (`<stdint.h>` inside `#ifdef __cplusplus` dual-language headers).
- **Linter Enforcement**: Enable `modernize-deprecated-headers` in `.clang-tidy`.

### 2.3 Header Guards, Modules & Standard Library Boundaries

| Rule Area | Upstream Google C++ Style Guide | `/cpp-pro` November 2026 Policy |
| :--- | :--- | :--- |
| **C++ Standard** | Targets C++20 baseline | Target **ISO C++23 (`-std=c++23`)** on Linux & macOS only (**Windows/MSVC unsupported**); prefer C++23 idioms everywhere |
| **Header Guards** | `#ifndef PROJECT_PATH_FILE_H_` | Prefer **`#pragma once`** in new headers (consistent with `/c-pro`); use `#ifndef` macro guards in existing repos that already use them |
| **Include What You Use** | Mandatory direct includes | Enforced via `misc-include-cleaner` in `.clang-tidy` |
| **Forward Declarations** | Ban for external/unowned symbols | Enforce strictly; include headers for third-party / Abseil / `std::` symbols |
| **Pointer & Reference Alignment** | Left alignment (`int* p`, `const T& r`) | Enforced via `DerivePointerAlignment: false` and `PointerAlignment: Left` in `.clang-format` |
| **C++20/23 Modules** | Disallowed | **Disallowed**: retain `#pragma once` headers for reliable `clang-tidy`, `misc-include-cleaner`, `ccache`, and CMake + `pixi` cross-compilation |
| **Coroutines (`<coroutine>`)** | Only via project-approved libraries; no custom promises | **Tiered C++23 Override** (Section 2.4): allowed freely on cold paths via vetted libraries; hardened custom infra primitives permitted under Clang 23 attributes; zero-alloc gate on hot paths |
| **`<cfenv>` & `long double`** | Disallowed | **Disallowed** (non-portable FPU environment and ABI sizing) |
| **`<filesystem>` & `<chrono>`/`<ratio>`** | `<filesystem>` & `<ratio>` disallowed | **Allowed** on non-real-time host, CLI, and test paths; **forbidden** on HFT/embedded/robotics real-time hot paths |
| **Checked Downcasts** | Prefer `absl::down_cast` | Use `absl::down_cast<Derived*>(base)` instead of unchecked `static_cast` when RTTI/debug assertions apply |
| **C++/Rust Interop Naming** | Naming exceptions allowed for Rust interop | Allow Rust/Crubit symbol parity at `cpp_api_from_rust` / `rust_api_from_cpp` boundaries |

### 2.4 Tiered C++23 Coroutines Policy (LLVM/Clang 23.1, Linux & macOS Only)

Upstream Google C++ Style restricts coroutines heavily because C++20 shipped without standard coroutine primitives, coroutine suspension introduces subtle dangling-reference bugs, and cross-platform codebases must cope with historical Windows/MSVC coroutine codegen, handle-state (`.done()`), and SEH unwinding bugs (`clang-cl` targeting the Windows ABI inherits those SEH hazards).

Because `/cpp-pro` targets **LLVM/Clang 23.1.5** strictly on **Linux** and **macOS** (excluding Windows/MSVC) and leverages LLVM's mature `coro-split` / `musttail` symmetric-transfer lowering and Heap Allocation Elision Optimization (HALO)—which both operate cleanly under `-fno-exceptions -fno-rtti`—we apply a **3-tier coroutine policy**:

1. **Tier 1 — Cold / Async I/O / Host Orchestration Paths (Permitted via Vetted Libraries)**:
   - Use coroutines freely for asynchronous gRPC/networking, telemetry pipelines, state-machine orchestration, and CLI tooling via vetted libraries: **`stdexec` (P2300 `exec::task`)**, **`asio::awaitable`**, **`libcoro`**, **`folly::coro`**, Pigweed **`pw::async2`**, or C++23 **`std::generator`** (`<generator>`, guarded by `#if __has_include(<generator>)` since `libstdc++` provides it while some `libc++` builds omit it).
2. **Tier 2 — Dedicated Infrastructure Custom Primitives (Conditionally Permitted)**:
   - Never hand-roll ad-hoc `promise_type` machinery inside domain or business logic.
   - Dedicated infrastructure modules *may* define custom `Task<T>` / `Generator<T>` / awaitable primitives **only if** all four guards are satisfied:
     1. Annotate the coroutine return type with Clang 23 lifetime and HALO attributes: `[[clang::coro_return_type, clang::coro_lifetimebound, clang::coro_await_elidable]]` (adding `[[clang::coro_only_destroy_when_complete]]` when the type is never destroyed while suspended).
     2. Implement `void unhandled_exception() noexcept` cleanly for `-fno-exceptions` compatibility (e.g., `noexcept` noop or `std::terminate()`).
     3. Pass all four coroutine safety checks in `.clang-tidy`: `cppcoreguidelines-avoid-capturing-lambda-coroutines`, `cppcoreguidelines-avoid-reference-coroutine-parameters`, `cppcoreguidelines-no-suspend-with-lock`, and `misc-coroutine-hostile-raii`.
     4. Verify with `AddressSanitizer` and `ThreadSanitizer` tests (pass arguments by value, never capture locals inside coroutine lambdas, and never hold mutexes/locks across `co_await`).
3. **Tier 3 — HFT / Embedded / 1 kHz+ Robotics Hot Paths (Zero-Allocation Gate)**:
   - Heap-allocating coroutines are **forbidden** on real-time hot paths.
   - Coroutines may run on hot paths **only** when zero dynamic heap allocation is structurally guaranteed—either via a fixed-pool/arena `promise_type::operator new(...) noexcept` paired with `get_return_object_on_allocation_failure()`, or via verified Clang HALO frame elision confirmed through disassembly and Google Benchmark regression checks. Otherwise, use deterministic synchronous state machines and lock-free SPSC rings.

---

## 3. `pixi` Dependencies & Platform-Native C++ Stdlib ABI Portability

Manage C++ dependencies (`abseil-cpp`, `gtest`, `benchmark`, `nanobind`) and toolchains (`clangxx`, `clang-tools`, `lld`, `cmake`, `ninja`, `ccache`, `gersemi`, `pre-commit`) using **`pixi`** (`pixi.toml` + `pixi.lock` via `conda-forge`; consult `/python-pro` for `pixi` CLI patterns). Inject `CMAKE_PREFIX_PATH="$CONDA_PREFIX"` inside `CMakePresets.json` (aligned with `/cmake-pro`'s `pixi` + `$CONDA_PREFIX` standard; fall back to host/sysroot `find_package(<Pkg> CONFIG REQUIRED)` only in air-gapped or bare-metal embedded SDKs).

### Platform-Native C++ Stdlib ABI Rule

Never mix C++ standard library ABIs across compiled binaries:

- **Linux (`linux-64`, `linux-aarch64`)**: Link against **`libstdc++`** (the default ABI used by `conda-forge` C++ packages such as `abseil-cpp`, `gtest`, and `benchmark`). **Never** force `-stdlib=libc++` on Linux when linking `conda-forge` C++ libraries unless you rebuild every dependency from source against `libc++`.
- **macOS (`osx-arm64`)**: Link against **`libc++`** (the native Darwin C++ ABI).
- **Guard Skew-Sensitive C++23 Headers**: Because Linux `libstdc++` and macOS `libc++` ship C++23 library components on slightly different schedules, always probe optional headers/features with standard feature-test macros rather than assuming universal presence:

| C++23 Feature / Header | Linux (`libstdc++` + Clang 23) | macOS (`libc++` + Clang 23) | Required Guard |
| :--- | :--- | :--- | :--- |
| `<expected>`, `<print>`, `<format>`, `<coroutine>` | Supported (`-fno-exceptions` safe) | Supported (`-fno-exceptions` safe) | Standard `-std=c++23` |
| `<mdspan>` (`std::mdspan`) | `libstdc++ >= 15` (absent in GCC 14 headers) | Supported | `#if __has_include(<mdspan>)` (fallback `MatrixView2D` / `Kokkos::mdspan`) |
| `<generator>` (`std::generator`) | Supported | Check availability | `#if __has_include(<generator>)` |
| `<flat_map>` / `<flat_set>` | Check availability | Supported | `#if __has_include(<flat_map>)` |
| `<stdfloat>` / `<spanstream>` | Supported | Check availability | `#if __has_include(<stdfloat>)` / `__has_include(<spanstream>)` |
| `std::move_only_function` (`<functional>`) | Supported | Check availability | `#ifdef __cpp_lib_move_only_function` |
| `std::start_lifetime_as` (`<memory>`) | Check availability | Check availability | `#ifdef __cpp_lib_start_lifetime_as` (fallback `std::bit_cast` / `memcpy`) |

---

## 4. Key Idiom Examples (Zero GSL, `std::expected`, `<print>`, Buffer Reuse)

### 4.1 `std::expected<T, E>` Instead of Exceptions or GSL

```cpp
// BAD: Throws exceptions, pulls in GSL, and uses built-in `unsigned long`.
// gsl::not_null<const unsigned long*> ParsePacket(gsl::span<const uint8_t> buf);

// GOOD (C++23): Zero-overhead deterministic error handling, no GSL, <cstdint>.
#pragma once

#include <cstdint>
#include <expected>
#include <span>

enum class ParseError : uint8_t {
  kTooShort = 1,
  kBadChecksum = 2,
};

struct FrameHeader {
  uint32_t sequence_id;
  uint16_t payload_bytes;
};

[[nodiscard]] std::expected<FrameHeader, ParseError> ParseHeader(
    std::span<const uint8_t> bytes) noexcept;
```

Under the default `-fno-exceptions`, **never** call `res.value()`. Always check `if (!res) { return std::unexpected(res.error()); }`, dereference `*res` only after checking (`bugprone-unchecked-optional-access` verifies this), or chain `.and_then()` / `.transform()` / `.value_or()`.

### 4.2 `<print>` Instead of `<iostream>` Formatting

```cpp
// BAD: Mutates stream state, pulls heavy <iostream> locale machinery, flushes via endl.
// std::cout << "Latency: 0x" << std::hex << std::setw(8) << cycles << std::endl;

// GOOD (C++23): Stateless, type-safe, faster, and locale-safe.
#include <cstdint>
#include <print>

void LogDiagnostics(uint32_t frame_id, double latency_us) {
  std::println("frame={:#010x} latency_us={:.3f}", frame_id, latency_us);
}
```

### 4.3 By-Value `std::span` vs. Non-`const` Reference Container Reuse (`0uz`)

Pass `std::span<T>` **by value** (it is already a non-owning `{pointer, size}` handle—never write `std::span<float>&`), and reserve non-`const` reference out-parameters (`std::vector<float>& out_scratch` or `JointTelemetryFrame& out_frame`) for zero-allocation buffer/capacity reuse on hot paths:

```cpp
#pragma once

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <expected>
#include <span>
#include <vector>

enum class FilterError : uint8_t {
  kSpanMismatch = 1,
  kEmptyInput = 2,
};

// GOOD: std::span passed by value; deterministic std::expected status.
[[nodiscard]] inline std::expected<void, FilterError> FilterJointTorques(
    std::span<const float> raw_torques, uint32_t gain_q16,
    std::span<float> out_filtered) noexcept {
  if (raw_torques.empty()) {
    return std::unexpected(FilterError::kEmptyInput);
  }
  if (out_filtered.size() < raw_torques.size()) {
    return std::unexpected(FilterError::kSpanMismatch);
  }
  const float scale = static_cast<float>(gain_q16) / 65536.0F;
  for (size_t i = 0uz; i < raw_torques.size(); ++i) {
    out_filtered[i] = raw_torques[i] * scale;
  }
  return {};
}

// GOOD: Non-const reference out-parameter reuses pre-reserved vector capacity.
inline void NormalizeIntoScratch(std::span<const float> samples,
                                 std::vector<float>& out_scratch) noexcept {
  out_scratch.resize(samples.size());
  std::ranges::copy(samples, out_scratch.begin());
}
```

### 4.4 Judicious `constinit` & Meyer's Singletons

When a static table or HAL handle is genuinely the cleanest design (e.g., a pre-allocated DMA slab pool, hardware watchdog registry, or calibrated monotonic clock anchor):

1. Prefer `constinit` for zero-cost compile-time initialization (`constinit HalosClockAnchor g_clock_anchor{};`), eliminating static initialization order fiasco.
2. If lazy runtime initialization is required on a cold path, use a function-local Meyer's singleton returning `T&` (guaranteed thread-safe by C++).
3. Annotate intentionally mutable static handles with `// NOLINT(cppcoreguidelines-avoid-non-const-global-variables)` and a one-line comment explaining the thread-safety and lifetime invariant.
