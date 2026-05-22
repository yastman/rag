# Runbook: LightRAG Failure

> **Owner:** Graph RAG / Retrieval extensions
> **Last verified:** 2026-05-22
> **Verification command:**
> ```bash
> COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml ps lightrag
> ```

Use this runbook when LightRAG alerts fire from `docker/monitoring/rules/extended-services.yaml`. LightRAG provides graph-based retrieval; its outages do not stop the bot's primary RAG path but degrade graph-aware answers.

## Covered Alerts

| Alert | Severity | Source |
|---|---|---|
| `LightRAGDown` | critical | [`extended-services.yaml`](../../docker/monitoring/rules/extended-services.yaml) |
| `LightRAGError` | warning | [`extended-services.yaml`](../../docker/monitoring/rules/extended-services.yaml) |
| `LightRAGAPIError` | warning | [`extended-services.yaml`](../../docker/monitoring/rules/extended-services.yaml) |

## Service / Container Map

| Compose service | Typical container names |
|---|---|
| `lightrag` | `dev-lightrag-1`, `dev_lightrag_1` |

> Endpoints, ports, profiles: [`DOCKER.md`](../../DOCKER.md). Local dev: [`docs/LOCAL-DEVELOPMENT.md`](../LOCAL-DEVELOPMENT.md).

## Fast-Path Diagnosis (read-only)

### 1. Container state

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml ps lightrag
docker inspect dev-lightrag-1 --format '
  Name={{.Name}}
  Status={{.State.Status}}
  OOMKilled={{.State.OOMKilled}}
  ExitCode={{.State.ExitCode}}
  Restarts={{.RestartCount}}
'
```

### 2. Bounded log slice

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs lightrag --tail=200
```

Pattern → alert mapping:

| Pattern (case-insensitive) | Alert |
|---|---|
| no logs for 10m | `LightRAGDown` |
| `error`, `exception`, `failed`, `traceback` (rate based) | `LightRAGError` |
| `openai.*error`, `api.*error`, `rate.*limit` | `LightRAGAPIError` |

### 3. Health endpoint (if exposed)

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec lightrag wget -qO- http://localhost:9621/health || true
```

### 4. Upstream LLM contract

LightRAG depends on an LLM/embedding provider for graph extraction. If `LightRAGAPIError` fires:

```bash
# Confirm presence of the env vars LightRAG uses (do not print values)
docker compose exec lightrag sh -lc 'set | grep -E "^(OPENAI_API_KEY|LLM_BASE_URL|EMBEDDING_BASE_URL)=" | sed "s/=.*/=present/"'
```

If the bot uses LiteLLM as the upstream LLM, cross-check with [`LITEllm_FAILURE.md`](LITEllm_FAILURE.md).

## Service Failure vs App Bug

| Observation | Interpretation | Next step |
|---|---|---|
| `LightRAGDown` with `OOMKilled=true` | Service failure (memory) | Raise memory limit in `compose.dev.yml`; recreate |
| `LightRAGDown` after deploy | Service failure (regression) | Roll back image tag |
| `LightRAGError` with `traceback` from query path | App bug | Capture sample query; reproduce locally |
| `LightRAGAPIError` with `429` | Upstream rate limit | Reduce concurrency; verify LiteLLM fallback chain |
| `LightRAGAPIError` with `connection refused` | Network / dependency outage | Check LiteLLM ([`LITEllm_FAILURE.md`](LITEllm_FAILURE.md)) and embedding service ([`EMBEDDING_SERVICE_FAILURE.md`](EMBEDDING_SERVICE_FAILURE.md)) |
| `LightRAGError` only on graph-build path | Data issue | Quarantine offending document; re-run graph extraction |

## Source Paths

| Component | Path |
|---|---|
| Compose definitions | [`compose.yml`](../../compose.yml), [`compose.dev.yml`](../../compose.dev.yml) |
| Alert rules | [`docker/monitoring/rules/extended-services.yaml`](../../docker/monitoring/rules/extended-services.yaml) |
| Bot graph-RAG integration (if any) | search [`telegram_bot/`](../../telegram_bot/) for `lightrag` |

## Logs and Artifacts

| Artifact | Location / command |
|---|---|
| Runtime logs | `docker compose logs lightrag --tail=200` |
| Container metadata | `docker inspect dev-lightrag-1` |
| Graph store volume | `docker volume inspect dev_lightrag_data` (or hyphen variant) |
| Model cache | named volume; review with `docker volume inspect` |

## Remediation

> ⚠️ **Caution:** Mutating commands. Run only after fast-path diagnosis confirms the issue.

### `LightRAGDown`

1. Capture exit reason and last 200 log lines.
2. If `OOMKilled=true`: raise the memory limit in `compose.dev.yml` and recreate.
3. Otherwise:
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml up -d --force-recreate lightrag
   ```
4. Because LightRAG is a graph-RAG accelerator, the bot can run without it. If the outage is prolonged, disable the LightRAG path in the bot config rather than letting users see degraded answers.

### `LightRAGError`

1. Aggregate the most common error class.
2. Distinguish data issues (single-document failures) from systemic issues (every request fails).
3. Apply the matching fix; do not blanket-restart while a single document is the culprit.

### `LightRAGAPIError`

1. If `429`: reduce LightRAG concurrency knobs; coordinate with the upstream LLM owner.
2. If `connection refused` / `timeout`: confirm LiteLLM and embedding services are up before restarting LightRAG.
3. If a recent secret rotation: refresh the LightRAG container's env (presence only) and recreate.

## Prevention

- Treat LightRAG as best-effort: feature-flag the graph path so the bot degrades gracefully when LightRAG is down.
- Keep memory limits with ≥ 30% headroom for graph builds.
- Pin LightRAG image tags via Renovate; review release notes for prompt / API changes before bumping.
- Cap graph-build concurrency in ingestion to stay under upstream LLM quotas.

## See Also

- [`LITEllm_FAILURE.md`](LITEllm_FAILURE.md)
- [`EMBEDDING_SERVICE_FAILURE.md`](EMBEDDING_SERVICE_FAILURE.md)
- [`QDRANT_TROUBLESHOOTING.md`](QDRANT_TROUBLESHOOTING.md)
- [`DOCKER.md`](../../DOCKER.md)
