***REMOVED*** Runbook: Qdrant Telemetry and Monitoring

Use this runbook when Qdrant collection has issues or monitoring shows anomalies.

***REMOVED******REMOVED*** Symptoms

- Collection exists but shows 0 points despite successful ingestion
- Slow query responses from Qdrant
- ColBERT coverage drops below 99.5%
- Collection health shows degraded state

***REMOVED******REMOVED*** Diagnosis

***REMOVED******REMOVED******REMOVED*** 1. Check Collection Status

```bash
***REMOVED*** List all collections
curl -s http://localhost:6333/collections | jq

***REMOVED*** Check specific collection
curl -s http://localhost:6333/collections/gdrive_documents_bge | jq

***REMOVED*** Get collection info with points count
curl -s http://localhost:6333/collections/gdrive_documents_bge/info | jq
```

***REMOVED******REMOVED******REMOVED*** 2. Check Points Count

```bash
***REMOVED*** Via Qdrant UI or CLI
curl -s 'http://localhost:6333/collections/gdrive_documents_bge/points/count' | jq
```

If `count: 0` but ingestion succeeded, see [VPS Google Drive Ingestion Recovery](vps-gdrive-ingestion-recovery.md).

***REMOVED******REMOVED******REMOVED*** 3. Check Cluster Health

```bash
***REMOVED*** Cluster info
curl -s http://localhost:6333/cluster | jq

***REMOVED*** Raft consensus status
curl -s http://localhost:6333/cluster/status | jq
```

***REMOVED******REMOVED******REMOVED*** 4. Check Query Latency

```bash
***REMOVED*** Get service metrics
curl -s http://localhost:6333/metrics | grep -E "(query_latency|search_latency)"
```

***REMOVED******REMOVED*** Remediation

***REMOVED******REMOVED******REMOVED*** Collection Has 0 Points

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

***REMOVED******REMOVED******REMOVED*** Slow Queries

1. Check CPU/memory usage:
   ```bash
   docker stats qdrant
   ```

2. Consider increasing Qdrant resources in `compose.yml`

3. Check if ColBERT reranking is causing slowdowns:
   - Set `RERANK_PROVIDER=none` temporarily

***REMOVED******REMOVED******REMOVED*** ColBERT Coverage Drop

ColBERT coverage measures the percentage of vectors with ColBERT embeddings.

**Causes:**
- Ingestion pipeline error during ColBERT computation
- Schema change that doesn't include ColBERT vectors

**Remediation:**
1. Re-run ingestion with ColBERT enabled
2. Check ingestion logs for ColBERT-related errors

***REMOVED******REMOVED*** Prevention

- Monitor `collection_points_count` metric
- Set up alerts for >5% point count drop
- Regular health checks via `/health` endpoint
