# Antigravity 2.31.2+ MCP Bridge Configuration (`--mcp`)

Marimo `0.25.2+` exposes a live Model Context Protocol (MCP) server on `/mcp/server` (default port `2718`) using **Streamable HTTP**.

> [!WARNING]
> **Antigravity 2.31.2+ Streamable HTTP Config Rule:** Never write a `"transport": "sse"` field inside Antigravity `mcp_config.json` `mcpServers` entries! Legacy SSE transport keys break Streamable HTTP handshakes (`MCP004`) and are rejected by Antigravity 2.31.2+. Always configure only the Streamable HTTP `"url"` field pointing at `/mcp/server`.

---

## 1. `--mcp tools` vs `--mcp code-mode`

Marimo supports two MCP server modes when starting `marimo edit` (in older pre-0.25 builds, `--mcp` had no argument; in Marimo 0.25.2+, pass `tools` or `code-mode`):

| CLI Flag | Exposed Interface | Best Used With |
| :--- | :--- | :--- |
| `--mcp tools` | Exposes structured read/lint tools (`GetMarimoRules`, `GetActiveNotebooks`, `LintNotebook`, etc.) | Read-only inspection + Antigravity shell / `execute-code.sh` pairing |
| `--mcp code-mode` | Exposes MCP-native `marimo._code_mode` execution (`run_python` / context bridge) alongside built-in inspection tools | Gemini 4 Carbon autonomous full-cycle cell inspection & live DAG mutation |
| `--mcp-allow-remote` (`MARIMO_MCP_ALLOW_REMOTE=1`) | Permits connecting over non-loopback interfaces (SSH tunnel, containers, WSL2 bridge) | Remote GPU servers or containerized notebooks behind private networking |

Start a headless pairing server bound to port `2718`:

```bash
# Recommended for Gemini 4 Carbon in Antigravity 2.31.2+:
uv run marimo edit notebook.py --headless --no-token --mcp code-mode --port 2718

# With token authentication or non-loopback hosts:
uv run marimo edit notebook.py --headless --mcp code-mode --mcp-allow-remote --port 2718
```

---

## 2. Antigravity 2.31.2+ `mcp_config.json` Entries

Register the live server in `.gemini/antigravity/mcp_config.json` (workspace or global):

### Standard Local Loopback (Streamable HTTP)

```json
{
  "mcpServers": {
    "marimo": {
      "url": "http://127.0.0.1:2718/mcp/server"
    }
  }
}
```

### Token-Authenticated / Remote Tunnel Endpoint

When running without `--no-token` or behind `--mcp-allow-remote`, pass the Bearer header securely:

```json
{
  "mcpServers": {
    "marimo": {
      "url": "http://127.0.0.1:2718/mcp/server",
      "headers": {
        "Authorization": "Bearer ${MARIMO_TOKEN}"
      },
      "variables": [
        {
          "name": "MARIMO_TOKEN",
          "title": "Marimo Auth Token",
          "description": "Bearer token used to authenticate against a protected Marimo MCP server.",
          "is_secret": true
        }
      ]
    }
  }
}
```

---

## 3. Built-In MCP Inspection Tools & Prompts

When connected to Marimo's MCP server on `/mcp/server`, the following 10 canonical tools are available:

| MCP Tool Name | Primary Purpose | Recommended Workflow Stage |
| :--- | :--- | :--- |
| `GetMarimoRules` | Returns canonical Marimo rules & coding constraints | Session startup / prompt priming |
| `GetActiveNotebooks` | Lists active notebook sessions, file paths, and `session_id` | Target resolution before edits |
| `GetLightweightCellMap` | Fast cell IDs, names, line counts, and previews | Cheap topology mapping |
| `GetCellRuntimeData` | Source code, runtime status, errors, and metadata per cell | Diagnosing failing cells |
| `GetCellOutputs` | Console streams and rich MIME display outputs per cell | Verifying charts, tables, Markdown |
| `GetCellDependencyGraph` | Cell variable definitions, references, parents, and children | Cycle & redefinition prevention |
| `GetTablesAndVariables` | Active in-memory DataFrames, schemas, and variable types | DataFrame profiling without stdout dumps |
| `GetDatabaseTables` | Connected SQL engine / DuckDB / SQLAlchemy catalog metadata | Writing reactive `mo.sql` cells |
| `GetNotebookErrors` | Summarizes syntax, DAG, and runtime errors across cells | Post-mutation health check |
| `LintNotebook` | Runs Marimo static linter rules on the live notebook | Enforcing `MB*` / `MR*` / `MF*` hygiene |

### Built-In MCP Prompts & CLI Docs

Marimo exposes structured MCP prompts — **`ActiveNotebooks`** and **`ErrorsSummary`** (plus Marimo `0.25.2+` local CLI `marimo pair docs`) — for rapid onboarding and diagnostics:

```bash
uv run marimo pair docs gotchas
uv run marimo pair docs notebook-improvements
uv run marimo pair docs rich-representations
```

### Pairing Programmatic `GetCellOutputs` Checks with Code-Mode Scratchpads

Even when MCP provides read telemetry, apply mutations and programmatic checks cleanly with `marimo._code_mode`:

```python
import marimo._code_mode as cm

async with cm.get_context() as ctx:
    cell_map = {cid: {'name': c.name, 'status': c.status} for cid, c in ctx.cells.items()}
    print('Cell map:', cell_map)
```

Verify variable lineage across parent/child edges before calling `edit_cell`:

```python
import marimo._code_mode as cm

async with cm.get_context() as ctx:
    for var_name, defs in ctx.graph.definitions.items():
        if len(defs) > 1:
            print('Duplicate definition conflict:', var_name, defs)
```

Inspect active tabular datasets safely before adding visualization cells:

```python
import marimo._code_mode as cm

async with cm.get_context() as ctx:
    for name, val in ctx.globals.items():
        if hasattr(val, 'schema') and hasattr(val, 'height'):
            print(name, 'rows=', val.height, 'schema=', dict(val.schema))
```
