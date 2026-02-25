"""Async Kommo CRM API adapter (#413).

First-party httpx adapter with OAuth2 auto-refresh.
Pattern: BGEM3Client (same project).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from telegram_bot.observability import observe
from telegram_bot.services.kommo_models import (
    Contact,
    ContactCreate,
    ContactUpdate,
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

RETRYABLE = (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout, httpx.PoolTimeout)


def _retryable_http_status(exc: BaseException) -> bool:
    if not isinstance(exc, httpx.HTTPStatusError):
        return False
    return exc.response.status_code in {429, 500, 502, 503, 504}


_kommo_retry = retry(
    retry=retry_if_exception_type(RETRYABLE) | retry_if_exception(_retryable_http_status),
    wait=wait_exponential_jitter(initial=1, max=8, jitter=2),
    stop=stop_after_attempt(3),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


class KommoClient:
    """Async Kommo CRM API adapter with auto-refresh OAuth2."""

    def __init__(self, *, subdomain: str, token_store: KommoTokenStore):
        subdomain = subdomain.removesuffix(".kommo.com")
        self._base_url = f"https://{subdomain}.kommo.com/api/v4"
        self._token_store = token_store
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            headers={"Content-Type": "application/json"},
        )

    @_kommo_retry
    async def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        """Execute request with auto-refresh on 401."""
        token = await self._token_store.get_valid_token()
        extra_headers = kwargs.pop("headers", None) or {}
        headers = {"Authorization": f"Bearer {token}", **extra_headers}

        response = await self._client.request(method, path, headers=headers, **kwargs)

        if response.status_code == 401:
            token = await self._token_store.force_refresh()
            headers["Authorization"] = f"Bearer {token}"
            response = await self._client.request(method, path, headers=headers, **kwargs)

        if response.status_code == 204:
            return {}

        # Raises for 429/5xx so tenacity can retry.
        response.raise_for_status()

        # Kommo can return empty body on some successful endpoints.
        if not response.content:
            return {}

        response_json = response.json()
        if not isinstance(response_json, dict):
            msg = "Unexpected Kommo API response shape."
            raise RuntimeError(msg)
        return cast(dict[str, Any], response_json)

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

    @observe(name="kommo-search-leads")
    async def search_leads(
        self,
        query: str | None = None,
        responsible_user_id: int | None = None,
        limit: int = 50,
    ) -> list[Lead]:
        """GET /api/v4/leads with optional query or responsible_user_id filter."""
        params: dict[str, Any] = {"limit": limit}
        if query is not None:
            params["query"] = query
        if responsible_user_id is not None:
            params["filter[responsible_user_id][]"] = responsible_user_id
        data = await self._request("GET", "/leads", params=params)
        items = data.get("_embedded", {}).get("leads", [])
        return [Lead(**item) for item in items]

    @observe(name="kommo-get-tasks")
    async def get_tasks(
        self,
        responsible_user_id: int | None = None,
        is_completed: bool | None = None,
        limit: int = 50,
    ) -> list[Task]:
        """GET /api/v4/tasks with optional filters."""
        params: dict[str, Any] = {"limit": limit}
        if responsible_user_id is not None:
            params["filter[responsible_user_id][]"] = responsible_user_id
        if is_completed is not None:
            params["filter[is_completed]"] = int(is_completed)
        data = await self._request("GET", "/tasks", params=params)
        items = data.get("_embedded", {}).get("tasks", [])
        return [Task(**item) for item in items]

    # --- Contacts ---

    @observe(name="kommo-upsert-contact")
    async def upsert_contact(self, phone: str, contact: ContactCreate) -> Contact:
        """Find by phone or create new contact. Smart update: fills empty name fields."""
        data = await self._request("GET", "/contacts", params={"query": phone})
        contacts = data.get("_embedded", {}).get("contacts", [])
        if contacts:
            existing = Contact(**contacts[0])
            updates: dict[str, str] = {}
            if not existing.first_name and contact.first_name:
                updates["first_name"] = contact.first_name
            if not existing.last_name and contact.last_name:
                updates["last_name"] = contact.last_name
            if updates:
                from .kommo_models import ContactUpdate

                await self.update_contact(existing.id, ContactUpdate(**updates))
            return existing

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

    @observe(name="kommo-update-contact")
    async def update_contact(self, contact_id: int, update: ContactUpdate) -> Contact:
        """PATCH /api/v4/contacts/{id}."""
        data = await self._request(
            "PATCH",
            f"/contacts/{contact_id}",
            json=update.model_dump(exclude_none=True),
        )
        return Contact(**data)

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

    # --- Lead Scores (compatibility path for supervisor tools/tests) ---

    @observe(name="kommo-update-lead-score")
    async def update_lead_score(self, *, lead_id: int, payload: dict, idempotency_key: str) -> dict:
        """PATCH /api/v4/leads/{id} with score custom fields."""
        return await self._request(
            "PATCH",
            f"/leads/{lead_id}",
            json=payload,
            headers={"X-Idempotency-Key": idempotency_key},
        )

    async def close(self) -> None:
        """Close httpx client."""
        await self._client.aclose()
