# Python 3.14 / 3.15 Features & Strict Typing Guide

This reference details the **Python 3.15** default baseline, **Python 3.14** compatibility floor rules, and strict static type checking with **`basedpyright`** and **`ty`**.

## 1. Python 3.15 Default Language & Stdlib Features

Use Python `3.15` for greenfield services, CLIs, applications, and libraries unless blocked by missing third-party `3.15` wheels:

| Feature | PEP | Usage Pattern | Notes & 3.14 Fallback |
| :--- | :--- | :--- | :--- |
| **Lazy Imports** | PEP 810 | `lazy import polars as pl` / `from math lazy import erfc` | Dramatically cuts CLI startup time; when targeting `>=3.14`, emulate cleanly with module `__lazy_modules__ = ["polars"]` (no-op attribute on 3.14) or function-local imports |
| **Immutable Mapping** | PEP 814 | Built-in `frozendict({"mode": "strict"})` | Hashable immutable dictionary in builtins; fall back to `types.MappingProxyType` under `3.14` |
| **Named Sentinels** | PEP 661 | `MISSING = sentinel("MISSING")` (`inspect` / builtin pattern) | Type-safe singleton sentinel without verbose `enum.Enum` boilerplate |
| **Comprehension Unpacking** | PEP 798 | `[*chunk for chunk in chunks]`, `{**d for d in dicts}` | Eliminates nested helper loops for flattening or merging mappings |
| **UTF-8 Default Encoding** | PEP 686 | UTF-8 active by default across `open()` and stdlib I/O | Still pass `encoding="utf-8"` explicitly whenever `requires-python = ">=3.14"` |
| **Sampling Profiler** | PEP 799 | `python -m profiling.sampling run script.py` | Tachyon low-overhead profiler supporting async & free-threaded `3.15t` runtimes |

### Free-Threading Readiness (`3.14t` / `3.15t`, PEP 779)

- Pure Python libraries without mutable module-level globals work naturally under `3.14t`/`3.15t`.
- C/C++/Rust extensions must declare GIL-free safety explicitly (`nanobind` `nb::mod_gil_not_used()`, `PyO3` `#[pymodule(gil_used = false)]`) and avoid static unprotected state.
- Only add `3.15t` to the CI test matrix once all critical runtime dependencies support free-threading cleanly.

## 2. Universal Python 3.14+ Floor Features (Mandatory Baseline)

Never target `< 3.14`. Every Python file in a `3.14+` or `3.15+` codebase adopts these constructs natively:

### Native Deferred Annotations (PEP 649 / PEP 749)

Python 3.14+ defers evaluation of annotations via `__annotate__` functions and `annotationlib`:

```python
import annotationlib
from dataclasses import dataclass


@dataclass(slots=True, frozen=True, kw_only=True)
class TreeNode:
    """Self-referential tree node without __future__ annotations."""

    label: str
    next_node: TreeNode | None = None


# Inspect forward-compatible annotations at runtime when needed:
annots = annotationlib.get_annotations(TreeNode, format=annotationlib.Format.FORWARDREF)
```

- **Strict Rule**: **Never write `from __future__ import annotations`** in `>=3.14` codebases. Enforce this via Ruff rule `TID251` (`banned-api`) in `pyproject.toml`.

### Native Generics & TypeVar Defaults (PEP 695 & PEP 696)

Prefer bracketed type parameters over legacy `TypeVar` / `Generic` boilerplate:

```python
type Matrix[Scalar: (float, complex) = float] = list[list[Scalar]]


class RingBuffer[T = bytes]:
    """Fixed-capacity typed buffer using PEP 695/696 defaults."""

    def __init__(self, items: list[T] | None = None) -> None:
        self._items: list[T] = list(items) if items is not None else []
```

### Safe Template Strings (PEP 750 `t"..."`)

Prefer PEP 750 `t"..."` template strings (`string.templatelib.Template` / `Interpolation`) over raw f-strings when building SQL queries, HTML snippets, shell invocations, or structured log payloads so interpolated values remain structured rather than flat text:

```python
from string.templatelib import Interpolation, Template


def render_safe_sql(query: Template) -> tuple[str, list[object]]:
    """Compile a PEP 750 template string into parameterized SQL and bindings."""
    sql_parts: list[str] = []
    params: list[object] = []
    for part in query:
        if isinstance(part, Interpolation):
            sql_parts.append("?")
            params.append(part.value)
        else:
            sql_parts.append(part)
    return "".join(sql_parts), params
```

### Standard-Library Zstandard (PEP 784)

Use `compression.zstd` directly instead of extra third-party bindings for straightforward streaming/one-shot Zstandard compression in `3.14+`:

```python
from compression import zstd


def roundtrip_payload(raw: bytes) -> bytes:
    """Compress and decompress bytes using Python 3.14+ compression.zstd."""
    compressed = zstd.compress(raw, level=3)
    return zstd.decompress(compressed)
```

## 3. Strict Static Typing (`basedpyright` + `ty`)

- **Authoritative CI Gate — `basedpyright`**: Run `basedpyright` in `"strict"` mode (`pyproject.toml` `[tool.basedpyright]`), rejecting implicit `Any`, unannotated parameters/returns, and unnarrowed unions.
- **Fast Local/Agent Verification — `ty`**: Run `uv run ty check` during inner-loop edits and on PEP 723 single-file scripts for sub-second feedback alongside `basedpyright`.
- **Legacy Fallback**: Use `mypy --strict` only if a legacy library relies on custom mypy compiler plugins lacking Pyright/ty support.

### Required Modern Typing Idioms

1. **`ReadOnly` `TypedDict` (PEP 705 / PEP 728)**: Mark immutable structured dictionary fields `ReadOnly[...]`:

   ```python
   from typing import ReadOnly, TypedDict


   class TelemetryFrame(TypedDict):
       """Immutable structured dictionary validated strictly."""

       timestamp_ns: ReadOnly[int]
       channel: ReadOnly[str]
   ```

2. **`TypeIs` (PEP 742)**: Prefer `typing.TypeIs[T]` over `TypeGuard` for sound true/false narrowing in `if`/`else` branches:

   ```python
   from typing import TypeIs


   def is_nonempty_str(value: object) -> TypeIs[str]:
       """Narrow both the true and false branches cleanly."""
       return isinstance(value, str) and bool(value)
   ```

3. **`@override` (PEP 698)**: Decorate subclass method overrides with `from typing import override` (`reportImplicitOverride` / safe refactoring).
4. **Domain Modeling vs. I/O Boundaries**:
   - **Internal domain state**: `@dataclass(slots=True, frozen=True, kw_only=True)` (low overhead, immutable, hashable).
   - **External boundaries** (JSON, CLI, HTTP, MCP, YAML configs): `pydantic` (`>=2.14`) `BaseModel` or `msgspec.Struct`.
5. **Timezone & Paths**: Always use `datetime.datetime.now(datetime.UTC)` (never naive `utcnow()` / `now()`) and `pathlib.Path` (never `os.path` string manipulation).
6. **Structured Concurrency**: Coordinate concurrent async tasks with `async with asyncio.TaskGroup()` and `asyncio.timeout(...)` rather than fire-and-forget `asyncio.gather` / dangling `create_task`.
