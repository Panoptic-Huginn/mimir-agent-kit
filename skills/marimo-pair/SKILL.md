---
name: marimo-pair
description: >-
  Live interactive pair-programming skill for Google Antigravity 2.31.2+ (Gemini
  4 Carbon) and running Marimo 0.25.2+ notebooks. Activates when inspecting live
  kernel state, profiling in-memory globals, or driving surgical reactive cell
  mutations through an ephemeral scratchpad via marimo._code_mode, the native
  marimo pair CLI, or Streamable HTTP MCP (--mcp code-mode / --mcp tools).
metadata:
  version: "2.0.0"
  publisher: mimir-agent-kit
---

# Live Interactive Pairing with Marimo 0.25.2+ (`marimo-pair`)

Optimized for **Google Antigravity 2.31.2+**, **Gemini 4 Carbon**, and **Marimo 0.25.2+**.

> [!CRITICAL]
> **Operational Cardinal Rule: Active Kernel is the Source of Truth**
>
> **CRITICAL RUNTIME INVARIANT:** When a `.py` notebook is actively open in a running `marimo edit` server, the live Marimo kernel owns the canonical cell graph and in-memory state. **NEVER** edit the backing `.py` file directly with file-editing tools (`edit_file` / `write_file` / shell `sed`) while a session is active — doing so causes **Disk-Edit Desynchronization**, and any unsynced edits will be **overwritten** by the running server or desync reactive execution! Perform every persistent change through `marimo._code_mode` inside an ephemeral scratchpad, or close the server cleanly before offline refactoring with `/marimo-pro`.

---

## 1. Execution Channels & Script Path Resolution

Choose the appropriate pairing channel for your environment:

1. **Direct CLI (`marimo pair`, Marimo 0.25.2+ built-in):** Native `marimo pair notebook list`, `marimo pair execute --url ... --session ...`, and `marimo pair docs {gotchas|notebook-improvements|rich-representations}`.
2. **Bundled POSIX Scripts (Cross-platform Linux / macOS / WSL2 / SSH fallback):** Resolve `<SKILL_DIR>` to this skill's directory (the directory containing this `SKILL.md`):
   - [scripts/discover-servers.sh](scripts/discover-servers.sh) (`<SKILL_DIR>/scripts/discover-servers.sh`) — Probes `~/.local/state/marimo/servers/` (POSIX / WSL2 + Windows host fallback) and active `/api/sessions` endpoints.
   - [scripts/execute-code.sh](scripts/execute-code.sh) (`<SKILL_DIR>/scripts/execute-code.sh`) — Streams Python scratchpads to `POST /api/kernel/execute` over HTTP/SSE, supporting `--url`, `--session`, `--file`, `--token`, and `--token-file`.
3. **Antigravity 2.31.2 MCP Bridge:** Launch with `marimo edit notebook.py --headless --no-token --mcp code-mode --port 2718` (or `--mcp tools`) and connect via Streamable HTTP at `http://127.0.0.1:2718/mcp/server`.

---

## 2. The 5-Step Safe Code-Mode Workflow

1. **Discover Active Server & Stable `session_id`:**
   Use `marimo pair notebook list` or `<SKILL_DIR>/scripts/discover-servers.sh`:

   ```bash
   # Native Marimo 0.25.2 CLI
   uv run marimo pair notebook list

   # Or bundled discovery script (includes WSL2 Windows host fallback)
   bash <SKILL_DIR>/scripts/discover-servers.sh
   ```

   Always bind to the `session_id` returned by discovery (it persists across browser reloads and file renames). If multiple sessions exist for the same notebook, ask the user before selecting one. If no session appears, remind the user to open the notebook URL in a browser tab so the kernel instantiates.
2. **Inspect Kernel State (Read-Only Scratchpad):**
   Query `ctx.cells`, `ctx.graph`, and `ctx.globals` before mutating anything:

   ```bash
   bash <SKILL_DIR>/scripts/execute-code.sh --url http://127.0.0.1:2718 --session "$SESSION_ID" --code-file - <<'PY'
   import marimo._code_mode as cm

   async with cm.get_context() as ctx:
       for cid, cell in ctx.cells.items():
           print(cid, cell.name, cell.status, len(cell.errors))
       print("Globals:", sorted(k for k in ctx.globals.keys() if not k.startswith("_")))
   PY
   ```

3. **Plan AST-Safe Cell Topology (Zero Redefinitions, Zero Cycles):**
   Respect **Single Variable Definition Rule**, **Cycle Prevention**, **No Wildcard Imports**, and reuse existing empty cells with `ctx.edit_cell` before creating new cells.
4. **Mutate & Explicitly Run Cells (`ctx.run_cell`):**
   Cells do **not** auto-execute on `create_cell` or `edit_cell`. Enqueue `ctx.run_cell(cid)` inside the same `async with cm.get_context() as ctx:` block so Marimo flushes the mutation and executes its reactive DAG on context exit.
5. **Verify Execution Status, Errors & Outputs:**
   Run a follow-up read-only scratchpad inspecting `cell.status`, `cell.errors`, `cell.output`, `cell.console_outputs`, or `await ctx.screenshot(cell_id=cid)` when visually verifying plots and UI widgets.

---

## 3. Non-Negotiable Scratchpad & `marimo._code_mode` Rules

1. **Scratchpad-Only Import Rule:** `import marimo._code_mode as cm` runs **exclusively** inside ephemeral scratchpads sent via `execute-code.sh` or `marimo pair execute`. **NEVER** place `import marimo._code_mode` inside a persistent cell created with `ctx.create_cell` or `ctx.edit_cell`.
2. **Use `async with cm.get_context() as ctx:` — NEVER `asyncio.run(...)`:** The scratchpad runner already executes inside a live async event loop. Always enter `async with cm.get_context() as ctx:`.
3. **Do NOT `await` Queued `ctx` Mutation Methods:** `ctx.create_cell`, `ctx.edit_cell`, `ctx.delete_cell`, `ctx.move_cell`, `ctx.run_cell`, `ctx.packages.add`, and `ctx.set_ui_value` are **synchronous** methods that enqueue operations onto the context transaction and commit atomically on `__aexit__`. Only `await cm.get_context()`, `await ctx.screenshot(...)`, and `await ctx.close_screenshot_session()` are async coroutines.
4. **Raw Cell Body Rule:** Pass **only raw, unindented Python statements** inside the code string to `ctx.create_cell(code)` and `ctx.edit_cell(cid, code)`. Do **NOT** wrap cell strings in `@app.cell`, `def _(...):`, `return (...)`, or indentation.
5. **Visual Display Output Rule:** In persistent cells whose purpose is visual display (charts, tables, widgets, Markdown), end the raw cell code with a **bare, unindented final expression** (e.g., `mo.vstack([chart, summary])`), never a silent assignment alone and never `return mo.md(...)`.
6. **`setup` Cell Imports Rule:** When an import should be shared across cells, use **`with app.setup:`** (or a single dedicated setup/import cell) — never place module-level imports outside `@app.cell` / `app.setup` via disk hacks. Do **not** overwrite existing `setup` definitions implicitly; inspect `ctx.cells["setup"]` first if modifying imports.
7. **Visible Code by Default When Authoring (`hide_code=False`):** In Marimo 0.25.2+, `ctx.create_cell(code)` defaults to `hide_code=True`! Pass `hide_code=False` when creating analysis cells the user expects to read and edit in the notebook UI.
8. **Confirm Destructive / Env Changes:** Ask before calling `ctx.delete_cell` (drops downstream variables) or `ctx.packages.add` (modifies project environment; prefer `ctx.packages.add` over shell `uv add` / `pip`).

---

## 4. Deep Reference Modules

Load only the specific reference needed for your current pairing step:

- **[Code-Mode Context API & Safe AST Mutations](references/code_mode_api.md)** — Full Marimo 0.25.2+ `AsyncCodeModeContext` reference (`ctx.cells.find`/`grep`, `ctx.globals`, `ctx.graph`, `ctx.packages`, `ctx.find_cell_defining_object`, `StaleCellError`, `Delete-and-Create` refactoring, rich representations, and screenshots).
- **[Antigravity 2.31.2 MCP Bridge Configuration](references/mcp_bridge_configuration.md)** — Streamable HTTP `mcp_config.json` setup on port `2718` (`/mcp/server`), `--mcp code-mode` vs `--mcp tools`, `--mcp-allow-remote`, all 10 built-in MCP inspection tools (`GetMarimoRules`, `LintNotebook`, etc.), and `marimo pair docs`.
- **[Session Discovery, Auth & Troubleshooting](references/session_targeting_troubleshooting.md)** — Token authentication (`--token-file`), WSL2 / SSH remote tunneling, `StaleCellError` recovery, `molab` / multi-session ambiguity, and fixing Disk-Edit Desynchronization.

---

## 5. Related Skills & Operational Boundaries

- **Do not use this skill when** scaffolding or writing new Marimo `.py` notebooks **from scratch** offline — use `/marimo-pro` instead, then transition to `/marimo-pair` once the live kernel session is running.
- Pair `/marimo-pair` with **`/python-pro`** for type-safe Python 3.14+ refactoring, and commit/open PRs strictly via **`/github-flow-lifecycle`** after closing any live server session cleanly.
