#!/bin/bash
# Qdrant restore script

set -e

COLLECTION_NAME="contextual_rag_criminal_code_v1"
BACKUP_FILE="$1"

if [ -z "$BACKUP_FILE" ]; then
  echo "Usage: $0 <backup_file>"
  echo ""
  echo "Available backups:"
  ls -lh /home/admin/backups/qdrant/*.snapshot 2>/dev/null
  exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
  echo "❌ Backup file not found: $BACKUP_FILE"
  exit 1
fi

echo "⚠️  WARNING: This will REPLACE the current collection!"
echo "   Collection: $COLLECTION_NAME"
echo "   Backup: $BACKUP_FILE"
echo ""
read -p "Continue? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
  echo "Aborted"
  exit 0
fi

echo ""
echo "🔄 Starting restore..."

# Upload snapshot
echo "📤 Uploading snapshot to Qdrant..."

SNAPSHOT_NAME=$(basename "$BACKUP_FILE")

curl -X POST \
  "http://localhost:6333/collections/$COLLECTION_NAME/snapshots/upload" \
  -F "snapshot=@$BACKUP_FILE" \
  --fail

if [ $? -eq 0 ]; then
  echo "✅ Snapshot uploaded"
else
  echo "❌ Upload failed"
  exit 1
fi

# Restore from snapshot
echo "📥 Restoring collection from snapshot..."

curl -X PUT \
  "http://localhost:6333/collections/$COLLECTION_NAME/snapshots/$SNAPSHOT_NAME/recover" \
  -H "Content-Type: application/json" \
  --fail

if [ $? -eq 0 ]; then
  echo "✅ Restore complete!"

  # Verify collection
  POINTS=$(curl -s "http://localhost:6333/collections/$COLLECTION_NAME" | jq '.result.points_count')
  echo "   Points restored: $POINTS"
else
  echo "❌ Restore failed"
  exit 1
fi

echo ""
echo "✅ Recovery complete!"
echo "   RTO: $(date)"
