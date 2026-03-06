"""Mini App chat — wraps existing RAG pipeline with SSE streaming."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator

from pydantic import BaseModel


logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str
    user_id: int
    expert_id: str | None = None
    question_id: str | None = None


async def run_mini_app_query(
    message: str,
    user_id: int,
    expert_id: str | None = None,
) -> dict:
    """Run RAG pipeline for Mini App query.

    Imports at call time to avoid circular deps and allow mocking.
    """
    from telegram_bot.agents.rag_pipeline import rag_pipeline  # type: ignore[import-untyped]

    return await rag_pipeline(query=message)  # type: ignore[no-any-return]


async def chat_sse_generator(request: ChatRequest) -> AsyncGenerator[str, None]:
    """Generate SSE events for chat response."""
    yield f"data: {json.dumps({'type': 'start'})}\n\n"

    try:
        result = await run_mini_app_query(
            message=request.message,
            user_id=request.user_id,
            expert_id=request.expert_id,
        )
        response = result.get("response", "")

        chunk_size = 20
        for i in range(0, len(response), chunk_size):
            chunk = response[i : i + chunk_size]
            yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"

        yield f"data: {json.dumps({'type': 'done', 'full_text': response})}\n\n"

    except Exception:
        logger.exception("Mini App chat error")
        yield (
            f"data: {json.dumps({'type': 'error', 'text': 'Произошла ошибка. Попробуйте позже.'})}\n\n"
        )
