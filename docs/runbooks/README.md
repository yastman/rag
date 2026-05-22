# Operational Runbooks Index

Operator entrypoint for container/service investigations and incident response. If a Docker service breaks, start here before ad hoc log searching.

## Quick Access

| Operator request | First command / doc |
|---|---|
| Remote Docker workflow (SSH, Colima, env sync, bot container) | See Docker runbook below |
| Native Git/GitHub hygiene | [`GIT_PR_ISSUE_NATIVE.md`](GIT_PR_ISSUE_NATIVE.md) |
| Recent Langfuse traces (Russian: "изучи последние трейсы") | `make validate-traces-fast` → [`LANGFUSE_TRACING_GAPS.md`](LANGFUSE_TRACING_GAPS.md) |
| Qdrant health / query / index issues (Russian: "изучи последние qdrant запросы") | `curl -fsS http://localhost:6333/readyz` → [`QDRANT_TROUBLESHOOTING.md`](QDRANT_TROUBLESHOOTING.md) |
| Redis / cache degradation (Russian: "сломался redis") | `COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec redis sh -lc 'redis-cli -a "$REDIS_PASSWORD" ping'` → [`REDIS_CACHE_DEGRADATION.md`](REDIS_CACHE_DEGRADATION.md) |
| LiteLLM / provider failure (Russian: "сломался litellm") | `curl -s http://localhost:4000/health` → [`LITEllm_FAILURE.md`](LITEllm_FAILURE.md) |
| Compose service health | `make docker-ps` → [`DOCKER.md`](../../DOCKER.md) |
| Self-hosted runner offline / nightly-heavy queued | `scripts/check_self_hosted_runner.sh` → [`SELF_HOSTED_RUNNER.md`](SELF_HOSTED_RUNNER.md) |
| Telegram bot is down / restarting / high error rate | `docker compose ps bot` → [`TELEGRAM_BOT_FAILURE.md`](TELEGRAM_BOT_FAILURE.md) |
| Embedding service (BGE-M3 / BM42 / Voyage) errors | `docker compose ps bge-m3` → [`EMBEDDING_SERVICE_FAILURE.md`](EMBEDDING_SERVICE_FAILURE.md) |
| Docling document parser down / OOM / conversion errors | `docker compose ps docling` → [`DOCLING_FAILURE.md`](DOCLING_FAILURE.md) |
| MinIO object storage down / disk full / corruption | `curl -fsS http://localhost:9000/minio/health/ready` → [`MINIO_FAILURE.md`](MINIO_FAILURE.md) |
| LightRAG graph retrieval down / API errors | `docker compose ps lightrag` → [`LIGHTRAG_FAILURE.md`](LIGHTRAG_FAILURE.md) |

## Start Here

| Symptom / Request | Runbook |
|---|---|
| Remote Docker workflow (SSH, Colima, env sync, bot container) | See Docker runbook below |
| Git/GitHub branch, PR, issue, worktree, and stash hygiene | [`GIT_PR_ISSUE_NATIVE.md`](GIT_PR_ISSUE_NATIVE.md) |
| Langfuse traces missing, gaps, or drift | [`LANGFUSE_TRACING_GAPS.md`](LANGFUSE_TRACING_GAPS.md) |
| LiteLLM / LLM connection failures or proxy errors | [`LITEllm_FAILURE.md`](LITEllm_FAILURE.md) |
| Redis cache degradation, eviction, or latency | [`REDIS_CACHE_DEGRADATION.md`](REDIS_CACHE_DEGRADATION.md) |
| Qdrant health, collection, or vector search issues | [`QDRANT_TROUBLESHOOTING.md`](QDRANT_TROUBLESHOOTING.md) |
| Postgres WAL recovery or replication issues | [`POSTGRESQL_WAL_RECOVERY.md`](POSTGRESQL_WAL_RECOVERY.md) |
| VPS / Google Drive ingestion recovery | [`vps-gdrive-ingestion-recovery.md`](vps-gdrive-ingestion-recovery.md) |
| Self-hosted GitHub Actions runner for `nightly-heavy.yml` is offline | [`SELF_HOSTED_RUNNER.md`](SELF_HOSTED_RUNNER.md) |
| Telegram bot container, Telegram API, or query-processing alerts | [`TELEGRAM_BOT_FAILURE.md`](TELEGRAM_BOT_FAILURE.md) |
| Embedding service (BGE-M3, BM42, Voyage) alerts | [`EMBEDDING_SERVICE_FAILURE.md`](EMBEDDING_SERVICE_FAILURE.md) |
| Docling document parser alerts | [`DOCLING_FAILURE.md`](DOCLING_FAILURE.md) |
| MinIO storage alerts | [`MINIO_FAILURE.md`](MINIO_FAILURE.md) |
| LightRAG graph-retrieval alerts | [`LIGHTRAG_FAILURE.md`](LIGHTRAG_FAILURE.md) |
| Weekly git/pr/issue hygiene workflow | [`GIT_PR_ISSUE_NATIVE.md`](GIT_PR_ISSUE_NATIVE.md) |

## Container / Service Map

| Service (Compose name) | Common container names | Runbook |
|---|---|---|
| `qdrant` | `dev-qdrant-1`, `dev_qdrant_1` | [`QDRANT_TROUBLESHOOTING.md`](QDRANT_TROUBLESHOOTING.md) |
| `redis` (app cache) and cache Redis containers | `dev-redis-1`, `dev_redis_1` | [`REDIS_CACHE_DEGRADATION.md`](REDIS_CACHE_DEGRADATION.md) |
| `langfuse`, `langfuse-worker`, ClickHouse, MinIO, Langfuse Postgres/Redis | `dev-langfuse-1`, `dev-langfuse-worker-1`, `dev-clickhouse-1`, `dev-minio-1` | [`LANGFUSE_TRACING_GAPS.md`](LANGFUSE_TRACING_GAPS.md) |
| `litellm` | `dev-litellm-1`, `dev_litellm_1` | [`LITEllm_FAILURE.md`](LITEllm_FAILURE.md) |
| `postgres` | `dev-postgres-1`, `dev_postgres_1` | [`POSTGRESQL_WAL_RECOVERY.md`](POSTGRESQL_WAL_RECOVERY.md) |
| Ingestion-related services | `dev-ingestion-1`, `dev-docling-1`, `dev-bge-m3-1` | [`vps-gdrive-ingestion-recovery.md`](vps-gdrive-ingestion-recovery.md) |

> **Note:** Container names may differ between Compose versions (`dev-qdrant-1` vs `dev_qdrant_1`). Prefer `docker compose ps` and service names in docs.

## Fast Search Commands

Search runbooks and source areas by topic:

```bash
# Langfuse / traces / observability
rg -n "Langfuse|trace|score|observation" docs/runbooks docs/audits telegram_bot src scripts

# Redis / cache
rg -n "Redis|cache|semantic cache|redis-cli" docs/runbooks telegram_bot src tests

# Qdrant / vectors
rg -n "Qdrant|collection|vector|ColBERT|hybrid" docs/runbooks src telegram_bot tests
```

## Safety Notes

- Use Docker Compose native env handling (`--env-file`, `-f`, `COMPOSE_DISABLE_ENV_FILE=1`).
- Do not print `.env` values in logs or runbooks.
- Prefer read-only checks before restarts, clears, or destructive operations.
- Container names may use hyphens or underscores depending on the Compose version and project name.
