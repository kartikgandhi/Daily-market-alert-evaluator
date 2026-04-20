#!/bin/zsh

set -eu

PLIST_PATH="${HOME}/Library/LaunchAgents/com.kartik.index-whatsapp-alerts.plist"

launchctl bootout "gui/$(id -u)" "${PLIST_PATH}" >/dev/null 2>&1 || true
rm -f "${PLIST_PATH}"

echo "Removed LaunchAgent ${PLIST_PATH}"
