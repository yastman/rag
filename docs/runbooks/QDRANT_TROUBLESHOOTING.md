# Runbook: Qdrant Telemetry and Monitoring

Use this runbook when Qdrant collection has issues or monitoring shows anomalies.

## Symptoms

- Collection exists but shows 0 points despite successful ingestion
- Slow query responses from Qdrant
- ColBERT coverage drops below 99.5%
- Collection health shows degraded state

## Diagnosis

### 1. Check Collection Status

```bash
# List all collections
curl -s http://localhost:6333/collections | jq

# Check specific collection
curl -s http://localhost:6333/collections/gdrive_documents_bge | jq

# Get collection info with points count
curl -s http://localhost:6333/collections/gdrive_documents_bge/info | jq
```

### 2. Check Points Count

```bash
# Via Qdrant UI or CLI
curl -s 'http://localhost:6333/collections/gdrive_documents_bge/points/count' | jq
```

If `count: 0` but ingestion succeeded, see [VPS Google Drive Ingestion Recovery](vps-gdrive-ingestion-recovery.md).

### 3. Check Cluster Health

```bash
# Cluster info
curl -s http://localhost:6333/cluster | jq

# Raft consensus status
curl -s http://localhost:6333/cluster/status | jq
```

### 4. Check Query Latency

```bash
# Get service metrics
curl -s http://localhost:6333/metrics | grep -E "(query_latency|search_latency)"
```

## Remediation

### Collection Has 0 Points

1. Verify ingestion completed:
   ```bash
   make ingest-unified-status
   ```

2. Check ingestion logs:
   ```bash
   make ingest-unified-logs
   ```

3. If using rclone sync, verify host directory:
   ```bash
   ls -la "$GDRIVE_SYNC_DIR"
   ```

See [VPS Google Drive Ingestion Recovery](vps-gdrive-ingestion-recovery.md) for full procedure.

### Slow Queries

1. Check CPU/memory usage:
   ```bash
   docker stats qdrant
   ```

2. Consider increasing Qdrant resources in `compose.yml`

3. Check if ColBERT reranking is causing slowdowns:
   - Set `RERANK_PROVIDER=none` temporarily

### ColBERT Coverage Drop

ColBERT coverage measures the percentage of vectors with ColBERT embeddings.

**Causes:**
- Ingestion pipeline error during ColBERT computation
- Schema change that doesn't include ColBERT vectors

**Remediation:**
1. Re-run ingestion with ColBERT enabled
2. Check ingestion logs for ColBERT-related errors

## Prevention

- Monitor `collection_points_count` metric
- Set up alerts for >5% point count drop
- Regular health checks via `/health` endpoint
