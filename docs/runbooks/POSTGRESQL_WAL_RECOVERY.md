# Runbook: PostgreSQL/WAL Corruption Recovery

Use this runbook when PostgreSQL shows signs of WAL (Write-Ahead Log) corruption.

The current Compose service uses `pgvector/pgvector:pg17` and the managed
`postgres_data` named volume (`dev_postgres_data` for the canonical local
project). Do not use old bind-path recovery commands or standalone PostgreSQL
recovery images that do not match the Compose service image for this stack.

## Symptoms

- `FATAL: WAL of base backup is corrupted`
- Database fails to start after restart
- Replication errors in logs
- Inconsistent data between queries

## Warning

**This runbook involves potentially destructive operations. Ensure you have a current backup before proceeding.**

All destructive steps below are marked as last resort. Prefer named-volume
backup/export and Compose-native commands before modifying the live data volume.

## Diagnosis

### 1. Check PostgreSQL Logs

```bash
docker compose logs postgres --tail=100 | grep -i "wal\|corrupt\|error"
```

### 2. Verify Named Volume

```bash
# Confirm the Compose-managed volume exists.
docker volume inspect dev_postgres_data

# Read-only listing through a short-lived helper container.
docker run --rm -v dev_postgres_data:/pgdata:ro alpine sh -lc 'ls -la /pgdata | head'
```

### 3. Check Disk Space

```bash
df -h
# WAL issues can occur with full disk
```

## Remediation

### Option 0: Export the Named Volume Before Remediation

Before any recovery command, create an offline copy of the named volume:

```bash
mkdir -p backups
docker compose stop postgres
docker run --rm \
  -v dev_postgres_data:/pgdata:ro \
  -v "$PWD/backups":/backup \
  alpine sh -lc 'tar czf /backup/postgres_data-$(date -u +%Y%m%dT%H%M%SZ).tgz -C /pgdata .'
```

Keep this archive until application-level checks confirm the recovered database
is consistent.

### Option 1: `pg_resetwal` (High Risk)

If PostgreSQL won't start due to WAL corruption:

1. Stop PostgreSQL:
   ```bash
   docker compose stop postgres
   ```

2. Run `pg_resetwal` with the same Compose service image and named volume:
   ```bash
   docker compose run --rm --no-deps --entrypoint pg_resetwal postgres \
     -f /var/lib/postgresql/data
   ```

3. Start PostgreSQL:
   ```bash
   docker compose start postgres
   ```

4. Immediately run integrity checks and take a fresh logical backup if the
   database starts. `pg_resetwal` can make committed transactions disappear and
   should only be used when restoring from backup is not viable.

### Option 2: Restore From Backup / PITR

If you have a recent base backup:

1. Identify last good backup
2. Stop PostgreSQL with `docker compose stop postgres`
3. Restore into a new or emptied `postgres_data` named volume according to the
   backup tool's PostgreSQL 17 recovery procedure
4. Start PostgreSQL in recovery mode and verify application databases before
   resuming dependent services

### Option 3: Reinitialize (Last Resort)

If other methods fail and data loss is acceptable, remove only the Compose
managed named volume after exporting it.

> **RED FLAG:** This deletes the local PostgreSQL data volume for the `dev`
> Compose project. Do not run it against VPS/production unless an incident
> commander has explicitly approved data loss or a restore path is ready.

1. Stop PostgreSQL:
   ```bash
   docker compose stop postgres
   ```

2. Export the current volume if you have not already done so:
   ```bash
   mkdir -p backups
   docker run --rm -v dev_postgres_data:/pgdata:ro -v "$PWD/backups":/backup \
     alpine sh -lc 'tar czf /backup/postgres_data-before-reinit-$(date -u +%Y%m%dT%H%M%SZ).tgz -C /pgdata .'
   ```

3. Remove the named volume:
   ```bash
   docker volume rm dev_postgres_data
   ```

4. Start PostgreSQL (will reinitialize):
   ```bash
   docker compose up -d postgres
   ```

5. Re-run any necessary setup scripts or restore logical dumps

## Prevention

- Regular base backups with PostgreSQL 17-compatible tooling
- Monitor disk space (WAL needs room)
- Set `max_wal_size` appropriately
- Regular `pg_checksums` validation
