# Modern C++23 Constructs, Abseil, Testing, Benchmarking, and Crubit Interop

Reference guide for November 2026 **C++23** (`LLVM/Clang 23.1.5`) standard library idioms, **Abseil (`absl` LTS `20260817.0+`)**, **Google Test (`v1.18.0+`)**, **Google Benchmark (`v1.10.0+`)**, and zero-overhead **Crubit** C++/Rust interoperability.

---

## 1. Preferred Modern C++23 Constructs

Always favor C++23 idioms over pre-C++20 workarounds:

### 1.1 Monadic `std::expected<T, E>` Pipelines (`<expected>`)

Replace exception-throwing error flows, `(bool, out_param)` pairs, and ad-hoc `int` error codes with monadic `std::expected<T, E>`:

```cpp
#pragma once

#include <cstdint>
#include <expected>
#include <span>

enum class OrderError : uint8_t {
  kMalformedFrame = 1,
  kRiskLimitExceeded = 2,
};

struct DecodedOrder {
  uint64_t order_id;
  int64_t price_ticks;
  int32_t qty;
};

[[nodiscard]] std::expected<DecodedOrder, OrderError> DecodeWireOrder(
    std::span<const uint8_t> packet) noexcept;

[[nodiscard]] std::expected<DecodedOrder, OrderError> CheckRiskLimits(
    const DecodedOrder& order) noexcept;

[[nodiscard]] inline std::expected<int64_t, OrderError> ValidateOrderNotional(
    std::span<const uint8_t> packet) noexcept {
  return DecodeWireOrder(packet)
      .and_then(CheckRiskLimits)
      .transform([](const DecodedOrder& valid) noexcept -> int64_t {
        return valid.price_ticks * int64_t{valid.qty};
      });
}
```

### 1.2 Deducing `this` (Explicit Object Parameters)

Eliminate CRTP boilerplate, duplicated `const`/non-`const` overloads, and `std::function` recursive lambdas using C++23 explicit object parameters (`this Self&& self`):

```cpp
#pragma once

#include <cstddef>
#include <utility>
#include <vector>

class TelemetryBuffer {
 public:
  // Single template handles lvalue, const lvalue, rvalue, and const rvalue.
  template <typename Self>
  [[nodiscard]] auto&& At(this Self&& self, size_t index) noexcept {
    return std::forward<Self>(self).samples_[index];
  }

 private:
  std::vector<double> samples_;
};
```

### 1.3 `std::mdspan` (`<mdspan>`), `std::flat_map` (`<flat_map>`), and Ranges

- **`std::mdspan`**: Zero-copy non-owning multi-dimensional view over contiguous storage (`float*`, `std::vector`, DMA buffers) with compile-time/runtime strides—ideal for robotics Jacobians, Kalman covariance matrices, and image tiles without pulling heavy tensor wrappers into public APIs.
- **`std::flat_map` / `std::flat_set`**: Sorted contiguous vector-backed associative containers offering cache-friendly binary search and compact memory footprints for small/medium read-mostly lookup tables.
- **`std::ranges` C++23 Views & `std::ranges::to`**: Use `std::views::zip`, `std::views::enumerate`, `std::views::chunk`, `std::views::stride`, and `std::ranges::to<std::vector>()` on cold paths and test code; verify via benchmarks before putting range adaptors in innermost tight loops.
- **Additional C++23 Primitives**:
  - `std::print` / `std::println` (`<print>`) and `std::format` (`<format>`) with custom `std::formatter<T>`.
  - `std::byteswap` (`<bit>`) for endianness conversion in network/CAN/EtherCAT parsers (`uint16_t`, `uint32_t`, `uint64_t`).
  - `std::to_underlying` (`<utility>`) for converting `enum class` values cleanly without verbose `static_cast`.
  - `std::unreachable()` (`<utility>`) and `[[assume(expr)]]` for optimizer hints when an invariant is proven externally (paired with `ABSL_DCHECK` in debug builds).
  - `if consteval` for clean compile-time vs. SIMD runtime branching inside `constexpr` functions.
  - `0uz` (`size_t`) and `0z` (`ptrdiff_t`) integer literal suffixes.

---

## 2. Abseil (`absl` LTS `20260817.0+`) Integration Guide

Per Google C++ Style Guide #1, prefer **Abseil** where it provides measurably better hash tables, memory locality, compile-time thread-safety checks, or string utilities than the standard library:

| Domain | Recommended Choice | Rationale & Usage Rule |
| :--- | :--- | :--- |
| **Unordered Hash Map / Set** | `absl::flat_hash_map`, `absl::flat_hash_set` | Swiss-table open addressing avoids per-node heap allocations and cache misses of `std::unordered_map` |
| **Pointer-Stable Hash Map** | `absl::node_hash_map` | Only when pointer/reference stability across rehashes is required |
| **Small-Buffer / Fixed Arrays** | `absl::InlinedVector<T, N>`, `absl::FixedArray<T>` | Stack-buffered storage avoids heap allocations for typical small sizes |
| **Non-Owning Callable** | `absl::FunctionRef<Sig>` | Zero-allocation callback reference (use instead of `std::function` when callable does not outlive the call) |
| **String Building & Matching** | `absl::StrCat`, `absl::StrAppend`, `absl::StrSplit`, `absl::StrJoin`, `absl::StartsWith`, `absl::StrContains` | Single-pass size calculation; faster and cleaner than `std::ostringstream` or repeated `+` |
| **Formatting** | `<print>` / `<format>` (C++23) or `absl::StrFormat` | Use `std::println`/`std::format` as default; `absl::StrFormat` when formatting directly into Abseil string pipelines |
| **Error Propagation** | `std::expected<T, E>` (Default) / `absl::StatusOr<T>` (Boundaries) | Standardize on `std::expected<T, E>` everywhere internally and on hot paths; use `absl::Status` / `absl::StatusOr<T>` at gRPC/Protobuf/host control-plane boundaries needing rich diagnostics |
| **Synchronization** | `absl::Mutex` + `ABSL_GUARDED_BY` / `ABSL_EXCLUSIVE_LOCKS_REQUIRED` | Smaller than `std::mutex`, supports `Condition` predicates, and activates Clang Thread-Safety Analysis (`-Wthread-safety`) |
| **Downcasting & Assertions** | `absl::down_cast`, `ABSL_CHECK`, `ABSL_DCHECK` | Debug-checked downcasts and fatal invariant assertions (`cppcoreguidelines` / `bugprone-assert-side-effect` aware) |

---

## 3. Unit Testing (Google Test `v1.18.0+`) & Benchmarking (Google Benchmark `v1.10.0+`)

### 3.1 Google Test (`GTest::gtest_main`, `GTest::gmock`)

- Keep unit tests fast, deterministic, hermetic (no network, no real wall-clock sleeps, no external data files), and registered with CMake `gtest_discover_tests()` (`/cmake-pro`).
- Always test `std::expected<T, E>` success and every error variant explicitly (`ASSERT_TRUE(res.has_value())`, `EXPECT_EQ(res.error(), ...)`).
- Use `TEST_P` + `INSTANTIATE_TEST_SUITE_P` for boundary value sweeps and `EXPECT_DEATH_IF_SUPPORTED` for `ABSL_CHECK` invariant tests.
- Run the entire test suite under `-fsanitize=address,undefined` and `-fsanitize=thread` presets before claiming completion.

### 3.2 Google Benchmark (`benchmark::benchmark_main`)

- Guard every computed output with `benchmark::DoNotOptimize(val)` and memory writes with `benchmark::ClobberMemory()` to defeat dead-code elimination.
- Exclude fixture setup/reset cycles using `benchmark::ScopedPauseTiming` (Google Benchmark `v1.10.0+`) rather than manual `PauseTiming()`/`ResumeTiming()` pairs.
- Use `BENCHMARK_NAMED` for readable parameterized suites, report `state.SetItemsProcessed(...)` / `state.SetBytesProcessed(...)`, and verify algorithmic scaling with `->RangeMultiplier(2)->Range(64, 65536)->Complexity()`.
- Collect hardware PMU counters on Linux via `--benchmark_perf_counters=CYCLES,INSTRUCTIONS,L1-DCACHE-LOAD-MISSES,BRANCH-MISSES` and inspect statistical shifts using Google Benchmark's `compare.py`.

---

## 4. Cross-Language Interoperability (Crubit, C23, SPARK Ada, Python)

### 4.1 Bidirectional C++ / Rust Interop with **Crubit** (`/rust-pro`)

For projects integrating C++23 and **Rust 1.99.1+**, strongly prefer **[Crubit](https://crubit.rs)** (`google/crubit`) over hand-written `extern "C"` shims or manual IDL codegen:

- **Why Crubit**:
  - Reads real C++ headers and Rust crates at build time—zero IDL files, zero hand-maintained glue, zero ABI drift.
  - Zero copies and zero extra heap allocations across the boundary.
  - Supports **non-`#[repr(C)]`** Rust structs and enums passed by value, plus idiomatic types (`Option`/`std::optional`, `Vec`/`std::vector`, `std::unique_ptr`, `&str`/`rs::StrRef`, slices, callbacks, `absl::Status`).
  - Maps Rust traits (`Display`, `Clone`, `Default`) to C++ operators/special member functions and C++ operators (`+`, `==`) to Rust traits (`Add`, `PartialEq`, `Drop`).
  - Annotates C++ lifetimes (`[[clang::lifetimebound]]`, `$a` macros) so Rust's borrow checker statically validates C++ pointer/reference lifetimes across FFI.
  - Per Google C++ Style Guide's Rust-interop rule, C++ wrapper boundaries may adapt naming where required to match Rust crate conventions cleanly.
- **Build-System Matrix**:
  - **C++ calling Rust (`cpp_api_from_rust`)**: Supported in **CMake**, **Bazel**, and `cargo cpp_api_from_rust`.
  - **Rust calling C++ (`rust_api_from_cpp`)**: Supported in **Bazel**. For pure-CMake builds where Rust calls C++ before CMake `rust_api_from_cpp` lands, fall back cleanly to `cxx` or a minimal `extern "C"` C23 ABI shim.

```cpp
// Example: C++23 operator calling a Rust kinematics crate via Crubit bindings.
#include <cstdint>
#include <print>

#include "halos_kinematics_rs_api.h"  // Generated by Crubit cpp_api_from_rust

void VerifyPoseTransform(double x_m, double y_m) {
  const halos_kinematics::Pose2d pose{.x_m = x_m, .y_m = y_m, .theta_rad = 0.0};
  const double norm = halos_kinematics::ComputePoseNorm(pose);
  std::println("pose_norm={:.6f}", norm);
}
```

### 4.2 C23 (`/c-pro`), SPARK Ada (`/ada-spark-pro`), and Python (`/python-pro`)

- **C23 & SPARK Ada**: Keep boundary headers valid ISO C23 (`#pragma once`, `#ifdef __cplusplus extern "C" { #endif`, `<stdint.h>` inside dual-language headers, `static_assert(sizeof(...))` layout checks). Wrap raw C integer status codes immediately into C++23 `std::expected<T, FaultCode>` inside a thin RAII facade—never leak raw pointers into C++ business logic.
- **Python**: Export C++23 compute kernels to Python 3.14.7 using `nanobind` (`nb::ndarray` zero-copy buffer protocol) orchestrated via `pixi` (`/python-pro`).
