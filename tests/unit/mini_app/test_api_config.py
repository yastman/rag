"""Tests for Mini App config API endpoint."""

import time

import pytest


pytest.importorskip("fastapi")

from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

from mini_app.api import app, get_validated_init_data


def _override_init_data(user_id: int = 123) -> None:
    """Override auth dependency for tests that focus on other logic."""
    app.dependency_overrides[get_validated_init_data] = lambda: {
        "user": {"id": user_id, "first_name": "Test"},
        "auth_date": str(int(time.time())),
    }


def _clear_init_data_override() -> None:
    app.dependency_overrides.pop(get_validated_init_data, None)


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


@pytest.mark.asyncio
async def test_phone_endpoint_returns_json():
    mock_kommo = MagicMock()
    mock_kommo.upsert_contact = AsyncMock(return_value={"id": 1})
    mock_kommo.create_lead = AsyncMock(return_value={"id": 2})
    _override_init_data(user_id=123)
    try:
        with patch("mini_app.phone.get_kommo_client", return_value=mock_kommo):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/phone",
                    json={"phone": "+359888123456", "source": "test", "user_id": 123},
                )
    finally:
        _clear_init_data_override()
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_cors_headers_present():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health", headers={"Origin": "https://t.me"})
    assert "access-control-allow-origin" in resp.headers
