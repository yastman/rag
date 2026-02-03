#!/bin/bash
# Google Drive → Local sync for RAG ingestion
# Runs via cron every 5 minutes
#
# Install: sudo cp docker/rclone/sync-drive.sh /opt/scripts/
#          sudo chmod +x /opt/scripts/sync-drive.sh

set -euo pipefail

SYNC_DIR="/data/drive-sync"
LOG_FILE="/var/log/rclone-sync.log"
LOCK_FILE="/tmp/rclone-sync.lock"
RCLONE_CONFIG="/repo/docker/rclone/rclone.conf"

# Prevent concurrent runs
exec 200>"$LOCK_FILE"
flock -n 200 || { echo "$(date): Sync already running" >> "$LOG_FILE"; exit 0; }

echo "$(date): Starting Drive sync" >> "$LOG_FILE"

rclone sync gdrive: "$SYNC_DIR" \
  --config "$RCLONE_CONFIG" \
  --drive-export-formats docx,xlsx,pptx \
  --fast-list \
  --delete-after \
  --transfers 4 \
  --checkers 8 \
  --log-file "$LOG_FILE" \
  --log-level INFO \
  --include "*.pdf" \
  --include "*.docx" \
  --include "*.pptx" \
  --include "*.xlsx" \
  --include "*.md" \
  --include "*.txt" \
  --exclude "*" \
  --exclude "*.tmp" \
  --exclude "~$*" \
  --exclude ".~*"

echo "$(date): Sync completed" >> "$LOG_FILE"

# Generate manifest for stable file IDs (optional)
if [ -x /opt/scripts/gdrive-manifest.sh ]; then
  /opt/scripts/gdrive-manifest.sh
fi
