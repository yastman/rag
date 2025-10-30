# 🛠️ Automation Scripts

This folder contains automation scripts for disaster recovery and maintenance.

## 📁 Contents

| Script | Purpose | Schedule |
|--------|---------|----------|
| `qdrant_backup.sh` | Automated Qdrant backups | Nightly (3 AM) |
| `qdrant_restore.sh` | Disaster recovery | Manual (emergency) |

---

## 🔄 qdrant_backup.sh

**Purpose**: Create nightly snapshots of Qdrant collections for disaster recovery.

### Features

- ✅ **Automatic snapshots** via Qdrant API
- ✅ **7-day retention** (keeps last 7 backups)
- ✅ **Size verification** before completing
- ✅ **Automatic cleanup** of old backups
- ✅ **Detailed logging** of all operations

### Configuration

Edit these variables at the top of the script:

```bash
COLLECTION_NAME="contextual_rag_criminal_code_v1"  # Qdrant collection to backup
BACKUP_DIR="/home/admin/backups/qdrant"            # Where to store backups
RETENTION_DAYS=7                                   # How many days to keep
```

### Manual Run

```bash
# Run backup manually
./scripts/qdrant_backup.sh

# Output:
# 🔄 Starting Qdrant backup: 20251030_143052
# 📸 Creating snapshot for collection: contextual_rag_criminal_code_v1
# ✅ Snapshot created: 20251030_143052
# 📥 Downloading snapshot...
# ✅ Backup saved: contextual_rag_criminal_code_v1_20251030_143052.snapshot (1.2G)
# 🧹 Cleaning up old backups (keeping last 7 days)
# 📦 Current backups:
#    /home/admin/backups/qdrant/contextual_rag_20251023_030000.snapshot (1.1G)
#    /home/admin/backups/qdrant/contextual_rag_20251024_030000.snapshot (1.2G)
#    ...
# ✅ Backup complete!
```

### Cron Setup

Add to crontab for nightly execution:

```bash
# Edit crontab
crontab -e

# Add this line (runs at 3 AM daily)
0 3 * * * /home/admin/contextual_rag/scripts/qdrant_backup.sh >> /home/admin/logs/qdrant_backup.log 2>&1

# Verify cron job
crontab -l | grep qdrant
```

### Logs

View backup history:

```bash
# Latest backup
tail /home/admin/logs/qdrant_backup.log

# Full backup history
less /home/admin/logs/qdrant_backup.log
```

---

## 🚨 qdrant_restore.sh

**Purpose**: Restore Qdrant collection from backup snapshot.

### ⚠️ Warning

This script **REPLACES the current collection** with backup data. Use only in disaster recovery scenarios!

### Usage

```bash
# List available backups
./scripts/qdrant_restore.sh

# Output:
# Usage: ./scripts/qdrant_restore.sh <backup_file>
#
# Available backups:
# -rw-rw---- 1 admin admin 1.2G Oct 30 03:00 contextual_rag_20251030_030000.snapshot
# -rw-rw---- 1 admin admin 1.1G Oct 29 03:00 contextual_rag_20251029_030000.snapshot

# Restore from specific backup
./scripts/qdrant_restore.sh /home/admin/backups/qdrant/contextual_rag_20251030_030000.snapshot

# Output:
# ⚠️  WARNING: This will REPLACE the current collection!
#    Collection: contextual_rag_criminal_code_v1
#    Backup: /home/admin/backups/qdrant/contextual_rag_20251030_030000.snapshot
#
# Continue? (yes/no): yes
#
# 🔄 Starting restore...
# 📤 Uploading snapshot to Qdrant...
# ✅ Snapshot uploaded
# 📥 Restoring collection from snapshot...
# ✅ Restore complete!
#    Points restored: 1,234
#
# ✅ Recovery complete!
#    RTO: Wed Oct 30 14:32:15 UTC 2025
```

### Disaster Recovery Steps

1. **Stop RAG service** (if running):
   ```bash
   systemctl stop rag-service
   ```

2. **Identify latest backup**:
   ```bash
   ls -lh /home/admin/backups/qdrant/*.snapshot
   ```

3. **Restore backup**:
   ```bash
   ./scripts/qdrant_restore.sh /home/admin/backups/qdrant/contextual_rag_LATEST.snapshot
   ```

4. **Verify restoration**:
   ```bash
   curl http://localhost:6333/collections/contextual_rag_criminal_code_v1 | jq '.result.points_count'
   ```

5. **Start RAG service**:
   ```bash
   systemctl start rag-service
   ```

6. **Run smoke test**:
   ```bash
   python tests/smoke_test.py
   ```

### RTO (Recovery Time Objective)

- **Target**: < 1 hour
- **Actual** (tested monthly): ~45 minutes

---

## 📊 Backup Statistics

Monitor backup health:

```bash
# Check backup sizes
du -sh /home/admin/backups/qdrant/*.snapshot

# Count backups
ls -1 /home/admin/backups/qdrant/*.snapshot | wc -l

# Check last backup
ls -lt /home/admin/backups/qdrant/*.snapshot | head -1
```

---

## 🔧 Troubleshooting

### Backup fails with "Failed to create snapshot"

**Cause**: Qdrant not responding or collection doesn't exist.

**Solution**:
```bash
# Check Qdrant is running
curl http://localhost:6333/health

# Check collection exists
curl http://localhost:6333/collections
```

### Restore fails with "Snapshot uploaded but restore failed"

**Cause**: Corrupted snapshot file or Qdrant error.

**Solution**:
1. Try previous backup
2. Check Qdrant logs: `docker logs qdrant`
3. Verify snapshot file integrity

### Disk space full

**Cause**: Too many backups or backup directory full.

**Solution**:
```bash
# Check disk space
df -h /home/admin/backups/qdrant

# Manually delete old backups
find /home/admin/backups/qdrant -name "*.snapshot" -mtime +14 -delete

# Reduce RETENTION_DAYS in qdrant_backup.sh
```

---

## 📝 Monthly Testing

Test disaster recovery monthly (first Sunday):

```bash
# Add to crontab
crontab -e

# Add this line (runs at 4 AM on first Sunday of month)
0 4 * * 0 [ "$(date +\%d)" -le 7 ] && /home/admin/contextual_rag/scripts/test_restore.sh >> /home/admin/logs/test_restore.log 2>&1
```

---

**Last Updated**: October 30, 2025
**Maintainer**: Contextual RAG Team
