"""respond_node — sends the final response to the user via Telegram.

Sends with Markdown parse_mode, falls back to plain text on parse error.
Attaches feedback buttons when trace_id is available (#229).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from telegram_bot.observability import get_client, observe


logger = logging.getLogger(__name__)


_NO_FEEDBACK_TYPES = frozenset({"CHITCHAT", "OFF_TOPIC"})
_NO_SOURCES_TYPES = frozenset({"CHITCHAT", "OFF_TOPIC"})
_MAX_SOURCES = 5


def _build_reply_markup(trace_id: str, query_type: str = "") -> Any:
    """Build feedback keyboard if trace_id is available and query is RAG-eligible."""
    if not trace_id or query_type in _NO_FEEDBACK_TYPES:
        return None
    from telegram_bot.feedback import build_feedback_keyboard

    return build_feedback_keyboard(trace_id)


def _extract_sent_message_ref(state: dict[str, Any]) -> tuple[int, int] | None:
    """Read serialized streamed-message reference from state."""
    sent_message = state.get("sent_message")
    if not isinstance(sent_message, dict):
        return None
    chat_id = sent_message.get("chat_id")
    message_id = sent_message.get("message_id")
    if isinstance(chat_id, int) and isinstance(message_id, int):
        return chat_id, message_id
    return None


def _format_sources(documents: list[dict[str, Any]], max_sources: int = _MAX_SOURCES) -> str:
    """Format source documents as Telegram Markdown footnotes (#225)."""
    if not documents:
        return ""

    parts: list[str] = []
    for i, doc in enumerate(documents[:max_sources], 1):
        meta = doc.get("metadata", {})
        title = meta.get("title", "Документ")
        city = meta.get("city", "")
        score = doc.get("score", 0)
        line = f"`[{i}]` {title}"
        if city:
            line += f" — {city}"
        line += f" _(рел: {score:.2f})_"
        parts.append(line)

    return "\n\n\U0001f4ce *Источники:*\n" + "\n".join(parts)


@observe(name="node-respond", capture_input=False, capture_output=False)
async def respond_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node: send response to the user.

    Reads state["response"] and state["message"] (aiogram Message object),
    sends with Markdown formatting and falls back to plain text on failure.
    Attaches feedback inline keyboard when trace_id is present (#229).
    Appends source attribution footnotes when show_sources is enabled (#225).

    Returns partial state update with latency_stages["respond"].
    """
    t0 = time.perf_counter()
    lf = get_client()

    message = state.get("message")
    response = state.get("response", "")
    response_sent = state.get("response_sent", False)
    trace_id = state.get("trace_id", "")
    query_type = state.get("query_type", "")
    documents = state.get("documents", [])
    show_sources = state.get("show_sources", True)

    if not response:
        response = "Извините, не удалось сформировать ответ. Попробуйте переформулировать вопрос."

    # Build source attribution footnotes (#225)
    sources_text = ""
    sources_count = 0
    if show_sources and documents and query_type not in _NO_SOURCES_TYPES:
        sources_text = _format_sources(documents)
        sources_count = min(len(documents), _MAX_SOURCES)

    lf.update_current_span(
        input={
            "response_length": len(response),
            "response_sent": bool(response_sent),
            "has_message": message is not None,
            "has_trace_id": bool(trace_id),
            "show_sources": show_sources,
            "sources_count": sources_count,
        }
    )

    reply_markup = _build_reply_markup(trace_id, query_type)

    # Streaming path: response already delivered, append sources + feedback buttons
    if response_sent:
        sent_ref = _extract_sent_message_ref(state)
        bot = getattr(message, "bot", None)
        if sent_ref is not None and bot is not None:
            chat_id, message_id = sent_ref
            if sources_text:
                full_text = response + sources_text
                try:
                    await bot.edit_message_text(
                        text=full_text,
                        chat_id=chat_id,
                        message_id=message_id,
                        parse_mode="Markdown",
                        reply_markup=reply_markup,
                    )
                except Exception:
                    try:
                        await bot.edit_message_text(
                            text=full_text,
                            chat_id=chat_id,
                            message_id=message_id,
                            reply_markup=reply_markup,
                        )
                    except Exception:
                        logger.debug("Failed to append sources to streamed message")
                        if reply_markup is not None:
                            try:
                                await bot.edit_message_reply_markup(
                                    chat_id=chat_id,
                                    message_id=message_id,
                                    reply_markup=reply_markup,
                                )
                            except Exception:
                                logger.debug("Failed to attach feedback buttons")
            elif reply_markup is not None:
                try:
                    await bot.edit_message_reply_markup(
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup=reply_markup,
                    )
                except Exception:
                    logger.debug("Failed to attach feedback buttons to streamed message")

        elapsed = time.perf_counter() - t0
        lf.update_current_span(
            output={
                "respond_skipped": True,
                "respond_delivered": False,
                "used_markdown": False,
                "feedback_buttons": reply_markup is not None,
                "sources_appended": bool(sources_text),
                "duration_ms": round(elapsed * 1000, 1),
            }
        )
        return {
            "latency_stages": {**state.get("latency_stages", {}), "respond": elapsed},
            "messages": [{"role": "assistant", "content": response}],
            "sources_count": sources_count,
        }

    # Non-streaming path: append sources to response before sending
    full_response = response + sources_text if sources_text else response

    delivered = False
    used_markdown = False
    if message is not None:
        try:
            await message.answer(full_response, parse_mode="Markdown", reply_markup=reply_markup)
            delivered = True
            used_markdown = True
        except Exception:
            logger.warning("Markdown parse failed, falling back to plain text")
            try:
                await message.answer(full_response, reply_markup=reply_markup)
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
            "feedback_buttons": reply_markup is not None,
            "sources_appended": bool(sources_text),
            "duration_ms": round(elapsed * 1000, 1),
        }
    )
    return {
        "latency_stages": {**state.get("latency_stages", {}), "respond": elapsed},
        "messages": [{"role": "assistant", "content": response}],
        "sources_count": sources_count,
    }
