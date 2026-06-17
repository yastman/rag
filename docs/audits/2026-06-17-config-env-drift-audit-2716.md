# Config and Environment Drift Audit (#2716)

Date: 2026-06-17
Scanner: `tests/contract/test_env_example_completeness_contract.py`

## Summary

- **Stale keys removed from `.env.example`**: 2 (`USE_CONTEXTUALIZED_EMBEDDINGS`, `CONTEXTUALIZED_EMBEDDING_DIM`)
- **Config owners**: `src/config/settings.py` (core pipeline), `telegram_bot/config.py` (`BotConfig`, bot adapter)
- **Contract test state after fix**: all 5 tests pass

---

## Classification Table

| Key / field | Owner | Where defined | Where read | Classification | Action |
|---|---|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | BotConfig | `.env.example`, compose.yml bot | `telegram_bot/config.py` | core required (bot profile) | none |
| `ENV` | Settings | `.env.example` | `src/config/settings.py` | core optional | none |
| `DEBUG` | Settings | `.env.example` | `src/config/settings.py` | core optional | none |
| `LOG_LEVEL` | logging | `.env.example` | `telegram_bot/logging_config.py` | core optional | none |
| `LOG_FORMAT` | logging | `.env.example` | `telegram_bot/logging_config.py` | core optional | none |
| `LOG_FILE` | logging | `.env.example` | `telegram_bot/logging_config.py` | core optional | none |
| `ADMIN_IDS` | BotConfig | `.env.example` | `telegram_bot/config.py` | core optional | none |
| `OPENAI_API_KEY` | Settings + BotConfig | `.env.example` | both config classes | core required (LLM) | shared key, both owners documented |
| `ANTHROPIC_API_KEY` | Settings | `.env.example` | `src/config/settings.py` | core optional (alt provider) | none |
| `GROQ_API_KEY` | Settings | `.env.example` | `src/config/settings.py` | core optional (alt provider) | none |
| `CEREBRAS_API_KEY` | BotConfig | `.env.example` | `telegram_bot/config.py` via `LLM_API_KEY` alias | core optional (alt provider) | none |
| `LLM_MODEL` | BotConfig | `.env.example` | `telegram_bot/config.py` | core required (bot) | none |
| `LLM_API_KEY` | BotConfig | `.env.example` | `telegram_bot/config.py` (alias for CEREBRAS_API_KEY) | compatibility alias | comment updated in .env.example |
| `LLM_BASE_URL` | BotConfig | `.env.example` | `telegram_bot/config.py` | deprecated compat alias | `llm_base_url=""` field has comment: "Deprecated; unused by SDK router" |
| `LLM_PROVIDER` | BotConfig | `.env.example` | `telegram_bot/config.py` / runtime | core optional | none |
| `LLM_TIMEOUT_SECONDS` | bot runtime | `.env.example` | `telegram_bot/` | core optional | none |
| `LLM_TEMPERATURE` | Settings/bot | `.env.example` | config | core optional | none |
| `LLM_MAX_TOKENS` | Settings | `.env.example` | `src/config/settings.py` | core optional | none |
| `GENERATE_MAX_TOKENS` | bot compose | `.env.example`, compose.yml | `telegram_bot/` | core optional | none |
| `MODEL_NAME` | Settings | `.env.example` | `src/config/settings.py` | core optional (alias) | allowlisted in contract |
| `API_PROVIDER` | Settings | `.env.example` | `src/config/settings.py` | core optional (helper scripts) | none |
| `SUPERVISOR_MODEL` | BotConfig | `.env.example` | `telegram_bot/config.py` | core optional | none |
| `SUPERVISOR_MAX_TOKENS` | BotConfig | `.env.example` | `telegram_bot/config.py` | core optional | none |
| `APARTMENT_EXTRACTION_MODEL` | BotConfig | `.env.example` | `telegram_bot/config.py` | optional (domain module) | allowlisted in contract |
| `MAX_LLM_CALLS` | BotConfig | `.env.example` | `telegram_bot/config.py` | core optional | none |
| `MAX_TOOL_CALLS` | BotConfig | `.env.example` | `telegram_bot/config.py` | core optional | none |
| `MAX_REWRITE_ATTEMPTS` | bot runtime | `.env.example` | `telegram_bot/` | core optional | none |
| `REWRITE_MODEL` | bot | `.env.example` | `telegram_bot/` | core optional | none |
| `REWRITE_MAX_TOKENS` | bot | `.env.example` | `telegram_bot/` | core optional | none |
| `QDRANT_URL` | Settings + BotConfig | `.env.example`, compose.yml | both | core required | shared key, both owners |
| `QDRANT_API_KEY` | Settings + BotConfig | `.env.example` | both | core optional | shared key |
| `QDRANT_COLLECTION` | BotConfig | `.env.example`, compose.yml | `telegram_bot/config.py` | core required (bot) | none |
| `QDRANT_HISTORY_COLLECTION` | BotConfig | `.env.example` | `telegram_bot/config.py` | core optional | none |
| `QDRANT_TIMEOUT` | BotConfig | `.env.example` | `telegram_bot/config.py` | core optional | none |
| `QDRANT_QUANTIZATION_MODE` | BotConfig | `.env.example` | `telegram_bot/config.py` | core optional | none |
| `QDRANT_USE_QUANTIZATION` | BotConfig | `.env.example` | `telegram_bot/config.py` | core optional | none |
| `QDRANT_QUANTIZATION_RESCORE` | BotConfig | `.env.example` | `telegram_bot/config.py` | core optional | none |
| `QDRANT_QUANTIZATION_OVERSAMPLING` | BotConfig | `.env.example` | `telegram_bot/config.py` | core optional | none |
| `QDRANT_QUANTIZATION_ALWAYS_RAM` | BotConfig | `.env.example` | `telegram_bot/config.py` | core optional | none |
| `QUANTIZATION_MODE` | Settings | `.env.example` | `src/config/settings.py` | core optional (src only) | separate from QDRANT_QUANTIZATION_MODE |
| `QUANTIZATION_RESCORE` | Settings | `.env.example` | `src/config/settings.py` | core optional (src only) | none |
| `QUANTIZATION_OVERSAMPLING` | Settings | `.env.example` | `src/config/settings.py` | core optional (src only) | none |
| `REDIS_URL` | BotConfig | `.env.example` | `telegram_bot/config.py` | core required (bot) | none |
| `REDIS_PASSWORD` | BotConfig + compose | `.env.example`, compose.yml | both | core required | none |
| `REDIS_MAXMEMORY` | compose | `.env.example`, compose.yml redis CMD | not Python | compose-only | in ALLOWLIST_NOT_IN_CODE |
| `BGE_M3_URL` | BotConfig | `.env.example` | `telegram_bot/config.py` | core optional | none |
| `BGE_M3_TIMEOUT` | bot | `.env.example` | `telegram_bot/` | core optional | none |
| `BGE_M3_BATCH_SIZE` | bge service | `.env.example` | `services/bge-m3-api/` | service-local only | none |
| `BGE_M3_MAX_LENGTH` | bge service | `.env.example` | `services/bge-m3-api/` | service-local only | none |
| `BGE_M3_MODEL` | bge service | `.env.example` | `services/bge-m3-api/` | service-local only | none |
| `BGE_M3_USE_FP16` | bge service | `.env.example` | `services/bge-m3-api/` | service-local only | none |
| `BGE_M3_MAX_CONCURRENCY` | bge service | `.env.example` | `services/bge-m3-api/` | service-local only | none |
| `BGE_M3_ONNX_MODEL_HOST_DIR` | compose build | `.env.example` | compose.yml build context | compose-only | in ALLOWLIST_NOT_IN_CODE |
| `ONNX_MODEL_DIR` | bge service | `.env.example` | `services/bge-m3-api/` | service-local only | none |
| `EMBEDDINGS_PROVIDER` | bot | `.env.example` | `telegram_bot/` | core optional | none |
| `RETRIEVAL_DENSE_PROVIDER` | BotConfig | `.env.example` | `telegram_bot/config.py` | core optional | none |
| `RERANK_PROVIDER` | BotConfig | `.env.example` | `telegram_bot/config.py` | core optional | none |
| `RERANK_TOP_K` | BotConfig | `.env.example` | `telegram_bot/config.py` | core optional | none |
| `RERANK_CANDIDATES_MAX` | BotConfig | `.env.example` | `telegram_bot/config.py` | core optional | none |
| `COLBERT_TIMEOUT` | bot | `.env.example` | `telegram_bot/` | core optional | none |
| `COLBERT_COVERAGE_WARN_THRESHOLD` | bot | `.env.example` | `telegram_bot/` | core optional | none |
| `SKIP_RERANK_THRESHOLD` | bot | `.env.example` | `telegram_bot/` | core optional | none |
| `SEARCH_TOP_K` | BotConfig | `.env.example` | `telegram_bot/config.py` | core optional | none |
| `SEARCH_ENGINE` | Settings | `.env.example` | `src/config/settings.py` | core optional (src) | none |
| `HYBRID_DENSE_WEIGHT` | BotConfig | `.env.example` | `telegram_bot/config.py` | core optional | none |
| `HYBRID_SPARSE_WEIGHT` | BotConfig | `.env.example` | `telegram_bot/config.py` | core optional | none |
| `RELEVANCE_THRESHOLD_RRF` | bot | `.env.example` | `telegram_bot/` | core optional | none |
| `SEMANTIC_CACHE_THRESHOLD` | BotConfig | `.env.example` | `telegram_bot/config.py` | core optional | none |
| `SEMANTIC_CACHE_TTL_DEFAULT` | BotConfig | `.env.example` | `telegram_bot/config.py` | core optional | none |
| `ENABLE_CACHING` | Settings | `.env.example` | `src/config/settings.py` | core optional (src) | none |
| `ENABLE_QUERY_EXPANSION` | Settings | `.env.example` | `src/config/settings.py` | core optional (src) | none |
| `ENABLE_LANGFUSE` | Settings | `.env.example` | `src/config/settings.py` | core optional | none |
| `LANGFUSE_ENABLED` | bot | `.env.example` | `telegram_bot/` | core optional (alias) | ENABLE_LANGFUSE / LANGFUSE_ENABLED overlap; both read |
| `LANGFUSE_TRACING_ENABLED` | bot | `.env.example` | `telegram_bot/` | core optional (alias) | same toggle, different key |
| `USE_HYDE` | Settings + BotConfig | `.env.example` | both | core optional | shared key |
| `HYDE_MIN_WORDS` | Settings + BotConfig | `.env.example` | both | core optional | shared key |
| `SMALL_TO_BIG_MODE` | Settings + BotConfig | `.env.example` | both | core optional | shared key |
| `SMALL_TO_BIG_WINDOW_BEFORE` | Settings + BotConfig | `.env.example` | both | core optional | shared key |
| `SMALL_TO_BIG_WINDOW_AFTER` | Settings + BotConfig | `.env.example` | both | core optional | shared key |
| `MAX_EXPANDED_CHUNKS` | Settings + BotConfig | `.env.example` | both | core optional | shared key |
| `MAX_CONTEXT_TOKENS` | Settings + BotConfig | `.env.example` | both | core optional | shared key |
| `CLIENT_DIRECT_PIPELINE_ENABLED` | BotConfig | `.env.example` | `telegram_bot/config.py` | core optional | none |
| `STREAMING_ENABLED` | bot | `.env.example` | `telegram_bot/` | core optional | none |
| `GUARD_MODE` | BotConfig | `.env.example` | `telegram_bot/config.py` | core optional | none |
| `CONTENT_FILTER_ENABLED` | BotConfig | `.env.example` | `telegram_bot/config.py` | core optional | none |
| `ENABLE_OFF_TOPIC_DETECTION` | BotConfig | `.env.example` | `telegram_bot/config.py` | core optional | none |
| `ENABLE_CONFIDENCE_SCORING` | BotConfig | `.env.example` | `telegram_bot/config.py` | core optional | none |
| `LOW_CONFIDENCE_THRESHOLD` | BotConfig | `.env.example` | `telegram_bot/config.py` | core optional | none |
| `CLASSIFIER_MODE` | bot | `.env.example` | `telegram_bot/` | core optional | none |
| `SHOW_SOURCES` | bot | `.env.example` | `telegram_bot/` | core optional | none |
| `SHOW_TRANSCRIPTION` | BotConfig | `.env.example` | `telegram_bot/config.py` | optional profile (voice) | none |
| `RESPONSE_STYLE_ENABLED` | bot | `.env.example` | `telegram_bot/` | core optional | none |
| `RESPONSE_STYLE_SHADOW_MODE` | bot | `.env.example` | `telegram_bot/` | core optional | none |
| `POSTGRES_PASSWORD` | compose | `.env.example`, compose.yml | not Python directly | compose-only | in ALLOWLIST_NOT_IN_CODE |
| `INGESTION_DATABASE_URL` | ingestion | `.env.example` | `src/ingestion/` | optional profile (ingest) | none |
| `GDRIVE_SYNC_DIR` | ingestion | `.env.example` | `src/ingestion/` | optional profile (ingest) | none |
| `GDRIVE_COLLECTION_NAME` | ingestion | `.env.example` | `src/ingestion/` | optional profile (ingest) | none |
| `DOCLING_URL` | ingestion | `.env.example` | `src/ingestion/` | optional profile (ingest) | none |
| `REALESTATE_DATABASE_URL` | BotConfig | `.env.example`, compose.yml | `telegram_bot/config.py` | optional (domain module) | domain-specific |
| `LANGFUSE_PUBLIC_KEY` | BotConfig | `.env.example` | `telegram_bot/config.py` | optional profile (ml) | none |
| `LANGFUSE_SECRET_KEY` | BotConfig | `.env.example` | `telegram_bot/config.py` | optional profile (ml) | none |
| `LANGFUSE_HOST` | BotConfig | `.env.example` | `telegram_bot/config.py` | optional profile (ml) | none |
| `LANGFUSE_DOCKER_HOST` | compose | `.env.example` | not Python | compose-only | in ALLOWLIST_NOT_IN_CODE |
| `LANGFUSE_REDIS_PASSWORD` | compose | `.env.example` | not Python | compose-only | in ALLOWLIST_NOT_IN_CODE |
| `LANGFUSE_RELEASE` | observability | `.env.example` | `telegram_bot/` | optional profile (ml) | none |
| `LANGFUSE_TRACING_ENVIRONMENT` | observability | `.env.example` | `telegram_bot/` | optional profile (ml) | none |
| `LANGFUSE_FLUSH_AT` | observability | `.env.example` | `telegram_bot/` | optional profile (ml) | none |
| `LANGFUSE_FLUSH_INTERVAL` | observability | `.env.example` | `telegram_bot/` | optional profile (ml) | none |
| `LANGFUSE_BASE_URL` | legacy | `.env.example` | not Python (legacy alias) | compatibility alias | in ALLOWLIST_NOT_IN_CODE |
| `NEXTAUTH_SECRET` | Langfuse service | `.env.example` | Langfuse image only | optional profile (ml) | in ALLOWLIST_NOT_IN_CODE |
| `SALT` | Langfuse service | `.env.example` | Langfuse image only | optional profile (ml) | in ALLOWLIST_NOT_IN_CODE |
| `ENCRYPTION_KEY` | Langfuse service | `.env.example` | Langfuse image only | optional profile (ml) | in ALLOWLIST_NOT_IN_CODE |
| `CLICKHOUSE_PASSWORD` | ClickHouse | `.env.example` | ClickHouse image only | optional profile (ml) | in ALLOWLIST_NOT_IN_CODE |
| `MINIO_ROOT_PASSWORD` | MinIO | `.env.example` | MinIO image only | optional profile (ml) | in ALLOWLIST_NOT_IN_CODE |
| `MINIO_API_PORT` | compose | `.env.example` | compose.dev.yml port mapping | optional profile (ml) | in ALLOWLIST_NOT_IN_CODE |
| `MINIO_CONSOLE_PORT` | compose | `.env.example` | compose.dev.yml port mapping | optional profile (ml) | in ALLOWLIST_NOT_IN_CODE |
| `OTEL_SERVICE_NAME` | observability | `.env.example` | `telegram_bot/` | optional profile (obs) | none |
| `OTEL_PROPAGATORS` | OTel SDK | `.env.example` | OTel SDK env (not Python) | optional profile (obs) | in ALLOWLIST_NOT_IN_CODE |
| `LIVEKIT_URL` | BotConfig | `.env.example` | `telegram_bot/config.py` | optional profile (voice) | none |
| `LIVEKIT_API_KEY` | BotConfig | `.env.example` | `telegram_bot/config.py` | optional profile (voice) | none |
| `LIVEKIT_API_SECRET` | BotConfig | `.env.example` | `telegram_bot/config.py` | optional profile (voice) | none |
| `SIP_TRUNK_ID` | BotConfig | `.env.example` | `telegram_bot/config.py` | optional profile (voice) | none |
| `STT_MODEL` | BotConfig | `.env.example` | `telegram_bot/config.py` | optional profile (voice) | none |
| `VOICE_LANGUAGE` | BotConfig | `.env.example` | `telegram_bot/config.py` | optional profile (voice) | none |
| `ELEVENLABS_API_KEY` | voice agent | `.env.example` | voice agent SDK env_file | optional profile (voice) | in ALLOWLIST_NOT_IN_CODE |
| `RAG_API_URL` | voice | `.env.example` | `src/voice/` or `src/api/` | optional profile (voice) | none |
| `MANAGER_IDS` | BotConfig | `.env.example` | `telegram_bot/config.py` | optional (domain module) | domain-specific |
| `MANAGERS_GROUP_ID` | BotConfig | `.env.example` | `telegram_bot/config.py` | optional (domain module) | domain-specific |
| `HANDOFF_ENABLED` | BotConfig | `.env.example` | `telegram_bot/config.py` | optional (domain module) | domain-specific |
| `HANDOFF_TTL_HOURS` | BotConfig | `.env.example` | `telegram_bot/config.py` | optional (domain module) | domain-specific |
| `HANDOFF_SUMMARY_MIN_MESSAGES` | BotConfig | `.env.example` | `telegram_bot/config.py` | optional (domain module) | domain-specific |
| `HANDOFF_WAIT_TIMEOUT_MIN` | BotConfig | `.env.example` | `telegram_bot/config.py` | optional (domain module) | domain-specific |
| `BUSINESS_HOURS_START` | BotConfig | `.env.example` | `telegram_bot/config.py` | optional (domain module) | domain-specific |
| `BUSINESS_HOURS_END` | BotConfig | `.env.example` | `telegram_bot/config.py` | optional (domain module) | domain-specific |
| `BUSINESS_HOURS_TZ` | BotConfig | `.env.example` | `telegram_bot/config.py` | optional (domain module) | domain-specific |
| `HISTORY_RELEVANCE_THRESHOLD` | BotConfig | `.env.example` | `telegram_bot/config.py` | core optional | none |
| `TELEGRAM_API_ID` | E2E tests | `.env.example` | `tests/e2e/` | archived surface (Telethon) | none |
| `TELEGRAM_API_HASH` | E2E tests | `.env.example` | `tests/e2e/` | archived surface (Telethon) | none |
| `E2E_BOT_USERNAME` | E2E tests | `.env.example` | `tests/e2e/` | archived surface (Telethon) | none |
| `E2E_VOICE_NOTE_PATH` | E2E tests | `.env.example` | `tests/e2e/` | optional (test fixture) | none |
| `TELEGRAM_ALERTING_BOT_TOKEN` | alerting | `.env.example` | alerting webhook/Loki | optional (obs) | in ALLOWLIST_NOT_IN_CODE |
| `TELEGRAM_ALERTING_CHAT_ID` | alerting | `.env.example` | alerting webhook/Loki | optional (obs) | in ALLOWLIST_NOT_IN_CODE |
| `MLFLOW_TRACKING_URI` | MLflow | `.env.example` | mlflow CLI only | optional (eval) | in ALLOWLIST_NOT_IN_CODE |
| `MINI_APP_URL` | BotConfig | `.env.example` | `telegram_bot/config.py` | archived surface (mini app) | none |
| `BOT_DOMAIN` | BotConfig | `.env.example` | `telegram_bot/config.py` | optional (domain module) | domain-specific |
| `BOT_LANGUAGE` | BotConfig | `.env.example` | `telegram_bot/config.py` | optional (domain module) | domain-specific |
| `TOKENIZERS_PARALLELISM` | bge/HF | `.env.example` | `services/` + `telegram_bot/` | service-local only | none |
| `OMP_NUM_THREADS` | bge | `.env.example` | `services/bge-m3-api/` + compose.yml | service-local only | none |
| `TTFT_DRIFT_WARN_MS` | bot metrics | `.env.example` | `telegram_bot/` | core optional | none |
| `REASONING_EFFORT` | bot LLM | `.env.example` | `telegram_bot/` | core optional | none |
| `REASONING_FORMAT` | bot LLM | `.env.example` | `telegram_bot/` | core optional | none |
| `DISABLE_REASONING` | bot LLM | `.env.example` | `telegram_bot/` | core optional | none |
| `BOT_START_MAX_ATTEMPTS` | bot | `.env.example` | `telegram_bot/` | core optional | none |
| `BOT_START_RETRY_DELAY_SEC` | bot | `.env.example` | `telegram_bot/` | core optional | none |
| `BOT_START_RETRY_MAX_SEC` | bot | `.env.example` | `telegram_bot/` | core optional | none |
| `COMPOSE_FILE` | docker compose | `.env.example` | compose CLI only | compose-only | in ALLOWLIST_NOT_IN_CODE |
| `COMPOSE_PROJECT_NAME` | docker compose | `.env.example` | compose CLI only | compose-only | in ALLOWLIST_NOT_IN_CODE |
| `REDIS_HOST` | compose | `.env.example` | not Python | compose-only | in ALLOWLIST_NOT_IN_CODE |
| `REDIS_PORT` | compose | `.env.example` | not Python | compose-only | in ALLOWLIST_NOT_IN_CODE |
| `OPENAI_BASE_URL` | OpenAI SDK | `.env.example` | OpenAI SDK env, not Python | eval/optional | in ALLOWLIST_NOT_IN_CODE |
| `EVAL_LLM_API_KEY` | eval | `.env.example` | eval extras only | optional (eval) | in ALLOWLIST_NOT_IN_CODE |
| `EVAL_LLM_BASE_URL` | eval | `.env.example` | eval extras only | optional (eval) | in ALLOWLIST_NOT_IN_CODE |
| `QDRANT_BACKUP_DIR` | scripts | `.env.example` | `scripts/` shell | optional (ops) | none |
| `USE_CONTEXTUALIZED_EMBEDDINGS` | — | ~~`.env.example`~~ | none | **stale/dead** | **removed from .env.example** |
| `CONTEXTUALIZED_EMBEDDING_DIM` | — | ~~`.env.example`~~ | none | **stale/dead** | **removed from .env.example** |

---

## Issues Found

### Stale Keys (removed)

| Key | Evidence | Action taken |
|---|---|---|
| `USE_CONTEXTUALIZED_EMBEDDINGS` | Zero Python references in `src/`, `telegram_bot/`, `services/`, `scripts/` | Removed from `.env.example` |
| `CONTEXTUALIZED_EMBEDDING_DIM` | Zero Python references in `src/`, `telegram_bot/`, `services/`, `scripts/` | Removed from `.env.example` |

Feature was experimental/planned (see `docs/CONTEXTUALIZED_EMBEDDINGS.md`); `src/models/contextualized_embedding.py` is tracked as dead code in `tests/contract/test_dead_code_cleanup_contract.py`. No operator can configure a feature that no code reads.

### Dual-Owner Keys (informational, no drift)

The following keys are legitimately read by both `Settings` (`src/config/settings.py`) and `BotConfig` (`telegram_bot/config.py`). Both classes have their own purpose (core pipeline vs Telegram adapter) and reading the same env var is intentional:

`QDRANT_URL`, `QDRANT_API_KEY`, `OPENAI_API_KEY`, `USE_HYDE`, `HYDE_MIN_WORDS`, `SMALL_TO_BIG_MODE`, `SMALL_TO_BIG_WINDOW_BEFORE`, `SMALL_TO_BIG_WINDOW_AFTER`, `MAX_EXPANDED_CHUNKS`, `MAX_CONTEXT_TOKENS`

### Langfuse Toggle Overlap (informational)

Three keys act as aliases for the same Langfuse on/off toggle:
- `ENABLE_LANGFUSE` (Settings)
- `LANGFUSE_ENABLED` (bot)
- `LANGFUSE_TRACING_ENABLED` (bot)

All three appear in `.env.example` with comments. No removal warranted — the contract scanner accepts any key that has at least one code reader.

---

## Contract Test Result

After removing the two stale keys:

```
tests/contract/test_env_example_completeness_contract.py::test_no_env_vars_used_in_code_missing_from_env_example PASSED
tests/contract/test_env_example_completeness_contract.py::test_no_env_vars_in_env_example_unused_by_code PASSED
tests/contract/test_env_example_completeness_contract.py::test_env_example_is_split_into_sections PASSED
tests/contract/test_env_example_completeness_contract.py::test_allowlists_have_no_overlap_with_documented_keys PASSED
tests/contract/test_env_example_completeness_contract.py::test_langfuse_container_env_surface_is_documented_and_fixture_backed PASSED
5 passed
```
