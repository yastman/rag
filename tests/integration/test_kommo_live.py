"""Live integration tests for Kommo CRM API (#409).

Requires real credentials:
  KOMMO_SUBDOMAIN, KOMMO_ACCESS_TOKEN

Run: uv run pytest tests/integration/test_kommo_live.py -v
Skip when creds missing (CI).
"""

from __future__ import annotations

import os
import time

import pytest


# Skip entire module if creds missing
pytestmark = [
    pytest.mark.integration,
    pytest.mark.kommo,
    pytest.mark.skipif(
        not os.getenv("KOMMO_ACCESS_TOKEN"),
        reason="KOMMO_ACCESS_TOKEN not set",
    ),
]


class _StaticTokenStore:
    """Minimal token store returning a static access token for live tests."""

    def __init__(self, token: str):
        self._token = token

    async def get_valid_token(self) -> str:
        return self._token

    async def force_refresh(self) -> str:
        return self._token


def _make_client():
    """Create fresh KommoClient (new httpx session per test)."""
    from telegram_bot.services.kommo_client import KommoClient

    return KommoClient(
        subdomain=os.environ["KOMMO_SUBDOMAIN"],
        token_store=_StaticTokenStore(os.environ["KOMMO_ACCESS_TOKEN"]),  # type: ignore[arg-type]
    )


# Shared state for ordered tests
_RUN_ID = f"ci-{int(time.time())}"


class TestKommoLiveCRUD:
    """Full CRUD lifecycle against real Kommo API."""

    _lead_id: int | None = None
    _contact_id: int | None = None

    async def test_01_create_lead(self):
        """Create a test lead."""
        from telegram_bot.services.kommo_models import LeadCreate

        client = _make_client()
        lead = await client.create_lead(LeadCreate(name=f"[CI] {_RUN_ID}", budget=1000))
        assert lead.id > 0
        TestKommoLiveCRUD._lead_id = lead.id

    async def test_02_get_lead(self):
        """Verify created lead via GET returns full fields."""
        assert self._lead_id, "test_01 must run first"

        client = _make_client()
        lead = await client.get_lead(self._lead_id)
        assert lead.id == self._lead_id
        assert lead.name == f"[CI] {_RUN_ID}"
        assert lead.budget == 1000

    async def test_03_update_lead(self):
        """Update lead budget and verify."""
        assert self._lead_id, "test_01 must run first"

        from telegram_bot.services.kommo_models import LeadUpdate

        client = _make_client()
        await client.update_lead(self._lead_id, LeadUpdate(budget=2000))

        refreshed = await client.get_lead(self._lead_id)
        assert refreshed.budget == 2000

    async def test_04_add_note(self):
        """Add note to lead."""
        assert self._lead_id, "test_01 must run first"

        client = _make_client()
        note = await client.add_note("leads", self._lead_id, f"Note {_RUN_ID}")
        assert note.id > 0

    async def test_05_create_task(self):
        """Create task linked to lead."""
        assert self._lead_id, "test_01 must run first"

        from telegram_bot.services.kommo_models import TaskCreate

        client = _make_client()
        due = int(time.time()) + 86400
        task = await client.create_task(
            TaskCreate(
                text=f"Task {_RUN_ID}",
                entity_id=self._lead_id,
                entity_type="leads",
                complete_till=due,
            )
        )
        assert task.id > 0

    async def test_06_upsert_contact(self):
        """Create a test contact via upsert."""
        from telegram_bot.services.kommo_models import ContactCreate

        client = _make_client()
        phone = f"+38099{_RUN_ID[-7:]}"
        contact = await client.upsert_contact(
            phone,
            ContactCreate(first_name="CI", last_name=_RUN_ID, phone=phone),
        )
        assert contact.id > 0
        TestKommoLiveCRUD._contact_id = contact.id

    async def test_07_link_contact_to_lead(self):
        """Link contact to lead."""
        assert self._lead_id, "test_01 must run first"
        assert self._contact_id, "test_06 must run first"

        client = _make_client()
        await client.link_contact_to_lead(self._lead_id, self._contact_id)

    async def test_08_list_pipelines(self):
        """List pipelines (smoke test)."""
        client = _make_client()
        pipelines = await client.list_pipelines()
        assert len(pipelines) > 0
        assert pipelines[0].id > 0
        assert pipelines[0].name

    async def test_09_get_contacts(self):
        """Search contacts by query."""
        client = _make_client()
        contacts = await client.get_contacts("CI")
        assert isinstance(contacts, list)
