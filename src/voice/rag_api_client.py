"""Typed client boundary for voice -> RAG API calls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class RagQueryRequest:
    """Typed payload for `/query` requests."""

    query: str
    session_id: str
    user_id: int = 0
    channel: str = "voice"
    langfuse_trace_id: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "query": self.query,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "channel": self.channel,
        }
        if self.langfuse_trace_id:
            payload["langfuse_trace_id"] = self.langfuse_trace_id
        return payload


class RagApiClientError(RuntimeError):
    """Raised when voice RAG API request failed in a recoverable way."""


class RagApiClient:
    """Small typed API client around `/query` endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout: float = 30.0,
        max_connections: int = 10,
        max_keepalive_connections: int = 5,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_connections = max_connections
        self._max_keepalive_connections = max_keepalive_connections
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Expose underlying client for compatibility/test assertions."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                limits=httpx.Limits(
                    max_connections=self._max_connections,
                    max_keepalive_connections=self._max_keepalive_connections,
                ),
            )
        return self._client

    async def close(self) -> None:
        """Close internal HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def search_knowledge_base(self, request: RagQueryRequest) -> str:
        """Call RAG API and return response text."""
        try:
            response = await self.client.post(
                f"{self._base_url}/query",
                json=request.to_payload(),
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise RagApiClientError("Unexpected RAG API response shape")
            return str(data.get("response", "Информация не найдена."))
        except httpx.HTTPError as exc:
            raise RagApiClientError("RAG API request failed") from exc
        except ValueError as exc:
            raise RagApiClientError("Invalid RAG API response payload") from exc
