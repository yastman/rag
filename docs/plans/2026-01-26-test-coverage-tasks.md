# Test Coverage 80% — Tasks

**Status:** IN_PROGRESS
**Started:** 2026-01-26
**Target:** 80% coverage, 0 failing tests
**Current:** 57% coverage, 22 failing tests

---

## Track 1: Fix Failing Tests (Worker 1) ✅ DONE

### 1.1 filter_extractor (4 tests) ✅
- [x] test_price_range_pattern_order — Fixed: test expected wrong behavior, code correctly extracts range
- [x] test_price_k_suffix_captured_by_regex — Fixed: renamed, code correctly handles "100к" → 100000
- [x] test_distance_pervaya_liniya — Fixed: renamed, code correctly extracts {"lte": 200}
- [x] test_distance_u_morya — Fixed: renamed, code correctly extracts {"lte": 200}

### 1.2 metrics_logger (15 tests) ✅
- [x] Причина: относительный импорт `from config_snapshot` → `from .config_snapshot`
- [x] test_query_metrics_creation
- [x] test_query_metrics_to_dict
- [x] test_query_metrics_to_json
- [x] test_query_metrics_to_prometheus
- [x] test_logger_init_creates_directory
- [x] test_logger_log_query
- [x] test_logger_aggregates_stats
- [x] test_logger_writes_json_log
- [x] test_logger_export_prometheus
- [x] test_logger_get_summary
- [x] test_slo_thresholds_defaults
- [x] test_slo_violation_count
- [x] test_latency_anomaly_logged
- [x] test_quality_anomaly_logged
- [x] test_zero_results_anomaly

### 1.3 otel_setup (2 tests) ✅
- [x] test_setup_opentelemetry — Fixed: proper module-level patching
- [x] test_traced_pipeline_query — Fixed: added missing _embed/_search/_rerank methods

### 1.4 evaluator (1 test) ✅
- [x] test_compare_engines_improvements — Fixed: use pytest.approx() for float comparison

---

## Track 2: Write New Tests (Worker 2)

### 2.1 cache.py (21% → 80%)
- [ ] test_initialize — подключение к Redis
- [ ] test_check_semantic_cache_hit — cache hit
- [ ] test_check_semantic_cache_miss — cache miss
- [ ] test_store_semantic_cache — сохранение в кеш
- [ ] test_get_cached_embedding — embedding cache hit
- [ ] test_store_embedding — сохранение embedding
- [ ] test_get_cached_sparse_embedding — sparse cache
- [ ] test_store_sparse_embedding — сохранение sparse
- [ ] test_get_conversation_history — история диалога
- [ ] test_store_conversation_message — сохранение сообщения
- [ ] test_clear_conversation_history — очистка истории
- [ ] test_get_metrics — метрики hit/miss

### 2.2 user_context.py (12% → 80%)
- [ ] test_get_context_new_user — новый пользователь
- [ ] test_get_context_existing_user — существующий
- [ ] test_update_from_query — обновление из запроса
- [ ] test_extract_preferences_cities — извлечение городов
- [ ] test_extract_preferences_budget — извлечение бюджета
- [ ] test_context_ttl_expiry — истечение TTL
- [ ] test_extraction_frequency — частота обновления

### 2.3 qdrant.py (23% → 80%)
- [ ] test_hybrid_search_rrf_empty_results — пустой результат
- [ ] test_hybrid_search_rrf_with_filters — с фильтрами
- [ ] test_hybrid_search_rrf_sparse_only — только sparse
- [ ] test_mmr_rerank_basic — базовый MMR
- [ ] test_mmr_rerank_lambda_variations — разные lambda
- [ ] test_search_timeout_fallback — graceful degradation
- [ ] test_close — закрытие клиента

### 2.4 query_router.py (25% → 80%)
- [ ] test_classify_query_chitchat_greetings — приветствия
- [ ] test_classify_query_chitchat_thanks — благодарности
- [ ] test_classify_query_simple — простые запросы
- [ ] test_classify_query_complex — сложные запросы
- [ ] test_get_chitchat_response_hello — ответ на привет
- [ ] test_get_chitchat_response_thanks — ответ на спасибо
- [ ] test_needs_rerank_simple_false — skip для simple
- [ ] test_needs_rerank_complex_true — rerank для complex

### 2.5 cesc.py (25% → 80%)
- [ ] test_is_personalized_query_with_markers — с маркерами
- [ ] test_is_personalized_query_generic — без маркеров
- [ ] test_personalize_full_flow — полный flow
- [ ] test_personalize_empty_context — пустой контекст
- [ ] test_personalize_llm_error_fallback — fallback при ошибке

---

## Progress

| Track | Total | Done | Remaining |
|-------|-------|------|-----------|
| Track 1 | 22 | 22 | 0 |
| Track 2 | 31 | 0 | 31 |

---

## Commands

```bash
# Worker 1: проверка своих тестов
pytest tests/unit/services/test_filter_extractor.py tests/unit/test_metrics_logger.py tests/unit/test_otel_setup.py tests/unit/test_evaluator.py -v

# Worker 2: проверка покрытия
pytest tests/unit/ --cov=telegram_bot/services --cov-report=term

# Финальная проверка
pytest tests/unit/ --cov=telegram_bot/services --cov-fail-under=80 -q
```
