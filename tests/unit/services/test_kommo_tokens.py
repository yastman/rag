"""Tests for Kommo OAuth token store (#389)."""

from unittest.mock import AsyncMock

import pytest

from telegram_bot.services.kommo_tokens import KommoTokenStore


@pytest.fixture
def redis_mock():
    redis = AsyncMock()
    redis.hgetall = AsyncMock(
        return_value={
            b"access_token": b"token_abc",
            b"refresh_token": b"token_refresh",
            b"expires_at": b"4102444800",  # 2100-01-01
        }
    )
    return redis


@pytest.fixture
def store(redis_mock):
    return KommoTokenStore(
        redis=redis_mock,
        client_id="id",
        client_secret="secret",
        redirect_uri="cb",
        subdomain="demo",
    )


async def test_get_valid_token_reads_cached_token(store):
    token = await store.get_valid_token()
    assert token == "token_abc"


async def test_token_not_in_logs(store, caplog):
    await store.get_valid_token()
    assert "token_abc" not in caplog.text


async def test_leak_rotation_order(store):
    assert store.LEAK_ROTATION_ORDER == ("client_secret", "tokens")


async def test_raises_when_no_tokens(redis_mock):
    redis_mock.hgetall = AsyncMock(return_value={})
    store = KommoTokenStore(
        redis=redis_mock,
        client_id="id",
        client_secret="secret",
        redirect_uri="cb",
        subdomain="demo",
    )
    with pytest.raises(RuntimeError, match="No Kommo tokens"):
        await store.get_valid_token()
