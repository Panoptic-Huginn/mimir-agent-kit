# Marimo Interactive UI Widgets & Declarative Layout Reference Manual

This manual provides a comprehensive API catalog and design guide for **Marimo** interactive UI widgets (`marimo.ui`), declarative layout containers (`mo.hstack`, `mo.vstack`, `mo.ui.tabs`, `mo.accordion`), scientific visualization integrations, and serverless WebAssembly (WASM) publishing.

---

## 1. Bidirectional Reactive UI Architecture

All Marimo UI components inherit from `marimo._plugins.ui._core.ui_element.UIElement`:
- **Bidirectional Binding**: Instantiating a widget in Python renders an interactive HTML5/React component in the frontend DOM. User interactions in the browser push the updated value back to the Python kernel.
- **Automatic Invalidation**: Whenever a widget's value updates, Marimo automatically identifies every cell that references that widget object and executes them in topological order.
- **Value Access**: The current state of any widget is accessed via its `.value` property.

---

## 2. Interactive UI Widgets Catalog

### 2.1 Numeric Controls: `mo.ui.slider`
Provides continuous or discrete numeric input:
```python
import marimo as mo

# Continuous float slider
learning_rate = mo.ui.slider(
    start=1e-4,
    stop=1e-1,
    step=1e-4,
    value=1e-2,
    debounce=True,
    label='Learning Rate (eta):',
)

# Discrete sequence slider
epoch_selector = mo.ui.slider(steps=[1, 5, 10, 25, 50, 100], value=25, label='Max Epochs:')
```

### 2.2 Selection Controls: `mo.ui.dropdown`
Enables single or multiple option selection from sequences or label-value dictionaries:
```python
model_selector = mo.ui.dropdown(
    options={
        'Linear Regression': 'lin_reg',
        'Extended Kalman Filter': 'ekf',
        'Bayesian MCMC': 'mcmc',
    },
    value='ekf',
    searchable=True,
    label='Telemetry Estimator Model:',
)
```

### 2.3 Text & String Inputs: `mo.ui.text`
Single-line text input with debounce and input masking:
```python
target_channel = mo.ui.text(
    value='system.ipc.latency',
    placeholder='e.g. system.ipc.latency',
    kind='text',  # "text", "password", "email", "url"
    debounce=True,
    label='IPC Channel:',
)
```

### 2.4 Tabular Data: `mo.ui.table`
High-performance interactive table supporting sorting, multi-column search, pagination, and row selection:
```python
telemetry_table = mo.ui.table(
    data=telemetry_records,  # List of dicts, Pandas DataFrame, or Polars DataFrame
    pagination=True,
    page_size=15,
    selection='multi',
    show_column_summaries=True,
    show_download=True,
)
```
- Accessing selection: `telemetry_table.value` returns a list of dictionaries or a filtered DataFrame corresponding to the selected rows.

### 2.5 Data Transformation: `mo.ui.dataframe`
Interactive visual pipeline allowing users to filter, group, aggregate, and sort DataFrames without writing code:
```python
df_transform = mo.ui.dataframe(df=raw_dataframe, page_size=10, limit=50000, show_download=True)
# df_transform.value returns the transformed DataFrame reactively
```

### 2.6 Execution Gating: `mo.ui.form`
Wraps any UI element or batch to suppress downstream reactivity until the user clicks an explicit "Submit" button. Essential for computationally intensive pipelines (e.g. MCMC sampling, orbital simulations):
```python
simulation_form = mo.ui.batch(
    html=mo.md('{particles} {iterations} {solver}'),
    elements={
        'particles': mo.ui.slider(100, 10000, step=100, value=1000, label='Particles'),
        'iterations': mo.ui.slider(10, 500, step=10, value=50, label='Iterations'),
        'solver': mo.ui.dropdown(['Euler', 'RK4', 'Verlet'], value='RK4', label='Solver'),
    },
).form(
    submit_button_label='Execute Simulation',
    validate=lambda vals: 'Particle count must exceed 500' if vals['particles'] < 500 else None,
)
```

### 2.7 Action Buttons: `mo.ui.button`
Triggers state updates or increments click counters:
```python
reset_btn = mo.ui.button(
    value=0,
    on_click=lambda count: count + 1,
    kind='warn',
    label='Reset Simulation State',
)
```

### 2.8 Dynamic Containers: `mo.ui.array` & `mo.ui.dictionary`
Groups dynamically generated collections of UI widgets into a single reactive structure:
```python
channel_gains = mo.ui.dictionary({f'ch_{i}': mo.ui.slider(0.0, 2.0, step=0.1, value=1.0) for i in range(4)})
# channel_gains.value returns {'ch_0': 1.0, 'ch_1': 1.0, ...}
```

---

## 3. Declarative Layout System

Construct responsive dashboards using Marimo's layout primitives.

### 3.1 Flexbox Rows & Columns: `mo.hstack` and `mo.vstack`
```python
# Horizontal layout with alignment and gap controls
controls_row = mo.hstack(
    items=[learning_rate, epoch_selector, model_selector],
    justify='space-between',
    align='center',
    gap=1.0,
    wrap=True,
)

# Vertical stacking
dashboard = mo.vstack(
    items=[mo.md('## Autonomous Flight Telemetry'), controls_row, telemetry_table],
    gap=1.5,
)
```

### 3.2 Reactive Tabs: `mo.ui.tabs`
Organizes multi-page analytical views. The active tab is accessible reactively via `tabs.value`.

> **⚠️ DEPRECATION NOTICE**: `mo.tabs` is deprecated in Marimo 0.25+ in favor of `mo.ui.tabs`. Always use `mo.ui.tabs` to retain tab selection reactivity and avoid deprecation warnings.

```python
analysis_tabs = mo.ui.tabs(
    tabs={
        'Light Curve Analysis': transit_plot_view,
        'MCMC Diagnostics': mcmc_chains_view,
        'Posterior Table': posterior_summary_table,
    },
    value='Light Curve Analysis',
)
```

### 3.3 Collapsible Accordions: `mo.accordion`
```python
advanced_config = mo.accordion(
    items={
        'Covariance Prior Hyperparameters': prior_controls,
        'Hardware Calibration Offsets': calibration_controls,
    },
    multiple=False,
    lazy=True,
)
```

### 3.4 Persistent Sidebar: `mo.sidebar`
Creates an application-level navigation and parameter drawer:
```python
app_sidebar = mo.sidebar(
    item=mo.vstack([
        mo.md('### Mission Parameters'),
        target_channel,
        learning_rate,
        reset_btn,
    ]),
    footer=mo.md('**Status**: Telemetry Lock Active'),
)
```

### 3.5 Informational Cards: `mo.stat` and `mo.callout`
```python
# Key Performance Indicator card
latency_stat = mo.stat(
    value='12.4 us',
    label='Median IPC Latency',
    caption='Target: < 20 us',
    direction='decrease',
)

# Severity banner
warning_banner = mo.callout('Sensor covariance matrix nearing singular threshold.', kind='danger')
```

---

## 4. Scientific Data Visualizers Integration

In analytical notebooks such as `astro_transit_photometry.py`, `robotics_kalman_filter.py`, `systems_telemetry_analysis.py`, and `bayesian_mcmc_diagnostic.py`, visualizers interact directly with UI widgets:

### 4.1 Plotly
Interactive WebGL/SVG graphics render natively. Return the Plotly `Figure` object or wrap in `mo.ui.plotly(fig)` for selection capture:
```python
import plotly.graph_objects as go

fig = go.Figure()
fig.add_trace(go.Scatter(x=time_steps, y=flux, mode='lines', name='Flux'))
fig.update_layout(template='plotly_dark', title='Photometric Light Curve')
# Returning fig renders the interactive chart
```

### 4.2 Altair
Declarative Vega-Lite charts with cross-filtering selections:
```python
import altair as alt

chart = (
    alt
    .Chart(dataframe)
    .mark_circle(size=60)
    .encode(
        x='orbital_phase:Q',
        y='normalized_flux:Q',
        color='transit_flag:N',
        tooltip=['time', 'flux', 'error'],
    )
    .interactive()
)
```

### 4.3 Matplotlib & Seaborn
Render Matplotlib figures cleanly into SVG/HTML using `mo.as_html` to prevent display anomalies:
```python
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(8, 4))
ax.hist(residuals, bins=50, color='teal', alpha=0.7)
ax.set_title('Kalman Innovation Residuals')
plt.tight_layout()

rendered_plot = mo.as_html(fig)
plt.close(fig)  # Prevent memory leak
```

---

## 5. Serverless WebAssembly (WASM) Publishing

Marimo notebooks can be exported to zero-server, client-side WebAssembly applications powered by Pyodide.

### 5.1 CLI Export Command
```bash
marimo export html-wasm notebook.py -o dist/index.html --include-code
```

### 5.2 Pyodide Runtime & Dependency Resolution
When executed in the browser:
1. Pyodide initializes a virtual WebAssembly CPython runtime inside a browser WebWorker.
2. Dependencies declared in PEP 723 inline script headers (`# /// script ... # ///`) are automatically downloaded as pure-Python or Emscripten-compiled wheels via `micropip`.
3. All interactive widgets (`mo.ui.slider`, `mo.ui.table`, `mo.ui.dropdown`, `mo.ui.button`, etc.) maintain full bidirectional reactivity entirely in client memory with zero server backend.

### 5.3 WASM Portability Guidelines
- **Supported**: Pure-Python packages, standard scientific wheels built for Pyodide (NumPy, SciPy, Pandas, Matplotlib, Altair).
- **Unsupported**: Raw POSIX sockets, multi-threaded C extensions without Emscripten ports, direct filesystem hardware access.

---

## 6. Sibling References & Skill Links

- [Marimo Architecture & Reactive DAG](./marimo_architecture_and_dag.md)
- [Dual Toolchain: Pixi & uv Environments](./dual_toolchain_pixi_uv.md)
- [Advanced Scientific & Engineering Data Analysis Scenarios](./advanced_data_analysis_scenarios.md)
- [Marimo Pro Root Skill Manual](../SKILL.md)
