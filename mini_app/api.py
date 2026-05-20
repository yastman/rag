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


@app.post("/api/start-expert")
async def start_expert(
    request: StartExpertRequest,
    redis: Any = Depends(get_redis),
) -> StartExpertResponse:
    """Store deep-link payload in Redis and return start_link for openTelegramLink."""
    from fastapi import HTTPException

    config = load_mini_app_config()
    experts = config.get("experts", [])
    expert = next((e for e in experts if e["id"] == request.expert_id), None)
    if expert is None:
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
        raise HTTPException(status_code=500, detail="BOT_USERNAME not configured")
    start_link = f"https://t.me/{bot_username}?start=q_{uid}"

    ***REMOVED*** Notify bot via Redis pub/sub — bot calls answerWebAppQuery + creates topic + RAG
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
async def phone(request: PhoneRequest) -> Any:
    """Collect phone and create CRM lead.

    Returns the same JSON shape as :func:`submit_phone`. On CRM failure
    (``success=False``) the response is wrapped in a ``502 Bad Gateway``
    so the frontend can distinguish a captured lead from a dropped one
    (***REMOVED***1596). Pydantic validation failures continue to surface as ``422``.
    """
    from fastapi.responses import JSONResponse

    result = await submit_phone(request)
    if not result.get("success"):
        return JSONResponse(status_code=502, content=result)
    return result


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
