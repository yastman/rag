"""Redis-backed OAuth2 token store for Kommo CRM (#413).

Stores access_token + refresh_token in Redis hash.
Auto-refreshes via Kommo OAuth2 endpoint when expired.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx


logger = logging.getLogger(__name__)

REDIS_KEY_PREFIX = "kommo:tokens:"
TOKEN_REFRESH_BUFFER_S = 300  # Refresh 5 min before expiry


class KommoTokenStore:
    """Redis-backed Kommo OAuth2 token manager."""

    def __init__(
        self,
        *,
        redis: Any,
        subdomain: str,
        client_id: str = "",
        client_secret: str = "",
        redirect_uri: str = "",
    ):
        self._redis = redis
        self._subdomain = subdomain
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._key = f"{REDIS_KEY_PREFIX}{subdomain}"

    async def get_valid_token(self) -> str:
        """Get valid access token, refreshing if needed."""
        data = await self._redis.hgetall(self._key)
        if not data:
            raise ValueError(f"No token stored for {self._subdomain}")

        expires_at = int(data.get(b"expires_at", 0))
        if time.time() < expires_at - TOKEN_REFRESH_BUFFER_S:
            return data[b"access_token"].decode()

        return await self.force_refresh()

    async def force_refresh(self) -> str:
        """Force token refresh via Kommo OAuth2."""
        data = await self._redis.hgetall(self._key)
        refresh_token = data.get(b"refresh_token", b"").decode()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://{self._subdomain}.kommo.com/oauth2/access_token",
                json={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "redirect_uri": self._redirect_uri,
                },
            )
            response.raise_for_status()
            tokens = response.json()

        await self._store_tokens(
            tokens["access_token"],
            tokens["refresh_token"],
            tokens.get("expires_in", 86400),
        )
        return tokens["access_token"]

    async def store_initial(
        self,
        *,
        access_token: str,
        refresh_token: str,
        expires_in: int,
    ) -> None:
        """Store initial token set (from OAuth2 authorization code flow)."""
        await self._store_tokens(access_token, refresh_token, expires_in)

    async def _store_tokens(
        self,
        access_token: str,
        refresh_token: str,
        expires_in: int,
    ) -> None:
        """Save tokens to Redis hash with expiry timestamp."""
        expires_at = int(time.time()) + expires_in
        await self._redis.hset(
            self._key,
            mapping={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": str(expires_at),
            },
        )
        logger.info("Stored Kommo tokens for %s (expires_in=%ds)", self._subdomain, expires_in)
