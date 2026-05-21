"""Tests for Mini App config API endpoint."""

import pytest


pytest.importorskip("fastapi")

from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

from mini_app.api import app, get_validated_init_data


def _stub_init_data() -> dict:
    return {"user": {"id": 123, "first_name": "Test"}, "auth_date": "0"}


async def test_get_config_returns_questions_and_experts():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "questions" in data
    assert "experts" in data
    assert len(data["questions"]) == 4
    assert len(data["experts"]) == 5


async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_phone_endpoint_returns_json():
    mock_kommo = MagicMock()
    mock_kommo.upsert_contact = AsyncMock(return_value={"id": 1})
    mock_kommo.create_lead = AsyncMock(return_value={"id": 2})
    app.dependency_overrides[get_validated_init_data] = _stub_init_data
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
        app.dependency_overrides.pop(get_validated_init_data, None)
    assert resp.status_code == 200
    assert resp.json()["success"] is True


async def test_cors_headers_present():
    """CORS middleware must respond to the configured allowed origin (#1595).

    The Mini App allows ``MINI_APP_ALLOWED_ORIGIN`` (default ``https://t.me``)
    rather than the wildcard. We assert the configured origin is honoured by
    the running middleware rather than asserting on a wildcard response.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health", headers={"Origin": "https://t.me"})
    assert resp.headers.get("access-control-allow-origin") == "https://t.me"
