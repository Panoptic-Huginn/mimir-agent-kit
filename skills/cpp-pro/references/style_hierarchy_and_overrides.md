# Style Hierarchy, Project Overrides, and C++ Core Guidelines Carve-Outs

This manual defines the exact precedence rules and C++ Core Guidelines exceptions enforced by `/cpp-pro` for modern (November 2026) **C++23** engineering on **LLVM/Clang 23.1.5**.

---

## 1. Descending Priority Order (Conflict Resolution)

When two guidelines conflict, resolve the disagreement strictly in descending order (`#1` overrides `#2`, `#2` overrides `#3`):

| Priority | Authority | Role & Scope | Explicit Project Overrides |
| :--- | :--- | :--- | :--- |
| **1 (Highest)** | [Google C++ Style Guide](https://google.github.io/styleguide/cppguide.html) | Formatting, naming, header hygiene, scoping, integer type policy, Abseil preference, RTTI/exceptions discipline, modern ownership | Target **C++23** (`-std=c++23`); prefer `#pragma once` in new headers; use `<c[library]>` over `<[library].h>`; allow `<filesystem>` and `<chrono>`/`<ratio>` on non-RT host paths |
| **2** | [C++ Core Guidelines](https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines) | Value semantics, RAII, Rule of Zero, `const`/`constexpr` discipline, resource safety | Ignore GSL (`gsl::*`), exceptions-over-error-codes, pre-C++26 contracts, `<iostream>` formatting, naming/layout, signed/unsigned rules, non-`const` ref out-param ban; apply judgement on singletons/global state |
| **3** | Standard Industry Best Practices (**HFT, Embedded & Robotics**) | Hot/cold path separation, zero-alloc loops, lock-free concurrency, cache alignment, bounded WCET, `std::expected`, SIMD | Acts as domain tie-breaker whenever `#1` and `#2` leave multiple valid designs (e.g., `std::flat_map` vs `absl::flat_hash_map`, static arenas vs heap containers, non-`const` ref buffer reuse) |

---

## 2. Google C++ Style Guide (#1) Mandates & Modern C++23 Overrides

### 2.1 Fundamental Integer Types (`<cstdint>` + `int`-Only Rule)

With the **sole exception of `int`**, **all** other built-in fundamental integer types (`short`, `long`, `long long`, `unsigned short`, `unsigned int`, `unsigned long`, `unsigned long long`) are prohibited. Every other fundamental integer type **shall** come from modern `<cstdint>` (such as `int8_t`, `uint8_t`, `int16_t`, `uint16_t`, `int32_t`, `uint32_t`, `int64_t`, `uint64_t`, `intptr_t`, `uintptr_t`), alongside `<cstddef>` for `size_t` and `ptrdiff_t`.

- **Qualification**: Unqualified `<cstdint>` names (`int16_t`, `uint32_t`, `int64_t`) are standard per Google Style; `std::int16_t` / `std::uint32_t` is also acceptable when a codebase mandates explicit `std::` qualification consistently.
- **Linter Enforcement**: Enable `google-runtime-int` in `.clang-tidy` to catch every stray `short`, `long`, or `unsigned` keyword automatically.
- **Unsigned Usage Override**: Unlike Google Style's general reluctance toward unsigned types, `/cpp-pro` ignores signed/unsigned bans so `uint8_t`, `uint16_t`, `uint32_t`, `uint64_t`, and `size_t` can be used cleanly for wire protocols, MMIO registers, bitmasks, nanosecond timestamps, and power-of-two ring-buffer wraparound arithmetic.

### 2.2 C Standard Library Headers (`<c[library]>` over `<[library].h>`)

Always use C++ `<c[library]>` wrapper headers instead of legacy C `<[library].h>` headers:

- Use `<cstdint>`, `<cstddef>`, `<cmath>`, `<cstring>`, `<cassert>`, `<cstdlib>`, `<cstdio>`, `<climits>`, `<cerrno>`.
- Never include `<stdint.h>`, `<stddef.h>`, `<math.h>`, `<string.h>`, `<assert.h>`, `<stdlib.h>`, `<stdio.h>` in `.cc` or C++-only `.h` files.
- **Exceptions**: OS/POSIX headers (`<unistd.h>`, `<sys/mman.h>`, `<pthread.h>`) and shared C23/C++23 `extern "C"` ABI boundary headers maintained under `/c-pro` keep `.h` compatibility headers (`<stdint.h>` inside `#ifdef __cplusplus` dual-language headers).
- **Linter Enforcement**: Enable `modernize-deprecated-headers` in `.clang-tidy`.

### 2.3 Header Guards, Modules & Standard Library Boundaries

| Rule Area | Upstream Google C++ Style Guide | `/cpp-pro` November 2026 Policy |
| :--- | :--- | :--- |
| **C++ Standard** | Targets C++20 baseline | Target **C++23 (`-std=c++23`)** and prefer C++23 constructs everywhere |
| **Header Guards** | `#ifndef PROJECT_PATH_FILE_H_` | Prefer **`#pragma once`** in new headers (consistent with `/c-pro`); use `#ifndef` macro guards in existing repos that already use them |
| **Include What You Use** | Mandatory direct includes | Enforced via `misc-include-cleaner` in `.clang-tidy` |
| **Forward Declarations** | Ban for external/unowned symbols | Enforce strictly; include headers for third-party / Abseil / `std::` symbols |
| **Pointer & Reference Alignment** | Left alignment (`int* p`, `const T& r`) | Enforced via `DerivePointerAlignment: false` and `PointerAlignment: Left` in `.clang-format` |
| **C++20/23 Modules** | Disallowed | **Disallowed**: retain `#pragma once` headers for reliable `clang-tidy`, `misc-include-cleaner`, `ccache`, and CMake/Vcpkg cross-compilation |
| **Coroutines** | Only via approved libraries | Only via project-approved runtime libraries (never hand-roll promise/awaitable types) |
| **`<cfenv>` & `long double`** | Disallowed | **Disallowed** (non-portable FPU environment and ABI sizing) |
| **`<filesystem>` & `<chrono>`/`<ratio>`** | `<filesystem>` & `<ratio>` disallowed | **Allowed** on non-real-time host, CLI, and test paths; **forbidden** on HFT/embedded/robotics real-time hot paths |
| **Checked Downcasts** | Prefer `absl::down_cast` | Use `absl::down_cast<Derived*>(base)` instead of unchecked `static_cast` when RTTI/debug assertions apply |
| **C++/Rust Interop Naming** | Naming exceptions allowed for Rust interop | Allow Rust/Crubit symbol parity at `cpp_api_from_rust` / `rust_api_from_cpp` boundaries |

---

## 3. C++ Core Guidelines (#2) — The 8 Explicit Carve-Outs

Apply C++ Core Guidelines for RAII (`R.*`), Rule of Zero (`C.20`), `const`/`constexpr` (`Con.*`), and resource ownership—**except** for the following 8 explicitly overridden or ignored rules:

### 3.1 Summary Matrix

| Core Guideline Category | Upstream Guidance | `/cpp-pro` November 2026 Mandate |
| :--- | :--- | :--- |
| **1. GSL (`gsl::*`)** | Use `gsl::span`, `gsl::not_null`, `gsl::owner`, `gsl::narrow` | **IGNORE COMPLETELY**: Zero `Microsoft.GSL` dependency. Use C++23 `std::span`, `std::mdspan`, `std::unique_ptr`, `absl::Span`, `absl::Cleanup`, and checked casts |
| **2. Exceptions (`E.*`)** | Throw exceptions over returning error codes | **IGNORE**: Standardize on C++23 `std::expected<T, E>` (with `-fno-exceptions -fno-rtti` by default, while allowing users to explicitly opt into RTTI and/or exceptions per project). Reserve `absl::Status`/`StatusOr` for gRPC/Protobuf boundaries |
| **3. Contracts (`I.6`–`I.8`)** | Use C++ contract annotations | **DO NOT USE YET**: Defer language contracts until **C++26**. Use `ABSL_CHECK`/`ABSL_DCHECK`, `<cassert>`, `static_assert`, `requires` concepts, and `std::expected` |
| **4. `<iostream>` (`SL.io.*`)** | Stream state & `<<` formatting | **BYPASS**: Use C++23 `std::print` / `std::println` (`<print>`) and `std::format` (`<format>`) for host output; `absl::StrFormat` or binary rings on hot paths |
| **5. Naming & Layout (`NL.*`)** | Core Guidelines naming/layout | **IGNORE**: Defer 100% to `#1` Google Style (`CamelCase`, `lower_case_`, `kConstant`) enforced via `.clang-format` and `readability-identifier-naming` |
| **6. Signed vs. Unsigned (`ES.100`–`ES.107`)** | Avoid unsigned except bitfields | **IGNORE**: Use `uint8_t`, `uint16_t`, `uint32_t`, `uint64_t`, `size_t` freely for protocols, registers, bitmasks, timestamps, and ring indices |
| **7. Non-`const` Ref Out-Params (`F.16`–`F.21`)** | Return values; avoid non-`const` ref out-params | **IGNORE**: Non-`const` reference outputs and in/out params are permitted per Google Style (inputs first, outputs last), ideal for zero-alloc buffer reuse |
| **8. Singletons / Global State (`I.2`, `I.3`)** | Strictly ban global state / singletons | **USE JUDGEMENT**: Avoid mutable globals by default, but permit intentional `constinit` tables, MMIO/HAL registries, static RT memory pools, calibrated clocks, and async log sinks when justified (`// NOLINT(...)`) |

### 3.2 Side-by-Side Idiom Examples

#### Carve-Out #1 & #2: `std::expected<T, E>` Instead of Exceptions or GSL

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

Remember: when compiling with the default `-fno-exceptions`, **never** call `res.value()` (which throws `std::bad_expected_access` or aborts depending on stdlib). Always check `if (!res) { return std::unexpected(res.error()); }`, dereference `*res` after checking (`bugprone-unchecked-optional-access` verifies this), or use `.and_then()` / `.transform()` / `.value_or()`.

#### Carve-Out #4: `<print>` Instead of `<iostream>` Formatting

```cpp
// BAD: Mutates stream state, drags heavy <iostream> parsing, and flushes via endl.
// std::cout << "Latency: 0x" << std::hex << std::setw(8) << cycles << std::endl;

// GOOD (C++23): Stateless, type-safe, faster, and locale-safe.
#include <cstdint>
#include <print>

void LogDiagnostics(uint32_t frame_id, double latency_us) {
  std::println("frame={:#010x} latency_us={:.3f}", frame_id, latency_us);
}
```

#### Carve-Out #7 & #6: Non-`const` Reference Buffer Reuse + `<cstdint>` Unsigned Indices

```cpp
// GOOD (C++23 / HFT & Robotics): Inputs first, non-const reference output buffer
// last for zero-allocation hot-path reuse, using <cstdint> + int only.
#include <cstddef>
#include <cstdint>
#include <span>

[[nodiscard]] int FilterJointTorques(std::span<const float> raw_torques,
                                     uint32_t gain_q16,
                                     std::span<float>& out_filtered) noexcept;
```

#### Carve-Out #8: Judicious Global State / Singletons

When a singleton or static pool is genuinely the cleanest design (for example, a pre-allocated DMA slab pool, hardware watchdog registry, or calibrated monotonic clock anchor):

1. Prefer `constinit` for zero-cost compile-time initialization (`constinit HalosClockAnchor g_clock_anchor{};`), eliminating static initialization order fiasco.
2. If lazy runtime initialization is required on a cold path, use a function-local Meyer's singleton returning a `T&` (C++ guarantees thread-safe initialization).
3. Annotate intentionally mutable static handles with `// NOLINT(cppcoreguidelines-avoid-non-const-global-variables)` and a one-line comment explaining the thread-safety and lifetime invariant.
