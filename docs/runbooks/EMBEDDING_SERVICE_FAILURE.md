# Runbook: Embedding Service Failure

> **Owner:** Retrieval / Ingestion subsystems
> **Last verified:** 2026-05-22
> **Verification command:**
> ```bash
> curl -fsS http://localhost:8081/health || \
>   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec bge-m3 wget -qO- http://localhost:8000/health
> ```

Use this runbook when alerts from `docker/monitoring/rules/infrastructure.yaml` and `docker/monitoring/rules/ingestion.yaml` fire on the embedding tier (BGE-M3, BM42, Voyage).

## Covered Alerts

| Alert | Severity | Source |
|---|---|---|
| `BGEServiceDown` | warning | [`infrastructure.yaml`](../../docker/monitoring/rules/infrastructure.yaml) |
| `BM42ServiceDown` | warning | [`infrastructure.yaml`](../../docker/monitoring/rules/infrastructure.yaml) |
| `EmbeddingServiceError` | warning | [`infrastructure.yaml`](../../docker/monitoring/rules/infrastructure.yaml) |
| `BGEEmbedRetryFromBot` | warning | [`infrastructure.yaml`](../../docker/monitoring/rules/infrastructure.yaml) |
| `BGEEmbedErrorFromBot` | critical | [`infrastructure.yaml`](../../docker/monitoring/rules/infrastructure.yaml) |
| `VoyageRateLimited` | warning | [`ingestion.yaml`](../../docker/monitoring/rules/ingestion.yaml) |

## Service / Container Map

| Compose service | Typical container names | Role |
|---|---|---|
| `bge-m3` | `dev-bge-m3-1`, `dev_bge_m3_1` | Dense + multivec embeddings (primary) |
| `bm42` | `dev-bm42-1`, `dev_bm42_1` | Sparse embeddings (when enabled) |
| `user-base` | `dev-user-base-1` | Auxiliary embedding cache; bundled in the embedding family alert |
| Voyage (external) | n/a — third-party API used by ingestion | Reranker / fallback embeddings |

## Fast-Path Diagnosis (read-only)

### 1. Container state

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml ps bge-m3 bm42 user-base
```

If a container is `Exited`/`Restarting`, capture the exit reason:

```bash
docker inspect dev-bge-m3-1 --format '
  Name={{.Name}}
  Status={{.State.Status}}
  OOMKilled={{.State.OOMKilled}}
  ExitCode={{.State.ExitCode}}
  Restarts={{.RestartCount}}
'
```

### 2. Bounded log slice

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs bge-m3 --tail=200
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs bm42 --tail=200
```

Patterns the alerts watch for:

| Pattern (case-insensitive) | Alert |
|---|---|
| no logs in last 10m | `BGEServiceDown` / `BM42ServiceDown` |
| `error`, `failed`, `exception` (across embedding family) | `EmbeddingServiceError` |
| `Retrying telegram_bot.integrations.embeddings` (in `dev-bot`) | `BGEEmbedRetryFromBot` |
| `Embedding failed after retries` (in `dev-bot`) | `BGEEmbedErrorFromBot` |
| `voyage.*429`, `rate.*limit` (in `dev-ingestion`) | `VoyageRateLimited` |

### 3. Health endpoint

```bash
# Host-side dev mapping if exposed
curl -fsS http://localhost:8081/health || true

# Inside the network
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec bge-m3 wget -qO- http://localhost:8000/health
```

### 4. Cross-check from the bot

```bash
make test-bot-health
```

If `bge_embed_error` rate from the bot is non-zero, `BGEEmbedErrorFromBot` is essentially fact-of-life until embeddings recover.

## Service Failure vs App Bug

| Observation | Interpretation | Next step |
|---|---|---|
| `BGEServiceDown` with `OOMKilled=true` | Service failure (memory) | Raise `BGE_M3_MEMORY_LIMIT`; inspect input batch sizes |
| Container alive, `EmbeddingServiceError` rising | Service failure (model load) | Check model cache volume; restart container after capturing logs |
| `BGEEmbedRetryFromBot` only, no service-side errors | App bug / network glitch | Inspect bot `httpx` config; rule out DNS issues inside Docker network |
| `BGEEmbedErrorFromBot` with healthy `bge-m3` | App bug | Check `EMBEDDING_BASE_URL` / collection alignment in bot env |
| `VoyageRateLimited` repeating | App bug / config | Reduce ingestion concurrency; rotate to local BGE-M3 fallback if Voyage is non-essential |
| `BM42ServiceDown` while bot is fine | Sparse-only outage | Sparse path may be optional; check `SPARSE_PROVIDER` flag before paging |

## Source Paths

| Component | Path |
|---|---|
| BGE-M3 service | [`services/bge-m3-api/`](../../services/bge-m3-api/) |
| Bot embeddings client | [`telegram_bot/integrations/embeddings.py`](../../telegram_bot/integrations/embeddings.py) |
| Reranker / Voyage usage | [`src/retrieval/reranker.py`](../../src/retrieval/reranker.py) |
| Compose definitions | [`compose.yml`](../../compose.yml), [`compose.dev.yml`](../../compose.dev.yml) |
| Alert rules | [`docker/monitoring/rules/infrastructure.yaml`](../../docker/monitoring/rules/infrastructure.yaml), [`docker/monitoring/rules/ingestion.yaml`](../../docker/monitoring/rules/ingestion.yaml) |

## Logs and Artifacts

| Artifact | Location / command |
|---|---|
| BGE-M3 logs | `docker compose logs bge-m3 --tail=200` |
| BM42 logs | `docker compose logs bm42 --tail=200` |
| Bot retry counters | `bge_embed_error`, `bge_embed_latency_ms`, `bge_model_processing_ms` Langfuse scores (see [`docs/RAG_QUALITY_SCORES.md`](../RAG_QUALITY_SCORES.md)) |
| Voyage rate-limit hits | `docker compose logs ingestion --tail=200 | grep -iE "voyage.*429|rate.*limit"` |

## Remediation

> ⚠️ **Caution:** Mutating commands. Run only after fast-path diagnosis confirms the issue.

### `BGEServiceDown` / `BM42ServiceDown`

1. Capture exit reason and last 200 log lines.
2. If `OOMKilled=true`: raise the relevant memory limit (`BGE_M3_MEMORY_LIMIT` for `bge-m3`) in `compose.dev.yml`, then:
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml up -d --force-recreate bge-m3
   ```
3. If model cache is corrupt: stop the service, prune its named volume, and restart so the model re-downloads.

### `EmbeddingServiceError`

1. Identify which container the errors come from (alert query covers `dev-bge-m3|dev-bm42|dev-user-base`).
2. Look for repeated patterns: missing model file, CUDA/CPU mismatch, timeouts.
3. Apply the matching service fix; do **not** restart the bot until embeddings recover, or it will retry-storm.

### `BGEEmbedRetryFromBot`

1. If the underlying service is healthy, this is usually network/DNS jitter.
2. Confirm `EMBEDDING_BASE_URL` (presence only) points at the in-network service name (`http://bge-m3:8000`), not the host port.
3. Increase `httpx` retry/backoff in the bot config only if retries are persistently failing.

### `BGEEmbedErrorFromBot`

Critical. Bot embedding calls have exhausted retries and are surfacing failures to users.

1. Pin the bge-m3 health and bot health side-by-side. If both are up, the issue is contractual (URL/keys).
2. Roll back to the last known-good `bge-m3` image tag if a recent deploy correlates.
3. Engage on-call before users notice degraded retrieval.

### `VoyageRateLimited`

1. Reduce ingestion concurrency: lower `INGEST_CONCURRENCY` (or the equivalent CocoIndex / unified flow knob).
2. If Voyage is optional, switch to local BGE-M3 fallback for ingestion.
3. Coordinate with the API key owner before bumping the Voyage tier.

### Canonical bge-m3 endpoint forwarding stuck on port 8000 (#2188 / #2182)

> **Symptom:** `make bot` preflight fails with
> `Preflight FAIL: bge_m3 [CRITICAL] ... Unreachable after 3 attempts: bge_m3`,
> `curl http://localhost:8000/health` returns `Connection refused`, and
> `docker compose ... ps bge-m3` shows no `dev-bge-m3-1` container — even
> though the image is healthy and the model cache is warm. Tracked under
> #2188; the upstream Docker Desktop port-forwarding-API stall is #2182.

In this state operators commonly side-load a temporary container as a
workaround:

```bash
# Workaround only — bge-m3-tmp binds 127.0.0.1:8888 -> container :8000
docker run -d --rm --name bge-m3-tmp \
  -p 127.0.0.1:8888:8000 \
  -v dev_hf_cache:/models \
  dev_bge-m3
# .env (workaround line — must be removed after canonical restore):
#   BGE_M3_URL=http://localhost:8888
```

The workaround unblocks `make bot` but leaves the canonical endpoint
broken. Use the steps below to restore canonical `127.0.0.1:8000`
forwarding so the side-load and the `.env` override can be retired.

#### 1. Confirm the failure mode

```bash
# Canonical port should be free; canonical service should be missing.
ss -lntp | awk '$4 ~ /:8000$|:8888$/ {print}'
docker compose --env-file .env -f compose.yml -f compose.dev.yml ps bge-m3
docker ps --filter name=bge-m3 --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
curl -fsS --max-time 3 http://localhost:8000/health || echo "canonical endpoint down"
```

If the workaround container `bge-m3-tmp` shows up on `127.0.0.1:8888`
and `dev-bge-m3-1` is missing from `compose ps`, you are in the #2188
state and the recovery below applies.

#### 2. Restart Docker forwarding

```bash
# macOS (Docker Desktop)
osascript -e 'quit app "Docker"' && open -a Docker
# Linux (Docker Engine)
sudo systemctl restart docker
# Windows (Docker Desktop)
# Restart Docker Desktop from the tray icon, or:
#   wsl --shutdown && start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
```

Wait for the daemon to come back (`docker info` succeeds) before moving on.

#### 3. Stop the workaround container

```bash
docker stop bge-m3-tmp 2>/dev/null || true
docker rm   bge-m3-tmp 2>/dev/null || true
ss -lntp | awk '$4 ~ /:8000$|:8888$/ {print}'   # both ports should now be free
```

#### 4. Recreate the canonical compose service

```bash
docker compose --env-file .env -f compose.yml -f compose.dev.yml up -d --force-recreate --no-deps bge-m3
docker compose --env-file .env -f compose.yml -f compose.dev.yml ps bge-m3
```

The first cold start can take several minutes while the model download
completes; the compose healthcheck has a `start_period: 420s` budget.

#### 5. Verify the canonical endpoint

```bash
curl -fsS http://localhost:8000/health
curl -fsS -X POST http://localhost:8000/encode/dense \
  -H 'content-type: application/json' \
  -d '{"texts": ["recovery probe"], "max_length": 64, "batch_size": 1}' | head -c 200
```

Both calls must succeed before continuing.

#### 6. Remove the `.env` workaround override

Edit `.env` and delete the temporary line plus its workaround comment so
the bot picks up the canonical compose-internal default
(`http://bge-m3:8000` for compose runs; `http://localhost:8000` for
native bot runs):

```diff
- # Workaround: Docker Desktop forwards-API stuck on port 8000 (issue #2182).
- # Temp bge-m3 container is bound to 8888. Remove this line after Docker daemon
- # restart + `docker compose up -d --force-recreate --no-deps bge-m3`.
- BGE_M3_URL=http://localhost:8888
```

`.env.example` documents the canonical default
(`# BGE_M3_URL=http://localhost:8000`) — leave it commented out for
local dev.

#### 7. Re-validate the bot path

```bash
make test-bot-health
make bot   # expect "Startup verdict: OK" without referencing port 8888
```

If `make test-bot-health` still flags `bge_m3`, repeat steps 1-5 with
fresh diagnostics — do not re-introduce the `8888` override or the
`bge-m3-tmp` container, or #2188 will silently recur.

## Prevention

- Pre-warm the BGE-M3 model on container start so the first request after deploy is not slow.
- Keep memory limits with ≥ 30% headroom; review after model upgrades.
- Track `bge_embed_error` and `bge_embed_latency_ms` Langfuse scores; alert thresholds in [`docs/RAG_QUALITY_SCORES.md`](../RAG_QUALITY_SCORES.md).
- For Voyage, cap ingestion concurrency in `Makefile` / `scripts/ingest_*.sh` to stay under quota.

## See Also

- [`TELEGRAM_BOT_FAILURE.md`](TELEGRAM_BOT_FAILURE.md)
- [`QDRANT_TROUBLESHOOTING.md`](QDRANT_TROUBLESHOOTING.md)
- [`vps-gdrive-ingestion-recovery.md`](vps-gdrive-ingestion-recovery.md)
- [`docs/RAG_QUALITY_SCORES.md`](../RAG_QUALITY_SCORES.md)
- [`DOCKER.md`](../../DOCKER.md)
