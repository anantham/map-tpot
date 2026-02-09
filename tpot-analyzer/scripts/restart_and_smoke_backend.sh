#!/usr/bin/env bash
# Restart TPOT backend and run discovery smoke verification.
#
# Usage:
#   ./scripts/restart_and_smoke_backend.sh
#   ./scripts/restart_and_smoke_backend.sh --host 127.0.0.1 --port 5001
#   ./scripts/restart_and_smoke_backend.sh --no-verify

set -euo pipefail

HOST="127.0.0.1"
PORT="5001"
WAIT_SECONDS="45"
VERIFY="1"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="${2:-}"
      shift 2
      ;;
    --port)
      PORT="${2:-}"
      shift 2
      ;;
    --wait-seconds)
      WAIT_SECONDS="${2:-}"
      shift 2
      ;;
    --no-verify)
      VERIFY="0"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PROJECT_DIR}/.venv/bin/python"
LOG_DIR="${PROJECT_DIR}/logs"
LOG_PATH="${LOG_DIR}/backend_restart.log"
BASE_URL="http://${HOST}:${PORT}"

mkdir -p "${LOG_DIR}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "✗ Missing venv python at ${PYTHON_BIN}" >&2
  echo "  Next: cd tpot-analyzer && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

echo "TPOT backend restart + smoke"
echo "- project_dir: ${PROJECT_DIR}"
echo "- base_url: ${BASE_URL}"

if lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "• Existing listener(s) found on :${PORT}; terminating..."
  while IFS= read -r pid; do
    [[ -n "${pid}" ]] || continue
    kill "${pid}" 2>/dev/null || true
  done < <(lsof -t -nP -iTCP:"${PORT}" -sTCP:LISTEN | sort -u)
  sleep 1
fi

echo "• Starting backend..."
(
  cd "${PROJECT_DIR}"
  nohup "${PYTHON_BIN}" -m scripts.start_api_server --host "${HOST}" --port "${PORT}" >"${LOG_PATH}" 2>&1 &
  echo $! > "${LOG_DIR}/backend_restart.pid"
)
BACKEND_PID="$(cat "${LOG_DIR}/backend_restart.pid")"
echo "  pid=${BACKEND_PID} log=${LOG_PATH}"

echo "• Waiting for /api/health (${WAIT_SECONDS}s max)..."
ready="0"
for _ in $(seq 1 "${WAIT_SECONDS}"); do
  if curl -sSf "${BASE_URL}/api/health" >/dev/null 2>&1; then
    ready="1"
    break
  fi
  sleep 1
done

if [[ "${ready}" != "1" ]]; then
  echo "✗ Backend did not become healthy in time"
  echo "  Last log lines:"
  tail -n 25 "${LOG_PATH}" || true
  exit 1
fi

echo "✓ Backend healthy at ${BASE_URL}/api/health"

if [[ "${VERIFY}" == "1" ]]; then
  echo "• Running discovery smoke verification..."
  (
    cd "${PROJECT_DIR}"
    "${PYTHON_BIN}" -m scripts.verify_discovery_endpoint --base-url "${BASE_URL}"
  )
  verify_code=$?
  if [[ "${verify_code}" -ne 0 ]]; then
    echo "✗ Discovery smoke verification failed"
    exit "${verify_code}"
  fi
  echo "✓ Discovery smoke verification passed"
else
  echo "• Skipped smoke verification (--no-verify)"
fi

echo ""
echo "Next steps:"
echo "- Tail backend log: tail -f ${LOG_PATH}"
echo "- Stop backend: kill ${BACKEND_PID}"
