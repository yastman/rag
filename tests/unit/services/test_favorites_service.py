"""Unit tests for FavoritesService (#628)."""

from __future__ import annotations

import datetime as dt
from unittest.mock import AsyncMock, MagicMock

import pytest
from asyncpg import UniqueViolationError

from telegram_bot.services.favorites_service import Favorite, FavoritesService


@pytest.fixture
def mock_pool() -> MagicMock:
    pool = MagicMock()
    pool.fetchrow = AsyncMock()
    pool.fetch = AsyncMock()
    pool.execute = AsyncMock()
    pool.fetchval = AsyncMock()
    return pool


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------


async def test_add(mock_pool: MagicMock) -> None:
    now = dt.datetime(2026, 2, 24, tzinfo=dt.UTC)
    mock_pool.fetchrow.return_value = {
        "id": 1,
        "property_id": "prop-42",
        "property_data": {"price": 100000},
        "created_at": now,
    }

    svc = FavoritesService(pool=mock_pool)
    result = await svc.add(
        telegram_id=123,
        property_id="prop-42",
        property_data={"price": 100000},
    )

    assert result is not None
    assert result["property_id"] == "prop-42"
    mock_pool.fetchrow.assert_awaited_once()


async def test_add_duplicate_returns_none(mock_pool: MagicMock) -> None:
    mock_pool.fetchrow.side_effect = UniqueViolationError("")

    svc = FavoritesService(pool=mock_pool)
    result = await svc.add(
        telegram_id=123,
        property_id="prop-42",
        property_data={},
    )

    assert result is None


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------


async def test_remove(mock_pool: MagicMock) -> None:
    mock_pool.execute.return_value = "DELETE 1"

    svc = FavoritesService(pool=mock_pool)
    deleted = await svc.remove(telegram_id=123, property_id="prop-42")

    assert deleted is True
    mock_pool.execute.assert_awaited_once()


async def test_remove_nonexistent(mock_pool: MagicMock) -> None:
    mock_pool.execute.return_value = "DELETE 0"

    svc = FavoritesService(pool=mock_pool)
    deleted = await svc.remove(telegram_id=123, property_id="prop-99")

    assert deleted is False


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


async def test_list(mock_pool: MagicMock) -> None:
    now = dt.datetime(2026, 2, 24, tzinfo=dt.UTC)
    mock_pool.fetch.return_value = [
        {"id": 1, "property_id": "prop-1", "property_data": {"price": 50000}, "created_at": now},
        {"id": 2, "property_id": "prop-2", "property_data": {}, "created_at": now},
    ]

    svc = FavoritesService(pool=mock_pool)
    favorites = await svc.list(telegram_id=123)

    assert len(favorites) == 2
    assert isinstance(favorites[0], Favorite)
    assert favorites[0].property_id == "prop-1"
    assert favorites[1].property_id == "prop-2"
    mock_pool.fetch.assert_awaited_once()


async def test_list_empty(mock_pool: MagicMock) -> None:
    mock_pool.fetch.return_value = []

    svc = FavoritesService(pool=mock_pool)
    favorites = await svc.list(telegram_id=999)

    assert favorites == []


# ---------------------------------------------------------------------------
# count
# ---------------------------------------------------------------------------


async def test_count(mock_pool: MagicMock) -> None:
    mock_pool.fetchval.return_value = 7

    svc = FavoritesService(pool=mock_pool)
    n = await svc.count(telegram_id=123)

    assert n == 7
    mock_pool.fetchval.assert_awaited_once()


# ---------------------------------------------------------------------------
# is_favorited
# ---------------------------------------------------------------------------


async def test_is_favorited(mock_pool: MagicMock) -> None:
    mock_pool.fetchval.return_value = 1

    svc = FavoritesService(pool=mock_pool)
    assert await svc.is_favorited(telegram_id=123, property_id="prop-42") is True

    mock_pool.fetchval.return_value = None
    assert await svc.is_favorited(telegram_id=123, property_id="prop-99") is False
