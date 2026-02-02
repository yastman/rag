"""Test EmbeddingsCache with correct RedisVL API."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_embeddings_cache():
    """Mock EmbeddingsCache."""
    cache = MagicMock()
    cache.aget = AsyncMock(return_value={"embedding": [0.1, 0.2, 0.3]})
    cache.aset = AsyncMock(return_value="key:123")
    return cache


@pytest.mark.asyncio
async def test_get_cached_embedding_uses_content_param(mock_embeddings_cache):
    """EmbeddingsCache.aget should use 'content' not 'text' parameter."""
    from telegram_bot.services.cache import CacheService

    service = CacheService(redis_url="redis://localhost:6379")
    service.embeddings_cache = mock_embeddings_cache

    result = await service.get_cached_embedding("test query", "voyage-3-large")

    # Verify aget was called with 'content' parameter
    mock_embeddings_cache.aget.assert_called_once_with(
        content="test query",
        model_name="voyage-3-large",
    )
    assert result == [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_store_embedding_uses_content_param(mock_embeddings_cache):
    """EmbeddingsCache.aset should use 'content' not 'text' parameter."""
    from telegram_bot.services.cache import CacheService

    service = CacheService(redis_url="redis://localhost:6379")
    service.embeddings_cache = mock_embeddings_cache

    await service.store_embedding(
        text="test query",
        embedding=[0.1, 0.2, 0.3],
        model_name="voyage-3-large",
        metadata={"source": "test"},
    )

    # Verify aset was called with 'content' parameter
    mock_embeddings_cache.aset.assert_called_once_with(
        content="test query",
        model_name="voyage-3-large",
        embedding=[0.1, 0.2, 0.3],
        metadata={"source": "test"},
    )
