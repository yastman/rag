***REMOVED*** 🛠️ Automation Scripts

This folder contains automation scripts for disaster recovery and maintenance.

***REMOVED******REMOVED*** 📁 Contents

| Script | Purpose | Schedule |
|--------|---------|----------|
| `qdrant_backup.sh` | Automated Qdrant backups | Nightly (3 AM) |
| `qdrant_restore.sh` | Disaster recovery | Manual (emergency) |

---

***REMOVED******REMOVED*** 🔄 qdrant_backup.sh

**Purpose**: Create nightly snapshots of Qdrant collections for disaster recovery.

***REMOVED******REMOVED******REMOVED*** Features

- ✅ **Automatic snapshots** via Qdrant API
- ✅ **7-day retention** (keeps last 7 backups)
- ✅ **Size verification** before completing
- ✅ **Automatic cleanup** of old backups
- ✅ **Detailed logging** of all operations

***REMOVED******REMOVED******REMOVED*** Configuration

Edit these variables at the top of the script:

```bash
COLLECTION_NAME="contextual_rag_criminal_code_v1"  ***REMOVED*** Qdrant collection to backup
BACKUP_DIR="/srv/backups/qdrant"            ***REMOVED*** Where to store backups
RETENTION_DAYS=7                                   ***REMOVED*** How many days to keep
```

***REMOVED******REMOVED******REMOVED*** Manual Run

```bash
***REMOVED*** Run backup manually
./scripts/qdrant_backup.sh

***REMOVED*** Output:
***REMOVED*** 🔄 Starting Qdrant backup: 20251030_143052
***REMOVED*** 📸 Creating snapshot for collection: contextual_rag_criminal_code_v1
***REMOVED*** ✅ Snapshot created: 20251030_143052
***REMOVED*** 📥 Downloading snapshot...
***REMOVED*** ✅ Backup saved: contextual_rag_criminal_code_v1_20251030_143052.snapshot (1.2G)
***REMOVED*** 🧹 Cleaning up old backups (keeping last 7 days)
***REMOVED*** 📦 Current backups:
***REMOVED***    /srv/backups/qdrant/contextual_rag_20251023_030000.snapshot (1.1G)
***REMOVED***    /srv/backups/qdrant/contextual_rag_20251024_030000.snapshot (1.2G)
***REMOVED***    ...
***REMOVED*** ✅ Backup complete!
```

***REMOVED******REMOVED******REMOVED*** Cron Setup

Add to crontab for nightly execution:

```bash
***REMOVED*** Edit crontab
crontab -e

***REMOVED*** Add this line (runs at 3 AM daily)
0 3 * * * /srv/app/scripts/qdrant_backup.sh >> /srv/logs/qdrant_backup.log 2>&1

***REMOVED*** Verify cron job
crontab -l | grep qdrant
```

***REMOVED******REMOVED******REMOVED*** Logs

View backup history:

```bash
***REMOVED*** Latest backup
tail /srv/logs/qdrant_backup.log

***REMOVED*** Full backup history
less /srv/logs/qdrant_backup.log
```

---

***REMOVED******REMOVED*** 🚨 qdrant_restore.sh

**Purpose**: Restore Qdrant collection from backup snapshot.

***REMOVED******REMOVED******REMOVED*** ⚠️ Warning

This script **REPLACES the current collection** with backup data. Use only in disaster recovery scenarios!

***REMOVED******REMOVED******REMOVED*** Usage

```bash
***REMOVED*** List available backups
./scripts/qdrant_restore.sh

***REMOVED*** Output:
***REMOVED*** Usage: ./scripts/qdrant_restore.sh <backup_file>
***REMOVED***
***REMOVED*** Available backups:
***REMOVED*** -rw-rw---- 1 admin admin 1.2G Oct 30 03:00 contextual_rag_20251030_030000.snapshot
***REMOVED*** -rw-rw---- 1 admin admin 1.1G Oct 29 03:00 contextual_rag_20251029_030000.snapshot

***REMOVED*** Restore from specific backup
./scripts/qdrant_restore.sh /srv/backups/qdrant/contextual_rag_20251030_030000.snapshot

***REMOVED*** Output:
***REMOVED*** ⚠️  WARNING: This will REPLACE the current collection!
***REMOVED***    Collection: contextual_rag_criminal_code_v1
***REMOVED***    Backup: /srv/backups/qdrant/contextual_rag_20251030_030000.snapshot
***REMOVED***
***REMOVED*** Continue? (yes/no): yes
***REMOVED***
***REMOVED*** 🔄 Starting restore...
***REMOVED*** 📤 Uploading snapshot to Qdrant...
***REMOVED*** ✅ Snapshot uploaded
***REMOVED*** 📥 Restoring collection from snapshot...
***REMOVED*** ✅ Restore complete!
***REMOVED***    Points restored: 1,234
***REMOVED***
***REMOVED*** ✅ Recovery complete!
***REMOVED***    RTO: Wed Oct 30 14:32:15 UTC 2025
```

***REMOVED******REMOVED******REMOVED*** Disaster Recovery Steps

1. **Stop RAG service** (if running):
   ```bash
   systemctl stop rag-service
   ```

2. **Identify latest backup**:
   ```bash
   ls -lh /srv/backups/qdrant/*.snapshot
   ```

3. **Restore backup**:
   ```bash
   ./scripts/qdrant_restore.sh /srv/backups/qdrant/contextual_rag_LATEST.snapshot
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

***REMOVED******REMOVED******REMOVED*** RTO (Recovery Time Objective)

- **Target**: < 1 hour
- **Actual** (tested monthly): ~45 minutes

---

***REMOVED******REMOVED*** 📊 Backup Statistics

Monitor backup health:

```bash
***REMOVED*** Check backup sizes
du -sh /srv/backups/qdrant/*.snapshot

***REMOVED*** Count backups
ls -1 /srv/backups/qdrant/*.snapshot | wc -l

***REMOVED*** Check last backup
ls -lt /srv/backups/qdrant/*.snapshot | head -1
```

---

***REMOVED******REMOVED*** 🔧 Troubleshooting

***REMOVED******REMOVED******REMOVED*** Backup fails with "Failed to create snapshot"

**Cause**: Qdrant not responding or collection doesn't exist.

**Solution**:
```bash
***REMOVED*** Check Qdrant is running
curl http://localhost:6333/health

***REMOVED*** Check collection exists
curl http://localhost:6333/collections
```

***REMOVED******REMOVED******REMOVED*** Restore fails with "Snapshot uploaded but restore failed"

**Cause**: Corrupted snapshot file or Qdrant error.

**Solution**:
1. Try previous backup
2. Check Qdrant logs: `docker logs qdrant`
3. Verify snapshot file integrity

***REMOVED******REMOVED******REMOVED*** Disk space full

**Cause**: Too many backups or backup directory full.

**Solution**:
```bash
***REMOVED*** Check disk space
df -h /srv/backups/qdrant

***REMOVED*** Manually delete old backups
find /srv/backups/qdrant -name "*.snapshot" -mtime +14 -delete

***REMOVED*** Reduce RETENTION_DAYS in qdrant_backup.sh
```

---

***REMOVED******REMOVED*** 📝 Monthly Testing

Test disaster recovery monthly (first Sunday):

```bash
***REMOVED*** Add to crontab
crontab -e

***REMOVED*** Add this line (runs at 4 AM on first Sunday of month)
0 4 * * 0 [ "$(date +\%d)" -le 7 ] && /srv/app/scripts/test_restore.sh >> /srv/logs/test_restore.log 2>&1
```

---

**Last Updated**: October 30, 2025
**Maintainer**: Contextual RAG Team
