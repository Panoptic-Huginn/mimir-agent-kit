# Marimo Interactive UI Widgets & Declarative Layout Reference Manual

This manual provides the API catalog and best practices for **Marimo 0.25.2+** interactive UI widgets (`marimo.ui`), declarative layout containers (`mo.hstack`, `mo.vstack`, `mo.ui.tabs`, `mo.accordion`), custom widgets (`_display_()`, `anywidget`), explicit plot themes, SQL cells (`mo.sql`), and serverless WebAssembly (WASM) publishing.

---

## 1. Bidirectional Reactive UI Architecture & Key Rules

All Marimo UI components inherit from `marimo._plugins.ui._core.ui_element.UIElement`:

1. **Cross-Cell Value Binding Rule**: You **cannot** access `widget.value` meaningfully inside the same `@app.cell` that creates `widget`. Always create, display (via unindented final expression), and `return (widget,)` in Cell A; read `widget.value` in downstream Cell B.
2. **Always Display Created Widgets**: Every interactive control or layout container cell must end with the UI object/container as its final unindented expression before `return`.
3. **Avoid Unnecessary `if widget:` Guards**: Downstream cells do not execute until their dependencies exist. Use `mo.stop(...)` when waiting for a button click or form submission (`not run_btn.value` or `form.value is None`).

---

## 2. Interactive UI Widgets Catalog

### 2.1 Numeric & Range Controls: `mo.ui.slider`, `mo.ui.range_slider`, `mo.ui.number`

```python
@app.cell
def numeric_controls(mo):
    learning_rate = mo.ui.slider(
        start=1e-4,
        stop=1e-1,
        step=1e-4,
        value=1e-2,
        debounce=True,
        label="Learning Rate (eta):",
    )
    epoch_selector = mo.ui.slider(
        steps=[1, 5, 10, 25, 50, 100],
        value=25,
        label="Max Epochs:",
    )
    band_range = mo.ui.range_slider(
        start=0.0, stop=100.0, value=[10.0, 90.0], label="Passband"
    )
    mo.hstack([learning_rate, epoch_selector, band_range], wrap=True)
    return band_range, epoch_selector, learning_rate
```

### 2.2 Selection & Text Controls: `mo.ui.dropdown`, `mo.ui.multiselect`, `mo.ui.text`, `mo.ui.radio`

```python
@app.cell
def selection_controls(mo):
    model_selector = mo.ui.dropdown(
        options={
            "Linear Regression": "lin_reg",
            "Extended Kalman Filter": "ekf",
            "Bayesian MCMC": "mcmc",
        },
        value="ekf",
        searchable=True,
        allow_select_none=False,
        label="Telemetry Estimator Model:",
    )
    target_channel = mo.ui.text(
        value="system.ipc.latency",
        placeholder="e.g. system.ipc.latency",
        kind="text",
        debounce=True,
        label="IPC Channel:",
    )
    mo.hstack([model_selector, target_channel])
    return model_selector, target_channel
```

### 2.3 Tabular Data & Interactive Explorers: `mo.ui.table`, `mo.ui.dataframe`, `mo.ui.data_explorer`

Marimo `0.25.2+` natively supports GeoJSON and GeoParquet table/map downloads alongside CSV/JSON/Parquet in `mo.ui.table`:

```python
@app.cell
def show_table(mo, telemetry_records):
    telemetry_table = mo.ui.table(
        data=telemetry_records,
        pagination=True,
        page_size=15,
        selection="multi",
        show_column_summaries=True,
        show_download=True,
    )
    telemetry_table
    return (telemetry_table,)
```

- `telemetry_table.value` returns the selected subset of rows (list of dicts or sliced DataFrame).
- `mo.ui.dataframe(df)` lets users interactively filter, sort, group, and aggregate DataFrames; `.value` yields the transformed DataFrame.

### 2.4 Forms & Batched Execution Gating: `.batch().form()`

`mo.ui.form(element=...)` requires a single `UIElement` (e.g., `mo.ui.dropdown(...).form(...)`, `mo.ui.dictionary(...).form(...)`, or `mo.md(...).batch(...).form(...)`). **Never pass `mo.vstack([...])` (`Html`) to `mo.ui.form(element=...)`.**

```python
@app.cell
def build_simulation_form(mo):
    simulation_form = (
        mo
        .md(
            """
            ### Simulation Parameters
            - **Particles**: {particles}
            - **Iterations**: {iterations}
            - **Solver**: {solver}
            """
        )
        .batch(
            particles=mo.ui.slider(100, 10000, step=100, value=1000, label="Particles"),
            iterations=mo.ui.slider(10, 500, step=10, value=50, label="Iterations"),
            solver=mo.ui.dropdown(
                ["Euler", "RK4", "Verlet"], value="RK4", label="Solver"
            ),
        )
        .form(
            submit_button_label="Execute Simulation",
            show_clear_button=True,
            clear_on_submit=False,
            bordered=True,
            validate=lambda vals: (
                "Particle count must exceed 500"
                if vals is None or vals["particles"] < 500
                else None
            ),
        )
    )
    simulation_form
    return (simulation_form,)
```

### 2.5 Action Buttons & Triggers: `mo.ui.button`, `mo.ui.run_button`, `mo.ui.refresh`

```python
@app.cell
def action_buttons(mo):
    run_btn = mo.ui.run_button(label="Compute Posterior", kind="primary")
    reset_btn = mo.ui.button(
        value=0,
        on_click=lambda count: count + 1,
        kind="warn",
        label="Reset State",
    )
    mo.hstack([run_btn, reset_btn], justify="start")
    return reset_btn, run_btn
```

### 2.6 Custom Rich Widgets: `_display_(self)` and `mo.ui.anywidget`

- **Read-only custom visuals**: Implement `_display_(self)` on any class returning `mo.Html` / markdown / SVG.
- **Bidirectional JS widgets**: Wrap any `anywidget.AnyWidget` subclass in `widget = mo.ui.anywidget(MyWidget())`. Access widget instance attrs via `widget.widget` and bound traitlets via `widget.value`.

---

## 3. Declarative Layout System & SQL

### 3.1 Containers, Tabs, Accordions, Sidebar, Cards

- `mo.hstack(items, justify="space-between", align="center", gap=1.0, wrap=True)`
- `mo.vstack(items, gap=1.5)`
- `mo.ui.tabs({"Overview": v1, "Diagnostics": v2}, value="Overview")`: **Always use `mo.ui.tabs`**, NOT deprecated `mo.tabs`.
- `mo.accordion({"Model Details": detail_md}, multiple=False, lazy=True)`
- `mo.sidebar(nav_vstack, footer=mo.md("**Status**: Live"))`
- `mo.stat(value="12.4 us", label="Median IPC Latency", caption="Target < 20 us", direction="decrease")`
- `mo.callout(mo.md("Covariance healthy."), kind="success")`

### 3.2 Native SQL Cells (`mo.sql`)

Query in-memory Polars/Pandas DataFrames, DuckDB relations, or external SQL engines cleanly with `mo.sql`:

```python
@app.cell
def query_outliers(mo, telemetry_df):
    high_latency_df = mo.sql(
        """
        SELECT core, subsystem, latency_us
        FROM telemetry_df
        WHERE latency_us >= 50.0
        ORDER BY latency_us DESC
        LIMIT 20
        """
    )
    return (high_latency_df,)
```

*Rule (`MF005`)*: Never include Python `#` comments inside SQL cells.

---

## 4. Scientific Data Visualizers & Marimo `0.25.2+` Plot Themes

In analytical notebooks such as `astro_transit_photometry.py`, `robotics_kalman_filter.py`, `systems_telemetry_analysis.py`, and `bayesian_mcmc_diagnostic.py`, note **Marimo 0.25.2 Breaking Change (#11147)**: marimo no longer automatically overrides Matplotlib, Plotly, Bokeh, or HoloViews plots with a dark theme. Set themes explicitly using `mo.app_meta().theme`:

### 4.1 Plotly

```python
@app.cell
def plot_light_curve(flux, go, mo, time_steps):
    _template = "plotly_dark" if mo.app_meta().theme == "dark" else "plotly_white"
    _fig = go.Figure()
    _fig.add_trace(go.Scatter(x=time_steps, y=flux, mode="lines", name="Flux"))
    _fig.update_layout(template=_template, title="Photometric Light Curve")
    chart = mo.ui.plotly(_fig)
    chart
    return (chart,)
```

### 4.2 Altair

Pass Polars or Pandas DataFrames directly and wrap in `mo.ui.altair_chart(chart)` for interactive brush selections:

```python
@app.cell
def plot_altair(alt, dataframe, mo):
    _chart = (
        alt
        .Chart(dataframe)
        .mark_circle(size=60)
        .encode(
            x="orbital_phase:Q",
            y="normalized_flux:Q",
            color="transit_flag:N",
            tooltip=["time", "flux", "error"],
        )
        .interactive()
    )
    selected_points = mo.ui.altair_chart(_chart)
    selected_points
    return (selected_points,)
```

### 4.3 Matplotlib & Seaborn

Pass `fig` or `plt.gca()` as the final expression (or wrap with `mo.as_html(fig)` and `plt.close(fig)`):

```python
@app.cell
def plot_residuals(mo, plt, residuals):
    _fig, _ax = plt.subplots(figsize=(8, 4))
    _ax.hist(residuals, bins=50, color="teal", alpha=0.7)
    _ax.set_title("Kalman Innovation Residuals")
    plt.tight_layout()
    _rendered = mo.as_html(_fig)
    plt.close(_fig)
    _rendered
    return
```

---

## 5. Serverless WebAssembly (WASM) Publishing (`0.25.2+`)

Marimo exports reactive notebooks to client-side WebAssembly applications powered by Pyodide:

```bash
# Directory export for HTTP static hosting (read-only app mode, code hidden)
uv run marimo export html-wasm notebook.py -o dist/ --mode run --no-show-code

# Single self-contained CDN HTML file (can be opened directly via file://)
uv run marimo export html-wasm notebook.py -o dist/app.html --mode run --single-file

# Fully offline WASM bundle (marimo 0.25.2+ downloads Pyodide + wheels locally)
uv run marimo export html-wasm notebook.py -o dist_offline/ --mode run --offline
```

### WASM Pre-Flight Check (`MW001`–`MW003`) & Heavy-Dependency Escape Hatch

Before exporting to WASM, run:

```bash
uv run marimo check notebook.py --select MW --format json
```

- Declare ALL notebook imports inside the PEP 723 `# /// script` header (`marimo` installs them automatically via `micropip` in Pyodide).
- If a notebook needs a non-WASM package (e.g., `torch`), mark `"torch; sys_platform != 'emscripten'"`, enable `[tool.marimo.runtime] cache_cells = true`, use `@mo.persistent_cache(method="lazy")` for discrete option grids, and export with `--execute`.
- Remember: Pyodide is capped at 2 GB memory, lacks raw POSIX sockets, and adapts `threading`/`multiprocessing` cooperatively (sequential execution).

---

## 6. Sibling References & Skill Links

- [Marimo Architecture & Reactive DAG](./marimo_architecture_and_dag.md)
- [Dual Toolchain: Pixi & uv Environments](./dual_toolchain_pixi_uv.md)
- [Advanced Scientific & Engineering Data Analysis Scenarios](./advanced_data_analysis_scenarios.md)
- [Marimo Pro Root Skill Manual](../SKILL.md)
