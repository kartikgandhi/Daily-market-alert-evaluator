#!/bin/zsh

set -eu

PROJECT_DIR="/Users/kartik/Developer/Codex/2026-04-20-build-a-program-which-send-me"
PYTHON_BIN="/usr/bin/python3"
JOB_CMD="cd ${PROJECT_DIR} && ${PYTHON_BIN} index_whatsapp_alert.py >> alert.log 2>&1"

TMP_FILE="$(mktemp)"
trap 'rm -f "$TMP_FILE"' EXIT

crontab -l 2>/dev/null | grep -v "index_whatsapp_alert.py" > "$TMP_FILE" || true

{
  echo "CRON_TZ=Asia/Kolkata"
  echo "0 11 * * 1-5 ${JOB_CMD}"
  echo "0 14 * * 1-5 ${JOB_CMD}"
  echo "35 15 * * 1-5 ${JOB_CMD}"
} >> "$TMP_FILE"

crontab "$TMP_FILE"
echo "Installed cron schedule for 11:00, 14:00, and 15:35 Asia/Kolkata on weekdays."
