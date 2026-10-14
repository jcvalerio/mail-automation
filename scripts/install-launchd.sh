#!/usr/bin/env bash
# Install (or remove) the launchd agent that runs scripts/morning.sh daily.
#
#   scripts/install-launchd.sh 2026-10-11          # first --apply date, 07:00
#   scripts/install-launchd.sh 2026-10-11 6 30     # at 06:30
#   scripts/install-launchd.sh --uninstall
#
# If the Mac is asleep at that time, launchd runs the job once on wake.

set -euo pipefail

LABEL="dev.mail-automation.morning"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DOMAIN="gui/$(id -u)"

if [ "${1:-}" = "--uninstall" ]; then
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "Removed $LABEL"
  exit 0
fi

FIRST_APPLY="${1:?usage: install-launchd.sh YYYY-MM-DD [hour] [minute] | --uninstall}"
HOUR="${2:-7}"
MINUTE="${3:-0}"
date -j -f %Y-%m-%d "$FIRST_APPLY" +%s >/dev/null || { echo "Bad date: $FIRST_APPLY"; exit 1; }

mkdir -p "$(dirname "$PLIST")" "$REPO/data/logs"
cat >"$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$REPO/scripts/morning.sh</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>TRIAGE_FIRST_APPLY</key><string>$FIRST_APPLY</string>
  </dict>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>$HOUR</integer>
    <key>Minute</key><integer>$MINUTE</integer>
  </dict>
  <key>StandardOutPath</key><string>$REPO/data/logs/launchd.log</string>
  <key>StandardErrorPath</key><string>$REPO/data/logs/launchd.log</string>
  <key>ProcessType</key><string>Background</string>
</dict>
</plist>
EOF
plutil -lint "$PLIST" >/dev/null

launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST"
printf 'Installed %s: daily at %02d:%02d\n' "$LABEL" "$HOUR" "$MINUTE"
echo "Run now:  launchctl kickstart $DOMAIN/$LABEL"
