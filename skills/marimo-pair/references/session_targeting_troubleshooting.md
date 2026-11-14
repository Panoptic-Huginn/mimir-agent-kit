# Session Discovery, Authentication & Troubleshooting

Use this guide to resolve session targeting, Bearer tokens, remote WSL2/SSH discovery, **Disk-Edit Desynchronization**, and optimistic locking conflicts in **Marimo 0.25.2+**.

---

## 1. Preventing & Recovering from Disk-Edit Desynchronization

**Disk-Edit Desynchronization** occurs when an external tool (`edit_file`, `sed`, `git checkout`) modifies a `.py` notebook file while `marimo edit` holds an active kernel session in memory. Because the browser + server continuously reconcile cell buffers against kernel memory, direct disk edits are routinely **overwritten** on save or trigger silent runtime state divergence.

### Recovery Procedure

1. **Do NOT retry disk edits.** Check running servers using `marimo pair notebook list` or `<SKILL_DIR>/scripts/discover-servers.sh`.
2. **Re-read authoritative kernel cells** via `marimo._code_mode` (`ctx.cells`) — never trust stale disk file contents over live `ctx.cells[cid].code`.
3. **If disk changes must take precedence** (e.g., `git pull` / external refactor), instruct the user to save/close the active Marimo tab (`Ctrl+C` on `marimo edit`), apply disk edits, and relaunch `marimo edit`.

```python
import marimo._code_mode as cm

async with cm.get_context() as ctx:
    # Dump authoritative kernel code before deciding whether to reconcile
    for cid, cell in ctx.cells.items():
        print(f"--- {cid} ({cell.name}) ---")
        print(cell.code)
```

---

## 2. Local Server Registration & Discovering Active Sessions

Marimo publishes **Local Server Registration** JSON manifests under `$XDG_STATE_HOME/marimo/servers/` (`$HOME/.local/state/marimo/servers/server_<pid>.json`) whenever a server starts — including local headless `--no-token` sessions (`marimo edit nb.py --headless --no-token`) and `--sandbox` PEP 723 isolated notebooks (`marimo edit --sandbox nb.py`).

- **POSIX / Local macOS & Linux:** Run `uv run marimo pair notebook list` or `bash <SKILL_DIR>/scripts/discover-servers.sh`.
- **PEP 723 Sandbox Sessions (`--sandbox`):** Ensure `discover-servers.sh` targets the server running inside the ephemeral `uv` sandbox; inspect the server's registered port and active `session_id` before executing scratchpads.
- **WSL2 + Windows Native Browser Server:** `discover-servers.sh` automatically inspects `/mnt/c/Users/<user>/.local/state/marimo/servers` alongside `$HOME/.local/state/marimo/servers`, normalizes `/api/sessions` (supporting `{id: {path, filename}}`, `{id: "path"}`, `{sessions: [...]}`, and array schemas), and emits unified JSON.
- **No Active Sessions Returned (`[]`):** Marimo launches kernels lazily when a browser client connects! Even if `http://127.0.0.1:2718` responds `200 OK` on `/api/status`, `/api/sessions` remains empty until a browser tab opens the notebook URL. Ask the user to open the notebook link in their browser, then re-run discovery.
- **Target Stability Rule:** Always pass the immutable `session_id` (`--session <ID>`) after discovery — it stays stable across browser page reloads and file renames. Only re-discover if Marimo reports an unknown session because the notebook tab was closed or restarted. Never switch sessions blindly after a transient `401` / network timeout.

---

## 3. Authentication Tokens (`--token`, `--token-file`, `MARIMO_TOKEN`)

When a server runs without `--no-token`, authenticate cleanly without exposing secrets in shell history or prompts:

- **Native CLI (`marimo pair`):** Pass `--token-file /path/to/token.txt` (pass the file path, not file contents!). Generate one interactively with `marimo pair prompt --url http://127.0.0.1:2718 --with-token`.
- **Bundled `execute-code.sh`:** Accepts `--token-file <PATH>`, `--token <TOKEN>`, or `MARIMO_TOKEN` environment variable:

```bash
bash <SKILL_DIR>/scripts/execute-code.sh \
    --url http://127.0.0.1:2718 \
    --token-file /tmp/marimo.token \
    --file analysis.py \
    --code-file - <<'PY'
import marimo._code_mode as cm

async with cm.get_context() as ctx:
    print("Authenticated session cell count:", len(ctx.cells))
PY
```

- **Cloud Hosted (`molab.marimo.io`):** Export `MOLAB_API_KEY` or pass the remote tunnel URL (`https://...`) with `--token-file` and ensure remote servers enable `--mcp-allow-remote` if connecting over MCP.

---

## 4. Common Runtime Errors & Fast Remedies

### A. `StaleCellError` on Context Exit

Another user edit or browser keystroke changed the notebook after you read `ctx.cells`. Catch `cm.StaleCellError`, inspect updated code, and re-apply cleanly:

```python
import marimo._code_mode as cm

async with cm.get_context() as ctx:
    # Always verify current cell content before forcing skip_staleness_check=True
    for cid, cell in ctx.cells.items():
        print(cid, "first line:", cell.code.splitlines()[0] if cell.code else "<empty>")
```

### B. Cell Created or Edited Remains Unexecuted (`status == "idle"` or stale outputs)

Remember: `ctx.create_cell` and `ctx.edit_cell` queue AST edits only. Always call `ctx.run_cell(cid)` inside the same `async with cm.get_context()` transaction, then verify in a fresh scratchpad:

```python
import marimo._code_mode as cm

async with cm.get_context() as ctx:
    stale_ids = [cid for cid, c in ctx.cells.items() if c.status == "stale"]
    for cid in stale_ids:
        ctx.run_cell(cid)
    print("Triggered stale cells:", stale_ids)
```
