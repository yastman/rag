"""Tests for KommoClient async httpx adapter (#413)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def mock_token_store():
    """Mock KommoTokenStore."""
    store = AsyncMock()
    store.get_valid_token = AsyncMock(return_value="test-token")
    store.force_refresh = AsyncMock(return_value="refreshed-token")
    return store


@pytest.fixture
def kommo_client(mock_token_store):
    """KommoClient with mocked token store."""
    from telegram_bot.services.kommo_client import KommoClient

    return KommoClient(subdomain="test-co", token_store=mock_token_store)


async def test_create_lead(kommo_client, httpx_mock):
    """create_lead sends POST /api/v4/leads."""
    from telegram_bot.services.kommo_models import LeadCreate

    httpx_mock.add_response(
        url="https://test-co.kommo.com/api/v4/leads",
        method="POST",
        json={"_embedded": {"leads": [{"id": 1, "name": "Test Lead"}]}},
    )

    lead = await kommo_client.create_lead(LeadCreate(name="Test Lead"))
    assert lead.id == 1
    assert lead.name == "Test Lead"


async def test_get_lead(kommo_client, httpx_mock):
    """get_lead sends GET /api/v4/leads/{id}."""
    httpx_mock.add_response(
        url="https://test-co.kommo.com/api/v4/leads/123",
        json={"id": 123, "name": "Existing Lead", "budget": 50000},
    )

    lead = await kommo_client.get_lead(123)
    assert lead.id == 123
    assert lead.budget == 50000


async def test_add_note(kommo_client, httpx_mock):
    """add_note sends POST to entity notes endpoint."""
    httpx_mock.add_response(
        url="https://test-co.kommo.com/api/v4/leads/123/notes",
        method="POST",
        json={"_embedded": {"notes": [{"id": 789, "text": "Note text"}]}},
    )

    note = await kommo_client.add_note("leads", 123, "Note text")
    assert note.id == 789


async def test_auto_refresh_on_401(kommo_client, mock_token_store, httpx_mock):
    """KommoClient retries with refreshed token on 401."""
    httpx_mock.add_response(
        url="https://test-co.kommo.com/api/v4/leads/1",
        status_code=401,
    )
    httpx_mock.add_response(
        url="https://test-co.kommo.com/api/v4/leads/1",
        json={"id": 1, "name": "Lead"},
    )

    lead = await kommo_client.get_lead(1)
    assert lead.id == 1
    mock_token_store.force_refresh.assert_called_once()


async def test_upsert_contact_find_existing(kommo_client, httpx_mock):
    """upsert_contact finds existing contact by phone."""
    import re

    from telegram_bot.services.kommo_models import ContactCreate

    httpx_mock.add_response(
        url=re.compile(r".*/contacts"),
        json={"_embedded": {"contacts": [{"id": 456, "first_name": "Existing"}]}},
    )

    contact = await kommo_client.upsert_contact(
        "+359888123456",
        ContactCreate(first_name="Иван", phone="+359888123456"),
    )
    assert contact.id == 456


# --- URL normalization (#411) ---


def test_subdomain_plain(mock_token_store):
    """Plain subdomain builds correct base URL."""
    from telegram_bot.services.kommo_client import KommoClient

    client = KommoClient(subdomain="linhminhphung1", token_store=mock_token_store)
    assert client._base_url == "https://linhminhphung1.kommo.com/api/v4"


def test_subdomain_with_kommo_suffix(mock_token_store):
    """Subdomain with .kommo.com suffix doesn't produce double domain (#411)."""
    from telegram_bot.services.kommo_client import KommoClient

    client = KommoClient(subdomain="linhminhphung1.kommo.com", token_store=mock_token_store)
    assert client._base_url == "https://linhminhphung1.kommo.com/api/v4"


def test_subdomain_with_dots(mock_token_store):
    """Subdomain containing dots (but not .kommo.com) works correctly."""
    from telegram_bot.services.kommo_client import KommoClient

    client = KommoClient(subdomain="api-c", token_store=mock_token_store)
    assert client._base_url == "https://api-c.kommo.com/api/v4"
