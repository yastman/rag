"""Tests for Kommo OAuth2 token store (Redis-backed)."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def mock_redis():
    """Create a mock async Redis client."""
    redis = AsyncMock()
    redis.hgetall = AsyncMock(return_value={})
    redis.hset = AsyncMock()
    redis.close = AsyncMock()
    return redis


@pytest.fixture
def token_store(mock_redis):
    from telegram_bot.services.kommo_tokens import KommoTokenStore

    return KommoTokenStore(
        redis=mock_redis,
        client_id="test_client_id",
        client_secret="test_secret",
        subdomain="testcompany",
        redirect_uri="https://example.com/callback",
    )


class TestKommoTokenStore:
    async def test_get_valid_token_from_cache(self, token_store, mock_redis):
        """Return cached token when not expired."""
        future_ts = str(int(time.time()) + 3600)
        mock_redis.hgetall.return_value = {
            b"access_token": b"cached_token",
            b"refresh_token": b"refresh_123",
            b"expires_at": future_ts.encode(),
        }
        token = await token_store.get_valid_token()
        assert token == "cached_token"

    async def test_get_valid_token_refreshes_when_near_expiry(self, token_store, mock_redis):
        """Auto-refresh when token expires within REFRESH_BUFFER_SEC."""
        near_expiry_ts = str(int(time.time()) + 60)  # 60s left, buffer is 300s
        mock_redis.hgetall.return_value = {
            b"access_token": b"old_token",
            b"refresh_token": b"refresh_123",
            b"expires_at": near_expiry_ts.encode(),
        }
        with patch.object(token_store, "_refresh_tokens", new_callable=AsyncMock) as mock_refresh:
            mock_refresh.return_value = "new_token"
            token = await token_store.get_valid_token()
            assert token == "new_token"
            mock_refresh.assert_called_once_with("refresh_123")

    async def test_get_valid_token_raises_when_no_tokens(self, token_store, mock_redis):
        """Raise when no tokens stored and no auth code."""
        mock_redis.hgetall.return_value = {}
        with pytest.raises(RuntimeError, match="No Kommo tokens"):
            await token_store.get_valid_token()

    async def test_force_refresh(self, token_store, mock_redis):
        """Force refresh retrieves new tokens."""
        mock_redis.hgetall.return_value = {
            b"access_token": b"old",
            b"refresh_token": b"refresh_123",
            b"expires_at": b"0",
        }
        with patch.object(token_store, "_refresh_tokens", new_callable=AsyncMock) as mock_refresh:
            mock_refresh.return_value = "brand_new_token"
            token = await token_store.force_refresh()
            assert token == "brand_new_token"

    async def test_initialize_with_auth_code(self, token_store, mock_redis):
        """Exchange auth code for initial tokens."""
        with patch.object(
            token_store, "_exchange_auth_code", new_callable=AsyncMock
        ) as mock_exchange:
            mock_exchange.return_value = "initial_token"
            token = await token_store.initialize(authorization_code="auth_code_123")
            assert token == "initial_token"
            mock_exchange.assert_called_once_with("auth_code_123")

    async def test_initialize_prefers_cached_token_over_auth_code(self, token_store, mock_redis):
        """Existing valid token should be reused even if auth code is provided."""
        future_ts = str(int(time.time()) + 3600)
        mock_redis.hgetall.return_value = {
            b"access_token": b"cached_token",
            b"refresh_token": b"refresh_123",
            b"expires_at": future_ts.encode(),
        }
        with patch.object(
            token_store, "_exchange_auth_code", new_callable=AsyncMock
        ) as mock_exchange:
            token = await token_store.initialize(authorization_code="auth_code_123")
            assert token == "cached_token"
            mock_exchange.assert_not_called()

    async def test_save_tokens_to_redis(self, token_store, mock_redis):
        """Verify tokens are persisted to Redis hash."""
        await token_store._save_tokens(
            access_token="at_123",
            refresh_token="rt_456",
            expires_in=86400,
        )
        mock_redis.hset.assert_called_once()
        call_kwargs = mock_redis.hset.call_args
        assert call_kwargs[0][0] == "kommo:oauth:tokens"  # key

    # --- #682: empty refresh_token must not trigger refresh ---

    async def test_get_valid_token_with_empty_refresh_returns_token_without_refresh(
        self, token_store, mock_redis
    ):
        """#682: expires_at=0 + empty refresh_token → return access_token as-is, no refresh call."""
        mock_redis.hgetall.return_value = {
            b"access_token": b"seeded_env_token",
            b"refresh_token": b"",
            b"expires_at": b"0",
        }
        with patch.object(token_store, "_refresh_tokens", new_callable=AsyncMock) as mock_refresh:
            token = await token_store.get_valid_token()
            assert token == "seeded_env_token"
            mock_refresh.assert_not_called()

    # --- #678 Task 3: seed_env_token method ---

    async def test_seed_env_token_writes_correct_mapping_to_redis(self, token_store, mock_redis):
        """#678 Task 3: seed_env_token writes access_token, empty refresh, expires_at=0."""
        await token_store.seed_env_token("env_access_token_abc")
        mock_redis.hset.assert_called_once()
        call_args = mock_redis.hset.call_args
        assert call_args[0][0] == "kommo:oauth:tokens"
        mapping = call_args[1]["mapping"]
        assert mapping["access_token"] == "env_access_token_abc"
        assert mapping["refresh_token"] == ""
        assert mapping["expires_at"] == "0"
        assert mapping["subdomain"] == "testcompany"

    async def test_get_valid_token_after_seed_env_token_returns_seeded_token(
        self, token_store, mock_redis
    ):
        """#678+#682: after seeding, get_valid_token returns seeded token without refresh attempt."""
        # Simulate seed written to Redis (expires_at=0, refresh_token="")
        mock_redis.hgetall.return_value = {
            b"access_token": b"live_env_token",
            b"refresh_token": b"",
            b"expires_at": b"0",
        }
        with patch.object(token_store, "_refresh_tokens", new_callable=AsyncMock) as mock_refresh:
            token = await token_store.get_valid_token()
            assert token == "live_env_token"
            mock_refresh.assert_not_called()

    async def test_initialize_with_seeded_token_does_not_raise(self, token_store, mock_redis):
        """#678+#682: initialize() with seeded token (no auth_code) succeeds without refresh."""
        mock_redis.hgetall.return_value = {
            b"access_token": b"seeded_token",
            b"refresh_token": b"",
            b"expires_at": b"0",
        }
        with patch.object(token_store, "_refresh_tokens", new_callable=AsyncMock) as mock_refresh:
            token = await token_store.initialize(authorization_code=None)
            assert token == "seeded_token"
            mock_refresh.assert_not_called()
