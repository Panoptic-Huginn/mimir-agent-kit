---
name: github-flow-lifecycle
description: >-
  Enforces end-to-end Git and GitHub Flow best practices using github-mcp-server
  and local Git/CI tools, including GitHub issue resolution/creation, ruleset
  inspection, linked remote feature branching, mandatory pre-commit local CI
  verification, pull request creation, review thread resolution, and autonomous
  remote GitHub Actions CI monitoring and self-healing. Use whenever implementing
  features, fixing bugs, refactoring code, creating commits, or opening and
  updating pull requests.
metadata:
  version: v1
  publisher: jamielapointe
---

# Git & GitHub Flow Lifecycle Protocol

This skill governs the complete software delivery lifecycle from initial task intake through a fully verified, green Pull Request ready for human review and merge.

## Related Skills

- **`/ada-spark-pro`**: Formally verified SPARK Ada 2022 (`GNAT 16.1+`, `gnatprove 16.1+`, `alr 2.1+`) safety-critical robotics kernels and Silver/Gold deductive proofs.
- **`/python-pro`**: Python 3.14+ (`pixi` and `uv`), `ruff`, `mypy`, `pytest`, and `rumdl` standards.
- **`/rust-pro`**: Safety-critical Rust 1.99.1+ (`pixi`, `clippy`, `cargo fmt`, Google Rust Styleguide) systems software.
- **`/cmake-pro`**: Modern CMake 4.4.3+ (`CMakePresets.json` v10+, `cmake --workflow --preset`, `gersemi`) standards.
- **`/c-pro`**: Modern ISO C23 (`-std=c23`, `clang-tidy`, `clang-format`, CERT C / MISRA C, sanitizers) systems and robotics safety standards.
- **`/cpp-pro`**: Modern C++23 (`clang-tidy`, `clang-format`, Google Test, Google Benchmark, sanitizers) standards.
- **`/jupyter-pro`**: Interactive Jupyter Notebook and Google Colab workflows and clean-output hygiene.
- **`/marimo-pro`**: Reactive marimo Python notebooks, `mo.ui` widgets, DAG execution, and `pixi`/`uv` toolchains.
- **`/marimo-pair`**: Live marimo kernel driving and durable notebook commits via `marimo._code_mode`.

---

## 1. High-Thinking Pre-Execution Directives

During your internal reasoning pass before every tool invocation, verify the following state invariants:

1. **Branch Isolation Check:** Confirm the active local Git branch is **NEVER** `main`, `master`, or a detached `HEAD` before modifying, staging, or committing files.
2. **MCP-First / Keyring-Backed Auth / Local-Git Boundary:**
   - Use **`github-mcp-server`** (plugin-namespaced as lazy-loaded `mimir-agent-kit_github` via `call_mcp_tool`, or registered globally as `github`) as the primary interface for all remote GitHub operations.
   - Authentication flows from `gh auth token --hostname github.com` (OS keyring: Ubuntu `libsecret` / macOS Keychain) into the container environment at launch, so one login spans both personal accounts (`jamielapointe`) and GitHub Enterprise Cloud organizations (`Panoptic-Huginn`) without PATs on disk. Note two upstream org tools are excluded via `GITHUB_EXCLUDE_TOOLS` to fit Antigravity's 64-char limit (see [references/mcp-tool-reference.md](references/mcp-tool-reference.md)).
   - **Degraded-Mode Fallback (`gh` CLI):** If `mimir-agent-kit_github` fails to start or is unavailable (e.g., Docker stopped while traveling on macOS, or inside Cloud Remote Agents where local stdio containers do not run), use the equivalent **Permitted Fallback** via `gh` CLI + `--body-file -` heredocs in [references/gh-cli-fallback.md](references/gh-cli-fallback.md). If `gh auth status` reports logged out, halt and ask the user to run `gh auth login --hostname github.com`.
   - Use **local workspace file tools and local `git` CLI** for all file edits, staging (`git add`), committing (`git commit`), and pushing (`git push`). **NEVER** use remote file-mutation tools (`create_or_update_file`, `push_files`, `delete_file`), as they bypass `.pre-commit-config.yaml` hooks and local CI gates.
3. **Verification-Before-Commit:** Never execute `git commit` (and never pass `--no-verify` or `-n`) until the full local CI suite—matching all applicable local tooling and `.github/workflows/*.yml` PR checks—has executed on the current working tree and exited with code `0`.
4. **No Autonomous Merge:** Your authority terminates once the Pull Request is open, all review threads are resolved, and all remote GitHub CI checks report `SUCCESS` (`conclusion == "success"`). Merging to `main` is strictly reserved for the human user.

---

## 2. Tool Boundary Matrix (`github-mcp-server` vs. `gh` Fallback & Local CLI)

| Operation | Primary (`mimir-agent-kit_github`) | Permitted Fallback | Forbidden | Reason |
| :--- | :--- | :--- | :--- | :--- |
| **User Context & Rulesets** | `get_me`; `repository_ruleset_read` (`level: "repository"`, `method: "get_rules_for_branch"`, `branch: "main"` — `[]`/404 = unprotected) | `gh api "repos/<o>/<r>/rules/branches/main"`, `gh ruleset check main -R <o>/<r>` | Guessing rulesets; `level: "organization"` without `admin:org` scope | Identifies linear history, squash rules, and required checks across personal & GHEC org repos |
| **Issues & Labels** | `search_issues`, `list_issues` (`perPage: 10`); `issue_read`; `issue_write`; `sub_issue_write`; `list_label`; `list_issue_types` (`owner`+`repo`) | `gh issue list/view/create -R <o>/<r> --body-file -` | Inline `--body` on LaTeX/code; working without an issue | Preserves structured metadata and deterministic issue tracking |
| **Branch Creation** | Local `git checkout -b "<branch>" && git push -u origin HEAD` or `create_branch` + `git fetch` + checkout | `gh issue develop <N> -R <o>/<r> --checkout --name "<branch>"` | Committing on `main`, `master`, or detached `HEAD` | Keeps local working tree and remote tracking ref aligned |
| **Edits & Commits** | Local file tools (`edit_file`, `write_file`) + `git add` & `git commit` | None | `push_files`, `create_or_update_file`, `delete_file`, `git commit --no-verify` | Remote API file writes bypass local pre-commit hooks and tests |
| **Pushing Commits** | `git push -u origin HEAD` / `git push origin HEAD` (`--force-with-lease origin HEAD` *only* on rebased feature branch) | None | `push_files`, `git push --force`, force-pushing shared branches | Keeps linear history safely without overwriting shared refs |
| **PR Creation & Sync** | `list_pull_requests` (`head: "<owner>:<branch>"`, omit `body`), `create_pull_request` (`head: "<branch>"`), `update_pull_request` | `gh pr create -R <o>/<r> --body-file -`, `gh pr edit`, `gh pr update-branch --rebase` | `update_pull_request_branch` on `required_linear_history`; pushing/merging to `main` | Enforces squash/linear-history rules and `Closes #<N>` linkage |
| **PR Reviews & Threads** | `pull_request_read` (`get_reviews`, `get_review_comments`, `get_comments`); `add_reply_to_pull_request_comment`; `pull_request_review_write` (`resolve_thread` with `owner`, `repo`, `pullNumber`, `threadId`) | `gh api graphql` (`resolveReviewThread`, see [references/gh-cli-fallback.md](references/gh-cli-fallback.md)) | Leaving threads open under `required_review_thread_resolution` | Satisfies review-thread merge gates (`gh pr view --comments` cannot resolve) |
| **Remote CI & Logs** | `pull_request_read` (`get_check_runs`, `get_status`), `actions_list`, `actions_get`, `get_job_logs` (`failed_only: true`, `return_content: true`) | `gh pr checks`, `gh run list -R <o>/<r>`, `gh run view <id> --log-failed` (no `--watch`) | Handing off before `HEAD_SHA` checks reach `completed` | Enables deterministic autonomous remote CI self-healing |
| **Merge PR** | **HUMAN ONLY** | **NONE** | `merge_pull_request`, `gh pr merge`, `git merge` into `main` | Human review and merge sign-off is strictly mandatory |

---

## 3. Entry-State Decision Tree

Evaluate local workspace and remote GitHub state before modifying any repository files (consult [references/mcp-tool-reference.md](references/mcp-tool-reference.md) for `v2.1.0` parameter details):

1. **Workspace is on `main` or `master` with uncommitted edits:**
   - Stash local changes immediately: `git stash push -u -m "wip: pre-branching stash"`.
   - Execute **Stage 1** (Issue Resolution) and **Stage 2** (Remote-Linked Branch Creation).
   - Apply the stash onto the new feature branch (`git stash pop`), then proceed to **Stage 3**.
2. **User provided an existing GitHub Issue number (`#<ISSUE_NUMBER>`):**
   - Call `issue_read` (`method: "get"` and `method: "get_comments"`) to extract requirements and acceptance criteria.
   - Skip issue creation in **Stage 1** and proceed directly to **Stage 2**.
3. **Workspace is already on a feature branch with an open PR that has failing CI or review comments:**
   - Call `list_pull_requests` (`head: "<head-owner>:<branch>"`, `fields: ["number","title","state","html_url","mergeable_state"]`) and `pull_request_read` (`method: "get"`, `"get_check_runs"`, `"get_review_comments"`).
   - Jump directly to **Stage 5** (Autonomous Remote CI Monitoring & Self-Healing Loop).
4. **Standard New Task (Clean workspace on `main`, no existing issue specified):**
   - Execute **Stages 1 through 6** sequentially without skipping any stage.

---

## 4. Six-Stage Execution State Machine

### Stage 1: Repository Context & Issue Resolution (`github-mcp-server`)

1. **Inspect User Context, Owner Identity & Branch Rulesets:**
   - Parse repository `owner` and `repo` from `git remote get-url origin` (handles both `git@github.com:<owner>/<repo>.git` and `https://github.com/<owner>/<repo>.git`).
   - Call `get_me` to identify the acting `login` (`jamielapointe`). **Critical Dual-Owner Rule:** For organization repositories (e.g., `Panoptic-Huginn/*`), keep `owner: "<org>"` on all repo/issue/PR/Actions calls and pass `get_me.login` only to `assignees` or fork prefixes.
   - Call `repository_ruleset_read` (`level: "repository"`, `method: "get_rules_for_branch"`, `owner`, `repo`, `branch: "main"`). Default `gh` OAuth scopes cover inherited rulesets here across both personal and GHEC org repos (whereas `level: "organization"` requires `admin:org`); treat `[]` or `404` on personal repos as unprotected. Check `required_linear_history`, `allowed_merge_methods`, `required_review_thread_resolution`, and required status check contexts.
2. **Search for Existing Open Issues:**
   - Query `search_issues` (`query: "repo:<owner>/<repo> is:issue is:open <keywords>"`, `perPage: 10`) or `list_issues` (`state: "OPEN"`, `perPage: 10`) to avoid duplicate issues.
3. **Create Issue (If None Exists):**
   - Call `list_label` (`owner`, `repo`) and optionally `list_issue_types` (`owner`, `repo`); omit `type` unless `list_issue_types` returns enabled entries.
   - Call `issue_write` (`method: "create"`) with:
     - **`title`**: `<type>(<scope>): <concise summary>` (e.g., `feat(estimators): ...`, `fix(ci): ...`, `refactor(core): ...`, `perf(kernels): ...`, `test(unit): ...`, `docs(thesis): ...`, `chore(deps): ...`)
     - **`body`**: Structured Markdown containing **Problem Statement**, **Technical Scope**, and **Verifiable Acceptance Criteria**.
     - **`labels`**: Applicable labels from `list_label` (e.g., `["enhancement"]`, `["bug"]`, `["documentation"]`).
     - **`assignees`**: `[<login from get_me>]` if appropriate.
4. Record the resulting `<ISSUE_NUMBER>` for all subsequent branch, commit, and PR operations.

---

### Stage 2: Remote-Linked Branch Creation

1. **Synchronize Local Default Branch:**

   ```bash
   git checkout main
   git pull --ff-only origin main
   ```

2. **Create and Push Feature Branch:**
   - Format branch name as `<type>/<ISSUE_NUMBER>-<short-kebab-slug>` (e.g., `feat/131-rotational-factor-graph`, `fix/142-pit-calibration-bound`).
   - **Option A (Local Git + Remote Tracking — Always Reliable):**

     ```bash
     git checkout -b "<type>/<ISSUE_NUMBER>-<short-kebab-slug>"
     git push -u origin HEAD
     ```

   - **Option B (Remote Creation via `github-mcp-server` `create_branch` + Local Checkout):**
     Call `create_branch` (`branch: "<type>/<ISSUE_NUMBER>-<short-kebab-slug>"`, `from_branch: "main"`), then run:

     ```bash
     git fetch origin
     git checkout -b "<type>/<ISSUE_NUMBER>-<short-kebab-slug>" "origin/<type>/<ISSUE_NUMBER>-<short-kebab-slug>"
     ```

   - **Option C (Optional `gh issue develop` Link):**
     If `gh` CLI is authenticated and permitted in the shell, `gh issue develop <ISSUE_NUMBER> --checkout --name "<type>/<ISSUE_NUMBER>-<short-kebab-slug>"` may be used. *(Note: Including `Closes #<ISSUE_NUMBER>` in the Stage 4 PR body automatically links the PR and branch to the issue on GitHub even without `gh issue develop`.)*
3. **Verify Branch Isolation Invariant:**

   ```bash
   git branch --show-current
   ```

   **Abort immediately** if the output is `main`, `master`, or empty.

---

### Stage 3: Implementation & Mandatory Pre-Commit Local CI Gate

1. **Implement Scoped Changes & Tests:**
   - Implement the feature, bugfix, or refactor adhering to workspace rules (`AGENTS.md`) and language skills (`/python-pro`, `/rust-pro`, `/cmake-pro`, `/cpp-pro`, `/marimo-pro`).
   - Add or update unit/integration tests covering the new behavior or bugfix.
2. **Inspect `.github/workflows/*.yml` for PR Job Parity:**
   - Check all workflows in `.github/workflows/` triggered by `pull_request` (e.g., `ci.yml`) so you know every check that remote GitHub Actions will execute.
3. **Detect and Execute the Full Local CI Pipeline BEFORE `git commit`:**
   Inspect `.github/workflows/*.yml` and the repository root, then run all applicable checks until every step exits with code `0` cleanly (without further formatter edits). Quick reference (full ecosystem table in [references/local-ci-matrix.md](references/local-ci-matrix.md)):

   - **Antigravity Plugin (`scripts/ci/run_local_ci.sh`):** `./scripts/ci/run_local_ci.sh`
   - **Pixi / Python / Cross-Ecosystem (`pixi.lock`):** `pixi run pre-commit run --all-files --show-diff-on-failure`, `pixi run ruff check` & `ruff format --check`, `pixi run mypy`, `pixi run pytest`, `pixi run build` (if defined)
   - **Pure `uv` Python (`uv.lock`):** `uv run pre-commit run --all-files`, `uv run ruff check .` & `ruff format --check .`, `uv run mypy .`, `uv run pytest`
   - **C/C++23 (`CMakePresets.json`), Rust (`Cargo.toml`), Node, Go, Docs:** Run configured format/lint/test workflows per [references/local-ci-matrix.md](references/local-ci-matrix.md).

---

### Stage 4: Atomic Commit, Push & Pull Request Creation

1. **Workspace, DVC & Secret Hygiene Audit:**
   - Run `git status` and `git diff` to verify:
     - Zero untracked scratch scripts, temporary files, build artifacts (`dist/`, `build/`), or secrets (`.env`, `.dvc/config.local`) are staged.
     - In DVC-enabled repositories (`heimdall-astro`), raw data directories (`data/latest/`, `data/baseline/*.zarr`, `*.html`) are **never** staged in Git; if `data/baseline.dvc` was updated, confirm `pixi run dvc push` completed first.
2. **Stage and Commit Verified Changes (Never Use `--no-verify`):**

   ```bash
   git add <specific-modified-files>
   git commit -m "<type>(<scope>): <concise summary> (#<ISSUE_NUMBER>)"
   ```

   *(Keep the subject line under 72 characters; include a structured multi-bullet body explaining the **what** and **why** so squash-merges preserve full architectural context.)*
3. **Push Branch to Remote:**

   ```bash
   git push -u origin HEAD
   ```

4. **Create or Update Pull Request via `github-mcp-server`:**
   - Check if a PR template exists (`.github/pull_request_template.md` or `.github/PULL_REQUEST_TEMPLATE/`).
   - Call `list_pull_requests` (`owner`, `repo`, `head: "<head-owner>:<branch-name>"`, `state: "open"`, `fields: ["number","title","state","html_url","head"]`).
   - If no open PR exists, call `create_pull_request` (or `update_pull_request` if one already exists):
     - **`owner` / `repo`**: From `git remote get-url origin` (e.g., `Panoptic-Huginn` or `jamielapointe`).
     - **`title`**: `<type>(<scope>): <concise summary> (#<ISSUE_NUMBER>)`
     - **`head`**: `<branch-name>` (same-repo branch; `"<fork-owner>:<branch-name>"` only for cross-fork PRs)
     - **`base`**: `main`
     - **`draft`**: `false` (unless the user explicitly requested a draft PR)
     - **`body`**:

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

       Note: Only list checks actually executed on the current working tree.

---

### Stage 5: Autonomous Remote CI Monitoring, Review Thread Resolution & Self-Healing Loop

**Never hand off a Pull Request immediately after creation or push.** You must wait for all remote GitHub Actions workflows and check runs on the pushed `HEAD` commit SHA to complete and self-heal any failures.

1. **Wait & Poll Remote Check Runs (`github-mcp-server` Primary):**
   - Capture `HEAD_SHA=$(git rev-parse HEAD)`.
   - Use the `schedule` tool for a ~20–30 second timer if waiting between polls (avoid blocking shell `sleep` loops), then poll using `github-mcp-server`:
     1. Call `pull_request_read` (`method: "get_check_runs"`, `owner`, `repo`, `pullNumber: <PR_NUMBER>`).
     2. Call `actions_list` (`method: "list_workflow_runs"`, `owner`, `repo`, `workflow_runs_filter: {"branch": "<branch-name>"}`).
   - Continue polling until all check runs matching `HEAD_SHA` have `status == "completed"`.

2. **Check Review Threads & Base Branch Currency:**
   - Call `pull_request_read` (`method: "get_review_comments"`, `owner`, `repo`, `pullNumber: <PR_NUMBER>` — paginate with `after` cursor if `hasNextPage` is true) and `pull_request_read` (`method: "get"`, `owner`, `repo`, `pullNumber: <PR_NUMBER>`).
   - If any actionable review comments exist, address them locally, verify Stage 3 + push, reply via `add_reply_to_pull_request_comment`, and resolve each thread via `pull_request_review_write` (`method: "resolve_thread"`, passing `owner`, `repo`, `pullNumber`, AND `threadId: "<PRRT_node_id>"` — required by JSON schema).
   - If the PR is behind `main`:
     - When `required_linear_history` is active (default across `Panoptic-Huginn` and `jamielapointe` rulesets), **do NOT** call `update_pull_request_branch` (it creates a merge commit). Run `git fetch origin main && git rebase origin/main`, re-run **Stage 3**, and push with `git push --force-with-lease origin HEAD`.
     - Only call `update_pull_request_branch` when linear history is *not* enforced and merge commits are permitted.

3. **Evaluate Remote CI Outcome:**
   - **All check runs & workflow runs report `status == "completed"` and `conclusion == "success"` (or `"skipped"` / `"neutral"` with `0` failures):** Proceed to **Stage 6**.
   - **Any check run or workflow run reports `conclusion == "failure"` / `"cancelled"` / `"timed_out"` / `"action_required"`:** Enter the **Remote CI Remediation Loop** below.

4. **Remote CI Remediation Loop (Max 5 Iterations):**
   - **Step 5a — Extract Failure Logs:** Identify failing `run_id` via `actions_list` (`list_workflow_runs`, then `list_workflow_jobs` with `resource_id: "<run_id>"`), then call `get_job_logs` (`{"owner": "<owner>", "repo": "<repo>", "run_id": <FAILED_RUN_ID>, "failed_only": true, "return_content": true, "tail_lines": 500}`). *(Fallback: `gh run view <FAILED_RUN_ID> -R "<owner>/<repo>" --log-failed`.)*
   - **Step 5b — Root-Cause Diagnosis:** Isolate code/test/typing/formatter differences, missing lockfile deps, OS/runner drift, workflow misconfiguration, or external GitHub/secret outages.
   - **Step 5c — Local Fix & Stage 3 Re-Verification:** Fix locally and re-run **Stage 3**. Never push speculative CI fixes without local verification.
   - **Step 5d — Commit, Push & Re-Poll:** Commit (`fix(ci): resolve remote <job-name> failure (#<ISSUE_NUMBER>)`), `git push origin HEAD`, and return to **Step 5.1** on the new `HEAD_SHA`.
   - **Circuit Breaker (Max 5 Iterations):** Halt and report failure logs, root cause, and attempted fixes to the user if remote CI still fails after 5 iterations or hits an unrecoverable permissions/infrastructure outage.

---

### Stage 6: Antigravity Walkthrough & Human Merge Handoff

Once local and remote CI pass (`0` failures) and all review threads are resolved:

1. Verify `git status` is clean and `git rev-parse HEAD` matches `git rev-parse origin/<branch-name>`.
2. **Do NOT merge the Pull Request** (`merge_pull_request` and `gh pr merge` are strictly forbidden) and **do NOT delete the branch**.
3. Present a concise completion summary (updating `walkthrough.md` if in `/plan` mode) with: **Linked Issue** (`#<ISSUE_NUMBER>` URL), **Remote Branch** + `<HEAD_SHA>`, **Pull Request** (`#<PR_NUMBER>` URL), **Local CI Summary** (exact commands + pass/skip counts), **Remote CI Summary** (`SUCCESS` per job), and **Merge Readiness** confirmation (rulesets satisfied, ready for human Squash Merge).

---

## References

- [references/mcp-tool-reference.md](references/mcp-tool-reference.md): `mimir-agent-kit_github` (`v2.1.0`) schemas, dual-owner routing, JSON schema quirks, excluded tools.
- [references/gh-cli-fallback.md](references/gh-cli-fallback.md): Keyring `gh` auth diagnostics, `--body-file -` LaTeX/Markdown safety, GraphQL `resolveReviewThread`, and full `gh` fallback recipes.
- [references/local-ci-matrix.md](references/local-ci-matrix.md): Full multi-ecosystem Stage 3 pre-commit CI detection and command matrix.
