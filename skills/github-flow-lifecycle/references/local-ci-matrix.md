# Pre-Commit Local CI Gate Matrix by Ecosystem

Inspect the repository root and `.github/workflows/*.yml` (specifically `pull_request`-triggered workflows) so local verification matches every remote PR check before running `git commit`.

| Ecosystem / Build Files Detected | Required Local CI Commands (Run All Applicable) |
| :--- | :--- |
| **`scripts/ci/run_local_ci.sh` (Antigravity Plugin)** | `./scripts/ci/run_local_ci.sh` (`uv lock --check`, `prek run --all-files --show-diff-on-failure`, `deptry .`, `pip-audit`, `validate_agentic_settings.py --strict`, `pytest`) |
| **`pixi.lock` / `pixi.toml` / `[tool.pixi]`** (Pixi Python / Cross-Ecosystem, e.g., `heimdall-astro`) | `pixi run prek run --all-files --show-diff-on-failure` (or `pre-commit`); `pixi run ci-hygiene` (if defined); `pixi run ruff check` && `pixi run ruff format --check`; `pixi run basedpyright` / `ty check`; `pixi run pytest tests/unit` (or `pixi run test -m "not live_fire"`); `pixi run build` (if in `ci.yml`) |
| **`pyproject.toml` + `uv.lock`** (Pure `uv` Python) | `uv run prek run --all-files`; `uv run ruff check .` && `uv run ruff format --check .`; `uv run basedpyright` && `uv run ty check`; `uv run deptry .`; `uv run pip-audit`; `uv run pytest`; `uv build` (if applicable) |
| **`.pre-commit-config.yaml` / `lefthook.yml`** (Standalone) | `pre-commit run --all-files --show-diff-on-failure` or `lefthook run pre-commit` |
| **`CMakePresets.json` / `CMakeLists.txt`** (C/C++23 — `/cmake-pro` & `/cpp-pro`) | `gersemi --check CMakeLists.txt cmake/ src/ tests/`; `clang-format --dry-run --Werror` & `clang-tidy`; `cmake --workflow --preset <ci-or-dev-preset>` (or `cmake --preset <p>` && `cmake --build --preset <p>` && `ctest --preset <p> --output-on-failure`) |
| **`Justfile` / `Makefile` / `Taskfile.yml`** | Run dedicated check/CI targets (`just check`, `just ci`, `make check`, `make test`) |
| **`Cargo.toml`** (Rust — `/rust-pro`) | `cargo fmt --all -- --check` && `cargo clippy --all-targets -- -D warnings` && `cargo test` |
| **`package.json`** (Node / TypeScript) | `npm run lint` && `npm run typecheck` (or `npx tsc --noEmit`) && `npm test` |
| **`go.mod`** (Go) | `test -z "$(gofmt -l .)"` && `go vet ./...` && `go test -race ./...` |
| **Markdown / Docs (`[tool.rumdl]` / MathJax)** | `rumdl check .` (or via `pre-commit`) and MathJax/LaTeX delimiter checks |
