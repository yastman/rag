# Runbook: Embedding Service Failure

> **Owner:** Retrieval & Embedding subsystems
> **Last verified:** 2025-07-14
> **Verification command:**
> ```bash
> curl -fsS http://localhost:8000/health
> ```

Use this runbook when embedding service alerts fire or embedding calls fail from the bot or ingestion pipeline.

## Symptoms

- BGE-M3 container stops producing logs (BGEServiceDown)
- BM42 sparse-vector container stops producing logs (BM42ServiceDown)
- Repeated error/exception messages in embedding containers (EmbeddingServiceError)
- Bot retrying BGE-M3 embedding calls (BGEEmbedRetryFromBot)
- Bot embedding calls failing after all retries (BGEEmbedErrorFromBot)
- Voyage API returning HTTP 429 rate-limit errors during ingestion (VoyageRateLimited)
- Users receiving degraded responses or timeouts due to missing embeddings

## Service / Container Map

| Compose service | Typical container names | Purpose |
|---|---|---|
| `bge-m3` | `dev-bge-m3` | Self-hosted BGE-M3 FastAPI embedding service (dense, sparse, ColBERT) |
| `user-base` | `dev-user-base` | Sentence-transformers service for user-level semantic caching |
| (historical) | `dev-bm42` | BM42 sparse vector container (sparse vectors now served by BGE-M3) |

> For service endpoints, ports, and Compose profiles, see the canonical [`DOCKER.md`](../../DOCKER.md).
> For local development commands and the validation ladder, see [`docs/LOCAL-DEVELOPMENT.md`](../LOCAL-DEVELOPMENT.md).

## Alerts Covered

| Alert | Source | Trigger | Severity |
|---|---|---|---|
| `BGEServiceDown` | [infrastructure.yaml](../../docker/monitoring/rules/infrastructure.yaml) | No logs from `dev-bge-m3` container for 10 min | warning |
| `BM42ServiceDown` | [infrastructure.yaml](../../docker/monitoring/rules/infrastructure.yaml) | No logs from `dev-bm42` container for 10 min | warning |
| `EmbeddingServiceError` | [infrastructure.yaml](../../docker/monitoring/rules/infrastructure.yaml) | >3 error/exception lines in `dev-bge-m3\|dev-bm42\|dev-user-base` within 5 min | warning |
| `BGEEmbedRetryFromBot` | [infrastructure.yaml](../../docker/monitoring/rules/infrastructure.yaml) | >3 retry log lines in `dev-bot` for `telegram_bot.integrations.embeddings` within 5 min | warning |
| `BGEEmbedErrorFromBot` | [infrastructure.yaml](../../docker/monitoring/rules/infrastructure.yaml) | Any "Embedding failed after retries" line in `dev-bot` within 5 min | critical |
| `VoyageRateLimited` | [ingestion.yaml](../../docker/monitoring/rules/ingestion.yaml) | >1 Voyage 429/rate-limit lines in `dev-ingestion` within 5 min | warning |

## Fast-Path Diagnosis (read-only)

Run these commands before deciding whether the issue is a service failure or an application bug.

### 1. Container health and reachability

```bash
# Check embedding services status
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env \
  -f compose.yml -f compose.dev.yml ps bge-m3 user-base

# BGE-M3 health check (dev Compose publishes on localhost:8000)
curl -fsS http://localhost:8000/health
```

Expected: HTTP 200 with:
```json
{"status": "ok", "model_loaded": true, "warmed_up": true}
```

> **Note:** During cold start (up to 7 min), the endpoint returns HTTP 200 with
> `"model_loaded": false` and `"warmed_up": false`. This means the service is
> running but **not yet ready to serve embeddings**. Wait for `model_loaded: true`
> before concluding the service is healthy.

If this fails with a non-200 response or times out, treat as **service failure** (container down or OOM).

### 2. GPU/CPU and memory usage

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env \
  -f compose.yml -f compose.dev.yml stats bge-m3 user-base --no-stream
```

BGE-M3 default memory limit is 4G. If usage is near the limit, the container may be OOM-killed.

### 3. Model load status

```bash
# Check if model is still loading (cold start can take up to 7 min)
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env \
  -f compose.yml -f compose.dev.yml logs bge-m3 --tail=50 | grep -i "model\|ready\|loaded"
```

The BGE-M3 service has a `start_period` of 420s (7 min) for initial model download. If the container recently restarted, wait for model load before escalating.

### 4. Bot retry and failure logs

```bash
# Check bot embedding retry activity
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env \
  -f compose.yml -f compose.dev.yml logs bot --tail=100 | grep -i "Retrying telegram_bot.integrations.embeddings\|Embedding failed after retries"
```

### 5. Voyage API rate-limit logs (ingestion)

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env \
  -f compose.yml -f compose.dev.yml logs ingestion --tail=100 | grep -i "voyage.*429\|rate.*limit"
```

### 6. Embedding service error logs

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env \
  -f compose.yml -f compose.dev.yml logs bge-m3 user-base --tail=200 | grep -iE "error|failed|exception"
```

## Service Failure vs App Bug

| Observation | Interpretation | Next step |
|---|---|---|
| `/health` returns non-200 or times out | Service failure | Check memory/disk; restart `bge-m3` |
| BGE-M3 healthy, but bot logs show `ConnectError` | App bug | Verify `BGE_M3_URL` env var (default `http://bge-m3:8000`) |
| Container running but no logs for 10+ min | Service failure | Container may be deadlocked; restart it |
| Errors only in `user-base` container | Service failure (caching layer) | Restart `user-base`; bot will still function without semantic cache |
| Bot shows "Retrying" but eventually succeeds | Transient issue | Monitor; if persistent, check BGE-M3 resource usage |
| Bot shows "Embedding failed after retries" | Service failure or timeout | Increase `BGE_M3_TIMEOUT` or restart `bge-m3` |
| Voyage 429 errors during ingestion | Rate limiting | Reduce ingestion batch frequency/document volume, or switch to `use_local_embeddings=True`; Voyage retry (6 attempts) will handle transient bursts |
| Errors only after recent deployment | App bug | Check for config/code changes in embedding wrappers |

## Source Paths

| Component | Path |
|---|---|
| BGE-M3 FastAPI service | [`services/bge-m3-api/app.py`](../../services/bge-m3-api/app.py) |
| BGE-M3 service configuration | [`services/bge-m3-api/config.py`](../../services/bge-m3-api/config.py) |
| LangChain embedding wrappers | [`telegram_bot/integrations/embeddings.py`](../../telegram_bot/integrations/embeddings.py) |
| Unified HTTP client with retry | [`src/services/bge_m3_client.py`](../../src/services/bge_m3_client.py) |
| Retry decorator (bge_retry) | [`src/services/_retry.py`](../../src/services/_retry.py) |
| Voyage AI service | [`src/services/voyage.py`](../../src/services/voyage.py) |
| Ingestion pipeline embedding usage | [`src/ingestion/unified/qdrant_writer.py`](../../src/ingestion/unified/qdrant_writer.py) |
| Alert rules (infrastructure) | [`docker/monitoring/rules/infrastructure.yaml`](../../docker/monitoring/rules/infrastructure.yaml) |
| Alert rules (ingestion) | [`docker/monitoring/rules/ingestion.yaml`](../../docker/monitoring/rules/ingestion.yaml) |
| Compose service definitions | [`compose.yml`](../../compose.yml) |
| Dev port mappings | [`compose.dev.yml`](../../compose.dev.yml) |
| CI env fixture | [`tests/fixtures/compose.ci.env`](../../tests/fixtures/compose.ci.env) |

## Environment Variables

| Variable | Default | Context |
|---|---|---|
| `BGE_M3_URL` | `http://bge-m3:8000` | Base URL for BGE-M3 service |
| `BGE_M3_TIMEOUT` | `120` (bot) / `600` (ingestion) | HTTP timeout in seconds |
| `BGE_M3_MEMORY_LIMIT` | `4G` | Docker memory limit for BGE-M3 container |
| `OMP_NUM_THREADS` | `4` | OpenMP thread count inside container |
| `MKL_NUM_THREADS` | `4` | MKL thread count inside container |
| `RETRIEVAL_DENSE_PROVIDER` | `bge_m3_api` | Dense embedding provider selection |
| `RETRIEVAL_SPARSE_PROVIDER` | `bge_m3_api` | Sparse embedding provider selection |
| `VOYAGE_API_KEY` | (required) | Voyage AI API key (when `use_local_embeddings=False`) |
| `BGE_M3_CONCURRENCY` | `1` | Ingestion concurrency for BGE-M3 calls |

## Logs and Artifacts

| Artifact | Location / command |
|---|---|
| BGE-M3 runtime logs | `docker compose logs bge-m3 --tail=200` |
| user-base runtime logs | `docker compose logs user-base --tail=200` |
| Bot embedding logs | `docker compose logs bot --tail=200 \| grep -i embed` |
| Ingestion logs | `docker compose logs ingestion --tail=200` |
| BGE-M3 model cache | Docker volume `bge_m3_model_cache` |
| Container memory stats | `docker stats dev-bge-m3 --no-stream` |

## Remediation

> **Caution:** Commands in this section mutate state. Run only after fast-path diagnosis confirms the issue is not an app bug.

### BGE-M3 Container Down or Unresponsive

1. Restart the service:
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env \
     -f compose.yml -f compose.dev.yml restart bge-m3
   ```

2. Wait for model to load (up to 7 min on cold start):
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env \
     -f compose.yml -f compose.dev.yml logs bge-m3 -f --since 1m | grep -i "ready\|loaded"
   ```

3. Verify health:
   ```bash
   curl -fsS http://localhost:8000/health
   ```

### OOM or Memory Pressure

1. Check if the container was killed:
   ```bash
   docker inspect dev-bge-m3 --format='{{.State.OOMKilled}}'
   ```

2. Increase memory limit in `compose.yml` or via env:
   ```bash
   # Set BGE_M3_MEMORY_LIMIT=6G in your .env file, then:
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env \
     -f compose.yml -f compose.dev.yml up -d bge-m3
   ```

3. Reduce thread counts if memory is limited:
   ```bash
   # Set OMP_NUM_THREADS=2 and MKL_NUM_THREADS=2 in .env
   ```

### Bot Embedding Failures (BGEEmbedErrorFromBot)

1. Confirm BGE-M3 is healthy (see Fast-Path step 1).

2. If healthy but timing out, increase timeout:
   ```bash
   # Set BGE_M3_TIMEOUT=240 in bot environment
   ```

3. Restart the bot to pick up new config:
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env \
     -f compose.yml -f compose.dev.yml restart bot
   ```

The bot uses `bge_retry` (3 attempts, 0.5s initial backoff, 4s max) and retries on transport errors (`ConnectError`, `ReadTimeout`). If all 3 attempts fail, the "Embedding failed after retries" critical alert fires.

### Voyage API Rate Limiting (VoyageRateLimited)

1. Reduce the number of documents per ingestion run or increase inter-batch delay.

2. If running large ingestion jobs, lower the volume of documents being processed concurrently.

3. The Voyage client uses tenacity with 6 retry attempts and exponential backoff. Rate-limit errors (`voyageai.error.RateLimitError`) are retried automatically. If the alert persists after retries exhaust, reduce ingestion throughput or contact Voyage AI to increase your rate limit.

4. If Voyage is persistently rate-limited, switch to local embeddings:
   ```bash
   # Set use_local_embeddings=True in ingestion config
   # This uses BGE-M3 instead of Voyage AI
   ```

### user-base Container Issues

1. Restart the service:
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env \
     -f compose.yml -f compose.dev.yml restart user-base
   ```

2. The user-base service has a 2G memory limit. If it OOMs, increase via compose overrides.

## Prevention

- Monitor `/health` endpoint of BGE-M3 and user-base services
- Set memory alerts at 80% of configured limits (4G for BGE-M3, 2G for user-base)
- Keep `BGE_M3_TIMEOUT` tuned to actual inference latency (120s covers most batch sizes)
- Pre-pull the BGE-M3 model image to reduce cold-start time in production
- Use `BGE_M3_CONCURRENCY=1` for ingestion to avoid overwhelming the service
- Monitor Voyage API usage dashboard for approaching rate limits
- Run `curl -fsS http://localhost:8000/health` as a periodic health check

## See Also

- [Qdrant Troubleshooting](QDRANT_TROUBLESHOOTING.md)
- [Redis Cache Degradation](REDIS_CACHE_DEGRADATION.md)
- [VPS Google Drive Ingestion Recovery](vps-gdrive-ingestion-recovery.md)
- [Docker Services Reference](../../DOCKER.md)
- [Local Development Guide](../LOCAL-DEVELOPMENT.md)
