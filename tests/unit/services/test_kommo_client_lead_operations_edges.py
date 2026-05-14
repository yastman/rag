"""Edge-case tests for KommoClient lead operations (#1090)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from telegram_bot.services.kommo_client import KommoClient
from telegram_bot.services.kommo_models import LeadCreate, LeadUpdate


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
    return KommoClient(subdomain="test-co", token_store=mock_token_store)


async def test_create_lead_sends_alias_aware_single_item_list(kommo_client, httpx_mock):
    """create_lead sends alias-aware single-item list payload and parses embedded lead."""
    httpx_mock.add_response(
        url="https://test-co.kommo.com/api/v4/leads",
        method="POST",
        json={"_embedded": {"leads": [{"id": 77, "name": "Alias Lead", "price": 150000}]}},
    )

    lead = await kommo_client.create_lead(LeadCreate(name="Alias Lead", budget=150000))

    request = httpx_mock.get_request(url="https://test-co.kommo.com/api/v4/leads", method="POST")
    sent = request.content.decode()
    assert sent == '[{"name":"Alias Lead","price":150000}]'
    assert lead.id == 77
    assert lead.budget == 150000


async def test_update_lead_excludes_none_fields(kommo_client, httpx_mock):
    """update_lead sends PATCH payload excluding None fields."""
    httpx_mock.add_response(
        url="https://test-co.kommo.com/api/v4/leads/99",
        method="PATCH",
        json={"id": 99, "name": "Updated Lead", "price": 75000},
    )

    lead = await kommo_client.update_lead(99, LeadUpdate(name=None, budget=75000))

    request = httpx_mock.get_request(
        url="https://test-co.kommo.com/api/v4/leads/99", method="PATCH"
    )
    sent = request.content.decode()
    assert sent == '{"price":75000}'
    assert lead.id == 99
    assert lead.budget == 75000


async def test_search_leads_with_contacts_parses_embedded_and_does_not_mutate_original_response(
    kommo_client, httpx_mock
):
    """search_leads(with_contacts=True) parses embedded contacts and does not mutate the original response dict object supplied to the mock."""
    import re

    original_response = {
        "_embedded": {
            "leads": [
                {
                    "id": 30,
                    "name": "Deal With Contacts",
                    "_embedded": {"contacts": [{"id": 8, "name": "Alice"}]},
                }
            ]
        }
    }

    httpx_mock.add_response(
        url=re.compile(r".*\/leads"),
        json=original_response,
    )

    leads = await kommo_client.search_leads(with_contacts=True)

    assert len(leads) == 1
    assert leads[0].contacts is not None
    assert leads[0].contacts[0]["name"] == "Alice"
    # Original dict must be unchanged
    assert original_response["_embedded"]["leads"][0]["_embedded"] == {
        "contacts": [{"id": 8, "name": "Alice"}]
    }


async def test_search_leads_does_not_mutate_response_object_returned_by_request(kommo_client):
    """search_leads preserves the raw response object returned by the transport layer."""
    original_response = {
        "_embedded": {
            "leads": [
                {
                    "id": 31,
                    "name": "Raw Deal With Contacts",
                    "_embedded": {"contacts": [{"id": 9, "name": "Bob"}]},
                }
            ]
        }
    }
    kommo_client._request = AsyncMock(return_value=original_response)

    leads = await kommo_client.search_leads(with_contacts=True)

    assert len(leads) == 1
    assert leads[0].contacts == [{"id": 9, "name": "Bob"}]
    assert original_response["_embedded"]["leads"][0]["_embedded"] == {
        "contacts": [{"id": 9, "name": "Bob"}]
    }


async def test_update_lead_score_propagates_idempotency_key(kommo_client, httpx_mock):
    """update_lead_score propagates X-Idempotency-Key header."""
    httpx_mock.add_response(
        url="https://test-co.kommo.com/api/v4/leads/555",
        method="PATCH",
        json={"id": 555},
    )

    await kommo_client.update_lead_score(
        lead_id=555,
        payload={"custom_fields_values": []},
        idempotency_key="key-123",
    )

    request = httpx_mock.get_request(
        url="https://test-co.kommo.com/api/v4/leads/555", method="PATCH"
    )
    assert request.headers["X-Idempotency-Key"] == "key-123"
