"""Redis-backed OAuth2 token store for Kommo CRM.

Handles token lifecycle: initial exchange, auto-refresh, persistence.
Pattern: stateless reads (Redis), atomic writes.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx


logger = logging.getLogger(__name__)

REDIS_KEY = "kommo:oauth:tokens"
REFRESH_BUFFER_SEC = 300  # refresh 5 min before expiry


class KommoTokenStore:
    """Manage Kommo OAuth2 tokens with Redis persistence."""

    def __init__(
        self,
        *,
        redis: Any,
        client_id: str,
        client_secret: str,
        subdomain: str,
        redirect_uri: str,
    ) -> None:
        self._redis = redis
        self._client_id = client_id
        self._client_secret = client_secret
        self._subdomain = subdomain
        self._redirect_uri = redirect_uri
        self._token_url = f"https://{subdomain}.kommo.com/oauth2/access_token"

    async def get_valid_token(self) -> str:
        """Return valid access_token, refreshing if near expiry."""
        data = await self._load_tokens()
        if not data:
            msg = "No Kommo tokens found in Redis. Call initialize() first."
            raise RuntimeError(msg)

        access_token = data.get("access_token", "")
        refresh_token = data.get("refresh_token", "")
        expires_at = int(data.get("expires_at", 0))

        if time.time() + REFRESH_BUFFER_SEC >= expires_at:
            logger.info("Kommo token near expiry, refreshing")
            return await self._refresh_tokens(refresh_token)

        return access_token

    async def force_refresh(self) -> str:
        """Force token refresh (e.g. after 401)."""
        data = await self._load_tokens()
        refresh_token = data.get("refresh_token", "") if data else ""
        if not refresh_token:
            msg = "No refresh_token available for Kommo."
            raise RuntimeError(msg)
        return await self._refresh_tokens(refresh_token)

    async def initialize(self, authorization_code: str | None = None) -> str:
        """First-time setup: exchange auth code for token pair.

        If tokens already exist in Redis, returns the current valid token.
        """
        if authorization_code:
            return await self._exchange_auth_code(authorization_code)

        # Try loading existing tokens
        data = await self._load_tokens()
        if data and data.get("access_token"):
            return await self.get_valid_token()

        msg = "No Kommo tokens and no authorization_code provided."
        raise RuntimeError(msg)

    async def _exchange_auth_code(self, code: str) -> str:
        """Exchange authorization code for access + refresh tokens."""
        payload = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._redirect_uri,
        }
        resp = await self._token_request(payload)
        await self._save_tokens(
            access_token=resp["access_token"],
            refresh_token=resp["refresh_token"],
            expires_in=resp["expires_in"],
        )
        return resp["access_token"]

    async def _refresh_tokens(self, refresh_token: str) -> str:
        """Refresh the access token using refresh_token."""
        payload = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "redirect_uri": self._redirect_uri,
        }
        resp = await self._token_request(payload)
        await self._save_tokens(
            access_token=resp["access_token"],
            refresh_token=resp["refresh_token"],
            expires_in=resp["expires_in"],
        )
        return resp["access_token"]

    async def _token_request(self, payload: dict) -> dict:
        """POST to Kommo OAuth2 token endpoint."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(self._token_url, json=payload)
            response.raise_for_status()
            return response.json()

    async def _save_tokens(self, *, access_token: str, refresh_token: str, expires_in: int) -> None:
        """Persist tokens to Redis hash."""
        expires_at = int(time.time()) + expires_in
        await self._redis.hset(
            REDIS_KEY,
            mapping={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": str(expires_at),
                "subdomain": self._subdomain,
            },
        )
        logger.info("Kommo tokens saved (expires_in=%ds)", expires_in)

    async def _load_tokens(self) -> dict[str, str] | None:
        """Load tokens from Redis hash."""
        raw = await self._redis.hgetall(REDIS_KEY)
        if not raw:
            return None
        # Decode bytes → str
        return {
            k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v
            for k, v in raw.items()
        }
