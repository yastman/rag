"""TDD tests for Telegram initData enforcement on Mini App mutation endpoints.

Closes #1595 — before this PR, /api/start-expert and /api/phone accepted
unauthenticated requests from any origin, trusting user_id from the JSON
body. This test file drives the required fix:

  1. Missing initData  → 401
  2. Invalid hash      → 401
  3. Valid initData    → request processed, user_id derived from token
  4. CORS must not be wildcard
"""

from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import quote
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi")

from httpx import ASGITransport, AsyncClient

from mini_app.api import app
import mini_app.api as api_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_BOT_TOKEN = "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"


def _make_init_data(bot_token: str, user_id: int = 42, **overrides: str) -> str:
    """Build a valid Telegram initData string with correct HMAC-SHA256 hash."""
    params: dict[str, str] = {
        "auth_date": str(int(time.time())),
        "user": f'{{"id":{user_id},"first_name":"Test"}}',
        **overrides,
    }
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    hash_val = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    params["hash"] = hash_val
    return "&".join(f"{k}={quote(v, safe='')}" for k, v in params.items())


def _make_invalid_init_data(bot_token: str, user_id: int = 42) -> str:
    """Build initData with a valid structure but a wrong hash."""
    valid = _make_init_data(bot_token, user_id=user_id)
    parts = dict(pair.split("=", 1) for pair in valid.split("&"))
    parts["hash"] = "deadbeef" * 8  # 64 hex chars but wrong value
    return "&".join(f"{k}={v}" for k, v in parts.items())


# ---------------------------------------------------------------------------
# /api/start-expert — auth enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_expert_without_init_data_returns_401():
    """POST /api/start-expert without X-Init-Data header must return 401."""
    # Provide a Redis override so the lifespan dependency doesn't error out
    # independently — the 401 should be the only thing that matters here.
    async def _noop_redis(_request=None):
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
        f"Expected 401 when X-Init-Data header is missing, got {resp.status_code}"
    )


@pytest.mark.asyncio
async def test_start_expert_with_invalid_init_data_returns_401():
    """POST /api/start-expert with a wrong HMAC hash must return 401."""
    invalid_init_data = _make_invalid_init_data(TEST_BOT_TOKEN)

    async def _noop_redis(_request=None):
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


@pytest.mark.asyncio
async def test_start_expert_with_valid_init_data_succeeds():
    """POST /api/start-expert with valid signed initData must return 200.

    user_id should be derived from initData, not from request body.
    """
    valid_init_data = _make_init_data(TEST_BOT_TOKEN, user_id=42)

    mock_redis = MagicMock()
    mock_redis.set = AsyncMock()
    mock_redis.publish = AsyncMock()

    async def _override_redis(_request=None):
        return mock_redis

    app.dependency_overrides[api_mod.get_redis] = _override_redis
    try:
        with patch.dict(
            "os.environ",
            {"TELEGRAM_BOT_TOKEN": TEST_BOT_TOKEN, "BOT_USERNAME": "testbot"},
            clear=False,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
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


@pytest.mark.asyncio
async def test_start_expert_user_id_derived_from_init_data():
    """user_id must come from validated initData, not from the JSON body."""
    # initData says user_id=99; if body user_id were trusted we'd see 99 in the
    # published Redis payload. We verify the validated user is used.
    valid_init_data = _make_init_data(TEST_BOT_TOKEN, user_id=99)

    mock_redis = MagicMock()
    mock_redis.set = AsyncMock()
    published_payloads: list[str] = []

    async def _fake_publish(channel: str, payload: str) -> None:
        published_payloads.append(payload)

    mock_redis.publish = _fake_publish

    async def _override_redis(_request=None):
        return mock_redis

    app.dependency_overrides[api_mod.get_redis] = _override_redis
    try:
        with patch.dict(
            "os.environ",
            {"TELEGRAM_BOT_TOKEN": TEST_BOT_TOKEN, "BOT_USERNAME": "testbot"},
            clear=False,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                # Body does NOT include user_id — it must be extracted from initData
                resp = await client.post(
                    "/api/start-expert",
                    json={"expert_id": "consultant"},
                    headers={"X-Init-Data": valid_init_data},
                )
    finally:
        app.dependency_overrides.pop(api_mod.get_redis, None)

    assert resp.status_code == 200, resp.text
    import json

    assert published_payloads, "Redis publish must have been called"
    published = json.loads(published_payloads[0])
    assert published["user_id"] == 99, (
        f"user_id in Redis payload must be 99 (from initData), got {published['user_id']}"
    )


# ---------------------------------------------------------------------------
# /api/phone — auth enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_phone_without_init_data_returns_401():
    """POST /api/phone without X-Init-Data header must return 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/phone",
            json={"phone": "+359888123456", "source": "test", "user_id": 42},
        )
    assert resp.status_code == 401, (
        f"Expected 401 when X-Init-Data header is missing, got {resp.status_code}"
    )


@pytest.mark.asyncio
async def test_phone_with_invalid_init_data_returns_401():
    """POST /api/phone with wrong hash must return 401."""
    invalid_init_data = _make_invalid_init_data(TEST_BOT_TOKEN)
    with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": TEST_BOT_TOKEN}, clear=False):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/phone",
                # user_id omitted — must come from initData after auth
                json={"phone": "+359888123456", "source": "test", "user_id": 42},
                headers={"X-Init-Data": invalid_init_data},
            )
    assert resp.status_code == 401, (
        f"Expected 401 for invalid hash, got {resp.status_code}: {resp.text}"
    )


@pytest.mark.asyncio
async def test_phone_with_valid_init_data_succeeds():
    """POST /api/phone with valid signed initData must return 200."""
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
                json={"phone": "+359888123456", "source": "test", "user_id": 42},
                headers={"X-Init-Data": valid_init_data},
            )

    assert resp.status_code == 200, (
        f"Expected 200 for valid initData on /api/phone, got {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# CORS restriction
# ---------------------------------------------------------------------------


def test_cors_restricted_to_configured_origin():
    """CORS allow_origins must NOT be the wildcard ['*'].

    The API should use a configurable origin via MINI_APP_ALLOWED_ORIGIN
    env var rather than allowing any origin. Check the middleware config
    directly on the app object.
    """
    from fastapi.middleware.cors import CORSMiddleware

    cors_middleware = None
    for mw in app.user_middleware:
        # FastAPI stores middleware as Middleware(cls, **kwargs) objects
        if hasattr(mw, "cls") and mw.cls is CORSMiddleware:
            cors_middleware = mw
            break
        # Some versions expose as (cls, args, kwargs) tuples
        if isinstance(mw, tuple) and len(mw) >= 1 and mw[0] is CORSMiddleware:
            cors_middleware = mw
            break

    assert cors_middleware is not None, "CORSMiddleware must be added to the app"

    # Extract kwargs — either .kwargs dict or last element of tuple
    if hasattr(cors_middleware, "kwargs"):
        cors_kwargs = cors_middleware.kwargs
    else:
        cors_kwargs = cors_middleware[-1] if isinstance(cors_middleware, tuple) else {}

    allow_origins = cors_kwargs.get("allow_origins", [])
    assert allow_origins != ["*"], (
        "CORS allow_origins must not be ['*']. "
        "Use MINI_APP_ALLOWED_ORIGIN env var or a safe default like 'https://t.me'. "
        f"Got: {allow_origins}"
    )
