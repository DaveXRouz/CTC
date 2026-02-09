#!/bin/bash
# Conductor — Install Script
set -e

CONDUCTOR_HOME="$HOME/.conductor"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_NAME="com.codexs.conductor.plist"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

echo "🎛️ Installing Conductor..."

# Create conductor home
mkdir -p "$CONDUCTOR_HOME"

# Check .env exists
if [ ! -f "$CONDUCTOR_HOME/.env" ]; then
    echo "⚠️  No .env found at $CONDUCTOR_HOME/.env"
    echo "   Copy .env.example and fill in your secrets:"
    echo "   cp $PROJECT_DIR/.env.example $CONDUCTOR_HOME/.env"
    exit 1
fi

# Create venv if needed
if [ ! -d "$PROJECT_DIR/.venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$PROJECT_DIR/.venv"
fi

# Install dependencies
echo "Installing dependencies..."
"$PROJECT_DIR/.venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt" -q

# Install launchd plist
mkdir -p "$LAUNCH_AGENTS"
cp "$PROJECT_DIR/scripts/$PLIST_NAME" "$LAUNCH_AGENTS/"
echo "Installed launchd plist to $LAUNCH_AGENTS/$PLIST_NAME"

# Load daemon
launchctl load "$LAUNCH_AGENTS/$PLIST_NAME" 2>/dev/null || true
echo "✅ Conductor installed and started!"
echo ""
echo "Check status: launchctl list | grep conductor"
echo "View logs:    tail -f $CONDUCTOR_HOME/conductor.log"
echo "Stop:         launchctl unload $LAUNCH_AGENTS/$PLIST_NAME"
