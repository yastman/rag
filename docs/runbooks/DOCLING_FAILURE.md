# Runbook: Docling Failure

- **Owner:** Ingestion / On-call
- **Last verified:** 2026-05-07
- **Verification command:** `curl -s http://localhost:5001/health`

Use this runbook when Docling (document conversion service) alerts fire or document ingestion is blocked due to conversion failures.

## Symptoms

- `DoclingDown` alert: no logs from the Docling container for 10 minutes
- `DoclingOOM` alert: container killed with OOM, segfault, or exit code 137
- `DoclingConversionFailed` alert: repeated document conversion errors in logs
- `DoclingError` alert: elevated error/exception rate in Docling logs
- Ingestion pipeline stalls with documents stuck in pending state
- Bot returns stale or missing knowledge for recently ingested documents
- Ingestion container logs show `docling.*error` or `docling.*timeout`

## Diagnosis

### 1. Check Docling Container State

```bash
# Is the container running?
docker compose ps docling

# Recent logs (bounded)
docker compose logs docling --tail=100
```

### 2. Test Docling Health Endpoint

```bash
# Health check (expect HTTP 200)
curl -s http://localhost:5001/health
```

If the health endpoint is unreachable, the container is down or not listening on port 5001.

### 3. Check for OOM / Exit 137

```bash
# Inspect container state
docker inspect dev-docling-1 --format '
  Name={{.Name}}
  OOMKilled={{.State.OOMKilled}}
  ExitCode={{.State.ExitCode}}
  Status={{.State.Status}}
'

# Search logs for OOM indicators
docker compose logs docling --tail=200 | grep -i "killed\|oom\|out of memory\|segmentation fault\|137"
```

**Interpretation:**
- `OOMKilled=true` or `ExitCode=137` - Docling was killed by the kernel due to memory exhaustion. Large PDFs or concurrent conversions can trigger this.
- `Status=restarting` with `OOMKilled=false` - Likely a code-level error; check logs for Python tracebacks.

### 4. Check Conversion Errors

```bash
# Look for conversion failures
docker compose logs docling --tail=200 | grep -i "failed to convert\|conversion failed\|pdf.*error\|ocr.*error\|timeout"

# Check which documents are failing
docker compose logs ingestion --tail=100 | grep -i "docling"
```

### 5. Check Resource Usage

```bash
# Current memory and CPU usage
docker stats dev-docling-1 --no-stream

# Check if memory is near the limit (default: 2G)
docker inspect dev-docling-1 --format '{{.HostConfig.Memory}}'
```

### 6. Verify Ingestion Pipeline Connectivity

```bash
# Confirm ingestion can reach Docling
docker compose exec ingestion python -c "import urllib.request; urllib.request.urlopen('http://docling:5001/health', timeout=5); print('OK')"
```

### 7. Check Docling Cache Health

Docling caches HuggingFace models for PDF/OCR processing. A corrupted cache can cause repeated failures:

```bash
# Check cache volume size
docker compose exec docling du -sh /app/.cache/huggingface 2>/dev/null || echo "Cache dir not accessible"

# Check for filesystem errors in logs
docker compose logs docling --tail=100 | grep -i "corrupt\|no space\|permission denied"
```

## Common Error Patterns

### OOM on Large PDFs

**Symptom:** Docling crashes with exit code 137 when processing large (>50 page) PDFs with complex tables or images.

**Cause:** The `accurate` table mode (`DOCLING_TABLE_MODE=accurate`) uses more memory for table detection. Large documents with many tables can exhaust the 2G memory limit.

### Conversion Timeout

**Symptom:** Logs show timeout errors; ingestion retries the same document repeatedly.

**Cause:** A single document takes longer than the configured timeout. Complex PDFs with OCR-heavy pages are the usual culprit.

### Model Download Failure on Cold Start

**Symptom:** Container starts but health check fails during the 120s start period. Logs show HuggingFace download errors.

**Cause:** First-time startup requires downloading OCR/table models. If network is unavailable or the cache volume was cleared, startup takes longer or fails.

### Permission Denied on Data Volume

**Symptom:** Conversion fails immediately with `PermissionError` or `OSError`.

**Cause:** The bind-mounted `./data/docling` directory has incorrect ownership. The container runs with default user permissions.

## Remediation

> **Caution:** Mutating commands below. Run only after confirming the diagnosis above.

### Restart Docling

```bash
docker compose restart docling
```

Wait for the health check to pass (up to 120s start period):

```bash
# Watch until healthy
docker compose ps docling
```

### Increase Memory Limit (OOM)

If OOM is confirmed, raise the memory limit in `compose.yml`:

```yaml
# compose.yml -> services.docling.deploy.resources.limits
memory: 4G  # default is 2G
```

Then recreate the container:

```bash
docker compose up -d --force-recreate docling
```

### Clear Corrupted Cache

> **Caution:** This forces a full model re-download on next startup (may take several minutes).

```bash
# Stop Docling
docker compose stop docling

# Remove the cache volume
docker volume rm "$(docker volume ls -q | grep docling_cache)"

# Restart (will re-download models)
docker compose up -d docling
```

### Skip Problematic Document

If a single document repeatedly crashes Docling, temporarily exclude it:

```bash
# Identify the failing document from ingestion logs
docker compose logs ingestion --tail=50 | grep -i "docling.*failed\|processing.*error"

# Move the problematic file out of the sync directory
# (adjust path based on your GDRIVE_SYNC_DIR)
mv "${GDRIVE_SYNC_DIR}/problematic-file.pdf" "${GDRIVE_SYNC_DIR}/../quarantine/"
```

### Switch Table Mode for Memory Reduction

If OOM is caused by table-heavy documents, switch to the faster (less accurate) table mode:

Edit `compose.yml` and change:
```yaml
DOCLING_TABLE_MODE: fast  # was: accurate
```

Then recreate:

```bash
docker compose up -d --force-recreate docling
```

### Fix Data Directory Permissions

```bash
# Ensure the data directory is writable
chmod 755 ./data/docling
```

## Prevention

- Monitor container memory usage; set alerts at 80% of the limit
- Keep the `docling_cache` volume persistent across deploys to avoid cold-start downloads
- Test large documents (>50 pages, table-heavy) in staging before bulk ingestion
- Consider splitting very large PDFs before ingestion
- Review `DOCLING_TABLE_MODE` setting when changing document corpus characteristics
- Ensure `start_period: 120s` in the health check allows time for model loading

## See Also

- [Ingestion Recovery](vps-gdrive-ingestion-recovery.md)
- [Docker Services Reference](../../DOCKER.md)
- [Docling Data Directory](../../data/docling/README.md)
- [ADR: CocoIndex + Docling Ingestion](../adr/0013-cocoindex-docling-ingestion.md)
- [Coverage Matrix](COVERAGE_MATRIX.md)
