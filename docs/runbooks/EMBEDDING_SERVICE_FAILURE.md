# Runbook: Embedding Service Failure

> **Owner:** Embeddings / Retrieval
> **Last verified:** 2026-05-07
> **Verification command:**
> ```bash
> curl -fsS http://localhost:8000/health
> ```

Use this runbook when embedding services (BGE-M3, BM42, user-base) are down, returning errors, or when the bot is retrying/failing embedding calls. Also covers Voyage API rate limiting during ingestion.

## Symptoms

- No logs from `dev-bge-m3` container for 10+ minutes (BGEServiceDown alert)
- No logs from `dev-bm42` container for 10+ minutes (BM42ServiceDown alert)
- Multiple errors/exceptions across embedding containers `dev-bge-m3`, `dev-bm42`, `dev-user-base` (EmbeddingServiceError alert)
- Bot retrying embedding calls: `Retrying telegram_bot.integrations.embeddings` in bot logs (BGEEmbedRetryFromBot alert)
- Bot embedding calls failing after all retries exhausted: `Embedding failed after retries` (BGEEmbedErrorFromBot alert)
- Voyage API returning HTTP 429 (rate limited) in ingestion container (VoyageRateLimited alert)

## Service / Container Map

| Compose service | Typical container names | Port | Health endpoint |
|---|---|---|---|
| `bge-m3` | `dev-bge-m3-1` (Compose v2+), `dev_bge_m3_1` (legacy) | 8000 | `/health` |
| `bm42` | `dev-bm42` (if configured) | 8000 | `/health` |
| `user-base` | `dev-user-base-1` (Compose v2+), `dev_user_base_1` (legacy) | 8000 | `/health` |
| `ingestion` | `dev-ingestion-1` (Compose v2+), `dev_ingestion_1` (legacy) | - | - |

> For service endpoints, ports, and Compose profiles, see the canonical [`DOCKER.md`](../../DOCKER.md).
> For local development commands and the validation ladder, see [`docs/LOCAL-DEVELOPMENT.md`](../LOCAL-DEVELOPMENT.md).

## Fast-Path Diagnosis (read-only)

Run these commands before deciding whether the issue is a service failure or an application bug.

### 1. Container health and reachability

```bash
# Check embedding service status with deterministic CI env (read-only, no local .env required)
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml ps bge-m3 user-base

# Health check (host-side; dev Compose publishes BGE-M3 REST on localhost:8000)
curl -fsS http://localhost:8000/health
```

Expected: exit code `0` (HTTP 200 OK).
If this fails, treat as **service failure** (container down, OOM, or model not loaded).

### 2. Embedding service logs

```bash
# BGE-M3 logs (last 200 lines)
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs bge-m3 --tail=200

# user-base logs
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs user-base --tail=200
```

Check for:
- OOM killer messages (`Killed`, exit code 137)
- Model loading errors (`RuntimeError`, `torch`, `OutOfMemoryError`)
- CUDA/CPU initialization failures

### 3. Bot logs for retry and failure patterns

```bash
# Check for embedding retries
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs bot --tail=200 | grep -i "Retrying telegram_bot.integrations.embeddings"

# Check for embedding failures after retries exhausted
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs bot --tail=200 | grep -i "Embedding failed after retries"
```

### 4. Ingestion logs for Voyage rate limiting

```bash
# Check for Voyage 429 / rate limit errors
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs ingestion --tail=200 | grep -iE "voyage.*429|rate.*limit"
```

## Service Failure vs App Bug

| Observation | Interpretation | Next step |
|---|---|---|
| `/health` fails from host | Service failure | Check container state, memory, restart service |
| BGE-M3 healthy but bot shows `Connection refused` | App bug | Verify `BGE_M3_URL` env var in bot container |
| Bot retrying but service `/health` returns 200 | Service degraded / slow | Check memory/CPU usage, reduce concurrency |
| `Embedding failed after retries` in bot logs | Service failure | Restart embedding service or scale resources |
| Voyage 429 in ingestion logs | External rate limit | Reduce ingestion batch size, rely on built-in backoff |
| Errors only in `user-base` container | user-base service issue | Restart user-base independently, check its model load |

## Source Paths

| Component | Path |
|---|---|
| Embeddings integration (bot) | [`telegram_bot/integrations/embeddings.py`](../../telegram_bot/integrations/embeddings.py) |
| BGE-M3 client with retry | [`src/services/bge_m3_client.py`](../../src/services/bge_m3_client.py) |
| Retry configuration | [`src/services/_retry.py`](../../src/services/_retry.py) |
| Voyage service | [`src/services/voyage.py`](../../src/services/voyage.py) |
| BGE-M3 API service | [`services/bge-m3-api/`](../../services/bge-m3-api/) |
| Compose service definitions | [`compose.yml`](../../compose.yml) |
| Dev overrides (ports, profiles) | [`compose.dev.yml`](../../compose.dev.yml) |
| Alert rules (infrastructure) | [`docker/monitoring/rules/infrastructure.yaml`](../../docker/monitoring/rules/infrastructure.yaml) |
| Alert rules (ingestion) | [`docker/monitoring/rules/ingestion.yaml`](../../docker/monitoring/rules/ingestion.yaml) |
| CI env fixture | [`tests/fixtures/compose.ci.env`](../../tests/fixtures/compose.ci.env) |

## Logs and Artifacts

| Artifact | Location / command |
|---|---|
| Runtime logs (BGE-M3) | `docker compose logs bge-m3 --tail=200` |
| Runtime logs (user-base) | `docker compose logs user-base --tail=200` |
| Model cache volume | `hf_cache` volume (`HF_HOME=/models/hf` inside container) |
| Langfuse traces | Embedding spans in Langfuse dashboard |
| Alert rules | `docker/monitoring/rules/infrastructure.yaml`, `docker/monitoring/rules/ingestion.yaml` |

## Remediation

> **Caution:** Commands in this section mutate state. Run only after fast-path diagnosis confirms the issue is not an app bug.

### A. BGE-M3 / BM42 Container Down

```bash
# Restart the embedding service
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml restart bge-m3
```

If the container was OOMKilled (exit code 137):

```bash
# Inspect exit status and OOM flag
docker inspect dev-bge-m3-1 --format '
  Name={{.Name}}
  OOMKilled={{.State.OOMKilled}}
  ExitCode={{.State.ExitCode}}
  Status={{.State.Status}}
'
```

If `OOMKilled=true` or `ExitCode=137`, increase the memory limit:

- Default: `BGE_M3_MEMORY_LIMIT=4G`
- Edit `compose.yml` or `compose.dev.yml` to raise `deploy.resources.limits.memory`
- Recreate the container after changing limits:

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml up -d --force-recreate bge-m3
```

**Cold-start note:** BGE-M3 has a `start_period` of 420s (7 minutes) to allow for model download on first run. If the model cache volume (`hf_cache`) is empty, the container will appear unhealthy until the download completes. Ensure the `hf_cache` volume persists across restarts.

### B. Embedding Service Degraded (High Latency)

```bash
# Check resource usage
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml stats bge-m3 user-base
```

To reduce CPU contention, tune threading env vars:

- `OMP_NUM_THREADS` - OpenMP thread count
- `MKL_NUM_THREADS` - Intel MKL thread count

Set these in `compose.dev.yml` or `.env` and restart the service.

### C. Voyage Rate Limiting

If ingestion logs show Voyage API 429 responses:

1. Reduce the ingestion batch size (fewer documents per pipeline run = fewer Voyage API calls)
2. The Voyage client (`src/services/voyage.py`) has built-in retry with exponential backoff (6 attempts, up to 60s wait). In most cases, the backoff will clear the rate window automatically
3. If rate limiting persists across multiple batches, introduce an explicit Voyage concurrency limit or rate-limit wrapper in `VoyageService`
4. Check Voyage API quota and usage dashboard for current limits

> **Note:** `BGE_M3_CONCURRENCY` controls only the local BGE-M3 semaphore and has no effect on Voyage API call rate.

```bash
# Restart ingestion after reducing batch size configuration
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml restart ingestion
```

## Prevention

- Monitor `/health` endpoint on all embedding services
- Alert on missing container logs (already configured via BGEServiceDown/BM42ServiceDown rules)
- Watch for OOM events in container state after deploys or traffic spikes
- Keep the `hf_cache` model cache volume persistent to avoid cold-start downloads on every restart
- Set resource limits (`BGE_M3_MEMORY_LIMIT`) appropriately for the deployment environment
- Monitor Voyage API quota usage to avoid unexpected rate limiting during large ingestion batches

## See Also

- [Qdrant Troubleshooting](QDRANT_TROUBLESHOOTING.md)
- [Redis Cache Degradation](REDIS_CACHE_DEGRADATION.md)
- [VPS Google Drive Ingestion Recovery](vps-gdrive-ingestion-recovery.md)
- [Docker Services Reference](../../DOCKER.md)
- [Local Development Guide](../LOCAL-DEVELOPMENT.md)
