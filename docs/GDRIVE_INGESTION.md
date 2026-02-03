# Google Drive Ingestion Pipeline

Always-on document ingestion from Google Drive to Qdrant for hybrid search.

## Architecture

```
Google Drive
    │
    ▼ (rclone sync, cron 5min)
/data/drive-sync/
    │
    ▼ (stateful watcher, poll 60s + sqlite state)
docling-serve:5001 (chunking)
    │
    ├── Voyage voyage-4-large (1024-dim dense)
    └── FastEmbed BM42 (sparse)
    │
    ▼
Qdrant (quantization via suffix)
Collections: gdrive_documents_scalar / gdrive_documents_binary
```

## Quick Start

### 1. Install rclone

```bash
# Official install script
curl https://rclone.org/install.sh | sudo bash

# Or via Makefile
make rclone-install
```

### 2. Setup Google Cloud Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Enable Google Drive API
3. Create Service Account:
   - Go to "IAM & Admin" > "Service Accounts"
   - Create new service account
   - Grant "Viewer" role (read-only)
   - Create JSON key and download
4. Save key to `/opt/credentials/gdrive-service-account.json`
5. Share your Drive folder with the service account email

### 3. Configure rclone

Edit `docker/rclone/rclone.conf`:

```ini
[gdrive]
type = drive
scope = drive.readonly
service_account_file = /opt/credentials/gdrive-service-account.json
root_folder_id = YOUR_FOLDER_ID_HERE
```

Get `root_folder_id` from Drive folder URL:
`https://drive.google.com/drive/folders/YOUR_FOLDER_ID_HERE`

Test configuration:

```bash
rclone ls gdrive: --config docker/rclone/rclone.conf
```

### 4. Install cron job

```bash
make sync-drive-install
```

This creates:
- `/opt/scripts/sync-drive.sh` - Sync script
- `/opt/scripts/gdrive-manifest.sh` - Manifest generator (stable file IDs)
- `/etc/cron.d/rclone-sync` - Cron job (every 5 min)

### 5. Setup Qdrant collections

```bash
make ingest-gdrive-setup
```

### 6. Run ingestion

```bash
# Once
make ingest-gdrive-run

# Continuous (watch mode)
make ingest-gdrive-watch
```

## Supported File Types

| Extension | Source | Notes |
|-----------|--------|-------|
| .pdf | Direct / Google Slides | OCR available |
| .docx | Direct / Google Docs | Full support |
| .xlsx | Direct / Google Sheets | Tables parsed |
| .pptx | Direct | Slides as pages |
| .md | Direct | Native |
| .txt | Direct | Native |

## rclone Export Formats

Google Workspace files are exported automatically:

| Google Type | Export Format |
|-------------|---------------|
| Google Docs | .docx |
| Google Sheets | .xlsx |
| Google Slides | .pptx |

Configure in `docker/rclone/sync-drive.sh`:

```bash
--drive-export-formats docx,xlsx,pptx
```

## Collection Schema

**Vectors (both collections):**
- `dense`: 1024-dim, cosine, quantization depends on collection (`*_scalar` / `*_binary`)
- `bm42`: sparse, IDF modifier

**Payload indexes:**
- `file_id` (keyword) - Stable ID from Drive or path hash
- `file_name` (keyword)
- `mime_type` (keyword)
- `source_path` (keyword)

## Replace Semantics

When a file changes:
1. DELETE all points where `file_id = X`
2. UPSERT new chunks

Point IDs are deterministic: `uuid5(file_id + chunk_location)`

## File ID Stability (Manifest)

The manifest script (`gdrive-manifest.sh`) generates `.gdrive_manifest.json` with Drive file IDs. This ensures:
- Renames in Drive don't create duplicates
- Moves in Drive don't break indexing
- Stable identity across sync cycles

## Deletions

If a file disappears from `/data/drive-sync` (deleted/renamed/moved in Drive → rclone sync), the watcher detects it via persistent state and deletes all points for that `file_id`.

## Makefile Targets

| Target | Description |
|--------|-------------|
| `make rclone-install` | Install rclone |
| `make sync-drive-install` | Install cron job + scripts |
| `make sync-drive-run` | Manual sync |
| `make sync-drive-status` | Show sync status |
| `make ingest-gdrive-setup` | Create Qdrant collections |
| `make ingest-gdrive-run` | Run ingestion once |
| `make ingest-gdrive-watch` | Run continuous watch |
| `make ingest-gdrive-status` | Show collection stats |

## Monitoring

```bash
# Check sync status
make sync-drive-status

# Check collection
make ingest-gdrive-status

# View logs
tail -f /var/log/rclone-sync.log
tail -f /var/log/rclone-manifest.log
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Sync not running | Check cron: `crontab -l`, `cat /etc/cron.d/rclone-sync` |
| Permission denied | Service account needs folder access (share folder with SA email) |
| `root_folder_id` not found | Get ID from Drive folder URL |
| Docling timeout | Use async endpoint for large PDFs |
| Voyage 429 | Reduce batch size, add delays |
| Too many non-doc files | Tighten allowlist in `sync-drive.sh` |
| Files not syncing | Check `rclone ls gdrive:` works |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GDRIVE_SYNC_DIR` | `/data/drive-sync` | Synced files location |
| `GDRIVE_COLLECTION_NAME` | `gdrive_documents_binary` | Target Qdrant collection |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant server |
| `DOCLING_URL` | `http://localhost:5001` | Docling server |
| `VOYAGE_API_KEY` | - | Required for embeddings |

## File Structure

```
docker/rclone/
├── rclone.conf          # rclone configuration
├── sync-drive.sh        # Sync script (→ /opt/scripts/)
├── gdrive-manifest.sh   # Manifest script (→ /opt/scripts/)
└── crontab              # Cron job (→ /etc/cron.d/)

/data/drive-sync/        # Synced files
├── .gdrive_manifest.json  # Drive file ID mapping
└── ...                    # Your documents

/var/log/
├── rclone-sync.log      # Sync logs
├── rclone-cron.log      # Cron output
└── rclone-manifest.log  # Manifest logs
```

## Security Notes

- Service account JSON contains credentials - never commit to git
- Use `drive.readonly` scope for read-only access
- Share only specific folders, not entire Drive
- Consider IP restrictions on service account if available
