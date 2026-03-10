"""Tests for Mini App API — /api/start-expert deep link endpoint."""

import os
from unittest.mock import AsyncMock, patch

import pytest


pytest.importorskip("fastapi")

from httpx import ASGITransport, AsyncClient

from mini_app.api import app


@pytest.mark.asyncio
async def test_health_endpoint():
    """Health check should return ok."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_chat_endpoint_streams_sse_event():
    """Legacy /api/chat endpoint should emit at least one SSE data event."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with client.stream(
            "POST",
            "/api/chat",
            json={"message": "Привет", "user_id": 123},
        ) as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    assert "Mini App chat is deprecated" in line
                    break
            else:
                pytest.fail("Expected at least one SSE data event")


@pytest.mark.asyncio
async def test_start_expert_not_found():
    """Unknown expert_id should return 404."""
    mock_redis = AsyncMock()
    with patch("mini_app.api.load_mini_app_config", return_value={"experts": []}):
        with patch("mini_app.api._get_redis", new=AsyncMock(return_value=mock_redis)):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/start-expert",
                    json={"user_id": 123, "expert_id": "nonexistent"},
                )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_start_expert_returns_start_link():
    """Valid expert should return start_link for deep linking."""
    mock_redis = AsyncMock()
    experts = [{"id": "consultant", "name": "Консультант", "emoji": "👷"}]
    with patch("mini_app.api.load_mini_app_config", return_value={"experts": experts}):
        with patch("mini_app.api._get_redis", new=AsyncMock(return_value=mock_redis)):
            with patch.dict(os.environ, {"BOT_USERNAME": "testbot"}):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.post(
                        "/api/start-expert",
                        json={
                            "user_id": 123,
                            "expert_id": "consultant",
                            "message": "Подбери квартиру",
                        },
                    )
    assert resp.status_code == 200
    data = resp.json()
    assert "start_link" in data
    assert "testbot" in data["start_link"]
    assert "q_" in data["start_link"]
    assert data["expert_name"] == "Консультант"
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_start_expert_stores_payload_in_redis():
    """API should store payload in Redis with TTL 300s."""
    mock_redis = AsyncMock()
    experts = [{"id": "consultant", "name": "Консультант", "emoji": "👷"}]
    with patch("mini_app.api.load_mini_app_config", return_value={"experts": experts}):
        with patch("mini_app.api._get_redis", new=AsyncMock(return_value=mock_redis)):
            with patch.dict(os.environ, {"BOT_USERNAME": "testbot"}):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.post(
                        "/api/start-expert",
                        json={"user_id": 123, "expert_id": "consultant", "message": "Тест"},
                    )
    assert resp.status_code == 200
    # Redis.set should have been called with TTL=300
    mock_redis.set.assert_called_once()
    call_args = mock_redis.set.call_args
    # key starts with "miniapp:q:"
    key = call_args.args[0] if call_args.args else call_args.kwargs.get("name", "")
    assert key.startswith("miniapp:q:")
    # TTL is 300
    assert call_args.kwargs.get("ex") == 300 or (
        len(call_args.args) > 2 and call_args.args[2] == 300
    )


@pytest.mark.asyncio
async def test_start_expert_fails_without_bot_username():
    """Missing BOT_USERNAME should return 500."""
    mock_redis = AsyncMock()
    experts = [{"id": "consultant", "name": "Консультант", "emoji": "👷"}]
    with patch("mini_app.api.load_mini_app_config", return_value={"experts": experts}):
        with patch("mini_app.api._get_redis", new=AsyncMock(return_value=mock_redis)):
            with patch.dict(os.environ, {"BOT_USERNAME": ""}, clear=False):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.post(
                        "/api/start-expert",
                        json={"user_id": 123, "expert_id": "consultant"},
                    )
    assert resp.status_code == 500
