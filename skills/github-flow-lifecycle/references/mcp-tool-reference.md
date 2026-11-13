# `github-mcp-server` (`mimir-agent-kit_github`) Reference (`v2.1.0` Native Binary)

In Google Antigravity `2.31+`, all 89 tools on `mimir-agent-kit_github` are **lazy-loaded** and invoked via `call_mcp_tool` with `ServerName: "mimir-agent-kit_github"` (or `"github"` if registered globally without plugin prefixing). Detailed JSON schemas reside on disk under the Antigravity MCP directory (`~/.gemini/antigravity/mcp/mimir-agent-kit_github/<tool>.json` on Unix hosts).

`scripts/github_mcp_launcher.py` bootstraps the official SHA-256-pinned `github/github-mcp-server` `v2.1.0` static binary into `${PLUGIN_DATA}` on both Ubuntu Linux and macOS (**zero Docker requirement**) and injects `gh auth token --hostname github.com` into `GITHUB_PERSONAL_ACCESS_TOKEN` in memory before calling `os.execve("github-mcp-server", ["github-mcp-server", "stdio"])`. A single `gh` keyring login accesses both personal repositories (`jamielapointe/*`) and GitHub Enterprise Cloud organization repositories (`Panoptic-Huginn/*`) with zero stored PATs.

---

## 1. Dual-Owner Routing & Keyring Scopes

1. **Always distinguish repository `owner` from `get_me.login`:**
   - Parse `owner` and `repo` from `git remote get-url origin`.
   - On organization repositories (e.g., `Panoptic-Huginn/mimir-agent-kit`), pass `owner: "Panoptic-Huginn"` for all issue, ruleset, PR, and Actions calls — pass `get_me.login` (`"jamielapointe"`) only to `assignees`, `reviewers`, or a personal fork prefix.
2. **Query rulesets at `level: "repository"` during PR workflows:**
   - `repository_ruleset_read(level: "repository", method: "get_rules_for_branch", owner: "<owner>", repo: "<repo>", branch: "main")` works with baseline `gh` OAuth scopes (`repo`, `read:org`) and evaluates org-inherited rulesets automatically.
   - `level: "organization"` calls `GET /orgs/<org>/rulesets`, which requires `admin:org`. To unlock org-level rulesets and workflow triggers once per workstation, run:

     ```bash
     gh auth refresh --hostname github.com --scopes workflow,admin:org
     ```

   - Unprotected personal repositories may return `[]` or `404` for rulesets; treat that as "no active branch rulesets" rather than an error.
3. **Pass both `owner` and `repo` to `list_issue_types`:**
   - Works uniformly across org and user repositories that enable Issue Types. Only pass `type` to `issue_write` if `list_issue_types` returns matching enabled types; omit `type` otherwise.

---

## 2. Exact `v2.1.0` Parameter Reference & Traps

| Lifecycle Step | Tool (`mimir-agent-kit_github`) | Exact Parameters & Edge Cases |
| :--- | :--- | :--- |
| **User identity** | `get_me` | `{}` — use `login` for `assignees` / `search_issues` author filters. |
| **Branch rules** | `repository_ruleset_read` | `level: "repository"`, `method: "get_rules_for_branch"`, `owner`, `repo`, `branch: "main"`. (`includes_parents: true` defaults on `get`/`list`.) |
| **Issue search / list** | `search_issues` / `list_issues` | Pass `perPage: 10` (`5–10` items); in `search_issues`, use `sort`/`order` params rather than `sort:` inside `query`. |
| **Issue read** | `issue_read` | `method: "get" \| "get_comments" \| "get_sub_issues" \| "get_parent" \| "get_labels"`, `owner`, `repo`, `issue_number`. |
| **Issue write** | `issue_write` | `method: "create" \| "update"`, `owner`, `repo`, optional `type` (only if enabled), `labels` (validated against `list_label`), `state_reason` when closing. |
| **List PRs** | `list_pull_requests` | `owner`, `repo`, `head: "<head-owner>:<branch-name>"`, `state: "open"`. Pass `fields` (e.g., `["number","title","state","html_url","head","mergeable_state"]`, omitting `"body"`) to cut response size. Use `search_pull_requests` instead when filtering by author. |
| **Create PR** | `create_pull_request` | `owner`, `repo`, `title`, `head: "<branch-name>"` (bare branch for same-repo PRs; `"<fork-owner>:<branch>"` for cross-fork PRs), `base: "main"`, `body`, `draft`. |
| **Read PR / checks / threads** | `pull_request_read` | `method: "get" \| "get_diff" \| "get_status" \| "get_files" \| "get_commits" \| "get_review_comments" \| "get_reviews" \| "get_comments" \| "get_check_runs"`. Note: `get_review_comments` uses cursor pagination (`perPage`, `after`); others use `page`, `perPage`. |
| **Reply to thread** | `add_reply_to_pull_request_comment` | Reply on an existing review comment before resolving its thread. |
| **Resolve thread** | `pull_request_review_write` | `method: "resolve_thread"`, `threadId: "PRRT_..."`. **Schema Trap:** JSON schema marks `owner`, `repo`, `pullNumber`, and `method` as `required`, even though server ignores the first three for `resolve_thread` — **always include all four**. |
| **Update PR branch** | `update_pull_request_branch` | **Merge-commit only** (`v2.1.0` exposes no `rebase` option). **Do NOT call** when `required_linear_history` is active; rebase locally (`git fetch origin main && git rebase origin/main && git push --force-with-lease origin HEAD`). |
| **Workflow & jobs** | `actions_list` | `method: "list_workflow_runs"` (`workflow_runs_filter: {"branch": "<branch>"}`, optional `resource_id: "<workflow.yml>"`); `method: "list_workflow_jobs"` (`resource_id: "<run_id>"`, optional `workflow_jobs_filter: {"filter": "latest"}`). |
| **Failed logs** | `get_job_logs` | `owner`, `repo`, `run_id` (required with `failed_only: true`), `failed_only: true`, `return_content: true`, `tail_lines: 500` (or `job_id` for a single job). |

---

## 3. Excluded Tools Notice

To ensure every `mcp_mimir-agent-kit_github_<tool>` identifier satisfies Antigravity's `^[a-zA-Z0-9_-]{1,64}$` constraint, `mcp_config.json` excludes two upstream tools (`GITHUB_EXCLUDE_TOOLS`):

- `list_org_repository_security_advisories`
- `manage_repository_notification_subscription`

Use the `gh api` equivalents in [gh-cli-fallback.md](./gh-cli-fallback.md#3-replacements-for-excluded-mcp-tools-64-char-cap) whenever either operation is required.
