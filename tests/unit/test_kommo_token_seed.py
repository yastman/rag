"""Tests for Kommo access_token fallback seeding (#678)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from telegram_bot.services.kommo_tokens import REDIS_KEY


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.hgetall = AsyncMock(return_value={})
    redis.hset = AsyncMock()
    return redis


class TestKommoAccessTokenSeed:
    async def test_seed_access_token_when_redis_empty(self, mock_redis):
        from telegram_bot.bot import _seed_kommo_access_token

        seeded = await _seed_kommo_access_token(
            redis=mock_redis,
            access_token="eyJ0eXA...",
            subdomain="testdomain",
        )
        assert seeded is True
        mock_redis.hset.assert_called_once_with(
            REDIS_KEY,
            mapping={
                "access_token": "eyJ0eXA...",
                "subdomain": "testdomain",
            },
        )

    async def test_skip_seed_when_redis_has_tokens(self, mock_redis):
        mock_redis.hgetall = AsyncMock(
            return_value={b"access_token": b"existing", b"refresh_token": b"rf"}
        )
        from telegram_bot.bot import _seed_kommo_access_token

        seeded = await _seed_kommo_access_token(
            redis=mock_redis,
            access_token="new-token",
            subdomain="testdomain",
        )
        assert seeded is False
        mock_redis.hset.assert_not_called()

    async def test_skip_seed_when_no_access_token(self, mock_redis):
        from telegram_bot.bot import _seed_kommo_access_token

        seeded = await _seed_kommo_access_token(
            redis=mock_redis,
            access_token="",
            subdomain="testdomain",
        )
        assert seeded is False
        mock_redis.hset.assert_not_called()
