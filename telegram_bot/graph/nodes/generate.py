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
from telegram_bot.integrations.prompt_templates import (
    build_system_prompt_with_manager,
    get_token_limit,
)
from telegram_bot.observability import get_client, observe
from telegram_bot.services.generate_response import generate_response as _generate_response_service
from telegram_bot.services.response_style_detector import ResponseStyleDetector


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
_MAX_HISTORY_MESSAGES = 12
_detector = ResponseStyleDetector()
_HISTORY_INSTRUCTION = (
    "Учитывай историю диалога. Если пользователь ссылается на предыдущие "
    "сообщения — отвечай из контекста разговора, а не из документов."
)
_CITATION_INSTRUCTION = (
    "Когда используешь информацию из контекста, ссылайся на источники как [1], [2] и т.д. "
    "Номера соответствуют объектам в контексте: [Объект 1] = [1], [Объект 2] = [2].\n"
    "НЕ добавляй список источников в конце ответа — он будет сформирован автоматически."
)


def _extract_sent_message_ref(sent_msg: Any) -> dict[str, int] | None:
    """Build serializable Telegram message reference for checkpointer state."""
    chat = getattr(sent_msg, "chat", None)
    chat_id = getattr(chat, "id", None)
    message_id = getattr(sent_msg, "message_id", None)
    if isinstance(chat_id, int) and isinstance(message_id, int):
        return {"chat_id": chat_id, "message_id": message_id}
    return None


def _get_config() -> Any:
    """Get GraphConfig from environment."""
    from telegram_bot.graph.config import GraphConfig

    return GraphConfig.from_env()


_GENERATE_FALLBACK = (
    "Ты — ассистент по {{domain}}.\n\n"
    "Отвечай на вопросы пользователя на основе предоставленного контекста.\n"
    f"{_HISTORY_INSTRUCTION}\n"
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

        meta_str = ""
        if "title" in metadata:
            meta_str += f"Название: {metadata['title']}\n"
        if "city" in metadata:
            meta_str += f"Город: {metadata['city']}\n"
        if "price" in metadata:
            meta_str += f"Цена: {metadata['price']:,}€\n"

        parts.append(f"[Объект {i}]\n{meta_str}{text}")

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


def _select_recent_history(
    messages: list[Any], max_messages: int = _MAX_HISTORY_MESSAGES
) -> list[Any]:
    """Return only recent conversation history messages for LLM context."""
    if not messages:
        return []
    return messages[-max_messages:]


def _ensure_history_instruction(system_prompt: str) -> str:
    """Ensure all prompt paths include history handling instruction."""
    lowered = system_prompt.lower()
    if (
        "ссылается на предыдущие" in lowered
        or "из контекста разговора" in lowered
        or _HISTORY_INSTRUCTION.lower() in lowered
    ):
        return system_prompt

    separator = "\n" if system_prompt.endswith("\n") else "\n\n"
    return f"{system_prompt}{separator}{_HISTORY_INSTRUCTION}"


async def _generate_streaming(
    llm: Any,
    config: Any,
    llm_messages: list[dict[str, str]],
    message: Any,
    max_tokens: int = 0,
) -> tuple[str, str, float, int | None, Any]:
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
        Tuple of (response_text, actual_model, ttft_ms, completion_tokens, sent_msg).

    Raises:
        Exception: On any streaming failure (caller handles fallback).
    """
    sent_msg = await message.answer(_STREAM_PLACEHOLDER)

    accumulated = ""
    last_edit = 0.0
    ttft_ms = 0.0
    actual_model = config.llm_model
    completion_tokens: int | None = None

    effective_max_tokens = max_tokens if max_tokens > 0 else int(config.generate_max_tokens)
    stream = await llm.chat.completions.create(
        model=config.llm_model,
        messages=llm_messages,
        temperature=config.llm_temperature,
        max_tokens=effective_max_tokens,
        stream=True,
        name="generate-answer",  # type: ignore[call-overload]  # langfuse kwarg
    )

    t_stream_start = time.monotonic()
    try:
        async for chunk in stream:
            if hasattr(chunk, "usage") and chunk.usage is not None:
                ct = getattr(chunk.usage, "completion_tokens", None)
                if ct is not None:
                    completion_tokens = ct
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                if ttft_ms == 0.0:
                    ttft_ms = (time.monotonic() - t_stream_start) * 1000
                accumulated += delta.content
                now = time.monotonic()
                if now - last_edit >= _STREAM_EDIT_INTERVAL:
                    with contextlib.suppress(Exception):
                        await sent_msg.edit_text(accumulated)
                    last_edit = now
            if hasattr(chunk, "model") and chunk.model:
                actual_model = chunk.model
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

    return accumulated, actual_model, ttft_ms, completion_tokens, sent_msg


def _extract_queue_ms_from_provider_headers(response_obj: Any | None) -> float | None:
    """Return provider-reported queue time in ms, or None if unavailable/unreliable."""
    return None


@observe(name="node-generate", capture_input=False, capture_output=False)
async def generate_node(state: RAGState, *, message: Any | None = None) -> dict[str, Any]:
    """Adapter: delegates generation core to shared service with node defaults."""
    documents = state.get("documents", [])
    raw_messages = state.get("messages", [])
    messages = _select_recent_history(raw_messages)
    last_msg = messages[-1] if messages else None
    query = ""
    if last_msg:
        query = (
            last_msg.get("content", "")
            if isinstance(last_msg, dict)
            else getattr(last_msg, "content", "")
        )

    return await _generate_response_service(
        query=query,
        documents=documents,
        retrieved_context=state.get("retrieved_context", []),
        raw_messages=raw_messages,
        latency_stages=state.get("latency_stages", {}),
        llm_call_count=int(state.get("llm_call_count", 0) or 0),
        message=message,
        config=_get_config(),
        lf_client=get_client(),
        max_context_docs=_MAX_CONTEXT_DOCS,
        format_context=_format_context,
        select_recent_history=_select_recent_history,
        build_system_prompt=_build_system_prompt,
        ensure_history_instruction=_ensure_history_instruction,
        build_fallback_response=_build_fallback_response,
        generate_streaming=_generate_streaming,
        style_detector=_detector,
        style_prompt_builder=build_system_prompt_with_manager,
        style_token_limit=get_token_limit,
        extract_queue_ms=_extract_queue_ms_from_provider_headers,
        extract_sent_message_ref=_extract_sent_message_ref,
        citation_instruction=_CITATION_INSTRUCTION,
    )
