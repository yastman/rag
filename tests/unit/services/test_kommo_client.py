"""Tests for KommoClient async httpx adapter (***REMOVED***413)."""

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


***REMOVED*** --- URL normalization (***REMOVED***411) ---


def test_subdomain_plain(mock_token_store):
    """Plain subdomain builds correct base URL."""
    from telegram_bot.services.kommo_client import KommoClient

    client = KommoClient(subdomain="linhminhphung1", token_store=mock_token_store)
    assert client._base_url == "https://linhminhphung1.kommo.com/api/v4"


def test_subdomain_with_kommo_suffix(mock_token_store):
    """Subdomain with .kommo.com suffix doesn't produce double domain (***REMOVED***411)."""
    from telegram_bot.services.kommo_client import KommoClient

    client = KommoClient(subdomain="linhminhphung1.kommo.com", token_store=mock_token_store)
    assert client._base_url == "https://linhminhphung1.kommo.com/api/v4"


def test_subdomain_with_dots(mock_token_store):
    """Subdomain containing dots (but not .kommo.com) works correctly."""
    from telegram_bot.services.kommo_client import KommoClient

    client = KommoClient(subdomain="api-c", token_store=mock_token_store)
    assert client._base_url == "https://api-c.kommo.com/api/v4"


***REMOVED*** --- Phase 2: search_leads, get_tasks, update_contact (***REMOVED***443) ---


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


***REMOVED*** --- Phase 3: create_task, link_contact_to_lead (***REMOVED***660) ---


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

    ***REMOVED*** Should complete without raising an exception
    await kommo_client.link_contact_to_lead(101, 456)


***REMOVED*** ─────────────────────────────────────────────────────────────────────────────
***REMOVED*** Task 4: search_leads with_contacts + get_tasks entity_id filter (***REMOVED***731)
***REMOVED*** ─────────────────────────────────────────────────────────────────────────────


async def test_search_leads_with_contacts_sends_with_param(kommo_client, httpx_mock):
    """search_leads(with_contacts=True) includes 'with=contacts' in request (***REMOVED***731)."""
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
    """search_leads without with_contacts returns leads with contacts=None (***REMOVED***731)."""
    import re

    httpx_mock.add_response(
        url=re.compile(r".*/leads"),
        json={"_embedded": {"leads": [{"id": 21, "name": "Plain Lead"}]}},
    )

    leads = await kommo_client.search_leads()
    assert len(leads) == 1
    assert leads[0].contacts is None


async def test_get_tasks_by_entity_id(kommo_client, httpx_mock):
    """get_tasks(entity_id=...) sends filter[entity_id][] param (***REMOVED***731)."""
    import re

    httpx_mock.add_response(
        url=re.compile(r".*/tasks"),
        json={"_embedded": {"tasks": [{"id": 301, "text": "Entity task", "entity_id": 42}]}},
    )

    tasks = await kommo_client.get_tasks(entity_id=42)
    assert len(tasks) == 1
    assert tasks[0].id == 301
    assert tasks[0].entity_id == 42


***REMOVED*** --- upsert_contact missing-name merge behavior (***REMOVED***717) ---


async def test_upsert_contact_updates_first_name_when_empty(kommo_client) -> None:
    """Existing contact with empty first_name gets ContactUpdate(first_name=...)."""
    from telegram_bot.services.kommo_models import Contact, ContactCreate, ContactUpdate

    existing_raw = {"id": 42, "first_name": None, "last_name": "Doe"}
    kommo_client._request = AsyncMock(  ***REMOVED*** type: ignore[method-assign]
        return_value={"_embedded": {"contacts": [existing_raw]}}
    )
    captured: list[tuple[int, ContactUpdate]] = []

    async def _mock_update(contact_id: int, update: ContactUpdate) -> Contact:
        captured.append((contact_id, update))
        return Contact(id=contact_id)

    kommo_client.update_contact = _mock_update  ***REMOVED*** type: ignore[method-assign]

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
    kommo_client._request = AsyncMock(  ***REMOVED*** type: ignore[method-assign]
        return_value={"_embedded": {"contacts": [existing_raw]}}
    )
    captured: list[tuple[int, ContactUpdate]] = []

    async def _mock_update(contact_id: int, update: ContactUpdate) -> Contact:
        captured.append((contact_id, update))
        return Contact(id=contact_id)

    kommo_client.update_contact = _mock_update  ***REMOVED*** type: ignore[method-assign]

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
    kommo_client._request = AsyncMock(  ***REMOVED*** type: ignore[method-assign]
        return_value={"_embedded": {"contacts": [existing_raw]}}
    )
    captured: list[tuple[int, ContactUpdate]] = []

    async def _mock_update(contact_id: int, update: ContactUpdate) -> Contact:
        captured.append((contact_id, update))
        return Contact(id=contact_id)

    kommo_client.update_contact = _mock_update  ***REMOVED*** type: ignore[method-assign]

    result = await kommo_client.upsert_contact(
        "+1234567890", ContactCreate(first_name="X", last_name="Y")
    )

    assert not captured
    assert result.id == 99


***REMOVED*** -----------------------------------------------------------------------------
***REMOVED*** httpx.Auth flow contract (***REMOVED***1646)
***REMOVED*** -----------------------------------------------------------------------------


class TestKommoOAuthAuthFlow:
    """KommoClient delegates OAuth bearer/refresh to a httpx.Auth subclass (***REMOVED***1646).

    Context7 baseline (/encode/httpx) recommends overriding ``async_auth_flow``
    on a subclass of ``httpx.Auth`` for multi-request authentication, including
    refresh-on-401. Coordinating concurrent refresh with ``asyncio.Lock`` is the
    documented pattern.
    """

    def test_kommo_oauth_auth_class_is_subclass_of_httpx_auth(self) -> None:
        import httpx

        from telegram_bot.services.kommo_client import KommoOAuthAuth

        assert issubclass(KommoOAuthAuth, httpx.Auth)

    def test_kommo_client_attaches_oauth_auth_to_async_client(self, mock_token_store) -> None:
        """The shared httpx.AsyncClient must be constructed with KommoOAuthAuth."""
        from telegram_bot.services.kommo_client import KommoClient, KommoOAuthAuth

        client = KommoClient(subdomain="test-co", token_store=mock_token_store)
        ***REMOVED*** httpx exposes the auth on the AsyncClient as ``client.auth``.
        assert isinstance(client._client.auth, KommoOAuthAuth)

    async def test_async_auth_flow_sets_bearer_then_yields(self, mock_token_store) -> None:
        import httpx

        from telegram_bot.services.kommo_client import KommoOAuthAuth

        auth = KommoOAuthAuth(token_store=mock_token_store)
        request = httpx.Request("GET", "https://test-co.kommo.com/api/v4/leads/1")

        flow = auth.async_auth_flow(request)
        first = await flow.__anext__()
        assert first is request
        assert first.headers["Authorization"] == "Bearer test-token"
        ***REMOVED*** Simulate 200: flow completes after the first yield.
        ok = httpx.Response(200, request=request)
        with pytest.raises(StopAsyncIteration):
            await flow.asend(ok)
        mock_token_store.get_valid_token.assert_awaited_once()
        mock_token_store.force_refresh.assert_not_called()

    async def test_async_auth_flow_refreshes_and_yields_again_on_401(
        self, mock_token_store
    ) -> None:
        import httpx

        from telegram_bot.services.kommo_client import KommoOAuthAuth

        auth = KommoOAuthAuth(token_store=mock_token_store)
        request = httpx.Request("GET", "https://test-co.kommo.com/api/v4/leads/1")

        flow = auth.async_auth_flow(request)
        first = await flow.__anext__()
        assert first.headers["Authorization"] == "Bearer test-token"

        unauthorized = httpx.Response(401, request=request)
        retry = await flow.asend(unauthorized)
        ***REMOVED*** Same Request object re-yielded with refreshed bearer.
        assert retry.headers["Authorization"] == "Bearer refreshed-token"
        ***REMOVED*** Flow ends after retry response.
        ok = httpx.Response(200, request=retry)
        with pytest.raises(StopAsyncIteration):
            await flow.asend(ok)

        mock_token_store.force_refresh.assert_awaited_once()

    async def test_async_auth_flow_deduplicates_concurrent_401_refreshes(
        self, mock_token_store
    ) -> None:
        import httpx

        from telegram_bot.services.kommo_client import KommoOAuthAuth

        mock_token_store.get_valid_token.side_effect = [
            "stale-token",
            "stale-token",
            "stale-token",
            "refreshed-token",
        ]
        mock_token_store.force_refresh.return_value = "refreshed-token"
        auth = KommoOAuthAuth(token_store=mock_token_store)
        first_request = httpx.Request("GET", "https://test-co.kommo.com/api/v4/leads/1")
        second_request = httpx.Request("GET", "https://test-co.kommo.com/api/v4/leads/2")

        first_flow = auth.async_auth_flow(first_request)
        second_flow = auth.async_auth_flow(second_request)
        await first_flow.__anext__()
        await second_flow.__anext__()

        first_retry = await first_flow.asend(httpx.Response(401, request=first_request))
        second_retry = await second_flow.asend(httpx.Response(401, request=second_request))

        assert first_retry.headers["Authorization"] == "Bearer refreshed-token"
        assert second_retry.headers["Authorization"] == "Bearer refreshed-token"
        mock_token_store.force_refresh.assert_awaited_once()

    async def test_async_auth_flow_swallows_runtime_error_from_refresh(
        self, mock_token_store
    ) -> None:
        """Seeded long-lived tokens raise RuntimeError on force_refresh.

        The auth flow must NOT propagate this RuntimeError out — httpx will
        otherwise wrap it as a generic auth failure. Returning lets the original
        401 response surface to the caller, where ``response.raise_for_status()``
        produces the canonical ``httpx.HTTPStatusError``.
        """
        import httpx

        from telegram_bot.services.kommo_client import KommoOAuthAuth

        mock_token_store.force_refresh = AsyncMock(
            side_effect=RuntimeError("No refresh_token available for Kommo.")
        )
        auth = KommoOAuthAuth(token_store=mock_token_store)
        request = httpx.Request("GET", "https://test-co.kommo.com/api/v4/leads/1")

        flow = auth.async_auth_flow(request)
        await flow.__anext__()
        unauthorized = httpx.Response(401, request=request)
        ***REMOVED*** Flow must terminate without re-yielding when refresh is impossible.
        with pytest.raises(StopAsyncIteration):
            await flow.asend(unauthorized)


class TestKommoClientRequestNoLongerHandles401:
    """AST: ``KommoClient._request`` no longer carries the manual 401 branch (***REMOVED***1646).

    Forbids regressing to the pre-***REMOVED***1646 manual ``if response.status_code == 401:``
    refresh-and-retry block that duplicated httpx.Auth's responsibility.
    """

    def test_request_body_does_not_check_401_status_code(self) -> None:
        import ast
        import inspect
        import textwrap

        from telegram_bot.services import kommo_client as mod

        source = textwrap.dedent(inspect.getsource(mod.KommoClient._request))
        tree = ast.parse(source)

        bad: list[int] = []
        for node in ast.walk(tree):
            ***REMOVED*** Look for `response.status_code == 401` comparisons in the body.
            if not isinstance(node, ast.Compare):
                continue
            left = node.left
            if not (isinstance(left, ast.Attribute) and left.attr == "status_code"):
                continue
            for cmp in node.comparators:
                if isinstance(cmp, ast.Constant) and cmp.value == 401:
                    bad.append(node.lineno)

        assert not bad, (
            "KommoClient._request must not check 401 inline; that is the "
            "responsibility of KommoOAuthAuth.async_auth_flow (***REMOVED***1646). "
            f"Offending lines: {bad}"
        )
