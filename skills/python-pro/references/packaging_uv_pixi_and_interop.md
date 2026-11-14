# Packaging (`uv` & `pixi`), Polyglot FFI & November 2026 Ecosystem

This reference covers package management selection (`uv` vs. `pixi`), embedded `[tool.pixi.*]` vs. standalone `pixi.toml` manifests, `src/` project structure, build-backend snippets (`uv_build`, `scikit-build-core`, `maturin`), PEP 723/735/751 standards, polyglot FFI integration, Marimo notebook workflows, and the November 2026 library landscape.

## 1. Decision Matrix: `uv` (Default) vs. `pixi`

Always default to **`uv`**. Adopt **`pixi`** (`>= 0.84.2`) **only** when one or more of the following 6 conditions apply:

1. **Multi-Language Workspace**: The repository co-develops Python with C23, C++23, Rust, SPARK Ada, or CUDA in one build graph.
2. **Native System Libraries or Compilers**: The project needs non-PyPI binary toolchains or libraries (LLVM/Clang, CMake, Ninja, `lld`, CUDA/cuDNN, HDF5, GDAL, OpenBLAS, `gnat_native`).
3. **`conda-forge`-Only Python Packages**: At least one required Python dependency is distributed solely on `conda-forge` and absent from PyPI.
4. **Pixi Built-In Task Runner**: The project explicitly adopts `[tasks]` / `[tool.pixi.tasks]` workflows across contributors.
5. **Co-Managed Non-Python Global CLIs**: Non-Python developer tools (`clang-format`, `clang-tidy`, `gersemi`, `cmake`, `ninja`, `actionlint`) must resolve uniformly in the project environment.
6. **Multi-Platform Conda + PyPI Binary Lockfiles (`pixi.lock`)**: Reproducible locking across native Conda binary packages *and* PyPI wheels is required across `linux-64`, `linux-aarch64`, and `osx-arm64`.
   - For pure Python and PyPI binary wheels, **`uv.lock`** and **PEP 751 `pylock.toml`** already deliver universal cross-platform locking with zero Conda overhead.

### Single-Lockfile Invariant: Embedded `[tool.pixi.*]` vs. Standalone `pixi.toml`

> **Single-Lockfile Rule**: Every repository has **one** authoritative lockfile—either `uv.lock` (pure Python / PyPI wheels) **or** `pixi.lock` (Conda + PyPI resolution). **Never** maintain both `uv.lock` and `pixi.lock` in the same repository.

- **Embedded `[tool.pixi.*]` in `pyproject.toml`**: Ideal for Python-first packages (such as scientific or astrophysics analytics) that depend on `conda-forge` system libraries (`openblas`, `hdf5`, `cuda-version`) while publishing standard PEP 621 Python wheels (`uv_build`, `hatchling`, or `scikit-build-core`).
- **Standalone `pixi.toml`**: Ideal for polyglot workspaces (`C23`, `C++23`, `Rust`, `SPARK Ada` + Python) where `CMakePresets.json`, Cargo workspaces, or Alire crates sit alongside Python bindings without mixing native toolchain graphs into Python wheel metadata (see [../examples/pixi.toml](../examples/pixi.toml)).

```toml
# Python-first repository needing conda-forge native libraries in pyproject.toml
# Lockfile: pixi.lock ONLY (do NOT generate uv.lock alongside it).
[project]
name = "astro-telemetry"
version = "0.1.0"
requires-python = ">=3.15"
dependencies = [
    "numpy>=2.5.0",
    "polars>=2.0.0",
]

[build-system]
requires = ["uv_build>=0.12.0,<0.13.0"]
build-backend = "uv_build"

[tool.pixi.workspace]
channels = ["conda-forge"]
platforms = ["linux-64", "linux-aarch64", "osx-arm64"]
requires-pixi = ">=0.84.2"

[tool.pixi.dependencies]
python = ">=3.15,<3.16"
hdf5 = ">=1.14.6"
openblas = ">=0.3.28"

[tool.pixi.pypi-dependencies]
astro-telemetry = { path = ".", editable = true }
pytest = ">=9.2.0"

[tool.pixi.tasks]
test = "pytest -v"
```

| Aspect | Embedded `[tool.pixi.*]` (`pyproject.toml`) | Standalone `pixi.toml` | Pure `uv` (`pyproject.toml`) |
| :--- | :--- | :--- | :--- |
| **Primary Use Case** | Python package + `conda-forge` native libs | Polyglot C23/C++23/Rust/SPARK + Python | Pure Python apps, libs, CLIs, PyPI wheels |
| **Lockfile** | `pixi.lock` | `pixi.lock` | `uv.lock` (+ optional `pylock.toml`) |
| **Command Runner** | `pixi run ...` | `pixi run ...` | `uv run ...` |

## 2. Standard Project Layout, Build Backends & PEPs

### Repository & `src/` Structure

```text
my-python-project/
├── .github/workflows/ci.yml
├── .pre-commit-config.yaml
├── pyproject.toml
├── uv.lock                    # OR pixi.lock (never both)
├── src/
│   └── my_package/
│       ├── __init__.py
│       └── py.typed           # PEP 561 marker (mandatory for importable packages)
└── tests/
    ├── unit/
    ├── integration/
    └── regression/
```

### Build Backends (`uv_build`, `scikit-build-core` + `nanobind`, `maturin` + `PyO3`)

1. **Pure Python Libraries & CLIs (`uv_build`)**: Fast, deterministic, zero-config `src/<pkg>/` packaging (full template in [../examples/pyproject.toml](../examples/pyproject.toml)):

   ```toml
   [build-system]
   requires = ["uv_build>=0.12.0,<0.13.0"]
   build-backend = "uv_build"
   ```

2. **C++23 Native Extensions (`scikit-build-core` + `nanobind`)**: Zero-copy `nb::ndarray` buffers compiled via CMake 4.5+ and Ninja; pair with `/cpp-pro` and `/cmake-pro`:

   ```toml
   [build-system]
   requires = ["scikit-build-core>=1.1.0,<2.0", "nanobind>=3.1.0"]
   build-backend = "scikit_build_core.build"

   [tool.scikit-build]
   minimum-version = "build-system.requires"
   cmake.build-type = "Release"
   wheel.packages = ["src/my_cpp_ext"]
   ```

3. **Rust Native Extensions (`maturin` + `PyO3`)**: Safe zero-copy Rust extensions built from `Cargo.toml` + `src/`; pair with `/rust-pro`:

   ```toml
   [build-system]
   requires = ["maturin>=1.16.0,<2.0"]
   build-backend = "maturin"

   [tool.maturin]
   python-source = "src"
   module-name = "my_rust_ext._native"
   features = ["pyo3/extension-module"]
   ```

### Dependency Groups (PEP 735), Lockfiles (PEP 751) & Scripts (PEP 723)

- **PEP 735 `[dependency-groups]`**: Place `dev`, `test`, `lint`, and `typecheck` tooling strictly under `[dependency-groups]` in `pyproject.toml` so downstream wheel consumers never inherit dev tooling as extras.
- **`[project.optional-dependencies]`**: Reserve strictly for runtime optional feature extras shipped to library users (e.g., `plotting`, `cuda`).
- **Lockfile Synchronization**: Update dependencies via CLI tooling rather than manual version guessing:
  - `uv`: `uv add polars`, `uv add --group dev hypothesis`, `uv lock --check`, `uv sync --locked`
  - `pixi`: `pixi add numpy`, `pixi add --pypi pytest-cov`, `pixi install --frozen`
- **PEP 751 `pylock.toml`**: Export universal standard lockfiles when external deployment or container builders require PEP 751 artifacts: `uv export --format pylock.toml -o pylock.toml`.
- **PEP 723 Inline Script Metadata**: All single-file automation scripts, reproducible experiments, and standalone diagnostics MUST embed a PEP 723 `# /// script` header (see [../examples/pep723_script.py](../examples/pep723_script.py)) and execute via `uv run --script my_script.py`.

## 3. Polyglot FFI Alignment with Sibling Skills

| Interop Path | Recommended Tooling | Aligned Sibling Skill | Key Rules |
| :--- | :--- | :--- | :--- |
| **C++23 Compute Kernels** | `nanobind` + `scikit-build-core` under `pixi` | `/cpp-pro`, `/cmake-pro` | Exchange buffers via zero-copy `nb::ndarray`, release GIL across compute, declare `nb::mod_gil_not_used()` for `3.14t`/`3.15t` |
| **Rust Safety / Compute Extensions** | `PyO3` (`>=0.30`) + `maturin` | `/rust-pro` | Enforce `#[pymodule(gil_used = false)]` where thread-safe, use `rust-numpy` for zero-copy array views |
| **ISO C23 Kernels & HIL** | `cffi` (ABI/API mode) or `ctypes` | `/c-pro` | Mirror C23 `extern "C"` header structs explicitly (`cffi.FFI().cdef(...)`), validate sizes/bounds at FFI boundary |
| **SPARK Ada Static Libraries** | `ctypes` / `cffi` via exported `extern "C"` symbols | `/ada-spark-pro` | Drive formally verified Ada/C-ABI robotics interceptors from Python HIL (`pytest` + `hypothesis`) harnesses |

## 4. Marimo-First Notebook Workflows & Legacy Migration

All new interactive data exploration, parameter sweeps, diagnostics, and reports MUST be authored as reactive **Marimo** `.py` notebooks (pure Python DAGs, Git-clean diffs, zero hidden execution order), never new `.ipynb` files.

### Execution & Sandbox Workflows

- **Workspace Notebooks**: Launch notebooks coupled to your project `src/` package with `uv run marimo edit notebooks/analysis.py` (or `pixi run marimo edit notebooks/analysis.py` when native `conda-forge` libraries are required).
- **Standalone Sandbox Notebooks**: Launch self-contained exploratory notebooks with `marimo edit --sandbox analysis.py`, storing dependencies inline via PEP 723 `# /// script` metadata so anyone can reproduce the environment via `uv` without polluting project manifests.

### Testing Reusable Notebook Functions & CI DAG Verification

- **Importable `@app.function` & `@app.class_definition` Units**: Author reusable domain logic as `@app.function` / `@app.class_definition` inside the Marimo `.py` file (or extract shared code into `src/`). External `pytest` test modules can import `@app.function` symbols directly, and embedded `def test_*():` cells execute natively under `uv run pytest notebooks/analysis.py`.
- **Pre-Commit (`prek`) & CI Enforcement**: Run `uv run marimo check notebooks/` (and `--strict` during authoring) inside `prek` hooks and GitHub Actions CI alongside `ruff check`, `ruff format --check`, `basedpyright`, and `ty check` to catch DAG cycles (`MB003`), duplicate definitions (`MB002`), and unparsable cells (`MB001`).

### Legacy `.ipynb` Migration & Skill Handoff

- **Legacy Boundary**: Restrict `/jupyter-pro` strictly to maintaining preexisting `.ipynb` artifacts or mandatory hosted Google Colab notebooks.
- **Migration Command**: Convert legacy notebooks to reactive Marimo Python files cleanly with:

  ```bash
  uvx marimo convert legacy.ipynb -o notebook.py
  uv run marimo check --strict notebook.py
  ```

- **Skill Routing**:
  - Hand off converted `.py` files on disk to **`/marimo-pro`** for reactive DAG refactoring (`mo.ui`, `mo.state`, `mo.stop`, `marimo check --strict`).
  - Whenever a live `marimo edit` kernel is actively running on a notebook, switch to **`/marimo-pair`** (`marimo._code_mode`) instead of editing disk files directly so live kernel state is never overwritten.

## 5. November 2026 Library Recommendations

> **Mandatory Evergreen Check**: Always verify the current PyPI / `conda-forge` release health and community consensus before locking dependencies, adopting the **latest recommended, actively maintained** scientific, engineering, statistics, and mathematics libraries rather than assuming static major versions forever.

- **Dataframes, SQL & Object Storage**: `polars` (2.x), `duckdb` (2.x), `pyarrow`, `narwhals` (DataFrame-agnostic APIs), `obstore` (Rust-backed S3/GCS/Azure object I/O).
- **Arrays, Science & Physical Units**: `numpy` (2.5+), `scipy`, `xarray`, `zarr` (3.x sharded stores), `pint`.
- **Differentiable Simulation & Optimization**: `jax` + `equinox` + `diffrax` (ODE/SDE/CDE) + `lineax` + `optimistix` + `jaxtyping`; `casadi` and `cvxpy` for optimal control / MPC / convex optimization.
- **Bayesian Inference & Probabilistic Programming**: `pymc` (6.x) + `nutpie` (high-speed Rust NUTS sampler) + modular **ArviZ 1.0+** (`arviz-base`, `arviz-stats`, `arviz-plots` with `DataTree` storage).
- **Visualization & Robotics Telemetry**: `plotly`, `altair`, and `rerun-sdk` (real-time 3D robotics/sensor logging).
- **Services, CLI & Observability**: `fastapi` + `pydantic` v2 / `msgspec` + `httpx`, `cyclopts` (or `typer`), `structlog` + `opentelemetry-sdk`.
