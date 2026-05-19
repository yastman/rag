"""Mini App FastAPI backend.

Langfuse observability (#1658):
    Endpoints ``/api/start-expert`` and ``/api/phone`` are wrapped with
    ``@observe`` so the Mini App entry → Telegram dialog → CRM funnel can be
    reconstructed in Langfuse Sessions UI. ``propagate_attributes`` attaches
    a deterministic ``session_id="miniapp-{user_id}"`` so the subsequent
    ``/start q_<uuid>`` Telegram trace links into the same session.

WARNING (blocked-by #1595): until Telegram initData validation lands,
``user_id`` is taken from the request body and may be forged. The Draft PR
opening this work documents the dependency; do not treat the resulting
``user_id`` attribute as authenticated.
"""

from __future__ import annotations

import json
import os
import uuid as _uuid_lib
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mini_app.expert_start import StartExpertRequest, StartExpertResponse
from mini_app.phone import PhoneRequest, submit_phone
from telegram_bot.observability import (
    get_client,
    observe,
    propagate_attributes,
)
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


def _miniapp_session_id(user_id: int) -> str:
    """Deterministic session id linking the Mini App entry to the Telegram dialog."""
    return f"miniapp-{user_id}"


def _safe_start_expert_input(req: StartExpertRequest) -> dict[str, Any]:
    """Curated, PII-free input payload for the start-expert span."""
    return {
        "content_type": "miniapp",
        "endpoint": "start-expert",
        "expert_id": req.expert_id,
        "message_present": req.message is not None and bool(req.message.strip()),
        "message_len": len(req.message) if req.message else 0,
        "query_id_present": req.query_id is not None,
    }


def _safe_phone_input(req: PhoneRequest) -> dict[str, Any]:
    """Curated, PII-free input payload for the submit-phone span."""
    return {
        "content_type": "miniapp",
        "endpoint": "submit-phone",
        "source": req.source,
        "phone_present": bool(req.phone),
        "phone_len": len(req.phone) if req.phone else 0,
        "name_present": req.name is not None and bool(req.name.strip()),
    }


@app.get("/api/config")
async def get_config() -> dict:
    """Return Mini App UI config: questions + experts."""
    return load_mini_app_config()


@observe(name="miniapp-start-expert", capture_input=False, capture_output=False)
async def start_expert(request: StartExpertRequest) -> StartExpertResponse:
    """Store deep-link payload in Redis and return start_link for openTelegramLink."""
    from fastapi import HTTPException

    with propagate_attributes(
        session_id=_miniapp_session_id(request.user_id),
        user_id=str(request.user_id),
        metadata={"source": "miniapp"},
        tags=["miniapp", "start-expert", request.expert_id],
    ):
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
        redis = await _get_redis()
        await redis.set(f"miniapp:q:{uid}", payload, ex=_DEEPLINK_TTL)

        bot_username = os.environ.get("BOT_USERNAME", "")
        if not bot_username:
            raise HTTPException(status_code=500, detail="BOT_USERNAME not configured")
        start_link = f"https://t.me/{bot_username}?start=q_{uid}"

        # Notify bot via Redis pub/sub — bot calls answerWebAppQuery + creates topic + RAG
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

        lf = get_client()
        if lf is not None:
            lf.update_current_span(
                input=_safe_start_expert_input(request),
                output={
                    "delivery_status": "sent",
                    "deeplink_emitted": True,
                    "expert_name_resolved": True,
                },
                metadata={"source": "miniapp", "endpoint": "start-expert"},
            )

        return StartExpertResponse(
            start_link=start_link,
            expert_name=expert["name"],
        )


# Bind decorated callable to FastAPI route after definition so the @observe
# wrapper participates in the request lifecycle.
app.post("/api/start-expert")(start_expert)


@app.post("/api/log")
async def remote_log(request: dict) -> dict:
    """Receive frontend remote logs (Eruda / remoteLog helper)."""
    level = request.get("level", "info")
    message = request.get("message", "")
    data = request.get("data")
    print(f"[REMOTE:{level}] {message} {data or ''}", flush=True)
    return {"status": "ok"}


@observe(name="miniapp-submit-phone", capture_input=False, capture_output=False)
async def phone(request: PhoneRequest) -> dict:
    """Collect phone and create CRM lead."""
    with propagate_attributes(
        session_id=_miniapp_session_id(request.user_id),
        user_id=str(request.user_id),
        metadata={"source": "miniapp"},
        tags=["miniapp", "submit-phone", request.source],
    ):
        result = await submit_phone(request)

        lf = get_client()
        if lf is not None:
            lf.update_current_span(
                input=_safe_phone_input(request),
                output={
                    "delivery_status": "sent" if result.get("lead_id") else "degraded",
                    "lead_created": result.get("lead_id") is not None,
                },
                metadata={"source": "miniapp", "endpoint": "submit-phone"},
            )

        return result


app.post("/api/phone")(phone)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
