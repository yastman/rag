# Runbook: Qdrant Telemetry and Monitoring

> **Owner:** Retrieval & Vector Storage subsystems
> **Last verified:** 2026-05-07
> **Verification command:**
> ```bash
> curl -fsS http://localhost:6333/collections/gdrive_documents_bge
> ```

Use this runbook when Qdrant collection has issues or monitoring shows anomalies.

## Symptoms

- Collection exists but shows 0 points despite successful ingestion
- Slow query responses from Qdrant
- ColBERT coverage drops below 99.5%
- Collection health shows degraded state
- `Qdrant connection refused` or timeout errors in bot / API logs

## Service / Container Map

| Compose service | Typical container names |
|---|---|
| `qdrant` | `dev-qdrant-1` (Compose v2+), `dev_qdrant_1` (legacy) |

> For service endpoints, ports, and Compose profiles, see the canonical [`DOCKER.md`](../../DOCKER.md).
> For local development commands and the validation ladder, see [`docs/LOCAL-DEVELOPMENT.md`](../LOCAL-DEVELOPMENT.md).

## Fast-Path Diagnosis (read-only)

Run these commands before deciding whether the issue is a service failure or an application bug.

### 1. Container health and reachability

```bash
# Check service status with deterministic CI env (read-only, no local .env required)
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml ps qdrant

# Health check (host-side; dev Compose publishes Qdrant REST on localhost:6333)
curl -fsS http://localhost:6333/readyz
```

Expected: exit code `0` (HTTP 200 OK).
If this fails, treat as **service failure** (container down, disk full, or OOM).

### 2. Collection and points count

```bash
# List all collections
curl -fsS http://localhost:6333/collections | jq

# Check specific collection metadata
curl -fsS http://localhost:6333/collections/gdrive_documents_bge | jq

# Get points count
curl -fsS 'http://localhost:6333/collections/gdrive_documents_bge/points/count' | jq
```

If `count: 0` but ingestion succeeded, see [VPS Google Drive Ingestion Recovery](vps-gdrive-ingestion-recovery.md).

### 3. Cluster health (single-node deployments)

```bash
curl -fsS http://localhost:6333/cluster | jq
curl -fsS http://localhost:6333/cluster/status | jq
```

On a single-node dev setup the cluster should show itself as the only peer.
If Raft consensus is unhealthy, treat as **service failure** (restart Qdrant after checking disk).

### 4. Query latency metrics

```bash
curl -fsS http://localhost:6333/metrics | grep -E "(query_latency|search_latency)"
```

### 5. Logs (read-only)

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs qdrant --tail=200
```

Check for:
- OOM killer messages
- Disk-full errors (`No space left on device`)
- Segment merge failures
- WAL corruption warnings

## Service Failure vs App Bug

| Observation | Interpretation | Next step |
|---|---|---|
| `/readyz` or `/collections` fails from the host | Service failure | Check host disk/memory; restart Qdrant |
| Qdrant is healthy, but bot logs show `Connection refused` | App bug | Verify `QDRANT_URL` and `QDRANT_COLLECTION` in bot / API env |
| `points/count` is 0 after ingestion reported success | App bug / ingestion failure | Check ingestion manifest and logs; see [VPS Google Drive Ingestion Recovery](vps-gdrive-ingestion-recovery.md) |
| `points/count` drops suddenly (>5%) | Service failure or data loss | Inspect Qdrant storage volume; check for accidental collection deletion |
| Queries are slow but Qdrant CPU/memory are low | App bug | Profile ColBERT reranking or reduce `RERANK_CANDIDATES_MAX`; temporarily set `RERANK_PROVIDER=none` in `compose.dev.yml` |
| High Qdrant CPU/memory with normal query volume | Service failure / capacity | Increase `deploy.resources.limits.memory` in `compose.yml`; check segment count |
| ColBERT coverage drops below 99.5% | App bug | Re-run ingestion with ColBERT enabled; check `search_engines.py` for schema drift |

## Source Paths

| Component | Path |
|---|---|
| Qdrant search & hybrid retrieval | [`src/retrieval/search_engines.py`](../../src/retrieval/search_engines.py) |
| Shared Qdrant models & filters | [`src/retrieval/search_engine_shared.py`](../../src/retrieval/search_engine_shared.py) |
| Reranking logic | [`src/retrieval/reranker.py`](../../src/retrieval/reranker.py) |
| Qdrant service definition | [`compose.yml`](../../compose.yml) |
| Dev overrides (ports, profiles) | [`compose.dev.yml`](../../compose.dev.yml) |
| CI env fixture (deterministic interpolation) | [`tests/fixtures/compose.ci.env`](../../tests/fixtures/compose.ci.env) |

## Logs and Artifacts

| Artifact | Location / command |
|---|---|
| Runtime logs | `docker compose logs qdrant --tail=200` |
| Qdrant storage volume | `qdrant_data` (managed volume, inspect with `docker volume inspect dev_qdrant_data`) |
| Collection snapshots | Inside container at `/qdrant/storage/snapshots/` |
| Query metrics | `curl http://localhost:6333/metrics` (dev only) |
| Ingestion manifest | `ingestion` service volume `ingestion-manifest`; check with `make ingest-unified-status` |

## Remediation

> ⚠️ **Caution:** Commands in this section mutate state. Run only after fast-path diagnosis confirms the issue is not an app bug.

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
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml stats qdrant
   ```

2. Consider increasing Qdrant resources in `compose.yml`:
   - Current limit: `memory: 1G`
   - Increase if segment count is high or payloads are large

3. Temporarily disable ColBERT reranking to isolate Qdrant vs reranker latency:
   - Set `RERANK_PROVIDER=none` in `compose.dev.yml` (dev) or the bot environment (production)
   - Restart the bot / API service and re-run the slow query

### ColBERT Coverage Drop

ColBERT coverage measures the percentage of vectors with ColBERT embeddings.

**Causes:**
- Ingestion pipeline error during ColBERT computation
- Schema change that doesn't include ColBERT vectors

**Remediation:**
1. Re-run ingestion with ColBERT enabled
2. Check ingestion logs for ColBERT-related errors
3. Verify `search_engines.py` still requests `multi_vector` payloads for the collection

### Disk or Memory Pressure

If Qdrant logs show storage or memory errors:

1. Inspect storage volume usage:
   ```bash
   docker exec dev-qdrant-1 df -h /qdrant/storage
   ```

2. Free space if needed (e.g., remove old snapshots inside the container):
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec qdrant sh -c 'rm -f /qdrant/storage/snapshots/*.snapshot'
   ```

3. Restart Qdrant after clearing space:
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml restart qdrant
   ```

## Prevention

- Monitor `collection_points_count` metric
- Set up alerts for >5% point count drop
- Regular health checks via `/health` and `/readyz` endpoints
- Keep Qdrant storage volume on a disk with >20% headroom
- Run `make ingest-unified-status` after every ingestion batch

## See Also

- [Redis Cache Degradation](REDIS_CACHE_DEGRADATION.md)
- [VPS Google Drive Ingestion Recovery](vps-gdrive-ingestion-recovery.md)
- [Docker Services Reference](../../DOCKER.md)
- [Local Development Guide](../LOCAL-DEVELOPMENT.md)
