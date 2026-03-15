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

    with patch("telegram_bot.services.kommo_tokens.httpx.AsyncClient") as mock_httpx:
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


async def test_force_refresh_concurrent_calls_serialized(mock_redis):
    """Concurrent force_refresh calls must be serialized via asyncio.Lock (#948 bug 5).

    Without a lock, two concurrent refreshes can interleave and both use the
    same (now-invalidated) refresh_token, causing the second to fail with 400.
    With a lock, only one HTTP refresh runs at a time.
    """
    import asyncio

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

    call_log: list[str] = []
    can_proceed = asyncio.Event()

    async def controlled_post(*args, **kwargs):
        call_log.append("http_start")
        await can_proceed.wait()
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "access_token": "new-token",
            "refresh_token": "new-refresh",
            "expires_in": 86400,
        }
        call_log.append("http_end")
        return resp

    with patch("telegram_bot.services.kommo_tokens.httpx.AsyncClient") as mock_httpx:
        mock_httpx.return_value.__aenter__ = AsyncMock(return_value=mock_httpx.return_value)
        mock_httpx.return_value.__aexit__ = AsyncMock()
        mock_httpx.return_value.post = controlled_post

        task1 = asyncio.create_task(store.force_refresh())
        await asyncio.sleep(0)  # Let task1 acquire lock and reach controlled_post
        task2 = asyncio.create_task(store.force_refresh())
        await asyncio.sleep(0)  # Let task2 try to acquire lock

        # With lock: task1 is in controlled_post (http_start logged), task2 waits for lock
        assert call_log == ["http_start"], (
            "With asyncio.Lock, only one force_refresh HTTP call should be in-flight at a time. "
            f"Got call_log={call_log!r} — Lock missing in force_refresh()"
        )

        can_proceed.set()
        await asyncio.gather(task1, task2)

    # Both calls completed, second one also made HTTP request after first finished
    assert "http_end" in call_log


async def test_legacy_store_tokens_method_still_available(mock_redis):
    """Compatibility shim must preserve _store_tokens for legacy callers/scripts."""
    from unittest.mock import AsyncMock

    from telegram_bot.services.kommo_token_store import KommoTokenStore

    storage: dict[str, str] = {}

    async def hset(_key, *, mapping):
        storage.update({str(k): str(v) for k, v in mapping.items()})

    async def hgetall(_key):
        return {k.encode(): v.encode() for k, v in storage.items()}

    redis = AsyncMock()
    redis.hset.side_effect = hset
    redis.hgetall.side_effect = hgetall

    store = KommoTokenStore(redis=redis, subdomain="test")

    await store._store_tokens("seed-token", "", 3600)

    token = await store.get_valid_token()
    assert token == "seed-token"
