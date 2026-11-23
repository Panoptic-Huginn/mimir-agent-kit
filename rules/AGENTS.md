# Global Agentic Git & GitHub Governance Rules

Across all repositories (`jamielapointe/*` personal repositories and `Panoptic-Huginn/*` GitHub Enterprise Cloud organization repositories), strictly uphold these universal invariants and skill-routing boundaries:

## 1. Universal Identity, Tooling & Safety Invariants

1. **Dual-Owner Identity Routing:**
   - **NEVER** pass `get_me.login` (`jamielapointe`) as repository `owner` when operating on organization repositories (`Panoptic-Huginn/*`). Always derive `owner` and `repo` from the target repository or `git remote get-url origin`, using `get_me.login` strictly for `assignees`, `reviewers`, or personal fork prefixes.
2. **`github-mcp-server` Primary / `gh` CLI Partner / Local `git` Working-Tree Boundary:**
   - Use **`github-mcp-server`** (the SHA-256-pinned native binary server registered by this plugin as `github` and exposed as lazy-loaded `mimir-agent-kit_github`, or a global `github` server, authenticated from the `gh auth token` OS keyring) as the primary mechanism for remote GitHub operations (`get_me`, `repository_ruleset_read`, `issue_read`, `issue_write`, `pull_request_read`, `create_pull_request`, `update_pull_request`, `pull_request_review_write`, `actions_list`, `actions_get`, `get_job_logs`).
   - Use **`gh` CLI** (`--body-file -` single-quoted heredocs for Markdown/LaTeX) as a permitted partner for GraphQL/REST operations not modeled by MCP (such as ruleset updates/deletions, repository merge-setting updates, release asset management, or the two >64-char excluded tools) and in Cloud Remote Agents where local stdio servers do not run.
   - Use **local workspace file tools and local `git` CLI** for all file edits, staging (`git add`), committing (`git commit`), and branch pushing (`git push`).
   - **NEVER** use `github-mcp-server` remote file-mutation tools (`push_files`, `create_or_update_file`, `delete_file` — excluded in `mcp_config.json`) that bypass the local working tree and pre-commit hooks.
3. **No MCP App Form Hallucination & Autonomous `--refresh-live` Self-Healing:**
   - Antigravity `2.34.0+` advertises `io.modelcontextprotocol/ui` during `initialize`, but because `mimir-agent-kit_github` is lazy-loaded via the generic `call_mcp_tool` wrapper (which strips `_meta.ui.resourceUri`) and `github-mcp-server` sets `isError: true` on deferred stubs, **no interactive MCP App form is EVER rendered in chat**. `mimir-agent-kit_github` disables form deferral via dual `--features=mcp_apps_disable_form_deferral` and `GITHUB_FEATURES=mcp_apps_disable_form_deferral`.
   - **Strict Prohibition:** **NEVER** claim an interactive PR or Issue form was shown/rendered in chat and **NEVER** ask the user to review or click "Submit" if `issue_write`, `create_pull_request`, or `update_pull_request` ever returns `"An interactive form has been shown to the user..."`.
   - **Mandatory Autonomous Self-Healing:** That error proves the running `mimir-agent-kit_github` `stdio` process predates a plugin/config update and lacks `--features=mcp_apps_disable_form_deferral`. Immediately run:

     ```bash
     uv run --isolated --no-project --python '>=3.15' python ~/.gemini/config/plugins/mimir-agent-kit/scripts/github_mcp_launcher.py --refresh-live
     ```

     (or workspace `${PLUGIN_ROOT}/scripts/github_mcp_launcher.py --refresh-live`, which calls `RefreshMcpServers` on loopback `${ANTIGRAVITY_LS_ADDRESS}` and verifies `MCP_SERVER_STATUS_READY`), and **immediately retry** the `mimir-agent-kit_github` MCP call. Inside a separate `antigravity-ide` (`agy --hub`) window where `ANTIGRAVITY_LS_ADDRESS` is unavailable, fall back to permitted `gh` CLI (`--body-file -`) or ask the user to run **Developer: Reload Window** — **never** mention a Submit button.
4. **Multi-Agent (`/swarm` & Subagent) MCP Execution Boundary:**
   - In native Antigravity **`/swarm`**, **only the Coordinator** holds MCP server access (`call_mcp_tool` -> `mimir-agent-kit_github`); swarm workers (`swarm{action: "add"}`) lack `call_mcp_tool` and receive `server mimir-agent-kit_github is not allowed in this context`. When combining `/swarm` with `/github-flow-lifecycle` or `/github-ops`, the **Coordinator** must execute `mimir-agent-kit_github` control-plane calls (issue/ruleset lookup & creation, `create_branch` if remote, PR creation/update, remote CI polling, review-thread resolution) while workers own local Git branching, edits, builds, and Stage 3 local CI (posting exact payloads to `@coordinator` rather than bypassing MCP via `gh issue/pr create` when MCP is active). Spawn concurrent editing workers with `workspace: "share"` (or `"branch"`) and merge/cherry-pick onto the `<type>/<issue-number>-<short-kebab-slug>` branch before `kill`, keeping read-only investigators and verifiers on `inherit`.
   - When delegating GitHub MCP operations via **`invoke_subagent` / `define_subagent`**, always use `TypeName: "self"` or pass `EnableMCPTools: true` on `define_subagent`.
5. **No Autonomous Merge & Destructive-Action Consent Gate:**
   - **NEVER** merge a Pull Request (`merge_pull_request` or `gh pr merge`) **unless** the user explicitly asks you to perform this task (and only once all required CI checks and branch rulesets are satisfied). Autonomous PR merging without an explicit user request is strictly forbidden—by default, hand off verified, green Pull Requests to the human user for final review and merge.
   - **NEVER** execute destructive or governance-weakening GitHub operations (`delete_repository`, changing repository visibility between private and public, archiving/transferring repositories, deleting releases/tags, or relaxing branch rulesets) without explicit prior human confirmation.

## 2. Mandatory Skill Routing

1. **Modifying Repository Files, Commits, or Pull Requests -> Activate `/github-flow-lifecycle`:**
   - Whenever implementing features, fixing bugs, refactoring code, editing repository configs/docs, creating Git commits, or opening/updating Pull Requests in any Git repository, you **MUST** activate and follow the `github-flow-lifecycle` skill (`/github-flow-lifecycle`):
     - **Branch Isolation Mandate:** **NEVER** commit directly to `main`, `master`, or a detached `HEAD`. Always resolve or create a tracking GitHub Issue via `github-mcp-server` (`search_issues`, `list_issues`, `issue_read`, `issue_write`) and work on an isolated, remote-tracked feature branch named `<type>/<issue-number>-<short-kebab-slug>`.
     - **Mandatory Pre-Commit Local CI Gate:** **NEVER** run `git commit` (and **NEVER** pass `--no-verify` or `-n`) until the repository's full local CI suite (`uv` / `pre-commit` / `CMakePresets.json` / `alr gnatprove` / unit tests / package build) has executed on the current working tree and exited with status code `0`.
     - **Autonomous Remote CI Self-Healing:** After opening or pushing to a Pull Request, poll remote GitHub Actions check runs (`pull_request_read` with `method: "get_check_runs"` and `actions_list` with `method: "list_workflow_runs"`) until completion, diagnosing and fixing any remote failures via `get_job_logs` (`failed_only: true, return_content: true`).
2. **Non-Code GitHub & GHEC Organization Administration -> Activate `/github-ops`:**
   - When managing repositories, `Panoptic-Huginn` Enterprise or `jamielapointe` rulesets, custom properties, issue/sub-issue backlogs, GitHub Projects v2, security alerts (Dependabot, CodeQL, Secret Scanning, Scorecard), releases, discussions, or cross-repository searches **without** modifying repository files, activate `/github-ops`. If a `/github-ops` task transitions into editing repository files, hand off immediately to `/github-flow-lifecycle`.
