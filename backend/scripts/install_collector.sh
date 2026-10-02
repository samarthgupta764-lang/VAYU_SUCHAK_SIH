#!/usr/bin/env bash
#
# Install the VAYU-SUCHAK daily fare collector as a macOS launchd agent.
# Run once:   bash scripts/install_collector.sh
# No sudo needed — it only writes to your own ~/Library/LaunchAgents.
#
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_DIR="$(cd "$BACKEND_DIR/.." && pwd)"
VENV_PYTHON="$BACKEND_DIR/.venv/bin/python"
SRC="$REPO_DIR/deploy/com.vayu-suchak.collector.plist"
DEST="$HOME/Library/LaunchAgents/com.vayu-suchak.collector.plist"
LABEL="com.vayu-suchak.collector"

[ -x "$VENV_PYTHON" ] || { echo "!! venv python not found at $VENV_PYTHON"; exit 1; }
[ -f "$SRC" ]         || { echo "!! plist template not found at $SRC"; exit 1; }

mkdir -p "$HOME/Library/LaunchAgents" "$BACKEND_DIR/data"

# fill the machine-specific paths into the template
sed -e "s|__VENV_PYTHON__|$VENV_PYTHON|g" \
    -e "s|__BACKEND_DIR__|$BACKEND_DIR|g" \
    "$SRC" > "$DEST"

# reload if already installed
launchctl unload "$DEST" 2>/dev/null || true
launchctl load "$DEST"

echo "installed -> $DEST"
echo "runs daily at 06:00 (or next wake). log: $BACKEND_DIR/data/collector.log"
echo
echo "  run one collection now :  launchctl start $LABEL"
echo "  check it is loaded     :  launchctl list | grep vayu"
echo "  see collection progress:  $VENV_PYTHON -m scripts.collector_status"
echo "  remove                 :  launchctl unload $DEST && rm $DEST"
