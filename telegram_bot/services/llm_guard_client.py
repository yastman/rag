"""Async HTTP client for LLM Guard prompt injection scanner.

Same pattern as BGEM3Client: httpx async client with retry/timeout.
Connects to the llm-guard Docker service (POST /scan/injection).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)


logger = logging.getLogger(__name__)

RETRYABLE_ERRORS = (
    httpx.RemoteProtocolError,
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
)

_guard_retry = retry(
    retry=retry_if_exception_type(RETRYABLE_ERRORS),
    wait=wait_exponential_jitter(initial=0.3, max=2, jitter=0.5),
    stop=stop_after_attempt(2),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)

DEFAULT_TIMEOUT = httpx.Timeout(connect=3.0, read=5.0, write=3.0, pool=3.0)


@dataclass
class ScanResult:
    """Result from POST /scan/injection."""

    detected: bool
    risk_score: float
    processing_time_ms: float


class LLMGuardClient:
    """Async HTTP client for LLM Guard API.

    Usage::

        client = LLMGuardClient("http://llm-guard:8100")
        result = await client.scan_injection("some text")
        if result.detected:
            print(f"Injection! score={result.risk_score}")
        await client.aclose()
    """

    def __init__(
        self,
        base_url: str = "http://llm-guard:8100",
        timeout: httpx.Timeout | float | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        if timeout is None:
            self._timeout = DEFAULT_TIMEOUT
        elif isinstance(timeout, (int, float)):
            self._timeout = httpx.Timeout(timeout)
        else:
            self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._client

    @_guard_retry
    async def scan_injection(self, text: str) -> ScanResult:
        """Scan text for prompt injection via POST /scan/injection."""
        client = self._get_client()
        resp = await client.post(
            f"{self.base_url}/scan/injection",
            json={"text": text},
        )
        resp.raise_for_status()
        data = resp.json()
        return ScanResult(
            detected=data["detected"],
            risk_score=data["risk_score"],
            processing_time_ms=data["processing_time_ms"],
        )

    async def health(self) -> bool:
        """Check LLM Guard service health."""
        try:
            client = self._get_client()
            resp = await client.get(f"{self.base_url}/health")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def aclose(self) -> None:
        """Close the underlying httpx client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
