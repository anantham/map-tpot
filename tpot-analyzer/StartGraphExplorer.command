#!/bin/bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/graph-explorer"

if [ ! -d "$FRONTEND_DIR" ]; then
  echo "✗ graph-explorer directory not found at $FRONTEND_DIR"
  exit 1
fi

printf '→ Launching Flask API server via Terminal…\n'
BACKEND_CMD="cd $(printf '%q' "$PROJECT_ROOT"); "
if [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
  BACKEND_CMD+="source .venv/bin/activate; "
fi
BACKEND_CMD+="API_LOG_LEVEL=DEBUG CLUSTER_LOG_LEVEL=DEBUG python3 -m scripts.start_api_server"

escape_for_applescript() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

run_in_terminal() {
  local command="$1"
  local description="$2"
  if ! osascript <<EOF
tell application "Terminal"
  do script "$(escape_for_applescript "$command")"
  activate
end tell
EOF
  then
    printf '✗ Unable to automate %s. Run manually:\n   %s\n' "$description" "$command"
    return 1
  fi
}

run_in_terminal "$BACKEND_CMD" "Flask API server"

printf '→ Launching Graph Explorer dev server via Terminal…\n'
FRONTEND_CMD="cd $(printf '%q' "$FRONTEND_DIR"); "
FRONTEND_CMD+="if [ ! -d node_modules ]; then npm install; fi; "
FRONTEND_CMD+="npm run dev"

run_in_terminal "$FRONTEND_CMD" "Graph Explorer dev server"

printf '→ Opening browser to http://localhost:5173 …\n'
open "http://localhost:5173" >/dev/null 2>&1 || true

printf '✓ Startup commands dispatched. Monitor the spawned Terminal windows for logs.\n'
