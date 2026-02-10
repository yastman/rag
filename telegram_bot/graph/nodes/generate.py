"""generate_node — LLM answer generation with conversation history.

Formats top-5 retrieved documents as context, builds system prompt with
domain from GraphConfig, includes conversation history, and calls LLM.
Falls back to a summary of retrieved docs if LLM is unavailable.

Supports streaming delivery to Telegram: sends placeholder message,
edits with accumulated chunks (throttled 300ms), finalizes with Markdown.
"""

from __future__ import annotations

import contextlib
import logging
import time
from typing import Any

from telegram_bot.graph.state import RAGState
from telegram_bot.integrations.prompt_manager import get_prompt
from telegram_bot.observability import observe


logger = logging.getLogger(__name__)


class StreamingPartialDeliveryError(Exception):
    """Raised when streaming delivered partial content to user then failed."""

    def __init__(self, sent_msg: Any, partial_text: str):
        self.sent_msg = sent_msg
        self.partial_text = partial_text
        super().__init__(f"Streaming failed after delivering {len(partial_text)} chars")


_MAX_CONTEXT_DOCS = 5
_STREAM_EDIT_INTERVAL = 0.3  # 300ms throttle for Telegram edit_text
_STREAM_PLACEHOLDER = "⏳ Генерирую ответ..."


def _get_config() -> Any:
    """Get GraphConfig from environment."""
    from telegram_bot.graph.config import GraphConfig

    return GraphConfig.from_env()


_GENERATE_FALLBACK = (
    "Ты — ассистент по {{domain}}.\n\n"
    "Отвечай на вопросы пользователя на основе предоставленного контекста.\n"
    "Если информации недостаточно, честно скажи об этом.\n"
    "Всегда указывай цены в евро и расстояния в метрах.\n"
    "Будь вежливым и полезным.\n\n"
    "Форматируй ответ с Markdown: используй **жирный** для важного, • для списков."
)


def _build_system_prompt(domain: str) -> str:
    """Build system prompt with domain context."""
    return get_prompt("generate", fallback=_GENERATE_FALLBACK, variables={"domain": domain})


def _format_context(documents: list[dict[str, Any]], max_docs: int = _MAX_CONTEXT_DOCS) -> str:
    """Format top-N retrieved documents into LLM context string."""
    if not documents:
        return "Релевантной информации не найдено."

    parts: list[str] = []
    for i, doc in enumerate(documents[:max_docs], 1):
        text = doc.get("text", "")
        metadata = doc.get("metadata", {})
        score = doc.get("score", 0)

        meta_str = ""
        if "title" in metadata:
            meta_str += f"Название: {metadata['title']}\n"
        if "city" in metadata:
            meta_str += f"Город: {metadata['city']}\n"
        if "price" in metadata:
            meta_str += f"Цена: {metadata['price']:,}€\n"

        parts.append(f"[Объект {i}] (релевантность: {score:.2f})\n{meta_str}{text}")

    return "\n\n---\n\n".join(parts)


def _build_fallback_response(documents: list[dict[str, Any]]) -> str:
    """Build fallback response from retrieved documents when LLM fails."""
    if not documents:
        return "⚠️ Извините, сервис временно недоступен.\n\nПопробуйте повторить запрос позже."

    fallback = "⚠️ Сервис генерации ответов временно недоступен.\n\n"
    fallback += "Вот найденные объекты по вашему запросу:\n\n"

    for i, doc in enumerate(documents[:3], 1):
        meta = doc.get("metadata", {})
        fallback += f"{i}. "
        if "title" in meta:
            fallback += f"{meta['title']}\n"
        if "price" in meta:
            price = meta["price"]
            if isinstance(price, int | float):
                fallback += f"   Цена: {price:,}€\n"
            else:
                fallback += f"   Цена: {price}€\n"
        if "city" in meta:
            fallback += f"   Город: {meta['city']}\n"
        fallback += "\n"

    fallback += "Пожалуйста, попробуйте повторить запрос позже для получения детального ответа."
    return fallback


async def _generate_streaming(
    llm: Any,
    config: Any,
    llm_messages: list[dict[str, str]],
    message: Any,
) -> str:
    """Stream LLM response directly to Telegram via message editing.

    Sends a placeholder message, then edits it with accumulated text as chunks
    arrive from the OpenAI streaming API. Throttles edits to _STREAM_EDIT_INTERVAL.
    Finalizes with Markdown parse_mode (falls back to plain text).

    Args:
        llm: AsyncOpenAI client instance.
        config: GraphConfig with model parameters.
        llm_messages: OpenAI-format message list.
        message: aiogram Message object for Telegram delivery.

    Returns:
        Complete response text.

    Raises:
        Exception: On any streaming failure (caller handles fallback).
    """
    sent_msg = await message.answer(_STREAM_PLACEHOLDER)

    accumulated = ""
    last_edit = 0.0

    stream = await llm.chat.completions.create(
        model=config.llm_model,
        messages=llm_messages,
        temperature=config.llm_temperature,
        max_tokens=config.generate_max_tokens,
        stream=True,
        name="generate-answer",  # type: ignore[call-overload]  # langfuse kwarg
    )

    try:
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                accumulated += delta.content
                now = time.monotonic()
                if now - last_edit >= _STREAM_EDIT_INTERVAL:
                    with contextlib.suppress(Exception):
                        await sent_msg.edit_text(accumulated)
                    last_edit = now
    except Exception:
        if accumulated:
            raise StreamingPartialDeliveryError(sent_msg, accumulated) from None
        # No real content delivered — clean up placeholder
        with contextlib.suppress(Exception):
            await sent_msg.delete()
        raise

    if not accumulated:
        # Stream produced no content — clean up placeholder
        with contextlib.suppress(Exception):
            await sent_msg.delete()
        raise ValueError("Streaming produced empty response")

    # Final edit with Markdown formatting
    try:
        await sent_msg.edit_text(accumulated, parse_mode="Markdown")
    except Exception:
        try:
            await sent_msg.edit_text(accumulated)
        except Exception:
            logger.warning("Failed to finalize streaming message")

    return accumulated


@observe(name="node-generate")
async def generate_node(state: RAGState, *, message: Any | None = None) -> dict[str, Any]:
    """Generate an answer from retrieved documents using LLM.

    Builds a prompt with:
    - System prompt (domain from config)
    - Formatted context from top-5 documents
    - Conversation history from state messages

    When message is provided and streaming is enabled, streams the response
    directly to Telegram via edit_text. Falls back to non-streaming on error.

    Returns partial state update with response, response_sent flag, and latency.
    """
    t0 = time.monotonic()

    documents = state.get("documents", [])
    messages = state.get("messages", [])

    config = _get_config()
    context = _format_context(documents)
    system_prompt = _build_system_prompt(config.domain)

    # Build OpenAI-format messages
    llm_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]

    # Add conversation history (all messages except the last user message)
    for msg in messages[:-1]:
        role = msg.get("role", "") if isinstance(msg, dict) else getattr(msg, "type", "")
        content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
        if role in ("user", "human"):
            llm_messages.append({"role": "user", "content": str(content)})
        elif role in ("assistant", "ai"):
            llm_messages.append({"role": "assistant", "content": str(content)})

    # Add current query with context
    last_msg = messages[-1] if messages else None
    query = ""
    if last_msg:
        query = (
            last_msg.get("content", "")
            if isinstance(last_msg, dict)
            else getattr(last_msg, "content", "")
        )

    user_content = (
        f"Контекст:\n{context}\n\nВопрос: {query}\n\nОтветь на вопрос на основе контекста выше."
    )
    llm_messages.append({"role": "user", "content": user_content})

    response_sent = False

    try:
        llm = config.create_llm()

        # Streaming path: deliver directly to Telegram
        if message is not None and config.streaming_enabled:
            try:
                answer = await _generate_streaming(llm, config, llm_messages, message)
                response_sent = True
            except StreamingPartialDeliveryError as e:
                logger.warning(
                    "Streaming failed after partial delivery (%d chars), "
                    "falling back to non-streaming with edit",
                    len(e.partial_text),
                    exc_info=True,
                )
                response = await llm.chat.completions.create(
                    model=config.llm_model,
                    messages=llm_messages,
                    temperature=config.llm_temperature,
                    max_tokens=config.generate_max_tokens,
                    name="generate-answer",  # type: ignore[call-overload]
                )
                answer = response.choices[0].message.content or ""
                # Edit existing message with fallback answer
                delivered = False
                try:
                    await e.sent_msg.edit_text(answer, parse_mode="Markdown")
                    delivered = True
                except Exception:
                    try:
                        await e.sent_msg.edit_text(answer)
                        delivered = True
                    except Exception:
                        logger.warning(
                            "Failed to deliver fallback edit after partial stream; "
                            "respond_node will send final answer",
                            exc_info=True,
                        )
                response_sent = delivered
            except Exception:
                logger.warning("Streaming failed, falling back to non-streaming", exc_info=True)
                # Fall back to non-streaming
                response = await llm.chat.completions.create(
                    model=config.llm_model,
                    messages=llm_messages,
                    temperature=config.llm_temperature,
                    max_tokens=config.generate_max_tokens,
                    name="generate-answer",  # type: ignore[call-overload]
                )
                answer = response.choices[0].message.content or ""
        else:
            # Non-streaming path (original)
            response = await llm.chat.completions.create(
                model=config.llm_model,
                messages=llm_messages,
                temperature=config.llm_temperature,
                max_tokens=config.generate_max_tokens,
                name="generate-answer",  # type: ignore[call-overload]  # langfuse kwarg
            )
            answer = response.choices[0].message.content or ""
    except Exception:
        logger.exception("generate_node: LLM call failed, using fallback")
        answer = _build_fallback_response(documents)

    elapsed = time.monotonic() - t0
    return {
        "response": answer,
        "response_sent": response_sent,
        "latency_stages": {**state.get("latency_stages", {}), "generate": elapsed},
    }
