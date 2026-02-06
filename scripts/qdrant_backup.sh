#!/bin/bash
# Qdrant backup script - Run nightly via cron

set -e

COLLECTION_NAME="${QDRANT_COLLECTION:-gdrive_documents_bge}"
BACKUP_DIR="/srv/backups/qdrant"
RETENTION_DAYS=7
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "🔄 Starting Qdrant backup: $TIMESTAMP"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Create snapshot via Qdrant API
echo "📸 Creating snapshot for collection: $COLLECTION_NAME"

QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"

SNAPSHOT_NAME=$(curl -s -X POST \
  "$QDRANT_URL/collections/$COLLECTION_NAME/snapshots" \
  -H "Content-Type: application/json" \
  | jq -r '.result.name')

if [ -z "$SNAPSHOT_NAME" ]; then
  echo "❌ Failed to create snapshot"
  exit 1
fi

echo "✅ Snapshot created: $SNAPSHOT_NAME"

# Download snapshot
echo "📥 Downloading snapshot..."

curl -o "$BACKUP_DIR/${COLLECTION_NAME}_${TIMESTAMP}.snapshot" \
  "$QDRANT_URL/collections/$COLLECTION_NAME/snapshots/$SNAPSHOT_NAME"

# Verify download
if [ -f "$BACKUP_DIR/${COLLECTION_NAME}_${TIMESTAMP}.snapshot" ]; then
  SIZE=$(du -h "$BACKUP_DIR/${COLLECTION_NAME}_${TIMESTAMP}.snapshot" | cut -f1)
  echo "✅ Backup saved: ${COLLECTION_NAME}_${TIMESTAMP}.snapshot ($SIZE)"
else
  echo "❌ Backup failed"
  exit 1
fi

# Delete remote snapshot (keep local copy only)
curl -s -X DELETE \
  "$QDRANT_URL/collections/$COLLECTION_NAME/snapshots/$SNAPSHOT_NAME"

# Cleanup old backups (keep last 7 days)
echo "🧹 Cleaning up old backups (keeping last $RETENTION_DAYS days)"

find "$BACKUP_DIR" -name "*.snapshot" -type f -mtime +$RETENTION_DAYS -delete

# List remaining backups
echo ""
echo "📦 Current backups:"
ls -lh "$BACKUP_DIR"/*.snapshot 2>/dev/null | awk '{print "   "$9" ("$5")"}'

echo ""
echo "✅ Backup complete!"
