# marimo `_code_mode` Runtime API Specification

This reference provides an in-depth technical specification of `marimo._code_mode` (`cm`), the private programmatic interface built into `marimo>=0.21.1` that allows autonomous agents to inspect, mutate, and orchestrate running marimo notebook kernels.

---

## 1. Scratchpad Execution vs. Code Mode Transactions

In a live pairing session, code executed via `execute-code.sh` or `/api/kernel/execute` runs inside the active Python kernel. However, there are two distinct execution scopes:

| Feature / Property | Ephemeral Scratchpad Execution | Code Mode Transaction (`cm.get_context()`) |
|---|---|---|
| **Invocation** | Standard Python code (e.g. `print(df.shape)`) | Wrapped in `async with cm.get_context() as ctx:` |
| **Namespace Scope** | Shallow copy of notebook global variables | Programmatic access to DAG, cells, and memory |
| **Persistence** | **Discarded upon completion**. No notebook cells created. | **Persisted to notebook canvas** and written to `.py` file |
| **Use Case** | Data inspection, shape checking, exploratory tests | Adding, updating, deleting, or re-running notebook cells |
| **Failure Handling** | Runtime exception printed to stderr; kernel untouched | Validation fails atomically on exit; changes discarded |

### The Scratchpad-Only Import Rule
> **CRITICAL INVARIANT**:  
> `import marimo._code_mode as cm` must **ONLY** be executed in scratchpad requests driven by the agent.  
> **NEVER** write `import marimo._code_mode` into a durable notebook cell (`ctx.create_cell(...)` or `ctx.edit_cell(...)`). Persisting `_code_mode` calls inside notebook cells creates self-referencing mutations that crash reactive compilation.

---

## 2. Mandatory Inspection Handshake

Because internal method signatures can evolve across marimo minor versions, agents **must always** begin by inspecting the live kernel's `_code_mode` module documentation:

```python
import marimo._code_mode as cm

help(cm)
```

Running this scratchpad command forces the agent to read the exact docstrings and method signatures supported by the active kernel before issuing mutations.

---

## 3. The `cm.get_context()` Context Manager

All durable notebook modifications must be enclosed in the asynchronous context manager:

```python
import marimo._code_mode as cm

async with cm.get_context(
    skip_validation=False,
    skip_staleness_check=False,
) as ctx:
    # 1. Inspect existing cells and graph
    # 2. Stage cell creations, edits, or deletions
    # 3. Queue execution
    ...
```

### Parameters:
- `skip_validation` (`bool`, default `False`): If `True`, bypasses the compile-time AST validation gate on exit. Use only when temporarily creating intermediate states that will be reconciled later.
- `skip_staleness_check` (`bool`, default `False`): If `True`, bypasses `StaleCellError` checking when modifying existing cells.

### Transactional Atomicity:
Mutations performed inside the context manager are staged in-memory. When the context manager exits:
1. The kernel constructs the candidate Directed Acyclic Graph (DAG) including proposed cell changes.
2. The AST compiler statically checks for cycles, multiple variable definitions, and syntax errors.
3. If validation succeeds, changes are committed to the in-memory kernel, pushed to the connected browser UI over WebSocket, and saved to the `.py` notebook file on disk.
4. If validation fails or an exception occurs, the entire transaction is rolled back; the notebook remains in its prior valid state.

---

## 4. Complete Context API Surface (`ctx`)

### 4.1 Context Properties

- **`ctx.cells`** (`Mapping[str, CellData]`):  
  A dictionary-like view of current notebook cells keyed by cell ID. Each cell object exposes:
  - `cell.id` (`str`): Unique identifier of the cell.
  - `cell.name` (`str | None`): Optional cell name (e.g. `setup`, `data_loader`).
  - `cell.code` (`str`): Python source code of the cell.
  - `cell.status` (`str`): Execution state (`idle`, `running`, `queued`, `disabled`).
  - `cell.errors` (`list`): List of active errors/exceptions on the cell.
  - `cell.config` (`dict`): Cell configuration dictionary (`hide_code`, `disabled`).
  *(Note: `ctx.cells` does NOT expose variable dependencies; use `ctx.graph` for dependency queries).*

- **`ctx.graph`** (`marimo.core.ast_compact.CellGraphCompact`):  
  The topological dependency graph of the notebook:
  - `ctx.graph.cells[cid].defs` (`set[str]`): Variable names defined by cell `cid`.
  - `ctx.graph.cells[cid].refs` (`set[str]`): Variable names referenced/read by cell `cid`.
  - `ctx.graph.ancestors(cid)` (`set[str]`): Set of cell IDs that cell `cid` depends upon.
  - `ctx.graph.descendants(cid)` (`set[str]`): Set of cell IDs that depend upon cell `cid`.

- **`ctx.globals`** (`dict[str, Any]`):  
  Direct read-only mapping of the live notebook's global variable namespace, allowing agents to inspect runtime objects (e.g. `ctx.globals['df'].columns`).

### 4.2 Structural Cell Operations

#### `ctx.create_cell(...)`
```python
# Signature: ctx.create_cell(code: str, name: str | None = None, hide_code: bool = True, before: str | None = None, after: str | None = None, disabled: bool = False) -> str
cid = ctx.create_cell(
    code="import polars as pl\nfiltered_df = df.filter(pl.col('val') > 0)",
    name='filter_positive_values',
    hide_code=False,
)
```
- **Description**: Stages the creation of a new cell. Returns the generated unique cell ID (`cid`).
- **Important**: Creating a cell is a **structural modification only**; it does not automatically execute the cell. You must call `ctx.run_cell(cid)` if execution is desired.
- **Positioning**: Specify `before="target_id"` or `after="target_id"` to place the cell relative to existing cells. If omitted, the cell is appended to the bottom.

#### `ctx.edit_cell(...)`
```python
# Signature: ctx.edit_cell(target: str, code: str | None = None, name: str | None = None, hide_code: bool | None = None, disabled: bool | None = None) -> None
ctx.edit_cell(
    'c1',
    code="import polars as pl\nfiltered_df = df.filter(pl.col('val') > 10)",
    hide_code=False,
)
```
- **Description**: Stages modification of an existing cell identified by cell ID or cell name.
- **Staleness Protection**: Triggers `StaleCellError` if the cell was modified in the UI since `ctx` was initialized.
- **Important**: To re-execute the edited cell and its downstream reactive dependents, call `ctx.run_cell(target)`.

#### `ctx.delete_cell(...)`
```python
# Signature: ctx.delete_cell(target: str) -> None
ctx.delete_cell('c1')
```
- **Description**: Stages deletion of a cell identified by ID or name.
- **Kernel Cleanup**: Deleting a cell scrubs all variables defined by that cell from kernel memory and triggers re-computation of downstream dependent cells.

#### `ctx.move_cell(...)`
```python
# Signature: ctx.move_cell(target: str, before: str | None = None, after: str | None = None) -> None
ctx.move_cell('c2', before='c1')
```
- **Description**: Reorders cell position in the notebook document. Does not alter execution order (which is strictly determined by topological DAG sorting).

#### `ctx.run_cell(...)`
```python
# Signature: ctx.run_cell(target: str) -> None
ctx.run_cell('c1')
```
- **Description**: Explicitly schedules a cell (and its reactive descendants) for execution upon context manager exit.

### 4.3 Environment & UI Operations

#### Package Management: `ctx.packages`
```python
ctx.packages.add('polars>=1.0.0')
ctx.packages.remove('legacy-lib')
```
- Installs or removes packages in the active environment.
- If the notebook is running with `--sandbox` and contains PEP 723 inline script metadata (`# /// script`), `ctx.packages.add` automatically updates the metadata block in the `.py` file.

#### UI Widget State Injection: `ctx.set_ui_value(...)`
```python
# Programmatically update slider or dropdown value
ctx.set_ui_value('threshold_slider', 0.85)
```
- Injects a new value into an active `mo.ui` component.
- Triggers reactive re-evaluation of all downstream cells that reference the UI component.

#### Output Capture: `ctx.screenshot(...)`
```python
# Signature: await ctx.screenshot(target: str, timeout_ms: int = 30000, as_data_url: bool = False, save_to: str | None = None) -> bytes
png_bytes = await ctx.screenshot(
    'c1',
    timeout_ms=30000,
    as_data_url=False,
    save_to='output.png',
)
```
- Captures visual rendered output of a cell as a PNG image (requires Playwright browser subsystem).

---

## 5. Concurrency Management and `StaleCellError`

### Why `StaleCellError` Occurs
During a live pairing session, both the human developer and the AI agent may modify the notebook concurrently. If an agent inspects cell `c1`, prepares an edit, and attempts to commit `ctx.edit_cell("c1", new_code)`, but the human user changed `c1` in the browser UI in the interim, marimo raises `StaleCellError`.

```text
marimo._code_mode.StaleCellError: Cell 'c1' was modified since last read.
```

### Prevention and Recovery Pattern
Always fetch the latest cell code immediately before modifying it:

```python
import marimo._code_mode as cm

# Step 1: Read latest state in scratchpad
async with cm.get_context() as ctx:
    current_code = ctx.cells['c1'].code

# Step 2: Prepare updated code based on current_code
updated_code = current_code.replace('alpha = 0.1', 'alpha = 0.01')

# Step 3: Apply edit
try:
    async with cm.get_context() as ctx:
        ctx.edit_cell('c1', code=updated_code)
        ctx.run_cell('c1')
except cm.StaleCellError:
    # Cell was modified concurrently; re-read and reconcile
    pass
```

If the agent explicitly wants to force an overwrite regardless of user edits:
```python
async with cm.get_context(skip_staleness_check=True) as ctx:
    ctx.edit_cell('c1', code=new_code)
    ctx.run_cell('c1')
```

---

## 6. AST Compilation Safety Gating

When `cm.get_context()` completes its execution block, marimo's compiler analyzes all queued operations against the notebook's global DAG invariants:

### Invariant 1: Single Variable Definition Rule
A top-level public variable name cannot be defined in more than one cell.
```python
# INVALID: Cell A defines x, Cell B defines x -> REJECTED
```
*Correction*: Use distinct names (`raw_df`, `clean_df`) or cell-private variables prefixed with `_` (`_temp = compute()`).

### Invariant 2: Cycle Prevention
Cells cannot form circular dependencies:
```python
# INVALID: Cell A refs y and defs x; Cell B refs x and defs y -> REJECTED
```

### Invariant 3: The Delete-and-Create Collision Trap
If an agent queues `ctx.delete_cell("cell_1")` (which defines `data`) and `ctx.create_cell("data = ...")` within the **same** `get_context()` block, the static AST analyzer may detect `Multiply-defined names: data` before the deletion is processed.
*Remedy*:
- Prefer `ctx.edit_cell("cell_1", code="data = ...")` instead of deleting and re-creating.
- Or pass `skip_validation=True` on `cm.get_context(skip_validation=True)`.

---

## 7. Cross References

- For setup and tool definitions of the streamable HTTP MCP server, see [MCP Bridge Configuration](mcp_bridge_configuration.md).
- For targeting multi-session servers and resolving connection issues, see [Session Targeting and Troubleshooting](session_targeting_troubleshooting.md).
- Return to the main skill manual at [Skill Entrypoint](../SKILL.md).
