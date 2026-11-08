"""Repository-wide Antigravity plugin, skill, MCP config, and secret-hygiene tests."""

import json
import os
import re
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
MAX_PLUGIN_SKILL_BODY_BYTES = 24_000

EXPECTED_SKILLS = {
    'ada-spark-pro',
    'c-pro',
    'cmake-pro',
    'cpp-pro',
    'github-flow-lifecycle',
    'jupyter-pro',
    'marimo-pair',
    'marimo-pro',
    'python-pro',
    'rust-pro',
}

EXPECTED_MCP_SERVERS = {
    'academic-mcp',
    'arxiv',
    'europe-pmc',
    'github-mcp-server',
    'google-workspace',
    'jupyter',
    'nasa_ads',
    'puppeteer',
    'semantic-scholar',
    'time',
    'zotero',
}

BUILTIN_MCP_PLACEHOLDERS = {'PLUGIN_ROOT', 'PLUGIN_DATA'}
VAR_PLACEHOLDER_RE = re.compile(r'\$\{([A-Za-z0-9_]+)\}')
MARKDOWN_REL_LINK_RE = re.compile(r'\]\((\.\.?/[^)#]+)(?:#[^)]*)?\)')

# Constructed via concatenation so this file never contains literal forbidden substrings.
FORBIDDEN_PATTERNS = [
    re.compile(r'/home/' + r'jamie-lapointe'),
    re.compile(r'/Users/' + r'jamie'),
    re.compile(r'Google' + r'Drive/agents'),
    re.compile(r'\bghp_[A-Za-z0-9]{20,}'),
    re.compile(r'\bgho_[A-Za-z0-9]{20,}'),
    re.compile(r'\bgithub_pat_[A-Za-z0-9_]{20,}'),
    re.compile(r'\bGOCSPX-[A-Za-z0-9_-]{15,}'),
    re.compile(r'\bAIzaSy[A-Za-z0-9_-]{25,}'),
]


def _split_frontmatter(markdown_text: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter and body from a `SKILL.md` file.

    Args:
        markdown_text: Full UTF-8 contents of `SKILL.md`.

    Returns:
        Tuple of `(frontmatter_dict, markdown_body)`.
    """
    assert markdown_text.startswith('---\n'), 'SKILL.md must begin with YAML frontmatter delimiter ---'
    _, rest = markdown_text.split('---\n', 1)
    raw_yaml, body = rest.split('\n---\n', 1)
    parsed = yaml.safe_load(raw_yaml)
    assert isinstance(parsed, dict)
    return (parsed, body.lstrip('\n'))


def test_plugin_manifest_and_workspace_discovery_configs() -> None:
    """Validate `plugin.json`, `.agents/*.json`, `rules/AGENTS.md`, `LICENSE`, and `assets/logo.svg`."""
    manifest = json.loads((REPO_ROOT / 'plugin.json').read_text(encoding='utf-8'))
    assert manifest['name'] == 'mimir-agent-kit'
    assert manifest['license'] == 'Apache-2.0'
    assert (REPO_ROOT / manifest['logo']).is_file()
    assert (REPO_ROOT / 'LICENSE').is_file()
    assert not (REPO_ROOT / 'AGENTS.md').exists(), 'Top-level AGENTS.md is ignored in plugins; keep in rules/AGENTS.md'

    rules_md = (REPO_ROOT / 'rules' / 'AGENTS.md').read_text(encoding='utf-8')
    assert not rules_md.startswith('---'), 'Plugin rules/AGENTS.md must be plain Markdown without frontmatter'
    assert 'github-flow-lifecycle' in rules_md

    skills_cfg = json.loads((REPO_ROOT / '.agents' / 'skills.json').read_text(encoding='utf-8'))
    rules_cfg = json.loads((REPO_ROOT / '.agents' / 'rules.json').read_text(encoding='utf-8'))
    assert skills_cfg == {'entries': [{'path': 'skills'}]}
    assert rules_cfg == {'entries': [{'path': 'rules'}]}


def test_all_custom_skills_valid_and_within_plugin_byte_limit() -> None:
    """Ensure all 7 custom skills match directory names, stay under 24 KB body cap, and have valid links."""
    skills_dir = REPO_ROOT / 'skills'
    discovered = {p.name for p in skills_dir.iterdir() if p.is_dir()}
    assert discovered == EXPECTED_SKILLS

    for skill_name in sorted(discovered):
        skill_file = skills_dir / skill_name / 'SKILL.md'
        assert skill_file.is_file(), f'Missing SKILL.md in {skill_name}'
        frontmatter, body = _split_frontmatter(skill_file.read_text(encoding='utf-8'))
        assert frontmatter.get('name') == skill_name
        description = str(frontmatter.get('description', '')).strip()
        assert len(description) >= 20

        body_bytes = len(body.encode('utf-8'))
        assert body_bytes < MAX_PLUGIN_SKILL_BODY_BYTES, f'{skill_name}/SKILL.md body is {body_bytes} bytes (>= {MAX_PLUGIN_SKILL_BODY_BYTES} plugin cap)'

        for rel_target in MARKDOWN_REL_LINK_RE.findall(body):
            resolved = (skill_file.parent / rel_target).resolve()
            assert resolved.exists(), f'Broken relative link {rel_target} in {skill_name}/SKILL.md'


def test_hooks_and_executable_scripts() -> None:
    """Validate `hooks.json` structure and executable permissions on bundled Python scripts."""
    hooks = json.loads((REPO_ROOT / 'hooks.json').read_text(encoding='utf-8'))
    guard = hooks['github-flow-lifecycle-guard']
    assert guard['enabled'] is True
    pre_tool_use = guard['PreToolUse']
    assert len(pre_tool_use) == 1
    assert 'mimir-agent-kit_github-mcp-server_merge_pull_request' and re.match(
        pre_tool_use[0]['matcher'],
        'mcp_mimir-agent-kit_github-mcp-server_merge_pull_request',
    )

    for script_name in ('git_github_guard.py', 'academic_mcp_server.py'):
        script_path = REPO_ROOT / 'scripts' / script_name
        assert script_path.is_file()
        assert os.access(script_path, os.X_OK), f'{script_path} must be executable (+x)'


def test_mcp_config_variables_and_secret_hygiene() -> None:
    """Ensure all 11 MCP servers declare matching `variables` metadata for every `${VAR}` placeholder."""
    mcp_cfg = json.loads((REPO_ROOT / 'mcp_config.json').read_text(encoding='utf-8'))
    servers: dict[str, Any] = mcp_cfg['mcpServers']
    assert set(servers) == EXPECTED_MCP_SERVERS

    for server_name, spec in servers.items():
        serialized = json.dumps({k: v for k, v in spec.items() if k != 'variables'})
        referenced_vars = set(VAR_PLACEHOLDER_RE.findall(serialized)) - BUILTIN_MCP_PLACEHOLDERS
        declared_vars_list = spec.get('variables', [])
        declared_vars = {entry['name'] for entry in declared_vars_list}
        assert referenced_vars == declared_vars, f'Server {server_name} placeholder mismatch: referenced={referenced_vars}, declared={declared_vars}'
        for entry in declared_vars_list:
            assert entry.get('title'), f'Missing variable title on {server_name}.{entry["name"]}'
            assert entry.get('description'), f'Missing variable description on {server_name}.{entry["name"]}'


def test_zero_hardcoded_machine_paths_or_plaintext_secrets() -> None:
    """Scan all repository text files for leaked home paths, Google Drive mounts, or credential tokens."""
    excluded_dirs = {
        '.agents',
        '.agents/teamwork',
        '.git',
        '.mypy_cache',
        '.pytest_cache',
        '.ruff_cache',
        '.rumdl_cache',
        '.venv',
        '__pycache__',
    }
    for path in REPO_ROOT.rglob('*'):
        if any(part in excluded_dirs for part in path.parts) or any(str(path.relative_to(REPO_ROOT)).startswith(d) for d in excluded_dirs) or not path.is_file():
            continue
        if path.name.startswith('.coverage') or path.suffix in {'.png', '.jpg', '.jpeg', '.webp', '.ico', '.db'}:
            continue
        try:
            content = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        for pattern in FORBIDDEN_PATTERNS:
            match = pattern.search(content)
            assert match is None, f'Forbidden pattern {pattern.pattern!r} found in {path.relative_to(REPO_ROOT)}'
