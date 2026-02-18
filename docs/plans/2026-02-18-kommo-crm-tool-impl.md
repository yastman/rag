# Kommo CRM Deal Lifecycle — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement full Kommo CRM deal lifecycle as supervisor tools — async KommoClient, OAuth2 token management, 7 CRM tools integrated into the supervisor agent.

**Architecture:** First-party async adapter (`httpx` + `tenacity`) following `BGEM3Client` pattern. Tools registered conditionally via `KOMMO_ENABLED` flag. Token storage in Redis with auto-refresh.

**Tech Stack:** httpx, tenacity, pydantic v2, redis (async), langchain-core (@tool), langfuse (@observe)

**Design doc:** `docs/plans/2026-02-18-kommo-crm-tool-design.md`
**Issue:** #312 | **Epic:** #263

> **Review note (2026-02-18, plan-review):** The points below are mandatory corrections and override conflicting snippets in this file.
> - Use `history_service.get_session_turns(user_id, session_id, limit=...)` (existing service API), not `get_recent_messages(...)`.
> - Use `self._cache.redis` (not `self._cache._redis`) and guard for `None` before creating `KommoTokenStore`.
> - Add notes via `POST /api/v4/{entity_type}/notes` with `entity_id` in payload, not `/{entity_type}/{id}/notes`.
> - For `custom_fields_values`, pass `field_id` or `field_code` (not `field_name`); add explicit `KOMMO_SESSION_FIELD_ID`.
> - Implement idempotency in `crm_finalize_deal` using Redis `SET key NX EX`, plus `crm_deal_idempotent_skip` score.
> - Retry policy must include HTTP 429/5xx handling (backoff/jitter + `Retry-After` support), not only transport errors.
> - In `PropertyBot.stop()`, close `self._kommo_client` if initialized.
> - Final required gate is: `make check` and `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`.

---

## Task 1: Pydantic Models (`kommo_models.py`)

**Files:**
- Create: `telegram_bot/services/kommo_models.py`
- Test: `tests/unit/services/test_kommo_models.py`

**Step 1: Write the failing test**

```python
# tests/unit/services/test_kommo_models.py
"""Tests for Kommo CRM Pydantic models."""

from __future__ import annotations

import pytest


class TestDealDraft:
    def test_minimal_draft(self):
        from telegram_bot.services.kommo_models import DealDraft

        draft = DealDraft()
        assert draft.client_name is None
        assert draft.source == "telegram_bot"

    def test_full_draft(self):
        from telegram_bot.services.kommo_models import DealDraft

        draft = DealDraft(
            client_name="Иван Петров",
            phone="+380501234567",
            email="ivan@example.com",
            budget=50000,
            property_type="квартира",
            location="Несебр",
            notes="Интересует 2-комнатная у моря",
        )
        assert draft.client_name == "Иван Петров"
        assert draft.budget == 50000
        assert draft.source == "telegram_bot"

    def test_draft_json_roundtrip(self):
        from telegram_bot.services.kommo_models import DealDraft

        draft = DealDraft(client_name="Test", budget=100)
        data = draft.model_dump_json()
        restored = DealDraft.model_validate_json(data)
        assert restored.client_name == "Test"
        assert restored.budget == 100


class TestContactCreate:
    def test_contact_with_phone(self):
        from telegram_bot.services.kommo_models import ContactCreate

        contact = ContactCreate(
            first_name="Иван",
            last_name="Петров",
            phone="+380501234567",
        )
        assert contact.first_name == "Иван"
        assert contact.phone == "+380501234567"

    def test_contact_to_kommo_payload(self):
        from telegram_bot.services.kommo_models import ContactCreate

        contact = ContactCreate(
            first_name="Иван",
            last_name="Петров",
            phone="+380501234567",
            email="ivan@example.com",
            telegram_user_id=123456,
        )
        payload = contact.to_kommo_payload()
        assert payload["first_name"] == "Иван"
        assert payload["last_name"] == "Петров"
        # custom_fields_values should contain phone and email
        cfv = payload.get("custom_fields_values", [])
        assert any(f["field_code"] == "PHONE" for f in cfv)
        assert any(f["field_code"] == "EMAIL" for f in cfv)


class TestLeadCreate:
    def test_lead_minimal(self):
        from telegram_bot.services.kommo_models import LeadCreate

        lead = LeadCreate(name="Сделка по квартире")
        assert lead.name == "Сделка по квартире"
        assert lead.price is None

    def test_lead_to_kommo_payload(self):
        from telegram_bot.services.kommo_models import LeadCreate

        lead = LeadCreate(
            name="Сделка",
            price=50000,
            pipeline_id=123,
            responsible_user_id=456,
            session_id="chat_789_abc",
        )
        payload = lead.to_kommo_payload()
        assert payload["name"] == "Сделка"
        assert payload["price"] == 50000
        assert payload["pipeline_id"] == 123
        # session_id should be in custom_fields_values
        cfv = payload.get("custom_fields_values", [])
        assert len(cfv) >= 1


class TestTaskCreate:
    def test_task_create(self):
        from telegram_bot.services.kommo_models import TaskCreate

        task = TaskCreate(
            text="Перезвонить клиенту",
            entity_id=100,
            entity_type="leads",
            complete_till=1739900000,
        )
        assert task.text == "Перезвонить клиенту"
        assert task.task_type_id == 1  # default: follow-up

    def test_task_to_kommo_payload(self):
        from telegram_bot.services.kommo_models import TaskCreate

        task = TaskCreate(
            text="Follow up",
            entity_id=100,
            entity_type="leads",
            complete_till=1739900000,
            responsible_user_id=456,
        )
        payload = task.to_kommo_payload()
        assert payload["text"] == "Follow up"
        assert payload["entity_id"] == 100
        assert payload["complete_till"] == 1739900000


class TestKommoResponse:
    def test_lead_response(self):
        from telegram_bot.services.kommo_models import LeadResponse

        resp = LeadResponse(id=12345, name="Сделка", price=50000)
        assert resp.id == 12345

    def test_contact_response(self):
        from telegram_bot.services.kommo_models import ContactResponse

        resp = ContactResponse(id=67890, name="Иван Петров")
        assert resp.id == 67890

    def test_task_response(self):
        from telegram_bot.services.kommo_models import TaskResponse

        resp = TaskResponse(id=111, text="Follow up")
        assert resp.id == 111
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/services/test_kommo_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'telegram_bot.services.kommo_models'`

**Step 3: Write minimal implementation**

```python
# telegram_bot/services/kommo_models.py
"""Pydantic v2 models for Kommo CRM API."""

from __future__ import annotations

from pydantic import BaseModel, Field


# --- Request Models ---


class DealDraft(BaseModel):
    """Structured deal data extracted from chat history by LLM."""

    client_name: str | None = None
    phone: str | None = None
    email: str | None = None
    budget: int | None = None
    property_type: str | None = None
    location: str | None = None
    notes: str | None = None
    source: str = "telegram_bot"


class ContactCreate(BaseModel):
    """Data for creating/upserting a Kommo contact."""

    first_name: str = ""
    last_name: str = ""
    phone: str | None = None
    email: str | None = None
    telegram_user_id: int | None = None
    responsible_user_id: int | None = None

    def to_kommo_payload(self) -> dict:
        """Convert to Kommo API request body."""
        payload: dict = {}
        if self.first_name:
            payload["first_name"] = self.first_name
        if self.last_name:
            payload["last_name"] = self.last_name
        if self.responsible_user_id:
            payload["responsible_user_id"] = self.responsible_user_id

        custom_fields: list[dict] = []
        if self.phone:
            custom_fields.append(
                {"field_code": "PHONE", "values": [{"value": self.phone, "enum_code": "MOB"}]}
            )
        if self.email:
            custom_fields.append(
                {"field_code": "EMAIL", "values": [{"value": self.email, "enum_code": "WORK"}]}
            )
        if custom_fields:
            payload["custom_fields_values"] = custom_fields

        return payload


class LeadCreate(BaseModel):
    """Data for creating a Kommo lead."""

    name: str
    price: int | None = None
    pipeline_id: int | None = None
    status_id: int | None = None
    responsible_user_id: int | None = None
    session_id: str | None = None
    session_field_id: int | None = None
    tags: list[str] = Field(default_factory=list)

    def to_kommo_payload(self) -> dict:
        """Convert to Kommo API request body."""
        payload: dict = {"name": self.name}
        if self.price is not None:
            payload["price"] = self.price
        if self.pipeline_id is not None:
            payload["pipeline_id"] = self.pipeline_id
        if self.status_id is not None:
            payload["status_id"] = self.status_id
        if self.responsible_user_id is not None:
            payload["responsible_user_id"] = self.responsible_user_id

        custom_fields: list[dict] = []
        if self.session_id and self.session_field_id:
            custom_fields.append(
                {"field_id": self.session_field_id, "values": [{"value": self.session_id}]}
            )
        if custom_fields:
            payload["custom_fields_values"] = custom_fields

        if self.tags:
            payload["_embedded"] = {
                "tags": [{"name": t} for t in self.tags],
            }
        return payload


class TaskCreate(BaseModel):
    """Data for creating a Kommo task."""

    text: str
    entity_id: int
    entity_type: str = "leads"
    task_type_id: int = 1  # 1 = Follow-up
    complete_till: int = 0  # Unix timestamp
    responsible_user_id: int | None = None

    def to_kommo_payload(self) -> dict:
        """Convert to Kommo API request body."""
        payload: dict = {
            "text": self.text,
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "task_type_id": self.task_type_id,
            "complete_till": self.complete_till,
        }
        if self.responsible_user_id is not None:
            payload["responsible_user_id"] = self.responsible_user_id
        return payload


# --- Response Models ---


class LeadResponse(BaseModel):
    """Kommo lead from API response."""

    id: int
    name: str = ""
    price: int = 0


class ContactResponse(BaseModel):
    """Kommo contact from API response."""

    id: int
    name: str = ""


class TaskResponse(BaseModel):
    """Kommo task from API response."""

    id: int
    text: str = ""


class NoteResponse(BaseModel):
    """Kommo note from API response."""

    id: int
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/services/test_kommo_models.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add telegram_bot/services/kommo_models.py tests/unit/services/test_kommo_models.py
git commit -m "feat(crm): add Pydantic models for Kommo CRM API (#312)"
```

---

## Task 2: Config Extension

**Files:**
- Modify: `telegram_bot/config.py:331-346` (extend existing kommo fields)
- Test: `tests/unit/config/test_bot_config_kommo.py`

**Step 1: Write the failing test**

```python
# tests/unit/config/test_bot_config_kommo.py
"""Tests for Kommo CRM config fields."""

from __future__ import annotations


class TestKommoConfig:
    def test_kommo_disabled_by_default(self):
        from telegram_bot.config import BotConfig

        config = BotConfig(telegram_token="test", llm_api_key="test")
        assert config.kommo_enabled is False

    def test_kommo_config_fields_exist(self):
        from telegram_bot.config import BotConfig

        config = BotConfig(
            telegram_token="test",
            llm_api_key="test",
            kommo_enabled=True,
            kommo_subdomain="mycompany",
            kommo_client_id="abc123",
            kommo_client_secret="secret",
            kommo_redirect_uri="https://example.com/callback",
            kommo_default_pipeline_id=100,
        )
        assert config.kommo_enabled is True
        assert config.kommo_subdomain == "mycompany"
        assert config.kommo_client_id == "abc123"
        assert config.kommo_client_secret.get_secret_value() == "secret"
        assert config.kommo_redirect_uri == "https://example.com/callback"
        assert config.kommo_default_pipeline_id == 100

    def test_kommo_auth_code_optional(self):
        from telegram_bot.config import BotConfig

        config = BotConfig(telegram_token="test", llm_api_key="test")
        assert config.kommo_auth_code == ""

    def test_kommo_responsible_user_id_optional(self):
        from telegram_bot.config import BotConfig

        config = BotConfig(telegram_token="test", llm_api_key="test")
        assert config.kommo_responsible_user_id is None

    def test_kommo_session_field_id_default(self):
        from telegram_bot.config import BotConfig

        config = BotConfig(telegram_token="test", llm_api_key="test")
        assert config.kommo_session_field_id == 0
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/config/test_bot_config_kommo.py -v`
Expected: FAIL — `kommo_client_id` field not found

**Step 3: Modify config.py — add new fields after existing kommo_telegram_field_id**

In `telegram_bot/config.py`, after line 346 (`kommo_telegram_field_id`), add:

```python
    kommo_client_id: str = Field(
        default="",
        validation_alias=AliasChoices("kommo_client_id", "KOMMO_CLIENT_ID"),
    )
    kommo_client_secret: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("kommo_client_secret", "KOMMO_CLIENT_SECRET"),
    )
    kommo_redirect_uri: str = Field(
        default="",
        validation_alias=AliasChoices("kommo_redirect_uri", "KOMMO_REDIRECT_URI"),
    )
    kommo_auth_code: str = Field(
        default="",
        validation_alias=AliasChoices("kommo_auth_code", "KOMMO_AUTH_CODE"),
    )
    kommo_default_pipeline_id: int = Field(
        default=0,
        validation_alias=AliasChoices("kommo_default_pipeline_id", "KOMMO_DEFAULT_PIPELINE_ID"),
    )
    kommo_responsible_user_id: int | None = Field(
        default=None,
        validation_alias=AliasChoices("kommo_responsible_user_id", "KOMMO_RESPONSIBLE_USER_ID"),
    )
    kommo_session_field_id: int = Field(
        default=0,
        validation_alias=AliasChoices("kommo_session_field_id", "KOMMO_SESSION_FIELD_ID"),
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/config/test_bot_config_kommo.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add telegram_bot/config.py tests/unit/config/test_bot_config_kommo.py
git commit -m "feat(crm): add Kommo OAuth2 config fields (#312)"
```

---

## Task 3: Token Store (`kommo_tokens.py`)

**Files:**
- Create: `telegram_bot/services/kommo_tokens.py`
- Test: `tests/unit/services/test_kommo_tokens.py`

**Step 1: Write the failing test**

```python
# tests/unit/services/test_kommo_tokens.py
"""Tests for Kommo OAuth2 token store (Redis-backed)."""

from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_redis():
    """Create a mock async Redis client."""
    redis = AsyncMock()
    redis.hgetall = AsyncMock(return_value={})
    redis.hset = AsyncMock()
    redis.close = AsyncMock()
    return redis


@pytest.fixture
def token_store(mock_redis):
    from telegram_bot.services.kommo_tokens import KommoTokenStore

    store = KommoTokenStore(
        redis=mock_redis,
        client_id="test_client_id",
        client_secret="test_secret",
        subdomain="testcompany",
        redirect_uri="https://example.com/callback",
    )
    return store


class TestKommoTokenStore:
    @pytest.mark.asyncio
    async def test_get_valid_token_from_cache(self, token_store, mock_redis):
        """Return cached token when not expired."""
        future_ts = str(int(time.time()) + 3600)
        mock_redis.hgetall.return_value = {
            b"access_token": b"cached_token",
            b"refresh_token": b"refresh_123",
            b"expires_at": future_ts.encode(),
        }
        token = await token_store.get_valid_token()
        assert token == "cached_token"

    @pytest.mark.asyncio
    async def test_get_valid_token_refreshes_when_near_expiry(self, token_store, mock_redis):
        """Auto-refresh when token expires within REFRESH_BUFFER_SEC."""
        near_expiry_ts = str(int(time.time()) + 60)  # 60s left, buffer is 300s
        mock_redis.hgetall.return_value = {
            b"access_token": b"old_token",
            b"refresh_token": b"refresh_123",
            b"expires_at": near_expiry_ts.encode(),
        }
        with patch.object(token_store, "_refresh_tokens", new_callable=AsyncMock) as mock_refresh:
            mock_refresh.return_value = "new_token"
            token = await token_store.get_valid_token()
            assert token == "new_token"
            mock_refresh.assert_called_once_with("refresh_123")

    @pytest.mark.asyncio
    async def test_get_valid_token_raises_when_no_tokens(self, token_store, mock_redis):
        """Raise when no tokens stored and no auth code."""
        mock_redis.hgetall.return_value = {}
        with pytest.raises(RuntimeError, match="No Kommo tokens"):
            await token_store.get_valid_token()

    @pytest.mark.asyncio
    async def test_force_refresh(self, token_store, mock_redis):
        """Force refresh retrieves new tokens."""
        mock_redis.hgetall.return_value = {
            b"access_token": b"old",
            b"refresh_token": b"refresh_123",
            b"expires_at": b"0",
        }
        with patch.object(token_store, "_refresh_tokens", new_callable=AsyncMock) as mock_refresh:
            mock_refresh.return_value = "brand_new_token"
            token = await token_store.force_refresh()
            assert token == "brand_new_token"

    @pytest.mark.asyncio
    async def test_initialize_with_auth_code(self, token_store, mock_redis):
        """Exchange auth code for initial tokens."""
        with patch.object(
            token_store, "_exchange_auth_code", new_callable=AsyncMock
        ) as mock_exchange:
            mock_exchange.return_value = "initial_token"
            token = await token_store.initialize(authorization_code="auth_code_123")
            assert token == "initial_token"
            mock_exchange.assert_called_once_with("auth_code_123")

    @pytest.mark.asyncio
    async def test_save_tokens_to_redis(self, token_store, mock_redis):
        """Verify tokens are persisted to Redis hash."""
        await token_store._save_tokens(
            access_token="at_123",
            refresh_token="rt_456",
            expires_in=86400,
        )
        mock_redis.hset.assert_called_once()
        call_kwargs = mock_redis.hset.call_args
        assert call_kwargs[0][0] == "kommo:oauth:tokens"  # key
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/services/test_kommo_tokens.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# telegram_bot/services/kommo_tokens.py
"""Redis-backed OAuth2 token store for Kommo CRM.

Handles token lifecycle: initial exchange, auto-refresh, persistence.
Pattern: stateless reads (Redis), atomic writes.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx


logger = logging.getLogger(__name__)

REDIS_KEY = "kommo:oauth:tokens"
REFRESH_BUFFER_SEC = 300  # refresh 5 min before expiry


class KommoTokenStore:
    """Manage Kommo OAuth2 tokens with Redis persistence."""

    def __init__(
        self,
        *,
        redis: Any,
        client_id: str,
        client_secret: str,
        subdomain: str,
        redirect_uri: str,
    ) -> None:
        self._redis = redis
        self._client_id = client_id
        self._client_secret = client_secret
        self._subdomain = subdomain
        self._redirect_uri = redirect_uri
        self._token_url = f"https://{subdomain}.kommo.com/oauth2/access_token"

    async def get_valid_token(self) -> str:
        """Return valid access_token, refreshing if near expiry."""
        data = await self._load_tokens()
        if not data:
            msg = "No Kommo tokens found in Redis. Call initialize() first."
            raise RuntimeError(msg)

        access_token = data.get("access_token", "")
        refresh_token = data.get("refresh_token", "")
        expires_at = int(data.get("expires_at", 0))

        if time.time() + REFRESH_BUFFER_SEC >= expires_at:
            logger.info("Kommo token near expiry, refreshing")
            return await self._refresh_tokens(refresh_token)

        return access_token

    async def force_refresh(self) -> str:
        """Force token refresh (e.g. after 401)."""
        data = await self._load_tokens()
        refresh_token = data.get("refresh_token", "") if data else ""
        if not refresh_token:
            msg = "No refresh_token available for Kommo."
            raise RuntimeError(msg)
        return await self._refresh_tokens(refresh_token)

    async def initialize(self, authorization_code: str | None = None) -> str:
        """First-time setup: exchange auth code for token pair.

        If tokens already exist in Redis, returns the current valid token.
        """
        if authorization_code:
            return await self._exchange_auth_code(authorization_code)

        # Try loading existing tokens
        data = await self._load_tokens()
        if data and data.get("access_token"):
            return await self.get_valid_token()

        msg = "No Kommo tokens and no authorization_code provided."
        raise RuntimeError(msg)

    async def _exchange_auth_code(self, code: str) -> str:
        """Exchange authorization code for access + refresh tokens."""
        payload = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._redirect_uri,
        }
        resp = await self._token_request(payload)
        await self._save_tokens(
            access_token=resp["access_token"],
            refresh_token=resp["refresh_token"],
            expires_in=resp["expires_in"],
        )
        return resp["access_token"]

    async def _refresh_tokens(self, refresh_token: str) -> str:
        """Refresh the access token using refresh_token."""
        payload = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "redirect_uri": self._redirect_uri,
        }
        resp = await self._token_request(payload)
        await self._save_tokens(
            access_token=resp["access_token"],
            refresh_token=resp["refresh_token"],
            expires_in=resp["expires_in"],
        )
        return resp["access_token"]

    async def _token_request(self, payload: dict) -> dict:
        """POST to Kommo OAuth2 token endpoint."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(self._token_url, json=payload)
            response.raise_for_status()
            return response.json()

    async def _save_tokens(
        self, *, access_token: str, refresh_token: str, expires_in: int
    ) -> None:
        """Persist tokens to Redis hash."""
        expires_at = int(time.time()) + expires_in
        await self._redis.hset(
            REDIS_KEY,
            mapping={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": str(expires_at),
                "subdomain": self._subdomain,
            },
        )
        logger.info("Kommo tokens saved (expires_in=%ds)", expires_in)

    async def _load_tokens(self) -> dict[str, str] | None:
        """Load tokens from Redis hash."""
        raw = await self._redis.hgetall(REDIS_KEY)
        if not raw:
            return None
        # Decode bytes → str
        return {
            k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v
            for k, v in raw.items()
        }
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/services/test_kommo_tokens.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add telegram_bot/services/kommo_tokens.py tests/unit/services/test_kommo_tokens.py
git commit -m "feat(crm): add Kommo OAuth2 token store with Redis persistence (#312)"
```

---

## Task 4: KommoClient (`kommo_client.py`)

**Files:**
- Create: `telegram_bot/services/kommo_client.py`
- Test: `tests/unit/services/test_kommo_client.py`

**Ref:** `telegram_bot/services/bge_m3_client.py` for httpx + tenacity pattern.

**Step 1: Write the failing test**

```python
# tests/unit/services/test_kommo_client.py
"""Tests for KommoClient async HTTP adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest


@pytest.fixture
def mock_token_store():
    store = AsyncMock()
    store.get_valid_token = AsyncMock(return_value="test_access_token")
    store.force_refresh = AsyncMock(return_value="refreshed_token")
    return store


@pytest.fixture
def kommo_client(mock_token_store):
    from telegram_bot.services.kommo_client import KommoClient

    client = KommoClient(subdomain="testcompany", token_store=mock_token_store)
    return client


class TestKommoClientRequest:
    @pytest.mark.asyncio
    async def test_request_adds_auth_header(self, kommo_client, mock_token_store):
        """Verify Authorization header is set."""
        mock_response = httpx.Response(200, json={"_embedded": {"leads": [{"id": 1}]}})
        with patch.object(kommo_client._client, "request", return_value=mock_response) as mock_req:
            result = await kommo_client._request("GET", "/leads")
            call_kwargs = mock_req.call_args
            assert "Bearer test_access_token" in str(call_kwargs)

    @pytest.mark.asyncio
    async def test_request_retries_on_401(self, kommo_client, mock_token_store):
        """Auto-refresh token on 401 and retry."""
        resp_401 = httpx.Response(401, json={"detail": "Unauthorized"})
        resp_200 = httpx.Response(200, json={"ok": True})
        with patch.object(
            kommo_client._client, "request", side_effect=[resp_401, resp_200]
        ):
            result = await kommo_client._request("GET", "/leads")
            assert result == {"ok": True}
            mock_token_store.force_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_retries_on_429(self, kommo_client):
        req = httpx.Request("GET", "https://testcompany.kommo.com/api/v4/leads")
        resp_429 = httpx.Response(429, headers={"Retry-After": "1"}, request=req)
        resp_200 = httpx.Response(200, json={"ok": True}, request=req)
        with patch.object(kommo_client._client, "request", side_effect=[resp_429, resp_200]):
            assert await kommo_client._request("GET", "/leads") == {"ok": True}

    @pytest.mark.asyncio
    async def test_request_retries_on_5xx(self, kommo_client):
        req = httpx.Request("GET", "https://testcompany.kommo.com/api/v4/leads")
        resp_503 = httpx.Response(503, request=req)
        resp_200 = httpx.Response(200, json={"ok": True}, request=req)
        with patch.object(kommo_client._client, "request", side_effect=[resp_503, resp_200]):
            assert await kommo_client._request("GET", "/leads") == {"ok": True}


class TestKommoClientLeads:
    @pytest.mark.asyncio
    async def test_create_lead(self, kommo_client):
        from telegram_bot.services.kommo_models import LeadCreate, LeadResponse

        mock_resp = httpx.Response(
            200, json={"_embedded": {"leads": [{"id": 999, "request_id": "0"}]}}
        )
        with patch.object(kommo_client._client, "request", return_value=mock_resp):
            lead_data = LeadCreate(name="Test Lead", price=50000, pipeline_id=100)
            result = await kommo_client.create_lead(lead_data)
            assert result.id == 999


class TestKommoClientContacts:
    @pytest.mark.asyncio
    async def test_create_contact(self, kommo_client):
        from telegram_bot.services.kommo_models import ContactCreate, ContactResponse

        mock_resp = httpx.Response(
            200, json={"_embedded": {"contacts": [{"id": 888, "request_id": "0"}]}}
        )
        with patch.object(kommo_client._client, "request", return_value=mock_resp):
            contact_data = ContactCreate(first_name="Иван", phone="+380501234567")
            result = await kommo_client.create_contact(contact_data)
            assert result.id == 888

    @pytest.mark.asyncio
    async def test_upsert_contact_existing(self, kommo_client):
        """Upsert returns existing contact when phone matches."""
        search_resp = httpx.Response(
            200,
            json={"_embedded": {"contacts": [{"id": 777, "name": "Existing"}]}},
        )
        with patch.object(kommo_client._client, "request", return_value=search_resp):
            from telegram_bot.services.kommo_models import ContactCreate

            result = await kommo_client.upsert_contact(
                phone="+380501234567",
                data=ContactCreate(first_name="Иван"),
            )
            assert result.id == 777

    @pytest.mark.asyncio
    async def test_upsert_contact_creates_new(self, kommo_client):
        """Upsert creates new contact when phone not found."""
        search_resp = httpx.Response(200, json={"_embedded": {"contacts": []}})
        create_resp = httpx.Response(
            200, json={"_embedded": {"contacts": [{"id": 666, "request_id": "0"}]}}
        )
        with patch.object(
            kommo_client._client, "request", side_effect=[search_resp, create_resp]
        ):
            from telegram_bot.services.kommo_models import ContactCreate

            result = await kommo_client.upsert_contact(
                phone="+380501234567",
                data=ContactCreate(first_name="Новый"),
            )
            assert result.id == 666


class TestKommoClientNotes:
    @pytest.mark.asyncio
    async def test_add_note(self, kommo_client):
        mock_resp = httpx.Response(
            200, json={"_embedded": {"notes": [{"id": 555}]}}
        )
        with patch.object(kommo_client._client, "request", return_value=mock_resp):
            result = await kommo_client.add_note(
                entity_type="leads", entity_id=100, text="Итог беседы"
            )
            assert result.id == 555


class TestKommoClientTasks:
    @pytest.mark.asyncio
    async def test_create_task(self, kommo_client):
        from telegram_bot.services.kommo_models import TaskCreate

        mock_resp = httpx.Response(
            200, json={"_embedded": {"tasks": [{"id": 444}]}}
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
    @pytest.mark.asyncio
    async def test_link_contact_to_lead(self, kommo_client):
        mock_resp = httpx.Response(204)
        with patch.object(kommo_client._client, "request", return_value=mock_resp):
            await kommo_client.link_contact_to_lead(lead_id=100, contact_id=200)
            # No exception = success
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/services/test_kommo_client.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# telegram_bot/services/kommo_client.py
"""Async Kommo CRM API adapter.

Pattern follows BGEM3Client: httpx.AsyncClient + tenacity retry + typed responses.
All methods auto-inject OAuth2 bearer token from KommoTokenStore.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

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
        if response.status_code == 429:
            # Optional: honor Retry-After for rate limits before raising.
            ...
        response.raise_for_status()
        return response.json()

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
        # Search by phone
        resp = await self._request("GET", "/contacts", params={"query": phone})
        contacts = resp.get("_embedded", {}).get("contacts", [])
        if contacts:
            c = contacts[0]
            return ContactResponse(id=c["id"], name=c.get("name", ""))
        # Create new
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
        resp = await self._request(
            "POST", f"/{entity_type}/notes", json=payload
        )
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
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/services/test_kommo_client.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add telegram_bot/services/kommo_client.py tests/unit/services/test_kommo_client.py
git commit -m "feat(crm): add KommoClient async HTTP adapter (#312)"
```

---

## Task 5: CRM Tools (`crm_tools.py`)

**Files:**
- Create: `telegram_bot/agents/crm_tools.py`
- Test: `tests/unit/agents/test_crm_tools.py`

**Step 1: Write the failing test**

```python
# tests/unit/agents/test_crm_tools.py
"""Tests for Kommo CRM supervisor tools."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.services.kommo_models import (
    ContactResponse,
    DealDraft,
    LeadResponse,
    NoteResponse,
    TaskResponse,
)


@pytest.fixture
def mock_kommo():
    client = AsyncMock()
    client.create_lead = AsyncMock(return_value=LeadResponse(id=100, name="Test", price=50000))
    client.upsert_contact = AsyncMock(return_value=ContactResponse(id=200, name="Иван"))
    client.link_contact_to_lead = AsyncMock()
    client.add_note = AsyncMock(return_value=NoteResponse(id=300))
    client.create_task = AsyncMock(return_value=TaskResponse(id=400, text="Follow up"))
    return client


@pytest.fixture
def mock_llm():
    return AsyncMock()


@pytest.fixture
def mock_history():
    svc = AsyncMock()
    svc.get_session_turns = AsyncMock(return_value=[
        {"role": "user", "content": "Ищу квартиру в Несебре, бюджет 50000"},
        {"role": "assistant", "content": "Могу предложить 2-комнатную..."},
        {"role": "user", "content": "Отлично! Меня зовут Иван, телефон +380501234567"},
    ])
    return svc


@pytest.fixture
def runnable_config():
    return {"configurable": {"user_id": 12345, "session_id": "chat_789"}}


class TestCreateCrmTools:
    def test_returns_list_of_tools(self, mock_kommo, mock_llm, mock_history):
        from telegram_bot.agents.crm_tools import create_crm_tools

        tools = create_crm_tools(
            kommo=mock_kommo, llm=mock_llm, history_service=mock_history,
            default_pipeline_id=1, responsible_user_id=None, session_field_id=123,
        )
        assert len(tools) == 7
        tool_names = [t.name for t in tools]
        assert "crm_generate_deal_draft" in tool_names
        assert "crm_upsert_contact" in tool_names
        assert "crm_create_deal" in tool_names
        assert "crm_link_contact_to_deal" in tool_names
        assert "crm_add_note" in tool_names
        assert "crm_create_followup_task" in tool_names
        assert "crm_finalize_deal" in tool_names


class TestCrmUpsertContact:
    @pytest.mark.asyncio
    async def test_upsert_contact_tool(self, mock_kommo, mock_llm, mock_history, runnable_config):
        from telegram_bot.agents.crm_tools import create_crm_tools

        tools = create_crm_tools(
            kommo=mock_kommo, llm=mock_llm, history_service=mock_history,
            default_pipeline_id=1, responsible_user_id=None, session_field_id=123,
        )
        upsert_tool = next(t for t in tools if t.name == "crm_upsert_contact")
        result = await upsert_tool.ainvoke(
            {"phone": "+380501234567", "first_name": "Иван"},
            config=runnable_config,
        )
        assert "200" in result or "Иван" in result  # contact ID or name in response
        mock_kommo.upsert_contact.assert_called_once()


class TestCrmCreateDeal:
    @pytest.mark.asyncio
    async def test_create_deal_tool(self, mock_kommo, mock_llm, mock_history, runnable_config):
        from telegram_bot.agents.crm_tools import create_crm_tools

        tools = create_crm_tools(
            kommo=mock_kommo, llm=mock_llm, history_service=mock_history,
            default_pipeline_id=1, responsible_user_id=None, session_field_id=123,
        )
        deal_tool = next(t for t in tools if t.name == "crm_create_deal")
        result = await deal_tool.ainvoke(
            {"name": "Квартира в Несебре", "price": 50000},
            config=runnable_config,
        )
        assert "100" in result  # lead ID in response
        mock_kommo.create_lead.assert_called_once()


class TestCrmAddNote:
    @pytest.mark.asyncio
    async def test_add_note_tool(self, mock_kommo, mock_llm, mock_history, runnable_config):
        from telegram_bot.agents.crm_tools import create_crm_tools

        tools = create_crm_tools(
            kommo=mock_kommo, llm=mock_llm, history_service=mock_history,
            default_pipeline_id=1, responsible_user_id=None, session_field_id=123,
        )
        note_tool = next(t for t in tools if t.name == "crm_add_note")
        result = await note_tool.ainvoke(
            {"deal_id": 100, "text": "Клиент заинтересован"},
            config=runnable_config,
        )
        assert "300" in result  # note ID
        mock_kommo.add_note.assert_called_once()


class TestCrmFinalizeDeal:
    @pytest.mark.asyncio
    async def test_finalize_deal_orchestrates_all_steps(
        self, mock_kommo, mock_llm, mock_history, runnable_config
    ):
        from telegram_bot.agents.crm_tools import create_crm_tools

        # Mock LLM to return structured DealDraft
        draft = DealDraft(
            client_name="Иван Петров",
            phone="+380501234567",
            budget=50000,
            property_type="квартира",
            location="Несебр",
            notes="2-комнатная у моря",
        )
        mock_llm.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content=draft.model_dump_json()))]
            )
        )

        tools = create_crm_tools(
            kommo=mock_kommo, llm=mock_llm, history_service=mock_history,
            default_pipeline_id=1, responsible_user_id=None, session_field_id=123,
        )
        finalize_tool = next(t for t in tools if t.name == "crm_finalize_deal")
        result = await finalize_tool.ainvoke(
            {"query": "создай сделку"},
            config=runnable_config,
        )

        # All steps should be called
        mock_kommo.upsert_contact.assert_called_once()
        mock_kommo.create_lead.assert_called_once()
        mock_kommo.link_contact_to_lead.assert_called_once_with(lead_id=100, contact_id=200)
        mock_kommo.add_note.assert_called_once()
        mock_kommo.create_task.assert_called_once()
        assert "100" in result  # lead ID in response

    @pytest.mark.asyncio
    async def test_finalize_deal_idempotent_skip(
        self, mock_kommo, mock_llm, mock_history, runnable_config
    ):
        from telegram_bot.agents.crm_tools import create_crm_tools

        # redis-like idempotency store: first call sets key, second call sees duplicate
        idem_store = AsyncMock()
        idem_store.set = AsyncMock(side_effect=[True, False])

        tools = create_crm_tools(
            kommo=mock_kommo,
            llm=mock_llm,
            history_service=mock_history,
            default_pipeline_id=1,
            responsible_user_id=None,
            session_field_id=123,
            idempotency_store=idem_store,
        )
        finalize_tool = next(t for t in tools if t.name == "crm_finalize_deal")
        await finalize_tool.ainvoke({"query": "создай сделку"}, config=runnable_config)
        second = await finalize_tool.ainvoke({"query": "создай сделку"}, config=runnable_config)

        assert "idempotent" in second.lower() or "already" in second.lower()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/agents/test_crm_tools.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# telegram_bot/agents/crm_tools.py
"""Kommo CRM supervisor tools (#312).

7 tools for deal lifecycle: draft, upsert_contact, create_deal,
link_contact, add_note, create_task, finalize_deal.

Pattern: factory function with dependency injection (same as tools.py).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from telegram_bot.observability import get_client, observe
from telegram_bot.services.kommo_models import (
    ContactCreate,
    DealDraft,
    LeadCreate,
    TaskCreate,
)


logger = logging.getLogger(__name__)

DEAL_DRAFT_SYSTEM_PROMPT = """\
Extract structured deal information from chat history.
Return ONLY a JSON object with these fields (null if not found):
- client_name: full name
- phone: phone number with country code
- email: email address
- budget: numeric budget in local currency
- property_type: type of property
- location: location/city
- notes: brief summary of requirements
- source: always "telegram_bot"
"""


def _get_user_context(config: RunnableConfig) -> tuple[int | None, str | None]:
    configurable = (config or {}).get("configurable", {})
    return configurable.get("user_id"), configurable.get("session_id")


def create_crm_tools(
    *,
    kommo: Any,
    llm: Any,
    history_service: Any,
    default_pipeline_id: int,
    responsible_user_id: int | None,
    session_field_id: int,
    idempotency_store: Any,
) -> list[Any]:
    """Create all CRM supervisor tools with injected dependencies."""

    @tool
    @observe(name="crm-generate-deal-draft")
    async def crm_generate_deal_draft(query: str, config: RunnableConfig) -> str:
        """Generate a structured deal draft by extracting data from chat history using LLM.

        Use this when you need to prepare deal data before creating it in CRM.
        Returns JSON with extracted client info (name, phone, budget, property type).
        """
        user_id, session_id = _get_user_context(config)
        if not user_id:
            return "Error: user context not available."

        messages = await history_service.get_session_turns(user_id, session_id, limit=40)
        chat_text = "\n".join(
            f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages
        )

        response = await llm.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": DEAL_DRAFT_SYSTEM_PROMPT},
                {"role": "user", "content": f"Chat history:\n{chat_text}"},
            ],
            name="crm-deal-draft-extraction",
        )
        draft_json = response.choices[0].message.content
        try:
            draft = DealDraft.model_validate_json(draft_json)
        except Exception:
            logger.warning("Failed to parse DealDraft, returning raw: %s", draft_json[:200])
            return draft_json or "Failed to generate deal draft."

        return draft.model_dump_json()

    @tool
    @observe(name="crm-upsert-contact")
    async def crm_upsert_contact(
        phone: str,
        first_name: str = "",
        last_name: str = "",
        email: str = "",
        config: RunnableConfig = None,
    ) -> str:
        """Find or create a contact in Kommo CRM by phone number.

        Use this to ensure the client exists in CRM before creating a deal.
        Returns the contact ID and name.
        """
        data = ContactCreate(
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email or None,
            responsible_user_id=responsible_user_id,
        )
        contact = await kommo.upsert_contact(phone=phone, data=data)
        return json.dumps({"contact_id": contact.id, "name": contact.name})

    @tool
    @observe(name="crm-create-deal")
    async def crm_create_deal(
        name: str,
        price: int = 0,
        config: RunnableConfig = None,
    ) -> str:
        """Create a new deal (lead) in Kommo CRM pipeline.

        Use this to register a new sales opportunity.
        Returns the deal ID.
        """
        user_id, session_id = _get_user_context(config)
        lead_data = LeadCreate(
            name=name,
            price=price or None,
            pipeline_id=default_pipeline_id or None,
            responsible_user_id=responsible_user_id,
            session_id=session_id,
            session_field_id=session_field_id or None,
            tags=["telegram_bot"],
        )
        start = time.perf_counter()
        lead = await kommo.create_lead(lead_data)
        latency_ms = (time.perf_counter() - start) * 1000

        lf = get_client()
        lf.score_current_trace(name="crm_deal_created", value=1, data_type="NUMERIC")
        lf.score_current_trace(
            name="crm_deal_create_latency_ms", value=latency_ms, data_type="NUMERIC"
        )

        return json.dumps({"deal_id": lead.id, "name": lead.name})

    @tool
    @observe(name="crm-link-contact-to-deal")
    async def crm_link_contact_to_deal(
        deal_id: int,
        contact_id: int,
        config: RunnableConfig = None,
    ) -> str:
        """Link a contact to a deal in Kommo CRM.

        Use this after creating both contact and deal to bind them together.
        """
        await kommo.link_contact_to_lead(lead_id=deal_id, contact_id=contact_id)
        return json.dumps({"linked": True, "deal_id": deal_id, "contact_id": contact_id})

    @tool
    @observe(name="crm-add-note")
    async def crm_add_note(
        deal_id: int,
        text: str,
        config: RunnableConfig = None,
    ) -> str:
        """Add a text note to a deal in Kommo CRM.

        Use this to attach chat summaries or important information to deals.
        """
        note = await kommo.add_note(entity_type="leads", entity_id=deal_id, text=text)
        return json.dumps({"note_id": note.id, "deal_id": deal_id})

    @tool
    @observe(name="crm-create-followup-task")
    async def crm_create_followup_task(
        deal_id: int,
        text: str = "Follow up with client",
        due_hours: int = 24,
        config: RunnableConfig = None,
    ) -> str:
        """Create a follow-up task linked to a deal in Kommo CRM.

        Use this to schedule reminders for the responsible user.
        """
        complete_till = int(time.time()) + (due_hours * 3600)
        task_data = TaskCreate(
            text=text,
            entity_id=deal_id,
            entity_type="leads",
            complete_till=complete_till,
            responsible_user_id=responsible_user_id,
        )
        task = await kommo.create_task(task_data)

        lf = get_client()
        lf.score_current_trace(name="crm_task_created", value=1, data_type="NUMERIC")

        return json.dumps({"task_id": task.id, "deal_id": deal_id})

    @tool
    @observe(name="crm-finalize-deal")
    async def crm_finalize_deal(query: str, config: RunnableConfig) -> str:
        """End-to-end deal creation: extract data from chat, create contact, deal, link, note, task.

        Use this when the user asks to create a deal based on the conversation.
        Orchestrates all CRM steps in sequence with idempotency checks.
        """
        user_id, session_id = _get_user_context(config)
        if not user_id:
            return "Error: user context not available."

        start = time.perf_counter()
        lf = get_client()
        idempotency_key = f"kommo:deal:{user_id}:{session_id}"

        was_set = await idempotency_store.set(
            idempotency_key,
            "1",
            ex=24 * 3600,
            nx=True,
        )
        if not was_set:
            lf.score_current_trace(name="crm_deal_idempotent_skip", value=1, data_type="BOOLEAN")
            return "Idempotent skip: deal for this session is already processed."

        try:
            # Step 1: Extract deal data from chat history
            messages = await history_service.get_session_turns(user_id, session_id, limit=40)
            chat_text = "\n".join(
                f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages
            )
            response = await llm.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": DEAL_DRAFT_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Chat history:\n{chat_text}"},
                ],
                name="crm-finalize-draft-extraction",
            )
            draft_json = response.choices[0].message.content
            try:
                draft = DealDraft.model_validate_json(draft_json)
            except Exception:
                return f"Failed to extract deal data from chat. Raw: {draft_json[:200]}"

            # Step 2: Upsert contact
            contact = None
            if draft.phone:
                contact_data = ContactCreate(
                    first_name=draft.client_name or "",
                    phone=draft.phone,
                    email=draft.email or None,
                    responsible_user_id=responsible_user_id,
                )
                contact = await kommo.upsert_contact(phone=draft.phone, data=contact_data)
                lf.score_current_trace(
                    name="crm_contact_upserted", value=1, data_type="NUMERIC"
                )

            # Step 3: Create deal
            deal_name = f"{draft.property_type or 'Сделка'}"
            if draft.location:
                deal_name += f" — {draft.location}"
            if draft.client_name:
                deal_name += f" ({draft.client_name})"

            lead_data = LeadCreate(
                name=deal_name,
                price=draft.budget,
                pipeline_id=default_pipeline_id or None,
                responsible_user_id=responsible_user_id,
                session_id=session_id,
                session_field_id=session_field_id or None,
                tags=["telegram_bot"],
            )
            lead = await kommo.create_lead(lead_data)

            # Step 4: Link contact to deal
            if contact:
                await kommo.link_contact_to_lead(lead_id=lead.id, contact_id=contact.id)

            # Step 5: Add note with chat summary
            note_text = f"Источник: Telegram Bot\n"
            if draft.notes:
                note_text += f"Запрос: {draft.notes}\n"
            note_text += f"Session: {session_id}"
            await kommo.add_note(entity_type="leads", entity_id=lead.id, text=note_text)

            # Step 6: Create follow-up task
            complete_till = int(time.time()) + 24 * 3600
            task = TaskCreate(
                text=f"Связаться с {draft.client_name or 'клиентом'} по запросу из Telegram",
                entity_id=lead.id,
                entity_type="leads",
                complete_till=complete_till,
                responsible_user_id=responsible_user_id,
            )
            await kommo.create_task(task)

            latency_ms = (time.perf_counter() - start) * 1000
            lf.score_current_trace(name="crm_deal_created", value=1, data_type="NUMERIC")
            lf.score_current_trace(
                name="crm_deal_create_latency_ms", value=latency_ms, data_type="NUMERIC"
            )
            lf.score_current_trace(name="crm_write_success", value=1, data_type="NUMERIC")
            lf.score_current_trace(name="crm_task_created", value=1, data_type="NUMERIC")

            result_parts = [f"Сделка #{lead.id} создана: {deal_name}."]
            if contact:
                result_parts.append(f"Контакт: {contact.name} (#{contact.id}).")
            result_parts.append("Задача follow-up назначена.")

            return " ".join(result_parts)

        except Exception:
            logger.exception("CRM finalize_deal failed")
            lf.score_current_trace(name="crm_write_success", value=0, data_type="NUMERIC")
            return "Ошибка при создании сделки в CRM. Попробуйте позже."

    return [
        crm_generate_deal_draft,
        crm_upsert_contact,
        crm_create_deal,
        crm_link_contact_to_deal,
        crm_add_note,
        crm_create_followup_task,
        crm_finalize_deal,
    ]
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/agents/test_crm_tools.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add telegram_bot/agents/crm_tools.py tests/unit/agents/test_crm_tools.py
git commit -m "feat(crm): add 7 Kommo CRM supervisor tools (#312)"
```

---

## Task 6: Bot Integration

**Files:**
- Modify: `telegram_bot/bot.py:162-209` (add KommoClient init)
- Modify: `telegram_bot/bot.py:524-537` (add CRM tools to supervisor)
- Test: `tests/unit/test_bot_kommo_integration.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_bot_kommo_integration.py
"""Tests for Kommo CRM integration in PropertyBot."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestBotKommoToolsRegistration:
    def test_crm_tools_not_added_when_disabled(self):
        """KOMMO_ENABLED=false → no CRM tools in supervisor."""
        from telegram_bot.config import BotConfig

        config = BotConfig(
            telegram_token="test",
            llm_api_key="test",
            kommo_enabled=False,
        )
        assert config.kommo_enabled is False

    def test_crm_tools_require_config(self):
        """KOMMO_ENABLED=true + subdomain → ready for CRM tools."""
        from telegram_bot.config import BotConfig

        config = BotConfig(
            telegram_token="test",
            llm_api_key="test",
            kommo_enabled=True,
            kommo_subdomain="mycompany",
            kommo_client_id="abc",
            kommo_client_secret="secret",
            kommo_redirect_uri="https://example.com/cb",
            kommo_default_pipeline_id=100,
        )
        assert config.kommo_enabled is True
        assert config.kommo_subdomain == "mycompany"
        assert config.kommo_default_pipeline_id == 100
```

Also add a focused unit test for supervisor tool registration in `PropertyBot._handle_query_supervisor()`:
- when `kommo_enabled=False`, `create_crm_tools` is not called;
- when `kommo_enabled=True` and `_kommo_client` is set, `create_crm_tools` is called and 7 tools are appended.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_bot_kommo_integration.py -v`
Expected: FAIL — supervisor registration assertions for CRM tools fail before `bot.py` integration changes.

**Step 3: Modify bot.py**

In `telegram_bot/bot.py`, add to `__init__` (after `self._cache_initialized = False`, around line 209):

```python
        # Kommo CRM client (initialized in start() if enabled)
        self._kommo_client = None
```

In `start()` method, add initialization block (after history service init):

```python
        # Initialize Kommo CRM client if enabled
        if self.config.kommo_enabled and self.config.kommo_subdomain:
            try:
                from .services.kommo_client import KommoClient
                from .services.kommo_tokens import KommoTokenStore

                if self._cache.redis is None:
                    raise RuntimeError("Cache redis client is not initialized")

                token_store = KommoTokenStore(
                    redis=self._cache.redis,  # reuse existing Redis connection
                    client_id=self.config.kommo_client_id,
                    client_secret=self.config.kommo_client_secret.get_secret_value(),
                    subdomain=self.config.kommo_subdomain,
                    redirect_uri=self.config.kommo_redirect_uri,
                )
                # Initialize tokens (exchange auth_code on first run, load from Redis after)
                auth_code = self.config.kommo_auth_code or None
                await token_store.initialize(authorization_code=auth_code)

                self._kommo_client = KommoClient(
                    subdomain=self.config.kommo_subdomain,
                    token_store=token_store,
                )
                logger.info("Kommo CRM client initialized (subdomain=%s)", self.config.kommo_subdomain)
            except Exception:
                logger.exception("Failed to initialize Kommo CRM client")
                self._kommo_client = None
```

In `stop()` method, add Kommo client cleanup:

```python
        if self._kommo_client is not None:
            await self._kommo_client.close()
            self._kommo_client = None
```

In `_handle_query_supervisor()`, after `tools.append(create_history_search_tool(...))` (around line 537):

```python
        # CRM tools (conditional on KOMMO_ENABLED + initialized client)
        if self.config.kommo_enabled and self._kommo_client is not None:
            from .agents.crm_tools import create_crm_tools

            tools.extend(
                create_crm_tools(
                    kommo=self._kommo_client,
                    llm=self._llm,
                    history_service=self._history_service,
                    default_pipeline_id=self.config.kommo_default_pipeline_id,
                    responsible_user_id=self.config.kommo_responsible_user_id,
                    session_field_id=self.config.kommo_session_field_id,
                    idempotency_store=self._cache.redis,
                )
            )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_bot_kommo_integration.py -v`
Expected: All PASS

**Step 5: Run full unit test suite to check no regressions**

Run: `uv run pytest tests/unit/ -n auto --dist=worksteal --timeout=60`
Expected: All existing tests PASS

**Step 6: Commit**

```bash
git add telegram_bot/bot.py tests/unit/test_bot_kommo_integration.py
git commit -m "feat(crm): integrate Kommo CRM tools into supervisor (#312)"
```

---

## Task 7: Lint, Types, Full Test Pass

**Files:** All modified files

**Step 1: Run linter**

Run: `make check`
Expected: PASS. If failures, fix and re-run.

**Step 2: Run full unit tests in parallel**

Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`
Expected: All PASS

**Step 3: Final commit (if any fixes)**

```bash
git add -u
git commit -m "fix(crm): lint and type fixes for Kommo integration (#312)"
```

---

## Summary

| Task | Files | Tests | Commit |
|------|-------|-------|--------|
| 1. Models | `services/kommo_models.py` | `test_kommo_models.py` | `feat(crm): add Pydantic models` |
| 2. Config | `config.py` | `test_bot_config_kommo.py` | `feat(crm): add OAuth2 config fields` |
| 3. Token Store | `services/kommo_tokens.py` | `test_kommo_tokens.py` | `feat(crm): add token store` |
| 4. KommoClient | `services/kommo_client.py` | `test_kommo_client.py` | `feat(crm): add KommoClient` |
| 5. CRM Tools | `agents/crm_tools.py` | `test_crm_tools.py` | `feat(crm): add 7 supervisor tools` |
| 6. Bot Integration | `bot.py` | `test_bot_kommo_integration.py` | `feat(crm): integrate into supervisor` |
| 7. Quality Gate | — | Full suite | `fix(crm): lint/type fixes` |

**Total:** file/LOC totals must be recalculated from actual diff at execution time (do not hardcode).

---

## Research Validation (2026-02-18)

> Validated via Context7 MCP (httpx, tenacity, pydantic v2, redis-py) and Exa MCP (OAuth2 patterns, Kommo rate limiting, Redis token storage best practices).

### Libraries Checked

| Library | Current Version | Plan Version/Usage |
|---------|----------------|-------------------|
| httpx | Latest (docs: `/encode/httpx`) | `httpx.AsyncClient` + `Timeout` + `Limits` |
| tenacity | Latest (docs: readthedocs) | `wait_exponential_jitter`, `retry_if_exception` |
| pydantic | v2.12+ | `BaseModel`, `model_dump_json`, `AliasChoices` |
| redis-py | v6.4.0 | `hset(mapping=...)`, `set(nx=True, ex=...)` |

---

### Confirmed Correct

1. **httpx `AsyncClient` lifecycle** — long-lived client in `__init__`, `aclose()` in `close()`. Matches docs best practice (don't create per-request).
2. **`httpx.Timeout(30.0, connect=10.0)`** — valid 4-axis timeout API, positional arg sets the default. Confirmed.
3. **`httpx.Limits(max_keepalive_connections=5, max_connections=10)`** — valid API, confirmed.
4. **tenacity `wait_exponential_jitter(initial=1, max=8, jitter=2)`** — dedicated class, additive jitter on top of exponential. API is current and stable.
5. **tenacity `|` operator** — `retry_if_exception_type(...) | retry_if_exception(...)` is stable API.
6. **tenacity `before_sleep_log`** — correct current API, no deprecation.
7. **pydantic `BaseModel`, `Field`, `AliasChoices`, `SecretStr`** — all v2 stable API; `model_dump_json()` / `model_validate_json()` are correct v2 methods (v1 `.json()` / `parse_obj()` deprecated but not used here).
8. **redis-py `hset(key, mapping={...})`** — correct; `hmset()` is deprecated since v4.0. Plan uses correct API.
9. **redis-py `set(key, value, nx=True, ex=...)`** — confirmed atomic NX+EX pattern for idempotency. Returns `True` if set, `None` if already existed.
10. **Notes endpoint** — `POST /{entity_type}/notes` with `entity_id` in payload (not `/{entity_type}/{id}/notes`). Already corrected in review note at top of plan. Confirmed correct.
11. **`custom_fields_values` with `field_code`** — using `"PHONE"` / `"EMAIL"` field codes is correct Kommo API pattern.

---

### Issues Found — Require Fixes Before Implementing

#### CRITICAL: Retry-After placeholder is a no-op ellipsis

In Task 4 `kommo_client.py`, the `_request` method has:

```python
if response.status_code == 429:
    # Optional: honor Retry-After for rate limits before raising.
    ...
response.raise_for_status()
```

The `...` (ellipsis literal) does nothing. Kommo docs confirm 7 req/s limit with 429 on violation. Since Kommo does NOT reliably send `Retry-After` headers, the implementation must honor it defensively when present and fall back to backoff otherwise. **Replace `...` with:**

```python
if response.status_code == 429:
    retry_after_raw = response.headers.get("Retry-After")
    if retry_after_raw:
        try:
            import asyncio
            await asyncio.sleep(float(retry_after_raw))
        except (ValueError, TypeError):
            pass  # non-numeric Retry-After — let tenacity backoff handle it
    response.raise_for_status()
```

> Note: `_request` is a `@_kommo_retry`-decorated coroutine; `raise_for_status()` on 429 will trigger tenacity retry with exponential jitter. The sleep above adds a Retry-After-aware delay before tenacity fires.

#### IMPORTANT: Missing `asyncio.Lock` in `KommoTokenStore.get_valid_token()`

If two concurrent requests check token expiry simultaneously, both will enter `_refresh_tokens()` — a stampede/thundering herd. The Exa research confirms this is the #1 pitfall. **Add a lock:**

```python
import asyncio

class KommoTokenStore:
    def __init__(self, ...):
        ...
        self._refresh_lock = asyncio.Lock()

    async def get_valid_token(self) -> str:
        data = await self._load_tokens()
        if not data:
            raise RuntimeError("No Kommo tokens found in Redis. Call initialize() first.")
        access_token = data.get("access_token", "")
        refresh_token = data.get("refresh_token", "")
        expires_at = int(data.get("expires_at", 0))

        if time.time() + REFRESH_BUFFER_SEC >= expires_at:
            async with self._refresh_lock:
                # Double-check after acquiring lock
                data = await self._load_tokens()
                expires_at = int(data.get("expires_at", 0))
                if time.time() + REFRESH_BUFFER_SEC >= expires_at:
                    logger.info("Kommo token near expiry, refreshing")
                    return await self._refresh_tokens(data["refresh_token"])
                return data["access_token"]

        return access_token
```

#### MODERATE: `create_crm_tools` — `idempotency_store` has no default

```python
def create_crm_tools(*, ..., idempotency_store: Any) -> list[Any]:
```

If `idempotency_store=None` is passed (e.g., when `self._cache.redis` is `None`), the `crm_finalize_deal` tool will crash with `AttributeError` on `await idempotency_store.set(...)`. **Add guard:**

```python
def create_crm_tools(*, ..., idempotency_store: Any | None = None) -> list[Any]:
    ...
    async def crm_finalize_deal(query: str, config: RunnableConfig) -> str:
        ...
        if idempotency_store is not None:
            was_set = await idempotency_store.set(idempotency_key, "1", ex=24 * 3600, nx=True)
            if not was_set:
                lf.score_current_trace(name="crm_deal_idempotent_skip", value=1, data_type="BOOLEAN")
                return "Idempotent skip: deal for this session is already processed."
```

#### MINOR: `pool` timeout not set in `httpx.Limits`

Plan uses `httpx.Timeout(30.0, connect=10.0)` but does not set `pool` timeout. Under high concurrency, requests waiting for a pool slot will block indefinitely until the `connect` timeout fires. **Add:**

```python
timeout=httpx.Timeout(30.0, connect=10.0, pool=10.0),
```

---

### Suggestions (Non-Blocking)

1. **`keepalive_expiry`** — Default is 5s (very short). For a low-traffic CRM integration, consider `keepalive_expiry=30` in `httpx.Limits` to reduce TCP reconnect overhead.

2. **Kommo IP blocking on 403 after repeated 429s** — Kommo docs state repeated violations cause IP-level 403 blocks. Consider differentiating 403 responses: only retry 403 if there was no prior 429 in the same session; otherwise surface as a hard error.

3. **`stop_after_attempt(3)` may be low for 429** — With Kommo's 7 req/s limit in production, transient 429s during bursts may need up to 5 retries with backoff. Consider `stop_after_attempt(5)` for `_kommo_retry`.

4. **Token encryption at rest** — Exa research recommends `cryptography.fernet.Fernet` for access/refresh tokens stored in Redis. Not required for #312 (internal Redis, threat model is low), but worth a follow-up issue.

5. **`asyncio.Lock` vs Redis SET NX for concurrent workers** — Plan uses `asyncio.Lock` (single-process app — correct). If the bot is ever horizontally scaled (multiple pods), switch to Redis `SET lock_key NX EX 30` pattern. The `KommoTokenStore` interface allows this without API change.

---

### Verdict

**Plan is architecturally sound. Three mandatory fixes required before implementation begins:**

| Priority | Fix | Task affected |
|----------|-----|--------------|
| CRITICAL | Replace `...` no-op with actual Retry-After sleep in `_request` | Task 4 |
| IMPORTANT | Add `asyncio.Lock` double-check in `get_valid_token()` | Task 3 |
| MODERATE | Guard `idempotency_store is None` in `crm_finalize_deal` | Task 5 |

The TDD approach (test first, then implement) will naturally surface the lock and idempotency-store-None issues at test-writing time if tests cover concurrent and None-store scenarios.
