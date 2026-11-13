# GitHub CLI (`gh`) Partner & Cloud-Sandbox Reference

Use this guide when pairing `gh` CLI with `mimir-agent-kit_github` (for custom REST/GraphQL endpoints or the two org/notification tools excluded to fit Antigravity's 64-character tool-name limit), or inside **Antigravity Cloud Remote Agents** where local `stdio` MCP binaries do not run.

> **Invariant Reminder:** Even when using `gh` CLI directly, **never** run `gh pr merge` autonomously (only when the user explicitly requests merging a green PR), **never** commit to `main`/`master`/detached `HEAD`, and **never** use remote file commits (`gh api` contents PUT) instead of local edits + `git commit` + local CI verification.

---

## 1. Preflight Auth, Scopes & Multi-Owner Verification

A single `gh` OAuth login to `github.com` stored in the OS keyring (`libsecret` on Ubuntu, Login Keychain on macOS) spans both your personal account (`jamielapointe`) and GitHub Enterprise Cloud organizations (`Panoptic-Huginn`).

```bash
# 1. Verify active keyring session, hostname, and scopes
gh auth status

# 2. If logged out or token expired, authenticate interactively once per machine
gh auth login --hostname github.com --git-protocol ssh

# 3. Recommended one-time scope upgrade for GHEC Org Owner + Actions triggers + Projects
gh auth refresh --hostname github.com --scopes repo,read:org,workflow,admin:org,project,notifications

# 4. Verify cached native github-mcp-server binary (zero Docker required)
uv run --isolated --no-project --python ">=3.14" python scripts/github_mcp_launcher.py --print-binary-path
```

### Extracting `OWNER` and `REPO` Safely

Never substitute `get_me` / `gh api user --jq .login` as the repository `OWNER` when working inside an organization repo:

```bash
REMOTE_URL="$(git remote get-url origin)"
OWNER_REPO="$(printf '%s\n' "${REMOTE_URL}" | sed -E 's#^git@[^:]+:##; s#^https?://[^/]+/##; s#\.git$##')"
OWNER="${OWNER_REPO%%/*}"
REPO="${OWNER_REPO##*/}"
ACTING_USER="$(gh api user --jq .login)"
```

### Safe Multiline Markdown / LaTeX Bodies

Repositories frequently contain `$...$` LaTeX math, shell `$VARS`, and triple backticks. **Always pass `--body-file -` with a single-quoted heredoc (`<<'EOF'`)** instead of inline `--body "..."`:

```bash
gh issue create -R "${OWNER}/${REPO}" \
  --title "fix(scope): concise summary" \
  --label "bug" \
  --assignee "${ACTING_USER}" \
  --body-file - <<'EOF'
## Problem Statement
...
EOF
```

---

## 2. Stage-by-Stage `gh` CLI Parity Recipes

### Stage 1: Rulesets, Issue Discovery & Issue Creation

```bash
# Effective branch rules on main (works with baseline `repo` + `read:org` scopes)
gh api "repos/${OWNER}/${REPO}/rules/branches/main"
gh ruleset check main -R "${OWNER}/${REPO}"

# Organization-level rulesets on Panoptic-Huginn (requires `admin:org` scope):
gh api "orgs/${OWNER}/rulesets"

# Search existing issues before creating a duplicate
gh issue list -R "${OWNER}/${REPO}" --state open --search "<keywords>"
gh issue view <ISSUE_NUMBER> -R "${OWNER}/${REPO}" --comments

# List labels before creating an issue
gh label list -R "${OWNER}/${REPO}" --limit 50
```

### Stage 2: Remote-Linked Branch Creation

```bash
git checkout main && git pull --ff-only origin main
git checkout -b "<type>/<ISSUE_NUMBER>-<short-kebab-slug>"
git push -u origin HEAD

# Optional: link branch directly in GitHub UI metadata
gh issue develop <ISSUE_NUMBER> -R "${OWNER}/${REPO}" --checkout --name "<type>/<ISSUE_NUMBER>-<short-kebab-slug>"
```

### Stage 4: Pull Request Creation & Updating

```bash
# Find existing open PR for current branch (same-repo branch; fork PRs use "<fork-owner>:<branch>")
BRANCH="$(git branch --show-current)"
gh pr list -R "${OWNER}/${REPO}" --head "${BRANCH}" --state open --json number,url,title

# Create PR cleanly without bash expansion
gh pr create -R "${OWNER}/${REPO}" \
  --base main \
  --head "${BRANCH}" \
  --title "<type>(<scope>): <concise summary> (#<ISSUE_NUMBER>)" \
  --body-file - <<'EOF'
## Summary

Closes #<ISSUE_NUMBER>
...
EOF
```

When `main` moves ahead on a repo with **`required_linear_history`**:

```bash
# Preferred (matches local CI gate before pushing):
git fetch origin main && git rebase origin/main
# Re-run Stage 3 full local CI suite here, then:
git push --force-with-lease origin HEAD

# Or server-side rebase via gh CLI (only if no conflicts; still wait for remote CI):
gh pr update-branch <PR_NUMBER> -R "${OWNER}/${REPO}" --rebase
```

### Stage 5: Remote CI Monitoring & Failure Log Extraction

Avoid `--watch` in non-TTY agent shells; pair bounded status queries with the Antigravity `schedule` timer (20–30 s) when waiting for completion:

```bash
HEAD_SHA="$(git rev-parse HEAD)"

# 1. Check PR check runs & combined status for HEAD_SHA
gh api "repos/${OWNER}/${REPO}/commits/${HEAD_SHA}/check-runs" \
  --jq '.check_runs[] | {name, status, conclusion, details_url}'

# 2. List workflow runs on current branch (always set -R!)
gh run list -R "${OWNER}/${REPO}" --branch "$(git branch --show-current)" --limit 10 \
  --json databaseId,workflowName,headSha,status,conclusion,url

# 3. Extract failed job logs for a failing run ID
gh run view <FAILED_RUN_ID> -R "${OWNER}/${REPO}" --log-failed | tail -n 500
```

### Stage 5 (Continued): Reading, Replying & Resolving PR Review Threads

`gh pr view --comments` **only prints comments and cannot resolve review threads**. Use GraphQL via `gh api graphql`:

```bash
# 1. Inspect review threads & locate unresolved PRRT_* node IDs + comment databaseIds
gh api graphql -F owner="${OWNER}" -F repo="${REPO}" -F pr=<PR_NUMBER> -f query='
query($owner: String!, $repo: String!, $pr: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $pr) {
      reviewThreads(first: 50) {
        nodes {
          id
          isResolved
          path
          line
          comments(first: 10) {
            nodes { databaseId author { login } body }
          }
        }
      }
    }
  }
}'

# 2. Reply to a review thread and mark it resolved
gh api graphql -F threadId="PRRT_..." -f body="Fixed in commit $(git rev-parse --short HEAD)." -f query='
mutation($threadId: ID!, $body: String!) {
  addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $threadId, body: $body}) {
    comment { id }
  }
  resolveReviewThread(input: {threadId: $threadId}) {
    thread { id isResolved }
  }
}'
```

---

## 3. Replacements for Excluded MCP Tools (64-Char Cap)

Two upstream tools are excluded in `mcp_config.json` via `GITHUB_EXCLUDE_TOOLS` because `mcp_mimir-agent-kit_github_<tool>` exceeds Antigravity's 64-character identifier limit. Invoke them with `gh api` when needed:

```bash
# Replacement for list_org_repository_security_advisories
gh api "/orgs/${OWNER}/security-advisories"

# Replacement for manage_repository_notification_subscription
gh api -X PUT "/repos/${OWNER}/${REPO}/notifications" -F ignored=false
```
