---
name: marimo-pair
description: "Drive live marimo reactive notebook sessions as an interactive workspace: execute scratchpad Python in running kernels, inspect in-memory variables and DAG states, and commit durable notebook changes via marimo._code_mode."
metadata:
  version: v1
  publisher: jamielapointe
---

You are an expert in live interactive pair programming and copilot orchestration with **Marimo** reactive Python notebooks (v0.21.1+ / v0.25.2+), operating within **Google AntiGravity 2.29.0+** targeting **Gemini 4 Argon** and **Gemini 4 Carbon** reasoning engines. You specialize in attaching to running marimo kernels, interrogating in-memory datasets and model states via ephemeral scratchpad execution, performing atomic cell mutations through the private `marimo._code_mode` API, and integrating with the streamable HTTP Model Context Protocol (MCP) server.

---

## ⚠️ Operational Cardinal Rule: Active Kernel is the Source of Truth

> **CRITICAL RUNTIME INVARIANT**:
> When a marimo session is actively running, **the in-memory kernel runtime is the sole authoritative source of truth**.
> **DO NOT** edit the notebook's underlying `.py` file directly on disk using filesystem tools (`replace_file_content`, `write_to_file`) while a pairing session is active.
> Direct filesystem edits **fail to reach the live kernel**, do not update the browser UI, and **will be silently overwritten and erased** the next time the notebook auto-saves or the user edits a cell.
> All live code modifications must be committed transactionally through `marimo._code_mode` or the `/api/kernel/execute` endpoint.

---

## Related Skills

- **`/marimo-pro`**: Master static marimo notebook file authoring on disk (`*.py`), complex Directed Acyclic Graph (DAG) architecture, `mo.ui` interactive widget catalogs, `mo.state`, embedded `pytest` test discovery, and headless WASM export.
- **`/python-pro`**: Modern Python 3.14+ engineering, PEP 621 / PEP 723 packaging standards, `uv` workflows, and strict `ruff` and `mypy` configurations.
- **`/github-flow-lifecycle`**: End-to-end Git feature branching, issue linking, local CI verification gates, and pull request workflows.

---

## Use this skill when

- Pairing interactively with a live, running marimo notebook server (`marimo edit`).
- Inspecting dataframes, matrices, tensors, and models residing in kernel RAM without polluting notebook state.
- Interrogating the runtime Directed Acyclic Graph (DAG) to diagnose cell dependencies, ancestors, descendants, and variable ownership.
- Programmatically adding, modifying, reordering, deleting, or re-executing notebook cells via `marimo._code_mode`.
- Interfacing with marimo's streamable HTTP Model Context Protocol (MCP) server on `/mcp/server`.
- Troubleshooting out-of-sync kernels, `StaleCellError`, circular dependencies, or duplicate variable definition errors during interactive pairing.

## Do not use this skill when

- Authoring brand-new reactive marimo notebooks from scratch on disk without an active kernel session (use `/marimo-pro` instead).
- Working with legacy linear Jupyter notebooks (`*.ipynb`) or Google Colab environments (use `/jupyter-pro` instead).
- Writing standalone non-notebook Python applications, microservices, or CLI packages (use `/python-pro` instead).

---

## 1. Environment Setup & Starting Pairable Sessions

The pair-programming engine and `marimo._code_mode` module ship natively within core `marimo>=0.21.1`. No external PyPI packages are needed for pairing.

### Toolchain Installation
```bash
# Using uv (recommended)
uv add "marimo>=0.21.1"

# For native HTTP MCP server support
uv add "marimo[mcp]>=0.21.1"
```

```toml
# Using pixi (pixi.toml)
[dependencies]
marimo = ">=0.21.1"

[pypi-dependencies]
mcp = ">=2.0.0,<3"
```

### Launching the Server
To enable automated agent discovery and script pairing, start the notebook with `--no-token`:

```bash
# Standard interactive pairing session
marimo edit notebook.py --no-token

# With PEP 723 sandboxing (strongly recommended for self-contained notebooks)
marimo edit notebook.py --no-token --sandbox

# With native HTTP MCP server enabled on /mcp/server
marimo edit notebook.py --no-token --mcp
```

> **IMPORTANT**: The marimo server must have an active browser tab open. If started in headless mode without an active browser connection, the session registry will have zero active kernel sessions.

---

## 2. Pairing Protocol: Step-by-Step Workflow

Autonomous pair programming with marimo follows a strict four-step lifecycle:

```
[ 1. Discovery ]       Find active servers: ./scripts/discover-servers.sh
       │
       ▼
[ 2. Handshake ]       Inspect kernel API: help(cm) via execute-code.sh
       │
       ▼
[ 3. Scratchpad ]      Interrogate live variables & test logic (read-only)
       │
       ▼
[ 4. Code Mode ]       Commit atomic cell changes: async with cm.get_context()
```

### Step 1: Server and Session Discovery
Discover active server ports and open notebook sessions using the bundled helper script:

```bash
./scripts/discover-servers.sh --json
```

The script inspects `$XDG_STATE_HOME/marimo/servers/*.json` (or `~/.local/state/marimo/servers/`), tests PID liveness and `/health`, and queries `/api/sessions` to return active server URLs and session IDs.

### Step 2: The Mandatory Inspection Handshake
Before issuing mutations, always run a scratchpad command to inspect the live kernel's `_code_mode` API:

```bash
./scripts/execute-code.sh -c "import marimo._code_mode as cm; help(cm)"
```

This guarantees the agent verifies the exact method signatures and parameters supported by the running marimo version.

### Step 3: Ephemeral Scratchpad Interrogation
When exploring data, testing hypotheses, or validating calculations, execute arbitrary Python code directly in the scratchpad:

```bash
./scripts/execute-code.sh -c "print(df.shape); print(df.columns); print(df.describe())"
```

- **Ephemeral Execution**: The code executes in a shallow copy of the active kernel namespace.
- **Zero Pollution**: Scratchpad assignments (e.g. `tmp = ...`) are wiped after execution and never appear in the notebook canvas or `.py` file.
- **Streaming Output**: Stdout and stderr stream directly back to the agent via Server-Sent Events (SSE).

### Step 4: Durable Mutations via `marimo._code_mode` (`cm`)
When code is verified and ready to be added to the notebook, wrap changes inside `async with cm.get_context() as ctx:`:

```bash
./scripts/execute-code.sh - <<'PY'
import marimo._code_mode as cm

async with cm.get_context() as ctx:
    # 1. Inspect existing cells
    print("Existing cell IDs:", list(ctx.cells.keys()))

    # 2. Queue cell creation
    cid = ctx.create_cell(
        code="import polars as pl\nfiltered_df = df.filter(pl.col('val') > 0)",
        name="filter_positive_values",
        hide_code=False,
    )

    # 3. Queue execution of the new cell
    ctx.run_cell(cid)
PY
```

---

## 3. Core `marimo._code_mode` Rules & Operations

### The Scratchpad-Only Import Rule
> **MANDATORY**: `import marimo._code_mode as cm` must **ONLY** be called within scratchpad execution blocks.
> **NEVER** insert `import marimo._code_mode` into permanent notebook cell code. Doing so creates invalid self-modifying cells that break the reactive DAG compiler.

### Operations Reference
All mutations are staged in-memory on the context object (`ctx`):

1. **`ctx.create_cell(code, name=None, hide_code=True, before=None, after=None)`**:
   Stages creation of a new cell and returns its unique cell ID. Creation is structural only; call `ctx.run_cell(cid)` to execute.
2. **`ctx.edit_cell(target, code=None, name=None, hide_code=None)`**:
   Stages source code edits for an existing cell identified by ID or name. Call `ctx.run_cell(target)` to trigger reactive re-execution.
3. **`ctx.delete_cell(target)`**:
   Stages deletion of a cell. When committed, all variables defined by that cell are scrubbed from kernel RAM, and downstream dependents are re-computed.
4. **`ctx.move_cell(target, before=None, after=None)`**:
   Reorders cell display position in the document without affecting topological execution order.
5. **`ctx.run_cell(target)`**:
   Schedules execution for a created or modified cell.
6. **`ctx.packages.add(pkg)` / `ctx.packages.remove(pkg)`**:
   Installs or removes dependencies, updating PEP 723 inline script metadata when running with `--sandbox`.
7. **`ctx.set_ui_value(element, val)`**:
   Updates `mo.ui` widget state, firing reactive propagation downstream.

### Concurrency & `StaleCellError` Handling
If a cell was modified in the browser UI between the time the agent read it and attempted to edit it, marimo raises `StaleCellError` to prevent silent overwrites:

- Always read `ctx.cells[cid].code` immediately before editing.
- Catch `cm.StaleCellError`, reconcile conflicts against the latest cell source, and re-attempt.
- Use `cm.get_context(skip_staleness_check=True)` only when forced overwrite is explicitly required.

### AST Compilation Safety Gate
When `async with cm.get_context() as ctx:` exits, marimo compiles ASTs and validates:
- **Single Definition Rule**: A public variable name cannot be defined in multiple cells.
- **No Cycles**: No circular dependency chains allowed in the DAG.
- **No Wildcard Imports**: `from module import *` is strictly forbidden.
- **The Delete-and-Create Trap**: Avoid deleting cell `A` (defining `x`) and creating cell `B` (defining `x`) in the same block. Use `ctx.edit_cell()` instead, or pass `skip_validation=True`.

---

## 4. HTTP Streamable MCP Server Integration

When launched with `--mcp`, marimo exposes a streamable HTTP Model Context Protocol (MCP) server at:
```
http://localhost:2718/mcp/server
```

### Registered Tools (10 Tools)
1. **`GetMarimoRules`**: Retrieves core reactive graph rules and principles.
2. **`GetActiveNotebooks`**: Lists all running notebooks and session IDs.
3. **`GetLightweightCellMap`**: Returns compact mapping of cell IDs, names, and states.
4. **`GetCellRuntimeData`**: Retrieves code, execution status, and defined variables for cells.
5. **`GetCellOutputs`**: Retrieves rendered HTML, charts, tables, and console streams.
6. **`GetCellDependencyGraph`**: Maps DAG ancestors, descendants, variable ownership, and cycles.
7. **`GetTablesAndVariables`**: Inspects runtime dataframes, column schemas, types, and summary statistics.
8. **`GetDatabaseTables`**: Inspects attached DuckDB, SQLite, or SQL database tables.
9. **`GetNotebookErrors`**: Aggregates all compile-time, cycle, and runtime exceptions.
10. **`LintNotebook`**: Runs marimo's reactive static analysis and linter on all cells.

### Registered Prompts (2 Prompts)
- **`ActiveNotebooks`**: System prompt summarizing open notebooks and active states.
- **`ErrorsSummary`**: Focused diagnostic prompt analyzing all notebook errors.

---

## 5. Bundled Portability Scripts

The skill provides two standalone executable bash scripts in `scripts/`:

- **`scripts/discover-servers.sh`**: Scans `$XDG_STATE_HOME/marimo/servers/` (`~/.local/state/marimo/servers/`), verifies process liveness and `/health`, and outputs structured JSON of active servers and sessions.
  ```bash
  ./scripts/discover-servers.sh [--json | --text | --clean-stale]
  ```

- **`scripts/execute-code.sh`**: Connects to the marimo SSE endpoint (`POST /api/kernel/execute`) to stream scratchpad commands or code-mode transactions directly to the live kernel.
  ```bash
  ./scripts/execute-code.sh [--url URL] [--file PATH | --session ID] [-c "code" | --code-file FILE | -]
  ```

---

## 6. Detailed Reference Manuals

For in-depth operational procedures, consult the modular reference guides in `references/`:

- [Code Mode API Specification](references/code_mode_api.md): In-depth guide to `marimo._code_mode`, AST safety checks, context manager options, UI state injection, and `StaleCellError` prevention.
- [MCP Bridge Configuration](references/mcp_bridge_configuration.md): Complete setup for `marimo edit --mcp`, AntiGravity `mcp_config.json`, and all 10 MCP tool schemas.
- [Session Targeting & Troubleshooting](references/session_targeting_troubleshooting.md): Multi-session targeting, PEP 723 `--sandbox` isolation, recovery from desynchronized kernels, and common gotchas.
