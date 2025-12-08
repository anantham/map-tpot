#!/bin/bash
# Wait for backend to be fully ready before starting frontend
# This prevents timeout errors during cold start initialization

set -e

BACKEND_URL="${BACKEND_URL:-http://localhost:5001}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-60}"
HEALTH_ENDPOINT="${BACKEND_URL}/health"

echo "🔥 Warming up backend at ${BACKEND_URL}..."
echo "⏱️  Max wait time: ${MAX_ATTEMPTS} seconds"

attempt=0

while [ $attempt -lt $MAX_ATTEMPTS ]; do
    # Use --max-time to avoid hanging indefinitely
    if curl -s -f --max-time 2 "${HEALTH_ENDPOINT}" > /dev/null 2>&1; then
        echo "✅ Backend ready after ${attempt} seconds!"
        exit 0
    fi

    # Show progress every 5 seconds
    if [ $((attempt % 5)) -eq 0 ]; then
        echo "⏳ Still waiting for backend... (${attempt}s elapsed)"
    fi

    sleep 1
    ((attempt++))
done

echo "❌ Backend failed to respond within ${MAX_ATTEMPTS} seconds"
echo "💡 Check if the backend process is running and listening on ${BACKEND_URL}"
exit 1
