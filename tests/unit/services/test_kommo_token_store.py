"""Tests for KommoTokenStore (Redis-backed OAuth2) (#413)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_redis():
    """Mock async Redis client."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=b"access-token-123")
    redis.set = AsyncMock()
    redis.hgetall = AsyncMock(
        return_value={
            b"access_token": b"access-token-123",
            b"refresh_token": b"refresh-token-456",
            b"expires_at": b"9999999999",
        }
    )
    redis.hset = AsyncMock()
    return redis


async def test_get_valid_token_from_cache(mock_redis):
    """Returns cached token when not expired."""
    from telegram_bot.services.kommo_token_store import KommoTokenStore

    store = KommoTokenStore(redis=mock_redis, subdomain="test")
    token = await store.get_valid_token()
    assert token == "access-token-123"


async def test_get_valid_token_refreshes_when_expired(mock_redis):
    """Refreshes token via OAuth2 when expired."""
    from telegram_bot.services.kommo_token_store import KommoTokenStore

    mock_redis.hgetall = AsyncMock(
        return_value={
            b"access_token": b"expired-token",
            b"refresh_token": b"refresh-456",
            b"expires_at": b"1000000000",  # Past
        }
    )

    store = KommoTokenStore(
        redis=mock_redis,
        subdomain="test",
        client_id="id",
        client_secret="secret",
        redirect_uri="https://example.com/callback",
    )

    with patch("telegram_bot.services.kommo_token_store.httpx.AsyncClient") as mock_httpx:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new-token",
            "refresh_token": "new-refresh",
            "expires_in": 86400,
        }
        mock_response.raise_for_status = MagicMock()
        mock_httpx.return_value.__aenter__ = AsyncMock(return_value=mock_httpx.return_value)
        mock_httpx.return_value.__aexit__ = AsyncMock()
        mock_httpx.return_value.post = AsyncMock(return_value=mock_response)

        token = await store.force_refresh()
        assert token == "new-token"


async def test_store_initial_sets_redis(mock_redis):
    """store_initial saves token data to Redis hash."""
    from telegram_bot.services.kommo_token_store import KommoTokenStore

    store = KommoTokenStore(redis=mock_redis, subdomain="test")
    await store.store_initial(
        access_token="tok-1",
        refresh_token="ref-1",
        expires_in=86400,
    )
    mock_redis.hset.assert_called_once()
