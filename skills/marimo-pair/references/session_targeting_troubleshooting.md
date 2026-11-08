# Session Targeting, Sandboxing & Troubleshooting

This guide covers session discovery mechanics, environment isolation via `--sandbox`, and troubleshooting procedures for common runtime anomalies encountered when pairing with live marimo notebooks.

---

## 1. Multi-Session Discovery & Targeting

### 1.1 Local Server Registration
When a marimo server starts with `--no-token`, it automatically writes its connection metadata to a JSON file inside the user's state directory:
- **Linux / macOS**: `${XDG_STATE_HOME:-~/.local/state}/marimo/servers/<id>.json`
- **Windows**: `%USERPROFILE%\.marimo\servers\<id>.json`
- **WSL2**: Bridged through `%USERPROFILE%` via `/mnt/c/Users/...`

Each registration record contains:
```json
{
  "pid": 48210,
  "port": 2718,
  "host": "127.0.0.1",
  "version": "0.25.2",
  "started_at": 1731000000.0,
  "token": ""
}
```

If the server is started **with an authentication token** (the default when `--no-token` is omitted), the server details are omitted from the auto-discovery registry to protect session security. In this mode, the agent must be explicitly provided the server URL and token via `--url` and `--token` (or `MARIMO_TOKEN` environment variable).

### 1.2 Target Disambiguation
When multiple marimo notebooks or servers run concurrently on the same machine, the agent must unambiguously specify the target notebook.

#### Option A: Auto-Discovery via Script
```bash
# Discover all running servers and open sessions
./scripts/discover-servers.sh --text
```

#### Option B: Target by Notebook Filepath
```bash
./scripts/execute-code.sh --file analysis_notebook.py -c "print(df.shape)"
```
The script queries `GET /api/sessions` on `http://127.0.0.1:2718`, maps file paths to active session IDs, and selects the matching session.

#### Option C: Target by Explicit Session ID and URL
```bash
./scripts/execute-code.sh --url http://127.0.0.1:2718 --session s_982ab1f4 -c "print(1 + 1)"
```

---

## 2. Environment Isolation & PEP 723 Sandboxing

### 2.1 The `--sandbox` Flag
Modern marimo notebooks support PEP 723 inline script metadata declared in the top header:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "polars>=1.0.0",
#     "altair>=5.0.0",
#     "pyarrow>=15.0.0",
# ]
# ///
```

When launching marimo:
```bash
marimo edit notebook.py --sandbox --no-token
```

- **With `--sandbox`**: Marimo provisions an isolated virtual environment (using `uv` or `pixi`) pinned strictly to the dependencies listed in the script header. Any packages added via `ctx.packages.add(...)` are installed into this environment and automatically recorded back into the header.
- **Without `--sandbox`**: Marimo executes inside whatever Python environment is currently active in the shell, ignoring the inline dependency header. This frequently causes `ModuleNotFoundError` if dependencies differ.

### 2.2 Mid-Session Package Caching Quirks
Certain libraries (notably `polars` and `pyarrow`) perform one-time import caching upon initial load. If `polars` was imported into the kernel *before* `pyarrow` was installed via `ctx.packages.add("pyarrow")`, calling `df.to_pandas()` may fail with:

```text
ModuleNotFoundError: pa.Table requires 'pyarrow'
```

#### Patching the Cache in Scratchpad:
Execute the following monkey-patch snippet in the scratchpad to re-link Polars to the newly installed PyArrow runtime:

```python
import polars.dataframe.frame as _f
import pyarrow as _pa

_f.pa = _pa
```

---

## 3. Troubleshooting & Recovery Procedures

### 3.1 The Disk-Edit Desynchronization Trap
> **PROBLEM**: An agent or human directly modified the `.py` notebook file on disk while the marimo server was actively running.  
> **SYMPTOMS**:
> - The live browser canvas does not reflect the disk edits.
> - The next time the user or kernel saves, the changes on disk are **completely overwritten and lost**.

#### Recovery Steps:
1. **Cease Direct Disk Edits**: Never use `write_to_file` or `replace_file_content` on an active notebook `.py` file.
2. **Reload from Disk in the UI**: In the browser UI, select `File -> Reload from file` (or start the server with `--watch`).
3. **If Desynchronized**: Copy the desired changes into a scratchpad script and apply them programmatically through `marimo._code_mode`:
   ```python
   import marimo._code_mode as cm

   async with cm.get_context() as ctx:
       ctx.edit_cell('target_cell', code='desired_code')
       ctx.run_cell('target_cell')
   ```

### 3.2 The Empty Sessions Trap (`--headless`)
> **PROBLEM**: Running `./scripts/execute-code.sh` fails with:
> `Error: No active sessions found on http://127.0.0.1:2718. Marimo requires an active browser session to evaluate kernel code.`

#### Cause:
The server was started with `marimo edit --headless` (or the browser tab was closed). Marimo instantiates kernel runtimes lazily upon client connection; a server without connected web clients has zero active kernel sessions.

#### Solution:
Open the notebook URL (e.g. `http://localhost:2718`) in a browser tab. Once the WebSocket connects, the session is registered in `/api/sessions` and execution will succeed.

### 3.3 Private Variable Scoping (`_` Prefix)
> **PROBLEM**: Cell B attempts to access `_cleaned_data` defined in Cell A and fails with `NameError: name '_cleaned_data' is not defined`.

#### Cause:
In marimo, variables starting with an underscore are strictly cell-private: they are not exported to the DAG or other cells.

#### Solution:
Remove the leading underscore (`cleaned_data = ...`) if the variable must be consumed downstream, or merge the logic into a single cell.

### 3.4 Resolving DAG Cycles and Duplicate Definitions
> **PROBLEM**: Code mode transaction rejected on exit with:
> `marimo.core.ast_compact.CycleError: Circular dependency detected`
> or `Multiply-defined names: df`.

#### Solution:
1. Use `ctx.graph` to inspect cell dependencies:
   ```python
   import marimo._code_mode as cm

   async with cm.get_context() as ctx:
       for cid, node in ctx.graph.cells.items():
           print(f'Cell {cid} ({ctx.cells[cid].name}): defs={node.defs}, refs={node.refs}')
   ```
2. For duplicate definitions: Rename the variable in one of the cells (e.g. `raw_df` vs `processed_df`), or combine both transformations into a single cell function.
3. For cycles: Break the feedback loop by passing intermediate values or using `mo.state` for intentional iterative algorithms.

---

## 4. Cross References

- For the complete API of `marimo._code_mode`, see [Code Mode API](code_mode_api.md).
- For MCP server tools and AntiGravity configuration, see [MCP Bridge Configuration](mcp_bridge_configuration.md).
- Return to the main skill manual at [Skill Entrypoint](../SKILL.md).
