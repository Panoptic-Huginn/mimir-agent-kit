#!/usr/bin/env bash
# ==============================================================================
# execute-code.sh
# Streams Python execution to a running marimo notebook session via HTTP SSE.
# Part of the marimo-pair skill for Google AntiGravity.
# ==============================================================================
set -euo pipefail

show_help() {
  cat <<'EOF'
Usage: execute-code.sh [OPTIONS] [CODE_OR_FILE]

Executes Python code or scratchpad instructions against a live marimo session
over HTTP/SSE (POST /api/kernel/execute).

Options:
  --url URL           Base URL of marimo server (default: $MARIMO_URL or http://127.0.0.1:2718)
  --session ID        Target session ID (default: $MARIMO_SESSION_ID or auto-resolved)
  --file PATH         Notebook path used to resolve session ID
  --token TOKEN       Bearer auth token (default: $MARIMO_TOKEN)
  -c, --code CODE     Inline Python code string to execute
  --code-file FILE    Path to Python file containing code to execute ('-' for stdin)
  -h, --help          Show this help message

Input modes:
  execute-code.sh -c "print(df.shape)"
  execute-code.sh --code-file analysis.py
  execute-code.sh - <<'PY'
  import marimo._code_mode as cm
  async with cm.get_context() as ctx:
      print(ctx.cells.keys())
  PY
EOF
}

TARGET_URL="${MARIMO_URL:-http://127.0.0.1:2718}"
SESSION_ID="${MARIMO_SESSION_ID:-}"
NOTEBOOK_FILE=""
TOKEN="${MARIMO_TOKEN:-}"
CODE_INPUT=""
READ_STDIN=false

# Dependency validation
for cmd in curl jq; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: '$cmd' is required but not installed or not in PATH." >&2
    exit 1
  fi
done

# Argument parsing
while [[ $# -gt 0 ]]; do
  case "$1" in
    --url)
      if [[ $# -lt 2 ]]; then
        echo "Error: Option '$1' requires an argument." >&2
        exit 2
      fi
      TARGET_URL="$2"
      shift 2
      ;;
    --session)
      if [[ $# -lt 2 ]]; then
        echo "Error: Option '$1' requires an argument." >&2
        exit 2
      fi
      SESSION_ID="$2"
      shift 2
      ;;
    --file)
      if [[ $# -lt 2 ]]; then
        echo "Error: Option '$1' requires an argument." >&2
        exit 2
      fi
      NOTEBOOK_FILE="$2"
      shift 2
      ;;
    --token)
      if [[ $# -lt 2 ]]; then
        echo "Error: Option '$1' requires an argument." >&2
        exit 2
      fi
      TOKEN="$2"
      shift 2
      ;;
    -c|--code)
      if [[ $# -lt 2 ]]; then
        echo "Error: Option '$1' requires an argument." >&2
        exit 2
      fi
      CODE_INPUT="$2"
      shift 2
      ;;
    --code-file)
      if [[ $# -lt 2 ]]; then
        echo "Error: Option '$1' requires an argument." >&2
        exit 2
      fi
      if [[ "$2" == "-" ]]; then
        READ_STDIN=true
      else
        if [[ ! -f "$2" ]]; then
          echo "Error: Code file '$2' not found." >&2
          exit 2
        fi
        CODE_INPUT="$(cat "$2")"
      fi
      shift 2
      ;;
    -h|--help)
      show_help
      exit 0
      ;;
    -)
      READ_STDIN=true
      shift
      ;;
    -*|--*)
      echo "Error: Unexpected option: $1" >&2
      show_help >&2
      exit 2
      ;;
    *)
      if [[ -z "$CODE_INPUT" && "$READ_STDIN" == "false" ]]; then
        if [[ -f "$1" ]]; then
          CODE_INPUT="$(cat "$1")"
        else
          CODE_INPUT="$1"
        fi
        shift
      else
        echo "Error: Unexpected argument: $1" >&2
        show_help >&2
        exit 2
      fi
      ;;
  esac
done

if [[ "$READ_STDIN" == "true" ]]; then
  CODE_INPUT="$(cat)"
fi

if [[ -z "$CODE_INPUT" ]]; then
  echo "Error: No Python code provided for execution." >&2
  show_help >&2
  exit 2
fi

# Clean trailing slash from URL
TARGET_URL="${TARGET_URL%/}"

# Auth header array
AUTH_HEADERS=()
if [[ -n "$TOKEN" ]]; then
  AUTH_HEADERS=(-H "Authorization: Bearer ${TOKEN}")
fi

# Resolve session ID if not explicitly specified
if [[ -z "$SESSION_ID" ]]; then
  sessions_raw="$(curl -sf --max-time 3 "${AUTH_HEADERS[@]+"${AUTH_HEADERS[@]}"}" "${TARGET_URL}/api/sessions" 2>/dev/null || true)"
  if [[ -z "$sessions_raw" ]]; then
    echo "Error: Could not retrieve sessions from ${TARGET_URL}/api/sessions. Is the server running?" >&2
    exit 1
  fi

  # Normalize session object/array
  normalized_sessions="$(echo "$sessions_raw" | jq -c '
    if type == "object" then
      to_entries | map({session_id: .key, path: .value})
    elif type == "array" then
      .
    else
      []
    end
  ' 2>/dev/null || echo "[]")"

  session_count="$(echo "$normalized_sessions" | jq 'length')"

  if [[ "$session_count" -eq 0 ]]; then
    echo "Error: No active sessions found on ${TARGET_URL}." >&2
    echo "Marimo requires an active browser session to evaluate kernel code." >&2
    echo "Please open the notebook in a browser tab to activate a session." >&2
    exit 1
  fi

  if [[ -n "$NOTEBOOK_FILE" ]]; then
    matched_id="$(echo "$normalized_sessions" | jq -r --arg path "$NOTEBOOK_FILE" '
      .[] | select(.path == $path or (.path | endswith($path))) | .session_id
    ' | head -n 1)"
    if [[ -n "$matched_id" && "$matched_id" != "null" ]]; then
      SESSION_ID="$matched_id"
    else
      echo "Error: No active session matches notebook path '$NOTEBOOK_FILE'." >&2
      echo "Available sessions:" >&2
      echo "$normalized_sessions" | jq -r '.[] | "  - Session: \(.session_id), Path: \(.path)"' >&2
      exit 1
    fi
  elif [[ "$session_count" -eq 1 ]]; then
    SESSION_ID="$(echo "$normalized_sessions" | jq -r '.[0].session_id')"
  else
    echo "Multiple active sessions detected. Specify --session <ID> or --file <PATH>:" >&2
    echo "$normalized_sessions" | jq -r '.[] | "  - Session: \(.session_id), Path: \(.path)"' >&2
    exit 1
  fi
fi

# Construct JSON payload
JSON_PAYLOAD="$(jq -n --arg code "$CODE_INPUT" '{code: $code}')"

# POST execution request and stream SSE response
EXECUTE_URL="${TARGET_URL}/api/kernel/execute"
CURRENT_EVENT=""
EXIT_CODE=0
RECEIVED_SSE=false
NON_SSE_BUFFER=""

CURL_ERR_FILE="$(mktemp)"
CURL_EXIT_FILE="$(mktemp)"
trap 'rm -f "$CURL_ERR_FILE" "$CURL_EXIT_FILE"' EXIT

while IFS= read -r line || [[ -n "$line" ]]; do
  # Strip carriage return if present
  line="${line%$'\r'}"

  if [[ "$line" =~ ^event:[[:space:]]*(.*)$ ]]; then
    CURRENT_EVENT="${BASH_REMATCH[1]}"
    RECEIVED_SSE=true
  elif [[ "$line" =~ ^data:[[:space:]]*(.*)$ ]]; then
    data_content="${BASH_REMATCH[1]}"
    RECEIVED_SSE=true

    case "$CURRENT_EVENT" in
      stdout)
        # Extract text field if formatted as JSON
        if echo "$data_content" | jq -e '.data' >/dev/null 2>&1; then
          echo "$data_content" | jq -r '.data'
        else
          echo "$data_content"
        fi
        ;;
      stderr)
        if echo "$data_content" | jq -e '.data' >/dev/null 2>&1; then
          echo "$data_content" | jq -r '.data' >&2
        else
          echo "$data_content" >&2
        fi
        ;;
      done)
        # Check completion status
        if echo "$data_content" | jq -e '.success == false' >/dev/null 2>&1; then
          EXIT_CODE=1
        fi
        # If there is a return output data, print it if non-empty
        out="$(echo "$data_content" | jq -r '.output.data // empty' 2>/dev/null || true)"
        if [[ -n "$out" && "$out" != "null" ]]; then
          echo "$out"
        fi
        ;;
      *)
        # Unknown or generic event, passthrough if meaningful
        if [[ -n "$data_content" && "$data_content" != "{}" ]]; then
          echo "$data_content"
        fi
        ;;
    esac
  elif [[ -z "$line" ]]; then
    # Empty line marks end of event block in SSE specification
    CURRENT_EVENT=""
  else
    # Capture non-SSE error lines (e.g. HTTP 4xx/5xx error bodies)
    NON_SSE_BUFFER="${NON_SSE_BUFFER}${line}"$'\n'
  fi
done < <(
  if curl -sS -N --fail-with-body -X POST \
    -H "Content-Type: application/json" \
    -H "Marimo-Session-Id: ${SESSION_ID}" \
    "${AUTH_HEADERS[@]+"${AUTH_HEADERS[@]}"}" \
    --data "$JSON_PAYLOAD" \
    "$EXECUTE_URL" 2>"$CURL_ERR_FILE"; then
    echo 0 >"$CURL_EXIT_FILE"
  else
    curl_rc=$?
    echo "$curl_rc" >"$CURL_EXIT_FILE"
  fi
)

CURL_EXIT="$(cat "$CURL_EXIT_FILE" 2>/dev/null || echo 1)"
CURL_STDERR="$(cat "$CURL_ERR_FILE" 2>/dev/null || echo "")"

if [[ "$CURL_EXIT" -ne 0 || "$RECEIVED_SSE" == "false" ]]; then
  if [[ -n "$CURL_STDERR" ]]; then
    echo "$CURL_STDERR" >&2
  fi
  if [[ -n "$NON_SSE_BUFFER" ]]; then
    trimmed_buffer="$(echo "$NON_SSE_BUFFER" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    if [[ -n "$trimmed_buffer" ]]; then
      echo "Error: Server response: $trimmed_buffer" >&2
    fi
  fi
  if [[ "$CURL_EXIT" -eq 0 && "$RECEIVED_SSE" == "false" ]]; then
    echo "Error: No SSE events received from ${EXECUTE_URL}." >&2
  fi
  if [[ "$EXIT_CODE" -eq 0 ]]; then
    EXIT_CODE=1
  fi
fi

exit "$EXIT_CODE"
