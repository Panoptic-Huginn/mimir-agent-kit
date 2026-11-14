# Modern C++23 Constructs, Coroutines, Abseil, Testing & Crubit Interop

Reference guide for November 2026 **ISO C++23** (`LLVM/Clang 23.1.5`) standard library idioms, hardened `<coroutine>` primitives, **Abseil (`absl` LTS `20260817.0+`)**, **Google Test (`v1.18.0+`)**, **Google Benchmark (`v1.10.0+`)**, and zero-overhead **Crubit** C++/Rust interoperability managed via `pixi`.

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

### 1.2 Deducing `this`, Multidimensional `operator[]`, and `auto(x)`

Eliminate CRTP boilerplate, duplicated `const`/non-`const` overloads, and `std::function` recursive lambdas using C++23 explicit object parameters (`this Self&& self`), and replace proxy-returning `operator()(r, c)` or `at(r, c)` indexing with C++23 multidimensional `operator[](r, c)`:

```cpp
#pragma once

#include <cstddef>
#include <span>
#include <utility>

template <typename T>
class MatrixView2D {
 public:
  constexpr MatrixView2D(std::span<T> storage, size_t rows,
                         size_t cols) noexcept
      : storage_(storage), rows_(rows), cols_(cols) {}

  // Single deducing-this template serves const, non-const, and rvalue views.
  template <typename Self>
  [[nodiscard]] constexpr auto&& operator[](this Self&& self, size_t row,
                                            size_t col) noexcept {
    return std::forward<Self>(self).storage_[(row * self.cols_) + col];
  }

  [[nodiscard]] constexpr size_t Rows() const noexcept { return rows_; }
  [[nodiscard]] constexpr size_t Cols() const noexcept { return cols_; }

 private:
  std::span<T> storage_{};
  size_t rows_ = 0uz;
  size_t cols_ = 0uz;
};
```

### 1.3 `std::mdspan`, `std::flat_map`, `std::out_ptr`, `std::move_only_function` & Ranges

- **`std::mdspan` (`<mdspan>`)**: Zero-copy non-owning multi-dimensional view over contiguous storage (`float*`, `std::vector`, DMA buffers) with compile-time/runtime strides—ideal for robotics Jacobians, Kalman covariance matrices, and image tiles.
- **`std::flat_map` / `std::flat_set` (`<flat_map>`, `<flat_set>`)**: Sorted contiguous vector-backed associative containers for cache-friendly lookup tables (guard with `#if __has_include(<flat_map>)` when targeting older Linux `libstdc++`).
- **`std::out_ptr` / `std::inout_ptr` (`<memory>`)**: Zero-overhead C++23 adaptor for passing `std::unique_ptr<T, Deleter>` directly into C23 `extern "C"` factory/reallocation functions expecting `T**`.
- **`std::move_only_function<Sig>` (`<functional>`)**: Owning, move-only type-erased callable supporting `const`/`noexcept` qualifiers for cold-path task queues (guard with `#ifdef __cpp_lib_move_only_function`); use **`absl::FunctionRef<Sig>`** for zero-allocation non-owning callbacks.
- **`std::ranges` C++23 Views & `std::ranges::to`**: Use `std::views::zip`, `std::views::enumerate`, `std::views::chunk`, `std::views::stride`, and `std::ranges::to<std::vector>()` on cold paths and test code; verify via benchmarks before putting range adaptors in innermost tight loops.
- **Additional C++23 Primitives**:
  - `std::print` / `std::println` (`<print>`) and `std::format` (`<format>`) with custom `std::formatter<T>`.
  - `constexpr <cmath>` (`std::abs`, `std::fabs`, `std::isfinite`) and `constexpr std::unique_ptr` for compile-time validation and calibration LUT synthesis.
  - `auto(x)` / `auto{x}` prvalue decay-copy for explicit copy materialization inside generic code without `std::decay_t`.
  - `<stdfloat>` (`std::float16_t`, `std::bfloat16_t` guarded by `#ifdef __STDCPP_FLOAT16_T__` / `__STDCPP_BFLOAT16_T__`) for compact telemetry/ML tensors, and `<spanstream>` (`#if __has_include(<spanstream>)`) for zero-allocation stack-buffer formatting.
  - `std::byteswap` (`<bit>`) for endianness conversion in network/CAN/EtherCAT parsers (`uint16_t`, `uint32_t`, `uint64_t`).
  - `std::to_underlying` (`<utility>`) for converting `enum class` values cleanly without verbose `static_cast`.
  - `std::unreachable()` (`<utility>`) and `[[assume(expr)]]` for optimizer hints when an invariant is proven externally (paired with `ABSL_DCHECK` in debug builds).
  - `if consteval` for clean compile-time vs. SIMD runtime branching inside `constexpr` functions, plus `0uz` (`size_t`) and `0z` (`ptrdiff_t`) integer literal suffixes.

### 1.4 Hardened C++23 Coroutine Primitives (`<coroutine>` + Clang 23 Attributes)

On cold/async I/O paths, prefer vetted libraries (`stdexec` / `exec::task`, `asio::awaitable`, `libcoro`, `folly::coro`, `pw::async2`, or guarded `std::generator`). When a dedicated infrastructure module defines a custom coroutine handle, harden it with Clang 23 attributes and `-fno-exceptions` safety:

```cpp
#pragma once

#include <coroutine>
#include <cstdlib>
#include <utility>

template <typename T>
class [[clang::coro_return_type, clang::coro_lifetimebound,
        clang::coro_await_elidable, clang::coro_only_destroy_when_complete]]
InfraTask {
 public:
  // C++ standard requires lowercase coroutine promise hooks.
  // NOLINTBEGIN(readability-identifier-naming)
  struct promise_type {
    T value{};

    InfraTask get_return_object() noexcept {
      return InfraTask{
          std::coroutine_handle<promise_type>::from_promise(*this)};
    }
    std::suspend_always initial_suspend() noexcept { return {}; }
    std::suspend_always final_suspend() noexcept { return {}; }
    void return_value(T v) noexcept { value = std::move(v); }
    void unhandled_exception() noexcept { std::abort(); }
  };
  // NOLINTEND(readability-identifier-naming)

  explicit InfraTask(std::coroutine_handle<promise_type> handle) noexcept
      : handle_(handle) {}
  InfraTask(InfraTask&& other) noexcept
      : handle_(std::exchange(other.handle_, {})) {}
  InfraTask& operator=(InfraTask&& other) noexcept {
    if (this != &other) {
      if (handle_) {
        handle_.destroy();
      }
      handle_ = std::exchange(other.handle_, {});
    }
    return *this;
  }
  InfraTask(const InfraTask&) = delete;
  InfraTask& operator=(const InfraTask&) = delete;

  ~InfraTask() {
    if (handle_) {
      handle_.destroy();
    }
  }

  [[nodiscard]] T RunToCompletion() noexcept {
    while (!handle_.done()) {
      handle_.resume();
    }
    return std::move(handle_.promise().value);
  }

 private:
  std::coroutine_handle<promise_type> handle_;
};
```

Always enforce by-value coroutine parameters (no dangling references), forbid capturing lambda coroutines, never hold locks across `co_await`, and validate with `ASan`/`TSan`.

---

## 2. Abseil (`absl` LTS `20260817.0+`) Integration Guide

Per Google C++ Style Guide #1, prefer **Abseil** where it provides measurably better hash tables, memory locality, compile-time thread-safety checks, or string utilities than the standard library:

| Domain | Recommended Choice | Rationale & Usage Rule |
| :--- | :--- | :--- |
| **Unordered Hash Map / Set** | `absl::flat_hash_map`, `absl::flat_hash_set` | Swiss-table open addressing avoids per-node heap allocations and cache misses of `std::unordered_map` |
| **Pointer-Stable Hash Map** | `absl::node_hash_map` | Only when pointer/reference stability across rehashes is required |
| **Small-Buffer / Fixed Arrays** | `absl::InlinedVector<T, N>`, `absl::FixedArray<T>` | Stack-buffered storage avoids heap allocations for typical small sizes |
| **Non-Owning / Owning Callable** | `absl::FunctionRef<Sig>` / `std::move_only_function<Sig>` | `absl::FunctionRef` for zero-alloc non-owning borrows; `std::move_only_function` for owning cold-path tasks |
| **String Building & Matching** | `absl::StrCat`, `absl::StrAppend`, `absl::StrSplit`, `absl::StrJoin`, `absl::StartsWith`, `absl::StrContains` | Single-pass size calculation; faster and cleaner than `std::ostringstream` or repeated `+` |
| **Formatting** | `<print>` / `<format>` (C++23) or `absl::StrFormat` | Use `std::println`/`std::format` as default; `absl::StrFormat` when formatting directly into Abseil string pipelines |
| **Error Propagation** | `std::expected<T, E>` (Default) / `absl::StatusOr<T>` (Boundaries) | Standardize on `std::expected<T, E>` everywhere internally and on hot paths; use `absl::Status` / `absl::StatusOr<T>` at gRPC/Protobuf/host control-plane boundaries needing rich diagnostics |
| **Synchronization** | `absl::Mutex` + `ABSL_GUARDED_BY` / `ABSL_EXCLUSIVE_LOCKS_REQUIRED` | Smaller than `std::mutex`, supports `Condition` predicates, and activates Clang Thread-Safety Analysis (`-Wthread-safety`) |
| **Downcasting & Assertions** | `absl::down_cast`, `ABSL_CHECK`, `ABSL_DCHECK` | Debug-checked downcasts and fatal invariant assertions (`bugprone-assert-side-effect` aware) |

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

- **C23 & SPARK Ada**: Keep boundary headers valid ISO C23 (`#pragma once`, `#ifdef __cplusplus extern "C" { #endif`, `<stdint.h>` inside dual-language headers, `static_assert(sizeof(...))` layout checks). Wrap C `T**` out-pointer factories cleanly with `std::out_ptr` into a custom-deleter `std::unique_ptr` and return `std::expected<T, FaultCode>` from a thin RAII facade—never leak raw owning pointers into C++ business logic:

```cpp
#pragma once

#include <cstdint>
#include <expected>
#include <memory>

// NOLINTBEGIN(readability-identifier-naming)
extern "C" {
struct HalosChannel;
int32_t halos_channel_open(uint32_t bus_id, struct HalosChannel** out_handle);
void halos_channel_close(struct HalosChannel* handle);
}
// NOLINTEND(readability-identifier-naming)

struct HalosChannelDeleter {
  void operator()(HalosChannel* handle) const noexcept {
    if (handle != nullptr) {
      halos_channel_close(handle);
    }
  }
};

using HalosChannelPtr = std::unique_ptr<HalosChannel, HalosChannelDeleter>;

[[nodiscard]] inline std::expected<HalosChannelPtr, int32_t> OpenHalosChannel(
    uint32_t bus_id) noexcept {
  HalosChannelPtr channel;
  const int32_t status =
      halos_channel_open(bus_id, std::out_ptr(channel));
  if (status != 0) {
    return std::unexpected(status);
  }
  return channel;
}
```

- **Python**: Export C++23 compute kernels to Python 3.14.7 using `nanobind` (`nb::ndarray` zero-copy buffer protocol) orchestrated via `pixi` (`/python-pro`).
