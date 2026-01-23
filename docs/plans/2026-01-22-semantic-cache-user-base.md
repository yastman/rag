# Semantic Cache: Миграция на deepvk/USER-base

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace voyage-3-lite with local deepvk/USER-base model for semantic cache to improve Russian morphology understanding and cache hit rate.

**Architecture:** Switch from VoyageAI API-based vectorizer to local HuggingFace model (deepvk/USER-base, 768-dim). Update threshold from 0.30 to 0.15 for tighter matching. Pre-download model in Docker build.

**Tech Stack:** sentence-transformers, redisvl (HFTextVectorizer), Redis Stack

---

## Background

| Параметр | voyage-3-lite | deepvk/USER-base |
|----------|---------------|------------------|
| STS (ruMTEB) | ~60 | **74.35** |
| Тип | API | Локальная |
| Cost | $0.10/day | **$0** |
| Latency | 200-500ms | **50-100ms** |
| Dimension | 512 | 768 |
| RAM | - | ~1.5GB |

---

### Task 1: Write Russian morphology tests (TDD - failing first)

**Files:**
- Create: `tests/test_cache_russian_morphology.py`

**Step 1: Create test file**

```python
"""Tests for Russian morphology handling in semantic cache.

Tests that deepvk/USER-base model correctly handles:
- Word order variations (вид рассрочки vs рассрочки вид)
- Morphological forms (купить vs покупка)
- Singular/plural (рассрочка vs рассрочки)
"""

import os

import pytest

from telegram_bot.services.cache import CacheService


class TestRussianMorphology:
    """Test Russian morphology handling in semantic cache."""

    @pytest.fixture
    async def cache_service(self):
        """Create initialized cache service with tight threshold."""
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        service = CacheService(redis_url=redis_url, distance_threshold=0.15)
        await service.initialize()
        yield service
        await service.close()

    @pytest.mark.asyncio
    async def test_word_order_variation_hits_cache(self, cache_service):
        """Word order variation should hit cache: 'вид рассрочки' vs 'рассрочки вид'."""
        if not cache_service.semantic_cache:
            pytest.skip("SemanticCache not initialized")

        # Store with one word order
        query1 = "вид рассрочки"
        answer = "Доступны следующие виды рассрочки: 12, 24, 36 месяцев"
        await cache_service.store_semantic_cache(query1, answer)

        # Check with reversed word order
        query2 = "рассрочки вид"
        result = await cache_service.check_semantic_cache(query2)

        assert result is not None, "Word order variation should hit cache"
        assert "рассрочки" in result

    @pytest.mark.asyncio
    async def test_plural_singular_hits_cache(self, cache_service):
        """Plural/singular forms should hit cache: 'виды рассрочек' vs 'вид рассрочки'."""
        if not cache_service.semantic_cache:
            pytest.skip("SemanticCache not initialized")

        # Store singular form
        query1 = "вид рассрочки"
        answer = "Рассрочка на 12 месяцев без процентов"
        await cache_service.store_semantic_cache(query1, answer)

        # Check plural form
        query2 = "виды рассрочек"
        result = await cache_service.check_semantic_cache(query2)

        assert result is not None, "Plural form should hit cache"

    @pytest.mark.asyncio
    async def test_verb_noun_forms_hits_cache(self, cache_service):
        """Different word forms should hit cache: 'купить квартиру' vs 'покупка квартиры'."""
        if not cache_service.semantic_cache:
            pytest.skip("SemanticCache not initialized")

        # Store verb form
        query1 = "купить квартиру"
        answer = "Для покупки квартиры нужен паспорт и ЕГН"
        await cache_service.store_semantic_cache(query1, answer)

        # Check noun form
        query2 = "покупка квартиры"
        result = await cache_service.check_semantic_cache(query2)

        assert result is not None, "Verb/noun form variation should hit cache"

    @pytest.mark.asyncio
    async def test_different_intent_misses_cache(self, cache_service):
        """Different intent should NOT hit cache: 'купить квартиру' vs 'продать квартиру'."""
        if not cache_service.semantic_cache:
            pytest.skip("SemanticCache not initialized")

        # Store buy intent
        query1 = "купить квартиру"
        answer = "Для покупки квартиры..."
        await cache_service.store_semantic_cache(query1, answer)

        # Check sell intent (different!)
        query2 = "продать квартиру"
        result = await cache_service.check_semantic_cache(query2)

        assert result is None, "Different intent should NOT hit cache"

    @pytest.mark.asyncio
    async def test_different_topic_misses_cache(self, cache_service):
        """Different topic should NOT hit cache: 'вид рассрочки' vs 'процент по ипотеке'."""
        if not cache_service.semantic_cache:
            pytest.skip("SemanticCache not initialized")

        # Store installment query
        query1 = "вид рассрочки"
        answer = "Рассрочка без процентов на 12 месяцев"
        await cache_service.store_semantic_cache(query1, answer)

        # Check mortgage query (different topic)
        query2 = "процент по ипотеке"
        result = await cache_service.check_semantic_cache(query2)

        assert result is None, "Different topic should NOT hit cache"

    @pytest.mark.asyncio
    async def test_cyrillic_latin_translit_misses(self, cache_service):
        """Cyrillic vs Latin should NOT match: 'квартира' vs 'kvartira'."""
        if not cache_service.semantic_cache:
            pytest.skip("SemanticCache not initialized")

        # Store Cyrillic
        query1 = "квартира в Бургасе"
        answer = "Квартиры в Бургасе от 50000 евро"
        await cache_service.store_semantic_cache(query1, answer)

        # Check Latin transliteration
        query2 = "kvartira v Burgase"
        result = await cache_service.check_semantic_cache(query2)

        # Note: USER-base may or may not handle this - document actual behavior
        # This test documents the behavior, not enforces it
        if result:
            print("Note: USER-base handles Cyrillic-Latin transliteration")
        else:
            print("Note: USER-base does NOT handle Cyrillic-Latin transliteration")


class TestCacheLatency:
    """Test cache latency with local model."""

    @pytest.fixture
    async def cache_service(self):
        """Create initialized cache service."""
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        service = CacheService(redis_url=redis_url, distance_threshold=0.15)
        await service.initialize()
        yield service
        await service.close()

    @pytest.mark.asyncio
    async def test_cache_check_latency_under_200ms(self, cache_service):
        """Cache check should complete under 200ms with local model."""
        import time

        if not cache_service.semantic_cache:
            pytest.skip("SemanticCache not initialized")

        # Store a query first
        await cache_service.store_semantic_cache("тестовый запрос", "тестовый ответ")

        # Measure check latency
        start = time.time()
        await cache_service.check_semantic_cache("тестовый запрос")
        latency_ms = (time.time() - start) * 1000

        # Local model should be faster than API (200-500ms)
        assert latency_ms < 200, f"Cache check took {latency_ms:.0f}ms, expected <200ms"
        print(f"Cache check latency: {latency_ms:.0f}ms")
```

**Step 2: Run tests to see them fail**

Run: `pytest tests/test_cache_russian_morphology.py -v`
Expected: Tests FAIL (voyage-3-lite doesn't handle Russian morphology well)

**Step 3: Commit test file**

```bash
git add tests/test_cache_russian_morphology.py
git commit -m "test(cache): add Russian morphology tests for USER-base migration"
```

---

### Task 2: Add sentence-transformers dependency

**Files:**
- Modify: `telegram_bot/requirements.txt:19-20`

**Step 1: Add dependency to requirements.txt**

Add `sentence-transformers>=2.2.0` after the fastembed line:

```
# FastEmbed for sparse vectors (BM42)
fastembed>=0.4.0

# Sentence Transformers for local embeddings (semantic cache)
sentence-transformers>=2.2.0
```

**Step 2: Commit**

```bash
git add telegram_bot/requirements.txt
git commit -m "deps: add sentence-transformers for local cache embeddings"
```

---

### Task 3: Update cache.py imports

**Files:**
- Modify: `telegram_bot/services/cache.py:18`

**Step 1: Update import statement**

Change line 18 from:
```python
from redisvl.utils.vectorize import HFTextVectorizer, VoyageAITextVectorizer
```
to:
```python
from redisvl.utils.vectorize import HFTextVectorizer
```

**Step 2: Verify import works**

Run: `python -c "from redisvl.utils.vectorize import HFTextVectorizer; print('OK')"`
Expected: OK

**Step 3: Commit**

```bash
git add telegram_bot/services/cache.py
git commit -m "refactor(cache): remove VoyageAITextVectorizer import"
```

---

### Task 4: Replace SemanticCache vectorizer

**Files:**
- Modify: `telegram_bot/services/cache.py:107-134`

**Step 1: Update vectorizer initialization**

Replace lines 107-134 (SemanticCache initialization block):

```python
            # Initialize native RedisVL SemanticCache (Tier 1)
            # Uses local deepvk/USER-base for high-quality Russian semantic matching
            # Best-in-class STS score (74.35 on ruMTEB) for Russian morphology
            try:
                logger.info("Initializing SemanticCache with deepvk/USER-base (local)...")
                vectorizer = HFTextVectorizer(
                    model="deepvk/USER-base",
                )
                self.semantic_cache = SemanticCache(
                    name="rag_llm_cache",
                    redis_url=self.redis_url,
                    ttl=self.semantic_cache_ttl,
                    distance_threshold=self.distance_threshold,
                    vectorizer=vectorizer,
                    filterable_fields=[
                        {"name": "user_id", "type": "tag"},
                        {"name": "language", "type": "tag"},
                        {"name": "query_type", "type": "tag"},
                    ],
                )
                logger.info(
                    f"✓ RedisVL SemanticCache initialized "
                    f"(vectorizer=deepvk/USER-base, distance_threshold={self.distance_threshold}, "
                    f"filterable_fields=[user_id, language, query_type])"
                )
            except Exception as e:
                logger.warning(f"SemanticCache initialization failed: {e}")
                self.semantic_cache = None
```

**Step 2: Verify syntax**

Run: `python -m py_compile telegram_bot/services/cache.py && echo "Syntax OK"`
Expected: Syntax OK

**Step 3: Commit**

```bash
git add telegram_bot/services/cache.py
git commit -m "feat(cache): switch SemanticCache to deepvk/USER-base"
```

---

### Task 5: Replace SemanticMessageHistory vectorizer

**Files:**
- Modify: `telegram_bot/services/cache.py:151-171`

**Step 1: Update SemanticMessageHistory initialization**

Replace lines 151-171 (SemanticMessageHistory initialization block):

```python
            # Initialize SemanticMessageHistory for conversation context
            # Uses same deepvk/USER-base model for consistency
            try:
                history_vectorizer = HFTextVectorizer(
                    model="deepvk/USER-base",
                )
                self.message_history = SemanticMessageHistory(
                    name="rag_conversations",
                    redis_url=self.redis_url,
                    vectorizer=history_vectorizer,
                    distance_threshold=0.15,  # Tighter threshold for conversation matching
                )
                logger.info("✓ SemanticMessageHistory initialized (deepvk/USER-base)")
            except Exception as e:
                logger.warning(f"SemanticMessageHistory initialization failed: {e}")
                self.message_history = None
```

**Step 2: Verify syntax**

Run: `python -m py_compile telegram_bot/services/cache.py && echo "Syntax OK"`
Expected: Syntax OK

**Step 3: Commit**

```bash
git add telegram_bot/services/cache.py
git commit -m "feat(cache): switch SemanticMessageHistory to deepvk/USER-base"
```

---

### Task 6: Update default distance threshold

**Files:**
- Modify: `telegram_bot/services/cache.py:43`

**Step 1: Change default threshold**

Change line 43 from:
```python
        distance_threshold: float = 0.30,  # cosine distance threshold (0.30 ≈ 70% similarity, handles Russian word order variations)
```
to:
```python
        distance_threshold: float = 0.15,  # cosine distance threshold (0.15 = tight matching, USER-base handles Russian morphology)
```

**Step 2: Verify syntax**

Run: `python -m py_compile telegram_bot/services/cache.py && echo "Syntax OK"`
Expected: Syntax OK

**Step 3: Commit**

```bash
git add telegram_bot/services/cache.py
git commit -m "feat(cache): tighten distance threshold to 0.15 for USER-base"
```

---

### Task 7: Update docstrings to remove Voyage references

**Files:**
- Modify: `telegram_bot/services/cache.py:200-203`, `telegram_bot/services/cache.py:267-269`

**Step 1: Update check_semantic_cache docstring**

Change lines 200-203 from:
```python
        """Check semantic cache using RedisVL with VoyageAI voyage-3-lite.

        Uses VoyageAI voyage-3-lite for fast, cost-effective cache matching.
        This is separate from BGE-M3 (1024-dim) used for Qdrant search.
```
to:
```python
        """Check semantic cache using RedisVL with deepvk/USER-base.

        Uses local deepvk/USER-base model for high-quality Russian semantic matching.
        STS score 74.35 on ruMTEB - best for Russian morphology.
```

**Step 2: Update store_semantic_cache docstring**

Change lines 267-269 from:
```python
        """Store question-answer pair in semantic cache using RedisVL.

        Uses VoyageAI voyage-3-lite for cache indexing.
```
to:
```python
        """Store question-answer pair in semantic cache using RedisVL.

        Uses deepvk/USER-base model for cache indexing.
```

**Step 3: Verify syntax**

Run: `python -m py_compile telegram_bot/services/cache.py && echo "Syntax OK"`
Expected: Syntax OK

**Step 4: Commit**

```bash
git add telegram_bot/services/cache.py
git commit -m "docs(cache): update docstrings for USER-base migration"
```

---

### Task 8: Update Dockerfile to pre-download model

**Files:**
- Modify: `telegram_bot/Dockerfile`

**Step 1: Rewrite Dockerfile with model pre-download**

Replace entire file:

```dockerfile
# Telegram Bot Dockerfile
# Multi-stage build for smaller image size

# Build stage
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY telegram_bot/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Pre-download deepvk/USER-base model for semantic cache (500MB)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('deepvk/USER-base')"

# Runtime stage
FROM python:3.12-slim AS runtime

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy pre-downloaded model from builder
COPY --from=builder /root/.cache/huggingface /home/botuser/.cache/huggingface

# Copy application code
COPY telegram_bot/ ./telegram_bot/

# Create non-root user and set permissions for model cache
RUN useradd -m -u 1000 botuser && \
    chown -R botuser:botuser /app && \
    chown -R botuser:botuser /home/botuser/.cache
USER botuser

# Environment variables (defaults, override in docker-compose)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Health check - verify bot module can be imported
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "from telegram_bot.bot import PropertyBot" || exit 1

# Run bot
CMD ["python", "-m", "telegram_bot.main"]
```

**Step 2: Commit**

```bash
git add telegram_bot/Dockerfile
git commit -m "build(docker): pre-download USER-base model in image"
```

---

### Task 9: Update docker-compose memory limit

**Files:**
- Modify: `docker-compose.dev.yml:238-240`

**Step 1: Increase bot memory limit**

Change lines 238-240 from:
```yaml
    deploy:
      resources:
        limits:
          memory: 512M
```
to:
```yaml
    deploy:
      resources:
        limits:
          memory: 3G
```

**Step 2: Commit**

```bash
git add docker-compose.dev.yml
git commit -m "build(docker): increase bot memory to 3G for USER-base model"
```

---

### Task 10: Run tests locally (verify implementation)

**Prerequisites:** Redis running locally or via Docker

**Step 1: Install sentence-transformers locally**

Run: `pip install sentence-transformers>=2.2.0`

**Step 2: Run morphology tests**

Run: `pytest tests/test_cache_russian_morphology.py -v`
Expected: All tests PASS (USER-base handles Russian morphology)

**Step 3: Run all cache tests**

Run: `pytest tests/test_cache_service.py tests/test_cache_russian_morphology.py -v`
Expected: All tests PASS

---

### Task 11: Migrate Redis index

**Prerequisites:** Docker services running (`docker compose -f docker-compose.dev.yml up -d redis`)

**Step 1: Drop old index**

Run: `docker exec dev-redis redis-cli FT.DROPINDEX rag_llm_cache DD`
Expected: OK (or error if index doesn't exist - that's fine)

**Step 2: Drop old conversation index**

Run: `docker exec dev-redis redis-cli FT.DROPINDEX rag_conversations DD`
Expected: OK (or error if index doesn't exist - that's fine)

**Step 3: Verify indexes dropped**

Run: `docker exec dev-redis redis-cli FT._LIST`
Expected: Should not contain `rag_llm_cache` or `rag_conversations`

---

### Task 12: Build Docker image

**Step 1: Build bot image**

Run: `docker compose -f docker-compose.dev.yml build bot`
Expected: Build succeeds (model download ~500MB, may take 5-10 min)

**Step 2: Verify image size**

Run: `docker images | grep bot`
Expected: Image ~2-3GB (includes model)

---

### Task 13: Deploy and verify bot

**Step 1: Start bot**

Run: `docker compose -f docker-compose.dev.yml up -d bot`

**Step 2: Check logs for initialization**

Run: `docker logs dev-bot 2>&1 | grep -E "(USER-base|SemanticCache)"`
Expected: Lines containing "deepvk/USER-base" and "SemanticCache initialized"

**Step 3: Verify bot is running**

Run: `docker ps --filter name=dev-bot --format "table {{.Names}}\t{{.Status}}"`
Expected: dev-bot with "Up" status

---

### Task 14: Integration test via Telegram

**Step 1: Send first query**

Send to bot: `вид рассрочки`
Expected: Bot responds with installment info, logs show "Semantic cache MISS"

**Step 2: Send morphologically similar query**

Send to bot: `рассрочки вид`
Expected: Bot responds quickly, logs show "Semantic cache HIT"

**Step 3: Send plural form**

Send to bot: `виды рассрочек`
Expected: Bot responds, logs show "Semantic cache HIT"

**Step 4: Verify cache hits in logs**

Run: `docker logs dev-bot 2>&1 | grep -E "cache (HIT|MISS)" | tail -20`
Expected: HIT messages for morphologically similar queries

---

### Task 15: Commit final state and tag release

**Step 1: Run full test suite**

Run: `pytest tests/test_cache_*.py -v`
Expected: All tests PASS

**Step 2: Create release commit**

```bash
git add -A
git commit -m "feat(cache): migrate semantic cache to deepvk/USER-base

- Replace VoyageAI voyage-3-lite with local deepvk/USER-base
- STS score 74.35 on ruMTEB (vs ~60 for voyage-3-lite)
- Zero API cost, 50-100ms latency (vs 200-500ms)
- Better Russian morphology handling (word order, plural/singular)
- Tighter distance threshold (0.15 vs 0.30)

BREAKING: Redis cache index rebuilt (different dimensions 512→768)"
```

**Step 3: Tag release (optional)**

```bash
git tag -a v2.13.0 -m "feat: semantic cache with deepvk/USER-base"
```

---

## Ожидаемые результаты

| Метрика | До | После |
|---------|-----|-------|
| Cache hit rate | 25% | **60-70%** |
| Latency (HIT) | 200-500ms | **50-100ms** |
| Cost | $0.10/day | **$0** |
| Russian accuracy | Poor | **Good** |

## Тесты

| Тест | Ожидание |
|------|----------|
| `test_word_order_variation_hits_cache` | PASS - "вид рассрочки" = "рассрочки вид" |
| `test_plural_singular_hits_cache` | PASS - "вид рассрочки" = "виды рассрочек" |
| `test_verb_noun_forms_hits_cache` | PASS - "купить квартиру" = "покупка квартиры" |
| `test_different_intent_misses_cache` | PASS - "купить" ≠ "продать" |
| `test_different_topic_misses_cache` | PASS - "рассрочка" ≠ "ипотека" |
| `test_cache_check_latency_under_200ms` | PASS - <200ms |

## Риски

1. **Первый запуск медленный** - скачивание модели 500MB (решение: pre-download в Dockerfile)
2. **RAM увеличится на ~1GB** - нужен контейнер 3GB+
3. **Потеря кеша** - одноразово при миграции (dimensions changed 512→768)
