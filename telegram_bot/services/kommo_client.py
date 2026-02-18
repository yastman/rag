"""Async Kommo CRM API adapter (#413).

First-party httpx adapter with OAuth2 auto-refresh.
Pattern: BGEM3Client (same project).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import httpx

from telegram_bot.observability import observe
from telegram_bot.services.kommo_models import (
    Contact,
    ContactCreate,
    Lead,
    LeadCreate,
    LeadUpdate,
    Note,
    Pipeline,
    Task,
    TaskCreate,
)


if TYPE_CHECKING:
    from telegram_bot.services.kommo_token_store import KommoTokenStore

logger = logging.getLogger(__name__)


class KommoClient:
    """Async Kommo CRM API adapter with auto-refresh OAuth2."""

    def __init__(self, *, subdomain: str, token_store: KommoTokenStore):
        subdomain = subdomain.removesuffix(".kommo.com")
        self._base_url = f"https://{subdomain}.kommo.com/api/v4"
        self._token_store = token_store
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=5),
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        """Execute request with auto-refresh on 401."""
        token = await self._token_store.get_valid_token()
        headers = {"Authorization": f"Bearer {token}"}

        response = await self._client.request(method, path, headers=headers, **kwargs)

        if response.status_code == 401:
            token = await self._token_store.force_refresh()
            headers["Authorization"] = f"Bearer {token}"
            response = await self._client.request(method, path, headers=headers, **kwargs)

        response.raise_for_status()
        # Kommo returns 204/empty body for some endpoints (e.g. GET /contacts with no results)
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    # --- Leads ---

    @observe(name="kommo-create-lead")
    async def create_lead(self, lead: LeadCreate) -> Lead:
        """POST /api/v4/leads."""
        data = await self._request(
            "POST", "/leads", json=[lead.model_dump(exclude_none=True, by_alias=True)]
        )
        item = data["_embedded"]["leads"][0]
        return Lead(**item)

    @observe(name="kommo-get-lead")
    async def get_lead(self, lead_id: int) -> Lead:
        """GET /api/v4/leads/{id}."""
        data = await self._request("GET", f"/leads/{lead_id}")
        return Lead(**data)

    @observe(name="kommo-update-lead")
    async def update_lead(self, lead_id: int, update: LeadUpdate) -> Lead:
        """PATCH /api/v4/leads/{id}."""
        data = await self._request(
            "PATCH", f"/leads/{lead_id}", json=update.model_dump(exclude_none=True, by_alias=True)
        )
        return Lead(**data)

    # --- Contacts ---

    @observe(name="kommo-upsert-contact")
    async def upsert_contact(self, phone: str, contact: ContactCreate) -> Contact:
        """Find by phone or create new contact."""
        data = await self._request("GET", "/contacts", params={"query": phone})
        contacts = data.get("_embedded", {}).get("contacts", [])
        if contacts:
            return Contact(**contacts[0])

        data = await self._request(
            "POST", "/contacts", json=[contact.model_dump(exclude_none=True)]
        )
        item = data["_embedded"]["contacts"][0]
        return Contact(**item)

    @observe(name="kommo-get-contacts")
    async def get_contacts(self, query: str) -> list[Contact]:
        """GET /api/v4/contacts?query=..."""
        data = await self._request("GET", "/contacts", params={"query": query})
        items = data.get("_embedded", {}).get("contacts", [])
        return [Contact(**c) for c in items]

    # --- Notes ---

    @observe(name="kommo-add-note")
    async def add_note(self, entity_type: str, entity_id: int, text: str) -> Note:
        """POST /api/v4/{entity_type}/{id}/notes."""
        data = await self._request(
            "POST",
            f"/{entity_type}/{entity_id}/notes",
            json=[{"note_type": "common", "params": {"text": text}}],
        )
        item = data["_embedded"]["notes"][0]
        return Note(**item)

    # --- Tasks ---

    @observe(name="kommo-create-task")
    async def create_task(self, task: TaskCreate) -> Task:
        """POST /api/v4/tasks."""
        data = await self._request("POST", "/tasks", json=[task.model_dump(exclude_none=True)])
        item = data["_embedded"]["tasks"][0]
        return Task(**item)

    # --- Links ---

    @observe(name="kommo-link-contact")
    async def link_contact_to_lead(self, lead_id: int, contact_id: int) -> None:
        """POST /api/v4/leads/{id}/link."""
        await self._request(
            "POST",
            f"/leads/{lead_id}/link",
            json=[{"to_entity_id": contact_id, "to_entity_type": "contacts"}],
        )

    # --- Pipelines ---

    @observe(name="kommo-list-pipelines")
    async def list_pipelines(self) -> list[Pipeline]:
        """GET /api/v4/leads/pipelines."""
        data = await self._request("GET", "/leads/pipelines")
        items = data.get("_embedded", {}).get("pipelines", [])
        return [Pipeline(**p) for p in items]

    async def close(self) -> None:
        """Close httpx client."""
        await self._client.aclose()
