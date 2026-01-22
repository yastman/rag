# Comprehensive Testing Design

> **Date:** 2026-01-22
> **Version:** v2.9.1
> **Branch:** feat/redis-stack-vector-search
> **Approach:** Automated (Smoke → Regression → Integration → E2E)

---

## Overview

Full test coverage for all new features in v2.9.0-2.9.1:
- Voyage AI migration (embeddings, reranker, hybrid search)
- CESC personalization (UserContext, CESCPersonalizer)
- Cache improvements (SemanticMessageHistory, EmbeddingsCache fix)
- LLM enhancements (generate(), streaming, Markdown)

**Target:** ~130 tests with 100% pass rate

---

## Etap 1: Smoke Testing

**File:** `tests/test_smoke_services.py`
**Purpose:** Verify all services are alive and responding

| Test | Service | Endpoint | Expected |
|------|---------|----------|----------|
| `test_qdrant_health` | Qdrant | `GET :6333/health` | 200 OK |
| `test_redis_health` | Redis | `PING` | PONG |
| `test_mlflow_health` | MLflow | `GET :5000/health` | 200 OK |
| `test_langfuse_health` | Langfuse | `GET :3001/api/public/health` | 200 OK |
| `test_docling_health` | Docling | `GET :5001/health` | 200 OK |
| `test_lightrag_health` | LightRAG | `GET :9621/health` | 200 OK |
| `test_voyage_api_health` | Voyage API | `POST /v1/embeddings` | 200 OK |
| `test_llm_api_health` | LLM API | `POST /chat/completions` | 200 OK |

**Run:** `pytest tests/test_smoke_services.py -v`
**Time:** ~5 seconds

---

## Etap 2: Infrastructure Tests

**File:** `tests/test_infrastructure.py`

##***REMOVED*** Tests

| Test | What |
|------|------|
| `test_qdrant_collections_exist` | `contextual_bulgaria_voyage`, `legal_documents` exist |
| `test_qdrant_collection_voyage_info` | 1024-dim vectors, BM42 sparse |
| `test_qdrant_points_count_bulgaria` | >= 92 documents |
| `test_qdrant_points_count_legal` | >= 1294 documents |
| `test_qdrant_search_dense` | Dense search returns results |
| `test_qdrant_search_sparse` | Sparse (BM42) search works |

### Redis Tests

| Test | What |
|------|------|
| `test_redis_search_module` | RediSearch module loaded |
| `test_redis_json_module` | RedisJSON module loaded |
| `test_redis_cache_index_exists` | `idx:semantic_cache` index exists |
| `test_redis_set_get` | Basic key-value operations |
| `test_redis_vector_search` | Vector similarity search works |
| `test_redis_json_operations` | JSON.SET/GET operations |

### MLflow Tests

| Test | What |
|------|------|
| `test_mlflow_experiments_list` | List experiments available |
| `test_mlflow_tracking_uri` | Tracking URI correct |

### Langfuse Tests

| Test | What |
|------|------|
| `test_langfuse_api_connection` | API keys valid |
| `test_langfuse_trace_create` | Create trace works |
| `test_langfuse_span_create` | Create span works |

### Docling Tests

| Test | What |
|------|------|
| `test_docling_parse_pdf` | PDF parsing returns text |
| `test_docling_parse_docx` | DOCX parsing works |

**Run:** `pytest tests/test_infrastructure.py -v`

---

## Etap 3: Service Unit Tests

### CacheService (`tests/test_cache_service.py`)

| Test | What |
|------|------|
| `test_cache_initialize` | Redis + SemanticCache + EmbeddingsCache + MessageHistory |
| `test_semantic_cache_store_check` | Store → Check returns result |
| `test_semantic_cache_distance_threshold` | Threshold 0.15 filters distant queries |
| `test_semantic_cache_user_isolation` | user_id isolates entries |
| `test_semantic_cache_threshold_override` | Dynamic threshold works |
| `test_embeddings_cache_store_get` | Store → Get embedding |
| `test_analyzer_cache_store_get` | JSON key-value cache |
| `test_search_cache_store_get` | Qdrant results cache |
| `test_semantic_message_history_add_get` | Conversation messages stored |
| `test_get_relevant_history` | Semantic similarity in history |
| `test_cache_metrics` | Hits/misses counting |

### HybridRetrieverService (`tests/test_hybrid_retriever.py`)

| Test | What |
|------|------|
| `test_hybrid_search_returns_results` | RRF fusion returns documents |
| `test_hybrid_search_rrf_weights_semantic` | Weights (0.6, 0.4) for semantic |
| `test_hybrid_search_rrf_weights_exact` | Weights (0.2, 0.8) for exact |
| `test_hybrid_search_with_filters` | Filter by city/price works |
| `test_hybrid_search_empty_sparse` | Graceful if sparse empty |
| `test_hybrid_search_qdrant_down` | Graceful degradation |

### QueryPreprocessor (`tests/test_query_preprocessor.py`)

| Test | What |
|------|------|
| `test_translit_sunny_beach` | "Sunny Beach" → "Солнечный берег" |
| `test_translit_sveti_vlas` | "Sveti Vlas" → "Святой Влас" |
| `test_translit_case_insensitive` | "sunny beach" → "Солнечный берег" |
| `test_translit_multiple` | Multiple cities in one query |
| `test_rrf_weights_semantic_query` | "квартира у моря" → (0.6, 0.4) |
| `test_rrf_weights_exact_id` | "ID 12345" → (0.2, 0.8) |
| `test_rrf_weights_exact_corpus` | "корпус 5" → (0.2, 0.8) |
| `test_cache_threshold_semantic` | Normal query → 0.10 |
| `test_cache_threshold_exact` | "ID 12345" → 0.05 |
| `test_has_exact_identifier` | Detection of IDs, corpus, block |
| `test_analyze_full` | Full analyze() returns all fields |

### UserContextService (`tests/test_user_context.py`)

| Test | What |
|------|------|
| `test_default_context` | New user gets default context |
| `test_get_context_from_redis` | Load from Redis JSON |
| `test_update_interaction_count` | Counter +1 per query |
| `test_last_queries_stored` | Last 5 queries saved |
| `test_extraction_frequency_3` | Extraction every 3rd query |
| `test_should_extract_first_query` | Extract on first query |
| `test_should_extract_empty_prefs` | Extract if prefs empty |
| `test_merge_preferences_cities` | Cities merged (not overwritten) |
| `test_merge_preferences_budget` | Budget overwritten |
| `test_merge_preferences_null_ignored` | None values ignored |
| `test_generate_summary` | Profile summary after 5 queries |
| `test_extract_preferences_json` | LLM JSON response parsed |
| `test_extract_preferences_markdown` | ```json blocks handled |

### CESCPersonalizer (`tests/test_cesc_personalizer.py`)

| Test | What |
|------|------|
| `test_should_personalize_with_cities` | True if cities present |
| `test_should_personalize_with_budget` | True if budget present |
| `test_should_personalize_with_types` | True if property_types present |
| `test_should_personalize_empty` | False if preferences empty |
| `test_personalize_calls_llm` | LLM called with correct prompt |
| `test_personalize_returns_result` | Personalized text returned |
| `test_personalize_fallback_on_error` | Returns cached_response on error |
| `test_build_prompt_format` | Prompt contains cities, budget, types |

### LLMService (`tests/test_llm_service.py`)

| Test | What |
|------|------|
| `test_generate_answer_success` | Answer generation works |
| `test_generate_answer_with_context` | Context formatted correctly |
| `test_generate_answer_markdown_prompt` | System prompt requests Markdown |
| `test_stream_answer_yields_tokens` | Streaming returns tokens |
| `test_stream_answer_sse_parsing` | SSE format parsed |
| `test_generate_simple` | generate() for CESC works |
| `test_generate_low_temperature` | temperature=0.3 for structured |
| `test_fallback_on_timeout` | Fallback on timeout |
| `test_fallback_on_http_error` | Fallback on HTTP 500 |
| `test_fallback_format` | Fallback contains objects from chunks |
| `test_format_context_with_metadata` | Metadata (title, city, price) formatted |
| `test_format_context_empty` | Empty context → "не найдено" |

---

## Etap 4: Voyage AI Tests

##***REMOVED***Client (`tests/test_voyage_client.py`)

| Test | What |
|------|------|
| `test_singleton_instance` | get_instance() returns same object |
| `test_retry_on_rate_limit` | Retry on 429 (tenacity) |
| `test_retry_on_server_error` | Retry on 500/502/503 |
| `test_no_retry_on_client_error` | No retry on 400/401 |
| `test_embed_texts_batch` | Batch embedding works |
| `test_rerank_documents` | Rerank returns scores |

##***REMOVED***EmbeddingService (`tests/test_voyage_embeddings.py`)

| Test | What |
|------|------|
| `test_embed_single_text` | Single embedding |
| `test_embed_batch_texts` | Batch up to 128 texts |
| `test_embed_dimension_1024` | Dimension = 1024 |
| `test_embed_model_voyage_3_large` | Model voyage-3-large |
| `test_embed_empty_text` | Graceful handling empty text |
| `test_embed_long_text` | Text > 32K tokens truncation |

##***REMOVED***RerankerService (`tests/test_voyage_reranker.py`)

| Test | What |
|------|------|
| `test_rerank_returns_scores` | Scores returned |
| `test_rerank_ordering` | Relevant docs higher |
| `test_rerank_top_k` | top_k limits results |
| `test_rerank_model_rerank_2` | Model rerank-2 |
| `test_rerank_empty_documents` | Empty list → empty result |
| `test_rerank_preserves_metadata` | Metadata preserved |

---

## Etap 5: Integration Tests

### Pipeline Integration (`tests/test_voyage_integration.py`)

| Test | What |
|------|------|
| `test_full_pipeline_query_to_answer` | Query → Embed → Search → Rerank → LLM → Answer |
| `test_pipeline_with_cache_miss` | Full pipeline on cache MISS |
| `test_pipeline_with_cache_hit` | Cache HIT → skip search/LLM |
| `test_pipeline_with_cesc` | Cache HIT + CESC personalization |
| `test_pipeline_query_preprocessor` | Translit + RRF weights applied |
| `test_pipeline_hybrid_search` | Dense + Sparse fusion works |
| `test_pipeline_filters_applied` | QueryAnalyzer filters → Qdrant |
| `test_pipeline_graceful_degradation` | LLM down → fallback answer |

### Bot Handler (`tests/test_bot_handler.py`)

| Test | What |
|------|------|
| `test_handle_query_returns_answer` | Query returns answer |
| `test_handle_query_markdown_format` | Answer in Markdown format |
| `test_handle_query_streaming` | Streaming works |
| `test_handle_query_cesc_enabled` | CESC personalization triggers |
| `test_handle_query_user_context_updated` | UserContext updated |
| `test_handle_query_cache_stored` | Answer stored in cache |
| `test_handle_query_conversation_stored` | Message history updated |

---

## Etap 6: E2E Tests

**File:** `tests/test_e2e_telegram.py`
**Method:** Direct bot API calls (not Telegram API)

| Test | Scenario | Expected |
|------|----------|----------|
| `test_e2e_simple_query` | "квартиры в Солнечном береге" | Answer with properties |
| `test_e2e_exact_query` | "корпус 5" | Exact results |
| `test_e2e_translit_query` | "Sunny Beach apartments" | Works (translit) |
| `test_e2e_price_filter` | "до 50000 евро" | Filtered results |
| `test_e2e_multi_turn` | 2-3 messages | Context preserved |
| `test_e2e_cache_hit_faster` | Repeat query | < 200ms |
| `test_e2e_markdown_rendered` | Any query | **bold** and • lists |

---

## Test Structure

```
tests/
├── test_smoke_services.py          # NEW (8 tests)
├── test_infrastructure.py          # NEW (18 tests)
├── test_voyage_client.py           # EXISTS (6 tests)
├── test_voyage_embeddings.py       # EXISTS (6 tests)
├── test_voyage_reranker.py         # EXISTS (6 tests)
├── test_voyage_integration.py      # EXTEND (8 tests)
├── test_cache_service.py           # NEW (11 tests)
├── test_hybrid_retriever.py        # EXTEND (6 tests)
├── test_query_preprocessor.py      # EXTEND (11 tests)
├── test_user_context.py            # NEW (13 tests)
├── test_cesc_personalizer.py       # NEW (8 tests)
├── test_cesc.py                    # EXISTS (keep)
├── test_cesc_integration.py        # EXISTS (3 tests)
├── test_llm_service.py             # NEW (12 tests)
├── test_bot_handler.py             # NEW (7 tests)
├── test_e2e_telegram.py            # NEW (7 tests)
└── conftest.py                     # Fixtures
```

---

## Run Commands

```bash
# 1. Smoke only (quick health check)
pytest tests/test_smoke_services.py -v

# 2. Infrastructure only
pytest tests/test_infrastructure.py -v

# 3. All unit tests (no E2E)
pytest tests/ -v --ignore=tests/legacy/ --ignore=tests/test_e2e_telegram.py -x

# 4. Integration + E2E
pytest tests/test_voyage_integration.py tests/test_e2e_telegram.py -v

# 5. Full suite
pytest tests/ -v --ignore=tests/legacy/ -x --tb=short

# 6. With coverage
pytest tests/ --ignore=tests/legacy/ --cov=telegram_bot --cov=src --cov-report=html
```

---

## Summary

| Category | New Tests | Total |
|----------|-----------|-------|
| Smoke | 8 | 8 |
| Infrastructure | 18 | 18 |
| Voyage AI | 0 | ~18 |
| Cache | 11 | ~21 |
| CESC | 21 | ~24 |
| LLM | 12 | ~17 |
| Bot Handler | 7 | 7 |
| E2E | 7 | 7 |
| **Total** | **~84** | **~130** |

---

## Success Criteria

1. **Smoke:** All 8 services respond healthy
2. **Regression:** 100% tests pass (0 failures)
3. **Integration:** Full pipeline works Query → Answer
4. **E2E:** Bot returns Markdown-formatted answers < 3s

---

## Next Steps

1. Create new test files (smoke, infrastructure, cache_service, etc.)
2. Run smoke tests first
3. Run full regression suite
4. Fix any failures
5. Generate coverage report
