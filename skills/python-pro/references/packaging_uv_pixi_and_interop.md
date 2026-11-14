# Packaging (`uv` & `pixi`), Polyglot FFI & November 2026 Ecosystem

This reference covers package management selection (`uv` vs. `pixi`), `src/` project structure, PEP 723/735/751 standards, polyglot FFI integration with sibling skills, and the November 2026 library landscape.

## 1. Decision Matrix: `uv` (Default) vs. `pixi`

Always default to **`uv`**. Adopt **`pixi`** (`>= 0.84.2`) **only** when one or more of the following 6 conditions apply:

1. **Multi-Language Workspace**: The repository co-develops Python with C, C++, Rust, SPARK Ada, or CUDA in one build graph.
2. **Native System Libraries or Compilers**: The project needs non-PyPI binary toolchains or libraries (LLVM/Clang, CMake, Ninja, `lld`, CUDA/cuDNN, HDF5, GDAL, OpenBLAS, `gnat_native`).
3. **`conda-forge`-Only Python Packages**: At least one required Python dependency is distributed solely on `conda-forge` and absent from PyPI.
4. **Pixi Built-In Task Runner**: The project explicitly adopts `[tasks]` / `[tool.pixi.tasks]` workflows across contributors.
5. **Co-Managed Non-Python Global CLIs**: Non-Python developer tools (`clang-format`, `clang-tidy`, `gersemi`, `cmake`, `ninja`, `actionlint`) must resolve uniformly in the project environment.
6. **Multi-Platform Conda + PyPI Binary Lockfiles (`pixi.lock`)**: Reproducible locking across native Conda binary packages *and* PyPI wheels is required across `linux-64`, `linux-aarch64`, and `osx-arm64`.
   - For pure Python and PyPI binary wheels, **`uv.lock`** and **PEP 751 `pylock.toml`** already deliver universal cross-platform locking with zero Conda overhead.

### `[tool.pixi.*]` in `pyproject.toml` vs. Standalone `pixi.toml`

- **`[tool.pixi.*]` inside `pyproject.toml`**: Ideal for Python-centric packages (e.g., an astrophysics or scientific analysis package using `conda-forge` binaries alongside PyPI tools). Single manifest, standard PEP 621 `[project]` metadata.
- **Standalone `pixi.toml`**: Ideal for polyglot workspaces (C++23/Rust/SPARK + Python) where CMakePresets or Cargo workspaces sit alongside Python bindings cleanly separated from Python package metadata (see `../examples/pixi.toml`).

## 2. Standard Project Layout & PEPs

### Repository & `src/` Structure

```text
my-python-project/
├── .github/workflows/ci.yml
├── .pre-commit-config.yaml
├── pyproject.toml
├── uv.lock                    # or pixi.lock
├── src/
│   └── my_package/
│       ├── __init__.py
│       └── py.typed           # PEP 561 marker (mandatory for importable packages)
└── tests/
    ├── unit/
    ├── integration/
    └── regression/
```

### Build Backends

- **Pure Python Libraries & CLIs**: `uv_build` (`requires = ["uv_build>=0.12,<0.13"]`, `build-backend = "uv_build"`). Fast, deterministic, zero-config `src/<pkg>/` layout support.
- **C++23 Native Extensions**: `scikit-build-core` + `nanobind` (`>=3.1`) exporting C++23 kernels as zero-copy `nb::ndarray` buffers; pair with `/cpp-pro` and `/cmake-pro`.
- **Rust Native Extensions**: `maturin` + `PyO3` (`>=0.27`); pair with `/rust-pro`.

### Dependency Groups (PEP 735) & Lockfiles (PEP 751)

- Place `dev`, `test`, `lint`, and `typecheck` dependencies strictly under `[dependency-groups]` in `pyproject.toml` so downstream wheel consumers never inherit dev tooling as extras.
- Reserve `[project.optional-dependencies]` strictly for runtime optional feature extras shipped to library users (e.g., `plotting`, `cuda`).
- Update dependencies with CLI tooling rather than manual version guessing:
  - `uv`: `uv add polars`, `uv add --group dev hypothesis`, `uv lock --check`, `uv sync --locked`
  - `pixi`: `pixi add numpy`, `pixi add --pypi pytest-cov`, `pixi install --frozen`
- Export universal PEP 751 lockfiles when external deployment/container builders consume standard lockfiles: `uv export --format pylock.toml -o pylock.toml`.

### Inline Script Metadata (PEP 723)

All single-file automation scripts, reproducible experiments, and standalone diagnostics MUST embed a PEP 723 `# /// script` header (`../examples/pep723_script.py`) and execute via `uv run --script my_script.py`.

## 3. Polyglot FFI Alignment with Sibling Skills

| Interop Path | Recommended Tooling | Aligned Sibling Skill | Key Rules |
| :--- | :--- | :--- | :--- |
| **C++23 Compute Kernels** | `nanobind` + `scikit-build-core` under `pixi` | `/cpp-pro`, `/cmake-pro` | Use `nb::ndarray` zero-copy buffer exchange, release GIL across compute, declare `nb::mod_gil_not_used()` when safe |
| **Rust Safety / Compute Extensions** | `PyO3` + `maturin` | `/rust-pro` | Enforce `#[pymodule(gil_used = false)]` where safe, use `rust-numpy` for zero-copy array views |
| **ISO C23 Kernels & HIL** | `cffi` (ABI/API mode) or `ctypes` | `/c-pro` | Validate C23 `extern "C"` header structs explicitly (`cffi.FFI().cdef(...)`), free-check bounds at FFI edge |
| **SPARK Ada Static Libraries** | `ctypes` / `cffi` via exported `extern "C"` symbols | `/ada-spark-pro` | Drive formally verified Ada/C-ABI robotics interceptors from Python HIL (`pytest` + `hypothesis`) harnesses |

## 4. Reactive Notebooks (`marimo`) vs. Legacy Jupyter

- **New Interactive Work**: Author pure-Python reactive **Marimo** `.py` notebooks (`.py` DAG execution, Git-clean diffs, importable under `pytest`) using `/marimo-pro` and `/marimo-pair`.
- **Execution**: Run standalone notebooks with `marimo edit --sandbox notebook.py` (PEP 723 + `uv`), or workspace notebooks with `uv run marimo edit notebook.py` / `pixi run marimo edit notebook.py`.
- **Verification**: Run `uv run marimo check` in both `prek` hooks and GitHub Actions CI.
- **Legacy Only**: Restrict `/jupyter-pro` to existing `.ipynb` files or mandatory Google Colab hosts, and migrate notebooks cleanly via `uvx marimo convert legacy.ipynb -o notebook.py`.

## 5. November 2026 Library Recommendations

> **Mandatory Evergreen Check**: Always verify the current PyPI / `conda-forge` release health and community consensus before locking dependencies, adopting the **latest recommended, actively maintained** scientific, engineering, statistics, and mathematics libraries rather than assuming static major versions forever.

- **Dataframes, SQL & Object Storage**: `polars` (2.x), `duckdb` (2.x), `pyarrow`, `narwhals` (DataFrame-agnostic APIs), `obstore` (Rust-backed S3/GCS/Azure object I/O).
- **Arrays, Science & Physical Units**: `numpy` (2.5+), `scipy`, `xarray`, `zarr` (3.x sharded stores), `pint`.
- **Differentiable Simulation & Optimization**: `jax` + `equinox` + `diffrax` (ODE/SDE/CDE) + `lineax` + `optimistix` + `jaxtyping`; `casadi` and `cvxpy` for optimal control / MPC / convex optimization.
- **Bayesian Inference & Probabilistic Programming**: `pymc` (6.x) + `nutpie` (high-speed Rust NUTS sampler) + modular **ArviZ 1.0+** (`arviz-base`, `arviz-stats`, `arviz-plots` with `DataTree` storage).
- **Visualization & Robotics Telemetry**: `plotly`, `altair`, and `rerun-sdk` (real-time 3D robotics/sensor logging).
- **Services, CLI & Observability**: `fastapi` + `pydantic` v2 / `msgspec` + `httpx`, `cyclopts` (or `typer`), `structlog` + `opentelemetry-sdk`.
