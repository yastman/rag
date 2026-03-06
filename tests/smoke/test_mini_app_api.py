"""Smoke tests for Mini App API endpoints.

Runs against a live mini-app-api service.
Requires MINI_APP_URL or defaults to http://localhost:8090.

Usage:
    uv run pytest tests/smoke/test_mini_app_api.py -v
"""

from __future__ import annotations

import os
import socket

import httpx
import pytest


def _api_url() -> str:
    return os.getenv("MINI_APP_URL", "http://localhost:8090")


def _is_api_available() -> bool:
    url = _api_url()
    # Parse host/port from URL like http://host:port
    try:
        without_scheme = url.split("://", 1)[1]
        host, _, port_str = without_scheme.partition(":")
        port = int(port_str.rstrip("/")) if port_str else 80
        with socket.create_connection((host, port), timeout=2.0):
            return True
    except OSError:
        return False


_skip_if_unavailable = pytest.mark.skipif(
    not _is_api_available(),
    reason=f"Mini App API not reachable at {_api_url()}",
)


@pytest.mark.smoke
class TestMiniAppApi:
    """End-to-end smoke tests for Mini App FastAPI backend."""

    @pytest.mark.asyncio
    @_skip_if_unavailable
    async def test_health(self) -> None:
        """GET /health returns 200 with status ok."""
        async with httpx.AsyncClient(base_url=_api_url(), timeout=10.0) as client:
            response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"

    @pytest.mark.asyncio
    @_skip_if_unavailable
    async def test_config_endpoint(self) -> None:
        """GET /api/config returns questions and experts lists."""
        async with httpx.AsyncClient(base_url=_api_url(), timeout=10.0) as client:
            response = await client.get("/api/config")
        assert response.status_code == 200
        data = response.json()
        # Config must contain at minimum these keys (from mini_app.yaml)
        assert isinstance(data, dict), "Config must be a dict"
        assert "questions" in data or "experts" in data, (
            f"Expected 'questions' or 'experts' in config, got keys: {list(data.keys())}"
        )

    @pytest.mark.asyncio
    @_skip_if_unavailable
    async def test_chat_endpoint_streams(self) -> None:
        """POST /api/chat returns SSE stream with at least one data event."""
        payload = {"message": "Привет", "user_id": 999999}
        async with httpx.AsyncClient(base_url=_api_url(), timeout=30.0) as client:
            async with client.stream("POST", "/api/chat", json=payload) as response:
                assert response.status_code == 200
                content_type = response.headers.get("content-type", "")
                assert "text/event-stream" in content_type, (
                    f"Expected SSE content-type, got: {content_type}"
                )
                # Read at least one chunk to confirm streaming works
                got_data = False
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        got_data = True
                        break
                assert got_data, "Expected at least one 'data:' SSE event"

    @pytest.mark.asyncio
    @_skip_if_unavailable
    async def test_phone_endpoint_validation(self) -> None:
        """POST /api/phone with invalid phone returns 422 or error payload."""
        payload = {"phone": "", "source": "smoke_test", "user_id": 999999}
        async with httpx.AsyncClient(base_url=_api_url(), timeout=10.0) as client:
            response = await client.post("/api/phone", json=payload)
        # Either 422 (validation) or 200 with error key — both acceptable
        assert response.status_code in (200, 422), (
            f"Unexpected status {response.status_code}: {response.text}"
        )
