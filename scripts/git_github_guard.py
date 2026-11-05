#!/usr/bin/env python3
"""Antigravity PreToolUse Safety Guard for Git & GitHub Flow Lifecycle.

Mechanically enforces the core invariants of the `github-flow-lifecycle` skill:
1. Blocks autonomous PR merging (`merge_pull_request`, `gh pr merge`) across both
   global (`github-mcp-server`) and plugin-namespaced (`<plugin>_github-mcp-server`)
   MCP server registrations.
2. Blocks remote MCP file mutations (`push_files`, `create_or_update_file`, `delete_file`)
   that bypass the local Git working tree, pre-commit hooks, and local CI gates.
3. Blocks `git commit --no-verify` / `git commit -n` (bypassing pre-commit hooks).
4. Blocks `git push --force` / `git push -f` targeting `main` or `master`.
5. Blocks `git commit` when the active local Git branch is `main`, `master`, or detached
   `HEAD` (unless the command itself creates/switches to a feature branch first).
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import select
import sys
from pathlib import Path
from typing import Any
from typing import NoReturn


FORBIDDEN_MCP_TOOLS: dict[str, str] = {
    'merge_pull_request': ('Blocked by github-flow-lifecycle PreToolUse hook: Autonomous PR merging (merge_pull_request) is strictly forbidden. Merging Pull Requests is reserved exclusively for human review and manual sign-off.'),
    'push_files': ('Blocked by github-flow-lifecycle PreToolUse hook: Remote file mutation (push_files) is forbidden because it bypasses the local Git working tree, pre-commit hooks, and local CI gates. Edit files locally and use git add, git commit, and git push on a feature branch.'),
    'create_or_update_file': ('Blocked by github-flow-lifecycle PreToolUse hook: Remote file mutation (create_or_update_file) is forbidden because it bypasses the local Git working tree, pre-commit hooks, and local CI gates. Edit files locally and use git add, git commit, and git push on a feature branch.'),
    'delete_file': ('Blocked by github-flow-lifecycle PreToolUse hook: Remote file deletion (delete_file) is forbidden because it bypasses the local Git working tree and local CI gates. Delete files locally via git rm and commit on a feature branch.'),
}

RE_QUOTED_LITERAL = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
RE_EAGER_GITHUB_MCP = re.compile(r'^mcp_(?:.+_)?github-mcp-server_(?P<tool>.+)$')
RE_GH_PR_MERGE = re.compile(r'(?:^|[;&|]\s*)\bgh\s+pr\s+merge\b')
RE_GIT_COMMIT = re.compile(r'(?:^|[;&|]\s*)\bgit\s+(?:-C\s+\S+\s+)?commit\b')
RE_GIT_COMMIT_NO_VERIFY = re.compile(
    r'(?:^|[;&|]\s*)\bgit\s+(?:-C\s+\S+\s+)?commit\b[^;&|]*(?:\s--no-verify\b|\s-[a-zA-Z]*n[a-zA-Z]*\b)',
)
RE_GIT_BRANCH_SWITCH = re.compile(
    r'\bgit\s+(?:-C\s+\S+\s+)?(?:checkout\s+-b|switch\s+-c)\b|\bgh\s+issue\s+develop\b',
)
RE_GIT_FORCE_PUSH_MAIN = re.compile(
    r'(?:^|[;&|]\s*)\bgit\s+(?:-C\s+\S+\s+)?push\b(?=[^;&|]*(?:\s--force\b|\s-f\b))(?=[^;&|]*\b(?:main|master)\b)',
)


def strip_quoted_literals(command_line: str) -> str:
    """Replace single- and double-quoted literals with empty quotes for safe flag parsing.

    Prevents commit messages or PR bodies that mention forbidden commands (such as
    `git commit -m "document --no-verify"`) from triggering false-positive blocks.

    Args:
        command_line: Raw shell command string.

    Returns:
        Sanitized command string with quoted literals replaced by `""`.
    """
    return RE_QUOTED_LITERAL.sub('""', command_line)


def is_github_mcp_server(server_name: str) -> bool:
    """Check whether an MCP server identifier refers to `github-mcp-server`.

    Matches both global un-prefixed (`github-mcp-server`) and plugin-namespaced
    (`<plugin>_github-mcp-server`, e.g., `mimir-agent-kit_github-mcp-server`) servers.

    Args:
        server_name: MCP `ServerName` field from `call_mcp_tool`.

    Returns:
        True if the server is a `github-mcp-server` instance, False otherwise.
    """
    return server_name == 'github-mcp-server' or server_name.endswith('_github-mcp-server')


def get_active_git_branch(start_dir: Path) -> str | None:
    """Resolve the active Git branch name for a directory or Git worktree.

    Walks upward from `start_dir` to locate `.git` (either a standard `.git/`
    directory or a worktree/submodule `.git` file with a `gitdir:` pointer).

    Args:
        start_dir: Directory inside or equal to the target Git working tree.

    Returns:
        Branch name (e.g., `'feat/1-slug'`), `'HEAD'` when in detached `HEAD` state,
        or `None` if `start_dir` is not inside a Git repository.
    """
    try:
        current = start_dir.resolve()
    except OSError:
        return None

    for candidate in (current, *current.parents):
        dot_git = candidate / '.git'
        try:
            if dot_git.is_file():
                gitdir_text = dot_git.read_text(encoding='utf-8').strip()
                if not gitdir_text.startswith('gitdir:'):
                    return None
                gitdir_raw = gitdir_text.removeprefix('gitdir:').strip()
                gitdir_path = (candidate / gitdir_raw).resolve()
                head_file = gitdir_path / 'HEAD'
            elif dot_git.is_dir():
                head_file = dot_git / 'HEAD'
            else:
                continue

            if not head_file.is_file():
                return None
            head_content = head_file.read_text(encoding='utf-8').strip()
            if head_content.startswith('ref: refs/heads/'):
                return head_content.removeprefix('ref: refs/heads/')
            return 'HEAD'
        except OSError:
            return None
    return None


def evaluate_mcp_tool(tool_name: str, args: dict[str, Any]) -> tuple[str, str | None]:
    """Evaluate a lazy or eager MCP tool invocation against `FORBIDDEN_MCP_TOOLS`.

    Args:
        tool_name: Tool name invoked by the agent (`call_mcp_tool` or `mcp_*`).
        args: Tool arguments dictionary.

    Returns:
        Tuple of `(decision, reason)` where `decision` is `'allow'` or `'deny'`.
    """
    if tool_name == 'call_mcp_tool':
        server_name = str(args.get('ServerName', ''))
        mcp_tool = str(args.get('ToolName', ''))
        if is_github_mcp_server(server_name) and mcp_tool in FORBIDDEN_MCP_TOOLS:
            return ('deny', FORBIDDEN_MCP_TOOLS[mcp_tool])
        return ('allow', None)

    eager_match = RE_EAGER_GITHUB_MCP.match(tool_name)
    if eager_match:
        mcp_tool = eager_match.group('tool')
        if mcp_tool in FORBIDDEN_MCP_TOOLS:
            return ('deny', FORBIDDEN_MCP_TOOLS[mcp_tool])

    return ('allow', None)


def evaluate_run_command(args: dict[str, Any], workspace_paths: list[str]) -> tuple[str, str | None]:
    """Evaluate a `run_command` shell invocation against Git and GitHub Flow invariants.

    Args:
        args: `run_command` arguments dictionary containing `CommandLine`.
        workspace_paths: Active workspace directory paths from the hook payload.

    Returns:
        Tuple of `(decision, reason)` where `decision` is `'allow'` or `'deny'`.
    """
    raw_cmd = str(args.get('CommandLine', ''))
    if not raw_cmd:
        return ('allow', None)

    sanitized_cmd = strip_quoted_literals(raw_cmd)

    if RE_GH_PR_MERGE.search(sanitized_cmd):
        return (
            'deny',
            ('Blocked by github-flow-lifecycle PreToolUse hook: "gh pr merge" is strictly forbidden. Merging Pull Requests to main is reserved exclusively for the human user.'),
        )

    if RE_GIT_COMMIT_NO_VERIFY.search(sanitized_cmd):
        return (
            'deny',
            ('Blocked by github-flow-lifecycle PreToolUse hook: Passing "--no-verify" or "-n" to "git commit" is strictly forbidden. All commits must pass pre-commit hooks and local CI gates.'),
        )

    if RE_GIT_FORCE_PUSH_MAIN.search(sanitized_cmd):
        return (
            'deny',
            ('Blocked by github-flow-lifecycle PreToolUse hook: Force-pushing to "main" or "master" is strictly forbidden.'),
        )

    if RE_GIT_COMMIT.search(sanitized_cmd) and not RE_GIT_BRANCH_SWITCH.search(sanitized_cmd):
        git_c_match = re.search(r'\bgit\s+-C\s+(\S+)\s+commit\b', raw_cmd)
        cd_match = re.search(r'(?:^|[;&|]\s*)cd\s+(\S+)\s*(?:&&|;)', raw_cmd)
        if git_c_match:
            target_dir_str = git_c_match.group(1).strip('\'"')
        elif cd_match:
            target_dir_str = cd_match.group(1).strip('\'"')
        else:
            target_dir_str = workspace_paths[0] if workspace_paths else str(Path.cwd())

        target_dir = Path(target_dir_str).expanduser()
        if target_dir.is_dir():
            branch = get_active_git_branch(target_dir)
            if branch in ('main', 'master', 'HEAD'):
                return (
                    'deny',
                    (f'Blocked by github-flow-lifecycle PreToolUse hook: Active Git branch in "{target_dir}" is "{branch}". Committing directly on main, master, or detached HEAD is forbidden. Create and check out a feature branch ("<type>/<issue-number>-<slug>") first.'),
                )

    return ('allow', None)


def evaluate_payload(data: dict[str, Any]) -> tuple[str, str | None]:
    """Evaluate a full Antigravity `PreToolUse` hook JSON payload.

    Args:
        data: Parsed JSON dictionary read from `stdin`.

    Returns:
        Tuple of `(decision, reason)` where `decision` is `'allow'` or `'deny'`.
    """
    if not data:
        return ('allow', None)

    tool_call_raw = data.get('toolCall')
    tool_call: dict[str, Any] = tool_call_raw if isinstance(tool_call_raw, dict) else {}
    tool_name = str(tool_call.get('name', ''))
    args_raw = tool_call.get('args')
    args: dict[str, Any] = args_raw if isinstance(args_raw, dict) else {}
    ws_raw = data.get('workspacePaths')
    workspace_paths: list[str] = [str(p) for p in ws_raw] if isinstance(ws_raw, list) else []

    if tool_name == 'run_command':
        return evaluate_run_command(args, workspace_paths)
    if tool_name == 'call_mcp_tool' or RE_EAGER_GITHUB_MCP.match(tool_name):
        return evaluate_mcp_tool(tool_name, args)
    return ('allow', None)


def read_stdin_nonblocking(timeout_sec: float = 0.05) -> str:
    """Read JSON hook input from `stdin` without hanging if the pipe stays open.

    Args:
        timeout_sec: Initial select readiness timeout in seconds.

    Returns:
        UTF-8 decoded string read from `stdin`, or empty string when unavailable.
    """
    if sys.stdin.isatty():
        return ''

    raw = bytearray()
    fd = sys.stdin.fileno()
    with contextlib.suppress(OSError, ValueError):
        os.set_blocking(fd, False)

    wait = timeout_sec
    while select.select([fd], [], [], wait)[0]:
        try:
            chunk = os.read(fd, 65536)
        except OSError:
            break
        if not chunk:
            break
        raw.extend(chunk)
        wait = 0.005

    return raw.decode('utf-8', errors='replace') if raw else ''


def emit(decision: str, reason: str | None = None) -> NoReturn:
    """Write the hook decision JSON object to `stdout` and exit immediately.

    Uses `os._exit(0)` to avoid Python interpreter teardown hangs on inherited pipes.

    Args:
        decision: Hook decision (`'allow'` or `'deny'`).
        reason: Optional human- and model-readable denial explanation.
    """
    payload: dict[str, Any] = {'decision': decision}
    if reason:
        payload['reason'] = reason
    sys.stdout.write(json.dumps(payload) + '\n')
    sys.stdout.flush()
    os._exit(0)


def main() -> NoReturn:
    """Execute the `PreToolUse` hook entrypoint.

    Raises:
        SystemExit: Propagated if explicitly raised during execution.
    """
    try:
        raw_text = read_stdin_nonblocking()
        data: dict[str, Any] = json.loads(raw_text) if raw_text.strip() else {}
        decision, reason = evaluate_payload(data)
        emit(decision, reason)
    except SystemExit:
        raise
    except Exception:
        emit('allow')


if __name__ == '__main__':
    main()
