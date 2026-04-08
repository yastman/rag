# VPS Google Drive Ingestion Recovery

Use this runbook when `gdrive_documents_bge` exists but stays empty, or when ingestion reports `No input data`.

## Expected Contract

The production path is:

```text
Google Drive -> rclone sync on host -> GDRIVE_SYNC_DIR -> /data/drive-sync in container -> unified ingestion -> gdrive_documents_bge
```

If the host sync directory is missing or empty, Qdrant may still have a valid collection with `0 points`.

## 1. Check Host Environment

Confirm the configured sync path and rclone config:

```bash
grep -E '^(GDRIVE_SYNC_DIR|RCLONE_CONFIG_FILE|RCLONE_REMOTE)=' .env
sudo cat /etc/rag-fresh/rclone-sync.env
```

The paths in `.env`, cron env, and Compose must point to the same host files.

## 2. Verify The Host Sync Directory

```bash
ls -la "$GDRIVE_SYNC_DIR"
find "$GDRIVE_SYNC_DIR" -maxdepth 2 -type f | head -50
```

Failure modes:
- Path missing: recreate the intended directory and fix the mount contract or deployment env.
- Path exists but is empty: rclone is not syncing data.
- Path contains only manifest/log files: remote or allowlist is wrong.

## 3. Verify rclone Directly

```bash
rclone ls "$RCLONE_REMOTE" --config "$RCLONE_CONFIG_FILE"
make sync-drive-run
tail -100 /var/log/rclone-sync.log
tail -100 /var/log/rclone-manifest.log
```

If `rclone ls` fails, fix credentials, folder sharing, or `root_folder_id` before touching ingestion.

## 4. Verify The Container Mount

```bash
docker compose exec ingestion sh -lc 'ls -la /data/drive-sync && find /data/drive-sync -maxdepth 2 -type f | head -50'
```

Interpretation:
- Host path has files, container path empty: bind mount contract is broken.
- Both host and container are empty: sync is the root cause.

## 5. Verify Preflight And Bootstrap

```bash
make ingest-unified-preflight
make ingest-unified-bootstrap
make ingest-unified-status
```

`preflight` should now fail early if `GDRIVE_SYNC_DIR` is missing or invalid.

## 6. Verify Qdrant From The Correct Network

If `localhost:6333` on the VPS host is not published, query Qdrant from Docker instead:

```bash
docker compose exec qdrant curl -fsS http://localhost:6333/collections
docker compose exec qdrant curl -fsS http://localhost:6333/collections/gdrive_documents_bge
```

Do not treat a missing host port as proof that the collection is absent.

## 7. Re-run Ingestion

Once the sync directory is populated:

```bash
make ingest-unified
make ingest-unified-status
make ingest-unified-logs
```

Then verify point counts:

```bash
docker compose exec qdrant curl -fsS http://localhost:6333/collections/gdrive_documents_bge
```

## Fast Diagnosis Matrix

| Symptom | Likely Cause | First Check |
|---------|--------------|-------------|
| `No input data` in ingestion logs | Empty or missing host sync dir | `ls -la "$GDRIVE_SYNC_DIR"` |
| Qdrant collection exists but `0 points` | Sync never populated local mirror | `make sync-drive-status` |
| Host `curl localhost:6333` fails | Port not published on host | `docker compose exec qdrant curl ...` |
| Compose starts ingestion with empty mount | Old short bind syntax silently created host path | Rendered `docker compose config` |
| Cron runs but no files appear | Broken `RCLONE_CONFIG_FILE` or remote | `rclone ls "$RCLONE_REMOTE" --config "$RCLONE_CONFIG_FILE"` |
