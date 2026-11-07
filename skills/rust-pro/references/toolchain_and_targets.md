# Toolchain, Target Architectures & Pixi Integration Manual

This manual provides authoritative guidance on configuring, cross-compiling, and orchestrating Rust 1.99.1+ projects using **Pixi** across Linux and macOS workstations, targeting **x86_64**, **aarch64**, and **RISC-V RVA23** architectures.

---

## 1. Rust 1.99.1 Modern Language Capabilities

Rust 1.99 (stabilized October 2026, patched in 1.99.1) introduces critical systems-level primitives that replace legacy nightly workarounds and unsafe hacks.

### A. First-Class C-Variadic Function Definitions in Rust
Rust 1.99 stabilizes defining C-compatible variadic functions directly in Rust rather than only declaring external C bindings:

```rust
use core::ffi::VaList;

/// Exported C-variadic logging interceptor.
///
/// # Safety
///
/// Caller must pass a valid format string and arguments matching the format specifiers.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn halos_log_format(
    severity: u32,
    fmt: *const core::ffi::c_char,
    mut args: ...
) -> i32 {
    // VaList handles ABI-specific argument unpacking safely
    let mut va: VaList = args.as_va_list();
    // Processing logic...
    0
}
```
- Available across both `"C"` and `"C-unwind"` calling conventions.
- Types passed across variadic boundaries must implement the compiler trait `core::ffi::VaArgSafe`.

### B. Raw Pointer Metadata & Layout Extraction
Safe raw pointer introspection is stabilized, allowing systems engineers to query the size and alignment of dynamically sized types (DSTs) through raw pointers without dereferencing or creating intermediate references:
- `core::ptr::metadata(ptr)`: Extracts pointer metadata (slice length or vtable pointer).
- `core::mem::size_of_val_raw(raw_ptr)`: Computes byte size without creating an intermediate `&T` reference.
- `core::mem::align_of_val_raw(raw_ptr)`: Computes memory alignment without dereference.

### C. `raw_borrows_via_references` Lint & `&raw const` / `&raw mut`
The compiler strictly lints against creating intermediate references when obtaining raw pointers:
```rust
// FORBIDDEN (can trigger undefined behavior if unaligned or dangling):
// let ptr = &(*unaligned_ptr).field as *const _;

// MANDATORY (uses native raw address-of operators):
let ptr = core::ptr::addr_of!((*unaligned_ptr).field);
```

### D. Explicit `#[unsafe(...)]` Attribute Syntax
To maintain safety transparency, compiler attributes that carry unsafe invariants now require explicit `#[unsafe(...)]` qualification:
- `#[unsafe(no_mangle)]`: Prevents symbol mangling while marking the export as unsafe.
- `#[unsafe(export_name = "custom_symbol")]`: Explicitly names the exported symbol.
- `#[unsafe(link_section = ".sram.text")]`: Places code into specific hardware memory banks.
- `#[unsafe(naked)]`: Defines naked functions for assembly context-switchers without compiler prologs.

---

## 2. Pixi Workspace Orchestration

Pixi provides hermetic, cross-platform environment isolation by leveraging the `conda-forge` binary repository. Unlike host package managers (`apt`, `brew`), Pixi locks exact toolchain versions across all developer machines and CI runners via `pixi.lock`.

### A. Channel & Dependency Configuration
A production `pixi.toml` for Rust systems projects declares:
```toml
[workspace]
name = "robotics-kernel"
channels = ["conda-forge"]
platforms = ["linux-64", "linux-aarch64", "osx-64", "osx-arm64"]

[dependencies]
rust = "1.99.1.*"
cargo-nextest = ">=0.9.150"
cargo-audit = ">=0.22.0"
cargo-deny = ">=0.20.0"
cargo-llvm-cov = ">=0.9.0"
cargo-zigbuild = ">=0.24.0"
rust-analyzer = ">=2026.08.0"
```

### B. Cross-Target Toolchain Packages
When compiling for foreign embedded architectures (e.g., RISC-V RVA23 or AArch64 Linux from an x86_64 host), declare the cross-compiler toolchains in platform-specific dependency tables:
```toml
[target.linux-64.dependencies]
gcc_linux-riscv64 = ">=16.2.0"
gcc_linux-aarch64 = ">=16.2.0"
qemu-execve-riscv64 = ">=11.0.0"
```

### C. Standardized Pixi Task Definitions
Pixi tasks abstract complex cargo invocations into unified CLI entry points:
- `pixi run check`: `cargo check --workspace --all-targets`
- `pixi run test`: `cargo nextest run --workspace --all-targets`
- `pixi run clippy`: `cargo clippy --workspace --all-targets -- -D warnings`
- `pixi run fmt`: `cargo fmt --all -- --check`
- `pixi run deny`: `cargo deny check bans licenses sources`
- `pixi run audit`: `cargo audit`
- `pixi run miri`: `cargo miri test --workspace`
- `pixi run build-riscv`: `cargo build --target riscv64a23-unknown-linux-gnu --release`
- `pixi run test-riscv`: `cargo test --target riscv64a23-unknown-linux-gnu`

---

## 3. Hardware Target Architectures & Triples

### A. Linux & macOS Host Triples
- **`x86_64-unknown-linux-gnu`**: Linux workstations and cloud compute instances (x86-64-v3 baseline).
- **`aarch64-unknown-linux-gnu`**: NVIDIA IGX Thor, Jetson AGX Orin, and ARM64 servers.
- **`aarch64-apple-darwin`**: Apple Silicon workstations (macOS M-series).
- **`x86_64-apple-darwin`**: Intel macOS legacy workstations.

### B. RISC-V RVA23 Profile Targets
The RISC-V RVA23 profile (`rva23u64` user / `rva23s64` supervisor) standardizes 64-bit RISC-V hardware features for modern operating systems and robotics accelerators:
- Target triple: `riscv64a23-unknown-linux-gnu` (Linux glibc) or `riscv64gc-unknown-linux-gnu`.
- Bare-metal embedded triple: `riscv64gc-unknown-none-elf` or `riscv64imac-unknown-none-elf`.

#### Mandatory RVA23 Architectural Extensions:
- `v`: 128-bit+ Vector Extension (SIMD processing).
- `zba`, `zbb`, `zbs`: Bit manipulation extensions for address calculation and bitwise operations.
- `zacas`: 128-bit Atomic Compare-and-Swap for lock-free multi-core coordination.
- `zca`, `zcb`: Standard compressed instructions for code-density optimization.

---

## 4. Companion Quality & Security Tooling

Every production Rust project integrates five mandatory companion tools:

| Tool | Purpose | Key Flag / Invocation |
| :--- | :--- | :--- |
| **`cargo-nextest`** | Fast, isolated parallel test runner with JUnit report generation | `cargo nextest run --workspace` |
| **`cargo-deny`** | Verifies dependency licenses, bans duplicates, audits crate sources | `cargo deny check` |
| **`cargo-audit`** | Scans `Cargo.lock` against RustSec Advisory Database | `cargo audit` |
| **`cargo-llvm-cov`** | Source-level LLVM coverage analysis | `cargo llvm-cov --lcov --output-path coverage.lcov` |
| **`cargo-zigbuild`** | Zero-sysroot cross-compilation linking via Zig | `cargo zigbuild --target aarch64-unknown-linux-gnu.2.34` |
| **`miri`** | Undefined behavior, pointer provenance, and memory leak detection | `cargo miri test` |

---

## 5. Cargo Target Configuration & Emulation Setup

File: `.cargo/config.toml`

```toml
[target.riscv64a23-unknown-linux-gnu]
linker = "riscv64-linux-gnu-gcc"
rustflags = [
    "-C", "target-feature=+rva23u64,+v,+zba,+zbb,+zbs",
    "-C", "link-arg=-Wl,-z,relro,-z,now",
]
runner = "qemu-riscv64 -cpu rv64,v=true,vext_spec=v1.0,zba=true,zbb=true,zbs=true -L /usr/riscv64-linux-gnu"

[target.aarch64-unknown-linux-gnu]
linker = "aarch64-linux-gnu-gcc"
rustflags = [
    "-C", "target-cpu=neoverse-n1",
    "-C", "target-feature=+neon,+crypto",
    "-C", "link-arg=-Wl,-z,relro,-z,now",
]
runner = "qemu-aarch64 -L /usr/aarch64-linux-gnu"
```

With this configuration, executing `cargo test --target riscv64a23-unknown-linux-gnu` transparently routes binary execution through QEMU with the exact RISC-V vector and bitmanipulation CPU flags enabled.
