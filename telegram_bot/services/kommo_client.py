"""Async Kommo CRM API adapter.

Pattern follows BGEM3Client: httpx.AsyncClient + tenacity retry + typed responses.
All methods auto-inject OAuth2 bearer token from KommoTokenStore.
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

from telegram_bot.services.kommo_models import (
    ContactResponse,
    LeadCreate,
    LeadResponse,
    NoteResponse,
    TaskCreate,
    TaskResponse,
)


if TYPE_CHECKING:
    from telegram_bot.services.kommo_models import ContactCreate
    from telegram_bot.services.kommo_tokens import KommoTokenStore


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
    """Async Kommo CRM API client."""

    def __init__(self, subdomain: str, token_store: KommoTokenStore) -> None:
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
        """Execute authenticated request with auto-refresh on 401."""
        token = await self._token_store.get_valid_token()
        headers = {"Authorization": f"Bearer {token}"}
        response = await self._client.request(method, path, headers=headers, **kwargs)

        # Retry once on 401 with refreshed token
        if response.status_code == 401:
            logger.warning("Kommo 401 — refreshing token")
            token = await self._token_store.force_refresh()
            headers["Authorization"] = f"Bearer {token}"
            response = await self._client.request(method, path, headers=headers, **kwargs)

        if response.status_code == 204:
            return {}

        # Raise for 429/5xx so tenacity can retry
        response.raise_for_status()
        response_json = response.json()
        if not isinstance(response_json, dict):
            msg = "Unexpected Kommo API response shape."
            raise RuntimeError(msg)
        return cast(dict[str, Any], response_json)

    # --- Leads ---

    async def create_lead(self, lead: LeadCreate) -> LeadResponse:
        """POST /leads — create a lead."""
        payload = lead.to_kommo_payload()
        resp = await self._request("POST", "/leads", json=[payload])
        lead_data = resp["_embedded"]["leads"][0]
        return LeadResponse(id=lead_data["id"], name=lead.name, price=lead.price or 0)

    # --- Contacts ---

    async def create_contact(self, data: ContactCreate) -> ContactResponse:
        """POST /contacts — create a contact."""
        payload = data.to_kommo_payload()
        resp = await self._request("POST", "/contacts", json=[payload])
        contact = resp["_embedded"]["contacts"][0]
        return ContactResponse(
            id=contact["id"],
            name=f"{data.first_name} {data.last_name}".strip(),
        )

    async def upsert_contact(self, phone: str, data: ContactCreate) -> ContactResponse:
        """Find contact by phone, or create new."""
        resp = await self._request("GET", "/contacts", params={"query": phone})
        contacts = resp.get("_embedded", {}).get("contacts", [])
        if contacts:
            c = contacts[0]
            return ContactResponse(id=c["id"], name=c.get("name", ""))
        return await self.create_contact(data)

    # --- Links ---

    async def link_contact_to_lead(self, lead_id: int, contact_id: int) -> None:
        """POST /leads/{id}/link — bind contact to lead."""
        payload = [{"to_entity_id": contact_id, "to_entity_type": "contacts"}]
        await self._request("POST", f"/leads/{lead_id}/link", json=payload)

    # --- Notes ---

    async def add_note(self, entity_type: str, entity_id: int, text: str) -> NoteResponse:
        """POST /{entity_type}/notes — add a text note."""
        payload = [{"entity_id": entity_id, "note_type": "common", "params": {"text": text}}]
        resp = await self._request("POST", f"/{entity_type}/notes", json=payload)
        note = resp["_embedded"]["notes"][0]
        return NoteResponse(id=note["id"])

    # --- Tasks ---

    async def create_task(self, task: TaskCreate) -> TaskResponse:
        """POST /tasks — create a task."""
        payload = task.to_kommo_payload()
        resp = await self._request("POST", "/tasks", json=[payload])
        t = resp["_embedded"]["tasks"][0]
        return TaskResponse(id=t["id"], text=task.text)

    # --- Lifecycle ---

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
