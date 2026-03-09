"""Mini App FastAPI backend."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from mini_app.chat import ChatRequest, chat_sse_generator
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


@app.get("/api/config")
async def get_config() -> dict:
    """Return Mini App UI config: questions + experts."""
    return load_mini_app_config()


@app.post("/api/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    """Chat endpoint with SSE streaming."""
    return StreamingResponse(
        chat_sse_generator(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/start-expert")
async def start_expert(request: StartExpertRequest) -> StartExpertResponse:
    """Create forum topic for expert and optionally send first message."""
    from fastapi import HTTPException

    from mini_app.bot_bridge import get_bot_bridge

    config = load_mini_app_config()
    experts = config.get("experts", [])
    expert = next((e for e in experts if e["id"] == request.expert_id), None)
    if expert is None:
        raise HTTPException(status_code=404, detail="Expert not found")

    topic_name = f"{expert['emoji']} {expert['name']}"

    bridge = get_bot_bridge()
    thread_id = await bridge.ensure_topic(
        chat_id=request.user_id,
        user_id=request.user_id,
        expert_id=request.expert_id,
        topic_name=topic_name,
    )

    if request.message:
        await bridge.send_to_topic(
            chat_id=request.user_id,
            thread_id=thread_id,
            message=request.message,
            expert_id=request.expert_id,
        )

    return StartExpertResponse(
        thread_id=thread_id,
        expert_name=expert["name"],
    )


@app.post("/api/phone")
async def phone(request: PhoneRequest) -> dict:
    """Collect phone and create CRM lead."""
    return await submit_phone(request)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
