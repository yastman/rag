"""Tests for ApartmentsService.get_distinct_values."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.apartments_service import ApartmentsService


@pytest.fixture
def svc() -> ApartmentsService:
    qdrant = MagicMock()
    qdrant.collection_name = "apartments"
    return ApartmentsService(qdrant=qdrant)


async def test_get_distinct_values_returns_sorted_unique(svc: ApartmentsService) -> None:
    """get_distinct_values returns sorted unique values for a field."""
    # Mock scroll returning records with duplicate cities
    record1 = MagicMock()
    record1.payload = {"city": "Свети Влас"}
    record1.id = "1"
    record2 = MagicMock()
    record2.payload = {"city": "Солнечный берег"}
    record2.id = "2"
    record3 = MagicMock()
    record3.payload = {"city": "Свети Влас"}  # duplicate
    record3.id = "3"

    svc._qdrant.client.scroll = AsyncMock(
        side_effect=[
            ([record1, record2, record3], None),  # first page, no next offset
        ]
    )

    result = await svc.get_distinct_values("city")
    assert result == ["Свети Влас", "Солнечный берег"]


async def test_get_distinct_values_empty_collection(svc: ApartmentsService) -> None:
    """get_distinct_values returns empty list for empty collection."""
    svc._qdrant.client.scroll = AsyncMock(return_value=([], None))

    result = await svc.get_distinct_values("city")
    assert result == []


async def test_get_distinct_values_skips_empty_strings(svc: ApartmentsService) -> None:
    """get_distinct_values skips records with empty or missing field values."""
    record1 = MagicMock()
    record1.payload = {"section": "A"}
    record1.id = "1"
    record2 = MagicMock()
    record2.payload = {"section": ""}
    record2.id = "2"
    record3 = MagicMock()
    record3.payload = {}
    record3.id = "3"

    svc._qdrant.client.scroll = AsyncMock(return_value=([record1, record2, record3], None))

    result = await svc.get_distinct_values("section")
    assert result == ["A"]


# ---------------------------------------------------------------------------
# Redis cache tests — Issue #846
# ---------------------------------------------------------------------------


async def test_get_distinct_values_cache_hit_skips_qdrant(svc: ApartmentsService) -> None:
    """On Redis cache hit, Qdrant scroll must NOT be called."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=json.dumps(["Банско", "Бургас"]))

    svc._qdrant.client.scroll = AsyncMock()

    result = await svc.get_distinct_values("city", redis=mock_redis)

    assert result == ["Банско", "Бургас"]
    svc._qdrant.client.scroll.assert_not_called()


async def test_get_distinct_values_cache_miss_queries_qdrant_and_stores(
    svc: ApartmentsService,
) -> None:
    """On Redis cache miss, Qdrant is queried and result is stored in Redis."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.setex = AsyncMock()

    record = MagicMock()
    record.payload = {"city": "Банско"}
    svc._qdrant.client.scroll = AsyncMock(return_value=([record], None))

    result = await svc.get_distinct_values("city", redis=mock_redis)

    assert result == ["Банско"]
    svc._qdrant.client.scroll.assert_called_once()
    mock_redis.setex.assert_called_once()
    # Verify the stored value is JSON-serialisable
    call_args = mock_redis.setex.call_args
    stored_json = call_args[0][2]
    assert json.loads(stored_json) == ["Банско"]


async def test_get_distinct_values_no_redis_works_as_before(svc: ApartmentsService) -> None:
    """Without redis kwarg, behaviour is identical to original (no cache)."""
    record = MagicMock()
    record.payload = {"city": "Варна"}
    svc._qdrant.client.scroll = AsyncMock(return_value=([record], None))

    result = await svc.get_distinct_values("city")

    assert result == ["Варна"]
    svc._qdrant.client.scroll.assert_called_once()


async def test_get_distinct_values_redis_cache_key_includes_field(
    svc: ApartmentsService,
) -> None:
    """Redis cache key must include the field name to avoid collisions."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=json.dumps(["A", "B"]))

    await svc.get_distinct_values("complex_name", redis=mock_redis)

    called_key: str = mock_redis.get.call_args[0][0]
    assert "complex_name" in called_key
