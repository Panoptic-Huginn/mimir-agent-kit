# Marimo Architecture & Reactive Directed Acyclic Graph (DAG) Reference Manual

This manual provides an authoritative, in-depth architectural reference for the **Marimo** reactive notebook runtime (version `0.25.2+`, November 2026). It covers the Directed Acyclic Graph (DAG) execution model, AST dependency analysis, variable scoping invariants, graph cycle resolution, explicit state primitives (`mo.state`), execution gating (`mo.stop`), and programmatic test harnesses.

---

## 1. The Directed Acyclic Graph (DAG) Execution Model

Unlike legacy computational notebooks (such as Jupyter) that maintain execution order through the historical sequence of manual cell executions—leading to hidden global mutable state, out-of-order execution bugs, and irreproducible workflows—Marimo operates as a pure **Directed Acyclic Graph (DAG)** of functional execution cells.

### 1.1 Pure Python File Representation (`*.py`)
A Marimo notebook is stored on disk as a standard, 100% valid Python script. Each notebook instantiates an `app = marimo.App()` object and encapsulates computational blocks inside `@app.cell` function decorators:

```python
import marimo

__generated_with = '0.25.2'
app = marimo.App(width='medium')


@app.cell
def load_constants():
    speed_of_light = 299_792_458.0  # m/s
    planck_constant = 6.62607015e-34  # J*s
    return planck_constant, speed_of_light


@app.cell
def compute_energy(planck_constant, speed_of_light):
    wavelength = 500e-9  # 500 nm photon
    photon_energy = (planck_constant * speed_of_light) / wavelength
    return photon_energy, wavelength


if __name__ == '__main__':
    app.run()
```

### 1.2 Abstract Syntax Tree (AST) Parsing
When a notebook is loaded or modified, Marimo does not rely on runtime inspection or global variable traps. Instead, it statically inspects each cell's Abstract Syntax Tree using `marimo._ast.visitor.ScopedVisitor`:
1. **Definitions (`defs`)**: Any top-level variable, function, or class assigned within the cell (e.g. `photon_energy = ...`).
2. **References (`refs`)**: Any external variable referenced inside the cell that is not defined locally (e.g. `planck_constant`, `speed_of_light`).
3. **Graph Edges**: A directed edge is created from Cell $A$ to Cell $B$ if and only if:
   $$\text{defs}(A) \cap \text{refs}(B) \neq \emptyset$$

### 1.3 Topological Sort & Execution Independence
The execution sequence of cells is determined strictly by topological sorting of the dependency graph (`marimo._runtime.dataflow.topological_sort`):
- **Physical Position Independence**: The physical line position of a cell function inside the `.py` source file has **zero effect** on execution order. A cell declared at line 400 that defines `sensor_config` will execute prior to a cell at line 20 that references `sensor_config`.
- **Deterministic Re-execution**: Modifying or triggering a cell automatically re-executes that cell and all of its transitive downstream descendants in topological order. Independent upstream or parallel branches remain untouched.

---

## 2. Variable Scoping Rules & Invariants

Marimo enforces deterministic scoping to eliminate hidden state and side effects.

### 2.1 The Single Variable Definition Rule (`MB002`)
A global variable name can be defined in **exactly one cell** across the entire notebook:
- If Cell 1 assigns `sensor_reading = 10` and Cell 2 assigns `sensor_reading = 20`, Marimo flags breaking diagnostic `critical[multiple-definitions]` (`MB002`) and halts execution with `MultipleDefinitionError`.
- **Rationale**: If two cells defined the same variable, downstream cells depending on that variable would have an ambiguous origin, destroying DAG determinism.

### 2.2 Cell Isolation via Leading Underscore (`_var`)
To use temporary variables (e.g. loop iterators, intermediate arrays, scratch buffers) without polluting the global notebook scope or causing variable collision errors:
- **Naming Rule**: Prefix the variable name with a single leading underscore (e.g. `_i`, `_temp_matrix`, `_raw_buffer`).
- **AST Mangling**: Marimo's compiler (`marimo._ast.variables.is_local`) identifies private identifiers and mangles them into `_cell_{cell_id}_var`.
- **Exclusion from `defs`**: Mangled local variables are excluded from the cell's exported `defs`. Downstream cells cannot reference them; attempting to do so raises `NameError`.

```python
@app.cell
def process_data(raw_records):
    # _filtered is cell-private; will not collide with other cells
    _filtered = [r for r in raw_records if r.get('valid')]
    clean_summary = len(_filtered)
    return (clean_summary,)
```

### 2.3 Top-Level Decorators & Contexts
- `@app.cell`: Standard reactive computation node.
- `@app.function`: Exposes a reusable Python function across cells as a callable entrypoint with explicit typed signatures.
- `@app.class_definition`: Exposes a class definition directly as a node in the graph.
- `with app.setup:` Context (MEP-0008): Defines root-level initialization logic (imports, base constants). Setup blocks must remain pure and cannot reference any notebook variables (`SetupRootError`, `MB004`).

---

## 3. Graph Cycles (`CycleError`, `MB003`) & Resolution Strategies

A cycle occurs when two or more cells directly or indirectly depend on each other's outputs:
$$\text{Cell } A \rightarrow \text{Cell } B \rightarrow \text{Cell } A$$
When detected, Marimo refuses to execute the affected subgraph and raises `marimo._ast.errors.CycleError` (`MB003`).

### 3.1 Cycle Example
```python
# Cell A
@app.cell
def cell_a(y):
    x = y + 10
    return (x,)


# Cell B
@app.cell
def cell_b(x):
    y = x * 2
    return (y,)
```

### 3.2 Resolution Strategies

#### Strategy 1: Shared Node Extraction
Extract the mutually dependent calculation into an upstream cell that computes both values or provides base inputs:
```python
# Upstream Cell
@app.cell
def compute_base():
    base_signal = 100
    return (base_signal,)


# Downstream Cell A
@app.cell
def step_a(base_signal):
    x = base_signal + 10
    return (x,)


# Downstream Cell B
@app.cell
def step_b(base_signal):
    y = base_signal * 2
    return (y,)
```

#### Strategy 2: Functional Parameterization
Convert one of the nodes into a pure function using `@app.function` and pass parameters explicitly rather than binding through global DAG references.

#### Strategy 3: Decoupling via `mo.state`
Use Marimo's explicit state container to manage asynchronous or user-driven state transitions without direct DAG feedback loops.

---

## 4. State Management with `mo.state`

When building interactive applications, simulations, or multi-step wizards where state must persist across user interactions or be shared across disconnected controls, use `mo.state`:

```python
import marimo as mo

get_counter, set_counter = mo.state(initial_value=0)
```

### 4.1 Getter & Setter Contract
- `get_counter()` (`State[T]`): Reads the current value. Calling `get_counter()` inside a cell registers that cell as a reactive subscriber to the state.
- `set_counter(new_val)` (`SetFunctor[T]`): Sets a new value.
- `set_counter(lambda prev: prev + 1)`: Functional updater accepting the prior state value.

### 4.2 Cycle Prevention (`allow_self_loops=False`)
By default, Marimo sets `allow_self_loops=False`:
- If Cell $A$ calls `set_counter(...)`, Marimo re-executes all *other* cells subscribing via `get_counter()`, but **does not re-execute Cell $A$**.
- This default prevents runaway infinite recursion loops.
- Setting `allow_self_loops=True` permits a cell to re-trigger itself upon setting state, but requires explicit termination guards (e.g. `if new_val != get_counter(): set_counter(new_val)`).

### 4.3 In-Place Mutation Anti-Pattern
Marimo tracks assignments to names in Python code. It **does not** hook low-level memory mutations.
- **Forbidden**:
  ```python
  # BUG: Downstream cells will NOT re-evaluate!
  records = get_records()
  records.append(new_item)
  ```
- **Correct**:
  ```python
  # Functional update triggers reactive subscribers
  set_records(lambda prev: [*prev, new_item])
  ```

---

## 5. Execution Gating with `mo.stop`

`mo.stop(predicate: bool, output: object = None)` conditionally halts cell execution and suppresses downstream DAG cascades:

```python
@app.cell
def validate_sensor_inputs(mo, raw_telemetry):
    is_valid = raw_telemetry is not None and len(raw_telemetry) > 0
    mo.stop(
        not is_valid,
        output=mo.callout('Telemetry stream empty. Awaiting hardware ingest...', kind='warn'),
    )
    # Code below only executes if is_valid is True
    normalized_data = raw_telemetry / 1000.0
    return (normalized_data,)
```

### 5.1 Flow Control & Transitive Cancellation
- When `predicate` evaluates to `True`, the cell immediately terminates execution.
- If `output` is provided (such as `mo.md()` or `mo.callout()`), it is rendered in the UI at the cell's position.
- **Transitive Cancellation**: All downstream descendant cells expecting variables produced by this cell are transitioned to `cancelled` state and bypassed entirely.

---

## 6. Cell Lifecycle State Machine

A cell within the Marimo kernel transitions through explicit lifecycle states:

```
+------------+       Edit / Trigger       +------------+
|    IDLE    | -------------------------> |   QUEUED   |
+------------+                            +------------+
      ^                                          |
      | Finish                                   | Runtime Dispatches
      |                                          v
+------------+     Ancestor Error / mo.stop() +------------+
| CANCELLED  | <---------------------------  |  RUNNING   |
+------------+                               +------------+
```

1. **`idle`**: The cell has evaluated and is awaiting graph invalidation.
2. **`queued`**: An upstream dependency has mutated; the cell is scheduled in topological order.
3. **`running`**: Bytecode is currently executing in the Python interpreter.
4. **`disabled-transitively`**: An upstream cell was configured as disabled.
5. **`cancelled`**: An upstream ancestor raised an exception or triggered `mo.stop()`.

---

## 7. Programmatic Headless Execution & Testing

Marimo notebooks (including demonstration notebooks such as `astro_transit_photometry.py`, `robotics_kalman_filter.py`, `systems_telemetry_analysis.py`, and `bayesian_mcmc_diagnostic.py`) can be imported and executed programmatically by external Python scripts or test suites:

### 7.1 Full Notebook Execution (`app.run()`)
```python
# Demonstrates running a Marimo app programmatically
from examples.robotics_kalman_filter import app


def test_robotics_kalman_filter_convergence():
    outputs, defs = app.run()
    assert defs['filter_converged'] is True
    assert defs['estimation_error'] < 0.05
```

### 7.2 Parameter Overrides (`app.run(defs={...})`)
Override specific cell definitions without running the original defining cell:
```python
def test_custom_parameters():
    # Bypasses the default noise_sigma cell and supplies 0.01 directly
    outputs, defs = app.run(defs={'noise_sigma': 0.01})
    assert defs['covariance_trace'] < 0.1
```

### 7.3 Isolated Cell Execution (`cell.run(**refs)`)
Directly unit-test a specific cell function, passing upstream refs as keyword arguments:
```python
from examples.astro_transit_photometry import compute_transit_model


def test_transit_model_unit():
    output, defs = compute_transit_model.run(radius_ratio=0.1, impact_param=0.2)
    flux = defs['transit_flux']
    assert len(flux) == 1000
    assert min(flux) < 1.0
```

---

## 8. Sibling References & Skill Links

- [Interactive Widgets & UI Components](./interactive_widgets_and_ui.md)
- [Dual Toolchain: Pixi & uv Environments](./dual_toolchain_pixi_uv.md)
- [Advanced Scientific & Engineering Data Analysis Scenarios](./advanced_data_analysis_scenarios.md)
- [Marimo Pro Root Skill Manual](../SKILL.md)
