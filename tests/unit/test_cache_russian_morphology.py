"""Tests for Russian morphology handling in semantic cache.

Tests that deepvk/USER-base model correctly handles:
- Word order variations (вид рассрочки vs рассрочки вид)
- Morphological forms (купить vs покупка)
- Singular/plural (рассрочка vs рассрочки)

NOTE: These are integration tests requiring redisvl + live Redis.
"""

import importlib.util
import os

import pytest


if importlib.util.find_spec("redisvl") is None:
    pytest.skip("redisvl not installed (integration test)", allow_module_level=True)

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
