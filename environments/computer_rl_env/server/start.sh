#!/bin/bash

Xvfb :99 -screen 0 1280x960x24 &
XVFB_PID=$!

sleep 2

export DISPLAY=:99

uvicorn computer_rl_env.server.app:create_app \
    --host 0.0.0.0 \
    --port 8000

trap "kill $XVFB_PID" EXIT