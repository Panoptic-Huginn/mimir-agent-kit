"""Unit and subprocess tests for `scripts/git_github_guard.py`."""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.git_github_guard import FORBIDDEN_MCP_TOOLS
from scripts.git_github_guard import evaluate_mcp_tool
from scripts.git_github_guard import evaluate_payload
from scripts.git_github_guard import evaluate_run_command
from scripts.git_github_guard import get_active_git_branch
from scripts.git_github_guard import is_github_mcp_server
from scripts.git_github_guard import strip_quoted_literals


GUARD_SCRIPT = Path(__file__).resolve().parent.parent / 'scripts' / 'git_github_guard.py'


def _init_fake_git_repo(repo_dir: Path, branch: str | None) -> Path:
    """Create a minimal `.git/HEAD` structure for deterministic branch-detection tests.

    Args:
        repo_dir: Directory in which to create `.git/`.
        branch: Branch name (e.g., `'main'`), or `None` for detached `HEAD`.

    Returns:
        `repo_dir` with `.git/HEAD` populated.
    """
    git_dir = repo_dir / '.git'
    git_dir.mkdir(parents=True, exist_ok=True)
    head_text = f'ref: refs/heads/{branch}\n' if branch else '4b825dc642cb6eb9a060e54bf8d69288fbee4904\n'
    (git_dir / 'HEAD').write_text(head_text, encoding='utf-8')
    return repo_dir


@pytest.mark.parametrize(
    ('server_name', 'expected'),
    [
        ('github-mcp-server', True),
        ('mimir-agent-kit_github-mcp-server', True),
        ('-1870732469773246571_github-mcp-server', True),
        ('academic-mcp', False),
        ('mimir-agent-kit_academic-mcp', False),
        ('github-mcp-server-fork', False),
        ('', False),
    ],
)
def test_is_github_mcp_server(server_name: str, expected: bool) -> None:
    """Recognize both global and plugin-namespaced `github-mcp-server` identifiers."""
    assert is_github_mcp_server(server_name) is expected


@pytest.mark.parametrize('forbidden_tool', sorted(FORBIDDEN_MCP_TOOLS))
@pytest.mark.parametrize(
    'server_name',
    [
        'github-mcp-server',
        'mimir-agent-kit_github-mcp-server',
        '-918273645_github-mcp-server',
    ],
)
def test_blocks_forbidden_lazy_mcp_tools(server_name: str, forbidden_tool: str) -> None:
    """Deny forbidden remote GitHub tools via `call_mcp_tool` across all prefixes."""
    decision, reason = evaluate_mcp_tool(
        'call_mcp_tool',
        {'ServerName': server_name, 'ToolName': forbidden_tool, 'Arguments': {}},
    )
    assert decision == 'deny'
    assert reason is not None
    assert forbidden_tool in reason


@pytest.mark.parametrize('forbidden_tool', sorted(FORBIDDEN_MCP_TOOLS))
@pytest.mark.parametrize(
    'prefix',
    [
        'mcp_github-mcp-server_',
        'mcp_mimir-agent-kit_github-mcp-server_',
        'mcp_-918273645_github-mcp-server_',
    ],
)
def test_blocks_forbidden_eager_mcp_tools(prefix: str, forbidden_tool: str) -> None:
    """Deny forbidden remote GitHub tools when registered as eager `mcp_*` tools."""
    payload: dict[str, Any] = {
        'toolCall': {
            'name': f'{prefix}{forbidden_tool}',
            'args': {'owner': 'Panoptic-Huginn', 'repo': 'mimir-agent-kit'},
        },
    }
    decision, reason = evaluate_payload(payload)
    assert decision == 'deny'
    assert reason is not None
    assert forbidden_tool in reason


@pytest.mark.parametrize(
    'safe_tool',
    ['get_me', 'issue_read', 'issue_write', 'create_pull_request', 'pull_request_read', 'actions_list'],
)
def test_allows_safe_github_mcp_tools(safe_tool: str) -> None:
    """Allow sanctioned read/PR/issue `github-mcp-server` tools."""
    decision, reason = evaluate_mcp_tool(
        'call_mcp_tool',
        {'ServerName': 'mimir-agent-kit_github-mcp-server', 'ToolName': safe_tool},
    )
    assert decision == 'allow'
    assert reason is None


@pytest.mark.parametrize(
    'command_line',
    [
        'gh pr merge 12 --squash',
        'git status && gh pr merge --auto',
        'git commit --no-verify -m "wip"',
        'git commit -n -m "wip"',
        'git commit -anm "wip"',
        'git -C /tmp/repo commit --no-verify -m "wip"',
        'git push --force origin main',
        'git push -f origin master',
    ],
)
def test_blocks_forbidden_shell_commands(tmp_path: Path, command_line: str) -> None:
    """Deny `gh pr merge`, `git commit --no-verify`/`-n`, and force-pushes to `main`/`master`."""
    repo = _init_fake_git_repo(tmp_path / 'repo', 'feat/1-test')
    decision, reason = evaluate_run_command({'CommandLine': command_line}, [str(repo)])
    assert decision == 'deny'
    assert reason is not None


def test_quoted_commit_messages_do_not_false_positive(tmp_path: Path) -> None:
    """Allow commit messages that mention `--no-verify` or `gh pr merge` inside quotes."""
    repo = _init_fake_git_repo(tmp_path / 'repo', 'feat/1-guard-docs')
    cmd = 'git commit -am "docs: explain why --no-verify, -n, and gh pr merge are blocked"'
    assert '--no-verify' not in strip_quoted_literals(cmd)
    decision, reason = evaluate_run_command({'CommandLine': cmd}, [str(repo)])
    assert decision == 'allow'
    assert reason is None


@pytest.mark.parametrize('protected_branch', ['main', 'master', None])
def test_blocks_git_commit_on_protected_or_detached_branch(
    tmp_path: Path,
    protected_branch: str | None,
) -> None:
    """Deny `git commit` when active branch is `main`, `master`, or detached `HEAD`."""
    repo = _init_fake_git_repo(tmp_path / 'repo', protected_branch)
    decision, reason = evaluate_run_command({'CommandLine': 'git commit -m "bad commit"'}, [str(repo)])
    assert decision == 'deny'
    assert reason is not None

    cd_decision, _ = evaluate_run_command(
        {'CommandLine': f'cd {repo} && git commit -m "bad commit"'},
        [],
    )
    assert cd_decision == 'deny'


def test_allows_git_commit_on_feature_branch_and_branch_switch(tmp_path: Path) -> None:
    """Allow `git commit` on a feature branch or after `git checkout -b` in the same command."""
    feature_repo = _init_fake_git_repo(tmp_path / 'feature_repo', 'feat/1-bootstrap')
    decision, reason = evaluate_run_command(
        {'CommandLine': 'git commit -m "feat(core): add guard (#1)"'},
        [str(feature_repo)],
    )
    assert decision == 'allow'
    assert reason is None

    main_repo = _init_fake_git_repo(tmp_path / 'main_repo', 'main')
    switch_decision, switch_reason = evaluate_run_command(
        {'CommandLine': 'git checkout -b feat/2-branch && git commit -m "feat: init (#2)"'},
        [str(main_repo)],
    )
    assert switch_decision == 'allow'
    assert switch_reason is None


def test_git_worktree_dot_git_file_resolution(tmp_path: Path) -> None:
    """Resolve active branch accurately when `.git` is a worktree `gitdir:` pointer file."""
    gitdir = tmp_path / 'actual_gitdir' / 'worktrees' / 'wt1'
    gitdir.mkdir(parents=True)
    (gitdir / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')

    worktree = tmp_path / 'worktree_checkout'
    subdir = worktree / 'nested' / 'pkg'
    subdir.mkdir(parents=True)
    (worktree / '.git').write_text(f'gitdir: {gitdir}\n', encoding='utf-8')

    assert get_active_git_branch(subdir) == 'main'


def test_subprocess_execution_across_interpreters() -> None:
    """Verify `git_github_guard.py` runs cleanly over `stdin`/`stdout` on host `python3` and `uv` Python."""
    interpreters = {sys.executable}
    host_python3 = shutil.which('python3')
    if host_python3:
        interpreters.add(host_python3)

    deny_payload = json.dumps(
        {
            'toolCall': {
                'name': 'call_mcp_tool',
                'args': {
                    'ServerName': 'mimir-agent-kit_github-mcp-server',
                    'ToolName': 'merge_pull_request',
                },
            },
        },
    )

    for python_bin in sorted(interpreters):
        proc = subprocess.run(
            [python_bin, str(GUARD_SCRIPT)],
            input=deny_payload,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        parsed = json.loads(proc.stdout.strip())
        assert parsed['decision'] == 'deny'
        assert 'merge_pull_request' in parsed['reason']
