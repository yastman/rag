"""Tests for Mini App chat SSE endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from mini_app.api import app


@pytest.mark.asyncio
async def test_chat_returns_sse_stream():
    mock_result = {"response": "Студии от 38 900 EUR", "response_sent": False}

    with patch("mini_app.chat.run_mini_app_query", AsyncMock(return_value=mock_result)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/chat",
                json={"message": "Какие цены на студии?", "user_id": 123},
            )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_chat_requires_message():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/chat", json={"user_id": 123})
    assert resp.status_code == 422
