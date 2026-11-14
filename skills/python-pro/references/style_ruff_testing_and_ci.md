# Google Style Overrides, Ruff Rules, Testing (`pytest` 9+) & CI Hardening

This reference defines the 3-tier style authority hierarchy, Ruff 23-family rule matrix (`RUF201`), `prek` pre-commit workflow, `pytest` 9+ + `hypothesis` testing standards, opt-in `3.15t` CI matrix, and SHA-pinned PyPI OIDC Trusted Publishing (PEP 740).

## 1. Three-Tier Style Authority Hierarchy

Resolve style decisions strictly in precedence order from Tier 1 (highest) to Tier 3:

```text
Tier 1: Project/Repo November 2026 Overrides  (highest precedence)
   └── 88-char line length, double quotes, docstring-code-format = true,
       grouped symbol imports allowed, PEP 649 native annotations (TID251 bans
       `from __future__ import annotations`)
Tier 2: Google Python Style Guide Baseline
   └── Docstring structure (D, DOC), absolute imports (TID252), exception
       chaining (B904 / BLE001), zero runtime `assert` validation (S101),
       clear naming & shallow cohesive functions
Tier 3: PEP 8 & 23-Family Ruff Automated Enforcement
   └── `ruff format` + `ruff check` across all 23 rule families with RUF201
       full-rule-name selectors
```

### Tier 1: Project/Repo November 2026 Overrides

1. **88-Column Formatting (`line-length = 88`, `double` quotes)**: Overrides Google's legacy 80-column limit and single quotes so PEP 695 generics, `TypedDict`, and multiline signatures wrap cleanly without churn. Managed exclusively by `ruff format` with `docstring-code-format = true`; ignore only `line-too-long` (`E501`) for unbreakable URLs or prose remaining after formatting.
2. **Direct Idiomatic Symbol Imports & `grouped` Sorting**: Direct symbol imports are idiomatic for unambiguous standard-library and domain types (`from pathlib import Path`, `from collections.abc import Sequence, Mapping`, `from dataclasses import dataclass`, `from typing import ReadOnly, TypeIs, override`). Keep module prefixes for ambiguous modules (`import datetime`, `import json`, `import math`). Group `stdlib`, `third-party`, `first-party`, and local imports cleanly with `lines-after-imports = 2` (standard `grouped` Ruff `I` sorting rather than `force-single-line`).
3. **Native PEP 649 Annotations (`TID251`)**: Ban `from __future__ import annotations` via Ruff `TID251` (`banned-api`) because Python 3.14+ natively defers annotation evaluation; move annotation-only imports into `if TYPE_CHECKING:` blocks (`TC`).

### Tier 2: Google Python Style Guide Core Rules Retained

- **Google Docstrings (`D`, `DOC`)**: Every public module, class, method, and function requires a concise Google-style docstring (`Args:`, `Returns:`, `Raises:`, and `Examples:` where doctested) verified against its signature (`DOC201`/`DOC402`/`DOC501`).
- **Absolute Imports Only (`TID252`)**: Enforce `ban-relative-imports = "all"`.
- **Exception Hygiene (`B904`, `BLE001`)**: Always chain contextual exceptions (`raise DomainError(...) from exc`) and never swallow broad exceptions silently.
- **No Production `assert` Validation (`S101`)**: Never use `assert` to validate runtime data or security boundaries (`assert` is stripped under `-O`); raise explicit `ValueError`/`TypeError`. Keep `assert` strictly inside `tests/**`.

### Tier 3: Ruff 23-Family Lint Configuration & `RUF201` Selectors

Ruff replaces legacy `black`, `pyink`, `isort`, `flake8`, and `pylint` completely. Enable all **23 high-signal rule families**:

- **Style & Correctness**: `E` (pycodestyle errors), `F` (Pyflakes), `W` (warnings), `I` (isort), `N` (pep8-naming), `UP` (pyupgrade), `B` (flake8-bugbear), `SIM` (simplify), `C4` (comprehensions), `RUF` (Ruff-native rules).
- **Docstrings**: `D` (pydocstyle Google), `DOC` (pydoclint signature sync).
- **Types, Performance & Modernization**: `ANN` (annotations), `TC` (type-checking imports), `PERF` (perflint), `FURB` (refurb), `PL` (Pylint rules).
- **Safety, Async, Paths, Time & Tests**: `S` (Bandit security), `ASYNC` (async/`TaskGroup` pitfalls), `DTZ` (timezone-aware UTC datetimes), `PTH` (`pathlib.Path` over `os.path`), `TID` (banned APIs / absolute imports), `PT` (`pytest` style).

Modern Ruff (`RUF201`) enforces full rule names (rather than bare codes like `"E501"` or `"S101"`) inside `ignore` and `per-file-ignores` while accepting category prefixes (`"ANN"`, `"D"`, `"DOC"`, `"PL"`):

```toml
[tool.ruff.lint]
select = [
    "E", "F", "W", "I", "N", "D", "DOC", "UP", "B", "SIM", "C4",
    "DTZ", "PT", "RUF", "PERF", "FURB", "S", "ANN", "ASYNC", "PTH",
    "TID", "TC", "PL",
]
ignore = ["line-too-long"]  # Full rule name (not E501) per RUF201

[tool.ruff.lint.flake8-tidy-imports]
ban-relative-imports = "all"

[tool.ruff.lint.flake8-tidy-imports.banned-api]
"__future__.annotations".msg = "Use native PEP 649/749 annotations (Python 3.14+); remove 'from __future__ import annotations'."

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["assert", "no-self-use", "magic-value-comparison"]
```

## 2. Fast Pre-Commit Orchestration with **`prek`**

- Use **`prek`** (Rust-native drop-in replacement for Python `pre-commit`) executing the standard `.pre-commit-config.yaml` schema ([../examples/.pre-commit-config.yaml](../examples/.pre-commit-config.yaml)).
- Mandatory hook categories:
  1. SHA-pinned `pre-commit/pre-commit-hooks` (`3e8a8703264a2f4a69428a0aa4dcb512790b2c8c # frozen: v6.0.0`): whitespace, EOF newline, YAML/TOML/JSON syntax, AST check, merge conflict markers, private key scan, large file guard, `no-commit-to-branch` (`main`, `master`).
  2. Local project hooks via `uv run` (or `pixi run`): `ruff-check` (`--fix --exit-non-zero-on-fix`), `ruff-format`, `basedpyright`, `ty check`, `marimo check` (if `.py` notebooks exist), `rumdl check`, `actionlint`, and `zizmor`.
- **No `--no-verify` Bypass**: Passing `--no-verify` or `-n` to `git commit` is **never** allowed. Remote GitHub Actions re-runs `SKIP=no-commit-to-branch uv run prek run --all-files --show-diff-on-failure` on every push/PR.
- **Workspace Discovery & `.prekignore`**: `prek` recursively discovers nested `.pre-commit-config.yaml` files as subprojects. When a repository stores starter-template `.pre-commit-config.yaml` fixtures (such as `examples/` or `templates/`), list those directories in a root `.prekignore` file so `prek` skips nested subproject discovery while root hooks still lint those files.

## 3. Testing Strategy with **`pytest` 9+** & **`hypothesis`**

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

### Concrete `hypothesis` `@given` + `pytest` 9+ Marker Example

Pair `strict = true` registered `pytest` markers with `hypothesis` `@given` property invariants so edge cases (boundary floats, clamping, ordering, round-trips) are fuzzed deterministically alongside explicit unit cases:

```python
import pytest
from hypothesis import given
from hypothesis import strategies as st


def normalize_unit_interval(value: float, low: float, high: float) -> float:
    """Clamp and scale ``value`` into ``[0.0, 1.0]``.

    Args:
        value: Input scalar to normalize.
        low: Inclusive lower range bound.
        high: Inclusive upper range bound (strictly greater than ``low``).

    Returns:
        Normalized float clamped to ``[0.0, 1.0]``.

    Raises:
        ValueError: If ``high`` does not strictly exceed ``low``.
    """
    if high <= low:
        raise ValueError("Upper bound must exceed lower bound")
    clamped = min(max(value, low), high)
    return (clamped - low) / (high - low)


@pytest.mark.unit
@given(
    value=st.floats(
        min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False
    ),
    low=st.floats(min_value=-1e3, max_value=0.0, allow_nan=False, allow_infinity=False),
    span=st.floats(
        min_value=1e-3, max_value=1e3, allow_nan=False, allow_infinity=False
    ),
)
def test_normalize_unit_interval_bounds(value: float, low: float, span: float) -> None:
    """Verify normalized outputs always remain inside [0.0, 1.0]."""
    result = normalize_unit_interval(value, low, low + span)
    assert 0.0 <= result <= 1.0
```

## 4. GitHub Actions CI & Supply-Chain Hardening

Every Python repository enforces these controls in `.github/workflows/ci.yml` ([../examples/ci.yml](../examples/ci.yml)):

1. **Minimal Permissions & SHA-Pinned Actions**: Top-level `permissions: contents: read`; third-party Actions pinned to immutable 40-char commit SHAs (`persist-credentials: false` on `actions/checkout`). Audit workflows with **`actionlint`** and **`zizmor --strict-collection --min-severity=low .github/workflows/`**.
2. **Locked Environment Verification**: `uv lock --check && uv sync --locked --all-extras --dev` (or `pixi install --frozen`).
3. **Full Version Matrix**: Test on both **`3.14`** and **`3.15`** (across `ubuntu-24.04` and `macos-latest` when cross-platform) — plus opt-in `3.15t` when claiming free-threaded compatibility.
4. **Dependency & Vulnerability Hygiene**:
   - **`deptry`**: Detects unused, missing, or transitive-only imports (`DEP001`–`DEP004`).
   - **`pip-audit`**: Scans the locked environment against known PyPI CVEs.
5. **Trusted Publishing (OIDC + PEP 740)**: Release workflows use GitHub OIDC (`id-token: write` scoped strictly to the publish job) with `pypa/gh-action-pypi-publish` generating PEP 740 digital attestations—never store long-lived PyPI API tokens.

### Opt-In `3.15t` Free-Threaded CI Matrix (`PYTHON_GIL=0`)

Add a dedicated `3.15t` job only once every runtime dependency publishes verified free-threaded wheels, forcing `PYTHON_GIL=0` so non-free-threaded extensions cannot silently re-enable the GIL:

```yaml
  free-threaded-test:
    name: Free-Threaded (${{ matrix.os }} / Py${{ matrix.python-version }})
    runs-on: ${{ matrix.os }}
    timeout-minutes: 15
    strategy:
      fail-fast: false
      matrix:
        os:
          - ubuntu-24.04
          - macos-latest
        python-version:
          - "3.15t"
    env:
      PYTHON_GIL: "0"
    steps:
      - name: Checkout repository
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - name: Set up uv and Python ${{ matrix.python-version }}
        uses: astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2 # v10.3.3
        with:
          python-version: ${{ matrix.python-version }}
      - name: Verify GIL disabled and run tests
        run: |
          uv sync --locked --python ${{ matrix.python-version }} --dev
          uv run --python ${{ matrix.python-version }} python -c "import sys; assert not sys._is_gil_enabled()"
          uv run --python ${{ matrix.python-version }} pytest -v
```

### SHA-Pinned PyPI OIDC Trusted Publishing Release Workflow (PEP 740)

Isolate package building from OIDC token issuance: keep top-level `permissions: contents: read`, build artifacts in an unprivileged `build` job, and grant `permissions: id-token: write` strictly to the `publish` job backed by a protected `pypi` GitHub Environment:

```yaml
name: Release to PyPI

on:
  release:
    types: [published]

permissions:
  contents: read

jobs:
  build:
    name: Build Wheel & Sdist
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    steps:
      - name: Checkout repository
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - name: Set up uv
        uses: astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2 # v10.3.3
      - name: Build distributions
        run: uv build
      - name: Upload dist artifacts
        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        with:
          name: python-package-distributions
          path: dist/

  publish:
    name: Publish via OIDC + PEP 740
    needs: [build]
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    environment:
      name: pypi
    permissions:
      id-token: write
    steps:
      - name: Download dist artifacts
        uses: actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333 # v8.0.2
        with:
          name: python-package-distributions
          path: dist/
      - name: Publish to PyPI with PEP 740 attestations
        uses: pypa/gh-action-pypi-publish@7245906fb61fa33a13554f9d5fb856fe61758086 # v1.14.3
        with:
          attestations: true
```
