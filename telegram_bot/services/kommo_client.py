"""Kommo CRM async HTTP client with rate limiting (#389).

Enforces 7 req/s throttle (Kommo API limit) and handles HTTP 429
with Retry-After from response body or header.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any

import httpx


logger = logging.getLogger(__name__)


class KommoClient:
    """Async Kommo API client with rate limiting and 429 retry."""

    def __init__(
        self,
        *,
        subdomain: str,
        token_store: Any,
        rate_limit_rps: int = 7,
        max_retries: int = 3,
    ) -> None:
        self._base_url = f"https://{subdomain}.kommo.com/api/v4"
        self._token_store = token_store
        self._rate_limit_rps = rate_limit_rps
        self._max_retries = max_retries
        self._http = httpx.AsyncClient(base_url=self._base_url, timeout=20.0)
        self._request_times: deque[float] = deque()
        self._rate_lock = asyncio.Lock()

    async def _acquire_rate_slot(self) -> None:
        """Wait until a rate limit slot is available (sliding window)."""
        async with self._rate_lock:
            now = time.monotonic()
            while self._request_times and now - self._request_times[0] >= 1.0:
                self._request_times.popleft()
            if len(self._request_times) >= self._rate_limit_rps:
                wait_s = 1.0 - (now - self._request_times[0])
                await asyncio.sleep(max(wait_s, 0.0))
            self._request_times.append(time.monotonic())

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated API request with rate limiting and 429 retry."""
        for attempt in range(self._max_retries + 1):
            await self._acquire_rate_slot()
            token = await self._token_store.get_valid_token()
            response = await self._http.request(
                method,
                path,
                json=json,
                headers={"Authorization": f"Bearer {token}"},
            )

            if response.status_code == 429 and attempt < self._max_retries:
                # Kommo returns retry_after in JSON body; fallback to header
                payload = response.json() if response.content else {}
                retry_after = float(
                    payload.get("retry_after") or response.headers.get("Retry-After") or "1"
                )
                logger.warning(
                    "Kommo 429 on %s %s, retry_after=%.1fs (attempt %d/%d)",
                    method,
                    path,
                    retry_after,
                    attempt + 1,
                    self._max_retries,
                )
                await asyncio.sleep(retry_after)
                continue

            response.raise_for_status()
            return response.json()

        raise RuntimeError("Kommo request retries exhausted")  # pragma: no cover

    async def close(self) -> None:
        """Close underlying HTTP client."""
        await self._http.aclose()
