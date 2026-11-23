---
name: github-flow-lifecycle
description: >-
  Enforces the 6-stage Git and GitHub Flow code-delivery lifecycle using native
  github-mcp-server (mimir-agent-kit_github), gh CLI, and local Git/CI tools,
  including GitHub issue resolution/creation, branch ruleset inspection, linked
  remote feature branching, mandatory pre-commit local CI verification, pull
  request creation, review thread resolution, and autonomous remote GitHub
  Actions CI monitoring and self-healing. Use whenever modifying repository
  files, implementing features, fixing bugs, refactoring code, creating commits,
  or opening and updating pull requests. For non-code repository, organization,
  backlog, project, security, or release management, use /github-ops instead.
metadata:
  version: v2
  publisher: jamielapointe
---

# Git & GitHub Flow Lifecycle Protocol

This skill governs end-to-end software delivery whenever repository files are created, modified, committed, or delivered via Pull Request—from task intake through a verified, green Pull Request ready for human review and merge.

> **Scope Boundary:** For **non-code GitHub operations** (repository creation/settings, `Panoptic-Huginn` or `jamielapointe` rulesets, custom properties, backlog/sub-issue/Projects v2 planning, Dependabot/CodeQL/Secret Scanning triage, releases, or cross-repo searches) without modifying local repository files, activate **`/github-ops`**.

## Related Skills

- **`/github-ops`**: Non-code GitHub & GHEC (`Panoptic-Huginn`) repository, ruleset, backlog, Projects v2, security, and release operations.
- **`/ada-spark-pro`**: Formally verified SPARK Ada 2022 (`GNAT 16.1+`, `gnatprove 16.1+`, `alr 2.1+`) safety kernels and Silver/Gold proofs.
- **`/python-pro`**: Python 3.15 (3.14 floor) (`uv` and `pixi`), `ruff`, `basedpyright`/`ty`, `prek`, `pytest` 9+, `deptry`, `pip-audit`, and `rumdl`.
- **`/rust-pro`**: Safety-critical Rust 1.99.1+ (`pixi`, `clippy`, `cargo fmt`, Google Rust Styleguide) systems software.
- **`/cmake-pro`**: Modern CMake 4.5+ (`CMakePresets.json` v11, `cmake --workflow --preset`, `gersemi`) standards.
- **`/c-pro`**: Deterministic ISO C23 (`-std=c23`, `clang-tidy`, `clang-format`, CERT C / MISRA C, sanitizers) systems standards.
- **`/cpp-pro`**: Modern C++23 (`clang-tidy`, `clang-format`, Google Test, Google Benchmark, sanitizers) standards.
- **`/jupyter-pro`**: Legacy Jupyter Notebook and Google Colab workflows and clean-output hygiene.
- **`/marimo-pro`**: Reactive marimo Python notebooks, `mo.ui` widgets, DAG execution, and `pixi`/`uv` toolchains.
- **`/marimo-pair`**: Live marimo kernel driving and durable notebook commits via `marimo._code_mode`.

---

## 1. High-Thinking Pre-Execution Directives

Before every tool invocation, enforce these invariants:

1. **Branch Isolation Check:** Active local Git branch must **NEVER** be `main`, `master`, or a detached `HEAD` before modifying, staging, or committing files.
2. **Docker-Free Native MCP Primary / Anti-Hallucination / Keyring Auth / Local-Git Boundary:**
   - Use **`github-mcp-server`** (lazy-loaded `mimir-agent-kit_github` via `call_mcp_tool`, or global `github`; `86` model-visible tools / `87` `tools/list` entries in `v2.2.0`) as primary for remote GitHub operations. `scripts/github_mcp_launcher.py` caches the SHA-256-verified `v2.2.0` binary in `${PLUGIN_DATA}` on Linux and macOS, reads `gh auth token --hostname github.com` from the OS keyring (`jamielapointe` + `Panoptic-Huginn`, zero PATs on disk), and enforces dual `--features=mcp_apps_disable_form_deferral` + `GITHUB_FEATURES=mcp_apps_disable_form_deferral`.
   - **No MCP App Form Hallucination & Autonomous `--refresh-live` Self-Healing:** Antigravity `2.34.0+` advertises `io.modelcontextprotocol/ui` during `initialize`, but because `mimir-agent-kit_github` is lazy-loaded via the generic `call_mcp_tool` wrapper (stripping `_meta.ui.resourceUri`) and `github-mcp-server` sets `isError: true` on deferred stubs, **no interactive MCP App form is EVER rendered in chat**. **NEVER** claim a PR/Issue form was shown or ask the user to click "Submit" if `issue_write`, `create_pull_request`, or `update_pull_request` returns `"An interactive form has been shown to the user..."`. That error proves a stale pre-update `stdio` process lacks `--features=mcp_apps_disable_form_deferral`; immediately run:

     ```bash
     uv run --isolated --no-project --python '>=3.15' python ~/.gemini/config/plugins/mimir-agent-kit/scripts/github_mcp_launcher.py --refresh-live
     ```

     (or workspace `${PLUGIN_ROOT}/scripts/github_mcp_launcher.py --refresh-live`, calling `RefreshMcpServers` on loopback `${ANTIGRAVITY_LS_ADDRESS}` and verifying `MCP_SERVER_STATUS_READY`), and **immediately retry** the `mimir-agent-kit_github` call! Inside a separate `antigravity-ide` (`agy --hub`) window where `ANTIGRAVITY_LS_ADDRESS` is unavailable, fall back to permitted `gh` CLI (`--body-file -`) or ask the user to run **Developer: Reload Window** — **never** mention a Submit button.
   - **Multi-Agent (`/swarm` & Subagent) MCP Routing:** Native `/swarm` workers (`swarm{action: "add"}`) lack `call_mcp_tool` (`server mimir-agent-kit_github is not allowed in this context`); **only the Coordinator** holds MCP access and executes Stage 1, Stage 4, and Stage 5 `mimir-agent-kit_github` calls while workers run local edits, builds, and Stage 3 CI (posting payloads to `@coordinator` rather than bypassing MCP via `gh issue/pr create`). Give concurrent editing workers `workspace: "share"` (or `"branch"`) and merge onto `<type>/<ISSUE_NUMBER>-<short-kebab-slug>` before `kill` (verifiers/readers keep `inherit`). Subagents require `TypeName: "self"` or `EnableMCPTools: true`.
   - **Partner & Cloud-Sandbox CLI (`gh` CLI):** Use `gh` CLI (`--body-file -` single-quoted heredocs) for GraphQL/REST endpoints not modeled by MCP, the two >64-char excluded tools, or Cloud Remote Agents where local stdio servers do not run (see [references/gh-cli-fallback.md](references/gh-cli-fallback.md)). If `gh auth status` reports logged out, halt and ask the user to run `gh auth login --hostname github.com`.
   - Use **local workspace file tools and local `git` CLI** for all edits, `git add`, `git commit`, and `git push`. **NEVER** use remote file-mutation tools (`create_or_update_file`, `push_files`, `delete_file` — excluded in `mcp_config.json`), which bypass `.pre-commit-config.yaml` and local CI.
3. **Verification-Before-Commit:** Never run `git commit` (and never pass `--no-verify` or `-n`) until the full local CI suite matching local tooling and `.github/workflows/*.yml` PR checks exits `0` on the current working tree.
4. **No Autonomous Merge:** Unless the user explicitly asks you to merge the Pull Request, stop once the PR is open, review threads are resolved, and remote GitHub CI checks report `SUCCESS` (`conclusion == "success"`). Autonomous merging to `main` is strictly forbidden.

---

## 2. Tool Boundary Matrix (`github-mcp-server` vs. `gh` Partner & Local CLI)

| Operation | Primary (`mimir-agent-kit_github`) | Permitted `gh` Partner / Cloud Fallback | Forbidden | Reason |
| :--- | :--- | :--- | :--- | :--- |
| **User Context & Rulesets** | `get_me`; `repository_ruleset_read` (`level: "repository"`, `method: "get_rules_for_branch"`, `branch: "main"` — `[]`/404 = unprotected) | `gh api "repos/<o>/<r>/rules/branches/main"`, `gh ruleset check main -R <o>/<r>` | Guessing rulesets; `level: "organization"` without `admin:org` | Identifies linear history, squash rules, and required checks |
| **Issues & Labels** | `search_issues`, `list_issues` (`perPage: 10`); `issue_read`; `issue_write`; `sub_issue_write`; `list_label`; `list_issue_types` (`owner`+`repo`) | `gh issue list/view/create -R <o>/<r> --body-file -` | Inline `--body` on LaTeX/code; claiming a form rendered / asking user to click Submit | Structured tracking; self-heal stale form deferral via `--refresh-live` |
| **Branch Creation** | Local `git checkout -b "<branch>" && git push -u origin HEAD` or `create_branch` + `git fetch` + checkout | `gh issue develop <N> -R <o>/<r> --checkout --name "<branch>"` | Committing on `main`, `master`, or detached `HEAD` | Keeps local working tree and remote tracking ref aligned |
| **Edits & Commits** | Local file tools (`edit_file`, `write_file`) + `git add` & `git commit` | None | `push_files`, `create_or_update_file`, `delete_file`, `git commit --no-verify` | Remote API file writes bypass pre-commit hooks and tests |
| **Pushing Commits** | `git push -u origin HEAD` / `git push origin HEAD` (`--force-with-lease origin HEAD` *only* on rebased feature branch) | None | `push_files`, `git push --force`, force-pushing shared branches | Preserves linear history without overwriting shared refs |
| **PR Creation & Sync** | `list_pull_requests` (`head: "<owner>:<branch>"`, omit `body`), `create_pull_request` (`head: "<branch>"`), `update_pull_request` | `gh pr create -R <o>/<r> --body-file -`, `gh pr edit`, `gh pr update-branch --rebase` | `update_pull_request_branch` on `required_linear_history`; claiming PR form rendered | Enforces squash/linear-history, `Closes #<N>`, and `--refresh-live` retry |
| **PR Reviews & Threads** | `pull_request_read` (`get_reviews`, `get_review_comments`, `get_comments`); `add_reply_to_pull_request_comment`; `pull_request_review_write` (`resolve_thread` with `owner`, `repo`, `pullNumber`, `threadId`) | `gh api graphql` (`resolveReviewThread`, see [references/gh-cli-fallback.md](references/gh-cli-fallback.md)) | Leaving threads open under `required_review_thread_resolution` | Satisfies review-thread merge gates (`gh pr view --comments` cannot resolve) |
| **Remote CI & Logs** | `pull_request_read` (`get_check_runs`, `get_status`), `actions_list`, `actions_get`, `get_job_logs` (`failed_only: true`, `return_content: true`) | `gh pr checks`, `gh run list -R <o>/<r>`, `gh run view <id> --log-failed` (no `--watch`) | Handing off before `HEAD_SHA` checks reach `completed` | Enables deterministic autonomous remote CI self-healing |
| **Merge PR** | **HUMAN DEFAULT** (`merge_pull_request` *only* on explicit user request) | `gh pr merge --squash` (*only* on explicit user request) | Autonomous `merge_pull_request` / `gh pr merge`, `git merge` into `main` | Merge only when explicitly requested after green CI |

---

## 3. Entry-State Decision Tree

Evaluate workspace and remote GitHub state before modifying files (see [references/mcp-tool-reference.md](references/mcp-tool-reference.md) for `v2.2.0` schemas):

1. **On `main` or `master` with uncommitted edits:** Stash (`git stash push -u -m "wip: pre-branching stash"`), run **Stages 1–2**, `git stash pop` onto the feature branch, then run **Stage 3**.
2. **Existing GitHub Issue `#<ISSUE_NUMBER>` supplied:** Call `issue_read` (`method: "get"` and `"get_comments"`) for acceptance criteria, skip issue creation in **Stage 1**, and proceed to **Stage 2**.
3. **Already on a feature branch with an open PR (failing CI or review comments):** Call `list_pull_requests` (`head: "<head-owner>:<branch>"`, `fields: ["number","title","state","html_url","mergeable_state"]`) and `pull_request_read` (`"get"`, `"get_check_runs"`, `"get_review_comments"`), then jump to **Stage 5**.
4. **Standard New Task (clean `main`, no issue specified):** Execute **Stages 1 through 6** sequentially.

---

## 4. Six-Stage Execution State Machine

### Stage 1: Repository Context & Issue Resolution (`github-mcp-server`)

1. **Inspect User Context, Owner Identity & Branch Rulesets:**
   - Parse `owner` and `repo` from `git remote get-url origin` (`git@github.com:<owner>/<repo>.git` or `https://github.com/<owner>/<repo>.git`).
   - Call `get_me` to read acting `login` (`jamielapointe`). **Critical Dual-Owner Rule:** On org repos (`Panoptic-Huginn/*`), keep `owner: "<org>"` on all repo/issue/PR/Actions calls and pass `get_me.login` only to `assignees` or fork prefixes.
   - Call `repository_ruleset_read` (`level: "repository"`, `method: "get_rules_for_branch"`, `owner`, `repo`, `branch: "main"`). Baseline `gh` scopes (`repo`, `read:org`) evaluate inherited org rulesets here (`level: "organization"` needs `admin:org`); treat `[]` or `404` on personal repos as unprotected. Check `required_linear_history`, `allowed_merge_methods`, `required_review_thread_resolution`, and required status checks.
2. **Search for Existing Open Issues:**
   - Inspect `~/.gemini/antigravity/mcp/mimir-agent-kit_github/<tool>.json` before first calling any lazy-loaded MCP tool.
   - Query `search_issues` (`owner`, `repo`, `query: "is:open <keywords>"`, `perPage: 10`, `fields: ["number","title","state","html_url","created_at","updated_at"]`) or `list_issues` (`owner`, `repo`, `state: "OPEN"`, `perPage: 10`, `fields: ["number","title","state","labels"]`) without loading multi-KB bodies.
3. **Create Issue (If None Exists):**
   - Call `list_label` (`owner`, `repo`) and optionally `list_issue_types` (`owner`, `repo`); omit `type` unless `list_issue_types` returns enabled entries.
   - Call `issue_write` (`method: "create"`) with `title` (`<type>(<scope>): <concise summary>`), structured `body` (**Problem Statement**, **Technical Scope**, **Verifiable Acceptance Criteria**), validated `labels`, and optional `assignees` (`[<login from get_me>]`). If `issue_write` returns `"An interactive form has been shown..."`, run `github_mcp_launcher.py --refresh-live` and retry immediately (never mention a form or Submit button).
4. Record `<ISSUE_NUMBER>` for all branch, commit, and PR operations.

---

### Stage 2: Remote-Linked Branch Creation

1. **Synchronize Local Default Branch:**

   ```bash
   git checkout main
   git pull --ff-only origin main
   ```

2. **Create and Push Feature Branch (`<type>/<ISSUE_NUMBER>-<short-kebab-slug>`):**
   - **Option A (Local Git + Remote Tracking — Preferred):**

     ```bash
     git checkout -b "<type>/<ISSUE_NUMBER>-<short-kebab-slug>"
     git push -u origin HEAD
     ```

   - **Option B (Remote `create_branch` + Local Checkout):** Call `create_branch` (`branch: "<type>/<ISSUE_NUMBER>-<short-kebab-slug>"`, `from_branch: "main"`), then `git fetch origin && git checkout -b "<type>/<ISSUE_NUMBER>-<short-kebab-slug>" "origin/<type>/<ISSUE_NUMBER>-<short-kebab-slug>"`.
   - **Option C (`gh issue develop`):** `gh issue develop <ISSUE_NUMBER> -R "<owner>/<repo>" --checkout --name "<type>/<ISSUE_NUMBER>-<short-kebab-slug>"` (`Closes #<ISSUE_NUMBER>` in the PR body also auto-links).
3. **Verify Branch Isolation Invariant:** Run `git branch --show-current` and **abort immediately** if `main`, `master`, or empty.

---

### Stage 3: Implementation & Mandatory Pre-Commit Local CI Gate

1. **Implement Scoped Changes & Tests:** Adhere to `AGENTS.md` and language skills (`/python-pro`, `/rust-pro`, `/cmake-pro`, `/c-pro`, `/cpp-pro`, `/ada-spark-pro`, `/marimo-pro`), adding unit/integration tests for new behavior or fixes.
2. **Inspect `.github/workflows/*.yml` for PR Job Parity:** Check every workflow triggered by `pull_request` (e.g., `ci.yml`).
3. **Execute the Full Local CI Pipeline BEFORE `git commit`:**
   Run all applicable checks until every step exits `0` cleanly without further formatter diffs (full table in [references/local-ci-matrix.md](references/local-ci-matrix.md)):

   - **Antigravity Plugin (`scripts/ci/run_local_ci.sh`):** `./scripts/ci/run_local_ci.sh` (plus `uv run rumdl check --no-exclude skills/<changed-skill>` when editing `skills/`)
   - **Pixi / Python / Cross-Ecosystem (`pixi.lock`):** `pixi run prek run --all-files --show-diff-on-failure` (or `pre-commit`), `pixi run ruff check` & `ruff format --check`, `pixi run basedpyright` & `ty check`, `pixi run pytest`, `pixi run build` (if defined)
   - **Pure `uv` Python (`uv.lock`):** `uv run prek run --all-files`, `uv run ruff check .` & `ruff format --check .`, `uv run basedpyright` & `uv run ty check`, `uv run deptry .`, `uv run pip-audit`, `uv run pytest`
   - **C/C++23 (`CMakePresets.json`), Rust (`Cargo.toml`), SPARK Ada (`alire.toml`), Node, Go, Docs:** Run configured format/lint/proof/test workflows per [references/local-ci-matrix.md](references/local-ci-matrix.md).

---

### Stage 4: Atomic Commit, Push & Pull Request Creation

1. **Workspace, DVC & Secret Hygiene Audit:**
   - Verify via `git status` and `git diff` that zero scratch files, build artifacts (`dist/`, `build/`), or secrets (`.env`, `.dvc/config.local`) are staged.
   - In DVC repositories (`heimdall-astro`), never stage raw data (`data/latest/`, `data/baseline/*.zarr`, `*.html`); if `data/baseline.dvc` changed, confirm `pixi run dvc push` completed first.
2. **Stage and Commit Verified Changes (Never Use `--no-verify`):**

   ```bash
   git add <specific-modified-files>
   git commit -m "<type>(<scope>): <concise summary> (#<ISSUE_NUMBER>)"
   ```

   Keep subjects under 72 chars with a multi-bullet **what/why** body for squash-merges.
3. **Push Branch to Remote:** `git push -u origin HEAD`
4. **Create or Update Pull Request via `github-mcp-server`:**
   - Check `.github/pull_request_template.md` (or `.github/PULL_REQUEST_TEMPLATE/`) and `list_pull_requests` (`owner`, `repo`, `head: "<head-owner>:<branch-name>"`, `state: "open"`, `fields: ["number","title","state","html_url","head"]`).
   - Call `create_pull_request` (or `update_pull_request` if open) with `owner`/`repo` from `origin`, `title: "<type>(<scope>): <concise summary> (#<ISSUE_NUMBER>)"`, `head: "<branch-name>"` (`"<fork-owner>:<branch>"` only for cross-fork PRs), `base: "main"`, `draft: false` (unless requested), and `body` listing only checks actually executed:

     ```markdown
     ## Summary

     Closes #<ISSUE_NUMBER>

     - **Root Cause / Motivation:** <concise explanation>
     - **Key Changes:**
       - <bulleted summary of architectural and code changes>

     ---

     ## Verification & Local CI

     - [x] Pre-commit & Hygiene (`<exact command>`): Passed
     - [x] Static Analysis / Type Checking (`<exact command>`): Passed
     - [x] Test Suite (`<exact command>`): `<N> passed[, <M> skipped]`
     ```

   - If `create_pull_request` or `update_pull_request` returns `"An interactive form has been shown..."`, run `github_mcp_launcher.py --refresh-live` and retry immediately (never claim a form rendered or ask the user to click Submit).

---

### Stage 5: Autonomous Remote CI Monitoring, Review Thread Resolution & Self-Healing Loop

**Never hand off a Pull Request immediately after creation or push.** Wait for all remote GitHub Actions check runs on `HEAD` to complete and self-heal failures.

1. **Wait & Poll Remote Check Runs (`github-mcp-server` Primary):**
   - Capture `HEAD_SHA=$(git rev-parse HEAD)` and use `schedule` (~20–30 s timer, never blocking shell `sleep` loops) between polls:
     1. `pull_request_read` (`method: "get_check_runs"`, `owner`, `repo`, `pullNumber: <PR_NUMBER>`).
     2. `actions_list` (`method: "list_workflow_runs"`, `owner`, `repo`, `workflow_runs_filter: {"branch": "<branch-name>"}` — native JSON object, **never** a JSON-encoded string).
   - Poll until all check runs matching `HEAD_SHA` report `status == "completed"`.

2. **Check Review Threads & Base Branch Currency:**
   - Call `pull_request_read` (`"get_review_comments"` — paginate with `after` if `hasNextPage` — and `"get"`).
   - Fix actionable comments locally, re-run **Stage 3** + push, reply via `add_reply_to_pull_request_comment` (`owner`, `repo`, `pullNumber`, numeric `commentId`, `body`), and resolve via `pull_request_review_write` (`method: "resolve_thread"`, passing `owner`, `repo`, `pullNumber`, AND `threadId: "<PRRT_node_id>"`).
   - If behind `main` under `required_linear_history` (default on `Panoptic-Huginn` and `jamielapointe`), **do NOT** call `update_pull_request_branch` (merge-commit only); run `git fetch origin main && git rebase origin/main`, re-run **Stage 3**, and `git push --force-with-lease origin HEAD`.

3. **Evaluate Remote CI Outcome:**
   - All runs `completed` with `conclusion == "success"` (or `"skipped"` / `"neutral"`, `0` failures) -> **Stage 6**.
   - Any `"failure"` / `"cancelled"` / `"timed_out"` / `"action_required"` -> **Remote CI Remediation Loop** (max 5 iterations):
     - **5a — Logs:** Locate failing `run_id` via `actions_list` (`list_workflow_runs`, `list_workflow_jobs` with `resource_id: "<run_id>"`), then `get_job_logs` (`{"owner": "<owner>", "repo": "<repo>", "run_id": <FAILED_RUN_ID>, "failed_only": true, "return_content": true, "tail_lines": 500}`; fallback: `gh run view <FAILED_RUN_ID> -R "<owner>/<repo>" --log-failed`).
     - **5b–5d — Diagnose, Fix, Stage 3 Re-Verify, Push & Re-Poll:** Fix root cause locally, re-verify **Stage 3**, commit (`fix(ci): resolve remote <job-name> failure (#<ISSUE_NUMBER>)`), `git push origin HEAD`, and re-poll new `HEAD_SHA`. Halt and report after 5 iterations or external outages.

---

### Stage 6: Antigravity Walkthrough & Human Merge Handoff

1. Confirm `git status` is clean and `git rev-parse HEAD` matches `git rev-parse origin/<branch-name>`.
2. **Do NOT autonomously merge** (`merge_pull_request` / `gh pr merge` **only** if explicitly requested by the user) and **do NOT delete the branch**.
3. Present a concise summary (and update `walkthrough.md` if in `/plan` mode): **Linked Issue** (`#<ISSUE_NUMBER>` URL), **Remote Branch** + `<HEAD_SHA>`, **Pull Request** (`#<PR_NUMBER>` URL), **Local CI Summary**, **Remote CI Summary** (`SUCCESS` per job), and **Merge Readiness** (rulesets satisfied, ready for human Squash Merge).

---

## References

- [references/mcp-tool-reference.md](references/mcp-tool-reference.md): `mimir-agent-kit_github` (`v2.2.0`) MCP Apps anti-hallucination & `--refresh-live` runbook, schemas, dual-owner routing, and excluded tools.
- [references/gh-cli-fallback.md](references/gh-cli-fallback.md): Keyring `gh` auth & scope diagnostics, `--body-file -` LaTeX/Markdown safety, GraphQL `resolveReviewThread`, and Cloud Remote Agent `gh` recipes.
- [references/local-ci-matrix.md](references/local-ci-matrix.md): Full multi-ecosystem Stage 3 pre-commit CI detection and command matrix.
