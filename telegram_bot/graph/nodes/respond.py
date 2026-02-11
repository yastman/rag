"""respond_node — sends the final response to the user via Telegram.

Sends with Markdown parse_mode, falls back to plain text on parse error.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from telegram_bot.observability import get_client, observe


logger = logging.getLogger(__name__)


@observe(name="node-respond", capture_input=False, capture_output=False)
async def respond_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node: send response to the user.

    Reads state["response"] and state["message"] (aiogram Message object),
    sends with Markdown formatting and falls back to plain text on failure.

    Returns partial state update with latency_stages["respond"].
    """
    t0 = time.perf_counter()
    lf = get_client()

    message = state.get("message")
    response = state.get("response", "")
    response_sent = state.get("response_sent", False)

    if not response:
        response = "Извините, не удалось сформировать ответ. Попробуйте переформулировать вопрос."

    lf.update_current_span(
        input={
            "response_length": len(response),
            "response_sent": bool(response_sent),
            "has_message": message is not None,
        }
    )

    # Skip sending if streaming already delivered the response
    if response_sent:
        elapsed = time.perf_counter() - t0
        lf.update_current_span(
            output={
                "respond_skipped": True,
                "respond_delivered": False,
                "used_markdown": False,
                "duration_ms": round(elapsed * 1000, 1),
            }
        )
        return {
            "latency_stages": {**state.get("latency_stages", {}), "respond": elapsed},
            "messages": [{"role": "assistant", "content": response}],
        }

    delivered = False
    used_markdown = False
    if message is not None:
        try:
            await message.answer(response, parse_mode="Markdown")
            delivered = True
            used_markdown = True
        except Exception:
            logger.warning("Markdown parse failed, falling back to plain text")
            try:
                await message.answer(response)
                delivered = True
            except Exception as e:
                logger.exception("Failed to send response")
                lf.update_current_span(
                    level="ERROR",
                    status_message=f"Telegram send failed: {str(e)[:200]}",
                )

    elapsed = time.perf_counter() - t0
    lf.update_current_span(
        output={
            "respond_skipped": False,
            "respond_delivered": delivered,
            "used_markdown": used_markdown,
            "duration_ms": round(elapsed * 1000, 1),
        }
    )
    return {
        "latency_stages": {**state.get("latency_stages", {}), "respond": elapsed},
        "messages": [{"role": "assistant", "content": response}],
    }
