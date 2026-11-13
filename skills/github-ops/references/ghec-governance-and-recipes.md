# GHEC & Personal Account Governance Recipes (`/github-ops`)

Canonical `mimir-agent-kit_github` and `gh api` payloads for administering `Panoptic-Huginn` (GitHub Enterprise Cloud Organization) and `jamielapointe` (Personal Account) repositories.

---

## 1. Standard Repository Merge & Branch-Hygiene Hardening

Enforce linear Squash-Merge history (matching `/github-flow-lifecycle` conventions), automatic head-branch cleanup after human squash merge, and no autonomous auto-merge:

```bash
OWNER="Panoptic-Huginn"   # or "jamielapointe"
REPO="<repo-name>"

gh api -X PATCH "repos/${OWNER}/${REPO}" --input - <<'EOF'
{
  "allow_squash_merge": true,
  "allow_merge_commit": false,
  "allow_rebase_merge": false,
  "squash_merge_commit_title": "PR_TITLE",
  "squash_merge_commit_message": "PR_BODY",
  "delete_branch_on_merge": true,
  "allow_auto_merge": false,
  "allow_update_branch": true
}
EOF
```

---

## 2. Canonical `main` Branch Ruleset (Repo-Level or `Panoptic-Huginn` Org-Level)

### A. Repo-Level Ruleset (`jamielapointe/*` or Repo-Specific Status Checks)

Can be created via `mimir-agent-kit_github` (`create_repository_ruleset`) or `gh api`:

```bash
gh api -X POST "repos/${OWNER}/${REPO}/rulesets" --input - <<'EOF'
{
  "name": "main-branch-protection",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "include": ["~DEFAULT_BRANCH"],
      "exclude": []
    }
  },
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    { "type": "required_linear_history" },
    {
      "type": "pull_request",
      "parameters": {
        "allowed_merge_methods": ["squash"],
        "dismiss_stale_reviews_on_push": true,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_approving_review_count": 0,
        "required_review_thread_resolution": true
      }
    }
  ]
}
EOF
```

Note: Set `required_approving_review_count: 0` on solo-owned repositories where `jamielapointe` opens PRs and manually reviews/merges them (GitHub blocks self-approval from satisfying `required_approving_review_count >= 1` unless bypass actors are used), while keeping `required_review_thread_resolution: true`, `required_linear_history`, `non_fast_forward`, and required CI status checks active!

### B. Inspecting Organization-Wide Rulesets on `Panoptic-Huginn`

Requires `admin:org` scope (`gh auth refresh --hostname github.com --scopes admin:org`):

```bash
# List all organization rulesets inherited across Panoptic-Huginn
gh api "orgs/Panoptic-Huginn/rulesets"

# Inspect a specific organization ruleset by ID
gh api "orgs/Panoptic-Huginn/rulesets/<RULESET_ID>"
```

---

## 3. Multi-Owner Inventory & Security Triage Sweep

Audit open PRs, failing default-branch workflows, Dependabot alerts, and Code Scanning alerts across both `Panoptic-Huginn` and `jamielapointe` in one read-only pass:

```bash
for OWNER in Panoptic-Huginn jamielapointe; do
  echo "=== Owner: ${OWNER} ==="
  gh repo list "${OWNER}" --limit 50 --no-archived --json nameWithOwner,isPrivate,defaultBranchRef \
    --jq '.[].nameWithOwner' | while read -r FULL_REPO; do
      OPEN_PRS="$(gh pr list -R "${FULL_REPO}" --state open --json number --jq 'length')"
      DEP_ALERTS="$(gh api "repos/${FULL_REPO}/dependabot/alerts?state=open&per_page=100" --jq 'length' 2>/dev/null || echo "n/a")"
      CODEQL_ALERTS="$(gh api "repos/${FULL_REPO}/code-scanning/alerts?state=open&per_page=100" --jq 'length' 2>/dev/null || echo "n/a")"
      printf "%-42s open_prs=%-4s dependabot=%-5s codeql=%s\n" "${FULL_REPO}" "${OPEN_PRS}" "${DEP_ALERTS}" "${CODEQL_ALERTS}"
    done
done
```

---

## 4. Cloning Label Taxonomies & Managing Sub-Issues

### Clone Standard Labels into a New Repository

```bash
gh label clone Panoptic-Huginn/mimir-agent-kit -R "${OWNER}/${NEW_REPO}" --force
```

### Wire a Child Issue as a Sub-Issue (`sub_issue_write`)

`sub_issue_write` expects the child issue's **numeric database `id`** (`sub_issue_id`), *not* its `#issue_number`:

1. Read the child issue via `issue_read` (`method: "get"`, `owner`, `repo`, `issue_number: <CHILD_NUMBER>`) and extract its integer `id`.
2. Call `sub_issue_write` (`method: "add"`, `owner`, `repo`, `issue_number: <PARENT_EPIC_NUMBER>`, `sub_issue_id: <CHILD_DATABASE_ID>`).

---

## 5. Excluded MCP Endpoints (64-Character Antigravity Identifier Cap)

Two upstream `github-mcp-server` tools are excluded via `GITHUB_EXCLUDE_TOOLS` in `mcp_config.json` because `mcp_mimir-agent-kit_github_<tool>` exceeds 64 characters:

```bash
# 1. Organization-wide security advisories (replaces list_org_repository_security_advisories)
gh api "/orgs/Panoptic-Huginn/security-advisories"

# 2. Repository notification subscription state (replaces manage_repository_notification_subscription)
gh api -X PUT "/repos/${OWNER}/${REPO}/notifications" -F subscribed=true -F ignored=false
```
