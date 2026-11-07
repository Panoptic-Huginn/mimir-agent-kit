# Google Rust Styleguide Comprehensive Reference

This manual codifies the authoritative Google Rust Styleguide (`https://google.github.io/styleguide/rustguide.html`) into actionable rules, invariants, and code examples for production software development.

---

## 1. Code Organization & File Layout

### A. Small Crates
- Crates should ideally focus on a single abstraction, single-file where practical.
- Re-export public APIs from leaf submodules at crate root (`pub use submodule::Item;`).
- Large multi-file crates are permitted only when required for trait coherence (orphan rule) or foundational standard libraries.

### B. Flat File Layout
- `.rs` source files belonging to one crate must reside in a single flat directory; avoid deeply nested subdirectories within a single crate.
- If a crate accumulates dozens of files across multiple conceptual layers, split it into multiple fine-grained crates.

### C. Primary Item File Naming
- Name source files and leaf modules after the primary user-defined item (e.g., struct `SensorReader` in `sensor_reader.rs` / `mod sensor_reader`).
- Consistent naming ensures automated code search and tooling can map types to files without AST parsing.

### D. Non-Leaf Module Purity
- Non-leaf modules (`mod.rs` or module parent files) must contain **only** module declarations (`mod foo;`) and re-exports (`pub use foo::*;`).
- **Never** implement structs, functions, or business logic inside a non-leaf routing module.

---

## 2. Code Formatting & Tool Standards

### A. Line Width & Indentation
- **Maximum Column Width**: Enforce `max_width = 100` characters per line in `rustfmt.toml`. Lines must strictly not exceed 100 characters.
- **Indentation**: 4 spaces per indentation level; hard tabs are forbidden.
- **Hex Literals**: Use lowercase hexadecimal characters (`hex_literal_case = "Lower"`, e.g., `0x1f`).
- **Imports Granularity**: Merge imports on a single module basis (`imports_granularity = "Module"`).
- **Macro Matchers**: Enable `format_macro_matchers = true` for readable macro declarations.
- **Selective Opt-Out**: `#[rustfmt::skip]` is restricted exclusively to 2D matrices or hardware lookup tables; forbidden for personal aesthetic preferences.

---

## 3. Imports & Qualification Rules

### A. Prohibition of Glob Imports
- Wildcard imports (`use foo::*;`) are strictly forbidden across production code.
- **Exceptions**:
  1. `use super::*;` inside inline unit test modules (`#[cfg(test)] mod tests`).
  2. `use MyEnum::*;` inside an `impl MyEnum` method body when matching variants.
  3. Re-exports (`pub use submodule::*;`) inside non-leaf routing modules.

```rust
// FORBIDDEN:
use std::collections::*;
use crate::models::*;

// MANDATORY:
use std::collections::BTreeMap;
use std::collections::HashMap;
use crate::models::SensorPacket;
```

### B. Module-Granularity Imports
- Each `use` statement imports items from exactly one module (`imports_granularity = "Module"` in `rustfmt.toml`).
- Nested multi-level braces (`use foo::{bar::Baz, qux::Quux};`) are disallowed.

```rust
// MANDATORY:
use std::io::Read;
use std::io::Write;
use std::sync::atomic::AtomicBool;
use std::sync::atomic::Ordering;
```

### C. Locally Scoped Trait Imports
- When a trait is used in only one function, import it locally within the function body to prevent namespace pollution:
```rust
fn parse_timestamp(s: &str) -> Option<u64> {
    use core::str::FromStr;
    u64::from_str(s).ok()
}
```

### D. Qualify Top-Level Functions vs. Unqualified Types
- **Top-Level Free Functions**: Must be called with a module qualifier so readers know the function is non-local without IDE cross-references:
  ```rust
  // MANDATORY:
  core::mem::drop(resource);
  std::thread::spawn(|| ...);
  ```
- **Types and Traits**: Import and refer to unqualified:
  ```rust
  use std::collections::HashMap;
  let map: HashMap<String, u64> = HashMap::new();
  ```
  *(Exception: Ambiguous names like `std::io::Error` vs `crate::Error` may be qualified as `io::Error` or aliased).*

---

## 3. Ownership, Borrowing & Function Signatures

### A. Avoid `Rc` and `Arc`
- Prefer unique ownership (`T`, `Box<T>`) and clear borrowing lifetimes (`&T`, `&mut T`).
- Avoid `Rc<RefCell<T>>` and `Arc<Mutex<T>>` for cyclic data structures; prefer generational arenas (`slotmap`) or flat index pools.

### B. Borrows over Deep Copies
- Use `.clone()` only when a genuine, independent deep copy is mathematically required.
- Never use `.clone()` as a lazy shortcut to appease the borrow checker.

### C. Flexible References for API Inputs
Functions should accept references to data itself, not specific container wrappers:
- Accept `&[T]` instead of `&Vec<T>`.
- Accept `&str` instead of `&String`.
- Accept `&Path` instead of `&PathBuf`.
- Accept `Option<&T>` instead of `&Option<T>`.

### D. Iterators in Return Types and Parameters
- In reusable libraries, prefer returning `impl Iterator<Item = T>` over allocating `Vec<T>`.
- Accept `impl IntoIterator<Item = T>` or `&[T]` in functions that process sequences.

### E. Enum over Bool in API Signatures
Boolean flags at call sites obscure meaning (`process_data(data, true, false)`). Prefer self-documenting enums:
```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SyncMode {
    Synchronous,
    Asynchronous,
}

pub fn process_data(data: &[u8], mode: SyncMode) { ... }
```

---

## 4. Error Reporting Triad & Concurrency

### A. The Error Triad
1. **`Option<T>`**: Use for simple or obvious absence (e.g. key missing in map, EOF, element search).
2. **`Result<T, E>`**: Use for all recoverable failures where callers need contextual information to retry or report.
3. **`panic!`**: Strictly reserved for violated programmer invariants, unreachable internal bugs, and post-assertion failure. Never use for expected external failures (network drop, bad input, hardware timeout).

### B. Prohibition of `panic::catch_unwind`
- Production systems and robotics software compile with `panic = "abort"` in release profiles.
- Because `catch_unwind` is a no-op under `panic = "abort"`, calling it is strictly prohibited. Propagate errors via `Result`.

### C. Mutex Poisoning Invariant
- **Never** reach inside a poisoned mutex (`lock().unwrap_or_else(|e| e.into_inner())`).
- When a thread panics while holding a mutex, protected data structures may be in an inconsistent, partially updated state. Reaching inside risks silent data corruption.

---

## 5. Structs, Accessors & Evolution

### A. Getter and Setter Naming Conventions
- **Getter**: `foo(&self) -> &T` (or `T` if `Copy`). Do not prefix with `get_`.
- **Mutable Getter**: `foo_mut(&mut self) -> &mut T`.
- **Setter**: `set_foo(&mut self, val: T)`.
- **Drain / Clear**: `take_foo(&mut self) -> Option<T>`.
- **Replace**: `replace_foo(&mut self, val: T) -> T`.

### B. Closure Accessors for Interior Mutability
To avoid leaking RAII lock guards (`MutexGuard`, `RefCell`) into public interfaces, provide scoped closure accessors:
```rust
pub struct SafeRegistry {
    data: std::sync::Mutex<Config>,
}

impl SafeRegistry {
    pub fn with_config<R>(&self, f: impl FnOnce(&Config) -> R) -> R {
        let guard = self.data.lock().expect("mutex poisoned");
        f(&guard)
    }
}
```

### C. `#[must_use]` and `#[non_exhaustive]`
- **`#[must_use]`**: Mandatory on pure functions, functions returning status codes or resources, and custom error types.
- **`#[non_exhaustive]`**: Mandatory on public enums and structs with public fields exposed across team or crate boundaries, enabling future additions without breaking downstream pattern matching.

---

## 6. Implementation Patterns & Documentation

### A. Pattern Matching over Check-Then-Unwrap
```rust
// FORBIDDEN:
if opt.is_some() {
    let val = opt.unwrap();
}

// MANDATORY:
if let Some(val) = opt {
    // Process val
}
```

### B. Prefer `expect` over `unwrap`
When unwrapping is mathematically unavoidable due to an unexpressed invariant, use `.expect("descriptive invariant reason")`.

### C. Documentation Standards
- Write rustdoc using `///` on items and `//!` on crate/module headers.
- Public functions must include structured sections:
  - `# Panics`: Detail any conditions leading to an assertion or panic.
  - `# Safety`: Mandatory on any `unsafe fn` or `unsafe trait`.
  - `# Examples`: Copy-pasteable testable code snippets (`cargo test --doc`).
