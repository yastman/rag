"""Mini App FastAPI backend."""

from __future__ import annotations

import json
import os
import uuid as _uuid_lib
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mini_app.expert_start import StartExpertRequest, StartExpertResponse
from mini_app.phone import PhoneRequest, submit_phone
from telegram_bot.services.content_loader import load_mini_app_config


app = FastAPI(title="FortNoks Mini App API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_redis_client: Any = None

_DEEPLINK_TTL = 300  # seconds


async def _get_redis() -> Any:
    """Lazy-init Redis client from REDIS_URL env var."""
    global _redis_client
    if _redis_client is None:
        import redis.asyncio as aioredis

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        _redis_client = aioredis.from_url(redis_url, decode_responses=True)
    return _redis_client


@app.get("/api/config")
async def get_config() -> dict:
    """Return Mini App UI config: questions + experts."""
    return load_mini_app_config()


@app.post("/api/start-expert")
async def start_expert(request: StartExpertRequest) -> StartExpertResponse:
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
        }
    )
    redis = await _get_redis()
    await redis.set(f"miniapp:q:{uid}", payload, ex=_DEEPLINK_TTL)

    bot_username = os.environ.get("BOT_USERNAME", "")
    if not bot_username:
        raise HTTPException(status_code=500, detail="BOT_USERNAME not configured")
    start_link = f"https://t.me/{bot_username}?start=q_{uid}"

    return StartExpertResponse(
        start_link=start_link,
        expert_name=expert["name"],
    )


@app.post("/api/phone")
async def phone(request: PhoneRequest) -> dict:
    """Collect phone and create CRM lead."""
    return await submit_phone(request)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
