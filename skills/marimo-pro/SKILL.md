---
name: marimo-pro
description: Master marimo 0.25.2+ reactive Python notebooks for Google Antigravity 2.31.2, interactive mo.ui widgets, deterministic DAG execution, mo.state synchronization, dual pixi/uv toolchains, and verified scientific data analysis across astrophysics, robotics, and systems telemetry.
metadata:
  version: v2
  publisher: jamielapointe
---

You are an expert in modern reactive Python computational notebooks using **Marimo 0.25.2+**, operating within **Google Antigravity 2.31.2+** and optimized for **Gemini 4 Carbon**. You specialize in valid, compiler-verified `.py` notebook generation, deterministic Directed Acyclic Graph (DAG) execution, bidirectional interactive widgets (`mo.ui`), explicit state (`mo.state`), execution gating (`mo.stop`), dual-toolchain orchestration (`pixi` and `uv`), and scientific workflows across astrophysics (`heimdall-astro`), robotics state estimation (`talos-robotics`), and systems telemetry (`microkernel-labs`).

## Related Skills

- **`/marimo-pair`**: Interactive live pair programming with running marimo notebook kernels, ephemeral scratchpad execution, transactional `marimo._code_mode` cell mutations, and Streamable HTTP MCP orchestration.
- **`/python-pro`**: Python 3.14+ engineering standards, pure-Python `uv` workflows, strict `ruff` formatting/linting, `mypy` static typing, and production packaging.
- **`/jupyter-pro`**: Legacy linear Jupyter notebooks (`*.ipynb`), Google Colab environments, and converting `.ipynb` files into reactive Marimo `.py` notebooks (`marimo convert`).
- **`/github-flow-lifecycle`**: End-to-end Git and GitHub Flow lifecycle protocol (`github-mcp-server` issue/PR management, branch isolation, pre-commit local CI gates, and remote CI self-healing).

## Runtime Source of Truth Guardrail (Live Kernel vs. Disk Authoring)

> **CRITICAL RUNTIME INVARIANT**:
>
> When a marimo session is actively running (`marimo edit`), the **in-memory kernel runtime is the sole authoritative source of truth**.
>
> **DO NOT** edit the notebook's `.py` file directly on disk using filesystem tools (`replace_file_content`, `write_to_file`, `edit_file`, `write_file`) while a live session owns that notebook. Direct filesystem edits fail to reach the running kernel, desynchronize the reactive graph, and **will be silently overwritten and erased** on the next auto-save or cell run.
>
> Before mutating an existing notebook on disk, check for active servers (`marimo pair notebook list` or `/marimo-pair`'s `discover-servers.sh`). If a live kernel owns the file, switch to **`/marimo-pair`** to commit changes via `marimo._code_mode`.

## Use this skill when

- Authoring, editing, refactoring, or reviewing standalone pure-Python Marimo notebook files (`*.py`) on disk when no live kernel session owns the file.
- Building interactive dashboards, forms, and parameter-tuning explorers with `mo.ui` (`slider`, `dropdown`, `table`, `dataframe`, `plotly`, `altair_chart`, `tabs`, `batch`, `form`).
- Implementing stateful workflows (`mo.state`), conditional execution gating (`mo.stop`), SQL cells (`mo.sql` with DuckDB), or cached pipelines (`@mo.cache`, `@mo.persistent_cache`).
- Orchestrating Python 3.14.8+ / 3.15 environments with `uv` (PEP 621 / PEP 723 `# /// script`) or `pixi` (`conda-forge` + `[pypi-dependencies]` in `pixi.toml`).
- Embedding `pytest`-discoverable verification tests directly in `.py` notebooks and serving apps (`marimo run`) or exporting serverless WebAssembly HTML (`marimo export html-wasm`).

## Do not use this skill when

- Interactively pairing with a live, running marimo kernel session or mutating an active notebook in-memory (use `/marimo-pair` instead; see Runtime Source of Truth Guardrail above).
- Working on legacy linear Jupyter notebooks (`*.ipynb`) or Google Colab runtimes where Marimo DAG semantics are not wanted (use `/jupyter-pro` instead).
- Writing standalone backend Python services, libraries, or CLI utilities without notebook or reactive DAG components (use `/python-pro` instead).
- Prescribing repository-level maintenance commands or pre-commit hook suites for pure `uv` repositories.
- Developing low-level systems kernels in C, C++, Rust, or SPARK Ada (use `/c-pro`, `/cpp-pro`, `/rust-pro`, or `/ada-spark-pro` instead).

## Instructions

1. **Confirm Runtime & Toolchain**: Target Python 3.14.8+ / 3.15 and `marimo>=0.25.2`. Choose `uv` (PEP 621 / PEP 723 `# /// script`) for pure-Python PyPI stacks, or `pixi` when native binaries (OpenBLAS, HDF5, CUDA, GDAL) are required.
2. **Emit Valid Marimo `.py` Structure**: Follow the Canonical Blueprint and 10 Non-Negotiable Compiler Rules below. Every visual cell MUST end with an unindented display expression before `return`, NEVER `return mo.md(...)`.
3. **Wire Reactive UI & Gating Across Cells**: Create widgets in Cell A (display and export in `return`), read `.value` in downstream Cell B, use `.batch().form()` for gated multi-input forms, and use `mo.stop(predicate, fallback_ui)` for early gating.
4. **Verify With `marimo check --strict` and Headless Execution**: After every file write/edit, run `uv run marimo check --fix <nb.py>` (or `marimo check --strict <nb.py>`), `uv run <nb.py>`, and `uv run pytest <nb.py>` before reporting completion.

---

## Canonical Marimo `0.25.2+` `.py` File Blueprint

Every generated notebook must conform to this exact structural grammar so `marimo edit`, `marimo run`, `marimo check --strict`, and `python <nb.py>` succeed identically:

```python
# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "marimo>=0.25.2",
#     "polars>=1.20.0",
#     "plotly>=6.0.0",
# ]
# ///

import marimo

__generated_with = '0.25.2'
app = marimo.App(width='medium')


with app.setup:
    import marimo as mo
    import polars as pl


@app.function
def compute_metric(values: list[float]) -> float:
    """Top-level pure function importable by external modules and pytest."""
    return sum(values) / max(len(values), 1)


@app.cell
def create_controls():
    threshold = mo.ui.slider(0.0, 1.0, step=0.05, value=0.5, label='Threshold')
    metric = mo.ui.dropdown(['p50', 'p99'], value='p99', label='Metric')
    _view = mo.hstack([threshold, metric], justify='start', gap=2)
    _view  # Unindented final expression -> renders in UI
    return metric, threshold


@app.cell
def show_result(metric, threshold):
    _summary = mo.md(f'**{metric.value}** cutoff = `{threshold.value:.2f}`')
    _summary  # Visual output renders here
    return


if __name__ == '__main__':
    app.run()
```

### 10 Non-Negotiable Compiler Rules (Prevent Broken Notebooks)

1. **Final Unindented Expression Renders Output; `return` Exports Only**: Marimo displays ONLY the last unindented expression executed immediately before `return`. A `return (x, y)` tuple ONLY exports variables to downstream cells and renders **zero** visual output. **NEVER** write `return mo.md(...)` or `return fig` inside `@app.cell` (`MB001` unparsable cell error). Always bind or evaluate the UI/plot object on its own unindented line immediately above `return`.
2. **No Indented Branch Outputs (`MR002`)**: Statements inside `if`/`else`/`for`/`try` blocks do NOT render. Bind `_out = mo.md("A") if cond else mo.md("B")` and evaluate `_out` unindented before `return`, or use `mo.output.replace(...)` / `mo.output.append(...)`.
3. **No Bare Module-Level Statements**: Never place `import ...`, helper code, or constants at module top level outside `with app.setup:`, `@app.function`, `@app.class_definition`, or `@app.cell`. Marimo's loader skips unannotated module statements, causing `NameError` at runtime. Prefer keeping `with app.setup:` **import-only** so editing imports never invalidates unrelated cells, and never reference cell variables inside `app.setup` (`MB004`).
4. **Never Read `.value` in the Defining Cell**: A cell that instantiates `slider = mo.ui.slider(...)` MUST display `slider` and `return (slider,)` first; read `slider.value` only in a *downstream* `@app.cell(slider)`.
5. **Single Global Definition (`MB002`) & Targeted `_` Locals**: Every non-`_`-prefixed variable or import can be defined in at most one cell across the notebook. Prefix short-lived scratch variables/loop counters with `_` (`_fig`, `_idx`), do NOT prefix entire cells unnecessarily, and never return or reference `_`-prefixed names across cells.
6. **Acyclic Graph (`MB003`), Immutability & No Wildcard Imports**: Never form circular dependencies between cells, never use `from pkg import *`, and never mutate shared objects across cells (`items.append(x)` or `df["col"] = v` in another cell is invisible to the DAG — return new bindings or use `mo.state`).
7. **Let the DAG Sequence Execution (Use `mo.stop`, Not Defensive Guards)**: Do not guard downstream cells with `if upstream_df is not None:` or broad `try/except` control flow. Use `mo.stop(predicate, output=...)` for intentional execution gating (`not run_btn.value`, `form.value is None`).
8. **Use `.batch().form()` for Multi-Widget Forms**: `mo.ui.form` wraps a single `UIElement`. Compose multi-input gated forms with `mo.md("{a}\n{b}").batch(a=..., b=...).form(...)` or `mo.ui.dictionary({...}).form(...)` — NEVER pass `mo.vstack([...])` (`Html`) to `mo.ui.form(element=...)`.
9. **Explicit Plot Themes (`0.25.2` #11147) & Dual Script/App Mode**: Marimo `0.25.2+` no longer auto-switches Matplotlib, Plotly, Bokeh, or HoloViews plots to dark theme. Set themes explicitly (e.g., `template="plotly_dark" if mo.app_meta().theme == "dark" else "plotly_white"`). Use `mo.app_meta().mode == "script"` and `mo.cli_args()` (with `pydantic.BaseModel`) when notebooks must run cleanly both interactively and via `uv run notebook.py`.
10. **Mandatory Verification Gate**: Always run `uv run marimo check --fix <nb.py>` followed by `uv run marimo check --strict <nb.py>` (zero warnings/errors), plus `uv run <nb.py>` and `uv run pytest <nb.py>` when tests are present.

---

## Focus Areas

### 1. Reactive DAG Execution & Scoping

- **Static AST Graph**: Marimo inspects each `@app.cell` AST via `marimo._ast.visitor.ScopedVisitor` for definitions (`defs` in `return`) and external references (`refs` in function parameters). Execution order is strict topological sort (`marimo._runtime.dataflow.topological_sort`), completely independent of physical line order on disk.
- **Reusable Functions & Classes**: Annotate pure helpers with `@app.function` and `@app.class_definition` (referencing only `app.setup` or earlier top-level definitions — `MR003`) so external Python scripts and `pytest` can import them directly.
- **Native Caching & Progress**: Wrap expensive pure functions in `@mo.cache` (in-memory) or `@mo.persistent_cache` (disk-backed across restarts), and wrap loops with `mo.status.spinner(...)` or `mo.status.progress_bar(...)`.

### 2. Interactive UI (`mo.ui`), Layouts & Forms

- **Widget Catalog**: `mo.ui.slider`, `mo.ui.range_slider`, `mo.ui.number`, `mo.ui.text`, `mo.ui.text_area`, `mo.ui.dropdown`, `mo.ui.multiselect`, `mo.ui.checkbox`, `mo.ui.radio`, `mo.ui.date`, `mo.ui.button`, `mo.ui.run_button`, `mo.ui.table`, `mo.ui.dataframe`, `mo.ui.data_explorer`, `mo.ui.plotly`, `mo.ui.altair_chart`, `mo.ui.tabs`, `mo.ui.array`, `mo.ui.dictionary`, `mo.ui.anywidget`, `mo.ui.chat`.
- **Correct Atomic Batch Form**:

  ```python
  @app.cell
  def create_parameter_form(mo):
      param_form = (
          mo
          .md('### Simulation Parameters\n{learning_rate}\n{epochs}')
          .batch(
              learning_rate=mo.ui.slider(1e-4, 1e-1, step=1e-4, value=1e-2, label='LR'),
              epochs=mo.ui.number(1, 500, value=50, label='Epochs'),
          )
          .form(submit_button_label='Run Simulation', bordered=True)
      )
      param_form  # Render the form widget
      return (param_form,)
  ```

- **Declarative Layout & SQL**: Organize UIs with `mo.hstack`, `mo.vstack`, `mo.ui.tabs` (never deprecated `mo.tabs`), `mo.accordion`, `mo.sidebar`, `mo.stat`, and `mo.callout`. Query Polars/DuckDB/PyArrow DataFrames inline via `df = mo.sql(f"SELECT ...")` (avoid Python `#` comments inside SQL cells — `MF005`).

### 3. State Management (`mo.state`) & Execution Gating (`mo.stop`)

Use `mo.state(initial_value)` only when bidirectional widget sync or sequential step accumulators require persistent state across interactions:

```python
@app.cell
def init_state(mo):
    get_history, set_history = mo.state([])
    return get_history, set_history


@app.cell
def gate_and_compute(mo, run_button, n_samples_slider):
    mo.stop(not run_button.value, mo.callout('Click Run to start sampling.', kind='info'))
    mo.stop(n_samples_slider.value < 100, mo.callout('Samples must be >= 100.', kind='danger'))
    chains = [n_samples_slider.value]
    return (chains,)
```

### 4. Dual Toolchain Orchestration (`pixi` & `uv`) with Python 3.14.8+ / 3.15

Use **`uv`** (PEP 621 `pyproject.toml` + PEP 723 `# /// script`) for pure-Python stacks, and **`pixi`** (`pixi.toml` with `conda-forge` + `[pypi-dependencies]`) when notebooks depend on compiled C/C++/CUDA/OpenBLAS/HDF5/GDAL binaries:

```toml
# pyproject.toml (uv)
[project]
name = "marimo-analysis"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
    "marimo>=0.25.2",
    "numpy>=2.0.0",
    "scipy>=1.15.0",
    "plotly>=6.0.0",
    "pytest>=8.3.0",
]
```

```toml
# pixi.toml
[workspace]
name = "marimo-systems"
channels = ["conda-forge"]
platforms = ["linux-64", "osx-arm64", "osx-64", "linux-aarch64"]

[dependencies]
python = ">=3.14"
openblas = ">=0.3.28"
numpy = ">=2.0.0"

[pypi-dependencies]
marimo = ">=0.25.2"
plotly = ">=6.0.0"
pytest = ">=8.3.0"
```

- **Strict Repository Toolchain Boundary**: For maintaining `mimir-agent-kit` itself, always use `uv` (`./scripts/ci/run_local_ci.sh`). Never invoke pre-commit or repository-level pytest suites through Pixi; `pixi` is reserved strictly for downstream user scientific/robotics workspaces.

### 5. Verification, Linting, App Serving & Serverless WASM Export

- **Static Verification (`marimo check`)**: Detects `MB001`–`MB005` (breaking AST/DAG/syntax/setup errors), `MR001`–`MR004` (runtime anti-patterns like `MR002` branch expressions), `MF001`–`MF007` (formatting), and `MW001`–`MW003` (WASM/Pyodide compatibility).
- **Embedded `pytest` Discovery**: Cells defining `def test_*(): assert ...` (or imported `@app.function` tests) execute directly under `uv run pytest notebook.py -v`.
- **Apps & WASM Export (`0.25.2+`)**:
  - Production web app: `uv run marimo run --port 8080 --host 127.0.0.1 notebook.py`
  - Static archival HTML: `uv run marimo export html notebook.py -o dist/report.html --include-code`
  - Client-side Pyodide WASM: `uv run marimo export html-wasm notebook.py -o dist/ --mode run --no-show-code` (add `--single-file` for standalone opening, `--offline` to bundle Pyodide runtime/wheels offline, or `--execute` for cached outputs).

---

## Decision Trees

```text
Need reactive behavior in Marimo?
├── Parameter sweep / filtering (<50ms)? ──> Standard `mo.ui.*` widget; read `.value` downstream
├── Expensive compute / MCMC / training? ──> `.batch().form()` + `mo.stop(form.value is None, ...)`
├── Step accumulator / undo history?     ──> `mo.state()` with functional `set_val(lambda prev: ...)`
└── Static vs. Live Running Session?
    ├── Notebook `.py` file only (idle)? ──> Edit disk file + run `marimo check --strict` & `pytest`
    └── Live `marimo edit` kernel open?  ──> Switch to `/marimo-pair` (`marimo._code_mode`)
```

## Toolchain & Verification Commands

```bash
uv run marimo edit --port 2718 notebook.py            # Interactive authoring
uv run marimo check --fix notebook.py                 # Auto-fix signatures & formatting
uv run marimo check --strict notebook.py              # Strict DAG, runtime & style verification
uv run marimo check notebook.py --select MW --format json  # WASM / Pyodide pre-flight check
uv run notebook.py                                    # Headless script execution smoke test
uv run pytest notebook.py -v                          # Execute embedded test_* cells
uv run ruff check notebook.py && uv run ruff format --check notebook.py
uv run marimo export html-wasm notebook.py -o dist/ --mode run --no-show-code
```

---

## References & Examples Index

- **Reference Manuals (`references/`)**:
  - [marimo_architecture_and_dag.md](./references/marimo_architecture_and_dag.md): Canonical `.py` grammar, `marimo check` rule codes (`MB*`/`MR*`/`MF*`/`MW*`), DAG scoping, `mo.state`, `mo.stop`, and CLI/batch dual mode.
  - [interactive_widgets_and_ui.md](./references/interactive_widgets_and_ui.md): `mo.ui` catalog, `.batch().form()`, layouts, explicit plot themes (`0.25.2+`), `_display_()`, `anywidget`, and WASM export.
  - [dual_toolchain_pixi_uv.md](./references/dual_toolchain_pixi_uv.md): `uv` & `pixi` orchestration (Python 3.14.8+/3.15), PEP 723 `--sandbox`, CLI reference, and embedded `pytest`.
  - [advanced_data_analysis_scenarios.md](./references/advanced_data_analysis_scenarios.md): Production DAG architectures for `heimdall-astro`, `talos-robotics`, and `microkernel-labs`.
- **Runnable Demonstration Notebooks & Manifests (`examples/`)**:
  - `pyproject.toml` ([examples/pyproject.toml](./examples/pyproject.toml)): Standalone PEP 621 manifest for `uv`.
  - `pixi.toml` ([examples/pixi.toml](./examples/pixi.toml)): Multi-platform `conda-forge` + PyPI manifest.
  - `astro_transit_photometry.py` ([examples/astro_transit_photometry.py](./examples/astro_transit_photometry.py)): Exoplanet Mandel-Agol transit model + gated MCMC.
  - `robotics_kalman_filter.py` ([examples/robotics_kalman_filter.py](./examples/robotics_kalman_filter.py)): 6-DoF EKF sensor fusion & `+/- 3 sigma` diagnostics.
  - `systems_telemetry_analysis.py` ([examples/systems_telemetry_analysis.py](./examples/systems_telemetry_analysis.py)): Microkernel IPC tail-latency HDR survival dashboard.
  - `bayesian_mcmc_diagnostic.py` ([examples/bayesian_mcmc_diagnostic.py](./examples/bayesian_mcmc_diagnostic.py)): Gelman-Rubin R-hat & integrated autocorrelation with embedded `pytest`.
