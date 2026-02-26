"""Redis-backed OAuth2 token store for Kommo CRM.

Handles token lifecycle: initial exchange, auto-refresh, persistence.
Pattern: stateless reads (Redis), atomic writes.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Protocol, cast, runtime_checkable

import httpx


logger = logging.getLogger(__name__)


@runtime_checkable
class KommoTokenStoreProtocol(Protocol):
    """Abstract token store contract for future Postgres migration (#384)."""

    async def get_valid_token(self) -> str: ...

    async def force_refresh(self) -> str: ...


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
        if not access_token:
            msg = "No Kommo access_token found in Redis."
            raise RuntimeError(msg)
        refresh_token = data.get("refresh_token", "")
        try:
            expires_at = int(data.get("expires_at", 0))
        except (TypeError, ValueError):
            expires_at = 0

        # Kommo OAuth refresh flow requires refresh_token. If only access_token is
        # available (seed/manual mode), use it as-is and let API 401 trigger handling.
        if not refresh_token:
            logger.info("Kommo token has no refresh_token; using cached access_token as-is")
            return access_token

        if time.time() + REFRESH_BUFFER_SEC >= expires_at:
            logger.info("Kommo token near expiry, refreshing")
            return await self._refresh_tokens(refresh_token)

        return access_token

    async def seed_env_token(self, access_token: str) -> None:
        """Seed Redis with a manually-provided access token when no OAuth flow ran yet.

        Used on first startup when only KOMMO_ACCESS_TOKEN env var is available.
        Stores empty refresh_token and expires_at=0 so get_valid_token() returns
        the token as-is (no refresh attempted) until a proper OAuth exchange occurs.
        """
        await self._redis.hset(
            REDIS_KEY,
            mapping={
                "access_token": access_token,
                "refresh_token": "",
                "expires_at": "0",
                "subdomain": self._subdomain,
            },
        )
        logger.info("Kommo access token seeded from env var (subdomain=%s)", self._subdomain)

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
        # Try loading existing tokens
        data = await self._load_tokens()
        if data and data.get("access_token"):
            return await self.get_valid_token()

        if authorization_code:
            return await self._exchange_auth_code(authorization_code)

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
        access_token = str(resp.get("access_token", ""))
        refresh_token = str(resp.get("refresh_token", ""))
        expires_in = int(resp.get("expires_in", 0))
        if not access_token or not refresh_token or expires_in <= 0:
            msg = "Invalid OAuth2 token response from Kommo."
            raise RuntimeError(msg)
        await self._save_tokens(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
        )
        return access_token

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
        access_token = str(resp.get("access_token", ""))
        new_refresh_token = str(resp.get("refresh_token", ""))
        expires_in = int(resp.get("expires_in", 0))
        if not access_token or not new_refresh_token or expires_in <= 0:
            msg = "Invalid OAuth2 refresh response from Kommo."
            raise RuntimeError(msg)
        await self._save_tokens(
            access_token=access_token,
            refresh_token=new_refresh_token,
            expires_in=expires_in,
        )
        return access_token

    async def _token_request(self, payload: dict) -> dict:
        """POST to Kommo OAuth2 token endpoint."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(self._token_url, json=payload)
            response.raise_for_status()
            response_json = response.json()
            if not isinstance(response_json, dict):
                msg = "Unexpected Kommo OAuth2 response shape."
                raise RuntimeError(msg)
            return cast(dict[str, Any], response_json)

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
        decoded: dict[str, str] = {}
        for key, value in raw.items():
            key_str = key.decode() if isinstance(key, bytes) else str(key)
            value_str = value.decode() if isinstance(value, bytes) else str(value)
            decoded[key_str] = value_str
        return decoded
