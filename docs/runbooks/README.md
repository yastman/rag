# Operational Runbooks

Operator entrypoint for incident response and service investigations. Start here when an alert fires or a service misbehaves.

## Runbook Index

| Runbook | Scope | Description |
|---------|-------|-------------|
| [EMBEDDING_SERVICE_FAILURE.md](EMBEDDING_SERVICE_FAILURE.md) | Embeddings | BGE-M3, BM42, and Voyage embedding service failures, retries, and rate limiting |
| [GIT_PR_ISSUE_NATIVE.md](GIT_PR_ISSUE_NATIVE.md) | Git / GitHub | Branch, PR, issue, and worktree hygiene |
| [LANGFUSE_TRACING_GAPS.md](LANGFUSE_TRACING_GAPS.md) | Observability | Langfuse missing traces, spans, and scores |
| [LITEllm_FAILURE.md](LITEllm_FAILURE.md) | LLM Proxy | LiteLLM proxy outages, provider errors, fallback routing |
| [POSTGRESQL_WAL_RECOVERY.md](POSTGRESQL_WAL_RECOVERY.md) | Database | PostgreSQL WAL corruption and recovery procedures |
| [QDRANT_TROUBLESHOOTING.md](QDRANT_TROUBLESHOOTING.md) | Vector DB | Qdrant health, collections, and query issues |
| [REDIS_CACHE_DEGRADATION.md](REDIS_CACHE_DEGRADATION.md) | Cache | Redis cache misses, eviction, and connection failures |
| [SELF_HOSTED_RUNNER.md](SELF_HOSTED_RUNNER.md) | CI/CD | GitHub Actions self-hosted runner for nightly-heavy CI |
| [vps-gdrive-ingestion-recovery.md](vps-gdrive-ingestion-recovery.md) | Ingestion | VPS ingestion pipeline and Google Drive sync recovery |

## Coverage & Gaps

See [COVERAGE_MATRIX.md](COVERAGE_MATRIX.md) for a full mapping of every Prometheus alert rule to its resolution runbook, including identified gaps and planned new runbooks.

## Safety Notes

- Use Docker Compose native env handling (`--env-file`, `-f`, `COMPOSE_DISABLE_ENV_FILE=1`).
- Do not print `.env` values in logs or runbooks.
- Prefer read-only checks before restarts, clears, or destructive operations.
- Container names may use hyphens or underscores depending on the Compose version and project name.
