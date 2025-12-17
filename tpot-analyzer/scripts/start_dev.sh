#!/bin/bash
# Orchestrated startup: backend first, then frontend after warmup
# Eliminates timeout errors during cold start

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

export TPOT_LOG_DIR="${TPOT_LOG_DIR:-$PROJECT_ROOT/logs}"
export API_LOG_LEVEL="${API_LOG_LEVEL:-DEBUG}"
export CLUSTER_LOG_LEVEL="${CLUSTER_LOG_LEVEL:-DEBUG}"

mkdir -p "$TPOT_LOG_DIR"

echo "🚀 Starting TPOT Analyzer development environment..."
echo "📂 Project root: ${PROJECT_ROOT}"
echo "🧾 Log dir: ${TPOT_LOG_DIR}"
echo "🔎 API_LOG_LEVEL=${API_LOG_LEVEL} CLUSTER_LOG_LEVEL=${CLUSTER_LOG_LEVEL}"
echo ""

# Cleanup function
cleanup() {
    echo ""
    echo "🛑 Shutting down services..."
    if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "   Stopping backend (PID: $BACKEND_PID)..."
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
    if [ -n "$FRONTEND_PID" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
        echo "   Stopping frontend (PID: $FRONTEND_PID)..."
        kill "$FRONTEND_PID" 2>/dev/null || true
    fi
    echo "✅ Cleanup complete"
    exit 0
}

trap cleanup SIGINT SIGTERM

# 1. Start backend
echo "1️⃣  Starting Flask backend..."
source .venv/bin/activate
python3 -m scripts.start_api_server > "${TPOT_LOG_DIR}/backend.log" 2>&1 &
BACKEND_PID=$!
echo "   Backend started (PID: $BACKEND_PID)"
echo "   Stdout/stderr: ${TPOT_LOG_DIR}/backend.log"
echo "   API logs:      ${TPOT_LOG_DIR}/api.log"
echo ""

# 2. Wait for backend to be ready
echo "2️⃣  Waiting for backend to initialize..."
./scripts/wait_for_backend.sh
echo ""

# 3. Start frontend
echo "3️⃣  Starting Vite frontend..."
cd graph-explorer
npm run dev > "${TPOT_LOG_DIR}/vite.log" 2>&1 &
FRONTEND_PID=$!
echo "   Frontend started (PID: $FRONTEND_PID)"
echo "   Stdout/stderr: ${TPOT_LOG_DIR}/vite.log"
echo "   Frontend logs: ${TPOT_LOG_DIR}/frontend.log (via POST /api/log)"
echo ""

echo "✨ Development environment ready!"
echo ""
echo "📊 Backend:  http://localhost:5001"
echo "🌐 Frontend: http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Wait for user interrupt
wait
