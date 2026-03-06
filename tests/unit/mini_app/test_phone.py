"""Tests for Mini App phone collection endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from mini_app.api import app


@pytest.mark.asyncio
async def test_submit_phone_success():
    mock_kommo = MagicMock()
    mock_kommo.upsert_contact = AsyncMock(return_value={"id": 1})
    mock_kommo.create_lead = AsyncMock(return_value={"id": 2})

    with patch("mini_app.phone.get_kommo_client", return_value=mock_kommo):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/phone",
                json={
                    "phone": "+359888123456",
                    "source": "viewing_consultant",
                    "user_id": 123,
                },
            )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_submit_phone_invalid():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/phone",
            json={"phone": "abc", "source": "test", "user_id": 123},
        )
    assert resp.status_code == 422
