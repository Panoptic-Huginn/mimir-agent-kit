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

- **`/python-pro`**: Python 3.14+ (`pixi` and `uv`), `ruff`, `mypy`, `pytest`, and `rumdl` standards.
- **`/cmake-pro`**: Modern CMake 4.4.3+ (`CMakePresets.json` v10+, `cmake --workflow --preset`, `gersemi`) standards.
- **`/c-pro`**: Modern ISO C23 (`-std=c23`, `clang-tidy`, `clang-format`, CERT C / MISRA C, sanitizers) systems and robotics safety standards.
- **`/cpp-pro`**: Modern C++23 (`clang-tidy`, `clang-format`, Google Test, Google Benchmark, sanitizers) standards.
- **`/jupyter-pro`**: Interactive Jupyter Notebook and Google Colab workflows and clean-output hygiene.
- **`/accidental-data-loss-prevention`**: Mandatory user consent before any destructive data or branch deletion operations.

---

## 1. High-Thinking Pre-Execution Directives

During your internal reasoning pass before every tool invocation, verify the following state invariants:

1. **Branch Isolation Check:** Confirm the active local Git branch is **NEVER** `main`, `master`, or a detached `HEAD` before modifying, staging, or committing files.
2. **MCP-First / Local-Git Boundary Enforcement:**
   - Use **`github-mcp-server`** (registered globally as `github-mcp-server` or plugin-namespaced as `mimir-agent-kit_github-mcp-server` / `<plugin>_github-mcp-server`) as the primary interface for all remote GitHub platform operations (Issues, Pull Requests, Rulesets, Labels, Check Runs, Workflow Runs, Job Logs, and Review Threads).
   - Use **local workspace file tools and local `git` CLI** for all file edits, staging (`git add`), committing (`git commit`), and pushing (`git push`). **NEVER** use `github-mcp-server` remote file-mutation tools (`create_or_update_file`, `push_files`, `delete_file`), as they bypass the local working tree, `.pre-commit-config.yaml` hooks, and local CI gates.
3. **Verification-Before-Commit:** Never execute `git commit` (and never pass `--no-verify` or `-n`) until the full local CI suite—matching all applicable local tooling and `.github/workflows/*.yml` PR checks—has executed on the current working tree and exited with code `0`.
4. **No Autonomous Merge:** Your authority terminates once the Pull Request is open, all review threads are addressed, and all remote GitHub CI checks report `SUCCESS` (`conclusion == "success"`). Merging to `main` is strictly reserved for the human user.
5. **Mechanical Hook Enforcement:** The companion `PreToolUse` hook ([scripts/git_github_guard.py](../../scripts/git_github_guard.py), bundled via `hooks.json` at the plugin root) mechanically blocks `merge_pull_request`, `gh pr merge`, remote MCP file mutations (`push_files`, `create_or_update_file`, `delete_file`) across both global (`github-mcp-server`) and plugin-namespaced (`<plugin>_github-mcp-server`) servers, `git commit --no-verify`, force-pushes to `main`/`master`, and `git commit` while on `main`/`master`.

---

## 2. Tool Boundary Matrix (`github-mcp-server` vs. Local CLI)

| Operation | Primary Required Mechanism | Permitted Fallback | Forbidden Mechanism | Reason |
| :--- | :--- | :--- | :--- | :--- |
| **User Context & Branch Rulesets** | `github-mcp-server`:<br>• `get_me`<br>• `repository_ruleset_read` (`level: "repository"`, `method: "get_rules_for_branch"`, `branch: "main"`) | `gh ruleset list` / `gh api` | Guessing branch protection rules | Identifies squash-only merge rules, linear history requirements, and required status checks upfront |
| **Search / Read / Create / Update Issues** | `github-mcp-server`:<br>• `search_issues`, `list_issues`<br>• `issue_read` (`method: "get" \| "get_comments" \| "get_sub_issues" \| "get_labels"`)<br>• `issue_write` (`method: "create" \| "update"`)<br>• `sub_issue_write` (`method: "add"`), `list_label` | `gh issue list / view / create` | Unstructured web scraping or working without an issue | Structured metadata, label validation, and deterministic issue number tracking |
| **Branch Creation & Checkout** | Local shell (`git checkout -b "<branch>" && git push -u origin HEAD`) or `github-mcp-server` (`create_branch`) + `git fetch origin && git checkout "<branch>"` | `gh issue develop <N> --checkout --name "<branch>"` | Committing directly on `main` or `master` | Guarantees local working tree and tracking ref match remote branch |
| **File Edits, Staging & Commits** | Local file tools (`edit_file`, `write_file`) + local `git add <files>` & `git commit` | None | `github-mcp-server` (`push_files`, `create_or_update_file`, `delete_file`), `git commit --no-verify` | Remote API file commits bypass local pre-commit hooks, linters, and local test suites |
| **Pushing Commits** | Local shell (`git push -u origin HEAD` / `git push origin HEAD`) | None | `github-mcp-server` (`push_files`), `git push --force` on shared branches | Preserves local-to-remote commit SHA parity and pre-push hooks |
| **Pull Request Creation & Updates** | `github-mcp-server`:<br>• `list_pull_requests`<br>• `create_pull_request`<br>• `update_pull_request`<br>• `update_pull_request_branch` | `gh pr create` / `gh pr edit` | Direct push or local merge to `main` | Enforces code review, ruleset compliance, and automatic `Closes #<ISSUE_NUMBER>` linkage |
| **PR Reviews & Thread Resolution** | `github-mcp-server`:<br>• `pull_request_read` (`method: "get_reviews" \| "get_review_comments" \| "get_comments"`)<br>• `add_reply_to_pull_request_comment`<br>• `pull_request_review_write` (`method: "resolve_thread"`) | `gh pr view --comments` | Leaving review threads unresolved when `required_review_thread_resolution` is active | Satisfies ruleset merge readiness requirements |
| **Remote CI Status & Failure Logs** | `github-mcp-server`:<br>• `pull_request_read` (`method: "get_check_runs" \| "get_status"`)<br>• `actions_list` (`method: "list_workflow_runs" \| "list_workflow_jobs"`)<br>• `actions_get` (`method: "get_workflow_run" \| "get_workflow_job"`)<br>• `get_job_logs` (`run_id`, `failed_only: true`, `return_content: true`) | `gh run list`, `gh run view <id> --log-failed` (avoid `--watch` in non-TTY shells) | Assuming remote CI passed without polling to `completed` | Enables deterministic, autonomous self-healing of remote GitHub Actions failures |
| **Merging Pull Request** | **HUMAN ONLY** | **NONE** | `github-mcp-server` (`merge_pull_request`), `gh pr merge`, `git merge` into `main` | Human review and merge sign-off is strictly mandatory |

---

## 3. Entry-State Decision Tree

Evaluate the local workspace and remote GitHub state before writing or modifying any repository files:

1. **Workspace is on `main` or `master` with uncommitted edits:**
   - Stash local changes immediately: `git stash push -u -m "wip: pre-branching stash"`.
   - Execute **Stage 1** (Issue Resolution) and **Stage 2** (Remote-Linked Branch Creation).
   - Apply the stash onto the new feature branch (`git stash pop`), then proceed to **Stage 3**.
2. **User provided an existing GitHub Issue number (`#<ISSUE_NUMBER>`):**
   - Call `github-mcp-server` `issue_read` (`method: "get"`, `issue_number: <ISSUE_NUMBER>`) and `issue_read` (`method: "get_comments"`) to extract requirements and acceptance criteria.
   - Skip issue creation in **Stage 1** and proceed directly to **Stage 2**.
3. **Workspace is already on a feature branch with an open PR that has failing CI or review comments:**
   - Call `github-mcp-server` `list_pull_requests` (`head: "<owner>:<branch>"`) and `pull_request_read` (`method: "get"`, `method: "get_check_runs"`, `method: "get_review_comments"`).
   - Jump directly to **Stage 5** (Autonomous Remote CI Monitoring & Self-Healing Loop).
4. **Standard New Task (Clean workspace on `main`, no existing issue specified):**
   - Execute **Stages 1 through 6** sequentially without skipping any stage.

---

## 4. Six-Stage Execution State Machine

### Stage 1: Repository Context & Issue Resolution (`github-mcp-server`)

1. **Inspect User Context & Branch Rulesets:**
   - Identify `owner` and `repo` from `git remote get-url origin`.
   - Call `github-mcp-server` `get_me` and `repository_ruleset_read` (`level: "repository"`, `method: "get_rules_for_branch"`, `branch: "main"`) to check active constraints (e.g., `required_linear_history`, `allowed_merge_methods: ["squash"]`, `required_review_thread_resolution`).
2. **Search for Existing Open Issues:**
   - Query `github-mcp-server` `search_issues` (`query: "repo:<owner>/<repo> is:issue is:open <keywords>"`) or `list_issues` (`state: "OPEN"`, `perPage: 10`) to avoid creating duplicate issues.
3. **Create Issue (If None Exists):**
   - Call `list_label` on the repository to identify valid label names (do not pass `type` to `issue_write` unless `list_issue_types` succeeds for the organization).
   - Call `github-mcp-server` `issue_write` (`method: "create"`) with:
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
   - Implement the feature, bugfix, or refactor adhering to workspace rules (`AGENTS.md`) and language skills (`/python-pro`, `/cmake-pro`, `/cpp-pro`).
   - Add or update unit/integration tests covering the new behavior or bugfix.
2. **Inspect `.github/workflows/*.yml` for PR Job Parity:**
   - Check all workflows in `.github/workflows/` triggered by `pull_request` (e.g., `ci.yml`) so you know every check that remote GitHub Actions will execute.
3. **Detect and Execute the Full Local CI Pipeline BEFORE `git commit`:**
   Inspect the repository root and run **all** applicable checks in order:

   | Ecosystem / Build Files Detected | Required Local CI Commands (Run All Applicable) |
   | :--- | :--- |
   | **`pixi.lock` / `pixi.toml` / `[tool.pixi]` in `pyproject.toml`** (Pixi Python / Cross-Ecosystem, e.g., `heimdall-astro`) | 1. `pixi run pre-commit run --all-files --show-diff-on-failure` (or `pixi run pre-commit`)<br>2. `pixi run ci-hygiene` (if defined in `[tool.pixi.tasks]`)<br>3. `pixi run ruff check` && `pixi run ruff format --check`<br>4. `pixi run mypy` (or `pixi run typecheck`)<br>5. `pixi run pytest tests/unit` (or `pixi run test -m "not live_fire"`)<br>6. `pixi run build` (if package build job exists in `ci.yml`) |
   | **`pyproject.toml` + `uv.lock` (without Pixi)** (Pure `uv` Python) | 1. `uv run pre-commit run --all-files` (if `.pre-commit-config.yaml` exists)<br>2. `uv run ruff check .` && `uv run ruff format --check .`<br>3. `uv run mypy .`<br>4. `uv run pytest`<br>5. `uv build` (if package build check applies) |
   | **`.pre-commit-config.yaml` / `lefthook.yml`** (Standalone) | `pre-commit run --all-files --show-diff-on-failure` or `lefthook run pre-commit` |
   | **`CMakePresets.json` / `CMakeLists.txt`** (C/C++23 — `/cmake-pro` & `/cpp-pro`) | 1. `gersemi --check CMakeLists.txt cmake/ src/ tests/` (if `.gersemirc` / `gersemi` installed)<br>2. `clang-format --dry-run --Werror` & `clang-tidy` (if configured)<br>3. `cmake --workflow --preset <ci-or-dev-preset>` (or `cmake --preset <preset>` && `cmake --build --preset <preset>` && `ctest --preset <preset> --output-on-failure`) |
   | **`Justfile` / `Makefile` / `Taskfile.yml`** | Run dedicated check/CI targets (`just check`, `just ci`, `make check`, `make test`) |
   | **`Cargo.toml`** (Rust) | `cargo fmt --all -- --check` && `cargo clippy --all-targets -- -D warnings` && `cargo test` |
   | **`package.json`** (Node / TypeScript) | `npm run lint` && `npm run typecheck` (or `npx tsc --noEmit`) && `npm test` |
   | **`go.mod`** (Go) | `test -z "$(gofmt -l .)"` && `go vet ./...` && `go test -race ./...` |
   | **Markdown / Docs (`[tool.rumdl]` / MathJax)** | `rumdl check .` (or via `pre-commit`) and MathJax/LaTeX delimiter checks |

4. **Local Self-Correction Loop:**
   - If *any* pre-commit hook, formatter, linter, static type checker, compiler warning, package build, or test fails (or modifies files during auto-fix), fix the root cause in the working tree and **re-run the local CI suite** until every check exits with code `0` on a clean pass without further file modifications.

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
   - Call `github-mcp-server` `list_pull_requests` (`owner`, `repo`, `head: "<owner>:<branch-name>"`, `state: "open"`).
   - If no open PR exists, call `github-mcp-server` `create_pull_request` (or `update_pull_request` if one already exists):
     - **`owner`**: `<owner>`
     - **`repo`**: `<repo>`
     - **`title`**: `<type>(<scope>): <concise summary> (#<ISSUE_NUMBER>)`
     - **`head`**: `<branch-name>`
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

       - [x] Pre-commit & Hygiene (`<command>`): Passed
       - [x] Static Analysis / Type Checking (`<command>`): Passed
       - [x] Unit & Integration Test Suite (`<command>`): `<N> passed`
       - [x] Package Build (`<command>`): Passed
       ```

---

### Stage 5: Autonomous Remote CI Monitoring, Review Thread Resolution & Self-Healing Loop

**Never hand off a Pull Request immediately after creation or push.** You must wait for all remote GitHub Actions workflows and check runs on the pushed `HEAD` commit SHA to complete and self-heal any failures.

1. **Wait & Poll Remote Check Runs (`github-mcp-server` Primary):**
   - Capture `HEAD_SHA=$(git rev-parse HEAD)`.
   - Wait ~15 seconds for GitHub Actions workflows to register on `HEAD_SHA`, then poll using `github-mcp-server`:
     1. Call `pull_request_read` (`method: "get_check_runs"`, `owner`, `repo`, `pullNumber: <PR_NUMBER>`).
     2. Call `actions_list` (`method: "list_workflow_runs"`, `owner`, `repo`, `workflow_runs_filter: {"branch": "<branch-name>"}`).
   - *(Note: In Antigravity, use the `schedule` tool for a 20–30 second timer if waiting between polls rather than blocking shell `sleep` loops, or poll until all check runs matching `HEAD_SHA` have `status == "completed"`.)*

2. **Check Review Threads & Base Branch Currency:**
   - Call `pull_request_read` (`method: "get_review_comments"`, `owner`, `repo`, `pullNumber: <PR_NUMBER>`) and `pull_request_read` (`method: "get"`, `owner`, `repo`, `pullNumber: <PR_NUMBER>`).
   - If any actionable review comments exist, address them locally, reply via `add_reply_to_pull_request_comment`, and resolve the thread via `pull_request_review_write` (`method: "resolve_thread"`, `threadId: "<PRRT_node_id>"`).
   - If the PR is behind `main` and conflicts or linear-history rules require updating, rebase cleanly (`git fetch origin main && git rebase origin/main`) or call `update_pull_request_branch`.

3. **Evaluate Remote CI Outcome:**
   - **All check runs & workflow runs report `status == "completed"` and `conclusion == "success"` (or `"skipped"` / `"neutral"` with `0` failures):** Proceed to **Stage 6**.
   - **Any check run or workflow run reports `conclusion == "failure"` / `"cancelled"` / `"timed_out"` / `"action_required"`:** Enter the **Remote CI Remediation Loop** below.

4. **Remote CI Remediation Loop (Max 5 Iterations):**
   - **Step 5a — Extract Failure Logs via `github-mcp-server`:**
     1. Identify the failing `run_id` (and `job_id`) from `actions_list` (`method: "list_workflow_runs"` then `method: "list_workflow_jobs"`, `resource_id: "<run_id>"`).
     2. Call `github-mcp-server` `get_job_logs`:
        ```json
        {
          "owner": "<owner>",
          "repo": "<repo>",
          "run_id": <FAILED_RUN_ID>,
          "failed_only": true,
          "return_content": true,
          "tail_lines": 500
        }
        ```
        *(Fallback if needed: `gh run view <FAILED_RUN_ID> --log-failed`.)*
   - **Step 5b — Root-Cause Diagnosis:**
     Determine whether the failure is caused by:
     - Code, test, type-checking, or formatting discrepancy (e.g., dirty file modified by formatter, missing dependency in `pixi.lock`/`pyproject.toml`, OS/runner difference, unprovisioned test data).
     - Workflow/action configuration issue.
     - External GitHub infrastructure or secret/token outage.
   - **Step 5c — Local Fix & Mandatory Stage 3 Re-Verification:**
     Apply the fix in the local working tree and **re-run Stage 3 (Full Local CI Gate)**. Never push a speculative remote CI fix without verifying it locally first.
   - **Step 5d — Commit, Push & Re-Poll:**
     ```bash
     git add <modified-files>
     git commit -m "fix(ci): resolve remote <job-name> failure (#<ISSUE_NUMBER>)"
     git push origin HEAD
     ```
     Return to **Step 5.1** and poll remote checks on the new `HEAD_SHA`.
   - **Circuit Breaker (Max 5 Iterations):**
     If remote CI still fails after **5 full remediation iterations**, or fails due to an unrecoverable external secret/permissions/runner outage, **halt immediately** and report the exact failure logs, root-cause diagnosis, and attempted fixes to the user.

---

### Stage 6: Antigravity Walkthrough & Human Merge Handoff

Once all local CI checks and remote GitHub Actions check runs are green (`0` errors) and all review threads are resolved:

1. Verify that `git status` is clean (`nothing to commit, working tree clean`) and `git rev-parse HEAD` matches `git rev-parse origin/<branch-name>`.
2. **Do NOT merge the Pull Request** (`merge_pull_request` and `gh pr merge` are strictly forbidden) and **do NOT delete the branch**.
3. Present a concise completion summary (and update `walkthrough.md` if in `/plan` mode) containing:
   - **Linked Issue:** `#<ISSUE_NUMBER>` (with clickable GitHub URL)
   - **Remote Branch:** `<branch-name>` (verified synced with `origin` at `<HEAD_SHA>`)
   - **Pull Request:** `#<PR_NUMBER>` (with clickable GitHub URL)
   - **Local CI Summary:** Exact commands executed and pass counts (e.g., `pre-commit`, `ci-hygiene`, `ruff`, `mypy`, `pytest`, `build`)
   - **Remote GitHub CI Summary:** All workflow jobs (`Continuous Integration`, `OpenSSF Scorecard`, etc.) verified `SUCCESS` on `<HEAD_SHA>` via `github-mcp-server`
   - **Ruleset & Merge Readiness Notice:** Confirm that the PR satisfies repository rulesets (e.g., linear history, resolved review threads, squash-ready title/body) and is ready for **human review and manual Squash Merge to `main`**.
