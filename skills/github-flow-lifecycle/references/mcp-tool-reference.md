# `github-mcp-server` (`mimir-agent-kit_github`) Reference (`v2.2.0` Native Binary)

In Google Antigravity `2.34+`, all 86 exposed tools on `mimir-agent-kit_github` are **lazy-loaded** and invoked via `call_mcp_tool` with `ServerName: "mimir-agent-kit_github"` (or `"github"` if registered globally without plugin prefixing). Always inspect `~/.gemini/antigravity/mcp/mimir-agent-kit_github/<tool>.json` before first invocation so nested object and enum parameters match the exact JSON schema.

`scripts/github_mcp_launcher.py` bootstraps the official SHA-256-pinned `github/github-mcp-server` `v2.2.0` static binary into `${PLUGIN_DATA}` on both Ubuntu Linux and macOS (**zero Docker requirement**), scrubs unexpanded `${VAR}` token placeholders, injects `gh auth token --hostname github.com` into `GITHUB_PERSONAL_ACCESS_TOKEN` in memory, and `exec`s `github-mcp-server stdio --features=mcp_apps_disable_form_deferral`. Disabling MCP Apps form deferral ensures `issue_write`, `create_pull_request`, and `update_pull_request` execute directly via the GitHub API when Antigravity `2.34+` advertises `io.modelcontextprotocol/ui`, rather than aborting with an unrendered interactive form error over `call_mcp_tool`.

---

## 1. Dual-Owner Routing, Multi-Agent Context & Keyring Scopes

1. **Always distinguish repository `owner` from `get_me.login`:**
   - Parse `owner` and `repo` from `git remote get-url origin`.
   - On organization repositories (e.g., `Panoptic-Huginn/mimir-agent-kit`), pass `owner: "Panoptic-Huginn"` for all issue, ruleset, PR, and Actions calls — pass `get_me.login` (`"jamielapointe"`) only to `assignees`, `reviewers`, or a personal fork prefix.
2. **Multi-Agent (`/swarm` & Subagent) MCP Access Control:**
   - Native `/swarm` workers (`swarm{action: "add"}`) do **not** receive `call_mcp_tool` (`server mimir-agent-kit_github is not allowed in this context`); **only the Swarm Coordinator** holds MCP server access. Keep all `mimir-agent-kit_github` calls in the Coordinator while swarm workers execute local branching, edits, builds, and Stage 3 local CI (posting issue/PR payloads to `@coordinator` rather than bypassing MCP via `gh issue/pr create` when MCP is active). When multiple swarm authors edit or build concurrently, give each author `workspace: "share"` (or `"branch"`) and merge/cherry-pick their verified commits onto the `<type>/<N>-<slug>` branch before `swarm{action: "kill"}` (leaving read-only investigators and verifiers on `inherit`).
   - Custom subagents (`define_subagent`) require `EnableMCPTools: true` (or `invoke_subagent(TypeName: "self")`) to call `mimir-agent-kit_github`.
3. **Query rulesets at `level: "repository"` during PR workflows:**
   - `repository_ruleset_read(level: "repository", method: "get_rules_for_branch", owner: "<owner>", repo: "<repo>", branch: "main")` works with baseline `gh` OAuth scopes (`repo`, `read:org`) and evaluates org-inherited rulesets automatically.
   - `level: "organization"` calls `GET /orgs/<org>/rulesets`, which requires `admin:org` (returns `404` otherwise). Security alert tools (`list_dependabot_alerts`, `list_code_scanning_alerts`, `list_secret_scanning_alerts`) challenge for `security_events` (or `repo`). Unlock all non-code scopes once per workstation with:

     ```bash
     gh auth refresh --hostname github.com --scopes repo,read:org,workflow,admin:org,project,notifications,security_events
     ```

   - Unprotected personal repositories may return `[]` or `404` for rulesets; repositories without CodeQL runs return `404 no analysis found` on `list_code_scanning_alerts`, and tag-only repositories without GitHub Releases return `404 Not Found` on `get_latest_release` (use `list_tags`). Treat those as "none present" rather than fatal errors.
4. **Pass both `owner` and `repo` to `list_issue_types`:**
   - Works uniformly across org and user repositories that enable Issue Types. Only pass `type` to `issue_write` if `list_issue_types` returns matching enabled types; omit `type` otherwise.

---

## 2. Exact `v2.2.0` Parameter Reference & Traps

| Lifecycle Step | Tool (`mimir-agent-kit_github`) | Exact Parameters & Edge Cases |
| :--- | :--- | :--- |
| **User identity** | `get_me` | `{}` — use `login` for `assignees` / `search_issues` author filters. |
| **Branch rules** | `repository_ruleset_read` | `level: "repository"`, `method: "get_rules_for_branch"`, `owner`, `repo`, `branch: "main"`. (`includes_parents: true` defaults on `get`/`list`.) |
| **Issue search / list** | `search_issues` / `list_issues` | `search_issues`: pass `owner`, `repo`, `query: "is:open <keywords>"` (scopes `is:issue`, **not** `is:open`), `perPage: 10`, `fields` (omit `body`, `reactions`, `field_values`), and `sort`/`order` params (never `sort:` in `query`). `list_issues`: requires uppercase `state: "OPEN" \| "CLOSED"` and restricts `fields` to 11 items (`number`, `title`, `body`, `state`, `user`, `labels`, `assignees`, `comments`, `created_at`, `updated_at`, `field_values` — **no `"html_url"` or `"reactions"`**). |
| **Issue read** | `issue_read` | `method: "get" \| "get_comments" \| "get_sub_issues" \| "get_parent" \| "get_labels"`, `owner`, `repo`, `issue_number`. |
| **Issue write** | `issue_write` | `method: "create" \| "update"`, `owner`, `repo`, optional `type` (only if enabled), `labels` (validated against `list_label`), `state_reason` when closing. |
| **List PRs** | `list_pull_requests` | `owner`, `repo`, `head: "<head-owner>:<branch-name>"`, `state: "open"`. Pass `fields` (e.g., `["number","title","state","html_url","head","mergeable_state"]`, omitting `"body"`) to cut response size. Use `search_pull_requests` instead when filtering by author. |
| **Create PR** | `create_pull_request` | `owner`, `repo`, `title`, `head: "<branch-name>"` (bare branch for same-repo PRs; `"<fork-owner>:<branch>"` for cross-fork PRs), `base: "main"`, `body`, `draft`. |
| **Read PR / checks / threads** | `pull_request_read` | `method: "get" \| "get_diff" \| "get_status" \| "get_files" \| "get_commits" \| "get_review_comments" \| "get_reviews" \| "get_comments" \| "get_check_runs"`. Note: `get_review_comments` uses cursor pagination (`perPage`, `after`); others use `page`, `perPage`. |
| **Reply to thread** | `add_reply_to_pull_request_comment` | Reply on an existing review comment before resolving its thread. **Schema Trap:** Top-level `required` lists only `owner`, `repo`, `commentId`, yet `pullNumber` (`number`) is mandatory whenever `body` is set, and `commentId` must be the numeric comment ID (`number`, from `#discussion_r...`), **never** the GraphQL `PRRT_...` `threadId`. |
| **Resolve thread** | `pull_request_review_write` | `method: "resolve_thread"`, `threadId: "PRRT_..."`. **Schema Trap:** JSON schema marks `owner`, `repo`, `pullNumber`, and `method` as `required`, even though server ignores the first three for `resolve_thread` — **always include all four**. |
| **Update PR branch** | `update_pull_request_branch` | **Merge-commit only** (`v2.2.0` exposes no `rebase` option). **Do NOT call** when `required_linear_history` is active; rebase locally (`git fetch origin main && git rebase origin/main && git push --force-with-lease origin HEAD`). |
| **Workflow & jobs** | `actions_list` | `method: "list_workflow_runs"` (`workflow_runs_filter: {"branch": "<branch>"}`, optional `resource_id: "<workflow.yml>"`); `method: "list_workflow_jobs"` (`resource_id: "<run_id>"`, optional `workflow_jobs_filter: {"filter": "latest"}`). **Schema Trap:** `workflow_runs_filter` and `workflow_jobs_filter` **must** be native JSON objects (`{...}`), never JSON-encoded strings (`"{...}"`). |
| **Failed logs** | `get_job_logs` | `owner`, `repo`, `run_id` (required with `failed_only: true`), `failed_only: true`, `return_content: true`, `tail_lines: 500` (or `job_id` for a single job). |

---

## 3. Excluded Tools Notice (`GITHUB_EXCLUDE_TOOLS`)

`mcp_config.json` excludes five upstream tools via `GITHUB_EXCLUDE_TOOLS`:

1. **64-character Antigravity identifier cap** (`^[a-zA-Z0-9_-]{1,64}$` — use `gh api` equivalents in [gh-cli-fallback.md](./gh-cli-fallback.md#3-replacements-for-excluded-mcp-tools-64-char-cap)):
   - `list_org_repository_security_advisories`
   - `manage_repository_notification_subscription`
2. **Working-tree & pre-commit safety enforcement** (forbidden remote file mutations that bypass `.pre-commit-config.yaml` and local CI gates — always edit locally and `git commit` + `git push`):
   - `create_or_update_file`
   - `delete_file`
   - `push_files`
