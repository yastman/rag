# Testing Plan - Comprehensive Test Coverage

> **Цель:** Достичь 80%+ покрытия кода тестами для критичных компонентов

**Дата:** 2025-01-06
**Версия:** 2.8.0
**Статус:** 📝 Plan

---

## 🎯 Приоритеты тестирования

### Tier 1: Critical Path (Must Have) 🔴
Компоненты, которые напрямую влияют на работу бота.

### Tier 2: Core Features (Should Have) 🟡
Важные функции, но не блокирующие.

### Tier 3: Nice to Have (Could Have) 🟢
Дополнительные тесты для улучшения качества.

---

## 📦 Unit Tests

### 1. telegram_bot/services/cache.py (Tier 1) 🔴

**Компонент:** Multi-level caching with Redis

**Тест-файл:** `tests/unit/test_cache_service.py`

**Тест-кейсы:**
```python
# Tier 1 - Semantic Cache
- test_semantic_cache_hit_above_threshold()
- test_semantic_cache_miss_below_threshold()
- test_semantic_cache_store_and_retrieve()
- test_semantic_cache_ttl_expiration()
- test_semantic_cache_with_no_redis_connection()

# Tier 1 - Embeddings Cache
- test_embeddings_cache_hit()
- test_embeddings_cache_miss()
- test_embeddings_cache_ttl()
- test_embeddings_cache_graceful_degradation()

# Tier 2 - Query Analyzer Cache
- test_query_analyzer_cache_hit()
- test_query_analyzer_cache_miss()
- test_query_analyzer_cache_with_filters()

# Tier 2 - Search Results Cache
- test_search_cache_hit_exact_filters()
- test_search_cache_miss_different_filters()
- test_search_cache_invalidation()

# Tier 1 - Conversation Memory
- test_conversation_store_and_retrieve()
- test_conversation_history_limit()
- test_conversation_clear()
- test_conversation_ttl_expiration()

# Tier 1 - Metrics
- test_cache_metrics_calculation()
- test_cache_hit_rate_accuracy()
- test_metrics_by_cache_type()

# Tier 1 - Graceful Degradation
- test_cache_continues_without_redis()
- test_cache_handles_redis_timeout()
- test_cache_handles_corrupted_data()
```

**Покрытие:** ~85% (критичный компонент)

---

### 2. telegram_bot/services/llm.py (Tier 1) 🔴

**Компонент:** LLM answer generation with streaming

**Тест-файл:** `tests/unit/test_llm_service.py`

**Тест-кейсы:**
```python
# Tier 1 - Answer Generation
- test_generate_answer_success()
- test_generate_answer_with_context()
- test_generate_answer_with_custom_prompt()
- test_generate_answer_empty_context()

# Tier 1 - Streaming
- test_stream_answer_success()
- test_stream_answer_chunk_by_chunk()
- test_stream_answer_handles_done_marker()
- test_stream_answer_json_decode_errors()

# Tier 1 - Graceful Degradation
- test_generate_answer_timeout_fallback()
- test_generate_answer_http_error_fallback()
- test_stream_answer_timeout_fallback()
- test_fallback_answer_format()
- test_fallback_answer_with_empty_results()

# Tier 2 - Context Formatting
- test_format_context_with_metadata()
- test_format_context_empty()
- test_format_context_with_scores()

# Tier 2 - Error Handling
- test_llm_handles_invalid_api_key()
- test_llm_handles_rate_limiting()
- test_llm_handles_malformed_response()
```

**Покрытие:** ~80%

---

### 3. telegram_bot/services/retriever.py (Tier 1) 🔴

**Компонент:** Qdrant vector search with filtering

**Тест-файл:** `tests/unit/test_retriever_service.py`

**Тест-кейсы:**
```python
# Tier 1 - Search
- test_search_with_vector()
- test_search_with_filters()
- test_search_with_price_range()
- test_search_with_exact_match()
- test_search_with_min_score_threshold()
- test_search_returns_formatted_results()

# Tier 1 - Filter Building
- test_build_base_filter_csv_only()
- test_build_filter_with_exact_match()
- test_build_filter_with_range()
- test_build_filter_with_multiple_conditions()

# Tier 1 - Graceful Degradation
- test_search_without_qdrant_connection()
- test_search_handles_qdrant_timeout()
- test_search_handles_collection_not_found()
- test_health_check_on_init()

# Tier 2 - Edge Cases
- test_search_with_empty_vector()
- test_search_with_invalid_filters()
- test_search_no_results()
```

**Покрытие:** ~75%

---

### 4. telegram_bot/services/query_analyzer.py (Tier 2) 🟡

**Компонент:** LLM-based filter extraction

**Тест-файл:** `tests/unit/test_query_analyzer.py`

**Тест-кейсы:**
```python
# Tier 2 - Filter Extraction
- test_analyze_with_price_filter()
- test_analyze_with_rooms_filter()
- test_analyze_with_city_filter()
- test_analyze_with_multiple_filters()
- test_analyze_with_price_range()
- test_analyze_no_filters()

# Tier 2 - Semantic Query
- test_semantic_query_extraction()
- test_semantic_query_unchanged()

# Tier 3 - Error Handling
- test_analyze_handles_llm_error()
- test_analyze_handles_invalid_json()
```

**Покрытие:** ~60%

---

### 5. src/retrieval/reranker.py (Tier 1) 🔴

**Компонент:** Cross-encoder reranking

**Тест-файл:** `tests/unit/test_reranker.py`

**Тест-кейсы:**
```python
# Tier 1 - Reranking
- test_rerank_results_success()
- test_rerank_preserves_original_score()
- test_rerank_sorts_by_relevance()
- test_rerank_with_top_k()
- test_rerank_empty_results()
- test_rerank_single_result()

# Tier 1 - Singleton Pattern
- test_cross_encoder_singleton()
- test_cross_encoder_loaded_once()

# Tier 2 - Graceful Degradation
- test_rerank_handles_model_error()
- test_rerank_returns_original_on_error()

# Tier 3 - Memory Management
- test_clear_cross_encoder()
```

**Покрытие:** ~70%

---

### 6. telegram_bot/logging_config.py (Tier 2) 🟡

**Компонент:** Structured JSON logging

**Тест-файл:** `tests/unit/test_logging_config.py`

**Тест-кейсы:**
```python
# Tier 2 - JSON Formatting
- test_json_formatter_basic_fields()
- test_json_formatter_with_exception()
- test_json_formatter_with_extra_fields()
- test_json_formatter_timestamp_format()

# Tier 2 - Setup
- test_setup_logging_json_format()
- test_setup_logging_text_format()
- test_setup_logging_with_file()
- test_setup_logging_third_party_levels()

# Tier 3 - StructuredLogger
- test_structured_logger_info_with_context()
- test_structured_logger_error_with_context()
```

**Покрытие:** ~60%

---

## 🔗 Integration Tests

### 7. RAG Pipeline End-to-End (Tier 1) 🔴

**Тест-файл:** `tests/integration/test_rag_pipeline.py`

**Тест-кейсы:**
```python
# Tier 1 - Full Pipeline
- test_query_to_answer_flow()
  # Query → Embeddings → Search → Rerank → LLM → Answer
- test_pipeline_with_cache_hit()
- test_pipeline_with_cache_miss()
- test_pipeline_with_filters()

# Tier 1 - Service Integration
- test_cache_stores_embeddings()
- test_cache_stores_semantic_results()
- test_retriever_uses_embeddings()
- test_llm_uses_search_results()

# Tier 1 - Conversation Flow
- test_conversation_memory_multi_turn()
- test_conversation_clear_resets_history()

# Tier 2 - Performance
- test_pipeline_latency_under_3s()
- test_cache_improves_latency()
```

**Покрытие:** Интеграционные тесты

---

### 8. Graceful Degradation (Tier 1) 🔴

**Тест-файл:** `tests/integration/test_graceful_degradation.py`

**Тест-кейсы:**
```python
# Tier 1 - Service Failures
- test_bot_continues_without_redis()
- test_bot_continues_without_qdrant()
- test_bot_continues_without_llm()
- test_bot_shows_fallback_without_llm()

# Tier 1 - Partial Failures
- test_bot_works_with_embeddings_cache_down()
- test_bot_works_with_semantic_cache_down()
- test_bot_works_with_reranker_error()

# Tier 2 - Timeout Scenarios
- test_bot_handles_qdrant_timeout()
- test_bot_handles_llm_timeout()
- test_bot_handles_redis_timeout()
```

**Покрытие:** Интеграционные тесты

---

### 9. Cache Behavior (Tier 2) 🟡

**Тест-файл:** `tests/integration/test_cache_behavior.py`

**Тест-кейсы:**
```python
# Tier 2 - Semantic Cache
- test_semantic_cache_finds_similar_queries()
- test_semantic_cache_different_phrasings()
- test_semantic_cache_threshold_boundary()

# Tier 2 - Cache Invalidation
- test_cache_respects_ttl()
- test_cache_clears_on_command()
- test_cache_metrics_accurate()

# Tier 3 - Cache Performance
- test_cache_reduces_latency()
- test_cache_hit_rate_over_time()
```

**Покрытие:** Интеграционные тесты

---

## 🤖 Bot Tests

### 10. Telegram Bot Handlers (Tier 2) 🟡

**Тест-файл:** `tests/bot/test_bot_handlers.py`

**Тест-кейсы:**
```python
# Tier 2 - Commands
- test_start_command()
- test_help_command()
- test_clear_command()
- test_stats_command()

# Tier 2 - Query Handling
- test_handle_query_simple()
- test_handle_query_with_filters()
- test_handle_query_no_results()

# Tier 2 - Streaming
- test_streaming_updates_message()
- test_streaming_fallback_on_error()

# Tier 3 - Middlewares
- test_throttling_middleware()
- test_error_handler_middleware()
```

**Покрытие:** ~50% (behavioral tests)

---

## 🔧 Test Infrastructure

### pytest.ini Configuration

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    -v
    --tb=short
    --strict-markers
    --disable-warnings
    --cov=telegram_bot
    --cov=src
    --cov-report=html
    --cov-report=term-missing
    --cov-fail-under=70

markers =
    unit: Unit tests (fast, no external deps)
    integration: Integration tests (require services)
    slow: Slow tests (>1s execution time)
    bot: Telegram bot tests
```

### conftest.py - Fixtures

```python
# tests/conftest.py

import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    redis = AsyncMock()
    redis.ping.return_value = True
    return redis

@pytest.fixture
def mock_qdrant():
    """Mock Qdrant client for testing."""
    qdrant = MagicMock()
    qdrant.get_collections.return_value = []
    return qdrant

@pytest.fixture
def mock_httpx():
    """Mock httpx client for LLM calls."""
    client = AsyncMock()
    return client

@pytest.fixture
def sample_query_vector():
    """Sample 1024-dim vector for testing."""
    return [0.1] * 1024

@pytest.fixture
def sample_search_results():
    """Sample Qdrant search results."""
    return [
        {
            "text": "Sample apartment",
            "metadata": {"price": 80000, "city": "Несебр"},
            "score": 0.95
        }
    ]
```

---

## 📊 Coverage Goals

| Component | Priority | Target Coverage |
|-----------|----------|----------------|
| telegram_bot/services/cache.py | 🔴 | 85% |
| telegram_bot/services/llm.py | 🔴 | 80% |
| telegram_bot/services/retriever.py | 🔴 | 75% |
| src/retrieval/reranker.py | 🔴 | 70% |
| telegram_bot/services/query_analyzer.py | 🟡 | 60% |
| telegram_bot/bot.py | 🟡 | 60% |
| Integration tests | 🔴 | N/A (behavioral) |
| **Overall Project** | - | **70%+** |

---

## 🚀 Implementation Plan

### Phase 1: Setup (Day 1)
1. Create `tests/unit/` structure
2. Create `tests/integration/` structure
3. Setup `pytest.ini` and `conftest.py`
4. Add pytest dependencies to requirements.txt

### Phase 2: Unit Tests (Days 2-3)
1. Write cache service tests (~20 test cases)
2. Write LLM service tests (~15 test cases)
3. Write retriever service tests (~12 test cases)
4. Write reranker tests (~8 test cases)

### Phase 3: Integration Tests (Day 4)
1. Write RAG pipeline tests (~8 test cases)
2. Write graceful degradation tests (~8 test cases)
3. Write cache behavior tests (~6 test cases)

### Phase 4: CI Integration (Day 5)
1. Setup GitHub Actions workflow
2. Run tests on PR
3. Generate coverage reports
4. Add badges to README

---

## 📦 Required Dependencies

```python
# Testing dependencies (add to requirements.txt)
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-cov>=4.1.0
pytest-mock>=3.11.0
pytest-timeout>=2.1.0
```

---

## ✅ Success Criteria

1. ✅ 70%+ overall test coverage
2. ✅ All Tier 1 (critical) tests passing
3. ✅ Integration tests for main user flows
4. ✅ Graceful degradation scenarios covered
5. ✅ CI pipeline running tests automatically
6. ✅ Test execution time < 30s for unit tests
7. ✅ Test execution time < 2min for full suite

---

## 📝 Notes

- **Mocking:** Use `unittest.mock` for external services (Redis, Qdrant, LLM APIs)
- **Async:** Use `pytest-asyncio` for async function testing
- **Fixtures:** Share common test data via `conftest.py`
- **Markers:** Use `@pytest.mark.unit` and `@pytest.mark.integration` for filtering
- **Performance:** Run unit tests fast (<100ms each), integration tests can be slower

---

**Автор:** Claude Code
**Последнее обновление:** 2025-01-06
**Версия документа:** 1.0
