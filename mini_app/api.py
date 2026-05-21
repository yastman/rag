"""Mini App FastAPI backend."""

from __future__ import annotations

import json
import os
import uuid as _uuid_lib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from mini_app.auth import validate_init_data
from mini_app.expert_start import StartExpertRequest, StartExpertResponse
from mini_app.phone import PhoneRequest, submit_phone
from telegram_bot.observability import get_client, observe, propagate_attributes
from telegram_bot.services.content_loader import load_mini_app_config


_DEEPLINK_TTL = 300  # seconds


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open the Redis client on startup and close it on shutdown.

    The Mini App backend uses Redis for short-lived deeplink payloads
    (``miniapp:q:<uuid>``) and pub/sub notifications to the bot. Owning
    the connection lifecycle here (instead of a module-level lazy
    global) ensures graceful close on process shutdown and matches the
    FastAPI-native pattern (#1645).
    """
    import redis.asyncio as aioredis

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    client = aioredis.from_url(redis_url, decode_responses=True)
    app.state.redis = client
    try:
        yield
    finally:
        # ``aioredis`` clients expose ``aclose`` in modern versions; fall back to
        # ``close`` for older releases. Either way, the connection pool drains.
        close = getattr(client, "aclose", None) or getattr(client, "close", None)
        if close is not None:
            result = close()
            if hasattr(result, "__await__"):
                await result


async def get_redis(request: Request) -> Any:
    """FastAPI dependency that returns the app-scoped Redis client.

    Handlers receive the connection via ``Depends(get_redis)`` so the
    lifecycle stays owned by ``lifespan`` instead of leaking into module
    globals.
    """
    return request.app.state.redis


def _get_bot_token() -> str:
    """Return the Telegram bot token from environment.

    Reads ``TELEGRAM_BOT_TOKEN`` (the canonical env var shared with
    telegram_bot) with ``BOT_TOKEN`` as a legacy alias.  Raises
    ``RuntimeError`` only if neither is set — callers translate this to
    a 500 so operators see a clear misconfiguration message.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not configured")
    return token


async def get_validated_init_data(
    x_init_data: str | None = Header(
        default=None,
        alias="X-Init-Data",
        description="Telegram WebApp signed initData string",
    ),
) -> dict:
    """FastAPI dependency: validate Telegram initData and return parsed user dict.

    Returns the parsed initData dict (including ``user`` sub-dict) on
    success.  Raises ``HTTP 401`` for missing header, missing token config,
    invalid hash, or expired ``auth_date``.

    Debug / test mode: when ``BOT_TOKEN`` equals the known test sentinel
    ``"TEST"`` (set in CI) validation is bypassed and a synthetic user
    dict is returned so the rest of the stack is exercised without a
    real bot token.
    """
    if x_init_data is None:
        raise HTTPException(status_code=401, detail="X-Init-Data header is required")

    try:
        bot_token = _get_bot_token()
    except RuntimeError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    # Allow bypass in debug/test mode with the test sentinel token.
    if bot_token == "TEST":
        return {"user": {"id": 0, "first_name": "TestUser"}, "auth_date": "0"}

    try:
        return validate_init_data(x_init_data, bot_token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# CORS — restrict to configured origin (not wildcard)
#
# Operators MUST set MINI_APP_ALLOWED_ORIGIN in production.
# Dev default falls back to https://t.me so the app still boots locally
# without any env configuration. An empty string is treated as missing.
# ---------------------------------------------------------------------------

_CORS_ORIGIN = os.environ.get("MINI_APP_ALLOWED_ORIGIN", "").strip() or "https://t.me"

app = FastAPI(title="FortNoks Mini App API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[_CORS_ORIGIN],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Init-Data"],
)


@app.get("/api/config")
async def get_config() -> dict:
    """Return Mini App UI config: questions + experts."""
    return load_mini_app_config()


def _update_current_span(**kwargs: Any) -> None:
    """Curated update_current_span; no-op when Langfuse client absent."""
    lf = get_client()
    if lf is not None:
        lf.update_current_span(**kwargs)


@app.post("/api/start-expert")
@observe(name="miniapp-start-expert", capture_input=False, capture_output=False)
async def start_expert(
    request: StartExpertRequest,
    redis: Any = Depends(get_redis),
    init_data: dict = Depends(get_validated_init_data),
) -> StartExpertResponse:
    """Store deep-link payload in Redis and return start_link for openTelegramLink.

    ``init_data`` is the validated Telegram initData dict injected by
    ``get_validated_init_data``.  ``user_id`` is derived from
    ``init_data["user"]["id"]`` — the JSON body value is accepted for
    optional fields (expert_id, message, query_id) but the user identity
    is **always** taken from the server-verified initData (#1595).

    Wrapped in ``@observe`` (#1658) so the Mini App entry point lands as a
    named Langfuse span. ``propagate_attributes(session_id="miniapp-{user_id}")``
    groups the Mini App and the subsequent Telegram ``/start q_<expert>``
    trace into the same Langfuse Session, reconstructing the funnel
    ``Mini App -> /start q_<expert> -> Telegram dialog -> CRM``.

    PII safety: ``capture_input/output=False`` and the curated
    ``update_current_span(input=...)`` records only ``expert_id`` plus
    payload-shape booleans — never the message body or raw deep-link UUID.
    """
    # Derive user_id from validated initData — never trust the request body.
    user_id: int = init_data["user"]["id"]

    with propagate_attributes(
        session_id=f"miniapp-{user_id}",
        user_id=str(user_id),
        tags=["miniapp", "start-expert", request.expert_id],
        metadata={"surface": "miniapp"},
    ):
        _update_current_span(
            input={
                "expert_id": request.expert_id,
                "has_message": request.message is not None,
                "has_query_id": request.query_id is not None,
            }
        )

        config = load_mini_app_config()
        experts = config.get("experts", [])
        expert = next((e for e in experts if e["id"] == request.expert_id), None)
        if expert is None:
            _update_current_span(level="ERROR", status_message="expert_not_found")
            raise HTTPException(status_code=404, detail="Expert not found")

        uid = str(_uuid_lib.uuid4())
        payload = json.dumps(
            {
                "expert_id": request.expert_id,
                "message": request.message,
                "user_id": user_id,
                "query_id": request.query_id,
            }
        )
        await redis.set(f"miniapp:q:{uid}", payload, ex=_DEEPLINK_TTL)

        bot_username = os.environ.get("BOT_USERNAME", "")
        if not bot_username:
            _update_current_span(level="ERROR", status_message="bot_username_not_configured")
            raise HTTPException(status_code=500, detail="BOT_USERNAME not configured")
        start_link = f"https://t.me/{bot_username}?start=q_{uid}"

        # Notify bot via Redis pub/sub — bot calls answerWebAppQuery + creates
        # topic + RAG.
        await redis.publish(
            "miniapp:start",
            json.dumps(
                {
                    "uuid": uid,
                    "user_id": user_id,
                    "query_id": request.query_id,
                }
            ),
        )

        # Curated success metadata — no raw UUID, no full URL.
        _update_current_span(
            output={
                "expert_id": request.expert_id,
                "expert_name": expert["name"],
                "deeplink_published": True,
            }
        )

        return StartExpertResponse(
            start_link=start_link,
            expert_name=expert["name"],
        )


@app.post("/api/log")
async def remote_log(request: dict) -> dict:
    """Receive frontend remote logs (Eruda / remoteLog helper)."""
    level = request.get("level", "info")
    message = request.get("message", "")
    data = request.get("data")
    print(f"[REMOTE:{level}] {message} {data or ''}", flush=True)
    return {"status": "ok"}


@app.post("/api/phone")
@observe(name="miniapp-submit-phone", capture_input=False, capture_output=False)
async def phone(
    request: PhoneRequest,
    init_data: dict = Depends(get_validated_init_data),
) -> Any:
    """Collect phone and create CRM lead.

    ``user_id`` is derived from the validated Telegram initData so callers
    cannot spoof another user's identity (#1595).

    Wrapped in ``@observe`` (#1658) with the same ``miniapp-{user_id}`` session
    grouping as ``start_expert`` so the funnel reconstructs in Langfuse
    Sessions. PII (phone, name) never reaches the span: ``capture_input/output``
    are off, and the inner ``submit_phone`` curates its own output. On CRM
    failure (``success=False``), return ``502 Bad Gateway`` so clients can
    distinguish a captured lead from a dropped one (#1596).
    """
    from fastapi.responses import JSONResponse

    # Override user_id with the server-verified value from initData (#1595).
    user_id: int = init_data["user"]["id"]
    # Re-create the request with the verified user_id to keep the rest of
    # the stack unchanged (submit_phone, propagate_attributes).
    verified_request = request.model_copy(update={"user_id": user_id})

    with propagate_attributes(
        session_id=f"miniapp-{user_id}",
        user_id=str(user_id),
        tags=["miniapp", "submit-phone", request.source],
        metadata={"surface": "miniapp"},
    ):
        _update_current_span(input={"source": request.source, "has_name": request.name is not None})
        result = await submit_phone(verified_request)
        if not result.get("success"):
            _update_current_span(level="ERROR", status_message="crm_submission_failed")
            return JSONResponse(status_code=502, content=result)
        return result


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
