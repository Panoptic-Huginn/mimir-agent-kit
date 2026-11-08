#!/usr/bin/env bash
# ==============================================================================
# discover-servers.sh
# Discovers running marimo notebook servers and active sessions.
# Part of the marimo-pair skill for Google AntiGravity.
# ==============================================================================
set -euo pipefail

show_help() {
  cat <<'EOF'
Usage: discover-servers.sh [OPTIONS]

Discovers active local marimo servers by scanning the server state registry,
verifying process liveness and health endpoints, and querying active sessions.

Options:
  --json          Output structured JSON array of active servers and sessions (default)
  --text          Output human-readable formatted summary
  --clean-stale   Attempt to delete state files for terminated server processes
  -h, --help      Show this help message
EOF
}

OUTPUT_FORMAT="json"
CLEAN_STALE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --json)
      OUTPUT_FORMAT="json"
      shift
      ;;
    --text)
      OUTPUT_FORMAT="text"
      shift
      ;;
    --clean-stale)
      CLEAN_STALE=true
      shift
      ;;
    -h|--help)
      show_help
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      show_help >&2
      exit 2
      ;;
  esac
done

# Verify mandatory dependencies
for cmd in curl jq; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: '$cmd' is required but not installed or not in PATH." >&2
    exit 1
  fi
done

# Resolve registry search directories
REGISTRY_DIRS=()
XDG_STATE="${XDG_STATE_HOME:-${HOME:-}/.local/state}/marimo/servers"
if [[ -d "$XDG_STATE" ]]; then
  REGISTRY_DIRS+=("$XDG_STATE")
fi

# Fallback POSIX location
FALLBACK_STATE="${HOME:-}/.marimo/servers"
if [[ -d "$FALLBACK_STATE" && "$FALLBACK_STATE" != "$XDG_STATE" ]]; then
  REGISTRY_DIRS+=("$FALLBACK_STATE")
fi

# WSL interop: check Windows user profile directory if available
if command -v wslpath >/dev/null 2>&1 && [[ -n "${USERPROFILE:-}" ]]; then
  WIN_STATE="$(wslpath -u "${USERPROFILE}")/.marimo/servers"
  if [[ -d "$WIN_STATE" ]]; then
    REGISTRY_DIRS+=("$WIN_STATE")
  fi
fi

FOUND_SERVERS=()

for reg_dir in ${REGISTRY_DIRS[@]+"${REGISTRY_DIRS[@]}"}; do
  shopt -s nullglob
  json_files=("$reg_dir"/*.json)
  shopt -u nullglob

  for f in ${json_files[@]+"${json_files[@]}"}; do
    [[ -f "$f" ]] || continue

    raw_json="$(cat "$f" 2>/dev/null || true)"
    [[ -n "$raw_json" ]] || continue

    # Parse core server attributes
    pid="$(echo "$raw_json" | jq -r '.pid // empty' 2>/dev/null || true)"
    port="$(echo "$raw_json" | jq -r '.port // empty' 2>/dev/null || true)"
    host="$(echo "$raw_json" | jq -r '.host // "127.0.0.1"' 2>/dev/null || echo "127.0.0.1")"
    token="$(echo "$raw_json" | jq -r '.token // empty' 2>/dev/null || true)"
    version="$(echo "$raw_json" | jq -r '.version // "unknown"' 2>/dev/null || echo "unknown")"
    started_at="$(echo "$raw_json" | jq -r '.started_at // 0' 2>/dev/null || echo "0")"

    # Default host resolution
    if [[ "$host" == "0.0.0.0" || "$host" == "" ]]; then
      query_host="127.0.0.1"
    else
      query_host="$host"
    fi

    [[ -n "$port" ]] || continue

    # Check process liveness if PID is recorded
    is_alive=false
    if [[ -n "$pid" ]]; then
      if kill -0 "$pid" 2>/dev/null; then
        is_alive=true
      fi
    fi

    # Probe HTTP /health endpoint
    base_url="http://${query_host}:${port}"
    health_resp="$(curl -sf --max-time 1 "${base_url}/health" 2>/dev/null || true)"
    is_healthy=false
    if echo "$health_resp" | jq -e '.healthy == true' >/dev/null 2>&1; then
      is_healthy=true
    fi

    # Stale file handling
    if [[ "$is_alive" == "false" && "$is_healthy" == "false" ]]; then
      if [[ "$CLEAN_STALE" == "true" ]]; then
        rm -f "$f" 2>/dev/null || true
      fi
      continue
    fi

    # Query active sessions from /api/sessions
    AUTH_HEADER=()
    if [[ -n "$token" ]]; then
      AUTH_HEADER=(-H "Authorization: Bearer ${token}")
    fi

    sessions_resp="$(curl -sf --max-time 2 "${AUTH_HEADER[@]+"${AUTH_HEADER[@]}"}" "${base_url}/api/sessions" 2>/dev/null || echo "{}")"

    # Format session list
    sessions_json="$(echo "$sessions_resp" | jq -c '
      if type == "object" then
        to_entries | map({session_id: .key, path: .value})
      elif type == "array" then
        .
      else
        []
      end
    ' 2>/dev/null || echo "[]")"

    server_entry="$(jq -n \
      --arg server_id "${query_host}:${port}" \
      --arg url "$base_url" \
      --arg host "$query_host" \
      --argjson port "$port" \
      --arg pid "$pid" \
      --arg version "$version" \
      --argjson started_at "$started_at" \
      --arg token "$token" \
      --argjson sessions "$sessions_json" \
      '{
        server_id: $server_id,
        url: $url,
        host: $host,
        port: $port,
        pid: (if $pid != "" then ($pid | tonumber) else null end),
        version: $version,
        started_at: $started_at,
        has_token: ($token != ""),
        sessions: $sessions
      }')"

    FOUND_SERVERS+=("$server_entry")
  done
done

# Assemble final array
if [[ ${#FOUND_SERVERS[@]} -eq 0 ]]; then
  FINAL_JSON="[]"
else
  FINAL_JSON="$(printf '%s\n' "${FOUND_SERVERS[@]}" | jq -s '.')"
fi

if [[ "$OUTPUT_FORMAT" == "json" ]]; then
  echo "$FINAL_JSON" | jq '.'
else
  # Human-readable text format
  count="$(echo "$FINAL_JSON" | jq 'length')"
  echo "Found $count active marimo server(s):"
  echo "------------------------------------------------------------"
  echo "$FINAL_JSON" | jq -r '
    .[] |
    "Server: \(.url) (PID: \(.pid // "N/A"), v\(.version))\n" +
    "  Sessions (\(.sessions | length)):\n" +
    (
      if (.sessions | length) == 0 then
        "    (no active browser sessions; open notebook in browser)\n"
      else
        (.sessions | map("    - ID: \(.session_id)\n      Path: \(.path)") | join("\n")) + "\n"
      end
    )
  '
fi
