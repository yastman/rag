# tests/smoke/conftest.py
"""Smoke test fixtures - require live Qdrant and Redis.

URL/credential fixtures (``redis_url``, ``qdrant_url``, ``qdrant_api_key``,
``qdrant_collection``) are owned by ``tests/fixtures/config.py`` and
registered globally in ``tests/conftest.py`` (issues #2066, #1515 D4).
This module only declares smoke-tier-specific fixtures (live-service
guard, service clients).
"""

import asyncio

import httpx
import pytest
import redis.asyncio as redis

from src.runtime.integrations.cache import CacheLayerManager
from src.runtime.services.qdrant import QdrantService


@pytest.fixture(scope="module")
def require_live_services(qdrant_url, redis_url):
    """Skip if live services not available. Checks BOTH Qdrant AND Redis."""
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
            await client.aclose()
        except Exception:
            pytest.skip("Redis not available")

    asyncio.run(check_redis())


@pytest.fixture(scope="module")
async def qdrant_service(qdrant_url, qdrant_api_key, qdrant_collection):
    """QdrantService for search.

    Reuses the root URL / credential / collection fixtures from
    ``tests/fixtures/config.py`` (issue #1515 D4).
    """
    service = QdrantService(
        url=qdrant_url,
        api_key=qdrant_api_key or None,
        collection_name=qdrant_collection,
    )
    yield service
    await service.close()


@pytest.fixture(scope="module")
async def cache_service(redis_url):
    """CacheLayerManager for caching."""
    service = CacheLayerManager(redis_url=redis_url)
    await service.initialize()
    yield service
    await service.close()
