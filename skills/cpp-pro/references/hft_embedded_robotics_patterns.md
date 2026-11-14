# High-Frequency Trading (HFT), Embedded & Robotics Systems Patterns

Canonical C++23 architectural patterns and build configurations aligned with **High-Frequency Trading**, **Embedded Firmware**, and **Safety-Critical Robotics (NVIDIA Halos / IGX Thor / Holoscan)** guidelines.

---

## 1. Hot-Path vs. Cold-Path Architectural Contract

Every low-latency or hard real-time C++23 system must explicitly partition initialization/control-plane (**cold path**) from deterministic execution loops (**hot path**):

| Concern | Cold Path (Startup, Config, Control Plane) | Hot Path (Tick-to-Trade, ISR, 1 kHz+ Control Loop) |
| :--- | :--- | :--- |
| **Dynamic Heap Allocation** | Allowed (`std::vector`, `absl::flat_hash_map`, arenas) | **FORBIDDEN**: Zero `new`, `delete`, `malloc`, `free`, or container growth after startup |
| **Error Propagation** | `std::expected<T, E>` (or `absl::StatusOr<T>` at gRPC boundaries) | `std::expected<T, E>` with `enum class` / trivially copyable `E` (no strings, no `.value()`) |
| **Coroutines (`<coroutine>`)** | Vetted async libraries (`stdexec` / `exec::task`, Asio, `libcoro`, `pw::async2`, guarded `<generator>`) | **Heap-Alloc Forbidden**: Synchronous state machines by default; coroutines only with fixed-pool `operator new noexcept` or verified Clang HALO |
| **Virtual Dispatch** | Interfaces & DI allowed | **Avoid**: Use `std::variant` + `std::visit`, templates/concepts, or deducing `this` |
| **Recursion & Stack** | Bounded | **FORBIDDEN**: Iterative bounded loops only; `-Wframe-larger-than=4096` |
| **Formatting & I/O** | `std::print` / `std::println`, `<filesystem>`, logging | **FORBIDDEN**: Push fixed-size POD telemetry structs onto an SPSC ring for off-thread printing |
| **OS Memory & CPU** | `mlockall(MCL_CURRENT \| MCL_FUTURE)`, prefault stacks, pin CPUs | Isolated cores (`isolcpus`), zero page faults, zero syscalls |
| **Cache Layout** | Normal struct layout | `alignas(kCacheLineBytes)` (`128uz` on Apple Silicon / `aarch64`, `64uz` on `x86_64`) on cross-thread atomics; contiguous SoA / `std::flat_map` / `std::mdspan` |

---

## 2. Pattern 1: Architecture-Aware Cache-Aligned Lock-Free SPSC Ring Buffer

Demonstrates strict `<cstdint>` + `int` usage, C++23 `0uz` / `1uz` / `64uz` / `128uz` `size_t` literals, `#pragma once`, `<bit>` (`std::has_single_bit`), architecture-aware `kCacheLineBytes` false-sharing elimination, explicit `acquire`/`release` memory ordering, and zero heap allocation after construction:

```cpp
// spsc_ring_buffer.h
#pragma once

#include <array>
#include <atomic>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <expected>
#include <type_traits>

#if defined(__APPLE__) && defined(__aarch64__)
inline constexpr size_t kCacheLineBytes = 128uz;  // Apple Silicon L2 coherency granule
#else
inline constexpr size_t kCacheLineBytes = 64uz;   // x86_64 / Linux ARM64 / RISC-V RVA23
#endif

enum class RingError : uint8_t {
  kFull = 1,
  kEmpty = 2,
};

template <typename T, size_t kCapacity>
  requires(std::is_trivially_copyable_v<T> && kCapacity >= 2uz &&
           std::has_single_bit(kCapacity))
class SpscRingBuffer {
 public:
  static_assert(std::atomic<size_t>::is_always_lock_free,
                "Target ISA must provide lock-free atomic size_t");

  [[nodiscard]] std::expected<void, RingError> TryPush(const T& item) noexcept {
    const size_t write_idx = write_idx_.load(std::memory_order_relaxed);
    const size_t read_idx = read_idx_.load(std::memory_order_acquire);
    if ((write_idx - read_idx) >= kCapacity) {
      return std::unexpected(RingError::kFull);
    }
    slots_[write_idx & kIndexMask] = item;
    write_idx_.store(write_idx + 1uz, std::memory_order_release);
    return {};
  }

  // Reuses caller pre-allocated storage via non-const reference out-parameter
  // per Google Style (#1) and HFT/Embedded zero-copy conventions.
  [[nodiscard]] std::expected<void, RingError> TryPop(T& out_item) noexcept {
    const size_t read_idx = read_idx_.load(std::memory_order_relaxed);
    const size_t write_idx = write_idx_.load(std::memory_order_acquire);
    if (read_idx == write_idx) {
      return std::unexpected(RingError::kEmpty);
    }
    out_item = slots_[read_idx & kIndexMask];
    read_idx_.store(read_idx + 1uz, std::memory_order_release);
    return {};
  }

  [[nodiscard]] size_t ApproximateSize() const noexcept {
    const size_t w = write_idx_.load(std::memory_order_acquire);
    const size_t r = read_idx_.load(std::memory_order_acquire);
    return w - r;
  }

 private:
  static constexpr size_t kIndexMask = kCapacity - 1uz;

  alignas(kCacheLineBytes) std::atomic<size_t> write_idx_{0uz};
  alignas(kCacheLineBytes) std::atomic<size_t> read_idx_{0uz};
  alignas(kCacheLineBytes) std::array<T, kCapacity> slots_{};
};
```

---

## 3. Pattern 2: Deterministic Safety & Risk Command Interceptor

Models an HFT pre-trade risk check or NVIDIA Halos actuation safety gate using `<cstdint>`, `0uz` indexing, `<cmath>` (`std::isfinite`, `std::fabs`), `std::expected<T, E>` (zero exceptions), `[[nodiscard]]`, `alignas(kCacheLineBytes)`, and pre-allocated output reuse:

```cpp
// safety_gate.h
#pragma once

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <expected>

#if defined(__APPLE__) && defined(__aarch64__)
inline constexpr size_t kGateCacheLineBytes = 128uz;
#else
inline constexpr size_t kGateCacheLineBytes = 64uz;
#endif

inline constexpr size_t kDofCount = 6uz;
inline constexpr uint64_t kMaxHeartbeatAgeNs = 5'000'000ULL;

enum class SafetyState : uint8_t {
  kInit = 0U,
  kActive = 1U,
  kFaultEstop = 2U,
};

enum class GateFault : uint8_t {
  kNotActive = 1U,
  kClockRegression = 2U,
  kStaleHeartbeat = 3U,
  kNonFiniteCommand = 4U,
  kLimitExceeded = 5U,
};

struct alignas(kGateCacheLineBytes) JointCommand {
  uint64_t timestamp_ns = 0ULL;
  uint32_t sequence_id = 0U;
  std::array<float, kDofCount> desired_torque_nm{};
};

class HalosSafetyGate {
 public:
  explicit constexpr HalosSafetyGate(
      std::array<float, kDofCount> max_abs_torque_nm) noexcept
      : max_abs_torque_nm_(max_abs_torque_nm) {}

  void Arm() noexcept {
    if (state_ == SafetyState::kInit) {
      state_ = SafetyState::kActive;
    }
  }

  [[nodiscard]] std::expected<void, GateFault> Intercept(
      const JointCommand& cmd, uint64_t now_ns,
      std::array<float, kDofCount>& out_safe_torques) noexcept {
    const auto zero_outputs = [&out_safe_torques] noexcept {
      out_safe_torques.fill(0.0F);
    };

    if (state_ != SafetyState::kActive) {
      zero_outputs();
      return std::unexpected(GateFault::kNotActive);
    }
    if (now_ns < cmd.timestamp_ns) {
      state_ = SafetyState::kFaultEstop;
      zero_outputs();
      return std::unexpected(GateFault::kClockRegression);
    }
    if ((now_ns - cmd.timestamp_ns) > kMaxHeartbeatAgeNs) {
      state_ = SafetyState::kFaultEstop;
      zero_outputs();
      return std::unexpected(GateFault::kStaleHeartbeat);
    }

    for (size_t i = 0uz; i < kDofCount; ++i) {
      const float req = cmd.desired_torque_nm[i];
      if (!std::isfinite(req)) {
        state_ = SafetyState::kFaultEstop;
        zero_outputs();
        return std::unexpected(GateFault::kNonFiniteCommand);
      }
      if (std::fabs(req) > max_abs_torque_nm_[i]) {
        state_ = SafetyState::kFaultEstop;
        zero_outputs();
        return std::unexpected(GateFault::kLimitExceeded);
      }
      out_safe_torques[i] = req;
    }
    return {};
  }

  [[nodiscard]] SafetyState State() const noexcept { return state_; }

 private:
  std::array<float, kDofCount> max_abs_torque_nm_{};
  SafetyState state_ = SafetyState::kInit;
};
```

---

## 4. Pattern 3: `std::mdspan` Compute Kernel & `pixi`-Integrated CMake Options

### 4.1 Zero-Copy `std::mdspan` Matrix-Vector Kernel

```cpp
#pragma once

#include <cstddef>
#include <mdspan>
#include <span>

using ConstMatrixView = std::mdspan<const float, std::dextents<size_t, 2>>;

// Computes out_y = jacobian * q_dot in-place without heap allocation.
inline void MultiplyJacobian(ConstMatrixView jacobian,
                             std::span<const float> q_dot,
                             std::span<float> out_y) noexcept {
  const size_t rows = jacobian.extent(0);
  const size_t cols = jacobian.extent(1);
  if (q_dot.size() < cols || out_y.size() < rows) {
    return;
  }

  for (size_t r = 0uz; r < rows; ++r) {
    float acc = 0.0F;
    for (size_t c = 0uz; c < cols; ++c) {
      acc += jacobian[r, c] * q_dot[c];
    }
    out_y[r] = acc;
  }
}
```

### 4.2 CMake 4.5+ Target Options (`-fno-exceptions -fno-rtti` Default + `pixi` Prefix)

Integrate with `/cmake-pro` interface libraries inside a `pixi` environment (`CMAKE_PREFIX_PATH="$CONDA_PREFIX"` in `CMakePresets.json`) so projects default to `-fno-exceptions -fno-rtti` while permitting explicit opt-in via presets or CLI (`-DENABLE_EXCEPTIONS=ON`, `-DENABLE_RTTI=ON`):

```cmake
# cmake/ProjectOptions.cmake (integrated with pixi + /cmake-pro)
option(ENABLE_EXCEPTIONS "Enable C++ exceptions (default OFF)" OFF)
option(ENABLE_RTTI "Enable C++ RTTI (default OFF)" OFF)

add_library(project_options INTERFACE)
target_compile_features(project_options INTERFACE cxx_std_23)

if(NOT ENABLE_EXCEPTIONS)
    target_compile_options(project_options INTERFACE -fno-exceptions)
endif()
if(NOT ENABLE_RTTI)
    target_compile_options(project_options INTERFACE -fno-rtti)
endif()
```
