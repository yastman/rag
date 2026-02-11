"""respond_node — sends the final response to the user via Telegram.

Sends with Markdown parse_mode, falls back to plain text on parse error.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from telegram_bot.observability import get_client, observe


logger = logging.getLogger(__name__)


@observe(name="node-respond")
async def respond_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node: send response to the user.

    Reads state["response"] and state["message"] (aiogram Message object),
    sends with Markdown formatting and falls back to plain text on failure.

    Returns partial state update with latency_stages["respond"].
    """
    t0 = time.perf_counter()

    message = state.get("message")
    response = state.get("response", "")

    if not response:
        response = "Извините, не удалось сформировать ответ. Попробуйте переформулировать вопрос."

    # Skip sending if streaming already delivered the response
    if state.get("response_sent", False):
        elapsed = time.perf_counter() - t0
        return {
            "latency_stages": {**state.get("latency_stages", {}), "respond": elapsed},
        }

    if message is not None:
        try:
            await message.answer(response, parse_mode="Markdown")
        except Exception:
            logger.warning("Markdown parse failed, falling back to plain text")
            try:
                await message.answer(response)
            except Exception as e:
                logger.exception("Failed to send response")
                get_client().update_current_span(
                    level="ERROR",
                    status_message=f"Telegram send failed: {str(e)[:200]}",
                )

    elapsed = time.perf_counter() - t0
    return {
        "latency_stages": {**state.get("latency_stages", {}), "respond": elapsed},
    }
