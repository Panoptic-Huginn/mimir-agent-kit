---
name: github-ops
description: >-
  Manages non-code GitHub and GitHub Enterprise Cloud operations across personal
  accounts (jamielapointe) and enterprise organizations (Panoptic-Huginn) using
  mimir-agent-kit_github and gh CLI: repository provisioning and governance
  settings, organization and repository rulesets, custom properties,
  issue/sub-issue and GitHub Projects v2 planning, Dependabot/CodeQL/Secret
  Scanning/Scorecard security triage, releases, discussions, and cross-repo
  search. Use when administering repositories, organizations, backlogs,
  projects, security alerts, or releases without modifying local code or opening
  code pull requests.
metadata:
  version: v1
  publisher: jamielapointe
---

# GitHub & GitHub Enterprise Operations (`/github-ops`)

This skill governs **control-plane, metadata, governance, planning, security-triage, and release operations** across your two `github.com` resource owners—**`jamielapointe`** (Personal Account) and **`Panoptic-Huginn`** (`Himinbjörg Panoptes`, GitHub Enterprise Cloud Organization)—when you are **not** modifying local repository files or executing a Pull Request code-delivery cycle.

## Related Skills

- **`/github-flow-lifecycle`**: Mandatory 6-stage code-delivery protocol whenever modifying repository files, creating commits, or opening/updating Pull Requests.
- **`/python-pro`**: Python 3.14+ (`uv` and `pixi`) project conventions when bootstrapping or auditing Python repositories.
- **`/rust-pro`**: Safety-critical Rust 1.99.1+ repository conventions.
- **`/cmake-pro`**: Modern CMake 4.4.3+ (`CMakePresets.json` v10+) repository conventions.
- **`/c-pro`**: Deterministic ISO C23 systems repository conventions.
- **`/cpp-pro`**: High-performance ISO C++23 repository conventions.
- **`/ada-spark-pro`**: Formally verified SPARK Ada 2022 (`alr`, `gnatprove`) repository conventions.

---

## 1. Boundary & Governance Guardrails

1. **Stay in `/github-ops` for Control-Plane Work (No Dummy Feature Branches):**
   - Do **not** create feature branches or run local `pytest` suites when the user asks solely to triage/create issues or sub-issues, manage GitHub Projects v2, inspect or configure repository/organization settings and rulesets, audit Dependabot/CodeQL/Secret Scanning alerts, manage releases/tags/discussions, or search across repositories.
2. **Immediate Handoff to `/github-flow-lifecycle` When Editing Repo Files:**
   - The moment a task transitions from control-plane triage into **editing tracked files inside a repository** (for example, fixing a CodeQL or Dependabot vulnerability in code, adding `.github/workflows/ci.yml` or `renovate.jsonc`, or updating `README.md`), **immediately activate and follow `/github-flow-lifecycle`** (Issue -> `<type>/<N>-<slug>` branch -> local CI -> PR -> remote Actions verification).
3. **Explicit Human-Consent Gate for Destructive or Security-Weakening Mutations:**
   - Always obtain explicit user confirmation **before** executing any of the following:
     - Deleting, transferring, or archiving a repository (`delete_repository`, `gh repo delete`, `gh repo archive`, `gh repo rename`)
     - Changing repository visibility (`private` <-> `public` / `internal`)
     - Deleting or bypassing branch/organization rulesets, or removing required status checks
     - Deleting Git tags or published GitHub Releases
   - **Never** merge Pull Requests (`merge_pull_request` and `gh pr merge` are strictly forbidden even during triage sweeps).

---

## 2. Dual-Owner Capability & Keyring Scope Matrix

Both resource owners live on `github.com` and authenticate seamlessly through a single OS-keyring `gh` login (`libsecret` on Ubuntu, Login Keychain on macOS), consumed automatically by `mimir-agent-kit_github` (`scripts/github_mcp_launcher.py`, zero Docker) and `gh` CLI.

| Dimension | `Panoptic-Huginn/*` (GHEC Enterprise Org — Owner) | `jamielapointe/*` (Personal Account — Owner) |
| :--- | :--- | :--- |
| **MCP / API `owner` Param** | Always `"Panoptic-Huginn"` (never pass `get_me.login`) | `"jamielapointe"` |
| **Ruleset Hierarchy** | **Org-level** (`level: "organization"`, inherited across repos) **+** **Repo-level** (`level: "repository"`) | **Repo-level only** (`level: "repository"`; `[]` or `404` when none configured) |
| **Custom Properties** | **Supported** (`custom_properties_read`, `custom_properties_write`) | Not available on personal user accounts |
| **Issue Types & Sub-Issues** | Org Issue Types (`Bug`, `Feature`, `Task`, etc.) + Sub-Issues | Sub-Issues supported; call `list_issue_types` before setting `type` |
| **Teams & Reviewers** | Org teams (`get_teams`, `get_team_members`, `ORG/team-slug` reviewers) | Individual collaborator logins only |
| **Security & GHAS** | Dependabot, CodeQL, Secret Scanning, Org Security Advisories | Dependabot, Secret Scanning, and CodeQL (public repos; private per GHAS setting) |

### Keyring OAuth Scopes Diagnostic & One-Time Upgrade

Inspect active scopes with `gh auth status`. Different non-code operations require specific OAuth scopes on your `github.com` keyring token:

- **Baseline (`repo`, `read:org`, `gist`):** Repo CRUD, issues, PRs, repo-level ruleset reads (`includes_parents: true`), releases, Gists.
- **Projects v2 (`project`):** Required by `projects_list`, `projects_get`, `projects_write`.
- **Notifications (`notifications`):** Required by `list_notifications`, `dismiss_notification`, `manage_notification_subscription`.
- **Workflow Dispatch (`workflow`):** Required by `actions_run_trigger` (`gh workflow run` / `gh run rerun`) and workflow mutations.
- **GHEC Organization Administration (`admin:org`):** Required for `repository_ruleset_read(level: "organization")`, authoring org-wide rulesets on `Panoptic-Huginn`, and org team/member mutations (returns `404` without `admin:org`).

If a needed scope is missing, prompt the user (or run if interactive TTY is available):

```bash
gh auth refresh --hostname github.com --scopes repo,read:org,workflow,admin:org,project,notifications
```

---

## 3. Tool Routing: `mimir-agent-kit_github` MCP vs. `gh` CLI

Use **lazy-loaded `mimir-agent-kit_github`** (`call_mcp_tool`) as primary for typed JSON operations, paired with **`gh` / `gh api`** where GitHub's REST/GraphQL surface extends beyond MCP's schema:

| Domain | Primary (`mimir-agent-kit_github`) | `gh` / `gh api` Partner |
| :--- | :--- | :--- |
| **Repo Discovery & Provisioning** | `search_repositories`, `create_repository`, `get_repository_tree`, `list_branches`, `list_tags` | `gh api -X PATCH "repos/<o>/<r>"` to enforce Squash-only merge, `delete_branch_on_merge`, description/topics (see [references/ghec-governance-and-recipes.md](references/ghec-governance-and-recipes.md)) |
| **Rulesets & Custom Properties** | `repository_ruleset_read`, `create_repository_ruleset`, `custom_properties_read`, `custom_properties_write` | `gh api "orgs/Panoptic-Huginn/rulesets"` (create/update org-wide GHEC rulesets) |
| **Issues, Sub-Issues & Labels** | `search_issues`, `list_issues`, `issue_read`, `issue_write`, `sub_issue_write`, `list_issue_types`, `list_label`, `label_write` | `gh label clone <src-repo> -R <dst-repo>` to clone standard label taxonomy across repos |
| **GitHub Projects v2** | `projects_list`, `projects_get`, `projects_write` | `gh project list/view/item-add --owner <owner>` |
| **Security & Supply-Chain** | `list_dependabot_alerts`, `get_dependabot_alert`, `list_code_scanning_alerts`, `get_code_scanning_alert`, `list_secret_scanning_alerts`, `list_repository_security_advisories` | `gh api "/orgs/Panoptic-Huginn/security-advisories"` (excluded from MCP to stay `<= 64` chars) |
| **Releases, Discussions & Gists** | `list_releases`, `get_latest_release`, `get_release_by_tag`, `list_discussions`, `get_discussion`, `discussion_comment_write`, `list_gists`, `create_gist`, `update_gist` | `gh release create <tag> -R <o>/<r> --verify-tag --notes-file -` and binary asset uploads |
| **Cross-Repo Code & Commit Audit** | `search_code`, `get_file_contents`, `list_commits`, `get_commit`, `actions_list`, `get_job_logs` | Multi-repository `gh repo list <owner> --json ...` inventory sweeps |

---

## 4. Operational Runbooks

### Runbook A: Provisioning & Hardening a New Repository

1. Confirm target owner (`Panoptic-Huginn` vs. `jamielapointe`), repository name (kebab-case), visibility (`private` by default unless the user explicitly specifies `public`), and license/gitignore expectations.
2. Create the repository via `create_repository` (note: `create_repository` creates under the authenticated user unless an organization parameter is supported in schema; inspect `~/.gemini/antigravity/mcp/mimir-agent-kit_github/create_repository.json` first, and use `gh repo create "Panoptic-Huginn/<repo>" --private --description "..."` when creating directly inside `Panoptic-Huginn`).
3. Apply standard repository merge & hygiene settings via `gh api -X PATCH "repos/<owner>/<repo>"` (Squash-Merge only with `PR_TITLE` + `PR_BODY`, `allow_merge_commit: false`, `allow_rebase_merge: false`, `delete_branch_on_merge: true`, `allow_auto_merge: false` — exact payload in [references/ghec-governance-and-recipes.md](references/ghec-governance-and-recipes.md)).
4. Verify inherited org rulesets (`repository_ruleset_read` with `level: "repository"`, `method: "get_rules_for_branch"`, `branch: "main"`). If the repo is under `jamielapointe` (or needs repo-specific status checks), apply the canonical `main` branch ruleset via `create_repository_ruleset` (`required_linear_history`, `pull_request` with `required_review_thread_resolution: true`, `non_fast_forward`, `deletion`).
5. On `Panoptic-Huginn` repositories, populate any applicable Enterprise Custom Properties via `custom_properties_read` / `custom_properties_write`.
6. Once initial scaffolding files (`pyproject.toml`, `CMakeLists.txt`, `.github/workflows/ci.yml`, `renovate.jsonc`) are ready to be authored locally, hand off to **`/github-flow-lifecycle`** once `main` exists.

### Runbook B: Roadmap, Epics, Sub-Issues & GitHub Projects v2

1. Check enabled issue types via `list_issue_types` (`owner`, `repo`) and existing labels via `list_label` (`owner`, `repo`) before creating issues so you never invent nonexistent labels or unsupported `type` values.
2. Search open issues (`search_issues` with `perPage: 10`) to prevent duplicates.
3. Create parent Epic / tracking issues and child task issues via `issue_write` (`method: "create"`). Preserve LaTeX (`$...$`) and code blocks cleanly via MCP JSON strings (or `--body-file - <<'EOF'` if using `gh`).
4. Wire parent-child hierarchy via `sub_issue_write` (`method: "add"`, passing parent `issue_number` and child `sub_issue_id` — Note: `sub_issue_id` is the child issue's numeric **database `id`**, not its `#number`, returned by `issue_read` / `issue_write`).
5. Attach issues and update status/iteration fields on `Panoptic-Huginn` or `jamielapointe` boards using `projects_list`, `projects_get`, and `projects_write`.

### Runbook C: Multi-Repository Security & Supply-Chain Triage

1. Enumerate target repositories across `Panoptic-Huginn` and/or `jamielapointe` (`search_repositories` with `query: "org:Panoptic-Huginn"` or `query: "user:jamielapointe"`, or `gh repo list`).
2. For each active repository, check:
   - **Dependabot Alerts:** `list_dependabot_alerts` (`state: "open"`)
   - **CodeQL / Code Scanning:** `list_code_scanning_alerts` (`state: "open"`)
   - **Secret Scanning:** `list_secret_scanning_alerts` (`state: "open"`)
   - **Renovate Dependency Dashboard & OpenSSF Scorecard:** `search_issues` (`"Dependency Dashboard"`) and `actions_list` (`list_workflow_runs` on `scorecard.yml` / `ci.yml`).
3. Summarize findings prioritized by severity (`critical` -> `high` -> `medium` -> `low`) with clickable URLs. Do **not** dismiss security alerts without explicit user approval; if asked to patch a vulnerability in a repo, switch to **`/github-flow-lifecycle`**.

### Runbook D: Releases, Tags & Cross-Repo Research

1. Inspect existing tags and releases via `list_tags` and `list_releases` (`get_latest_release`) to verify Semantic Versioning continuity (`vMAJOR.MINOR.PATCH`).
2. Draft or publish releases with structured changelog notes (`gh release create vX.Y.Z -R "<owner>/<repo>" --target main --title "vX.Y.Z" --notes-file - <<'EOF'`). Never delete or overwrite an existing tag/release without explicit human confirmation.
3. For cross-repository architecture questions across uncloned repos, use `search_code` (`query: "org:Panoptic-Huginn <symbol>"` or `query: "user:jamielapointe <symbol>"` — omit `sort:` from `query`), `get_repository_tree`, and `get_file_contents` instead of cloning full repositories unnecessarily.

---

## References

- [references/ghec-governance-and-recipes.md](references/ghec-governance-and-recipes.md): Ready-to-run `gh api` & MCP payloads for repository merge hardening, `main` linear-history rulesets, `Panoptic-Huginn` org ruleset & security sweeps, label cloning, and excluded >64-char endpoints.
