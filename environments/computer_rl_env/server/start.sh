#!/bin/bash
set -e

echo "Starting Computer RL Environment with Supervisord..."

export DISPLAY=:99
mkdir -p /var/log/supervisor

# Create dummy .Xauthority to satisfy Xlib
touch ~/.Xauthority


# Enable accessibility
gsettings set org.gnome.desktop.interface toolkit-accessibility true 2>/dev/null || true

# Start supervisord
exec /usr/bin/supervisord -c /app/environments/computer_rl_env/server/supervisord.conf