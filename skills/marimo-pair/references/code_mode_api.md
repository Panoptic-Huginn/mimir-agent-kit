# Code-Mode Context API & Safe AST Mutations (`marimo._code_mode`)

Every persistent mutation on a live **Marimo 0.25.2+** session must go through `marimo._code_mode` inside an ephemeral scratchpad while respecting AST DAG invariants.

---

## 1. Scratchpad Execution Invariants

1. **Scratchpad-Only Import Rule:** Never write `import marimo._code_mode` inside a cell created by `ctx.create_cell` or `ctx.edit_cell`. Keep `import marimo._code_mode as cm` strictly inside ephemeral scratchpads.
2. **Never Call `asyncio.run(...)`:** Scratchpad code executes directly inside an active async event loop. Always use top-level `async with cm.get_context() as ctx:`.
3. **Sync Queue vs Async Methods:** `ctx.create_cell`, `ctx.edit_cell`, `ctx.delete_cell`, `ctx.move_cell`, `ctx.run_cell`, `ctx.set_ui_value`, and `ctx.packages.add` are **synchronous** calls that enqueue mutations onto the transaction and flush atomically when `async with cm.get_context()` exits. **Do NOT `await` them.** Only `cm.get_context()`, `ctx.screenshot()`, and `ctx.close_screenshot_session()` are coroutines.
4. **Raw Cell Body Rule:** Pass raw Python body statements only — never `@app.cell`, `def ...():`, or `return (...)`. End visual cells with an unindented display expression so Marimo renders the cell output.

---

## 2. Inspecting Kernel State (`ctx.cells`, `ctx.graph`, `ctx.globals`)

Use read-only scratchpads first to map cells, search source code, and inspect live variables cleanly:

```python
import marimo._code_mode as cm

async with cm.get_context() as ctx:
    for cid, cell in ctx.cells.items():
        print(f'{cid} [{cell.name or "unnamed"}] status={cell.status} errors={len(cell.errors)}')

    # Substring and regex search across live notebook cells (Marimo 0.25.2+)
    matches = ctx.cells.find('mo.ui.slider')
    regex_hits = ctx.cells.grep(r'def\s+fit_')
    print('Slider cells:', [c.id for c in matches], 'Model defs:', [c.id for c in regex_hits])
```

Inspect runtime globals, the live DAG `ctx.graph`, and which cell owns an object via `ctx.find_cell_defining_object`:

```python
import marimo._code_mode as cm

async with cm.get_context() as ctx:
    user_vars = {k: type(v).__name__ for k, v in ctx.globals.items() if not k.startswith('_')}
    print('Live globals:', user_vars)

    if 'df' in ctx.globals:
        owner = ctx.find_cell_defining_object(ctx.globals['df'])
        print('df owner:', owner)
        print('DAG children of owner:', ctx.graph.children.get(owner, set()))
```

Inspect execution errors, standard output, and HTML/UI outputs after a run:

```python
import marimo._code_mode as cm

async with cm.get_context() as ctx:
    for cell in ctx.cells.values():
        if cell.errors or cell.status in ('exception', 'marimo_error'):
            print('FAILED CELL:', cell.id, cell.errors)
        if cell.console_outputs:
            print('CONSOLE:', cell.id, [o.data for o in cell.console_outputs])
        if cell.output is not None:
            print('OUTPUT MIME:', cell.id, getattr(cell.output, 'mimetype', type(cell.output).__name__))
```

---

## 3. Enqueueing Cell Creation, Editing, Moving, and Running

Check for empty cells first (`not cell.code.strip()`) and reuse them with `ctx.edit_cell` instead of creating cluttered empty cells. Pass `hide_code=False` when creating visible code cells (since `hide_code` defaults to `True` in Marimo 0.25.2+):

```python
import marimo._code_mode as cm

async with cm.get_context() as ctx:
    empty_cells = [c.id for c in ctx.cells.values() if not c.code.strip()]
    body = "summary_df = raw_df.group_by('region').len()\nsummary_table = mo.ui.table(summary_df, label='Regional Counts')\nsummary_table"
    if empty_cells:
        target_id = empty_cells[0]
        ctx.edit_cell(target_id, body, hide_code=False, name='summarize_regions')
    else:
        target_id = ctx.create_cell(body, hide_code=False, name='summarize_regions')

    # Cells do not auto-run on create/edit; enqueue run_cell in the same block
    ctx.run_cell(target_id)
```

You can also reposition cells, manage dependencies relative to existing cells (`before` / `after`), and trigger UI widgets programmatically with `ctx.set_ui_value`:

```python
import marimo._code_mode as cm

async with cm.get_context() as ctx:
    cell_ids = list(ctx.cells.keys())
    if len(cell_ids) >= 2:
        ctx.move_cell(cell_ids[-1], after=cell_ids[0])

    # Update a UI slider programmatically and inspect stale downstream cells
    if 'threshold_slider' in ctx.globals:
        ctx.set_ui_value(ctx.globals['threshold_slider'], 0.75)
        for cid, cell in ctx.cells.items():
            if cell.status == 'stale':
                ctx.run_cell(cid)
```

---

## 4. AST Safety Gate Rules & Conflict Recovery

Every mutation committed by `cm.get_context()` must satisfy Marimo's DAG invariants:

1. **Single Variable Definition Rule:** Never assign or import a top-level symbol in two different cells (`MultipleDefinitionError`). Search first with `ctx.cells.find(...)` / `ctx.graph.definitions`.
2. **Cycle Prevention:** Inspect `ctx.graph` before introducing back-edges between producer and consumer cells (`CycleError`).
3. **No Wildcard Imports:** Never emit `from module import *` inside notebook cells.
4. **Setup Cell Imports Rule:** Avoid shadowing or redefining variables already defined in `setup`. Keep shared module imports consolidated in one dedicated cell (or `setup`) rather than duplicating imports across cells.
5. **Delete-and-Create Refactoring:** When splitting or renaming an entangled cell that creates multiple variables or temporary conflicts, enqueue `ctx.delete_cell` followed by `ctx.create_cell` inside one atomic transaction (confirm with the user first before dropping cells whose variables are referenced elsewhere):

```python
import marimo._code_mode as cm

async with cm.get_context() as ctx:
    old_id = 'legacy_cell'
    if old_id in ctx.cells:
        ctx.delete_cell(old_id)
    loader_id = ctx.create_cell(
        "df_loaded = pl.read_parquet('events.parquet')\nmo.stat(label='Rows', value=str(df_loaded.height))",
        hide_code=False,
        name='load_events',
    )
    plot_id = ctx.create_cell(
        "fig = px.histogram(df_loaded.to_pandas(), x='latency_ms', template='plotly_white')\nmo.ui.plotly(fig)",
        after=loader_id,
        hide_code=False,
        name='plot_latency',
    )
    ctx.run_cell(loader_id)
    ctx.run_cell(plot_id)
```

---

## 5. `StaleCellError`, `skip_staleness_check`, Packages & Visual Screenshots

### Optimistic Concurrency (`StaleCellError`)

By default, `cm.get_context()` verifies that notebook cells have not been edited in the browser since your previous read. If another user or browser action modified the notebook mid-flight, exiting the context raises `StaleCellError`. Always catch `cm.StaleCellError`, re-read `ctx.cells`, and only pass `skip_staleness_check=True` when the user explicitly requests forcing an overwrite:

```python
import marimo._code_mode as cm

try:
    async with cm.get_context() as ctx:
        ctx.edit_cell('cell_a', "metric = 42\nmo.md(f'Metric = **{metric}**')")
        ctx.run_cell('cell_a')
except cm.StaleCellError:
    async with cm.get_context(skip_staleness_check=True) as ctx:
        print('Re-reading latest cell version before manual reconciliation:', ctx.cells['cell_a'].code)
```

### Installing & Auditing Packages (`ctx.packages`)

In Marimo 0.25.2+, always use `ctx.packages` (`list`, `add`, `remove`) rather than shelling out to `uv add` or `pip install` (and ask user confirmation if they did not request a dependency change):

```python
import marimo._code_mode as cm

async with cm.get_context() as ctx:
    installed = ctx.packages.list()
    print('Environment packages:', installed[:10])
    # Queued synchronously and installed on context exit:
    ctx.packages.add('polars>=1.22.0')
```

### Live Visual Screenshots (`await ctx.screenshot`)

Use async `await ctx.screenshot(...)` (and close the headless Playwright browser cleanly when finished) to verify charts and layout visually:

```python
import marimo._code_mode as cm

async with cm.get_context() as ctx:
    png_path = await ctx.screenshot(cell_id='plot_latency')
    print('Saved cell screenshot to:', png_path)
    await ctx.close_screenshot_session()
```

### Two-Pass Safe Create-Then-Inspect Verification

Verify runtime errors separately after context exit executes `run_cell`:

```python
import marimo._code_mode as cm

async with cm.get_context() as ctx:
    new_id = ctx.create_cell('x = 1 / 0', hide_code=False)
    ctx.run_cell(new_id)

async with cm.get_context() as ctx:
    for cid, cell in ctx.cells.items():
        if cell.errors:
            print('Verification caught error in', cid, cell.errors)
```

### Read-Only Deep Variable & Rich Representation Audit

Prefer `mo.md(...)`, `mo.ui.table(...)`, and interactive `mo.ui.plotly(...)` / Altair charts over raw `print()` dumps, and inspect rich MIME outputs safely:

```python
import marimo._code_mode as cm

async with cm.get_context() as ctx:
    snapshot = {k: repr(v)[:120] for k, v in ctx.globals.items() if not k.startswith('_') and not callable(v)}
    print(snapshot)
```
