# Global Agentic Git & GitHub Governance Rules

Across all repositories (`jamielapointe/*` personal repositories and `Panoptic-Huginn/*` GitHub Enterprise Cloud organization repositories), strictly uphold these universal invariants and skill-routing boundaries:

## 1. Universal Identity, Tooling & Safety Invariants

1. **Dual-Owner Identity Routing:**
   - **NEVER** pass `get_me.login` (`jamielapointe`) as repository `owner` when operating on organization repositories (`Panoptic-Huginn/*`). Always derive `owner` and `repo` from the target repository or `git remote get-url origin`, using `get_me.login` strictly for `assignees`, `reviewers`, or personal fork prefixes.
2. **`github-mcp-server` Primary / `gh` CLI Partner / Local `git` Working-Tree Boundary:**
   - Use **`github-mcp-server`** (the SHA-256-pinned native binary server registered by this plugin as `github` and exposed as lazy-loaded `mimir-agent-kit_github`, or a global `github` server, authenticated from the `gh auth token` OS keyring) as the primary mechanism for remote GitHub operations (`get_me`, `repository_ruleset_read`, `issue_read`, `issue_write`, `pull_request_read`, `create_pull_request`, `update_pull_request`, `pull_request_review_write`, `actions_list`, `actions_get`, `get_job_logs`).
   - Use **`gh` CLI** (`--body-file -` single-quoted heredocs for Markdown/LaTeX) as a permitted partner for GraphQL/REST operations not modeled by MCP (such as org-level ruleset mutations, repository merge-setting updates, release asset management, or the two >64-char excluded tools) and in Cloud Remote Agents where local stdio servers do not run.
   - Use **local workspace file tools and local `git` CLI** for all file edits, staging (`git add`), committing (`git commit`), and branch pushing (`git push`).
   - **NEVER** use `github-mcp-server` remote file-mutation tools (`push_files`, `create_or_update_file`, `delete_file`) that bypass the local working tree and pre-commit hooks.
3. **No Autonomous Merge & Destructive-Action Consent Gate:**
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
