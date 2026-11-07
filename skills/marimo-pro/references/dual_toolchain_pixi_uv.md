# Marimo Dual Toolchain: Pixi & uv Environment Management Reference Manual

This manual provides an authoritative guide for managing **Marimo** notebook environments across **Python 3.14.8+** and **Python 3.15** using both **Pixi** (`pixi.toml`) and **uv** (`pyproject.toml`). It details dual dependency sourcing (conda-forge + PyPI), CLI operations, headless static linting, and automated Pytest discovery.

---

## 1. Dual Toolchain Architecture

Modern scientific computing requires balancing native binary performance (C/C++, BLAS, LAPACK, CUDA) with rapid deployment of bleeding-edge Python wheels:

| Feature | Pixi (`pixi.toml`) | uv (`pyproject.toml`) |
| :--- | :--- | :--- |
| **Primary Domain** | Complex scientific stacks, multi-language bindings, robotics | Pure-Python libraries, rapid CI/CD, microservices |
| **Resolution Engine** | Conda-forge binaries + PyPI wheels (`[pypi-dependencies]`) | Pure PyPI resolver and universal wheel cache |
| **Target Versions** | Python 3.14.8+, Python 3.15 | Python 3.14.8+, Python 3.15 |
| **Lockfile Standard** | Multi-platform `pixi.lock` | Fast universal `uv.lock` |
| **Sandbox Execution**| `marimo edit --sandbox pixi` | `marimo edit --sandbox uv` |

> **Repository Toolchain Policy**: The core repository enforces `uv` and standard Python packaging for CI gates and pre-commit checks. Pixi is documented and supported for advanced data science projects and modular workspaces.

---

## 2. Pixi Workflow (`pixi.toml`)

Pixi orchestrates Conda binaries and PyPI wheels in a single, reproducible workspace.

### 2.1 Workspace Configuration Manifest
```toml
[workspace]
name = "mimir-marimo-science"
version = "0.1.0"
channels = ["conda-forge"]
platforms = ["linux-64", "osx-arm64", "win-64"]

[dependencies]
python = ">=3.14.8"
numpy = ">=2.0.0"
scipy = ">=1.15.0"
polars = ">=1.20.0"

[pypi-dependencies]
marimo = ">=0.25.2"
plotly = ">=5.24.0"
altair = ">=5.4.0"

[feature.py315.dependencies]
python = ">=3.15.0rc1"

[environments]
default = ["py314"]
py315 = ["py315"]

[tasks]
edit = "marimo edit examples/astro_transit_photometry.py"
run = "marimo run examples/astro_transit_photometry.py"
check = "marimo check examples/"
export = "marimo export html examples/astro_transit_photometry.py -o dist/report.html"
test = "pytest tests/"
```

### 2.2 Operational CLI Commands
- `pixi run edit`: Starts the Marimo reactive development server.
- `pixi run run`: Serves the notebook as a read-only production dashboard.
- `pixi run check`: Executes static analysis linting across all notebooks.
- `pixi run -e py315 test`: Executes verification tests under Python 3.15.

---

## 3. uv Workflow (`pyproject.toml`)

`uv` provides extreme installation speed, PEP 621 adherence, and deterministic virtual environment locking.

### 3.1 PEP 621 Manifest
```toml
[project]
name = "mimir-marimo-analysis"
version = "0.1.0"
description = "High-performance reactive data analysis"
requires-python = ">=3.14.8"
dependencies = [
    "marimo>=0.25.2",
    "numpy>=2.0.0",
    "scipy>=1.15.0",
    "polars>=1.20.0",
    "plotly>=5.24.0",
]

[dependency-groups]
dev = [
    "pytest>=8.3.0",
    "ruff>=0.9.0",
    "nbformat>=5.10.0",
]
```

### 3.2 Operational CLI Commands
- `uv run marimo edit notebook.py`: Runs editor within the project environment.
- `uv run marimo run notebook.py`: Runs production read-only web server.
- `uv run marimo check notebook.py`: Validates DAG integrity and formatting.
- `uv run --python 3.15 marimo edit notebook.py`: Launches editor under Python 3.15.
- `uvx marimo edit notebook.py`: Runs Marimo in an isolated, ephemeral tool cache without modifying local environment.

---

## 4. PEP 723 Script Sandboxing (`--sandbox`)

Marimo natively supports PEP 723 inline script metadata declared at the head of `.py` notebook files:

```python
# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "marimo",
#     "numpy",
#     "polars",
#     "scipy",
# ]
# ///
import marimo
```

When opened with sandboxing:
- `marimo edit --sandbox uv notebook.py`: Automatically provisions an isolated temporary virtualenv via `uv run --isolated`.
- `marimo edit --sandbox pixi notebook.py`: Provisons a sandboxed environment via `pixi install --script`.

---

## 5. Marimo CLI Commands Reference

| Command | Primary Options | Description & Exit Semantics |
| :--- | :--- | :--- |
| `marimo edit [FILE]` | `--port`, `--host`, `--headless`, `--sandbox [uv\|pixi]`, `--watch`, `--token / --no-token`, `--timeout` | Launches interactive browser editor. Creates file if non-existent. |
| `marimo run FILE` | `--port`, `--host`, `--headless`, `--include-code`, `--sandbox`, `--check / --no-check` | Launches read-only production dashboard. Fails on startup if DAG has breaking errors. |
| `marimo check [FILES]`| `--fix`, `--strict`, `--unsafe-fixes`, `--format [full\|json]`, `--select`, `--ignore` | Static analysis linter. Exits 0 if clean. Exits 1 if breaking errors (`MB*`) or strict warnings exist. |
| `marimo export html` | `-o, --output`, `--include-code`, `--watch`, `--sandbox`, `-f, --force` | Headlessly evaluates notebook and exports standalone static HTML report. |
| `marimo export html-wasm` | `-o, --output`, `--include-code`, `--sandbox` | Exports zero-server WebAssembly / Pyodide interactive web application. |
| `marimo export ipynb`| `-o, --output`, `--sort [top-down\|topological]`, `--include-outputs` | Converts Marimo notebook to Jupyter `.ipynb`. **Requires `nbformat`**. |
| `marimo export script`| `-o, --output`, `--watch`, `-f, --force` | Flattens notebook into a linear Python script with `# %%` cell markers. |
| `marimo convert FILE` | `-o, --output` | Converts Jupyter `.ipynb` or percent-format script into a reactive Marimo notebook. |

---

## 6. Testing Reactive Notebooks

In production workflows featuring notebooks like `astro_transit_photometry.py`, `robotics_kalman_filter.py`, `systems_telemetry_analysis.py`, and `bayesian_mcmc_diagnostic.py`, testing is performed continuously via `marimo check` and `pytest`:

### 6.1 Static Verification Gate (`marimo check`)
`marimo check` verifies code cleanliness without launching a Python kernel:
- **Breaking Error Codes (`MB*`, Exit Code 1)**:
  - `MB001`: Unparsable cell syntax.
  - `MB002`: Multiple variable definitions (`MultipleDefinitionError`).
  - `MB003`: Dependency cycle in DAG (`CycleError`).
  - `MB004`: Setup block dependency leak (`SetupRootError`).
  - `MB005`: Invalid variable assignment target.
- **Formatting Codes (`MF*`)**:
  - `MF001`: Missing `__generated_with` version tag.
  - `MF004`: Empty cells (`marimo check --fix` automatically prunes).
  - `MF007`: Markdown indentation / unclosed fences.

```bash
# Automated check in CI gate
uv run marimo check --strict examples/
```

### 6.2 Native Pytest Integration
Marimo provides native discovery hooks implemented in `marimo._ast.pytest`:

#### Pattern 1: Top-Level Cell Test Functions
Any `@app.cell` whose name starts with `test_` is automatically collected by Pytest:
```python
@app.cell
def setup_filter():
    kalman_gain = 0.85
    return (kalman_gain,)


@app.cell
def test_kalman_gain_bounds(kalman_gain):
    assert 0.0 <= kalman_gain <= 1.0
```
- Parameters matching upstream cell definitions (e.g. `kalman_gain`) are resolved through the DAG.
- Parameters ending in `_fixture` (e.g. `tmp_path_fixture`) are injected directly from Pytest fixtures.

#### Pattern 2: Synthesized Test Classes (`MarimoTestBlock`)
Cells can embed inner test functions or `Test*` classes. Marimo compiles dynamic `MarimoTestBlock_<idx>(MarimoTest)` test suites:
```python
@app.cell
def _(data_vector, pytest):
    @pytest.mark.parametrize('scale,expected', [(1.0, 10.0), (2.0, 20.0)])
    def test_scaling(scale, expected):
        assert data_vector[0] * scale == expected

    class TestConvergence:
        def test_stationarity(self):
            assert len(data_vector) > 50
```

### 6.3 Programmatic App Testing (`app.run`)
External Pytest files can import and exercise notebooks headlessly:
```python
from examples.bayesian_mcmc_diagnostic import app


def test_mcmc_convergence():
    outputs, defs = app.run()
    assert defs['gelman_rubin_r_hat'] < 1.05
    assert defs['chains_converged'] is True
```

---

## 7. Sibling References & Skill Links

- [Marimo Architecture & Reactive DAG](./marimo_architecture_and_dag.md)
- [Interactive Widgets & UI Components](./interactive_widgets_and_ui.md)
- [Advanced Scientific & Engineering Data Analysis Scenarios](./advanced_data_analysis_scenarios.md)
- [Marimo Pro Root Skill Manual](../SKILL.md)
