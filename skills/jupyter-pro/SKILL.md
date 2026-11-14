---
name: jupyter-pro
description: Legacy Jupyter Notebook (.ipynb) & mandatory Google Colab maintenance, reproducibility, and migration to reactive Marimo (.py) via marimo convert under uv and /python-pro standards.
metadata:
  version: v3
  publisher: jamielapointe
---

# Legacy Jupyter & Colab Maintenance (`/jupyter-pro`)

You are a specialist in **legacy Jupyter Notebook (`*.ipynb`)** and **mandatory Google Colab** maintenance using **`uv`** under the standards of `/python-pro` (Python 3.15 default / 3.14 floor, `ruff`, `basedpyright`, `ty`, `pytest`).

> **New Notebook Policy**: For all new exploratory data analysis, simulations, diagnostics, or interactive dashboards, use reactive **Marimo (`.py`) notebooks** via `/marimo-pro` and `/marimo-pair`. Restrict this skill strictly to maintaining preexisting `.ipynb` files, running Colab-hosted workflows, or converting legacy `.ipynb` artifacts to Marimo via `uvx marimo convert old.ipynb -o new.py`.

## Related Skills

- **`/marimo-pro`**: Default authoring skill for new reactive Python notebooks (`.py` DAG execution, `mo.ui`, `mo.state`, dual `pixi`/`uv` toolchains).
- **`/marimo-pair`**: Interactive live-kernel pair programming on running Marimo sessions.
- **`/python-pro`**: Python 3.15 (3.14 floor) standards, `uv`, `ruff`, `basedpyright`/`ty`, `prek`, and `pytest` 9+.
- **`/github-flow-lifecycle`**: 6-stage Git/GitHub Flow protocol (branch isolation, clean-notebook pre-commit checks, remote CI self-healing).

## Scope Boundaries

- **Use `/jupyter-pro` only when**:
  - Editing, cleaning, debugging, or executing a preexisting `.ipynb` file that cannot yet be retired.
  - Operating inside a mandatory hosted **Google Colab** runtime requiring `.ipynb` sync.
  - Migrating legacy `.ipynb` notebooks into reactive Marimo modules with `uvx marimo convert <notebook>.ipynb -o <notebook>.py`.
- **Delegate to `/marimo-pro` + `/marimo-pair` when**:
  - Creating any new interactive computational notebook from scratch.

## Core Requirements & Rules

1. **Follow `/python-pro` Standards**: Adhere to Python 3.15 (or `>=3.14` floor when Colab/package pins require it), Google style overrides (`ruff`), strict typing (`basedpyright`/`ty`), and zero `pip`/`Anaconda` usage.
2. **Use `uv` Exclusively**: Run tools and local Jupyter servers solely via `uv`:

   ```bash
   uv run --with plotly --with jupyter jupyter notebook --NotebookApp.allow_origin='https://colab.research.google.com' --port=8888 --ServerApp.port_retries=0 --ip=0.0.0.0 --no-browser
   ```

3. **Extract Reusable Logic**: Move non-trivial domain logic out of notebook cells into tested `src/` modules and import them cleanly rather than duplicating cell code.
4. **Targeted, Reproducible Edits**:
   - Preserve existing notebook structure and keep cells small, atomic, and top-to-bottom runnable.
   - Re-execute top-to-bottom against a clean kernel after edits and clear noisy execution outputs before committing.
5. **Migration Path (`marimo convert`)**: When modernizing a legacy notebook into version-controllable Python DAG code, run `uvx marimo convert legacy.ipynb -o notebook.py`, verify with `uv run marimo check notebook.py`, and continue authoring via `/marimo-pro` / `/marimo-pair`.
