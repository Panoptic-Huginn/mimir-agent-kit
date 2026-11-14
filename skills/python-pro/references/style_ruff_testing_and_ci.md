# Google Style Overrides, Ruff Rules, Testing (`pytest` 9+) & CI Hardening

This reference provides the exact style baseline, Ruff 23-family rule matrix, `prek` pre-commit workflow, `pytest` 9+ configuration, and GitHub Actions supply-chain hardening.

## 1. Google Python Style Guide Baseline & November 2026 Overrides

Adopt the **Google Python Style Guide** as the baseline across formatting, naming, docstrings, and exception discipline, with four explicit November 2026 overrides:

1. **88-Column Formatting (`line-length = 88`, double quotes)**: Overrides Google's legacy 80-column limit and single quotes so modern PEP 695 generics, `TypedDict`, and multiline type signatures wrap cleanly without churn. Managed exclusively by `ruff format`; ignore only `line-too-long` (`E501`) for unbreakable URLs/docstrings remaining after formatting.
2. **Direct Idiomatic Symbol Imports**: Where Google historically preferred module-only imports, direct symbol imports are idiomatic for unambiguous standard-library and domain types (`from pathlib import Path`, `from collections.abc import Sequence, Mapping`, `from dataclasses import dataclass`, `from typing import ReadOnly, TypeIs, override`). Keep module prefixes for ambiguous modules (`import datetime`, `import json`, `import math`).
3. **Grouped Sorted Imports**: Group `stdlib`, `third-party`, `first-party`, and local imports cleanly (standard Ruff `I` sorting rather than `force-single-line`).
4. **Native PEP 649 Annotations**: Ban `from __future__ import annotations` via Ruff `TID251`; move annotation-only imports into `if TYPE_CHECKING:` blocks (`TC`).

### Core Google Rules Retained Without Relaxation

- **Google Docstrings (`D`, `DOC`)**: Every public module, class, method, and function requires a concise Google-style docstring (`Args:`, `Returns:`, `Raises:`) verified in sync with its signature (`DOC201`/`DOC402`/`DOC501`) and formatted in code examples (`docstring-code-format = true`).
- **Absolute Imports Only (`TID252`)**: `ban-relative-imports = "all"`.
- **Exception Hygiene (`B904`, `BLE001`)**: Always chain contextual exceptions (`raise DomainError(...) from exc`) and never swallow broad exceptions silently.
- **No Production `assert` Validation (`S101`)**: Never use `assert` to validate runtime data or security boundaries (`assert` is stripped under `-O`); raise explicit `ValueError`/`TypeError`. Keep `assert` strictly inside `tests/**`.

## 2. Ruff 23-Family Lint Configuration & `RUF201` Selectors

Ruff replaces legacy `black`, `pyink`, `isort`, `flake8`, and `pylint` completely. Enable all **23 high-signal rule families**:

- **Style & Correctness**: `E` (pycodestyle errors), `F` (Pyflakes), `W` (warnings), `I` (isort), `N` (pep8-naming), `UP` (pyupgrade), `B` (flake8-bugbear), `SIM` (simplify), `C4` (comprehensions), `RUF` (Ruff-native rules).
- **Docstrings**: `D` (pydocstyle Google), `DOC` (pydoclint signature sync).
- **Types, Performance & Modernization**: `ANN` (annotations), `TC` (type-checking imports), `PERF` (perflint), `FURB` (refurb), `PL` (Pylint rules).
- **Safety, Async, Paths, Time & Tests**: `S` (Bandit security), `ASYNC` (async/TaskGroup pitfalls), `DTZ` (timezone-aware UTC datetimes), `PTH` (`pathlib.Path` over `os.path`), `TID` (banned APIs / absolute imports), `PT` (`pytest` style).

### Ruff Rule Selector Naming (`RUF201`)

Modern Ruff enforces full rule names (rather than bare codes like `"E501"` or `"S101"`) inside `ignore` and `per-file-ignores` lists while accepting category prefixes (`"ANN"`, `"D"`, `"DOC"`, `"PL"`):

```toml
[tool.ruff.lint]
select = [
    "E", "F", "W", "I", "N", "D", "DOC", "UP", "B", "SIM", "C4",
    "DTZ", "PT", "RUF", "PERF", "FURB", "S", "ANN", "ASYNC", "PTH",
    "TID", "TC", "PL",
]
ignore = ["line-too-long"]  # Full rule name (not E501) per RUF201

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["assert", "no-self-use", "magic-value-comparison"]
```

## 3. Fast Pre-Commit Orchestration with **`prek`**

- Use **`prek`** (Rust-native drop-in replacement for Python `pre-commit`) executing the standard `.pre-commit-config.yaml` schema (`../examples/.pre-commit-config.yaml`).
- Mandatory hook categories:
  1. SHA-pinned `pre-commit/pre-commit-hooks` (`3e8a8703264a2f4a69428a0aa4dcb512790b2c8c # frozen: v6.0.0`): whitespace, EOF newline, YAML/TOML/JSON syntax, AST check, merge conflict markers, private key scan, large file guard, `no-commit-to-branch` (`main`, `master`).
  2. Local project hooks via `uv run` (or `pixi run`): `ruff-check` (`--fix --exit-non-zero-on-fix`), `ruff-format`, `basedpyright`, `ty check`, `marimo check` (if `.py` notebooks exist), `rumdl check`, `actionlint`, and `zizmor`.
- **No `--no-verify` Bypass**: Passing `--no-verify` or `-n` to `git commit` is **never** allowed. Remote GitHub Actions re-runs `SKIP=no-commit-to-branch uv run prek run --all-files --show-diff-on-failure` on every push/PR.
- **Workspace Discovery & `.prekignore`**: `prek` recursively discovers nested `.pre-commit-config.yaml` files as subprojects. When a repository stores starter-template `.pre-commit-config.yaml` fixtures (such as `examples/` or `templates/`), list those directories in a root `.prekignore` file so `prek` skips nested subproject discovery while root hooks still lint those files.

## 4. Testing Strategy with **`pytest` 9+**

Configure `pytest` 9+ using its native **`[tool.pytest]`** TOML table (no legacy `[tool.pytest.ini_options]` string-splitting needed):

```toml
[tool.pytest]
minversion = "9.0"
testpaths = ["tests"]
strict = true
filterwarnings = ["error"]
addopts = ["-ra", "--doctest-modules", "--cov=src", "--cov-branch"]
markers = [
    "unit: fast, isolated tests with zero network or external I/O",
    "integration: component interaction tests",
    "regression: tests guarding against previously observed defects",
    "e2e: full-stack end-to-end verification tests",
]
```

- **Randomization (`pytest-randomly`)**: Surface hidden shared-state test coupling automatically on every run.
- **Property-Based Fuzzing (`hypothesis`)**: Verify numerical/state invariants, serialization round-trips, and boundary edges cleanly.
- **Branch Coverage (`pytest-cov`)**: Track branch coverage (`[tool.coverage.run] branch = true`).

## 5. GitHub Actions CI & Supply-Chain Hardening

Every Python repository enforces these controls in `.github/workflows/ci.yml` (`../examples/ci.yml`):

1. **Minimal Permissions & SHA-Pinned Actions**: Top-level `permissions: contents: read`; third-party Actions pinned to immutable 40-char commit SHAs (`persist-credentials: false` on `actions/checkout`). Audit workflows with **`actionlint`** and **`zizmor --strict-collection --min-severity=low .github/workflows/`**.
2. **Locked Environment Verification**: `uv lock --check && uv sync --locked --all-extras --dev` (or `pixi install --frozen`).
3. **Full Version Matrix**: Test on both **`3.14`** and **`3.15`** (across `ubuntu-24.04` and `macos-latest` when cross-platform) — plus `3.15t` when claiming free-threaded compatibility.
4. **Dependency & Vulnerability Hygiene**:
   - **`deptry`**: Detects unused, missing, or transitive-only imports (`DEP001`–`DEP004`).
   - **`pip-audit`**: Scans the locked environment against known PyPI CVEs.
5. **Trusted Publishing (OIDC + PEP 740)**: Release workflows use GitHub OIDC (`id-token: write` scoped strictly to the publish job) with `pypa/gh-action-pypi-publish` generating PEP 740 digital attestations—never store long-lived PyPI API tokens.
