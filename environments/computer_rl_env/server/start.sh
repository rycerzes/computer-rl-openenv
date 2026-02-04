#!/bin/bash
set -e

echo "Starting Computer RL Environment with Supervisord..."

export DISPLAY=:99
mkdir -p /var/log/supervisor

# Create dummy .Xauthority to satisfy Xlib
# Start DBus system bus (Required for Chrome)
mkdir -p /run/dbus
if [ -f /var/run/dbus/pid ]; then
    rm -f /var/run/dbus/pid
fi
dbus-daemon --system --fork

# Create .Xauthority if it doesn't exist (Fixes Xlib error)
touch ~/.Xauthority

# Enable accessibility
gsettings set org.gnome.desktop.interface toolkit-accessibility true 2>/dev/null || true

# Start DBus session bus
# We use a fixed address so it can be shared with docker exec sessions
export DBUS_SESSION_BUS_ADDRESS=unix:path=/dev/shm/dbus_session_socket
if [ -f /var/run/dbus/session_pid ]; then
    rm -f /var/run/dbus/session_pid
fi
# Clean up socket if exists
if [ -S /dev/shm/dbus_session_socket ]; then
    rm -f /dev/shm/dbus_session_socket
fi

echo "Starting DBus session at $DBUS_SESSION_BUS_ADDRESS..."
dbus-daemon --session --fork --address=$DBUS_SESSION_BUS_ADDRESS --print-pid > /var/run/dbus/session_pid

# Persist env var for interactive shells (docker exec)
echo "export DBUS_SESSION_BUS_ADDRESS=$DBUS_SESSION_BUS_ADDRESS" >> ~/.bashrc
echo "export DISPLAY=:99" >> ~/.bashrc

# Start supervisord
# We pass the env vars to supervisord so child processes inherit DBUS_SESSION_BUS_ADDRESS
exec /usr/bin/supervisord -c /app/environments/computer_rl_env/server/supervisord.conf