"""Tests for KommoClient async HTTP adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest


_DUMMY_REQ = httpx.Request("GET", "https://testcompany.kommo.com/api/v4/test")


@pytest.fixture
def mock_token_store():
    store = AsyncMock()
    store.get_valid_token = AsyncMock(return_value="test_access_token")
    store.force_refresh = AsyncMock(return_value="refreshed_token")
    return store


@pytest.fixture
def kommo_client(mock_token_store):
    from telegram_bot.services.kommo_client import KommoClient

    return KommoClient(subdomain="testcompany", token_store=mock_token_store)


class TestKommoClientRequest:
    async def test_request_adds_auth_header(self, kommo_client, mock_token_store):
        """Verify Authorization header is set."""
        mock_response = httpx.Response(
            200, json={"_embedded": {"leads": [{"id": 1}]}}, request=_DUMMY_REQ
        )
        with patch.object(kommo_client._client, "request", return_value=mock_response) as mock_req:
            await kommo_client._request("GET", "/leads")
            call_kwargs = mock_req.call_args
            assert "Bearer test_access_token" in str(call_kwargs)

    async def test_request_retries_on_401(self, kommo_client, mock_token_store):
        """Auto-refresh token on 401 and retry."""
        resp_401 = httpx.Response(401, json={"detail": "Unauthorized"}, request=_DUMMY_REQ)
        resp_200 = httpx.Response(200, json={"ok": True}, request=_DUMMY_REQ)
        with patch.object(kommo_client._client, "request", side_effect=[resp_401, resp_200]):
            result = await kommo_client._request("GET", "/leads")
            assert result == {"ok": True}
            mock_token_store.force_refresh.assert_called_once()

    async def test_request_retries_on_429(self, kommo_client):
        resp_429 = httpx.Response(429, headers={"Retry-After": "1"}, request=_DUMMY_REQ)
        resp_200 = httpx.Response(200, json={"ok": True}, request=_DUMMY_REQ)
        with patch.object(kommo_client._client, "request", side_effect=[resp_429, resp_200]):
            assert await kommo_client._request("GET", "/leads") == {"ok": True}

    async def test_request_retries_on_5xx(self, kommo_client):
        resp_503 = httpx.Response(503, request=_DUMMY_REQ)
        resp_200 = httpx.Response(200, json={"ok": True}, request=_DUMMY_REQ)
        with patch.object(kommo_client._client, "request", side_effect=[resp_503, resp_200]):
            assert await kommo_client._request("GET", "/leads") == {"ok": True}


class TestKommoClientLeads:
    async def test_create_lead(self, kommo_client):
        from telegram_bot.services.kommo_models import LeadCreate

        mock_resp = httpx.Response(
            200,
            json={"_embedded": {"leads": [{"id": 999, "request_id": "0"}]}},
            request=_DUMMY_REQ,
        )
        with patch.object(kommo_client._client, "request", return_value=mock_resp):
            lead_data = LeadCreate(name="Test Lead", price=50000, pipeline_id=100)
            result = await kommo_client.create_lead(lead_data)
            assert result.id == 999


class TestKommoClientContacts:
    async def test_create_contact(self, kommo_client):
        from telegram_bot.services.kommo_models import ContactCreate

        mock_resp = httpx.Response(
            200,
            json={"_embedded": {"contacts": [{"id": 888, "request_id": "0"}]}},
            request=_DUMMY_REQ,
        )
        with patch.object(kommo_client._client, "request", return_value=mock_resp):
            contact_data = ContactCreate(first_name="Иван", phone="+380501234567")
            result = await kommo_client.create_contact(contact_data)
            assert result.id == 888

    async def test_upsert_contact_existing(self, kommo_client):
        """Upsert returns existing contact when phone matches."""
        search_resp = httpx.Response(
            200,
            json={"_embedded": {"contacts": [{"id": 777, "name": "Existing"}]}},
            request=_DUMMY_REQ,
        )
        with patch.object(kommo_client._client, "request", return_value=search_resp):
            from telegram_bot.services.kommo_models import ContactCreate

            result = await kommo_client.upsert_contact(
                phone="+380501234567",
                data=ContactCreate(first_name="Иван"),
            )
            assert result.id == 777

    async def test_upsert_contact_creates_new(self, kommo_client):
        """Upsert creates new contact when phone not found."""
        search_resp = httpx.Response(200, json={"_embedded": {"contacts": []}}, request=_DUMMY_REQ)
        create_resp = httpx.Response(
            200,
            json={"_embedded": {"contacts": [{"id": 666, "request_id": "0"}]}},
            request=_DUMMY_REQ,
        )
        with patch.object(kommo_client._client, "request", side_effect=[search_resp, create_resp]):
            from telegram_bot.services.kommo_models import ContactCreate

            result = await kommo_client.upsert_contact(
                phone="+380501234567",
                data=ContactCreate(first_name="Новый"),
            )
            assert result.id == 666


class TestKommoClientNotes:
    async def test_add_note(self, kommo_client):
        mock_resp = httpx.Response(
            200, json={"_embedded": {"notes": [{"id": 555}]}}, request=_DUMMY_REQ
        )
        with patch.object(kommo_client._client, "request", return_value=mock_resp):
            result = await kommo_client.add_note(
                entity_type="leads", entity_id=100, text="Итог беседы"
            )
            assert result.id == 555


class TestKommoClientTasks:
    async def test_create_task(self, kommo_client):
        from telegram_bot.services.kommo_models import TaskCreate

        mock_resp = httpx.Response(
            200, json={"_embedded": {"tasks": [{"id": 444}]}}, request=_DUMMY_REQ
        )
        with patch.object(kommo_client._client, "request", return_value=mock_resp):
            task = TaskCreate(
                text="Follow up",
                entity_id=100,
                entity_type="leads",
                complete_till=1739900000,
            )
            result = await kommo_client.create_task(task)
            assert result.id == 444


class TestKommoClientLink:
    async def test_link_contact_to_lead(self, kommo_client):
        mock_resp = httpx.Response(204, request=_DUMMY_REQ)
        with patch.object(kommo_client._client, "request", return_value=mock_resp):
            await kommo_client.link_contact_to_lead(lead_id=100, contact_id=200)
            # No exception = success
