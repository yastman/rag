"""TDD tests for Telegram initData enforcement on Mini App mutation endpoints.

Closes #1595 — before this PR, /api/start-expert and /api/phone accepted
unauthenticated requests from any origin and trusted ``user_id`` from the
JSON body. This test file drives the SDK-audited fix:

  1. Missing initData header  → 401
  2. Invalid HMAC signature   → 401
  3. Valid initData           → 200, user_id derived from the signed token
  4. /api/phone enforcement   → mirror of (1)/(3) for the phone endpoint
  5. CORS allow_origins must NOT be the wildcard ``["*"]``

The HMAC fixture builder uses the canonical Telegram WebApp scheme so the
aiogram SDK validator (``aiogram.utils.web_app.safe_parse_webapp_init_data``)
accepts it byte-for-byte.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import quote

import pytest


pytest.importorskip("fastapi")

from httpx import ASGITransport, AsyncClient

import mini_app.api as api_mod
from mini_app.api import app


TEST_BOT_TOKEN = "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"


def _make_init_data(bot_token: str, user_id: int = 42, **overrides: str) -> str:
    """Build a Telegram-compliant signed initData query string."""
    user_payload = json.dumps(
        {"id": user_id, "first_name": "Test"},
        separators=(",", ":"),
    )
    params: dict[str, str] = {
        "auth_date": str(int(time.time())),
        "user": user_payload,
        **overrides,
    }
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    params["hash"] = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    # Quote in URL-safe form so parse_qsl on the receiving end recovers the
    # exact same key/value bytes that fed the HMAC.
    return "&".join(f"{k}={quote(v, safe='')}" for k, v in params.items())


def _make_invalid_init_data(bot_token: str, user_id: int = 42) -> str:
    """Build initData with valid structure but wrong hash."""
    valid = _make_init_data(bot_token, user_id=user_id)
    parts = dict(pair.split("=", 1) for pair in valid.split("&"))
    parts["hash"] = "deadbeef" * 8
    return "&".join(f"{k}={v}" for k, v in parts.items())


# ---------------------------------------------------------------------------
# /api/start-expert — auth enforcement
# ---------------------------------------------------------------------------


async def test_start_expert_without_init_data_returns_401() -> None:
    """POST /api/start-expert without X-Init-Data header must return 401."""

    async def _noop_redis():
        return MagicMock()

    app.dependency_overrides[api_mod.get_redis] = _noop_redis
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/start-expert",
                json={"expert_id": "consultant"},
            )
    finally:
        app.dependency_overrides.pop(api_mod.get_redis, None)

    assert resp.status_code == 401, (
        f"Expected 401 when X-Init-Data is missing, got {resp.status_code}: {resp.text}"
    )


async def test_start_expert_with_invalid_hash_returns_401() -> None:
    """POST /api/start-expert with a tampered HMAC must return 401."""
    invalid_init_data = _make_invalid_init_data(TEST_BOT_TOKEN)

    async def _noop_redis():
        return MagicMock()

    app.dependency_overrides[api_mod.get_redis] = _noop_redis
    try:
        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": TEST_BOT_TOKEN}, clear=False):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/start-expert",
                    json={"expert_id": "consultant"},
                    headers={"X-Init-Data": invalid_init_data},
                )
    finally:
        app.dependency_overrides.pop(api_mod.get_redis, None)

    assert resp.status_code == 401, (
        f"Expected 401 for invalid hash, got {resp.status_code}: {resp.text}"
    )


async def test_start_expert_with_valid_init_data_succeeds_and_derives_user_id() -> None:
    """Valid signed initData → 200 and user_id sourced from initData, not body."""
    valid_init_data = _make_init_data(TEST_BOT_TOKEN, user_id=99)

    mock_redis = MagicMock()
    mock_redis.set = AsyncMock()
    published_payloads: list[str] = []

    async def _capture_publish(_channel: str, payload: str) -> None:
        published_payloads.append(payload)

    mock_redis.publish = _capture_publish

    async def _override_redis():
        return mock_redis

    app.dependency_overrides[api_mod.get_redis] = _override_redis

    experts_cfg = {"experts": [{"id": "consultant", "name": "Консультант", "emoji": "👷"}]}
    try:
        with (
            patch("mini_app.api.load_mini_app_config", return_value=experts_cfg),
            patch.dict(
                "os.environ",
                {"TELEGRAM_BOT_TOKEN": TEST_BOT_TOKEN, "BOT_USERNAME": "testbot"},
                clear=False,
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                # Body intentionally omits user_id; the SDK must derive it.
                resp = await client.post(
                    "/api/start-expert",
                    json={"expert_id": "consultant"},
                    headers={"X-Init-Data": valid_init_data},
                )
    finally:
        app.dependency_overrides.pop(api_mod.get_redis, None)

    assert resp.status_code == 200, (
        f"Expected 200 for valid initData, got {resp.status_code}: {resp.text}"
    )
    assert published_payloads, "Redis publish must have been called"
    payload = json.loads(published_payloads[0])
    assert payload["user_id"] == 99, (
        f"user_id in published Redis payload must be 99 (from initData), got {payload['user_id']}"
    )


# ---------------------------------------------------------------------------
# /api/phone — auth enforcement
# ---------------------------------------------------------------------------


async def test_phone_without_init_data_returns_401() -> None:
    """POST /api/phone without X-Init-Data header must return 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/phone",
            json={"phone": "+359888123456", "source": "test", "user_id": 42},
        )
    assert resp.status_code == 401, (
        f"Expected 401 when X-Init-Data is missing, got {resp.status_code}: {resp.text}"
    )


async def test_phone_with_valid_init_data_succeeds() -> None:
    """POST /api/phone with valid signed initData succeeds and overrides user_id."""
    valid_init_data = _make_init_data(TEST_BOT_TOKEN, user_id=42)

    mock_kommo = MagicMock()
    mock_kommo.upsert_contact = AsyncMock(return_value={"id": 1})
    mock_kommo.create_lead = AsyncMock(return_value={"id": 2})

    with (
        patch("mini_app.phone.get_kommo_client", return_value=mock_kommo),
        patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": TEST_BOT_TOKEN}, clear=False),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/phone",
                # Caller-supplied user_id 12345 must be IGNORED in favour of the
                # initData-derived value (42). We do not assert on the request
                # body's user_id; we assert on what reached the CRM.
                json={
                    "phone": "+359888123456",
                    "source": "test",
                    "user_id": 12345,
                },
                headers={"X-Init-Data": valid_init_data},
            )

    assert resp.status_code == 200, (
        f"Expected 200 for valid initData on /api/phone, got {resp.status_code}: {resp.text}"
    )
    # The CRM upsert call's default name is f"Mini App User {user_id}"; verify
    # the SDK-validated id was used rather than the spoofed body value.
    upsert_kwargs = mock_kommo.upsert_contact.await_args.kwargs
    assert upsert_kwargs["name"] == "Mini App User 42", (
        f"submit_phone must use SDK-validated user_id (42) not body value (12345); "
        f"got name={upsert_kwargs['name']!r}"
    )


# ---------------------------------------------------------------------------
# CORS hardening
# ---------------------------------------------------------------------------


def test_cors_not_wildcard_on_running_app() -> None:
    """Live FastAPI app must not register CORSMiddleware with allow_origins=['*']."""
    from fastapi.middleware.cors import CORSMiddleware

    cors_mw = None
    for mw in app.user_middleware:
        if hasattr(mw, "cls") and mw.cls is CORSMiddleware:
            cors_mw = mw
            break

    assert cors_mw is not None, "CORSMiddleware must be registered"
    cors_kwargs = getattr(cors_mw, "kwargs", {}) or {}
    allow_origins = cors_kwargs.get("allow_origins", [])
    assert allow_origins != ["*"], (
        "CORS allow_origins must not be ['*']. Use MINI_APP_ALLOWED_ORIGIN env var "
        f"(default 'https://t.me'). Got: {allow_origins!r}"
    )
