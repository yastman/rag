# tests/smoke/conftest.py
"""Smoke test fixtures - require live Qdrant and Redis."""

import asyncio
import os

import httpx
import pytest
import redis.asyncio as redis

from telegram_bot.integrations.cache import CacheLayerManager
from telegram_bot.services.qdrant import QdrantService


@pytest.fixture(scope="module")
def redis_url() -> str:
    """Redis URL for smoke tests, with REDIS_PASSWORD injected if not embedded.

    Mirrors `scripts/validate_traces.py::_build_redis_url` so smoke tests work
    against Compose dev defaults (auth-required Redis) without per-test plumbing.
    """
    base = os.getenv("REDIS_URL", "redis://localhost:6379")
    password = os.getenv("REDIS_PASSWORD", "")
    if password and "@" not in base:
        base = base.replace("redis://", f"redis://:{password}@", 1)
    return base


@pytest.fixture(scope="module")
def require_live_services(request):
    """Skip if live services not available. Checks BOTH Qdrant AND Redis."""
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    redis_url = request.getfixturevalue("redis_url")

    # Check Qdrant
    try:
        resp = httpx.get(f"{qdrant_url}/collections", timeout=2)
        if resp.status_code != 200:
            pytest.skip("Qdrant not available")
    except (httpx.HTTPError, OSError):
        pytest.skip("Qdrant not available")

    # Check Redis
    async def check_redis():
        try:
            client = redis.from_url(redis_url, socket_connect_timeout=2)
            await client.ping()
            await client.aclose()
        except (redis.RedisError, OSError):
            pytest.skip("Redis not available")

    asyncio.run(check_redis())


@pytest.fixture(scope="module")
async def voyage_service():
    """VoyageService for embeddings."""
    api_key = os.getenv("VOYAGE_API_KEY")
    if not api_key:
        pytest.skip("VOYAGE_API_KEY not set")
    try:
        from telegram_bot.services.voyage import VoyageService
    except Exception as exc:  # pragma: no cover - depends on optional third-party packages
        pytest.skip(f"Voyage stack unavailable in this environment: {exc}")
    return VoyageService(api_key=api_key)


@pytest.fixture(scope="module")
async def qdrant_service():
    """QdrantService for search."""
    url = os.getenv("QDRANT_URL", "http://localhost:6333")
    api_key = os.getenv("QDRANT_API_KEY", "")
    collection = os.getenv("QDRANT_COLLECTION", "gdrive_documents_bge")

    service = QdrantService(
        url=url,
        api_key=api_key or None,
        collection_name=collection,
    )
    yield service
    await service.close()


@pytest.fixture(scope="module")
async def cache_service(request):
    """CacheLayerManager for caching."""
    redis_url = request.getfixturevalue("redis_url")
    service = CacheLayerManager(redis_url=redis_url)
    await service.initialize()
    yield service
    await service.close()
