"""Kommo OAuth token store with security-first behavior (#389).

Stores access/refresh tokens in Redis. Handles expiration checks
and token refresh via Kommo OAuth2 endpoint.

Security:
- Token values are never logged
- LEAK_ROTATION_ORDER defines priority: rotate client_secret first, then tokens
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx


logger = logging.getLogger(__name__)


class KommoTokenStore:
    """Redis-backed Kommo OAuth token storage."""

    REDIS_KEY = "kommo:oauth:tokens"
    LEAK_ROTATION_ORDER = ("client_secret", "tokens")
    _TOKEN_EXPIRY_BUFFER_S = 300  # refresh 5 min before expiry

    def __init__(
        self,
        *,
        redis: Any,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        subdomain: str,
    ) -> None:
        self._redis = redis
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._subdomain = subdomain

    async def get_valid_token(self) -> str:
        """Return a valid access token, refreshing if near expiry."""
        data = await self._redis.hgetall(self.REDIS_KEY)
        if not data:
            raise RuntimeError("No Kommo tokens found — run initial OAuth exchange first")

        access_token = data.get(b"access_token", b"").decode()
        expires_at = int(data.get(b"expires_at", b"0").decode() or "0")

        if expires_at <= int(time.time()) + self._TOKEN_EXPIRY_BUFFER_S:
            logger.info("Kommo token near expiry, refreshing")
            return await self._refresh_token(refresh_token=data.get(b"refresh_token", b"").decode())
        return access_token

    async def _refresh_token(self, refresh_token: str) -> str:
        """Refresh access token via Kommo OAuth2 endpoint."""
        url = f"https://{self._subdomain}.kommo.com/oauth2/access_token"
        payload = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "redirect_uri": self._redirect_uri,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        new_access = data["access_token"]
        new_refresh = data["refresh_token"]
        expires_in = int(data.get("expires_in", 86400))

        await self._redis.hset(
            self.REDIS_KEY,
            mapping={
                "access_token": new_access,
                "refresh_token": new_refresh,
                "expires_at": str(int(time.time()) + expires_in),
            },
        )
        logger.info("Kommo token refreshed successfully")
        return new_access
