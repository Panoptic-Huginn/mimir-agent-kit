# Systems Paradigms, Robotics Safety & Safe/Unsafe Guardrails

This manual establishes architectural blueprints across standard, embedded, and bare-metal Rust paradigms, details the canonical **NVIDIA Halos Safety Command Interceptor** implementation, and defines strict guardrails for safe versus unsafe Rust boundaries.

---

## 1. The Three Systems Engineering Paradigms

Systems development in Rust spans three distinct operating environments:

```
+-------------------------------------------------------------------------+
| Standard Rust (std)                                                     |
| - Full OS available (Linux, macOS)                                      |
| - Dynamic allocation (Vec, Box, Arc), threads, networking, filesystem   |
| - High-throughput sensor ingestion, async RPC, planning models          |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
| Embedded Systems (no_std + HAL/RTOS)                                    |
| - FreeRTOS, Embassy, or RTIC on microcontrollers / safety co-processors |
| - Static pools, embedded-hal trait abstractions, DMA channels           |
| - Hard real-time control, peripheral drivers (CAN-FD, EtherCAT, SPI)    |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
| Bare-Metal & Safety Kernels (no_std, zero-alloc, bounded WCET)          |
| - NVIDIA Halos, IGX Thor Functional Safety Island, RISC-V safety MCUs   |
| - Zero dynamic heap allocation on real-time paths                       |
| - Typestate MMIO, bounded loops, lock-free atomics, deterministic panic |
+-------------------------------------------------------------------------+
```

### A. Standard Rust (`std`)
Used for host simulation, high-compute trajectory planners, and telemetry loggers where full OS services are available. Employs `thiserror` for typed library errors and `anyhow` for application orchestration.

### B. Embedded Systems (`no_std` + HAL/RTOS)
Operates without the standard library using `core` and optional static allocation pools (e.g. `heapless::Vec`). Relies on trait abstractions from `embedded-hal` for modular peripheral drivers.

### C. Bare-Metal & Safety Kernels (Zero-Alloc, Bounded WCET)
Mandates absolute execution determinism:
- **No Dynamic Memory Allocation**: Prohibit `alloc` on hot paths. All state is pre-allocated at startup or lives in static memory.
- **Bounded WCET**: No unbounded loops or recursion. Every loop has a statically provable trip count.
- **Typestate MMIO**: Hardware registers are encapsulated in compile-time typestates to prevent invalid hardware state transitions.

---

## 2. NVIDIA Halos Real-Time Safety Command Interceptor Pattern

The **NVIDIA Halos Pattern** is the reference architecture for decoupling untrusted AI/perception inputs from physical actuation. The safety interceptor acts as a deterministic firewall between high-compute models (Isaac GR00T, ROS 2, Python planners) and hardware motor controllers.

### Canonical Rust Implementation

```rust
//! Safety Command Interceptor implementing the NVIDIA Halos architecture.
//!
//! Enforces monotonic heartbeat freshness (5ms deadline), IEEE-754 finiteness,
//! joint torque/velocity safety envelopes, and zero dynamic heap allocation.

#![no_std]


/// Maximum allowable age of an incoming command before triggering E-STOP.
pub const MAX_COMMAND_AGE_NS: u64 = 5_000_000; // 5.0 milliseconds

/// Maximum absolute joint torque permitted by the safety envelope.
pub const MAX_JOINT_TORQUE_NM: f32 = 80.0;

/// Number of controlled robotic joint degrees of freedom.
pub const DOF_COUNT: usize = 6;

/// Lifecycle states of the safety interceptor state machine.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(i32)]
pub enum SafetyState {
    /// Initial startup state; actuators unpowered.
    Init = 0,
    /// Hardware verified; ready for operational arming.
    Armed = 1,
    /// Normal operational state; active trajectory pass-through.
    Active = 2,
    /// Transient disturbance or degraded sensor mode.
    Degraded = 3,
    /// Latched safety fault state; zero-torque safe shutdown.
    FaultEstop = 4,
}

/// Raw actuation command packet passed across IPC/C-ABI boundaries.
#[derive(Debug, Clone, Copy)]
#[repr(C)]
pub struct ActuationCommand {
    /// Monotonic timestamp of command generation in nanoseconds.
    pub timestamp_ns: u64,
    /// Target joint torques in Newton-meters for each DOF.
    pub torques: [f32; DOF_COUNT],
    /// Monotonically incrementing sequence identifier.
    pub sequence_id: u32,
}

/// Safety status and latched safe output.
#[derive(Debug, Clone, Copy)]
#[repr(C)]
pub struct InterceptorOutput {
    /// Latched safety state.
    pub state: SafetyState,
    /// Validated safe torque commands applied to actuators.
    pub safe_torques: [f32; DOF_COUNT],
    /// Bitmask of detected fault causes.
    pub fault_flags: u32,
}

pub mod fault_flags {
    pub const HEARTBEAT_TIMEOUT: u32 = 1 << 0;
    pub const NON_FINITE_VALUE: u32 = 1 << 1;
    pub const TORQUE_LIMIT_EXCEEDED: u32 = 1 << 2;
    pub const CLOCK_REGRESSION: u32 = 1 << 3;
}

/// Deterministic, zero-allocation safety interceptor.
#[repr(C)]
pub struct HalosSafetyInterceptor {
    state: SafetyState,
    last_sequence_id: u32,
    fault_flags: u32,
}

impl HalosSafetyInterceptor {
    /// Construct a new interceptor in the safe `Init` state.
    #[must_use]
    pub const fn new() -> Self {
        Self {
            state: SafetyState::Init,
            last_sequence_id: 0,
            fault_flags: 0,
        }
    }

    /// Arm the interceptor from `Init` after pre-flight safety checks pass.
    pub fn arm(&mut self) -> Result<(), &'static str> {
        if self.state == SafetyState::Init {
            self.state = SafetyState::Armed;
            Ok(())
        } else {
            Err("Cannot arm unless in Init state")
        }
    }

    /// Process an actuation command deterministically against safety rules.
    #[must_use]
    pub fn intercept(
        &mut self,
        cmd: &ActuationCommand,
        current_time_ns: u64,
    ) -> InterceptorOutput {
        // Once latched in FaultEstop, require authenticated manual reset
        if self.state == SafetyState::FaultEstop {
            return InterceptorOutput {
                state: SafetyState::FaultEstop,
                safe_torques: [0.0; DOF_COUNT],
                fault_flags: self.fault_flags,
            };
        }

        let mut detected_faults = 0u32;

        // 1. Clock Monotonicity & Heartbeat Deadline Check
        if current_time_ns < cmd.timestamp_ns {
            detected_faults |= fault_flags::CLOCK_REGRESSION;
        } else {
            let age_ns = current_time_ns - cmd.timestamp_ns;
            if age_ns > MAX_COMMAND_AGE_NS {
                detected_faults |= fault_flags::HEARTBEAT_TIMEOUT;
            }
        }

        // 2. IEEE-754 Finiteness & Torque Bounds Envelope Verification
        let mut bounded_torques = [0.0f32; DOF_COUNT];
        for i in 0..DOF_COUNT {
            let t = cmd.torques[i];
            if !t.is_finite() {
                detected_faults |= fault_flags::NON_FINITE_VALUE;
            } else if t.abs() > MAX_JOINT_TORQUE_NM {
                detected_faults |= fault_flags::TORQUE_LIMIT_EXCEEDED;
            } else {
                bounded_torques[i] = t;
            }
        }

        // 3. State Transition Logic
        if detected_faults != 0 {
            // Latch immediately into E-STOP
            self.state = SafetyState::FaultEstop;
            self.fault_flags |= detected_faults;
            InterceptorOutput {
                state: SafetyState::FaultEstop,
                safe_torques: [0.0; DOF_COUNT], // Zero-torque safe state
                fault_flags: self.fault_flags,
            }
        } else {
            self.state = SafetyState::Active;
            self.last_sequence_id = cmd.sequence_id;
            InterceptorOutput {
                state: SafetyState::Active,
                safe_torques: bounded_torques,
                fault_flags: 0,
            }
        }
    }
}

// -----------------------------------------------------------------------------
// Exported C-ABI Interface (Zero-Copy Interop with C23 / C++23 Kernels)
// -----------------------------------------------------------------------------

/// C-compatible initialization for HalosSafetyInterceptor.
///
/// # Safety
///
/// `interceptor` must point to a valid, aligned, writable memory location for `HalosSafetyInterceptor`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn halos_interceptor_init(interceptor: *mut HalosSafetyInterceptor) -> i32 {
    if interceptor.is_null() {
        return -1;
    }

    // SAFETY: Caller guarantees `interceptor` is non-null and valid for writes.
    unsafe {
        (*interceptor).state = SafetyState::Init;
        (*interceptor).last_sequence_id = 0;
        (*interceptor).fault_flags = 0;
    }

    0
}

/// Exported C-ABI entry point for the Halos Safety Interceptor.
///
/// # Safety
///
/// - `interceptor` must be a valid, aligned, non-null pointer to a `HalosSafetyInterceptor`.
/// - `cmd` must point to an initialized `ActuationCommand`.
/// - `out` must point to writable memory of size `sizeof(InterceptorOutput)`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn halos_interceptor_process(
    interceptor: *mut HalosSafetyInterceptor,
    cmd: *const ActuationCommand,
    current_time_ns: u64,
    out: *mut InterceptorOutput,
) -> i32 {
    if interceptor.is_null() || cmd.is_null() || out.is_null() {
        return -1;
    }

    // SAFETY: Pointers are verified non-null, properly aligned by caller contract,
    // and borrow lifetimes do not outlive the scope of this function call.
    unsafe {
        let interceptor_ref = &mut *interceptor;
        let cmd_ref = &*cmd;
        let result = interceptor_ref.intercept(cmd_ref, current_time_ns);
        core::ptr::write(out, result);
    }

    0
}
```

---

## 3. Typestate Pattern for Memory-Mapped I/O (MMIO)

To prevent runtime errors such as transmitting before a peripheral is initialized, bare-metal Rust enforces hardware lifecycle transitions at compile time:

```rust
use core::marker::PhantomData;

pub struct Disabled;
pub struct Enabled;

/// Compile-time typestate-governed peripheral register block.
pub struct Uart<State> {
    base_addr: usize,
    _state: PhantomData<State>,
}

impl Uart<Disabled> {
    /// Create a new UART peripheral in the disabled state.
    pub const fn new(base_addr: usize) -> Self {
        Self {
            base_addr,
            _state: PhantomData,
        }
    }

    /// Enable the UART peripheral, transitioning type state.
    pub fn enable(self, baud_rate: u32) -> Uart<Enabled> {
        let ctrl_reg = (self.base_addr + 0x00) as *mut u32;
        // SAFETY: The base_addr is verified valid hardware MMIO region,
        // and register writes follow device datasheet ordering.
        unsafe {
            core::ptr::write_volatile(ctrl_reg, baud_rate | 0x01);
        }
        Uart {
            base_addr: self.base_addr,
            _state: PhantomData,
        }
    }
}

impl Uart<Enabled> {
    /// Transmit a single byte. Statically impossible to call on an uninitialized UART!
    pub fn transmit(&mut self, byte: u8) {
        let data_reg = (self.base_addr + 0x04) as *mut u8;
        // SAFETY: Hardware MMIO register is accessible and peripheral is enabled.
        unsafe {
            core::ptr::write_volatile(data_reg, byte);
        }
    }
}
```

---

## 4. Safe vs. Unsafe Rust Guardrails

### A. The Inviolable `// SAFETY:` Mandate
Every single `unsafe` block must be immediately preceded by a `// SAFETY:` comment that proves why the operation cannot cause undefined behavior. The justification must address:
1. **Pointer Validity**: Why the pointer is non-null, aligned, and points to allocated memory.
2. **Aliasing**: Why no other mutable references or conflicting reads exist.
3. **Data Invariants**: Why the values written or read satisfy target type invariants.

```rust
// FORBIDDEN:
let val = unsafe { *ptr };

// MANDATORY:
// SAFETY: `ptr` is non-null and aligned, verified by the caller's check on line 42.
// It points to a live `f32` in the static sensor buffer, and no mutable references
// can exist concurrently during this inspection phase.
let val = unsafe { *ptr };
```

### B. Lint Enforcement
In workspace `Cargo.toml`:
```toml
[lints.clippy]
undocumented_unsafe_blocks = "deny"

[lints.rust]
unsafe_op_in_unsafe_fn = "deny"
```
Under `#![deny(unsafe_op_in_unsafe_fn)]`, the body of an `unsafe fn` does not automatically permit unsafe operations without an explicit inner `unsafe { ... }` block and `// SAFETY:` comment.

### C. Dynamic & Formal Verification Gates
1. **Miri Interpreter (`cargo miri test`)**:
   - Detects out-of-bounds memory accesses.
   - Verifies stacked borrows / tree borrows pointer aliasing rules.
   - Detects memory leaks and uninitialized memory reads.
2. **AddressSanitizer & UndefinedBehaviorSanitizer**:
   - Run in CI via `-Zsanitizer=address,undefined` on nightly or test targets.
3. **Kani Rust Verifier**:
   - Model checks functional contracts and asserts absence of panics for high-integrity components.
