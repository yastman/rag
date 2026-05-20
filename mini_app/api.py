"""Mini App FastAPI backend."""

from __future__ import annotations

import json
import os
import uuid as _uuid_lib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from mini_app.expert_start import StartExpertRequest, StartExpertResponse
from mini_app.phone import PhoneRequest, submit_phone
from telegram_bot.observability import get_client, observe, propagate_attributes
from telegram_bot.services.content_loader import load_mini_app_config


_DEEPLINK_TTL = 300  ***REMOVED*** seconds


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open the Redis client on startup and close it on shutdown.

    The Mini App backend uses Redis for short-lived deeplink payloads
    (``miniapp:q:<uuid>``) and pub/sub notifications to the bot. Owning
    the connection lifecycle here (instead of a module-level lazy
    global) ensures graceful close on process shutdown and matches the
    FastAPI-native pattern (***REMOVED***1645).
    """
    import redis.asyncio as aioredis

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    client = aioredis.from_url(redis_url, decode_responses=True)
    app.state.redis = client
    try:
        yield
    finally:
        ***REMOVED*** ``aioredis`` clients expose ``aclose`` in modern versions; fall back to
        ***REMOVED*** ``close`` for older releases. Either way, the connection pool drains.
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


app = FastAPI(title="FortNoks Mini App API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
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
) -> StartExpertResponse:
    """Store deep-link payload in Redis and return start_link for openTelegramLink.

    Wrapped in ``@observe`` (***REMOVED***1658) so the Mini App entry point lands as a
    named Langfuse span. ``propagate_attributes(session_id="miniapp-{user_id}")``
    groups the Mini App and the subsequent Telegram ``/start q_<expert>``
    trace into the same Langfuse Session, reconstructing the funnel
    ``Mini App -> /start q_<expert> -> Telegram dialog -> CRM``.

    PII safety: ``capture_input/output=False`` and the curated
    ``update_current_span(input=...)`` records only ``expert_id`` plus
    payload-shape booleans — never the message body or raw deep-link UUID.
    """
    from fastapi import HTTPException

    with propagate_attributes(
        session_id=f"miniapp-{request.user_id}",
        user_id=str(request.user_id),
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
                "user_id": request.user_id,
                "query_id": request.query_id,
            }
        )
        await redis.set(f"miniapp:q:{uid}", payload, ex=_DEEPLINK_TTL)

        bot_username = os.environ.get("BOT_USERNAME", "")
        if not bot_username:
            _update_current_span(level="ERROR", status_message="bot_username_not_configured")
            raise HTTPException(status_code=500, detail="BOT_USERNAME not configured")
        start_link = f"https://t.me/{bot_username}?start=q_{uid}"

        ***REMOVED*** Notify bot via Redis pub/sub — bot calls answerWebAppQuery + creates
        ***REMOVED*** topic + RAG.
        await redis.publish(
            "miniapp:start",
            json.dumps(
                {
                    "uuid": uid,
                    "user_id": request.user_id,
                    "query_id": request.query_id,
                }
            ),
        )

        ***REMOVED*** Curated success metadata — no raw UUID, no full URL.
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
async def phone(request: PhoneRequest) -> Any:
    """Collect phone and create CRM lead.

    Wrapped in ``@observe`` (***REMOVED***1658) with the same ``miniapp-{user_id}`` session
    grouping as ``start_expert`` so the funnel reconstructs in Langfuse
    Sessions. PII (phone, name) never reaches the span: ``capture_input/output``
    are off, and the inner ``submit_phone`` curates its own output. On CRM
    failure (``success=False``), return ``502 Bad Gateway`` so clients can
    distinguish a captured lead from a dropped one (***REMOVED***1596).
    """
    from fastapi.responses import JSONResponse

    with propagate_attributes(
        session_id=f"miniapp-{request.user_id}",
        user_id=str(request.user_id),
        tags=["miniapp", "submit-phone", request.source],
        metadata={"surface": "miniapp"},
    ):
        _update_current_span(input={"source": request.source, "has_name": request.name is not None})
        result = await submit_phone(request)
        if not result.get("success"):
            _update_current_span(level="ERROR", status_message="crm_submission_failed")
            return JSONResponse(status_code=502, content=result)
        return result


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
