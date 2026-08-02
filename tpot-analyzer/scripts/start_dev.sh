#!/usr/bin/env bash
# Reproducible local Research Notes runtime: one token, one origin, explicit data.

set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

CHECK_ONLY=false
if [[ "${1:-}" == "--check" ]]; then
    CHECK_ONLY=true
elif [[ $# -gt 0 ]]; then
    echo "✗ Usage: ./scripts/start_dev.sh [--check]" >&2
    exit 2
fi

# This resolver prints shell-quoted, non-secret assignments only. It validates
# the archive schema and persistent state destination before either process starts.
if ! RUNTIME_ASSIGNMENTS="$(python3 -m scripts.dev_runtime --project-root "$PROJECT_ROOT" --format shell)"; then
    exit 2
fi
eval "$RUNTIME_ASSIGNMENTS"
unset RUNTIME_ASSIGNMENTS
export ARCHIVE_DB_PATH SNAPSHOT_DIR CORS_ORIGINS VITE_API_URL

if [[ -n "${TPOT_DEV_PYTHON:-}" ]]; then
    DEV_PYTHON="$TPOT_DEV_PYTHON"
elif [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
    DEV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
elif [[ -n "${TPOT_PRIMARY_PROJECT_ROOT:-}" && -x "$TPOT_PRIMARY_PROJECT_ROOT/.venv/bin/python" ]]; then
    DEV_PYTHON="$TPOT_PRIMARY_PROJECT_ROOT/.venv/bin/python"
else
    echo "✗ No project Python environment found." >&2
    echo "  Set TPOT_DEV_PYTHON or create $PROJECT_ROOT/.venv." >&2
    exit 2
fi

if ! "$DEV_PYTHON" -c "import flask, flask_cors, flask_limiter, pandas, scipy" 2>/dev/null; then
    echo "✗ Development Python is missing required backend packages: $DEV_PYTHON" >&2
    echo "  Install requirements into that environment or set TPOT_DEV_PYTHON." >&2
    exit 2
fi
if ! command -v npm >/dev/null 2>&1; then
    echo "✗ npm is required to start the graph explorer." >&2
    exit 2
fi
if [[ ! -x "$PROJECT_ROOT/graph-explorer/node_modules/.bin/vite" ]]; then
    echo "✗ Frontend dependencies are absent." >&2
    echo "  Run: cd '$PROJECT_ROOT/graph-explorer' && npm ci" >&2
    exit 2
fi

# A caller may pin a token for an existing local session. Otherwise every start
# gets a fresh secret. The same process environment feeds Flask and Vite; the
# value is never echoed or written to an env file.
if [[ -z "${TPOT_CURATOR_TOKEN:-}" ]]; then
    TPOT_CURATOR_TOKEN="$("$DEV_PYTHON" -c 'import secrets; print(secrets.token_hex(32))')"
fi
export TPOT_CURATOR_TOKEN
export VITE_TPOT_CURATOR_TOKEN="$TPOT_CURATOR_TOKEN"

export TPOT_LOG_DIR="${TPOT_LOG_DIR:-$PROJECT_ROOT/logs}"
export API_LOG_LEVEL="${API_LOG_LEVEL:-INFO}"
export CLUSTER_LOG_LEVEL="${CLUSTER_LOG_LEVEL:-INFO}"
mkdir -p "$TPOT_LOG_DIR"

echo "✓ Research Notes runtime configuration"
echo "  Archive (read-only): $ARCHIVE_DB_PATH"
echo "  Snapshot/state dir:  $SNAPSHOT_DIR"
echo "  Persistent tag DB:   $TPOT_DEV_ACCOUNT_TAGS_DB_PATH"
echo "  Backend:              $TPOT_DEV_API_ORIGIN"
echo "  Frontend:             $TPOT_DEV_UI_ORIGIN"
echo "  Curator token:        ephemeral/shared (value not printed)"

if [[ "$CHECK_ONLY" == true ]]; then
    echo "✓ Preflight complete; no service was started"
    exit 0
fi

require_free_port() {
    local port="$1"
    if ! "$DEV_PYTHON" -c \
        'import socket, sys; s=socket.socket(); s.bind(("127.0.0.1", int(sys.argv[1]))); s.close()' \
        "$port" 2>/dev/null; then
        echo "✗ localhost:$port is already in use; stop that stale service and retry." >&2
        exit 1
    fi
}
require_free_port 5001
require_free_port 5184

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
    status=$?
    trap - EXIT INT TERM
    for pid in "$FRONTEND_PID" "$BACKEND_PID"; do
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    [[ -n "$FRONTEND_PID" ]] && wait "$FRONTEND_PID" 2>/dev/null || true
    [[ -n "$BACKEND_PID" ]] && wait "$BACKEND_PID" 2>/dev/null || true
    exit "$status"
}
trap cleanup EXIT INT TERM

echo "→ Starting Flask backend"
"$DEV_PYTHON" -m scripts.start_api_server --host 127.0.0.1 --port 5001 \
    > "$TPOT_LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!

if ! BACKEND_URL="$TPOT_DEV_API_ORIGIN" MAX_ATTEMPTS=60 ./scripts/wait_for_backend.sh; then
    echo "✗ Backend failed; inspect $TPOT_LOG_DIR/backend.log" >&2
    exit 1
fi
if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "✗ Backend exited during startup; inspect $TPOT_LOG_DIR/backend.log" >&2
    exit 1
fi

echo "→ Starting Vite frontend"
(
    cd graph-explorer
    npm run dev -- --host localhost --port 5184 --strictPort
) > "$TPOT_LOG_DIR/vite.log" 2>&1 &
FRONTEND_PID=$!

frontend_attempt=0
until curl -fsS --max-time 2 "$TPOT_DEV_UI_ORIGIN" >/dev/null 2>&1; do
    if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
        echo "✗ Frontend exited during startup; inspect $TPOT_LOG_DIR/vite.log" >&2
        exit 1
    fi
    if (( frontend_attempt >= 30 )); then
        echo "✗ Frontend did not become ready; inspect $TPOT_LOG_DIR/vite.log" >&2
        exit 1
    fi
    sleep 1
    ((frontend_attempt += 1))
done

echo "✓ Development environment ready: $TPOT_DEV_UI_ORIGIN/?view=research-notes"
echo "  Logs: $TPOT_LOG_DIR/backend.log and $TPOT_LOG_DIR/vite.log"
echo "  Press Ctrl+C to stop both services"

while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
    sleep 1
done
echo "✗ A development service stopped unexpectedly; inspect $TPOT_LOG_DIR" >&2
exit 1
