#!/bin/bash
set -e

echo "Starting Computer RL Environment..."

Xvfb :99 -screen 0 1280x960x24 -ac +render -noreset &
XVFB_PID=$!
echo "Started Xvfb with PID: $XVFB_PID"

sleep 2

export DISPLAY=:99

cd /app

function cleanup() {
    echo "Shutting down gracefully..."
    if [ -n "$XVFB_PID" ]; then
        kill $XVFB_PID 2>/dev/null || true
    fi
    exit 0
}

trap cleanup SIGTERM SIGINT EXIT

exec /app/.venv/bin/uvicorn computer_rl_env.server.app:create_app \
    --host 0.0.0.0 \
    --port 8000 \
    --factory