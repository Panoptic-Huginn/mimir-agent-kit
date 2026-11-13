# Marimo Architecture & Reactive Directed Acyclic Graph (DAG) Reference Manual

This manual provides the authoritative architectural reference for **Marimo 0.25.2+** reactive Python notebooks targeting **Google Antigravity 2.31.2+** and **Gemini 4 Carbon**. It covers canonical `.py` file grammar, cell output rendering vs. `return` tuples, AST dependency analysis, exact `marimo check` lint codes, `mo.state`, `mo.stop`, dual interactive/CLI batch mode, and programmatic test harnesses.

---

## 1. Canonical `.py` Representation & Cell Rendering Rules

Unlike Jupyter JSON (`.ipynb`) notebooks with hidden mutable state and out-of-order execution bugs, a Marimo notebook is a pure-Python module (`*.py`) governed by strict top-level grammar.

### 1.1 Valid Top-Level File Grammar

Marimo's parser ONLY preserves these top-level constructs when loading or saving a notebook:

1. Optional PEP 723 metadata block (`# /// script ... # ///`).
2. `import marimo` and `__generated_with = "0.25.2"`.
3. `app = marimo.App(...)`.
4. At most ONE `with app.setup:` block (recommended: **import-only**, zero references to cell variables — `MB004`).
5. Optional `@app.function` and `@app.class_definition` reusable definitions (can reference only `app.setup` or earlier top-level symbols — `MR003`).
6. Zero or more `@app.cell` (or `@app.cell(column=0, hide_code=True)`) functions.
7. `if __name__ == "__main__": app.run()`.

> **CRITICAL**: Never place bare module-level `import ...` statements or variables outside `with app.setup:` or `@app.cell`. Marimo skips arbitrary top-level statements during notebook loading, causing `NameError` at runtime.

```python
# /// script
# requires-python = ">=3.14"
# dependencies = ["marimo>=0.25.2", "pydantic>=2.10.0"]
# ///

import marimo

__generated_with = '0.25.2'
app = marimo.App(width='medium')

with app.setup:
    import marimo as mo
    from pydantic import BaseModel, Field


@app.function
def photon_energy_j(wavelength_m: float) -> float:
    """Pure reusable helper importable by external Python modules."""
    _h = 6.62607015e-34
    _c = 299_792_458.0
    return (_h * _c) / wavelength_m


@app.cell
def compute_band():
    wavelength = 500e-9
    photon_energy = photon_energy_j(wavelength)
    _card = mo.stat(value=f'{photon_energy:.3e} J', label='500 nm Photon Energy')
    _card  # Unindented final expression -> renders in UI
    return photon_energy, wavelength


if __name__ == '__main__':
    app.run()
```

### 1.2 Cell Visual Output vs. `return` Statement (Why Notebooks Render Blank)

The **single most common LLM authoring bug** is assigning a UI layout or plot to a variable and returning it (`return (view,)`) without evaluating it:

- **`return (var1, var2)` ONLY exports variables to the DAG.** It produces **zero visual output** in `marimo edit` or `marimo run`.
- **Visual output comes ONLY from the final unindented expression statement executed before `return`**.
- **Never return a UI expression (`return mo.md(...)`)**: `return` in `@app.cell` must return only exported variable names (`return x, y` or bare `return`), never inline calls (`MB001` unparsable cell).
- **Never rely on indented expressions (`MR002`)**: An expression inside `if`, `else`, or `for` does NOT render. Assign `_view = mo.md("A") if cond else mo.md("B")` and evaluate `_view` unindented before `return`, or call `mo.output.replace(...)` / `mo.output.append(...)`.

```python
# WRONG: renders blank! (plot_view is exported, never evaluated as final expression)
# @app.cell
# def show_plot(fig, mo):
#     plot_view = mo.ui.plotly(fig)
#     return (plot_view,)

# RIGHT: final unindented expression renders AND exports if downstream cells need it
@app.cell
def show_plot(fig, mo):
    plot_view = mo.ui.plotly(fig)
    plot_view
    return (plot_view,)
```

### 1.3 AST Analysis & Topological Execution

Marimo parses each `@app.cell` AST using `marimo._ast.visitor.ScopedVisitor`:

1. **Definitions (`defs`)**: Non-underscore top-level variables/imports assigned in the cell.
2. **References (`refs`)**: External symbols read in the cell (declared as cell function parameters).
3. **Graph Edges**: Directed edge $A \to B$ whenever $\text{defs}(A) \cap \text{refs}(B) \neq \emptyset$.
4. **Topological Order**: Execution order (`marimo._runtime.dataflow.topological_sort`) depends strictly on DAG edges, never on physical line position in the `.py` file.

---

## 2. Variable Scoping & Marimo `0.25.2` Lint Rules

### 2.1 Single Definition Rule (`MB002`) & `_` Local Isolation

Every public (non-`_`) variable or import can be defined by **at most one cell**. Defining the same public name in two cells triggers `MB002` (`Multiply-defined names` / `MultipleDefinitionError`).

- Prefix short-lived loop indices or temporary intermediates with `_` (`_idx`, `_filtered`) so Marimo mangles them locally and excludes them from global `defs`.
- Avoid over-prefixing entire cells with `_` — only use `_` for genuine scratch/local names, and remember `_var` cannot be returned or read by another cell.
- **No Wildcard Imports**: Never use `from module import *`.

### 2.2 Complete Marimo `0.25.2` `marimo check` Rule Matrix

| Category | Code | Rule Class | Meaning & Resolution |
| :--- | :--- | :--- | :--- |
| Breaking | `MB001` | `UnparsableRule` | Cell cannot be parsed as valid Marimo `@app.cell` (e.g. `return mo.md(...)`). |
| Breaking | `MB002` | `MultipleDefinitionsRule` | Same public variable defined in >=2 cells; rename or prefix scratch vars `_`. |
| Breaking | `MB003` | `CycleDependenciesRule` | Circular DAG dependency between cells; extract shared upstream node or `mo.state`. |
| Breaking | `MB004` | `SetupCellDependenciesRule` | `app.setup` references cell-defined variables; keep `app.setup` import/constant-only. |
| Breaking | `MB005` | `SyntaxErrorRule` | Python syntax error inside cell or notebook module. |
| Runtime | `MR001` | `SelfImportRule` | Notebook imports itself. |
| Runtime | `MR002` | `BranchExpressionRule` | Final expression inside `if`/`else`/`try` branch will not display; hoist to unindented line. |
| Runtime | `MR003` | `ReusableDefinitionOrderRule` | `@app.function` / `@app.class_definition` references symbol defined after it in file. |
| Runtime | `MR004` | `PrivateImportAliasRule` | Underscore import alias hides module unexpectedly. |
| Formatting | `MF001`–`MF007` | General, stdout/stderr, empty cell, SQL (`MF005`), misc log, markdown dedent | Fix automatically via `marimo check --fix`. Avoid Python comments in `mo.sql()` cells (`MF005`). |
| WASM | `MW001`–`MW003` | `IncompatibleImportsRule`, `UnsafeSystemCallsRule`, `IncompatiblePackagesRule` | Audited via `marimo check --select MW --format json` for Pyodide exports. |

---

## 3. Graph Cycles (`MB003`), Resolution & Caching

A cycle ($\text{Cell } A \rightarrow \text{Cell } B \rightarrow \text{Cell } A$) halts execution (`CycleError`):

1. **Shared Node Extraction**: Move shared initialization into one upstream cell feeding both branches.
2. **Functional Parameterization**: Lift pure logic into `@app.function` taking explicit arguments.
3. **Decoupling via `mo.state`**: Use explicit getter/setter state containers (`allow_self_loops=False` default) for iterative state updates.

### Caching Expensive Computations

- **`@mo.cache`**: Memoizes pure function results in RAM keyed by arguments and code hash.
- **`@mo.persistent_cache(save_path=...)`**: Persists deterministic computation across kernel restarts (ideal for precomputing WASM `--execute` branches).

---

## 4. State Management (`mo.state`) & Execution Gating (`mo.stop`)

Use `mo.state` only when bidirectional widget synchronization or accumulators cannot be expressed as pure DAG transforms:

```python
@app.cell
def init_counter_state(mo):
    get_records, set_records = mo.state([])
    return get_records, set_records
```

- Calling `get_records()` subscribes the cell reactively.
- Always update immutably: `set_records(lambda prev: [*prev, new_item])`. Never call `records.append(...)` across cells — in-place mutations are invisible to the DAG!
- **Execution Gating (`mo.stop`)**: Halts execution when `predicate` is `True`, renders `output` in place, and cancels downstream dependents cleanly:

```python
@app.cell
def validate_sensor_inputs(mo, raw_telemetry):
    _is_valid = raw_telemetry is not None and len(raw_telemetry) > 0
    mo.stop(
        not _is_valid,
        output=mo.callout('Telemetry stream empty. Awaiting hardware ingest...', kind='warn'),
    )
    normalized_data = raw_telemetry / 1000.0
    normalized_data
    return (normalized_data,)
```

---

## 5. Dual Interactive UI & Headless CLI Batch Mode

Use `mo.app_meta().mode == "script"` with `mo.cli_args()` and `pydantic.BaseModel` so the same notebook serves an interactive form in `marimo edit`/`run` AND accepts typed CLI arguments in `uv run notebook.py -- --samples 4096`:

```python
@app.cell
def resolve_params(BaseModel, Field, mo, param_form):
    class RunParams(BaseModel):
        samples: int = Field(default=1024, ge=64)

    if mo.app_meta().mode == 'script':
        _cli = {k.replace('-', '_'): v for k, v in mo.cli_args().items()}
        run_params = RunParams(**_cli)
    else:
        mo.stop(param_form.value is None, mo.md('Submit parameters to execute.'))
        run_params = RunParams(**param_form.value)
    return (run_params,)
```

For multi-column notebooks, decorate cells with `@app.cell(column=0, hide_code=True)` (requires `app = marimo.App(width="columns")`).

---

## 6. Programmatic Headless Execution & Testing

Marimo notebooks (including demonstration notebooks such as `astro_transit_photometry.py`, `robotics_kalman_filter.py`, `systems_telemetry_analysis.py`, and `bayesian_mcmc_diagnostic.py`) can be imported and executed directly in automated tests:

```python
# Full notebook execution: outputs[i] is cell i's rendered visual value (None if silent)
from examples.robotics_kalman_filter import app


def test_robotics_kalman_filter_convergence():
    outputs, defs = app.run()
    assert defs['filter_converged'] is True
    assert defs['estimation_error'] < 0.05


def test_custom_parameters():
    outputs, defs = app.run(defs={'noise_sigma': 0.01})
    assert defs['covariance_trace'] < 0.1


# Isolated single-cell execution via cell.run(**refs)
from examples.astro_transit_photometry import compute_transit_model


def test_transit_model_unit():
    output, defs = compute_transit_model.run(radius_ratio=0.1, impact_param=0.2)
    flux = defs['transit_flux']
    assert len(flux) == 1000
    assert min(flux) < 1.0
```

---

## 7. Sibling References & Skill Links

- [Interactive Widgets & UI Components](./interactive_widgets_and_ui.md)
- [Dual Toolchain: Pixi & uv Environments](./dual_toolchain_pixi_uv.md)
- [Advanced Scientific & Engineering Data Analysis Scenarios](./advanced_data_analysis_scenarios.md)
- [Marimo Pro Root Skill Manual](../SKILL.md)
