"""Edge-case tests for Kommo OAuth2 token store (Redis-backed)."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

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


class TestKommoTokenStoreEdgeCases:
    async def test_force_refresh_raises_when_no_refresh_token(self, token_store, mock_redis):
        """force_refresh() raises RuntimeError when Redis has no refresh token."""
        mock_redis.hgetall.return_value = {
            b"access_token": b"only_access",
        }
        with pytest.raises(RuntimeError, match="No refresh_token available for Kommo"):
            await token_store.force_refresh()

    async def test_force_refresh_raises_when_redis_empty(self, token_store, mock_redis):
        """force_refresh() raises RuntimeError when Redis is empty."""
        mock_redis.hgetall.return_value = {}
        with pytest.raises(RuntimeError, match="No refresh_token available for Kommo"):
            await token_store.force_refresh()

    async def test_exchange_auth_code_rejects_missing_access_token(self, token_store):
        """_exchange_auth_code() rejects missing access_token and does not save."""
        with (
            patch.object(token_store, "_token_request", new_callable=AsyncMock) as mock_request,
            patch.object(token_store, "_save_tokens", new_callable=AsyncMock) as mock_save,
        ):
            mock_request.return_value = {
                "refresh_token": "rt",
                "expires_in": 3600,
            }
            with pytest.raises(RuntimeError, match="Invalid OAuth2 token response from Kommo"):
                await token_store._exchange_auth_code("auth_code_123")
            mock_save.assert_not_called()

    async def test_exchange_auth_code_rejects_missing_refresh_token(self, token_store):
        """_exchange_auth_code() rejects missing refresh_token and does not save."""
        with (
            patch.object(token_store, "_token_request", new_callable=AsyncMock) as mock_request,
            patch.object(token_store, "_save_tokens", new_callable=AsyncMock) as mock_save,
        ):
            mock_request.return_value = {
                "access_token": "at",
                "expires_in": 3600,
            }
            with pytest.raises(RuntimeError, match="Invalid OAuth2 token response from Kommo"):
                await token_store._exchange_auth_code("auth_code_123")
            mock_save.assert_not_called()

    async def test_exchange_auth_code_rejects_missing_expires_in(self, token_store):
        """_exchange_auth_code() rejects missing/invalid expires_in and does not save."""
        with (
            patch.object(token_store, "_token_request", new_callable=AsyncMock) as mock_request,
            patch.object(token_store, "_save_tokens", new_callable=AsyncMock) as mock_save,
        ):
            mock_request.return_value = {
                "access_token": "at",
                "refresh_token": "rt",
                "expires_in": 0,
            }
            with pytest.raises(RuntimeError, match="Invalid OAuth2 token response from Kommo"):
                await token_store._exchange_auth_code("auth_code_123")
            mock_save.assert_not_called()

    async def test_refresh_tokens_rejects_malformed_response(self, token_store):
        """_refresh_tokens() rejects malformed refresh response and does not save."""
        with (
            patch.object(token_store, "_token_request", new_callable=AsyncMock) as mock_request,
            patch.object(token_store, "_save_tokens", new_callable=AsyncMock) as mock_save,
        ):
            mock_request.return_value = {
                "access_token": "",
                "refresh_token": "",
                "expires_in": 0,
            }
            with pytest.raises(RuntimeError, match="Invalid OAuth2 refresh response from Kommo"):
                await token_store._refresh_tokens("old_refresh")
            mock_save.assert_not_called()

    async def test_token_request_rejects_non_dict_json(self, token_store):
        """_token_request() rejects non-dict JSON response."""
        mock_response = MagicMock()
        mock_response.json.return_value = ["not", "a", "dict"]
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "telegram_bot.services.kommo_tokens.httpx.AsyncClient", return_value=mock_client
        ):
            with pytest.raises(RuntimeError, match="Unexpected Kommo OAuth2 response shape"):
                await token_store._token_request({"grant_type": "authorization_code"})

    async def test_load_tokens_decodes_mixed_bytes_and_str(self, token_store, mock_redis):
        """_load_tokens() decodes mixed bytes/str Redis hash values."""
        future_ts = str(int(time.time()) + 3600)
        mock_redis.hgetall.return_value = {
            b"access_token": "str_value",
            "refresh_token": b"bytes_value",
            "expires_at": future_ts,
        }
        result = await token_store._load_tokens()
        assert result is not None
        assert result["access_token"] == "str_value"
        assert result["refresh_token"] == "bytes_value"
        assert result["expires_at"] == future_ts

    async def test_load_tokens_decodes_bytes_keys_and_values(self, token_store, mock_redis):
        """_load_tokens() handles all-bytes Redis hash."""
        mock_redis.hgetall.return_value = {
            b"access_token": b"at",
            b"refresh_token": b"rt",
        }
        result = await token_store._load_tokens()
        assert result is not None
        assert result["access_token"] == "at"
        assert result["refresh_token"] == "rt"
