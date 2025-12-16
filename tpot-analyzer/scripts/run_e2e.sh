#!/usr/bin/env bash
# E2E Test Runner for tpot-analyzer (Playwright)
#
# Usage:
#   ./scripts/run_e2e.sh [mock|mock-no-server|full|ui|headed|debug]
#
# Notes:
# - `mock` uses a mocked backend (API routes are intercepted).
# - `full` requires the Flask backend at http://localhost:5001.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${script_dir}/../graph-explorer"

if ! command -v node >/dev/null 2>&1; then
  echo "Error: node is not available on PATH. Install Node.js or initialize nvm before running e2e." >&2
  exit 1
fi
if ! command -v npx >/dev/null 2>&1; then
  echo "Error: npx is not available on PATH. Ensure npm is installed." >&2
  exit 1
fi

case "${1:-mock}" in
  mock)
    echo "Running mocked E2E tests (no backend required; Vite dev server auto-starts)..."
    npx playwright test e2e/cluster_mock.spec.ts --reporter=line
    ;;
  mock-no-server)
    echo "Running mocked E2E tests against an already-running dev server (PW_NO_SERVER=1)..."
    PW_NO_SERVER=1 npx playwright test e2e/cluster_mock.spec.ts --reporter=line
    ;;
  full)
    echo "Running full E2E tests (backend must be running at http://localhost:5001)..."
    echo "Start backend: cd tpot-analyzer && .venv/bin/python -m scripts.start_api_server"
    npx playwright test e2e/cluster.spec.ts --reporter=line
    ;;
  ui)
    echo "Opening Playwright UI mode..."
    npx playwright test --ui
    ;;
  headed)
    echo "Running mocked tests in headed mode..."
    npx playwright test e2e/cluster_mock.spec.ts --headed --reporter=line
    ;;
  debug)
    echo "Running mocked tests in debug mode..."
    npx playwright test e2e/cluster_mock.spec.ts --debug
    ;;
  *)
    echo "Usage: $0 [mock|mock-no-server|full|ui|headed|debug]" >&2
    exit 1
    ;;
esac
