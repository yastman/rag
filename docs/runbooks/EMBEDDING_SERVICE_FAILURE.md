# Runbook: Embedding Service Failure

> **Owner:** Retrieval & Embeddings subsystems
> **Last verified:** 2026-05-07
> **Verification command:**
> ```bash
> curl -fsS http://localhost:8000/health
> ```

Use this runbook when embedding services are down, degraded, or returning errors. Covers both the local BGE-M3 embedding service and the external Voyage AI provider used during ingestion.

## Alerts Covered

| Alert | Severity | Source | Trigger |
|-------|----------|--------|---------|
| `BGEServiceDown` | warning | infrastructure.yaml | No logs from `dev-bge-m3` container for 10 min |
| `BM42ServiceDown` | warning | infrastructure.yaml | No logs from `dev-bm42` container for 10 min |
| `EmbeddingServiceError` | warning | infrastructure.yaml | >3 error/failed/exception lines in embedding containers in 5 min |
| `BGEEmbedRetryFromBot` | warning | infrastructure.yaml | Bot retrying BGE-M3 embedding calls (>3 retries in 5 min) |
| `BGEEmbedErrorFromBot` | critical | infrastructure.yaml | Bot embedding calls failing after all retries exhausted |
| `VoyageRateLimited` | warning | ingestion.yaml | Voyage API 429 responses detected in ingestion logs |

## Symptoms

- Bot responses contain no retrieved context (search returns empty)
- Bot logs show `Retrying telegram_bot.integrations.embeddings` or `Embedding failed after retries`
- Ingestion pipeline stalls with Voyage rate-limit (HTTP 429) errors
- Queries to Qdrant succeed but return zero results because embeddings were never generated
- BGE-M3 health endpoint (`/health`) returns non-200 or times out
- Container `dev-bge-m3` or `dev-bm42` is restarting or missing from `docker compose ps`

## Service / Container Map

| Compose service | Typical container names | Port (dev) | Health endpoint |
|---|---|---|---|
| `bge-m3` | `dev-bge-m3-1` | `localhost:8000` | `GET /health` |
| `bm42` | `dev-bm42-1` | (internal only) | `GET /health` |
| `user-base` | `dev-user-base-1` | (internal only) | `GET /health` |
| `bot` | `dev-bot-1` | - | - |
| `ingestion` | `dev-ingestion-1` | - | - |

> For full service endpoints and Compose profiles, see [`DOCKER.md`](../../DOCKER.md).
> For local development commands and the validation ladder, see [`docs/LOCAL-DEVELOPMENT.md`](../LOCAL-DEVELOPMENT.md).

## Fast-Path Diagnosis (read-only)

Run these commands before deciding whether the issue is a service failure or an application bug.

### 1. Container health and reachability

```bash
# Check embedding service status
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env \
  -f compose.yml -f compose.dev.yml ps bge-m3

# Health check (host-side; bge-m3 publishes on localhost:8000 in dev)
curl -fsS http://localhost:8000/health
```

Expected: exit code `0` (HTTP 200 OK).
If this fails, treat as **service failure** (container down, OOM, or model failed to load).

### 2. Check for BGE-M3 retry/error signals in bot logs

```bash
# Retries (degraded but still functioning)
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env \
  -f compose.yml -f compose.dev.yml logs bot --tail=200 \
  | grep -i "Retrying telegram_bot.integrations.embeddings"

# Hard failures (all retries exhausted)
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env \
  -f compose.yml -f compose.dev.yml logs bot --tail=200 \
  | grep -i "Embedding failed after retries"
```

### 3. Check embedding service logs for errors

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env \
  -f compose.yml -f compose.dev.yml logs bge-m3 --tail=200 \
  | grep -iE "error|failed|exception|oom|killed"
```

### 4. Check BM42 container (if alert is BM42ServiceDown)

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env \
  -f compose.yml -f compose.dev.yml ps bm42

COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env \
  -f compose.yml -f compose.dev.yml logs bm42 --tail=100
```

### 5. Voyage rate-limit diagnosis (ingestion pipeline)

```bash
# Check for 429 errors in ingestion logs
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env \
  -f compose.yml -f compose.dev.yml logs ingestion --tail=200 \
  | grep -iE "voyage.*429|rate.*limit"
```

### 6. OOM / Exit 137 diagnosis

```bash
docker inspect dev-bge-m3-1 --format '
  Name={{.Name}}
  OOMKilled={{.State.OOMKilled}}
  ExitCode={{.State.ExitCode}}
  Status={{.State.Status}}
'
```

**Interpretation:**
- `OOMKilled=true` or `ExitCode=137` -- BGE-M3 was killed by the kernel due to memory exhaustion.
- `Status=restarting` with `OOMKilled=false` -- Likely a model loading failure or configuration error.

### 7. Prometheus metrics (if available)

```bash
# BGE-M3 encoding metrics
curl -fsS http://localhost:8000/metrics | grep -E "bge_encode"
```

## Service Failure vs App Bug

| Observation | Interpretation | Next step |
|---|---|---|
| `/health` fails from the host | Service failure | Check container state; restart `bge-m3` |
| BGE-M3 healthy, but bot shows `Connection refused` | App bug | Verify `BGE_M3_URL` env var in bot container |
| Retries happening but queries eventually succeed | Degraded service | Monitor; consider increasing `BGE_M3_TIMEOUT` |
| All retries exhausted, embedding failures | Service failure | Restart `bge-m3`; check OOM |
| `dev-bm42` container missing | Service failure | Restart `bm42`; check if profile is enabled |
| Voyage 429 errors during ingestion | Rate limiting | Reduce batch concurrency; add backoff delay |
| Errors in `dev-user-base` but not `dev-bge-m3` | Partial failure | Restart `user-base` independently |
| High `bge_encode_seconds` latency | Degraded performance | Check CPU/memory; reduce `BGE_M3_TIMEOUT` batch size |

## Source Paths

| Component | Path |
|---|---|
| BGE-M3 API service | [`services/bge-m3-api/app.py`](../../services/bge-m3-api/app.py) |
| BGE-M3 Dockerfile | [`services/bge-m3-api/Dockerfile`](../../services/bge-m3-api/Dockerfile) |
| Bot embeddings integration | [`telegram_bot/integrations/embeddings.py`](../../telegram_bot/integrations/embeddings.py) |
| Bot BGE-M3 HTTP client | [`telegram_bot/services/bge_m3_client.py`](../../telegram_bot/services/bge_m3_client.py) |
| Shared BGE-M3 client (src) | [`src/services/bge_m3_client.py`](../../src/services/bge_m3_client.py) |
| Voyage AI service | [`src/services/voyage.py`](../../src/services/voyage.py) |
| Ingestion flow (Voyage embeddings) | [`src/ingestion/cocoindex_flow.py`](../../src/ingestion/cocoindex_flow.py) |
| Compose service definition | [`compose.yml`](../../compose.yml) |
| Dev overrides (ports, profiles) | [`compose.dev.yml`](../../compose.dev.yml) |
| Alert rules (infrastructure) | [`docker/monitoring/rules/infrastructure.yaml`](../../docker/monitoring/rules/infrastructure.yaml) |
| Alert rules (ingestion) | [`docker/monitoring/rules/ingestion.yaml`](../../docker/monitoring/rules/ingestion.yaml) |
| CI env fixture | [`tests/fixtures/compose.ci.env`](../../tests/fixtures/compose.ci.env) |

## Remediation

> **Caution:** Commands in this section mutate state. Run only after fast-path diagnosis confirms the issue is not an app bug.

### BGEServiceDown / BGEEmbedErrorFromBot - Restart BGE-M3

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env \
  -f compose.yml -f compose.dev.yml restart bge-m3
```

Wait for the health check to pass (start period is up to 420s for cold-start model download):

```bash
# Poll until healthy
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env \
  -f compose.yml -f compose.dev.yml ps bge-m3
```

### BM42ServiceDown - Restart BM42

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env \
  -f compose.yml -f compose.dev.yml restart bm42
```

### EmbeddingServiceError - Identify and restart affected container

The alert fires for any of `dev-bge-m3`, `dev-bm42`, or `dev-user-base`. Check which container is generating errors, then restart only that service:

```bash
# Check each container's recent errors
for svc in bge-m3 bm42 user-base; do
  echo "=== $svc ==="
  COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env \
    -f compose.yml -f compose.dev.yml logs "$svc" --tail=50 \
    | grep -ciE "error|failed|exception"
done
```

Restart the specific service with the highest error count.

### BGEEmbedRetryFromBot - Investigate degradation

This alert indicates the service is slow or intermittently failing, but the bot is still recovering via retries.

1. Check BGE-M3 resource usage:
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env \
     -f compose.yml -f compose.dev.yml stats bge-m3 --no-stream
   ```

2. If memory is near the limit (`BGE_M3_MEMORY_LIMIT`, default 4G), increase it in `compose.yml` or via env:
   ```bash
   BGE_M3_MEMORY_LIMIT=6G COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env \
     -f compose.yml -f compose.dev.yml up -d --force-recreate bge-m3
   ```

3. If CPU is saturated, reduce concurrent load or increase `BGE_M3_TIMEOUT` in the bot env.

### BGE-M3 OOM (ExitCode 137)

1. Increase the memory limit:
   - Default: `BGE_M3_MEMORY_LIMIT=4G` in `compose.yml`
   - Increase to `6G` or `8G` depending on available host memory

2. Recreate the container with the new limit:
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env \
     -f compose.yml -f compose.dev.yml up -d --force-recreate bge-m3
   ```

3. Monitor for recurrence -- if OOM repeats, check for memory leaks in the model serving code or reduce `--limit-concurrency` in the Dockerfile CMD.

### VoyageRateLimited - Reduce ingestion batch concurrency

The Voyage AI API enforces rate limits. When hit, the ingestion pipeline logs HTTP 429 responses.

1. Reduce batch concurrency in the ingestion configuration:
   - Check `src/ingestion/cocoindex_flow.py` for batch size settings
   - Reduce the number of concurrent embedding requests

2. Increase backoff delay -- the `VoyageService` in `src/services/voyage.py` uses `tenacity` retry with exponential backoff. If retries are still exhausting, consider:
   - Increasing `stop_after_attempt` count
   - Widening the `wait_random_exponential` parameters

3. If rate limiting is persistent, check your Voyage AI plan limits and consider upgrading or distributing load across multiple API keys.

4. Restart ingestion after adjusting configuration:
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env \
     -f compose.yml -f compose.dev.yml restart ingestion
   ```

## Impact on RAG Quality

When embedding services fail:
- **Bot queries return no context** -- the retrieval pipeline cannot generate query embeddings, so Qdrant search returns empty results
- **Ingestion halts** -- new documents are not embedded and will not appear in search results
- **Degraded mode** -- if retries succeed intermittently, users experience slow responses but still get results
- **No fallback** -- unlike LLM routing, there is no automatic fallback between BGE-M3 and Voyage for query-time embeddings; they serve different roles (local dense/sparse vs. external ingestion)

## Prevention

- Monitor `bge_encode_requests_total` and `bge_encode_seconds` Prometheus metrics
- Set up alerts for container restart loops (already covered by `BGEServiceDown`)
- Keep BGE-M3 memory limit with headroom above observed peak usage
- For Voyage: monitor API quota usage in the Voyage AI dashboard
- Run periodic health checks: `curl -fsS http://localhost:8000/health`
- Validate embedding dimensions after model updates (BGE-M3 produces 1024-dim dense vectors)

## See Also

- [Qdrant Troubleshooting](QDRANT_TROUBLESHOOTING.md)
- [LiteLLM Failure](LITEllm_FAILURE.md)
- [VPS Google Drive Ingestion Recovery](vps-gdrive-ingestion-recovery.md)
- [Docker Services Reference](../../DOCKER.md)
- [Local Development Guide](../LOCAL-DEVELOPMENT.md)
