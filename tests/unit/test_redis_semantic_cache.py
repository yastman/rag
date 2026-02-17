import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.cache.redis_semantic_cache import RedisSemanticCache


@pytest.fixture
def mock_redis():
    with patch("src.cache.redis_semantic_cache.redis.from_url") as mock_from_url:
        mock_client = AsyncMock()
        mock_from_url.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_tracer():
    with patch("src.cache.redis_semantic_cache.trace.get_tracer") as mock_get_tracer:
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
        mock_get_tracer.return_value = mock_tracer
        yield mock_tracer


@pytest.fixture
def cache(mock_redis, mock_tracer):
    return RedisSemanticCache(redis_url="redis://localhost:6379/0", index_version="1.0.0")


async def test_get_embedding_hit(cache, mock_redis):
    # Setup
    query = "test query"
    embedding = [0.1, 0.2, 0.3]
    mock_redis.get.return_value = json.dumps(embedding)

    # Execute
    result = await cache.get_embedding(query)

    # Assert
    assert result == embedding
    assert cache.get_stats()["cache_hits"] == 1
    mock_redis.get.assert_called_once()
    # Check key format
    call_args = mock_redis.get.call_args[0][0]
    assert call_args.startswith("embedding_v1.0.0_")


async def test_get_embedding_miss(cache, mock_redis):
    # Setup
    mock_redis.get.return_value = None

    # Execute
    result = await cache.get_embedding("test query")

    # Assert
    assert result is None
    assert cache.get_stats()["cache_misses"] == 1


async def test_set_embedding(cache, mock_redis):
    # Setup
    query = "test query"
    embedding = [0.1, 0.2, 0.3]

    # Execute
    await cache.set_embedding(query, embedding)

    # Assert
    mock_redis.setex.assert_called_once()
    call_args = mock_redis.setex.call_args
    # Check TTL used
    assert call_args[0][1] == cache.embedding_ttl


async def test_get_response_hit(cache, mock_redis):
    # Setup
    query = "test query"
    start_response = {"results": ["doc1"]}
    mock_redis.get.return_value = json.dumps(start_response)

    # Execute
    result = await cache.get_response(query, top_k=10)

    # Assert
    assert result == start_response
    assert cache.get_stats()["cache_hits"] == 1
    # Check key format contains version and top_k
    call_args = mock_redis.get.call_args[0][0]
    assert "response_v1.0.0_" in call_args
    assert "_10" in call_args


async def test_set_response(cache, mock_redis):
    query = "test query"
    response = {"results": ["doc1"]}

    await cache.set_response(query, 10, response)

    mock_redis.setex.assert_called_once()
    assert mock_redis.setex.call_args[0][1] == cache.response_ttl


def test_initialization_defaults():
    with patch.dict("os.environ", {"REDIS_HOST": "test-host", "REDIS_PASSWORD": "pass"}):
        with patch("src.cache.redis_semantic_cache.redis.from_url") as mock_from_url:
            _cache = RedisSemanticCache()
            mock_from_url.assert_called_with("redis://:pass@test-host:6379/2")
