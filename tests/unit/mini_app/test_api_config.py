"""Tests for Mini App config API endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient

from mini_app.api import app


@pytest.mark.asyncio
async def test_get_config_returns_questions_and_experts():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "questions" in data
    assert "experts" in data
    assert len(data["questions"]) == 4
    assert len(data["experts"]) == 5


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
