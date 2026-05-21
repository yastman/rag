"""Tests for Mini App phone collection endpoint."""

import pytest


pytest.importorskip("fastapi")

from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

from mini_app.api import app, get_validated_init_data
from mini_app.phone import PhoneRequest, submit_phone


***REMOVED*** The endpoint enforces SDK-validated Telegram initData (***REMOVED***1595). Tests in
***REMOVED*** this file focus on the CRM/Kommo path, so we bypass the auth dependency
***REMOVED*** with a synthetic validated payload. Auth enforcement itself is covered
***REMOVED*** by tests/unit/mini_app/test_mini_app_auth_enforcement.py and
***REMOVED*** tests/contract/test_mini_app_auth_contract.py.
def _stub_init_data(user_id: int = 123) -> dict:
    return {"user": {"id": user_id, "first_name": "Test"}, "auth_date": "0"}


@pytest.fixture(autouse=True)
def _bypass_auth_for_phone_tests():
    app.dependency_overrides[get_validated_init_data] = lambda: _stub_init_data()
    yield
    app.dependency_overrides.pop(get_validated_init_data, None)


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


@pytest.mark.asyncio
async def test_submit_phone_crm_failure_returns_error_payload():
    """CRM failures must surface as success=False so clients can react.
    Previously every exception was swallowed into success=True, leaving
    the UI unable to distinguish a real lead from a dropped one (***REMOVED***1596).
    """
    with patch("mini_app.phone.get_kommo_client", side_effect=Exception("CRM down")):
        result = await submit_phone(PhoneRequest(phone="+359888123456", source="test", user_id=123))
    assert result["success"] is False
    assert result["lead_id"] is None
    assert result.get("error") == "crm_submission_failed"


@pytest.mark.asyncio
async def test_phone_endpoint_returns_502_on_crm_failure():
    """The /api/phone endpoint must return a non-2xx status (502 Bad Gateway)
    when the CRM submission fails so the frontend can show a retry/error
    UI instead of treating the lead as captured (***REMOVED***1596)."""
    with patch("mini_app.phone.get_kommo_client", side_effect=Exception("CRM down")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/phone",
                json={
                    "phone": "+359888123456",
                    "source": "viewing_consultant",
                    "user_id": 123,
                },
            )
    assert resp.status_code == 502
    body = resp.json()
    assert body["success"] is False
    assert body["lead_id"] is None
    assert body.get("error") == "crm_submission_failed"


@pytest.mark.asyncio
async def test_submit_phone_formats_name():
    mock_kommo = MagicMock()
    mock_kommo.upsert_contact = AsyncMock(return_value={"id": 1})
    mock_kommo.create_lead = AsyncMock(return_value={"id": 2})
    with patch("mini_app.phone.get_kommo_client", return_value=mock_kommo):
        await submit_phone(PhoneRequest(phone="+359888123456", source="test", user_id=456))
    mock_kommo.upsert_contact.assert_called_once_with(
        phone="+359888123456", name="Mini App User 456"
    )


@pytest.mark.asyncio
async def test_submit_phone_source_in_lead():
    mock_kommo = MagicMock()
    mock_kommo.upsert_contact = AsyncMock(return_value={"id": 7})
    mock_kommo.create_lead = AsyncMock(return_value={"id": 99})
    with patch("mini_app.phone.get_kommo_client", return_value=mock_kommo):
        await submit_phone(
            PhoneRequest(phone="+359888123456", source="viewing_consultant", user_id=123)
        )
    mock_kommo.create_lead.assert_called_once_with(
        name="Mini App: viewing_consultant", contact_id=7
    )
