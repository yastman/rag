***REMOVED***!/bin/bash
***REMOVED*** Generate Drive manifest for stable file IDs (rename/move safe)
***REMOVED*** Maps local paths to Google Drive file IDs
***REMOVED***
***REMOVED*** Install: sudo cp docker/rclone/gdrive-manifest.sh /opt/scripts/
***REMOVED***          sudo chmod +x /opt/scripts/gdrive-manifest.sh

set -euo pipefail

MANIFEST_DIR="/data/drive-sync"
TMP_FILE="${MANIFEST_DIR}/.gdrive_manifest.json.tmp"
OUT_FILE="${MANIFEST_DIR}/.gdrive_manifest.json"
LOG_FILE="/var/log/rclone-manifest.log"
RCLONE_CONFIG="/repo/docker/rclone/rclone.conf"

echo "$(date): Generating Drive manifest" >> "$LOG_FILE"

***REMOVED*** root_folder_id in rclone.conf makes gdrive: scoped to that folder.
***REMOVED*** lsjson returns: Path, Name, Size, MimeType, ModTime, ID, etc.
rclone lsjson gdrive: \
  --config "$RCLONE_CONFIG" \
  --recursive \
  --files-only \
  --metadata \
  > "$TMP_FILE"

mv "$TMP_FILE" "$OUT_FILE"
echo "$(date): Manifest updated: $OUT_FILE ($(wc -l < "$OUT_FILE") entries)" >> "$LOG_FILE"
