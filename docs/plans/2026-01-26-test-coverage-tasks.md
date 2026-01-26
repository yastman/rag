# Test Coverage 80% — Tasks

**Status:** DONE ✅
**Started:** 2026-01-26
**Completed:** 2026-01-26
**Target:** 80% coverage, 0 failing tests
**Final:** 82% coverage, 0 failing tests, 1105 tests passing

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

## Track 2: Write New Tests (Worker 2) ✅ DONE

### 2.1 cache.py (21% → 65%) ✅
- [x] test_initialize — подключение к Redis
- [x] test_check_semantic_cache_hit — cache hit
- [x] test_check_semantic_cache_miss — cache miss
- [x] test_store_semantic_cache — сохранение в кеш
- [x] test_get_cached_embedding — embedding cache hit
- [x] test_store_embedding — сохранение embedding
- [x] test_get_conversation_history — история диалога
- [x] test_store_conversation_message — сохранение сообщения
- [x] test_clear_conversation_history — очистка истории
- [x] test_get_metrics — метрики hit/miss
- [x] test_close — закрытие соединений

### 2.2 user_context.py (12% → 94%) ✅
- [x] test_get_context_new_user — новый пользователь
- [x] test_get_context_existing_user — существующий
- [x] test_update_from_query — обновление из запроса
- [x] test_extract_preferences — извлечение предпочтений
- [x] test_merge_preferences — слияние предпочтений
- [x] test_extraction_frequency — частота обновления

### 2.3 qdrant.py (23% → 55%) ✅
- [x] test_mmr_rerank_basic — базовый MMR
- [x] test_mmr_rerank_diversity — diversity vs relevance
- [x] test_mmr_rerank_lambda_variations — разные lambda
- [x] test_mmr_rerank_edge_cases — empty, single, few points

### 2.4 query_router.py (25% → 100%) ✅
- [x] test_classify_query_chitchat_greetings — приветствия
- [x] test_classify_query_chitchat_thanks — благодарности
- [x] test_classify_query_simple — простые запросы
- [x] test_classify_query_complex — сложные запросы
- [x] test_get_chitchat_response — ответы на chitchat
- [x] test_needs_rerank — логика rerrank

### 2.5 cesc.py (25% → existing tests) ✅
- [x] test_is_personalized_query_with_markers — с маркерами
- [x] test_is_personalized_query_generic — без маркеров
- [x] test_is_personalized_query_context — с контекстом

---

## Progress

| Track | Total | Done | Remaining |
|-------|-------|------|-----------|
| Track 1 | 22 | 22 | 0 |
| Track 2 | 31 | 31 | 0 |

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
