***REMOVED*** Runbook: PostgreSQL/WAL Corruption Recovery

Use this runbook when PostgreSQL shows signs of WAL (Write-Ahead Log) corruption.

***REMOVED******REMOVED*** Symptoms

- `FATAL: WAL of base backup is corrupted`
- Database fails to start after restart
- Replication errors in logs
- Inconsistent data between queries

***REMOVED******REMOVED*** Warning

**This runbook involves potentially destructive operations. Ensure you have a current backup before proceeding.**

***REMOVED******REMOVED*** Diagnosis

***REMOVED******REMOVED******REMOVED*** 1. Check PostgreSQL Logs

```bash
docker compose logs postgres --tail=100 | grep -i "wal\|corrupt\|error"
```

***REMOVED******REMOVED******REMOVED*** 2. Verify Data Directory

```bash
***REMOVED*** Check data directory exists and is accessible
ls -la ${DATABASE_DIR:-./data}/postgres/
```

***REMOVED******REMOVED******REMOVED*** 3. Check Disk Space

```bash
df -h
***REMOVED*** WAL issues can occur with full disk
```

***REMOVED******REMOVED*** Remediation

***REMOVED******REMOVED******REMOVED*** Option 1: pg_resetwal (Least Destructive)

If PostgreSQL won't start due to WAL corruption:

1. Stop PostgreSQL:
   ```bash
   docker compose stop postgres
   ```

2. Run pg_resetwal:
   ```bash
   docker run --rm -v ${PWD}/data/postgres:/var/lib/postgresql/data postgres:16 \
     pg_resetwal -f /var/lib/postgresql/data
   ```

3. Start PostgreSQL:
   ```bash
   docker compose start postgres
   ```

***REMOVED******REMOVED******REMOVED*** Option 2: Point-in-Time Recovery (PITR)

If you have a recent base backup:

1. Identify last good backup
2. Configure `recovery.conf`:
   ```bash
   restore_command = 'cp /path/to/archive/%f %p'
   recovery_target_time = 'YYYY-MM-DD HH:MI:SS UTC'
   ```

3. Start PostgreSQL in recovery mode

***REMOVED******REMOVED******REMOVED*** Option 3: Reinitialize (Last Resort)

If other methods fail and data loss is acceptable:

1. Stop PostgreSQL:
   ```bash
   docker compose stop postgres
   ```

2. Clear data directory:
   ```bash
   rm -rf ${DATABASE_DIR:-./data}/postgres/*
   ```

3. Start PostgreSQL (will reinitialize):
   ```bash
   docker compose start postgres
   ```

4. Re-run any necessary setup scripts

***REMOVED******REMOVED*** Prevention

- Regular base backups: `pg_basebackup`
- Monitor disk space (WAL needs room)
- Set `max_wal_size` appropriately
- Regular `pg_checksums` validation
