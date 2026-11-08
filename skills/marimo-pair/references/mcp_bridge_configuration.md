# marimo Model Context Protocol (MCP) Bridge Configuration

This reference details the streamable HTTP Model Context Protocol (MCP) server provided by `marimo[mcp]` (v0.21.1+ / v0.25.2+), its integration with Google AntiGravity 2.29.0+, and the schemas for its 10 inspection and debugging tools.

---

## 1. Overview of the marimo MCP Bridge

When marimo runs with MCP support enabled, it exposes a native Starlette streamable HTTP MCP server:
- **Server Endpoint**: `http://localhost:<PORT>/mcp/server` (default: `http://localhost:2718/mcp/server`)
- **Protocol**: JSON-RPC 2.0 over Server-Sent Events (SSE) and HTTP POST.
- **Authentication**: Uses `edit` scope session authorization. When started with `--no-token`, unauthenticated local connections are accepted.

---

## 2. Launching marimo with MCP Enabled

Install marimo with the `mcp` extra:

```bash
# Using uv
uv add "marimo[mcp]>=0.21.1"

# Ad-hoc launch without installation
uvx --with="marimo[mcp]" marimo edit notebook.py --mcp --no-token
```

```bash
# Using pixi (pixi.toml)
[dependencies]
marimo = ">=0.21.1"

[pypi-dependencies]
mcp = ">=2.0.0,<3"
httpx2 = ">=2.5.0,<3"
```

Start the editor with `--mcp`:
```bash
marimo edit notebook.py --mcp --no-token
```

---

## 3. Google AntiGravity MCP Configuration

### 3.1 Static Configuration (`mcp_config.json`)

To register the running marimo notebook as an MCP server within Google AntiGravity workspaces, add an entry to your workspace `mcp_config.json`:

```json
{
  "mcpServers": {
    "marimo-notebook": {
      "url": "http://127.0.0.1:2718/mcp/server",
      "transport": "sse"
    }
  }
}
```

If authentication is enabled, pass the token as a Bearer header:

```json
{
  "mcpServers": {
    "marimo-notebook": {
      "url": "http://127.0.0.1:2718/mcp/server",
      "transport": "sse",
      "headers": {
        "Authorization": "Bearer ${MARIMO_TOKEN}"
      }
    }
  }
}
```

### 3.2 Programmatic Configuration via Google AntiGravity SDK

```python
from google.antigravity import Agent, LocalAgentConfig, types

config = LocalAgentConfig(
    mcp_servers=[
        types.McpStreamableHttpServer(
            name='marimo-notebook',
            url='http://127.0.0.1:2718/mcp/server',
            headers={'Authorization': 'Bearer ...'} if token else {},
        )
    ]
)
agent = Agent(config=config)
```

---

## 4. MCP Tool Specifications (10 Tools)

The marimo MCP server registers 10 structured tools allowing autonomous agents to query notebook state without executing ad-hoc scratchpad scripts:

### 1. `GetMarimoRules`
- **Purpose**: Returns the core reactive principles and syntax rules enforced by marimo's compiler.
- **Input Parameters**: None.
- **Output**: Markdown string summarizing DAG requirements, Single Definition Rule, and cell encapsulation.
- **When to Use**: Call during session initialization to calibrate agent instructions to the live kernel.

### 2. `GetActiveNotebooks`
- **Purpose**: Lists all open notebook files, active session IDs, and kernel statuses.
- **Input Parameters**: None.
- **Output**: JSON array of `{ "session_id": str, "path": str, "status": str }`.
- **When to Use**: Call when multiple notebooks are hosted on the same server to resolve the target `session_id`.

### 3. `GetLightweightCellMap`
- **Purpose**: Provides a compact index of all cells in the notebook.
- **Input Parameters**:
  - `session_id` (`str`, optional): Target session ID.
- **Output**: JSON mapping of cell IDs to their names, line ranges, and execution states.
- **When to Use**: Call to quickly understand the document layout without downloading full cell code and outputs.

### 4. `GetCellRuntimeData`
- **Purpose**: Retrieves full code, execution timings, and defined variable names for specified cells.
- **Input Parameters**:
  - `cell_ids` (`list[str]`, optional): Specific cell IDs to inspect. If omitted, returns all cells.
  - `session_id` (`str`, optional): Target session ID.
- **Output**: JSON array of cell metadata objects including `.code`, `.status`, and runtime metrics.
- **When to Use**: Call before editing a cell to inspect its exact source code and runtime status.

### 5. `GetCellOutputs`
- **Purpose**: Fetches rendered outputs (stdout, HTML, SVG plots, markdown representations) for cells.
- **Input Parameters**:
  - `cell_ids` (`list[str]`): Target cell IDs.
  - `session_id` (`str`, optional): Target session ID.
- **Output**: JSON array of output structures and mime types.
- **When to Use**: Verify that visual plots or data summary tables rendered correctly after code execution.

### 6. `GetCellDependencyGraph`
- **Purpose**: Returns the complete topological Directed Acyclic Graph (DAG) for the notebook.
- **Input Parameters**:
  - `session_id` (`str`, optional): Target session ID.
- **Output**: Graph representation containing:
  - `cells`: Dict of cell nodes with `defs` (defined variables) and `refs` (referenced variables).
  - `edges`: Parent $\to$ child dependency pairs.
  - `cycles`: List of detected circular dependency cycles (empty if DAG is valid).
- **When to Use**: Diagnose dependency order, identify upstream ancestors, or isolate downstream impact before editing a cell.

### 7. `GetTablesAndVariables`
- **Purpose**: Inspects live variables in kernel memory, focusing on dataframes (Pandas, Polars, PyArrow), schema types, row/column counts, and summary statistics.
- **Input Parameters**:
  - `session_id` (`str`, optional): Target session ID.
- **Output**: JSON summary of variables, types, shapes, and column schemas.
- **When to Use**: Inspect data structures in memory without manually printing `df.info()` or `df.columns` in the scratchpad.

### 8. `GetDatabaseTables`
- **Purpose**: Queries attached SQL databases (DuckDB, SQLite, PostgreSQL) accessible within the notebook.
- **Input Parameters**:
  - `session_id` (`str`, optional): Target session ID.
- **Output**: List of attached database schemas, tables, and column data types.
- **When to Use**: Assist in authoring SQL cells (`mo.sql(...)`) against in-memory DuckDB tables.

### 9. `GetNotebookErrors`
- **Purpose**: Aggregates all current errors across the notebook, including compile-time name collisions, syntax errors, and runtime exceptions.
- **Input Parameters**:
  - `session_id` (`str`, optional): Target session ID.
- **Output**: Array of error records with `cell_id`, error category, and full traceback.
- **When to Use**: Call immediately after cell mutations to verify that the notebook executed cleanly with zero errors.

### 10. `LintNotebook`
- **Purpose**: Runs marimo's reactive static analysis and linting engine over the notebook.
- **Input Parameters**:
  - `session_id` (`str`, optional): Target session ID.
- **Output**: List of lint findings: unused variables, undeclared global references, cell-private naming recommendations (`_`).
- **When to Use**: Quality-assurance check before finalizing a pair programming task.

---

## 5. Registered MCP Prompts (2 Prompts)

In addition to tools, the marimo MCP server exposes 2 standardized prompts:

1. **`ActiveNotebooks`**:
   Generates a prompt context containing high-level metadata of all open notebooks on the server.
2. **`ErrorsSummary`**:
   Generates a focused diagnostic prompt detailing all broken cells, exceptions, and suggested remediation steps.

---

## 6. Pairing via MCP vs. Shell Scripts

| Dimension | MCP Server (`/mcp/server`) | Portability Scripts (`execute-code.sh`) |
|---|---|---|
| **Installation** | Requires `marimo[mcp]` extra | Works on any core `marimo` install (v0.21.1+) |
| **Agent Interface** | Native tool calls (`GetCellRuntimeData`, etc.) | Bash execution via `run_command` |
| **Code Execution** | Inspection tools; code execution requires scratchpad | Arbitrary Python evaluation & `cm.get_context()` |
| **Best Used For** | Fast read-only inspection, DAG analysis, linting | Dynamic code changes, exploratory analysis |

**Recommended Agent Strategy**:  
Use MCP inspection tools (`GetNotebookErrors`, `GetTablesAndVariables`, `GetCellDependencyGraph`) when connected to an MCP server, and use `execute-code.sh` with `marimo._code_mode` to stage and commit code modifications.

---

## 7. Cross References

- For programmatic context mutations, see [Code Mode API](code_mode_api.md).
- For targeting multi-session servers and resolving connection issues, see [Session Targeting and Troubleshooting](session_targeting_troubleshooting.md).
- Return to the main skill manual at [Skill Entrypoint](../SKILL.md).
