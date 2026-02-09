#!/bin/bash
# Conductor — Uninstall Script
set -e

PLIST_NAME="com.codexs.conductor.plist"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

echo "🎛️ Uninstalling Conductor..."

# Unload daemon
if [ -f "$LAUNCH_AGENTS/$PLIST_NAME" ]; then
    launchctl unload "$LAUNCH_AGENTS/$PLIST_NAME" 2>/dev/null || true
    rm "$LAUNCH_AGENTS/$PLIST_NAME"
    echo "Removed launchd plist"
fi

# Kill any running conductor tmux sessions
tmux list-sessions 2>/dev/null | grep "^conductor-" | cut -d: -f1 | while read session; do
    tmux kill-session -t "$session" 2>/dev/null || true
    echo "Killed tmux session: $session"
done

echo "✅ Conductor uninstalled."
echo ""
echo "Note: ~/.conductor/ directory preserved (contains your data and config)."
echo "To remove completely: rm -rf ~/.conductor/"
