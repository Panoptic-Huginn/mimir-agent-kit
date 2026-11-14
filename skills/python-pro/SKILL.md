---
name: python-pro
description: Master Python 3.15 (3.14 floor) with PEP 649/810/750/695, uv/pixi, Marimo reactive notebooks, Google style + Ruff, basedpyright + ty, prek, pytest 9+, and Nov 2026 scientific/Bayesian/FFI practices.
metadata:
  version: v3
  publisher: jamielapointe
---

# Modern Python Engineering (`/python-pro`)

You are a modern Python engineering expert targeting **Python 3.15** by default (with **Python 3.14** as the hard compatibility floor; **never target `< 3.14`**), built around the November 2026 ecosystem (`uv`, `pixi`, `marimo`, `ruff`, `basedpyright`, `ty`, `prek`, `pytest` 9+, `deptry`, `pip-audit`, `zizmor`). Keep `SKILL.md` focused on architecture, routing decisions, and invariants; consult `references/` and `examples/` for deep code recipes and copy-ready templates.

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

- Bootstrapping, refactoring, linting, typing, testing, or packaging Python `>=3.14` / `>=3.15` libraries, services, CLIs, or scripts.
- Selecting between `uv` and `pixi`, configuring `pyproject.toml` or `pixi.toml`, setting up `prek` hooks, or hardening GitHub Actions CI and PyPI OIDC Trusted Publishing (PEP 740).
- Prototyping scientific simulations, Bayesian/MCMC inference, data pipelines, robotics HIL harnesses, or C23/C++23/Rust/SPARK Ada FFI extensions.

## Do not use this skill when

- The target is an interactive computational notebook deliverable (author via `/marimo-pro` or `/marimo-pair`; maintain legacy `.ipynb` only via `/jupyter-pro`).
- The target contains zero Python code (use `/cpp-pro`, `/rust-pro`, `/c-pro`, `/ada-spark-pro`, or `/cmake-pro` directly).

---

## 1. Decision Trees (Quick Routing)

### Runtime Target Decision Tree

~~~text
What Python runtime should the project target?
├─ Greenfield apps, services, CLIs, or libraries (DEFAULT)
│  └─ Python 3.15: requires-python = ">=3.15", Ruff target-version = "py315"
│     └─ Enables PEP 810 lazy import, PEP 814 frozendict, PEP 661 sentinel,
│        PEP 798 comprehension unpacking, PEP 686 UTF-8 default, PEP 799 Tachyon
├─ Blocked by missing third-party 3.15 wheels?
│  └─ Python 3.14 floor ONLY: requires-python = ">=3.14", target-version = "py314"
│     └─ Never target < 3.14; gate 3.15 features via sys.version_info >= (3, 15)
│        or __lazy_modules__; keep explicit encoding="utf-8" on all text I/O
└─ CPU-bound multi-core workload needing shared-memory thread parallelism?
   └─ Opt-in free-threaded 3.15t / 3.14t (PEP 779, PYTHON_GIL=0)
      └─ Audit all C extensions (Py_MOD_GIL_NOT_USED), eliminate unsynchronized
         global mutable state, and test explicitly on 3.15t in CI
~~~

### Toolchain & Packaging Decision Tree

~~~text
Which toolchain, backend, and lockfile fit this workspace?
[SINGLE-LOCKFILE INVARIANT: NEVER mix uv.lock and pixi.lock in one repo]
├─ Standalone single-file CLI, utility, or reproducible experiment?
│  └─ PEP 723 inline # /// script + uv run --script -> examples/pep723_script.py
├─ Pure Python / PyPI wheel ecosystem (DEFAULT)?
│  └─ uv + uv_build + uv.lock -> examples/pyproject.toml (or PEP 751 pylock.toml)
├─ Python-first repo needing conda-forge runtime libs (HDF5, OpenBLAS, GDAL)?
│  └─ pixi (>= 0.84.2) via [tool.pixi.*] in pyproject.toml + pixi.lock
└─ Polyglot repo (C23, C++23, Rust, SPARK Ada) or pinned native compilers / CUDA?
   └─ Standalone pixi.toml + pixi.lock -> examples/pixi.toml
      ├─ C++23 extensions -> scikit-build-core + nanobind
      └─ Rust extensions  -> maturin + PyO3
~~~

### Interactive Notebook & Skill Routing Decision Tree

~~~text
Where should interactive computation, FFI, or Git/CI delivery be routed?
├─ Greenfield exploration, EDA, dashboards, or reactive .py DAGs?
│  └─ /marimo-pro (default; never create new .ipynb notebooks)
├─ Live running Marimo kernel inspection or in-memory cell mutation?
│  └─ /marimo-pair (marimo._code_mode; never overwrite kernel-owned disk files)
├─ Existing legacy .ipynb or mandatory Google Colab runtime?
│  └─ /jupyter-pro (maintenance only, or migrate via uvx marimo convert)
├─ Native FFI / systems / build orchestration?
│  └─ /cpp-pro (C++23 nanobind), /rust-pro (PyO3 + maturin),
│     /c-pro (C23 cffi / ctypes), /ada-spark-pro (SPARK Ada HIL),
│     /cmake-pro (CMake 4.5+ nanobind_add_module)
└─ Git branches, PRs, CI gates, or GitHub governance?
   └─ /github-flow-lifecycle (code/PRs/CI) | /github-ops (org/repo governance)
~~~

---

## 2. Python Version Policy (3.15 Default, 3.14 Floor)

1. **Greenfield Default (`requires-python = ">=3.15"`)**: Default new projects, applications, and services to **Python 3.15**, adopting:
   - **PEP 810 (`lazy import`)**: Defer heavy module loads (`lazy import polars as pl` / `from mod lazy import ...`) for crisp CLI startup (`__lazy_modules__` provides portable 3.14 compatibility).
   - **PEP 814 (`frozendict`)**: Built-in immutable hashable mapping `frozendict({...})` replacing bespoke `MappingProxyType` wrappers.
   - **PEP 661 (`sentinel`)**: Built-in `sentinel("MISSING")` objects with clean `repr` and static typing support.
   - **PEP 798 (Comprehension Unpacking)**: Native `[*chunk for chunk in batches]` and `{**cfg for cfg in layers}` unpacking inside comprehensions.
   - **PEP 686 (UTF-8 Mode Default)**: UTF-8 is the default locale encoding in 3.15 (still pass `encoding="utf-8"` explicitly whenever `>=3.14` compatibility is supported).
   - **PEP 799 (`profiling.sampling` / Tachyon)**: Low-overhead built-in sampling profiler with free-threaded `3.15t` support.
2. **Compatibility Floor (`requires-python = ">=3.14"`)**: Fall back to `3.14` **only** when blocked by missing third-party 3.15 wheels. Gate 3.15-only syntax behind `sys.version_info >= (3, 15)` checks or 3.14 fallbacks, and enforce the universal `3.14+` baseline:
   - **PEP 649 / PEP 749 (`annotationlib`)**: Native deferred annotation evaluation. **Strictly ban `from __future__ import annotations`** via Ruff `TID251`.
   - **PEP 695 & PEP 696**: Native type parameter syntax (`class Buffer[T = bytes]:`, `def f[T: float](x: T) -> T:`) with `TypeVar` defaults over `TypeVar(...)` / `Generic[...]`.
   - **PEP 750 (`t"..."` Template Strings)**: `string.templatelib.Template` for injection-safe SQL, HTML, shell command, and structured-log formatting.
   - **PEP 784 (`compression.zstd`)**: Standard-library Zstandard compression instead of external wrappers.
   - **PEP 779 (`3.14t` / `3.15t` Free-Threading)**: Opt in (`PYTHON_GIL=0`) only when C extensions declare `Py_MOD_GIL_NOT_USED`, shared mutable state is synchronized, and `3.15t` passes CI.

Deep version-gating recipes and `annotationlib` / PEP 750 / PEP 784 examples live in [python_314_315_and_typing.md](references/python_314_315_and_typing.md).

---

## 3. Package & Environment Management (`uv` vs. `pixi`)

Standard `pip`, manual `venv`/`virtualenv`, and `Anaconda` workflows are unsupported. Always use **`uv`** by default (`uv.lock` or PEP 751 `pylock.toml`); switch to **`pixi`** (`>= 0.84.2`, `pixi.lock`) **only** when at least one of these 6 conditions holds, and **never mix `uv.lock` and `pixi.lock`** in the same repository:

| Criterion | Choose `uv` (Default) | Choose `pixi` |
| :--- | :--- | :--- |
| **Pure Python / PyPI wheels** | Yes (`pyproject.toml` + `uv.lock`) | Only if one of the 6 rules below triggers |
| **Multi-language workspace** | No | Yes (C23, C++23, Rust, SPARK Ada alongside Python) |
| **Native system libraries / compilers** | No | Yes (CUDA/cuDNN, LLVM, Clang, CMake, HDF5, OpenBLAS) |
| **`conda-forge`-only Python packages** | No | Yes (packages missing from PyPI) |
| **Built-in multi-env task runner** | `uv run` scripts / CI commands | Yes (when repo standardizes on `pixi run` DAG tasks) |
| **Non-Python global CLI tools in lockfile** | No | Yes (`clang-format`, `gersemi`, `cmake`, `ninja` pinned) |
| **Cross-OS Conda + PyPI binary lockfile** | Universal `uv.lock` / PEP 751 `pylock.toml` | Yes (`pixi.lock` pinning native Conda + PyPI binaries) |

### Packaging & Layout Rules

- **Layout & Marker**: Always use `src/<package_name>/` layout with a PEP 561 `py.typed` marker inside the package so type checkers read inline annotations downstream.
- **Build Backends**:
  - Pure Python: `uv_build` (turnkey template in [pyproject.toml](examples/pyproject.toml)).
  - C++23 Extensions: `scikit-build-core` + `nanobind` (`nb::ndarray` zero-copy buffers under `pixi` — see `/cmake-pro` and `/cpp-pro`).
  - Rust Extensions: `maturin` + `PyO3`.
- **Dependency Groups (PEP 735)**: Put `dev`, `lint`, `typecheck`, `test`, and `security` tooling exclusively in `[dependency-groups]`—never pollute `[project.optional-dependencies]` with dev tools. Manage dependencies via `uv add` / `uv add --group dev` or `pixi add` / `pixi add --pypi`.
- **Standalone Scripts (PEP 723)**: Single-file automation and reproducible experiments MUST embed `# /// script` metadata and execute via `uv run --script script.py` (template: [pep723_script.py](examples/pep723_script.py)).
- **Pixi Manifests**: Use `[tool.pixi.*]` inside `pyproject.toml` for Python-centric `conda-forge` projects, and standalone [pixi.toml](examples/pixi.toml) for polyglot C23/C++23/Rust/SPARK Ada or CUDA workspaces.

Full `uv`/`pixi` commands, build-backend snippets, and FFI recipes live in [packaging_uv_pixi_and_interop.md](references/packaging_uv_pixi_and_interop.md).

---

## 4. Reactive Notebooks (`marimo` over Legacy Jupyter)

1. **Marimo `.py` Default**: New projects needing interactive notebooks (EDA, algorithm prototyping, simulation diagnostics, dashboards) MUST author **Marimo reactive notebooks** (`.py` DAG files), never new `.ipynb` files. Marimo `.py` files diff cleanly in Git, eliminate hidden out-of-order state, and import cleanly under `pytest`.
2. **Execution Modes**:
   - Standalone exploratory notebooks: `marimo edit --sandbox notebook.py` backed by `uv` and PEP 723 `# /// script` metadata.
   - Workspace-coupled notebooks: `uv run marimo edit` or `pixi run marimo edit`.
3. **Static & CI Checks**: Enforce `marimo check` alongside `ruff format --check`, `ruff check`, `basedpyright`, and `ty check` in local hooks ([.pre-commit-config.yaml](examples/.pre-commit-config.yaml)) and remote CI ([ci.yml](examples/ci.yml)).
4. **Routing Boundary**: Delegate disk authoring to `/marimo-pro` and live kernel mutations to `/marimo-pair`. Restrict `/jupyter-pro` strictly to legacy `.ipynb` / Colab maintenance or migration via `uvx marimo convert old.ipynb -o new.py`.

---

## 5. 3-Tier Style Authority Hierarchy, Ruff & Static Analysis

Resolve formatting, lint, and architectural questions using this strict **3-Tier Style Authority Hierarchy** (Tier 1 overrides Tier 2; Tier 2 frames Tier 3):

1. **Tier 1 — Repository November 2026 Overrides (Highest Authority)**:
   - **88-Column Formatting & Double Quotes**: Configure `line-length = 88`, `quote-style = "double"`, and `docstring-code-format = true` in `[tool.ruff]`; rely on `ruff format` for wrapping and ignore only `"line-too-long"` when unbreakable strings or URLs remain.
   - **Grouped Idiomatic Imports & Absolute Paths**: Allow grouped symbol imports where crystal clear (`from pathlib import Path`, `from collections.abc import Sequence`, `from dataclasses import dataclass`) with `lines-after-imports = 2`; retain module imports for ambiguous namespaces (`import datetime`, `import math`, `import typing`); ban relative imports (`TID252`, `ban-relative-imports = "all"`).
   - **PEP 649 Native Deferred Annotations**: Strictly **ban `from __future__ import annotations`** via Ruff `TID251`.
2. **Tier 2 — Google Python Style Guide Baseline**:
   - Enforce the **Google Python Style Guide** for architecture, naming (`CapWords` classes, `lower_with_under` modules/functions/variables, `CAPS_WITH_UNDER` constants), Google docstrings (`D`, `convention = "google"` + `DOC` signature sync), explicit exception chaining (`raise ValueError(...) from err`), immutable default arguments, and zero runtime `assert` validation in production (`"assert"` / `S101` relaxed only in `tests/**`).
3. **Tier 3 — PEP 8 & 23-Family Ruff + `RUF201` Automated Enforcement**:
   - Use Ruff exclusively (replacing `black`/`pyink`, `isort`, `flake8`, and `pylint`) with all 23 rule families enabled: `E`, `F`, `W`, `I`, `N`, `D`, `DOC`, `UP`, `B`, `SIM`, `C4`, `DTZ`, `PT`, `RUF`, `PERF`, `FURB`, `S`, `ANN`, `ASYNC`, `PTH`, `TID`, `TC`, `PL`.
   - Enforce **`RUF201`**: every entry in `ignore` and `per-file-ignores` MUST use full rule names (`"line-too-long"`, `"assert"`), never raw alphanumeric codes.

### Dual Static Typing & Idiomatic Modeling

- **Strict CI Gate (`basedpyright`) + Local Loop (`ty`)**: Run `basedpyright` (`typeCheckingMode = "strict"`, zero implicit `Any`, explicit `@override`, `TypeIs`, `ReadOnly` `TypedDict` keys) in CI and `ty check` (`Astral ty`) for sub-second local/editor and PEP 723 script verification. This dual-checker workflow replaces legacy `mypy` (reserve `mypy --strict` strictly for legacy plugins without Pyright/ty support).
- **Domain Modeling & Async**: Use `@dataclass(slots=True, frozen=True, kw_only=True)` for internal domain/value types and `TypedDict` (with `ReadOnly`) for typed dictionaries; restrict `pydantic` (`>=2.14`) or `msgspec` to external I/O/HTTP/CLI/MCP boundaries. Prefer `pathlib.Path` (`PTH`), `asyncio.TaskGroup` + `asyncio.timeout` (`ASYNC`), and `datetime.datetime.now(datetime.UTC)` (`DTZ`).

Full Ruff rationale, strict typing patterns, and CI configs live in [style_ruff_testing_and_ci.md](references/style_ruff_testing_and_ci.md).

---

## 6. Local Hooks (`prek`), Testing (`pytest` 9+) & Remote GitHub CI

1. **Fast Pre-Commit Hooks via `prek`**:
   - Ship [.pre-commit-config.yaml](examples/.pre-commit-config.yaml) with SHA-pinned `pre-commit/pre-commit-hooks` (`3e8a8703264a2f4a69428a0aa4dcb512790b2c8c # frozen: v6.0.0`, including `no-commit-to-branch` for `main`/`master`) and run locally via **`prek`** (`uv run prek install --overwrite` / `uv run prek run --all-files`).
   - Passing `--no-verify` or `-n` to `git commit` is **strictly forbidden**; CI executes `SKIP=no-commit-to-branch uv run prek run --all-files --show-diff-on-failure` to catch bypasses.
2. **Native `[tool.pytest]` Configuration (`pytest` 9+)**:
   - Configure `pytest` 9+ via `[tool.pytest]` (`minversion = "9.0"`, `strict = true`, `filterwarnings = ["error"]`, `addopts = ["-ra", "--doctest-modules", "--cov", "--cov-branch"]`).
   - Pair with `pytest-randomly`, `pytest-cov` (branch coverage), and `hypothesis` property-based tests; organize suites under `unit`, `integration`, `regression`, and `e2e` markers.
3. **Hardened GitHub Actions CI & Trusted Publishing**:
   - Replicate [ci.yml](examples/ci.yml): `permissions: contents: read`, SHA-pinned Actions (`actions/checkout`, `astral-sh/setup-uv`, `actions/cache`) with `persist-credentials: false`, `uv lock --check` + `uv sync --locked` (or `pixi install --frozen`), `3.14` + `3.15` matrix (plus `3.15t` when claiming free-threading), `deptry`, `pip-audit`, `actionlint`, and `zizmor`.
   - Publish packages exclusively via **PyPI Trusted Publishing (OIDC)** with **PEP 740** digital attestations—never store long-lived PyPI API tokens in secrets.

---

## 7. November 2026 Domain & FFI Ecosystem (Always Verify Latest Versions)

> **Evergreen Package Verification Rule**: Always verify latest releases on **PyPI** / **`conda-forge`** (`uv add`, `uv pip compile`, `pixi info`, or official docs) and adopt the **latest recommended, actively maintained** scientific, engineering, statistics, and mathematics libraries rather than freezing legacy APIs or stale majors.

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

## 8. Bundled Templates & Deep References

- **References**: [python_314_315_and_typing.md](references/python_314_315_and_typing.md) (3.15/3.14 PEPs, dual-version gating, strict typing) | [packaging_uv_pixi_and_interop.md](references/packaging_uv_pixi_and_interop.md) (`uv`/`pixi` manifests, FFI backends, Marimo migration) | [style_ruff_testing_and_ci.md](references/style_ruff_testing_and_ci.md) (3-tier style hierarchy, Ruff 23 families, `pytest` 9+, OIDC PEP 740)
- **Examples**: [pyproject.toml](examples/pyproject.toml) (pure `uv` + `uv_build` + 23-family Ruff + `basedpyright` + `ty` + `pytest` 9+) | [pixi.toml](examples/pixi.toml) (polyglot `conda-forge` + `nanobind` + C++23 workspace) | [.pre-commit-config.yaml](examples/.pre-commit-config.yaml) (`prek` local QA hooks) | [ci.yml](examples/ci.yml) (hardened 3.14/3.15 matrix + security gates) | [pep723_script.py](examples/pep723_script.py) (standalone PEP 723 + 3.14/3.15 script template)
