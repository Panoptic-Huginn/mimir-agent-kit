#!/usr/bin/env bash
# ==============================================================================
# scripts/ci/run_local_ci.sh - Local CI Invariant Verification Gate
# Project: mimir-agent-kit
#
# Enforces Invariant 3 of rules/AGENTS.md:
# "Mandatory Pre-Commit Local CI Gate: NEVER run git commit until the
#  repository's full local CI suite has executed on the current working tree
#  and exited with status code 0."
#
# Sequential verification stages:
#   1. Lockfile synchronization check (uv lock --check)
#   2. Curated pre-commit hooks on all files (uv run pre-commit run --all-files --show-diff-on-failure)
#   3. Comprehensive test suite execution (uv run pytest)
# ==============================================================================

set -euo pipefail

# Determine repository root directory dynamically
SOURCE="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${SOURCE}")" && pwd)"
if command -v git &> /dev/null && git -C "${SCRIPT_DIR}" rev-parse --is-inside-work-tree &> /dev/null; then
    REPO_ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel)"
else
    REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
fi
cd "${REPO_ROOT}"

# Configure terminal formatting / ANSI colors (disabled if stdout is not a TTY or NO_COLOR is set)
if [[ -t 1 ]] && [[ -z "${NO_COLOR:-}" ]]; then
    BOLD="\033[1m"
    DIM="\033[2m"
    GREEN="\033[0;32m"
    BLUE="\033[0;34m"
    CYAN="\033[0;36m"
    RED="\033[0;31m"
    YELLOW="\033[0;33m"
    RESET="\033[0m"
else
    BOLD=""
    DIM=""
    GREEN=""
    BLUE=""
    CYAN=""
    RED=""
    YELLOW=""
    RESET=""
fi

# Help message
if [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
    printf "%b\n" "${BOLD}Usage:${RESET} $(basename "$0") [pytest-options...]"
    printf "%b\n" ""
    printf "%b\n" "Runs the local CI invariant verification gate for mimir-agent-kit."
    printf "%b\n" ""
    printf "%b\n" "${BOLD}Verification Stages:${RESET}"
    printf "%b\n" "  1. uv lock --check"
    printf "%b\n" "  2. uv run pre-commit run --all-files --show-diff-on-failure"
    printf "%b\n" "  3. uv run pytest [pytest-options...]"
    printf "%b\n" ""
    printf "%b\n" "${BOLD}Exit Code:${RESET} 0 on success, non-zero (1) on any failure."
    exit 0
fi

# Track current stage for actionable diagnostic error reporting
CURRENT_STAGE="Initialization"
START_TIMESTAMP="$(date +%s)"

handle_error() {
    local exit_code="$?"
    printf "\n%b\n" "${RED}${BOLD}============================================================${RESET}" >&2
    printf "%b\n" "${RED}${BOLD}[LOCAL CI GATE FAILED]${RESET}" >&2
    printf "%b\n" "${RED}Stage:${RESET}     ${CURRENT_STAGE}" >&2
    printf "%b\n" "${RED}Exit Code:${RESET} ${exit_code}" >&2
    printf "%b\n" "${RED}${BOLD}============================================================${RESET}" >&2
    exit 1
}

trap handle_error ERR INT TERM

# Banner
printf "%b\n" "${BLUE}${BOLD}============================================================${RESET}"
printf "%b\n" "${BLUE}${BOLD}Mimir-Agent-Kit: Local Pre-Commit CI Gate${RESET}"
printf "%b\n" "${DIM}Root: ${REPO_ROOT}${RESET}"
printf "%b\n" "${BLUE}${BOLD}============================================================${RESET}"

# Verify uv is installed and accessible
if ! command -v uv &> /dev/null; then
    printf "%b\n" "${RED}[ERROR] 'uv' executable not found in PATH.${RESET}" >&2
    printf "%b\n" "Please install uv (https://docs.astral.sh/uv/) to run local CI checks." >&2
    exit 1
fi

# Stage 1: Lockfile synchronization
CURRENT_STAGE="Stage 1: uv lock --check"
printf "\n%b\n" "${CYAN}--> [1/3] Verifying uv.lock consistency...${RESET}"
uv lock --check
printf "%b\n" "${GREEN}✓ uv.lock is synchronized with pyproject.toml${RESET}"

# Stage 2: Curated pre-commit hooks
CURRENT_STAGE="Stage 2: uv run pre-commit run --all-files"
printf "\n%b\n" "${CYAN}--> [2/3] Running curated pre-commit hooks on all files...${RESET}"
uv run pre-commit run --all-files --show-diff-on-failure
printf "%b\n" "${GREEN}✓ All pre-commit hooks passed${RESET}"

# Stage 3: Comprehensive test suite
CURRENT_STAGE="Stage 3: uv run pytest"
printf "\n%b\n" "${CYAN}--> [3/3] Running full test suite & agentic settings verification...${RESET}"
if [[ $# -gt 0 ]]; then
    uv run pytest "$@"
else
    uv run pytest
fi
printf "%b\n" "${GREEN}✓ All pytest test suites passed${RESET}"

# Success summary
END_TIMESTAMP="$(date +%s)"
DURATION=$((END_TIMESTAMP - START_TIMESTAMP))

printf "\n%b\n" "${GREEN}${BOLD}============================================================${RESET}"
printf "%b\n" "${GREEN}${BOLD}ALL LOCAL CI CHECKS PASSED SUCCESSFULLY in ${DURATION}s!${RESET}"
printf "%b\n" "${GREEN}${BOLD}============================================================${RESET}"
exit 0
