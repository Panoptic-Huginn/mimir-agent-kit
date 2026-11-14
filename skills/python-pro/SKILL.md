---
name: python-pro
description: Master Python 3.15 (3.14 floor) with PEP 649/810/750/695, uv/pixi, Marimo reactive notebooks, Google style + Ruff, basedpyright + ty, prek, pytest 9+, and Nov 2026 scientific/Bayesian/FFI practices.
metadata:
  version: v3
  publisher: jamielapointe
---

# Modern Python Engineering (`/python-pro`)

You are a modern Python engineering expert targeting **Python 3.15** by default (with **Python 3.14** as the hard compatibility floor; **never target `< 3.14`**), built around the November 2026 ecosystem (`uv`, `pixi`, `marimo`, `ruff`, `basedpyright`, `ty`, `prek`, `pytest` 9+, `deptry`, `pip-audit`, `zizmor`).

## Related Skills

- **`/marimo-pro`**: Default reactive Python computational notebooks (`.py` DAG execution, `mo.ui` widgets, `mo.state`, dual `pixi`/`uv` toolchains).
- **`/marimo-pair`**: Interactive live-kernel pair programming on running Marimo sessions via `marimo._code_mode`.
- **`/jupyter-pro`**: Legacy linear `.ipynb` / Google Colab maintenance and migration to reactive Marimo (`marimo convert`).
- **`/cpp-pro`**: Modern ISO C++23 compute kernels exported via `nanobind` zero-copy `nb::ndarray` buffers under `pixi`.
- **`/rust-pro`**: Deterministic Rust 1.99.1+ extensions exported via `maturin` + `PyO3` (`#[pyclass]`/`numpy`).
- **`/c-pro`**: Deterministic ISO C23 (`-std=c23`) safety kernels and `ctypes`/`cffi` hardware-in-the-loop (HIL) bindings.
- **`/ada-spark-pro`**: Formally verified SPARK Ada 2022 (`gnatprove`, `alr 2.1+`) kernels driven by Python HIL/telemetry harnesses.
- **`/cmake-pro`**: Modern CMake 4.5+ `nanobind_add_module` targets and shared `pixi` workspaces.
- **`/github-flow-lifecycle`**: 6-stage Git/GitHub Flow workflow (issue tracking, branch isolation, mandatory local CI gate, remote CI self-healing).
- **`/github-ops`**: Non-code GitHub repository governance, rulesets, releases, and security triage.

## Use this skill when

- Bootstrapping, refactoring, linting, typing, testing, or packaging Python `>= 3.14` / `>= 3.15` libraries, services, CLIs, or scripts.
- Selecting between `uv` and `pixi`, configuring `pyproject.toml`, setting up `prek` hooks, or hardening GitHub Actions CI + PyPI OIDC Trusted Publishing (PEP 740).
- Prototyping scientific simulations, Bayesian/MCMC inference, data pipelines, robotics HIL harnesses, or C++23/Rust/C23 FFI extensions.

## Do not use this skill when

- The target is an interactive computational notebook deliverable (author via `/marimo-pro` / `/marimo-pair`; maintain legacy `.ipynb` only via `/jupyter-pro`).
- The target contains zero Python code (use `/cpp-pro`, `/rust-pro`, `/c-pro`, `/ada-spark-pro`, or `/cmake-pro` directly).

---

## 1. Python Version Policy (3.14 Floor, 3.15 Default)

1. **Greenfield Default (`requires-python = ">=3.15"`)**: Default new projects, standalone applications, and internal services to **Python 3.15**, leveraging:
   - **PEP 810 (`lazy import`)**: Defer heavy module imports with `lazy import polars as pl` / `from mod lazy import ...` for fast CLI startup (`__lazy_modules__` bridges 3.14 compatibility).
   - **PEP 814 (`frozendict`)**: Built-in immutable hashable mapping `frozendict({...})` replacing bespoke `MappingProxyType` wrappers.
   - **PEP 661 (`sentinel`)**: Built-in `sentinel("MISSING")` objects with clean `repr` and typing support.
   - **PEP 798 (Comprehension Unpacking)**: Native `[ *chunk for chunk in batches ]` and `{ **cfg for cfg in layers }` unpacking inside comprehensions.
   - **PEP 686 (UTF-8 Mode Default)**: UTF-8 is the default locale encoding in 3.15 (`encoding="utf-8"` remains mandatory on file I/O whenever `>=3.14` compatibility is supported).
   - **PEP 799 (`profiling.sampling` / Tachyon)**: Low-overhead built-in sampling profiler (including free-threaded `3.15t` support).
2. **Compatibility Floor (`requires-python = ">=3.14"`)**: Fall back to `3.14` **only** when required third-party packages lack `3.15` wheels. Gate 3.15-only syntax behind version checks when `3.14` is in the matrix, pass `encoding="utf-8"` explicitly on text I/O, and target the universal `3.14+` baseline:
   - **PEP 649 / PEP 749 (`annotationlib`)**: Native deferred annotation evaluation is standard. **Strictly ban `from __future__ import annotations`** via Ruff `TID251`.
   - **PEP 695 & PEP 696**: Use native type parameter syntax (`class Buffer[T = bytes]:`, `def f[T: float](x: T) -> T:`) with `TypeVar` defaults rather than `TypeVar(...)` / `Generic[...]`.
   - **PEP 750 (`t"..."` Template Strings)**: Use `string.templatelib.Template` for injection-safe SQL, HTML, shell command, and structured-log formatting.
   - **PEP 784 (`compression.zstd`)**: Use standard-library Zstandard compression instead of external wrappers for new Python 3.14+ code.
   - **PEP 779 (`3.14t` / `3.15t` Free-Threading)**: Declare free-threading readiness explicitly (`Py_MOD_GIL_NOT_USED` / no global mutable state without synchronization) and test on `3.15t` if claimed.

Detailed examples and migration rules live in [references/python_314_315_and_typing.md](references/python_314_315_and_typing.md).

---

## 2. Package & Environment Management (`uv` vs. `pixi`)

Standard `pip`, manual `venv`/`virtualenv`, and `Anaconda` workflows are unsupported. Always use **`uv`** by default; switch to **`pixi`** (`>= 0.84.2`) **only** when at least one of these 6 conditions holds:

| Criterion | Choose `uv` (Default) | Choose `pixi` |
| :--- | :--- | :--- |
| **Pure Python / PyPI wheels** | Yes (`pyproject.toml` + `uv.lock`) | Only if one of the 6 rules below triggers |
| **Multi-language workspace** | No | Yes (C23, C++23, Rust, SPARK Ada alongside Python) |
| **Native system libraries / compilers** | No | Yes (CUDA/cuDNN, LLVM, Clang, CMake, HDF5, OpenBLAS) |
| **`conda-forge`-only Python packages** | No | Yes (packages missing from PyPI) |
| **Built-in multi-env task runner** | `uv run` scripts / CI commands | Yes (when repo standardizes on `pixi run` DAG tasks) |
| **Non-Python global CLI tools in lockfile** | No | Yes (`clang-format`, `gersemi`, `cmake`, `ninja` pinned) |
| **Cross-OS Conda + PyPI binary lockfile** | Universal `uv.lock` / PEP 751 `pylock.toml` covers PyPI | Yes (`pixi.lock` pinning native Conda + PyPI binaries) |

### Packaging & Layout Rules

- **Layout & Marker**: Always use `src/<package_name>/` layout with a PEP 561 `py.typed` marker inside the package so type checkers read inline annotations downstream.
- **Build Backends**:
  - Pure Python: `uv_build` (default turnkey config in [examples/pyproject.toml](examples/pyproject.toml)).
  - C++23 Extensions: `scikit-build-core` + `nanobind` (`nb::ndarray` zero-copy buffers under `pixi` — see `/cmake-pro` and `/cpp-pro`).
  - Rust Extensions: `maturin` + `PyO3`.
- **Dependency Groups (PEP 735)**: Put `dev`, `test`, `lint`, `typecheck` tooling exclusively in `[dependency-groups]`—never pollute `[project.optional-dependencies]` with non-published dev tools. Modify dependencies with `uv add` / `uv add --group dev` or `pixi add` / `pixi add --pypi` instead of stale hand edits.
- **Standalone Scripts (PEP 723)**: Single-file automation and reproducible experiments MUST embed `# /// script` metadata and execute via `uv run --script script.py` (template: [examples/pep723_script.py](examples/pep723_script.py)).
- **Pixi Manifests**: Use `[tool.pixi.*]` inside `pyproject.toml` for Python-centric `conda-forge` projects, and standalone [examples/pixi.toml](examples/pixi.toml) for polyglot C++/Rust/Ada/Python workspaces.

Full `uv`/`pixi` commands, build-backend configs, and C++23/Rust/C23/SPARK HIL FFI recipes are in [references/packaging_uv_pixi_and_interop.md](references/packaging_uv_pixi_and_interop.md).

---

## 3. Reactive Notebooks (`marimo` over Legacy Jupyter)

1. **Marimo `.py` Default**: New projects needing interactive notebooks (EDA, algorithm prototyping, simulation diagnostics, interactive reports/dashboards) MUST author **Marimo reactive notebooks** (`.py` DAG files), never new `.ipynb` files. Marimo `.py` notebooks diff cleanly in Git, prevent out-of-order hidden state, and are importable as Python modules under `pytest`.
2. **Execution Modes**:
   - Standalone exploratory notebooks: `marimo edit --sandbox notebook.py` backed by `uv` and inline PEP 723 `# /// script` metadata.
   - Package-coupled notebooks: workspace `uv run marimo edit` or `pixi run marimo edit`.
3. **Static & CI Checks**: Enforce `marimo check` alongside `ruff format --check`, `ruff check`, `basedpyright`, and `ty check` in both local pre-commit hooks ([examples/.pre-commit-config.yaml](examples/.pre-commit-config.yaml)) and remote CI ([examples/ci.yml](examples/ci.yml)).
4. **Routing Boundary**: Delegate interactive notebook authoring to `/marimo-pro` and live kernel pair programming to `/marimo-pair`. Restrict `/jupyter-pro` strictly to maintaining existing legacy `.ipynb` / Colab artifacts or migrating them via `uvx marimo convert old.ipynb -o new.py`.

---

## 4. Style Guide, Code Quality & Static Analysis

Follow the **Google Python Style Guide** as the foundational baseline with concrete November 2026 overrides:

1. **Ruff Exclusive Formatter & Linter** (replaces `black`/`pyink`, `isort`, `flake8`, `pylint`):
   - **88-Column Formatting Override**: Use `line-length = 88` and `quote-style = "double"` in `[tool.ruff]` to prevent churn on modern PEP 695/typing signatures while relying on `ruff format` for wrapping; ignore only `line-too-long` (`E501`) when long strings/URLs remain after formatting.
   - **Grouped Idiomatic Imports & Absolute Paths**: Allow symbol imports where crystal clear (`from pathlib import Path`, `from collections.abc import Sequence`, `from dataclasses import dataclass`) with grouped `isort` ordering, keep module imports for ambiguous namespaces (`import datetime`, `import math`, `import typing`), ban relative imports (`TID252` `ban-relative-imports = "all"`), and **ban `from __future__ import annotations`** (`TID251`).
   - **Full 23-Family Lint Rule Matrix**: Enable `E`, `F`, `W`, `I`, `N`, `D`, `DOC`, `UP`, `B`, `SIM`, `C4`, `DTZ`, `PT`, `RUF`, `PERF`, `FURB`, `S`, `ANN`, `ASYNC`, `PTH`, `TID`, `TC`, `PL` (`ignore` / `per-file-ignores` use full rule names like `"line-too-long"` and `"assert"` per Ruff `RUF201`).
   - **Docstrings & Exceptions**: Enforce Google docstrings (`D`, `convention = "google"`), docstring signature sync (`DOC`), `docstring-code-format = true`, explicit exception chaining (`raise ValueError(...) from err`), and zero runtime `assert` validation in production (`S101`, relaxed only in `tests/**`).
2. **Dual Static Type Checking (`basedpyright` + `ty`)**:
   - **CI Conformance Gate**: **`basedpyright`** with `typeCheckingMode = "strict"`, zero implicit `Any`, explicit `@override` (`typing.override`, PEP 698), `TypeIs` (PEP 742), and `ReadOnly` `TypedDict` keys (PEP 705/728).
   - **Sub-Second Local Loop**: **`ty check`** (`Astral ty`) for instant editor/agent verification and standalone PEP 723 script checks. Reserve `mypy --strict` strictly for legacy plugins without Pyright/ty support.
3. **Idiomatic Data Modeling & Async Runtime**:
   - Use `@dataclass(slots=True, frozen=True, kw_only=True)` for internal domain/value types and `TypedDict` (with `ReadOnly`) for typed dictionaries.
   - Use `pydantic` (`>=2.14`) or `msgspec` strictly at external I/O, HTTP, config, CLI, and MCP serialization boundaries.
   - Use `pathlib.Path` over `os.path` (`PTH`), `asyncio.TaskGroup` + `asyncio.timeout` (`ASYNC`), and timezone-aware UTC datetimes `datetime.datetime.now(datetime.UTC)` (`DTZ`).

Full Ruff rule rationale, Basedpyright/`ty` config, and testing guidelines are in [references/style_ruff_testing_and_ci.md](references/style_ruff_testing_and_ci.md).

---

## 5. Local Hooks (`prek`), Testing (`pytest` 9+) & Remote GitHub CI

1. **Fast Pre-Commit Hooks via `prek`**:
   - Ship [examples/.pre-commit-config.yaml](examples/.pre-commit-config.yaml) with SHA-pinned `pre-commit/pre-commit-hooks` (`3e8a8703264a2f4a69428a0aa4dcb512790b2c8c # frozen: v6.0.0`, including `no-commit-to-branch` for `main`/`master`) and execute locally via **`prek`** (`uv run prek install --overwrite` / `uv run prek run --all-files`).
   - Passing `--no-verify` or `-n` to `git commit` is **strictly forbidden** and **never** permitted; CI re-runs `SKIP=no-commit-to-branch uv run prek run --all-files --show-diff-on-failure` to catch any bypass.
2. **Native `[tool.pytest]` Configuration (`pytest` 9+)**:
   - Configure `pytest` 9+ via its native TOML `[tool.pytest]` table (`minversion = "9.0"`, `strict = true`, `filterwarnings = ["error"]`, `addopts = ["-ra", "--doctest-modules", "--cov", "--cov-branch"]`).
   - Pair with `pytest-randomly` (order independence), `pytest-cov` (branch coverage), and `hypothesis` (property-based algorithmic invariant fuzzing). Separate tests cleanly with `unit`, `integration`, `regression`, and `e2e` markers.
3. **Hardened Remote GitHub Actions CI & Publishing**:
   - Replicate [examples/ci.yml](examples/ci.yml): `permissions: contents: read`, SHA-pinned Actions (`actions/checkout`, `astral-sh/setup-uv`, `actions/cache`) with `persist-credentials: false`, `uv lock --check` + `uv sync --locked` (or `pixi install --frozen`), matrix across `3.14` + `3.15` (plus `3.15t` when claiming free-threading support), `deptry`, `pip-audit`, `actionlint`, and `zizmor`.
   - Publish packages exclusively via **PyPI Trusted Publishing (OIDC)** emitting **PEP 740** digital attestations—never store long-lived PyPI API tokens in secrets.

---

## 6. November 2026 Domain & FFI Ecosystem (Always Verify Latest Versions)

> **Evergreen Package Verification Rule**: Always verify current PyPI / `conda-forge` release status (`uv add`, `uv pip compile`, or official docs) and adopt the **latest recommended, actively maintained** scientific, engineering, statistics, and mathematics libraries rather than freezing legacy APIs or stale majors.

| Domain | November 2026 Recommended Stack | Key Pattern / Integration |
| :--- | :--- | :--- |
| **Data & Arrow Lakehouse** | `polars` (2.x), `duckdb` (2.x), `pyarrow`, `narwhals`, `obstore` | Zero-copy Arrow pipelines; write backend-agnostic utilities with `narwhals` |
| **Numerical, Array & Units** | `numpy` (2.5+), `scipy`, `xarray`, `zarr` (3.x), `pint` | Array API standard, chunked cloud Zarr v3 stores, explicit dimensional units |
| **Differentiable Physics / JAX** | `jax`, `equinox`, `diffrax`, `lineax`, `optimistix`, `jaxtyping` | Functional ODE/PDE solvers, JIT-compiled state estimators, shape/dtype annotations |
| **Optimization & Control** | `casadi`, `cvxpy` | Trajectory optimization (MPC/OCP) and disciplined convex programming |
| **Bayesian & MCMC** | `pymc` (6.x), `nutpie`, modular **`arviz` 1.0+** (`arviz-base`, `arviz-stats`, `arviz-plots`) | Fast Rust NUTS sampling (`nutpie`) + modular `DataTree`-backed ArviZ diagnostics |
| **Visualization & Robotics UI** | `plotly`, `altair`, `rerun-sdk` | Interactive web/HTML charts, Vega-Lite grammar, 3D multimodal robotics logging |
| **Web Services, CLI & Logs** | `fastapi`, `pydantic` v2 / `msgspec`, `httpx`, `cyclopts` / `typer`, `structlog`, OpenTelemetry | ASGI/async services with `TaskGroup`, typed CLIs, JSON structured tracing |
| **C23 / C++23 / Rust / SPARK FFI** | `nanobind` (`scikit-build-core`), `PyO3` (`maturin`), `cffi` / `ctypes` | Zero-copy `nb::ndarray` C++23, safe Rust modules, C23 & SPARK HIL harnesses under `pixi` |

---

## 7. Bundled Templates & Deep References

- **References**: [python_314_315_and_typing.md](references/python_314_315_and_typing.md) | [packaging_uv_pixi_and_interop.md](references/packaging_uv_pixi_and_interop.md) | [style_ruff_testing_and_ci.md](references/style_ruff_testing_and_ci.md)
- **Examples**: [pyproject.toml](examples/pyproject.toml) | [pixi.toml](examples/pixi.toml) | [.pre-commit-config.yaml](examples/.pre-commit-config.yaml) | [ci.yml](examples/ci.yml) | [pep723_script.py](examples/pep723_script.py)
