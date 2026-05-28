"""Tests for Mini App phone collection endpoint."""

import pytest


pytest.importorskip("fastapi")
pytestmark = pytest.mark.requires_extras

from unittest.mock import AsyncMock, MagicMock

from httpx import ASGITransport, AsyncClient

from mini_app.api import app, get_validated_init_data
from mini_app.phone import PhoneRequest, submit_phone


# The endpoint enforces SDK-validated Telegram initData (#1595). Tests in
# this file focus on the CRM/Kommo path, so we bypass the auth dependency
# with a synthetic validated payload. Auth enforcement itself is covered
# by tests/unit/mini_app/test_mini_app_auth_enforcement.py and
# tests/contract/test_mini_app_auth_contract.py.
def _stub_init_data(user_id: int = 123) -> dict:
    return {"user": {"id": user_id, "first_name": "Test"}, "auth_date": "0"}


@pytest.fixture(autouse=True)
def _bypass_auth_for_phone_tests():
    app.dependency_overrides[get_validated_init_data] = lambda: _stub_init_data()
    yield
    app.dependency_overrides.pop(get_validated_init_data, None)


def _build_kommo_mock(*, contact_id: int = 1, lead_id: int = 2) -> MagicMock:
    """Build a Kommo client mock used by DI in #2212."""
    mock_kommo = MagicMock()
    mock_kommo.upsert_contact = AsyncMock(return_value={"id": contact_id})
    mock_kommo.create_lead = AsyncMock(return_value={"id": lead_id})
    return mock_kommo


@pytest.fixture
def stub_kommo_on_app_state():
    """Inject a successful Kommo mock into ``app.state.kommo_client``.

    Yields the mock so individual tests can override its return values
    or side_effect to simulate CRM failures.
    """
    mock_kommo = _build_kommo_mock()
    app.state.kommo_client = mock_kommo
    yield mock_kommo
    app.state.kommo_client = None


@pytest.mark.asyncio
async def test_submit_phone_success(stub_kommo_on_app_state):
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
    the UI unable to distinguish a real lead from a dropped one (#1596).
    """
    failing_client = MagicMock()
    failing_client.upsert_contact = AsyncMock(side_effect=Exception("CRM down"))
    result = await submit_phone(
        PhoneRequest(phone="+359888123456", source="test", user_id=123),
        client=failing_client,
    )
    assert result["success"] is False
    assert result["lead_id"] is None
    assert result.get("error") == "kommo_submission_failed"


@pytest.mark.asyncio
async def test_phone_endpoint_returns_502_on_crm_failure():
    """The /api/phone endpoint must return a non-2xx status (502 Bad Gateway)
    when the CRM submission fails so the frontend can show a retry/error
    UI instead of treating the lead as captured (#1596)."""
    failing_client = MagicMock()
    failing_client.upsert_contact = AsyncMock(side_effect=Exception("CRM down"))
    app.state.kommo_client = failing_client
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/phone",
                json={
                    "phone": "+359888123456",
                    "source": "viewing_consultant",
                    "user_id": 123,
                },
            )
    finally:
        app.state.kommo_client = None
    assert resp.status_code == 502
    body = resp.json()
    assert body["success"] is False
    assert body["lead_id"] is None
    assert body.get("error") == "kommo_submission_failed"


@pytest.mark.asyncio
async def test_phone_endpoint_returns_503_when_kommo_unconfigured():
    """When Mini App boot did not wire Kommo, the endpoint must return
    503 with kommo_unconfigured error code (#2212). This is distinct from
    502 (transient CRM failure) so monitoring can alert separately."""
    app.state.kommo_client = None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/phone",
            json={
                "phone": "+359888123456",
                "source": "viewing_consultant",
                "user_id": 123,
            },
        )
    assert resp.status_code == 503
    assert resp.json().get("error") == "kommo_unconfigured"


@pytest.mark.asyncio
async def test_submit_phone_formats_name():
    mock_kommo = _build_kommo_mock()
    await submit_phone(
        PhoneRequest(phone="+359888123456", source="test", user_id=456),
        client=mock_kommo,
    )
    mock_kommo.upsert_contact.assert_called_once_with(
        phone="+359888123456", name="Mini App User 456"
    )


@pytest.mark.asyncio
async def test_submit_phone_source_in_lead():
    mock_kommo = _build_kommo_mock(contact_id=7, lead_id=99)
    await submit_phone(
        PhoneRequest(phone="+359888123456", source="viewing_consultant", user_id=123),
        client=mock_kommo,
    )
    mock_kommo.create_lead.assert_called_once_with(
        name="Mini App: viewing_consultant", contact_id=7
    )
