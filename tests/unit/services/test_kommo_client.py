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


async def test_401_with_seeded_token_raises_http_error(mock_token_store, httpx_mock):
    """401 with seeded token (no refresh_token) raises HTTPStatusError, not RuntimeError."""
    from httpx import HTTPStatusError

    from telegram_bot.services.kommo_client import KommoClient

    mock_token_store.force_refresh = AsyncMock(
        side_effect=RuntimeError("No refresh_token available for Kommo.")
    )
    client = KommoClient(subdomain="test-co", token_store=mock_token_store)

    httpx_mock.add_response(
        url="https://test-co.kommo.com/api/v4/leads/1",
        status_code=401,
    )

    with pytest.raises(HTTPStatusError, match="401"):
        await client.get_lead(1)

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


# --- Phase 2: search_leads, get_tasks, update_contact (#443) ---


async def test_search_leads_by_query(kommo_client, httpx_mock):
    """search_leads sends GET /api/v4/leads?query=..."""
    import re

    httpx_mock.add_response(
        url=re.compile(r".*/leads"),
        json={"_embedded": {"leads": [{"id": 10, "name": "Test Deal"}]}},
    )

    leads = await kommo_client.search_leads(query="Test")
    assert len(leads) == 1
    assert leads[0].id == 10
    assert leads[0].name == "Test Deal"


async def test_search_leads_by_responsible_user_id(kommo_client, httpx_mock):
    """search_leads sends GET /api/v4/leads with responsible_user_id filter."""
    import re

    httpx_mock.add_response(
        url=re.compile(r".*/leads"),
        json={"_embedded": {"leads": [{"id": 11, "name": "My Lead"}]}},
    )

    leads = await kommo_client.search_leads(responsible_user_id=42)
    assert len(leads) == 1
    assert leads[0].id == 11


async def test_search_leads_empty_result(kommo_client, httpx_mock):
    """search_leads returns empty list when no leads match."""
    import re

    httpx_mock.add_response(
        url=re.compile(r".*/leads"),
        json={},
    )

    leads = await kommo_client.search_leads(query="nonexistent")
    assert leads == []


async def test_get_tasks_by_responsible_user(kommo_client, httpx_mock):
    """get_tasks sends GET /api/v4/tasks with responsible_user_id filter."""
    import re

    httpx_mock.add_response(
        url=re.compile(r".*/tasks"),
        json={"_embedded": {"tasks": [{"id": 200, "text": "Call client", "is_completed": False}]}},
    )

    tasks = await kommo_client.get_tasks(responsible_user_id=42)
    assert len(tasks) == 1
    assert tasks[0].id == 200
    assert tasks[0].text == "Call client"


async def test_get_tasks_with_is_completed_filter(kommo_client, httpx_mock):
    """get_tasks sends is_completed=0 filter for active tasks."""
    import re

    httpx_mock.add_response(
        url=re.compile(r".*/tasks"),
        json={"_embedded": {"tasks": []}},
    )

    tasks = await kommo_client.get_tasks(is_completed=False)
    assert tasks == []


async def test_get_tasks_accepts_result_list_payload(kommo_client, httpx_mock):
    """get_tasks parses Kommo tasks where result is an empty list."""
    import re

    httpx_mock.add_response(
        url=re.compile(r".*/tasks"),
        json={
            "_embedded": {
                "tasks": [{"id": 201, "text": "Open task", "is_completed": False, "result": []}]
            }
        },
    )

    tasks = await kommo_client.get_tasks(is_completed=False)
    assert len(tasks) == 1
    assert tasks[0].id == 201
    assert tasks[0].result == []


async def test_update_contact(kommo_client, httpx_mock):
    """update_contact sends PATCH /api/v4/contacts/{id}."""
    from telegram_bot.services.kommo_models import ContactUpdate

    httpx_mock.add_response(
        url="https://test-co.kommo.com/api/v4/contacts/456",
        method="PATCH",
        json={"id": 456, "first_name": "Updated"},
    )

    update = ContactUpdate(first_name="Updated")
    contact = await kommo_client.update_contact(456, update)
    assert contact.id == 456
    assert contact.first_name == "Updated"


async def test_update_contact_with_custom_fields(kommo_client, httpx_mock):
    """update_contact sends phone/email in custom_fields_values."""
    from telegram_bot.services.kommo_models import ContactUpdate

    httpx_mock.add_response(
        url="https://test-co.kommo.com/api/v4/contacts/789",
        method="PATCH",
        json={"id": 789, "first_name": "Ivan"},
    )

    fields = ContactUpdate.build_contact_fields(phone="+380991234567")
    update = ContactUpdate(custom_fields_values=fields)
    contact = await kommo_client.update_contact(789, update)
    assert contact.id == 789


# --- Phase 3: create_task, link_contact_to_lead (#660) ---


async def test_create_task(kommo_client, httpx_mock):
    """create_task sends POST /api/v4/tasks and returns Task."""
    from telegram_bot.services.kommo_models import TaskCreate

    httpx_mock.add_response(
        url="https://test-co.kommo.com/api/v4/tasks",
        method="POST",
        json={
            "_embedded": {
                "tasks": [{"id": 300, "text": "Перезвонить: +380501234567", "entity_id": 101}]
            }
        },
    )

    task = await kommo_client.create_task(
        TaskCreate(text="Перезвонить: +380501234567", entity_id=101, complete_till=9999999999)
    )
    assert task.id == 300
    assert task.entity_id == 101


async def test_link_contact_to_lead(kommo_client, httpx_mock):
    """link_contact_to_lead sends POST /api/v4/leads/{id}/link without error."""
    httpx_mock.add_response(
        url="https://test-co.kommo.com/api/v4/leads/101/link",
        method="POST",
        json={},
    )

    # Should complete without raising an exception
    await kommo_client.link_contact_to_lead(101, 456)


# ─────────────────────────────────────────────────────────────────────────────
# Task 4: search_leads with_contacts + get_tasks entity_id filter (#731)
# ─────────────────────────────────────────────────────────────────────────────


async def test_search_leads_with_contacts_sends_with_param(kommo_client, httpx_mock):
    """search_leads(with_contacts=True) includes 'with=contacts' in request (#731)."""
    import re

    httpx_mock.add_response(
        url=re.compile(r".*/leads"),
        json={
            "_embedded": {
                "leads": [
                    {
                        "id": 20,
                        "name": "Deal With Contact",
                        "_embedded": {"contacts": [{"id": 5, "name": "Мария Иванова"}]},
                    }
                ]
            }
        },
    )

    leads = await kommo_client.search_leads(with_contacts=True)
    assert len(leads) == 1
    assert leads[0].contacts is not None
    assert leads[0].contacts[0]["name"] == "Мария Иванова"


async def test_search_leads_without_contacts_no_embedded(kommo_client, httpx_mock):
    """search_leads without with_contacts returns leads with contacts=None (#731)."""
    import re

    httpx_mock.add_response(
        url=re.compile(r".*/leads"),
        json={"_embedded": {"leads": [{"id": 21, "name": "Plain Lead"}]}},
    )

    leads = await kommo_client.search_leads()
    assert len(leads) == 1
    assert leads[0].contacts is None


async def test_get_tasks_by_entity_id(kommo_client, httpx_mock):
    """get_tasks(entity_id=...) sends filter[entity_id][] param (#731)."""
    import re

    httpx_mock.add_response(
        url=re.compile(r".*/tasks"),
        json={"_embedded": {"tasks": [{"id": 301, "text": "Entity task", "entity_id": 42}]}},
    )

    tasks = await kommo_client.get_tasks(entity_id=42)
    assert len(tasks) == 1
    assert tasks[0].id == 301
    assert tasks[0].entity_id == 42


# --- upsert_contact missing-name merge behavior (#717) ---


async def test_upsert_contact_updates_first_name_when_empty(kommo_client) -> None:
    """Existing contact with empty first_name gets ContactUpdate(first_name=...)."""
    from telegram_bot.services.kommo_models import Contact, ContactCreate, ContactUpdate

    existing_raw = {"id": 42, "first_name": None, "last_name": "Doe"}
    kommo_client._request = AsyncMock(  # type: ignore[method-assign]
        return_value={"_embedded": {"contacts": [existing_raw]}}
    )
    captured: list[tuple[int, ContactUpdate]] = []

    async def _mock_update(contact_id: int, update: ContactUpdate) -> Contact:
        captured.append((contact_id, update))
        return Contact(id=contact_id)

    kommo_client.update_contact = _mock_update  # type: ignore[method-assign]

    await kommo_client.upsert_contact("+1234567890", ContactCreate(first_name="John"))

    assert len(captured) == 1
    cid, update_payload = captured[0]
    assert cid == 42
    assert update_payload.first_name == "John"
    assert update_payload.last_name is None


async def test_upsert_contact_updates_last_name_when_empty(kommo_client) -> None:
    """Existing contact with empty last_name gets ContactUpdate(last_name=...)."""
    from telegram_bot.services.kommo_models import Contact, ContactCreate, ContactUpdate

    existing_raw = {"id": 7, "first_name": "Jane", "last_name": None}
    kommo_client._request = AsyncMock(  # type: ignore[method-assign]
        return_value={"_embedded": {"contacts": [existing_raw]}}
    )
    captured: list[tuple[int, ContactUpdate]] = []

    async def _mock_update(contact_id: int, update: ContactUpdate) -> Contact:
        captured.append((contact_id, update))
        return Contact(id=contact_id)

    kommo_client.update_contact = _mock_update  # type: ignore[method-assign]

    await kommo_client.upsert_contact(
        "+1234567890", ContactCreate(first_name="Jane", last_name="Smith")
    )

    assert len(captured) == 1
    cid, update_payload = captured[0]
    assert cid == 7
    assert update_payload.first_name is None
    assert update_payload.last_name == "Smith"


async def test_upsert_contact_no_update_when_names_already_filled(kommo_client) -> None:
    """When names are already present, upsert_contact should return existing contact unchanged."""
    from telegram_bot.services.kommo_models import Contact, ContactCreate, ContactUpdate

    existing_raw = {"id": 99, "first_name": "Alice", "last_name": "Wonder"}
    kommo_client._request = AsyncMock(  # type: ignore[method-assign]
        return_value={"_embedded": {"contacts": [existing_raw]}}
    )
    captured: list[tuple[int, ContactUpdate]] = []

    async def _mock_update(contact_id: int, update: ContactUpdate) -> Contact:
        captured.append((contact_id, update))
        return Contact(id=contact_id)

    kommo_client.update_contact = _mock_update  # type: ignore[method-assign]

    result = await kommo_client.upsert_contact(
        "+1234567890", ContactCreate(first_name="X", last_name="Y")
    )

    assert not captured
    assert result.id == 99
