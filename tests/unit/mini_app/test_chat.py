"""Tests for Mini App API — /api/start-expert deep link endpoint."""

import os
from unittest.mock import AsyncMock, patch

import pytest


pytest.importorskip("fastapi")

from httpx import ASGITransport, AsyncClient

from mini_app.api import app, get_redis


def _override_redis(mock_redis: AsyncMock) -> None:
    """Install ``mock_redis`` as the FastAPI Depends(get_redis) override."""
    app.dependency_overrides[get_redis] = lambda: mock_redis


def _clear_redis_override() -> None:
    """Remove the dependency override after the test."""
    app.dependency_overrides.pop(get_redis, None)


@pytest.mark.asyncio
async def test_health_endpoint():
    """Health check should return ok."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_start_expert_not_found():
    """Unknown expert_id should return 404."""
    mock_redis = AsyncMock()
    _override_redis(mock_redis)
    try:
        with patch("mini_app.api.load_mini_app_config", return_value={"experts": []}):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/start-expert",
                    json={"user_id": 123, "expert_id": "nonexistent"},
                )
    finally:
        _clear_redis_override()
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_start_expert_returns_start_link():
    """Valid expert should return start_link for deep linking."""
    mock_redis = AsyncMock()
    experts = [{"id": "consultant", "name": "Консультант", "emoji": "👷"}]
    _override_redis(mock_redis)
    try:
        with patch("mini_app.api.load_mini_app_config", return_value={"experts": experts}):
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
    finally:
        _clear_redis_override()
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
    _override_redis(mock_redis)
    try:
        with patch("mini_app.api.load_mini_app_config", return_value={"experts": experts}):
            with patch.dict(os.environ, {"BOT_USERNAME": "testbot"}):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.post(
                        "/api/start-expert",
                        json={"user_id": 123, "expert_id": "consultant", "message": "Тест"},
                    )
    finally:
        _clear_redis_override()
    assert resp.status_code == 200
    ***REMOVED*** Redis.set should have been called with TTL=300
    mock_redis.set.assert_called_once()
    call_args = mock_redis.set.call_args
    ***REMOVED*** key starts with "miniapp:q:"
    key = call_args.args[0] if call_args.args else call_args.kwargs.get("name", "")
    assert key.startswith("miniapp:q:")
    ***REMOVED*** TTL is 300
    assert call_args.kwargs.get("ex") == 300 or (
        len(call_args.args) > 2 and call_args.args[2] == 300
    )


@pytest.mark.asyncio
async def test_start_expert_fails_without_bot_username():
    """Missing BOT_USERNAME should return 500."""
    mock_redis = AsyncMock()
    experts = [{"id": "consultant", "name": "Консультант", "emoji": "👷"}]
    _override_redis(mock_redis)
    try:
        with patch("mini_app.api.load_mini_app_config", return_value={"experts": experts}):
            with patch.dict(os.environ, {"BOT_USERNAME": ""}, clear=False):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.post(
                        "/api/start-expert",
                        json={"user_id": 123, "expert_id": "consultant"},
                    )
    finally:
        _clear_redis_override()
    assert resp.status_code == 500
