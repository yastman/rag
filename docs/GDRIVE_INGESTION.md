# Google Drive Ingestion Pipeline

Canonical runtime path for knowledge-base documents:

```text
Google Drive
  -> rclone sync (cron / manual)
  -> GDRIVE_SYNC_DIR on host
  -> /data/drive-sync in ingestion container
  -> CocoIndex LocalFile source
  -> Docling parse + chunk
  -> BGE-M3 embeddings
  -> Qdrant collection gdrive_documents_bge
```

The old `gdrive_documents_scalar` and `gdrive_documents_binary` collections are no longer the active runtime path.

## Runtime Contract

- Google Drive is copied locally first through `rclone`.
- Unified ingestion reads only from the local sync directory.
- The ingestion container bind-mounts `GDRIVE_SYNC_DIR` into `/data/drive-sync`.
- Compose now uses fail-fast bind mounting. If the host path is missing, startup fails instead of creating an empty directory.
- The canonical target collection is `gdrive_documents_bge`.

## Quick Start

### 1. Install rclone

```bash
curl https://rclone.org/install.sh | sudo bash
```

Or:

```bash
make rclone-install
```

### 2. Prepare Google Drive access

1. Create a Google Cloud service account with Drive read-only access.
2. Download the JSON key to a secure host path such as `/opt/credentials/gdrive-service-account.json`.
3. Share the target Drive folder with the service account email.
4. Create an rclone config file on the host and point it at that service account key.

Example rclone config:

```ini
[gdrive]
type = drive
scope = drive.readonly
service_account_file = /opt/credentials/gdrive-service-account.json
root_folder_id = YOUR_FOLDER_ID_HERE
```

### 3. Configure environment

Set these variables in `.env` or the host environment:

| Variable | Example | Description |
|----------|---------|-------------|
| `GDRIVE_SYNC_DIR` | `/opt/rag-fresh/drive-sync` | Host path used for the local Google Drive mirror |
| `RCLONE_CONFIG_FILE` | `/opt/credentials/rclone.conf` | Host path to the rclone config file |
| `RCLONE_REMOTE` | `gdrive:RAG` | Remote/folder to sync |
| `GDRIVE_COLLECTION_NAME` | `gdrive_documents_bge` | Canonical Qdrant collection |

Validate the remote before installing cron:

```bash
rclone ls "$RCLONE_REMOTE" --config "$RCLONE_CONFIG_FILE"
```

### 4. Install sync scripts and cron

```bash
make sync-drive-install
```

This installs:
- `/opt/scripts/sync-drive.sh`
- `/opt/scripts/gdrive-manifest.sh`
- `/etc/cron.d/rclone-sync`
- `/etc/rag-fresh/rclone-sync.env`

### 5. Seed the local mirror

```bash
make sync-drive-run
make sync-drive-status
```

Do not start ingestion until `GDRIVE_SYNC_DIR` contains the expected files.

### 6. Bootstrap and run ingestion

```bash
make ingest-unified-preflight
make ingest-unified-bootstrap
make ingest-unified
```

For continuous mode:

```bash
make ingest-unified-watch
```

## Supported File Types

The unified pipeline accepts the document formats configured in `src/ingestion/unified/config.py`.
Typical knowledge-base inputs include `.pdf`, `.docx`, `.xlsx`, `.pptx`, `.md`, and `.txt`.

Google Workspace files are exported by `rclone` into Office-compatible formats:

| Google Type | Export Format |
|-------------|---------------|
| Google Docs | `.docx` |
| Google Sheets | `.xlsx` |
| Google Slides | `.pptx` |

## Identity And Replace Semantics

- `gdrive-manifest.sh` writes `.gdrive_manifest.json` into `GDRIVE_SYNC_DIR`.
- The unified pipeline builds stable `file_id` values from file content and manifest metadata.
- When a file changes, ingestion replaces all chunks for that `file_id`.
- When a file disappears from the sync directory, ingestion deletes the corresponding Qdrant points.

## Operator Commands

| Target | Description |
|--------|-------------|
| `make sync-drive-install` | Install sync scripts and cron |
| `make sync-drive-run` | Run a sync cycle immediately |
| `make sync-drive-status` | Inspect local mirror and recent logs |
| `make ingest-unified-preflight` | Validate env, sync dir, and services |
| `make ingest-unified-bootstrap` | Create or validate `gdrive_documents_bge` schema |
| `make ingest-unified` | Run one ingestion pass |
| `make ingest-unified-watch` | Run continuous ingestion |
| `make ingest-unified-status` | Show unified ingestion state |
| `make ingest-unified-logs` | Tail ingestion container logs |

Legacy `make ingest-gdrive-*` targets still exist only as compatibility aliases and now forward to the unified commands above.

## Troubleshooting

| Issue | Check |
|-------|-------|
| Qdrant collection exists but has `0 points` | Verify `GDRIVE_SYNC_DIR` is populated before debugging Qdrant |
| `preflight` fails on sync dir | Confirm `GDRIVE_SYNC_DIR` exists and is a directory |
| Ingestion says `No input data` | Check the host path, then the container mount at `/data/drive-sync` |
| Sync not running | Check `/etc/cron.d/rclone-sync` and `/var/log/rclone-sync.log` |
| `RCLONE_CONFIG_FILE` not found | Fix the host path in `.env` or `/etc/rag-fresh/rclone-sync.env` |
| Qdrant looks empty from VPS host | Query from the Docker network if port `6333` is not published on the host |

For the full VPS recovery sequence, see `docs/runbooks/vps-gdrive-ingestion-recovery.md`.
