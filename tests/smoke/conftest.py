# tests/smoke/conftest.py
"""Smoke test fixtures - require live Qdrant and Redis."""

import asyncio
import os
from pathlib import Path

import httpx
import pytest
import redis.asyncio as redis

from telegram_bot.integrations.cache import CacheLayerManager
from telegram_bot.services.qdrant import QdrantService


_THIS_DIR = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-apply 'smoke' marker to all tests in this directory."""
    for item in items:
        if item.path.parent == _THIS_DIR or _THIS_DIR in item.path.parents:
            item.add_marker(pytest.mark.smoke)


def _build_redis_url() -> str:
    """Build Redis URL with password support.

    Reads REDIS_URL and REDIS_PASSWORD from env. If URL has no auth
    but REDIS_PASSWORD is set, injects password into URL.
    """
    url = os.getenv("REDIS_URL", "redis://localhost:6379")
    password = os.getenv("REDIS_PASSWORD", "")
    if password and "@" not in url:
        url = url.replace("redis://", f"redis://:{password}@", 1)
    return url


@pytest.fixture(scope="module")
def require_live_services():
    """Skip if live services not available. Checks BOTH Qdrant AND Redis."""
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    redis_url = _build_redis_url()

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

    asyncio.get_event_loop().run_until_complete(check_redis())


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
async def cache_service():
    """CacheLayerManager for caching."""
    redis_url = _build_redis_url()
    service = CacheLayerManager(redis_url=redis_url)
    await service.initialize()
    yield service
    await service.close()
