#!/bin/bash
# Install a launchd job that runs the stock check every 60 seconds.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
LABEL="com.ps5pro.stockalert"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
INTERVAL="${1:-60}"

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>$DIR/stock_alert.py</string>
  </array>
  <key>StartInterval</key><integer>$INTERVAL</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$DIR/stock_alert.log</string>
  <key>StandardErrorPath</key><string>$DIR/stock_alert.log</string>
</dict>
</plist>
PLIST

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed $LABEL (every ${INTERVAL}s). Logs: $DIR/stock_alert.log"
echo "Uninstall: launchctl bootout gui/\$(id -u)/$LABEL && rm $PLIST"
