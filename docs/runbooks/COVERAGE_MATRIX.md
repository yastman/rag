# Alert-to-Runbook Coverage Matrix

Maps every alert from `docker/monitoring/rules/*.yaml` to its resolution status.

**Legend**

| Status | Meaning |
|--------|---------|
| covered | Alert maps directly to an existing runbook addressing its symptoms and resolution |
| gap-accepted | Alert is low-priority or its impact is already addressed by an adjacent runbook |
| gap-to-fill | No existing runbook covers this alert class; a new runbook is needed |

---

## telegram-bot.yaml - Service: bot

| Alert Name | Severity | Service | Runbook | Status | Notes |
|------------|----------|---------|---------|--------|-------|
| BotContainerDown | critical | bot | [TELEGRAM_BOT_FAILURE.md](TELEGRAM_BOT_FAILURE.md) | covered | |
| BotHighErrorRate | warning | bot | [TELEGRAM_BOT_FAILURE.md](TELEGRAM_BOT_FAILURE.md) | covered | |
| BotCriticalError | critical | bot | [TELEGRAM_BOT_FAILURE.md](TELEGRAM_BOT_FAILURE.md) | covered | |
| TelegramAPIError | warning | bot | [TELEGRAM_BOT_FAILURE.md](TELEGRAM_BOT_FAILURE.md) | covered | |
| BotRestarted | info | bot | [TELEGRAM_BOT_FAILURE.md](TELEGRAM_BOT_FAILURE.md) | covered | |
| QueryProcessingError | warning | bot | [TELEGRAM_BOT_FAILURE.md](TELEGRAM_BOT_FAILURE.md) | covered | |
| LLMGenerationError | warning | bot | [LITEllm_FAILURE.md](LITEllm_FAILURE.md) | covered | LLM proxy runbook covers generation errors |
| CacheError | warning | bot | [REDIS_CACHE_DEGRADATION.md](REDIS_CACHE_DEGRADATION.md) | covered | Redis runbook covers cache errors |
| SlowBotResponse | warning | bot | [TELEGRAM_BOT_FAILURE.md](TELEGRAM_BOT_FAILURE.md) | covered | |
| BotMemoryWarning | warning | bot | [TELEGRAM_BOT_FAILURE.md](TELEGRAM_BOT_FAILURE.md) | covered | |

## infrastructure.yaml - Service: qdrant

| Alert Name | Severity | Service | Runbook | Status | Notes |
|------------|----------|---------|---------|--------|-------|
| QdrantDown | critical | qdrant | [QDRANT_TROUBLESHOOTING.md](QDRANT_TROUBLESHOOTING.md) | covered | |
| QdrantError | warning | qdrant | [QDRANT_TROUBLESHOOTING.md](QDRANT_TROUBLESHOOTING.md) | covered | |
| QdrantSlowQuery | warning | qdrant | [QDRANT_TROUBLESHOOTING.md](QDRANT_TROUBLESHOOTING.md) | covered | |

## infrastructure.yaml - Service: redis

| Alert Name | Severity | Service | Runbook | Status | Notes |
|------------|----------|---------|---------|--------|-------|
| RedisDown | critical | redis | [REDIS_CACHE_DEGRADATION.md](REDIS_CACHE_DEGRADATION.md) | covered | |
| RedisMemoryWarning | warning | redis | [REDIS_CACHE_DEGRADATION.md](REDIS_CACHE_DEGRADATION.md) | covered | |
| RedisConnectionError | warning | redis | [REDIS_CACHE_DEGRADATION.md](REDIS_CACHE_DEGRADATION.md) | covered | |

## infrastructure.yaml - Service: litellm

| Alert Name | Severity | Service | Runbook | Status | Notes |
|------------|----------|---------|---------|--------|-------|
| LiteLLMDown | critical | litellm | [LITEllm_FAILURE.md](LITEllm_FAILURE.md) | covered | |
| LiteLLMRateLimited | warning | litellm | [LITEllm_FAILURE.md](LITEllm_FAILURE.md) | covered | |
| LiteLLMProviderError | warning | litellm | [LITEllm_FAILURE.md](LITEllm_FAILURE.md) | covered | |
| LiteLLMFallbackTriggered | info | litellm | [LITEllm_FAILURE.md](LITEllm_FAILURE.md) | covered | |

## infrastructure.yaml - Service: langfuse

| Alert Name | Severity | Service | Runbook | Status | Notes |
|------------|----------|---------|---------|--------|-------|
| LangfuseDown | warning | langfuse | [LANGFUSE_TRACING_GAPS.md](LANGFUSE_TRACING_GAPS.md) | covered | |
| LangfuseWorkerDown | warning | langfuse | [LANGFUSE_TRACING_GAPS.md](LANGFUSE_TRACING_GAPS.md) | covered | |
| LangfuseError | warning | langfuse | [LANGFUSE_TRACING_GAPS.md](LANGFUSE_TRACING_GAPS.md) | covered | |

## infrastructure.yaml - Service: bge-m3 / embeddings

| Alert Name | Severity | Service | Runbook | Status | Notes |
|------------|----------|---------|---------|--------|-------|
| BGEServiceDown | warning | bge-m3 | [EMBEDDING_SERVICE_FAILURE.md](EMBEDDING_SERVICE_FAILURE.md) | covered | |
| BM42ServiceDown | warning | bm42 | [EMBEDDING_SERVICE_FAILURE.md](EMBEDDING_SERVICE_FAILURE.md) | covered | |
| EmbeddingServiceError | warning | embeddings | [EMBEDDING_SERVICE_FAILURE.md](EMBEDDING_SERVICE_FAILURE.md) | covered | |
| BGEEmbedRetryFromBot | warning | bge-m3 | [EMBEDDING_SERVICE_FAILURE.md](EMBEDDING_SERVICE_FAILURE.md) | covered | |
| BGEEmbedErrorFromBot | critical | bge-m3 | [EMBEDDING_SERVICE_FAILURE.md](EMBEDDING_SERVICE_FAILURE.md) | covered | |

## infrastructure.yaml - Service: postgres

| Alert Name | Severity | Service | Runbook | Status | Notes |
|------------|----------|---------|---------|--------|-------|
| PostgresDown | critical | postgres | [POSTGRESQL_WAL_RECOVERY.md](POSTGRESQL_WAL_RECOVERY.md) | covered | |
| PostgresError | warning | postgres | [POSTGRESQL_WAL_RECOVERY.md](POSTGRESQL_WAL_RECOVERY.md) | covered | |

## infrastructure.yaml - Service: clickhouse

| Alert Name | Severity | Service | Runbook | Status | Notes |
|------------|----------|---------|---------|--------|-------|
| ClickHouseDown | warning | clickhouse | [LANGFUSE_TRACING_GAPS.md](LANGFUSE_TRACING_GAPS.md) | gap-accepted | ClickHouse only backs Langfuse analytics; Langfuse runbook covers upstream impact |

## extended-services.yaml - Service: docling

| Alert Name | Severity | Service | Runbook | Status | Notes |
|------------|----------|---------|---------|--------|-------|
| DoclingDown | critical | docling | [DOCLING_FAILURE.md](DOCLING_FAILURE.md) | covered | |
| DoclingOOM | critical | docling | [DOCLING_FAILURE.md](DOCLING_FAILURE.md) | covered | |
| DoclingConversionFailed | warning | docling | [DOCLING_FAILURE.md](DOCLING_FAILURE.md) | covered | |
| DoclingError | warning | docling | [DOCLING_FAILURE.md](DOCLING_FAILURE.md) | covered | |

## extended-services.yaml - Service: minio

| Alert Name | Severity | Service | Runbook | Status | Notes |
|------------|----------|---------|---------|--------|-------|
| MinioDown | critical | minio | [MINIO_FAILURE.md](MINIO_FAILURE.md) | covered | |
| MinioDiskFull | critical | minio | [MINIO_FAILURE.md](MINIO_FAILURE.md) | covered | |
| MinioCorruption | critical | minio | [MINIO_FAILURE.md](MINIO_FAILURE.md) | covered | |
| MinioHealingFailed | warning | minio | [MINIO_FAILURE.md](MINIO_FAILURE.md) | covered | |
| MinioError | warning | minio | [MINIO_FAILURE.md](MINIO_FAILURE.md) | covered | |

## extended-services.yaml - Service: redis-langfuse

| Alert Name | Severity | Service | Runbook | Status | Notes |
|------------|----------|---------|---------|--------|-------|
| RedisLangfuseDown | critical | redis-langfuse | [LANGFUSE_TRACING_GAPS.md](LANGFUSE_TRACING_GAPS.md) | gap-accepted | Langfuse-internal Redis; impact covered by Langfuse runbook |
| RedisLangfuseConnectionError | critical | redis-langfuse | [LANGFUSE_TRACING_GAPS.md](LANGFUSE_TRACING_GAPS.md) | gap-accepted | Langfuse-internal Redis; impact covered by Langfuse runbook |
| RedisLangfuseMemory | warning | redis-langfuse | [LANGFUSE_TRACING_GAPS.md](LANGFUSE_TRACING_GAPS.md) | gap-accepted | Langfuse-internal Redis; impact covered by Langfuse runbook |

## extended-services.yaml - Service: lightrag

| Alert Name | Severity | Service | Runbook | Status | Notes |
|------------|----------|---------|---------|--------|-------|
| LightRAGDown | critical | lightrag | [LIGHTRAG_FAILURE.md](LIGHTRAG_FAILURE.md) | covered | |
| LightRAGError | warning | lightrag | [LIGHTRAG_FAILURE.md](LIGHTRAG_FAILURE.md) | covered | |
| LightRAGAPIError | warning | lightrag | [LIGHTRAG_FAILURE.md](LIGHTRAG_FAILURE.md) | covered | |

## ingestion.yaml - Service: ingestion

| Alert Name | Severity | Service | Runbook | Status | Notes |
|------------|----------|---------|---------|--------|-------|
| IngestionPipelineStalled | warning | ingestion | [vps-gdrive-ingestion-recovery.md](vps-gdrive-ingestion-recovery.md) | covered | |
| IngestionHighFailureRate | warning | ingestion | [vps-gdrive-ingestion-recovery.md](vps-gdrive-ingestion-recovery.md) | covered | |
| IngestionDLQGrowing | warning | ingestion | [vps-gdrive-ingestion-recovery.md](vps-gdrive-ingestion-recovery.md) | covered | |
| DoclingErrors | warning | ingestion | [vps-gdrive-ingestion-recovery.md](vps-gdrive-ingestion-recovery.md) | covered | Also gap-to-fill for service-level in DOCLING_FAILURE.md |
| VoyageRateLimited | warning | ingestion | [EMBEDDING_SERVICE_FAILURE.md](EMBEDDING_SERVICE_FAILURE.md) | covered | Embedding service runbook covers Voyage rate limiting |
| IngestionContainerDown | critical | ingestion | [vps-gdrive-ingestion-recovery.md](vps-gdrive-ingestion-recovery.md) | covered | |

---

## Summary

| Metric | Count |
|--------|-------|
| **Total alerts** | 52 |
| **Covered** | 48 |
| **Gap-accepted** | 4 |
| **Gap-to-fill** | 0 |

### New runbooks needed

| Runbook | Alerts covered |
|---------|---------------|
| _None_ | All non-accepted gaps currently map to runbooks. |
