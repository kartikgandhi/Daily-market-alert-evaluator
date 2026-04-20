#!/bin/zsh

set -eu

PROJECT_DIR="/Users/kartik/Developer/Codex/2026-04-20-build-a-program-which-send-me"
TEMPLATE_PATH="${PROJECT_DIR}/index-whatsapp-alerts.plist.template"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
PLIST_PATH="${LAUNCH_AGENTS_DIR}/com.kartik.index-whatsapp-alerts.plist"
LABEL="com.kartik.index-whatsapp-alerts"

mkdir -p "${LAUNCH_AGENTS_DIR}"
mkdir -p "${PROJECT_DIR}/logs"

sed "s|__PROJECT_DIR__|${PROJECT_DIR}|g" "${TEMPLATE_PATH}" > "${PLIST_PATH}"

launchctl bootout "gui/$(id -u)" "${PLIST_PATH}" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "${PLIST_PATH}"
launchctl enable "gui/$(id -u)/${LABEL}"

echo "Installed LaunchAgent at ${PLIST_PATH}"
echo "Scheduled for weekdays at 11:00, 14:00, and 15:35 Asia/Kolkata."
