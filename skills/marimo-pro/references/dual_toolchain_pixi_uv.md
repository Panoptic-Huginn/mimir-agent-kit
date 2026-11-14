# Dual Toolchain Operations: `pixi`, `uv`, and Pure `uv` CI Gates

This reference establishes the operational boundaries and command mappings between **`pixi`** (hybrid C++/Rust/CUDA/Python environments) and **`uv`** (pure-Python PEP 723 standalone notebooks and Antigravity CI gates) for **Marimo 0.25.2+** on **Python 3.14.8+ / 3.15** and **Google Antigravity 2.31.2+**.

---

## 1. Toolchain Boundary Decision Matrix

| Project Profile | Primary Env Manager | Lockfile & Manifest | Rationale |
| :--- | :--- | :--- | :--- |
| **Pure-Python / Polars / Plotly / SciPy / Single `.py` Notebook** | **`uv`** | PEP 723 (`# /// script`) or `pyproject.toml` + `uv.lock` | Zero-overhead, standalone reproducible execution via `uv run` and `marimo run --sandbox`. |
| **Compiled Extensions (ROS2, CUDA, OpenCV, C++23, Rust/PyO3, GDAL)** | **`pixi`** | `pixi.toml` + `pixi.lock` | Reproducible `conda-forge` ABI-matched C/C++/CUDA toolchains alongside PyPI wheels via `[pypi-dependencies]`. |
| **Repository CI Gates (`pre-commit`, `pytest`, `rumdl`, `marimo check`)** | **`uv` exclusively** | Root `pyproject.toml` + `uv.lock` | Deterministic root-environment CI without polluting global or subproject virtual environments. |

> [!CRITICAL]
> **Pure `uv` Execution Mandate for Repository CI:** Never execute `pre-commit` or `pytest` through a Pixi wrapper. Always run `uv run pre-commit run --all-files` and `uv run pytest` directly under the repository root `uv` environment. Likewise, never create `.venv` inside `skills/marimo-pro/examples/` — set `UV_PROJECT_ENVIRONMENT` to a directory outside the repository tree (for example `/tmp/mimir-marimo-examples-venv`) when running isolated example checks.

---

## 2. Dual-Toolchain Configurations

### A. Standalone Single-File PEP 723 Notebook (`uv` Sandbox)

Marimo automatically creates and caches an ephemeral isolated `uv` virtual environment when invoked with `--sandbox`:

```python
# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "marimo>=0.25.2",
#     "numpy>=2.2.0",
#     "polars>=1.22.0",
#     "plotly>=6.0.0",
# ]
# ///

import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium")
```

Run directly with zero manual `pip install` or environment activation:

```bash
uv run --with marimo marimo edit --sandbox analysis_notebook.py
uv run --with marimo marimo check --strict analysis_notebook.py
uv run analysis_notebook.py --help
```

### B. Hybrid Native Project (`pixi.toml`)

Use `pixi.toml` when combining conda-forge native binaries with Marimo notebooks:

```toml
[workspace]
name = "robotics-perception-workbench"
version = "0.1.0"
channels = ["conda-forge"]
platforms = ["linux-64", "osx-arm64"]

[dependencies]
python = ">=3.14,<3.16"
numpy = ">=2.2.0"
scipy = ">=1.15.0"
polars = ">=1.22.0"

[pypi-dependencies]
marimo = ">=0.25.2"
plotly = ">=6.0.0"

[tasks]
edit = "marimo edit notebooks/"
run = "marimo run notebooks/telemetry_dashboard.py"
check = "marimo check --strict notebooks/"
export-wasm = "marimo export html-wasm notebooks/telemetry_dashboard.py -o dist/telemetry --mode edit --show-code"
```

### C. Pure-Python Workspace (`pyproject.toml` + `uv`)

```toml
[project]
name = "astro-analytics-notebooks"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
    "marimo>=0.25.2",
    "numpy>=2.2.0",
    "scipy>=1.15.0",
    "polars>=1.22.0",
    "plotly>=6.0.0",
    "pytest>=8.3.0",
]

[tool.uv]
package = false
```

---

## 3. Complete Marimo 0.25.2+ CLI Command Matrix

| Operation | `uv` Command | `pixi` Command | Purpose |
| :--- | :--- | :--- | :--- |
| **Interactive Editor** | `uv run marimo edit notebook.py` | `pixi run marimo edit notebook.py` | Launch local IDE browser editor |
| **Sandbox PEP 723 Edit** | `uv run --with marimo marimo edit --sandbox nb.py` | `N/A` (`uv` manages PEP 723) | Isolated auto-resolved dependencies |
| **Read-Only App Mode** | `uv run marimo run notebook.py --port 2718` | `pixi run marimo run notebook.py` | Serve notebook as locked web app |
| **Headless MCP Bridge** | `uv run marimo edit nb.py --headless --no-token --mcp code-mode --port 2718` | `pixi run marimo edit nb.py --headless --no-token --mcp code-mode --port 2718` | Antigravity live-kernel MCP + `code_mode` |
| **Convert Jupyter `.ipynb`** | `uv run marimo convert legacy.ipynb -o modern.py` | `pixi run marimo convert legacy.ipynb -o modern.py` | Migrate legacy Jupyter notebooks |
| **Strict DAG Linting** | `uv run marimo check --strict notebook.py` | `pixi run marimo check --strict notebook.py` | Static AST DAG & format validation |
| **Auto-Fix Formatting** | `uv run marimo check --fix notebook.py` | `pixi run marimo check --fix notebook.py` | Auto-repair `MF*` and safe lint rules |
| **Export Static HTML** | `uv run marimo export html nb.py -o report.html --no-include-code` | `pixi run marimo export html nb.py -o report.html --no-include-code` | Pre-rendered static HTML artifact |
| **Export Pyodide WASM** | `uv run marimo export html-wasm nb.py -o dist/nb --mode run --no-show-code` | `pixi run marimo export html-wasm nb.py -o dist/nb --mode run --no-show-code` | Client-side interactive WebAssembly app |
| **Export Single-File WASM** | `uv run marimo export html-wasm nb.py -o dist/app.html --mode run --no-show-code --single-file --execute` | `pixi run marimo export html-wasm nb.py -o dist/app.html --mode run --no-show-code --single-file --execute` | Single HTML file with CDN assets and pre-computed outputs |
| **Export Offline Directory WASM** | `uv run marimo export html-wasm nb.py -o dist/offline_app --mode run --offline --execute` | `pixi run marimo export html-wasm nb.py -o dist/offline_app --mode run --offline --execute` | Air-gapped directory bundle with Pyodide runtime & wheels |
| **Embedded Unit Tests** | `uv run pytest notebook.py -v` | `uv run pytest notebook.py -v` | Execute `@app.cell def test_*()` natively |
| **Script / CLI Execution** | `uv run python notebook.py --arg val` | `pixi run python notebook.py --arg val` | Dual-mode execution via `if __name__ == "__main__":` |

---

## 4. Export Workflows & WASM Flags (`marimo export html-wasm`)

In Marimo `0.25.2+`, `marimo export html-wasm` supports CDN directory builds, standalone `--single-file` HTML builds, and `--offline` directory bundles:

- `--mode {edit,run}`: Choose read-only app presentation (`run`) or full client-side editor (`edit`).
- `--show-code` / `--no-show-code`: Show or hide source Python cells by default in `run` mode (`marimo export html` uses `--include-code` / `--no-include-code`).
- `--single-file`: Bundle HTML, CSS, and notebook payload into one `.html` file (`-o dist/app.html`) loading Pyodide assets from CDN so it can be opened directly.
- `--offline`: Download the Pyodide 314.0.0 runtime and notebook wheels into the export output directory for air-gapped HTTP serving.
- `--execute` / `--no-execute`: Run the notebook prior to exporting and embed preview outputs while WebAssembly boots.
- `--watch` / `--no-watch`: Rebuild automatically on file change during local authoring.

```bash
# Single-file HTML with preview outputs (CDN runtime)
uv run marimo export html-wasm examples/astro_transit_photometry.py \
    -o /tmp/astro_dashboard.html \
    --mode run \
    --no-show-code \
    --single-file \
    --execute

# Air-gapped directory bundle with local Pyodide runtime and wheels
uv run marimo export html-wasm examples/astro_transit_photometry.py \
    -o /tmp/astro_offline_dir \
    --mode run \
    --offline \
    --execute
```

---

## 5. Comprehensive `marimo check` Diagnostics Matrix

Always run `marimo check --strict` and inspect **breaking (`MB*`)**, **runtime (`MR*`)**, **formatting (`MF*`)**, and **warning (`MW*`)** diagnostics:

| Rule Prefix | Severity | Key Codes & Meaning | Mandatory Fix |
| :--- | :--- | :--- | :--- |
| **`MB*`** | Breaking | `MB001` multiple definitions; `MB002` cyclic dependency; `MB003` setup cell defines app; `MB004` invalid AST statement; `MB005` duplicate/non-top-level cell | Isolate each global in one cell, keep `setup` clean, place every `@app.cell` at module top level. |
| **`MR*`** | Runtime | `MR001` self-referencing cell; `MR002` UI element `.value` accessed in same cell; `MR003` invalid setup placement; `MR004` `return` misuse / runtime DAG trap | Move `.value` access to a downstream cell; never bypass execution order with imperative `return` tricks. |
| **`MF*`** | Formatting | `MF001`–`MF007` header spacing, unformatted cells, parse/unparse structure, unexpected top-level statements | Run `marimo check --fix`, put shared imports in `with app.setup:`, ensure `if __name__ == "__main__": app.run()`. |
| **`MW*`** | Warning | `MW001` general DAG smell; `MW002` empty cell; `MW003` SQL/branching/layout hygiene | Clean empty cells, keep reactive SQL explicit, inspect warnings under `--strict`. |

---

## 6. Executing Embedded `pytest` Suites Inside Notebooks

Marimo allows **top-level** `@app.cell` test functions (`def test_*(...):`) and `@app.function` pure helpers to be discovered directly by `pytest`:

```python
@app.function
def compute_residual_rms(observed: "np.ndarray", model: "np.ndarray") -> float:
    """Compute root-mean-square residual between data and model."""
    import numpy as np

    return float(np.sqrt(np.mean((observed - model) ** 2)))


@app.cell
def test_residual_rms_zero_on_identical_arrays(np) -> None:
    """Verify RMS residual vanishes when model matches observation."""
    signal = np.linspace(0.0, 1.0, 64)
    assert compute_residual_rms(signal, signal) == 0.0
    return
```

Run tests with standard `uv` CLI hygiene:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/mimir-marimo-examples-venv \
    uv run --project skills/marimo-pro/examples pytest \
    skills/marimo-pro/examples/bayesian_mcmc_diagnostic.py -v
```
