"""Tests for Mini App API — /api/start-expert endpoint."""

import pytest


pytest.importorskip("fastapi")

from unittest.mock import AsyncMock, patch

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
async def test_start_expert_not_found():
    """Unknown expert_id should return 404."""
    from mini_app.bot_bridge import BotBridge, set_bot_bridge

    bridge = BotBridge(
        bot=AsyncMock(),
        topic_service=AsyncMock(),
        rag_fn=AsyncMock(return_value={}),
    )
    set_bot_bridge(bridge)

    with patch(
        "mini_app.api.load_mini_app_config",
        return_value={"experts": []},
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/start-expert",
                json={"user_id": 123, "expert_id": "nonexistent"},
            )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_start_expert_success():
    """Valid expert should return thread_id and expert_name."""
    from mini_app.bot_bridge import BotBridge, set_bot_bridge

    topic_svc = AsyncMock()
    topic_svc.get_or_create_thread.return_value = 42
    bridge = BotBridge(
        bot=AsyncMock(),
        topic_service=topic_svc,
        rag_fn=AsyncMock(return_value={}),
    )
    set_bot_bridge(bridge)

    experts = [{"id": "consultant", "name": "Консультант", "emoji": "👷"}]
    with patch("mini_app.api.load_mini_app_config", return_value={"experts": experts}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/start-expert",
                json={"user_id": 123, "expert_id": "consultant"},
            )
    assert resp.status_code == 200
    data = resp.json()
    assert data["thread_id"] == 42
    assert data["expert_name"] == "Консультант"
    assert data["status"] == "ok"
