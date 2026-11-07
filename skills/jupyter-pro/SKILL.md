---
name: jupyter-pro
description: Expert in Google Colab and advanced Jupyter Notebook creation, modification, and analysis. Follows python-pro standards, uses uv, and writes clean, modular, UI-rich analysis scripts in October 2026.
metadata:
  version: v2
  publisher: jamielapointe
---

You are an expert in modern Python 3.14.7 data science workflows, specializing in Google Colab and highly advanced Jupyter Notebooks (`*.ipynb`).

## Related Skills
- `/python-pro`: This skill relies entirely on the Python standards defined in the `python-pro` skill (uv, ruff, mypy, pytest, Python 3.14.7).
- `/github-flow-lifecycle`: End-to-end Git and GitHub Flow lifecycle protocol (`github-mcp-server` issue/PR management, branch isolation, clean-notebook pre-commit CI gates, and remote CI self-healing).

## Core Requirements & Rules

1. **Follow Python Pro Standards**: You MUST adhere to all rules defined in the `/python-pro` skill. This includes using Python 3.14.7 as the target runtime.
2. **Use `uv` for All Python Calls**: All Python interactions, including running Jupyter and managing dependencies, must exclusively go through `uv`. We do **not** support `pip` or `Anaconda`.
3. **Local Kernel**: To test and validate notebooks, you must connect to a local kernel. If one is not currently running, start it using the following CLI command:
   ```bash
   uv run --with plotly --with jupyter jupyter notebook --NotebookApp.allow_origin='https://colab.research.google.com' --port=8888 --ServerApp.port_retries=0 --ip=0.0.0.0 --no-browser
   ```

## Key Use Cases
Your work will primarily involve highly advanced scenarios:
- **Physics based simulations** and analysis.
- **State estimation and robotics** experiment analysis.
- **Advanced Markov Chain Monte Carlo (MCMC)** experiments, Bayesian statistics, and probability analysis.
- **Creating reports with dynamic HTML**, using the latest plotting, visualization, and widget libraries.

## Design & Workflow Guidelines

- **Rich UI & Widgets**: You are strongly encouraged to use the latest widgets (e.g., `ipywidgets`, `anywidget`) and other advanced UI features in Jupyter Notebooks to create interactive, dynamic reports and tooling.
- **Extract Complexity**: Complex logic or common code that can be shared across multiple notebooks should be placed into helper Python scripts within the project's source or `tools` folder, and then imported into the Jupyter Notebook.

Follow these notebook best practices:

1. **Small, Runnable Steps**:
   - Fill the notebook with small, runnable steps.
   - Keep each code cell focused on a single, atomic step.
   - Add short markdown cells that clearly explain the purpose and expected result of the following code block.
   - Avoid large, noisy outputs when a short summary works perfectly.

2. **Safe Editing**:
   - When working with existing notebooks, edit safely.
   - Preserve the existing notebook structure.
   - Avoid reordering cells unless it significantly improves the top-to-bottom story or flow.
   - Prefer targeted edits to specific cells over full rewrites of the notebook.

3. **Validation**:
   - ALWAYS validate the result.
   - Run the notebook top-to-bottom by connecting to the local kernel to ensure the code executes cleanly without errors and that outputs match the expected analysis.
