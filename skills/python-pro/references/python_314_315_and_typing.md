# Python 3.14 / 3.15 Features & Strict Typing Guide

This reference details the **Python 3.15** default baseline, **Python 3.14** compatibility floor rules, dual-version gating idioms, and strict static type checking with **`basedpyright`** and **`ty`**.

## 1. Python 3.15 Default Language & Stdlib Features

Use Python `3.15` (`requires-python = ">=3.15"`) for greenfield services, CLIs, applications, and libraries unless blocked by missing third-party `3.15` wheels:

| Feature | PEP | Usage Pattern | Notes & 3.14 Fallback |
| :--- | :--- | :--- | :--- |
| **Lazy Imports** | PEP 810 | `lazy import polars as pl` / `from math lazy import erfc` | Cuts CLI startup latency; use module `__lazy_modules__` or local imports under `>=3.14` |
| **Immutable Mapping** | PEP 814 | Built-in `frozendict({"mode": "strict"})` | Order-preserving, hashable immutable mapping; use `types.MappingProxyType` under `3.14` |
| **Named Sentinels** | PEP 661 | `MISSING = sentinel("MISSING")` | Built-in singleton with direct type `int \| MISSING`; use `enum.Enum` singleton on `3.14` |
| **Comprehension Unpacking** | PEP 798 | `[*chunk for chunk in chunks]`, `{**d for d in dicts}` | Flattens iterables or merges dicts without nested helper loops |
| **UTF-8 Default Encoding** | PEP 686 | UTF-8 active by default across `open()` and stdlib I/O | Still pass `encoding="utf-8"` explicitly whenever `requires-python = ">=3.14"` |
| **Sampling Profiler** | PEP 799 | `python -m profiling.sampling run script.py` | `Tachyon` low-overhead profiler supporting live attach, async, and `3.15t` |

### PEP 810, PEP 814, PEP 661 & PEP 799 Operational Notes

- **PEP 810 (`lazy import`)**: Defers module execution until first attribute access (**reification**). Inspect `sys.lazy_modules` vs. `sys.modules` in diagnostics to check whether a module has loaded without triggering reification. Because missing optional dependencies fail on first use rather than at startup, test lazy subcommand paths explicitly.
- **PEP 814 (`frozendict`)**: Inherits from `object` (implementing `collections.abc.Mapping`, not `dict`), preserves insertion order, and is hashable whenever all keys and values are hashable—safe as `@functools.lru_cache` arguments, dictionary keys, and default function parameters.
- **PEP 661 (`sentinel`)**: Returns a named singleton whose `repr`, `copy`/`deepcopy`, and `pickle` identity persist reliably, and participates directly in type expressions (`timeout: int | MISSING = MISSING`) without `Literal[...]` wrappers.
- **PEP 799 (`profiling.sampling` / `Tachyon`)**: Captures statistical CPU/async call stacks via `python -m profiling.sampling run ...` or attaches to live production PIDs with negligible overhead, including free-threaded `3.15t` threads.

### Free-Threading Readiness (`3.14t` / `3.15t`, PEP 779)

- Run free-threaded builds with `PYTHON_GIL=0` and assert `not sys._is_gil_enabled()` in verification tests so C extensions lacking free-threading support cannot silently re-enable the GIL.
- Pure Python libraries must avoid unsynchronized mutable module-level globals; prefer immutable `frozendict` / frozen `@dataclass` values, `contextvars.ContextVar`, or explicit `threading.Lock` guards.
- C/C++/Rust extensions must declare GIL-free safety explicitly (`nanobind` `nb::mod_gil_not_used()`, `PyO3` `#[pymodule(gil_used = false)]`) and protect any internal static state.
- Keep `3.15t` as an opt-in CI matrix axis until every critical runtime dependency publishes verified free-threaded wheels.

## 2. Dual 3.14 / 3.15 Compatibility & Version-Gating Idioms

Fall back to `requires-python = ">=3.14"` **only** when required third-party dependencies lack `3.15` wheels. When supporting both `3.14` and `3.15`, never place 3.15-only syntax (`lazy import`, `[*x for x in xs]`) directly at parse scope because Python `3.14` parses the entire file eagerly.

### Runtime & Typing Guards (`sys.version_info >= (3, 15)`)

Type checkers (`basedpyright` and `ty`) understand `sys.version_info >= (3, 15)` directly when choosing runtime APIs while keeping return types portable via `collections.abc.Mapping` and PEP 695 aliases:

```python
import sys
from collections.abc import Mapping
from types import MappingProxyType


def freeze_config(raw: Mapping[str, str]) -> Mapping[str, str]:
    """Return an immutable mapping via PEP 814 on 3.15+ or proxy on 3.14."""
    if sys.version_info >= (3, 15):
        return frozendict(raw)  # type: ignore[name-defined]  # 3.15 builtin
    return MappingProxyType(dict(raw))
```

- Notice the tradeoff: `MappingProxyType` blocks mutations at runtime on `3.14` without copying into a hashable bucket table, whereas PEP 814 `frozendict` is natively hashable. Do not rely on `hash(freeze_config(...))` unless `requires-python = ">=3.15"`.

### Lazy Imports: `__lazy_modules__` Fallback vs. 3.15 `lazy import`

- **Python 3.15-only projects (`>=3.15`)**: Write `lazy import polars as pl` or `from math lazy import erfc` directly at top level.
- **Dual `3.14` / `3.15` projects (`>=3.14`)**: Declare `__lazy_modules__` *before* the imports it governs. Python `3.15+` activates lazy proxy loading for matching module names, while Python `3.14` parses it cleanly as a module attribute and imports eagerly (move heavy imports inside functions only if startup deferral is strictly required on `3.14`):

```python
# Portable >=3.14 pattern: lazy under Python 3.15+, standard eager import on 3.14
__lazy_modules__ = ["json", "polars"]

import json
import polars as pl
```

```text
# Native Python 3.15+ syntax (use when requires-python = ">=3.15"):
lazy import polars as pl
from math lazy import erfc
```

### Sentinels: PEP 661 `sentinel` vs. `enum.Enum` Singleton Fallback

When targeting `>=3.15`, call `MISSING = sentinel("MISSING")` directly as a builtin and annotate parameters as `timeout: float | MISSING = MISSING`. When supporting `3.14`, gate or use a single-member `enum.Enum` singleton—unlike `object()`, an `Enum` singleton has a readable `repr`, pickles by module/name, and narrows cleanly in `basedpyright` and `ty`:

```python
# Python 3.15+ (PEP 661 built-in sentinel):
MISSING = sentinel("MISSING")  # type: ignore[name-defined]


def connect_timeout(seconds: float | MISSING = MISSING) -> float:
    """Resolve explicit timeout under Python 3.15+ PEP 661."""
    return 5.0 if seconds is MISSING else seconds
```

```python
import enum
from typing import Final, Literal


class _MissingSentinel(enum.Enum):
    """Single-member enum providing a typed sentinel compatible with Python 3.14."""

    TOKEN = enum.auto()


MISSING: Final = _MissingSentinel.TOKEN
type Missing = Literal[_MissingSentinel.TOKEN]


def resolve_timeout(seconds: float | Missing = MISSING) -> float:
    """Resolve explicit timeout or fall back to default budget on Python 3.14+."""
    if seconds is MISSING:
        return 5.0
    return seconds
```

### Comprehension Unpacking (PEP 798) & UTF-8 I/O (PEP 686)

- **PEP 798**: Under `>=3.15`, flatten sequences with `[*chunk for chunk in chunks]` and merge mappings with `{**layer for layer in layers}` directly. Under `>=3.14`, use `itertools.chain.from_iterable(chunks)` and nested dict comprehensions so the module parses cleanly on `3.14`:

```text
# Native Python 3.15+ (PEP 798 unpacking in comprehensions):
flat_items = [*chunk for chunk in chunks]
merged_cfg = {**layer for layer in layers}
```

```python
from itertools import chain


# Portable >=3.14 equivalents when 3.14 remains in the CI matrix:
chunks: list[list[int]] = [[1, 2], [3, 4]]
layers: list[dict[str, int]] = [{"a": 1}, {"b": 2, "a": 3}]
flat_items = list(chain.from_iterable(chunks))
merged_cfg = {key: val for layer in layers for key, val in layer.items()}
```

- **PEP 686**: Even though `3.15` enables UTF-8 mode by default across all platforms, always pass `encoding="utf-8"` explicitly to `Path.read_text()`, `Path.write_text()`, and `open()` in any codebase with `requires-python = ">=3.14"`.

## 3. Universal Python 3.14+ Floor Features (Mandatory Baseline)

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

- **Strict Rule**: **Never write `from __future__ import annotations`** in `>=3.14` codebases. Enforce this via Ruff rule `TID251` (`banned-api`) in `pyproject.toml`, and place annotation-only imports inside `if TYPE_CHECKING:` blocks (`TC`).

### Native Generics & TypeVar Defaults (PEP 695 & PEP 696)

Prefer bracketed type parameters over legacy `TypeVar` / `Generic` boilerplate:

```python
type Matrix[Scalar: (float, complex) = float] = list[list[Scalar]]


class RingBuffer[T = bytes]:
    """Fixed-capacity typed buffer using PEP 695/696 defaults."""

    def __init__(self, items: list[T] | None = None) -> None:
        self._items: list[T] = list(items) if items is not None else []
```

### `type` Alias vs. `NewType`, `Self` (PEP 673), and `Final`

- **`type` alias (PEP 695)**: Use `type Name = ...` for transparent structural aliases (replacing legacy `TypeAlias`); zero runtime wrapping overhead.
- **`NewType`**: Use `NewType("OrderId", int)` **only** when nominal type safety is required to stop callers from swapping two structurally identical primitives (e.g., `UserId` vs. `OrderId`).
- **`Self` (PEP 673)** and **`Final`**: Use `Self` on fluent builders, `classmethod` constructors, and `__enter__` methods; use `Final` for module/class constants that must never be rebound or overridden:

```python
from typing import Final, NewType, Self


DEFAULT_CAPACITY: Final[int] = 64

type SampleVector = list[float]
SensorId = NewType("SensorId", str)
StreamId = NewType("StreamId", str)


class PipelineBuilder:
    """Fluent configuration builder using PEP 673 Self."""

    def __init__(self, sensor: SensorId) -> None:
        self.sensor = sensor
        self.samples: SampleVector = []

    def with_sample(self, value: float) -> Self:
        """Append a measurement and return the concrete builder subtype."""
        self.samples.append(value)
        return self
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

## 4. Strict Static Typing (`basedpyright` + `ty`)

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
