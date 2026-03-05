"""Tests for ApartmentsService.get_distinct_values."""

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
