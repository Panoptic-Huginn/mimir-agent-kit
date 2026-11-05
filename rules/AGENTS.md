# Global Agentic Git & GitHub Flow Rules

Whenever implementing features, fixing bugs, refactoring code, creating Git commits, or opening/updating Pull Requests in any Git repository, you **MUST** activate and follow the `github-flow-lifecycle` skill (`/github-flow-lifecycle`) and strictly uphold these invariants:

1. **Branch Isolation Mandate:**
   - **NEVER** commit directly to `main`, `master`, or a detached `HEAD`.
   - Always resolve or create a tracking GitHub Issue via `github-mcp-server` (exposed globally as `github-mcp-server` or plugin-namespaced as `mimir-agent-kit_github-mcp-server`) using `search_issues`, `list_issues`, `issue_read`, and `issue_write`, and work on an isolated, remote-tracked feature branch named `<type>/<issue-number>-<short-kebab-slug>`.
2. **`github-mcp-server` Primary / Local Git Working-Tree Boundary:**
   - Use **`github-mcp-server`** (`github-mcp-server` or `mimir-agent-kit_github-mcp-server`) as the primary mechanism for all remote GitHub operations (`get_me`, `repository_ruleset_read`, `issue_read`, `issue_write`, `pull_request_read`, `create_pull_request`, `update_pull_request`, `pull_request_review_write`, `actions_list`, `actions_get`, `get_job_logs`).
   - Use **local workspace file tools and local `git` CLI** for all file edits, staging (`git add`), committing (`git commit`), and branch pushing (`git push`).
   - **NEVER** use `github-mcp-server` remote file-mutation tools (`push_files`, `create_or_update_file`, `delete_file`) that bypass the local working tree and pre-commit hooks.
3. **Mandatory Pre-Commit Local CI Gate:**
   - **NEVER** run `git commit` (and **NEVER** pass `--no-verify` or `-n`) until the repository's full local CI suite (`pixi` / `uv` / `pre-commit` / `CMakePresets.json` / `alr gnatprove` / unit tests / package build) has executed on the current working tree and exited with status code `0`.
4. **Autonomous Remote CI Self-Healing & No Autonomous Merge:**
   - After opening or pushing to a Pull Request, poll remote GitHub Actions check runs (`pull_request_read` with `method: "get_check_runs"` and `actions_list` with `method: "list_workflow_runs"`) until completion, diagnosing and fixing any remote failures via `get_job_logs` (`failed_only: true, return_content: true`).
   - **NEVER** merge a Pull Request (`merge_pull_request` and `gh pr merge` are strictly forbidden). Hand off the verified, green Pull Request to the human user for final review and merge.
