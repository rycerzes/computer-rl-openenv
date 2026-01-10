#!/bin/bash
set -e

echo "Starting Computer RL Environment with Supervisord..."

export DISPLAY=:99
mkdir -p /var/log/supervisor

# Start supervisord
exec /usr/bin/supervisord -c /app/environments/computer_rl_env/server/supervisord.conf