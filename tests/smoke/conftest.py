# tests/smoke/conftest.py
"""Smoke test fixtures - require live Qdrant and Redis."""

import asyncio
import os

import httpx
import pytest
import redis.asyncio as redis

from telegram_bot.services.cache import CacheService
from telegram_bot.services.qdrant import QdrantService
from telegram_bot.services.voyage import VoyageService


@pytest.fixture(scope="module")
def require_live_services():
    """Skip if live services not available. Checks BOTH Qdrant AND Redis."""
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")

    # Check Qdrant
    try:
        resp = httpx.get(f"{qdrant_url}/collections", timeout=2)
        if resp.status_code != 200:
            pytest.skip("Qdrant not available")
    except Exception:
        pytest.skip("Qdrant not available")

    # Check Redis
    async def check_redis():
        try:
            client = redis.from_url(redis_url, socket_connect_timeout=2)
            await client.ping()
            await client.close()
        except Exception:
            pytest.skip("Redis not available")

    asyncio.get_event_loop().run_until_complete(check_redis())


@pytest.fixture(scope="module")
async def voyage_service():
    """VoyageService for embeddings."""
    api_key = os.getenv("VOYAGE_API_KEY")
    if not api_key:
        pytest.skip("VOYAGE_API_KEY not set")
    return VoyageService(api_key=api_key)


@pytest.fixture(scope="module")
async def qdrant_service():
    """QdrantService for search."""
    url = os.getenv("QDRANT_URL", "http://localhost:6333")
    api_key = os.getenv("QDRANT_API_KEY", "")
    collection = os.getenv("QDRANT_COLLECTION", "contextual_bulgaria_voyage4")

    service = QdrantService(
        url=url,
        api_key=api_key or None,
        collection_name=collection,
    )
    yield service
    await service.close()


@pytest.fixture(scope="module")
async def cache_service():
    """CacheService for caching."""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    service = CacheService(redis_url=redis_url)
    await service.initialize()
    yield service
    await service.close()
