"""generate_node — LLM answer generation with conversation history.

Formats top-5 retrieved documents as context, builds system prompt with
domain from GraphConfig, includes conversation history, and calls LLM.
Falls back to a summary of retrieved docs if LLM is unavailable.

Supports streaming delivery to Telegram: sends placeholder message,
edits with accumulated chunks (throttled 300ms), finalizes with Markdown.
"""

from __future__ import annotations

import contextlib
import hashlib
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
) -> tuple[str, str, float, int | None]:
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
        Tuple of (response_text, actual_model, ttft_ms, completion_tokens).

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

    return accumulated, actual_model, ttft_ms, completion_tokens


def _extract_queue_ms_from_provider_headers(response_obj: Any | None) -> float | None:
    """Return provider-reported queue time in ms, or None if unavailable/unreliable."""
    return None


@observe(name="node-generate", capture_input=False, capture_output=False)
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
    raw_messages = state.get("messages", [])
    messages = _select_recent_history(raw_messages)

    config = _get_config()
    context = _format_context(documents)

    # Extract current query (needed for style detection before prompt building)
    last_msg = messages[-1] if messages else None
    query = ""
    if last_msg:
        query = (
            last_msg.get("content", "")
            if isinstance(last_msg, dict)
            else getattr(last_msg, "content", "")
        )

    # Detect response style (C+ scoring, no LLM call, ~0ms) (#129)
    # Rollout-safe: disabled → legacy, shadow → compute metrics but legacy prompt/tokens
    style_info = _detector.detect(query)
    style_enabled = bool(getattr(config, "response_style_enabled", False))
    shadow_mode = bool(getattr(config, "response_style_shadow_mode", False))

    legacy_max_tokens = int(config.generate_max_tokens)

    use_style = style_enabled and not shadow_mode
    if use_style:
        style_system_prompt = build_system_prompt_with_manager(
            style=style_info.style,
            difficulty=style_info.difficulty,
            domain=config.domain,
        )
        style_budget = get_token_limit(style_info.style, style_info.difficulty)
        system_prompt = style_system_prompt
        max_tokens = min(style_budget, legacy_max_tokens)
    else:
        system_prompt = _build_system_prompt(config.domain)
        max_tokens = legacy_max_tokens

    system_prompt = _ensure_history_instruction(system_prompt)

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

    user_content = (
        f"Контекст:\n{context}\n\nВопрос: {query}\n\nОтветь на вопрос на основе контекста выше."
    )
    llm_messages.append({"role": "user", "content": user_content})

    response_sent = False
    actual_model = config.llm_model
    ttft_ms = 0.0
    response_obj: Any | None = None
    completion_tokens: int | None = None
    stream_recovery = False
    hard_timeout = False

    # Curated span metadata
    lf = get_client()
    lf.update_current_span(
        input={
            "query_preview": query[:120],
            "query_len": len(query),
            "query_hash": hashlib.sha256(query.encode()).hexdigest()[:8],
            "context_docs_count": len(documents),
            "streaming_enabled": bool(message is not None and config.streaming_enabled),
        }
    )

    try:
        llm = config.create_llm()

        # Streaming path: deliver directly to Telegram
        if message is not None and config.streaming_enabled:
            try:
                answer, actual_model, ttft_ms, completion_tokens = await _generate_streaming(
                    llm,
                    config,
                    llm_messages,
                    message,
                    max_tokens,
                )
                response_sent = True
            except StreamingPartialDeliveryError as e:
                logger.warning(
                    "Streaming failed after partial delivery (%d chars), "
                    "falling back to non-streaming with edit",
                    len(e.partial_text),
                    exc_info=True,
                )
                response_obj = await llm.chat.completions.create(
                    model=config.llm_model,
                    messages=llm_messages,
                    temperature=config.llm_temperature,
                    max_tokens=max_tokens,
                    name="generate-answer",  # type: ignore[call-overload]
                )
                answer = response_obj.choices[0].message.content or ""
                actual_model = getattr(response_obj, "model", config.llm_model) or config.llm_model
                # Recovery is successful once fallback LLM response is produced,
                # even if edit delivery fails and respond_node sends later.
                stream_recovery = True
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
                get_client().update_current_span(
                    level="WARNING",
                    status_message="Streaming failed, using non-streaming fallback",
                )
                # Fall back to non-streaming
                response_obj = await llm.chat.completions.create(
                    model=config.llm_model,
                    messages=llm_messages,
                    temperature=config.llm_temperature,
                    max_tokens=max_tokens,
                    name="generate-answer",  # type: ignore[call-overload]
                )
                answer = response_obj.choices[0].message.content or ""
                actual_model = getattr(response_obj, "model", config.llm_model) or config.llm_model
                stream_recovery = True
        else:
            # Non-streaming path (original)
            response_obj = await llm.chat.completions.create(
                model=config.llm_model,
                messages=llm_messages,
                temperature=config.llm_temperature,
                max_tokens=max_tokens,
                name="generate-answer",  # type: ignore[call-overload]  # langfuse kwarg
            )
            answer = response_obj.choices[0].message.content or ""
            actual_model = getattr(response_obj, "model", config.llm_model) or config.llm_model
    except Exception as e:
        logger.exception("generate_node: LLM call failed, using fallback")
        get_client().update_current_span(
            level="ERROR",
            status_message=f"LLM failed: {str(e)[:200]}",
        )
        answer = _build_fallback_response(documents)
        actual_model = "fallback"
        ttft_ms = 0.0
        hard_timeout = True
        stream_recovery = False

    elapsed = time.monotonic() - t0

    span_output: dict[str, Any] = {
        "response_length": len(answer),
        "llm_provider_model": actual_model,
        "llm_ttft_ms": ttft_ms if ttft_ms > 0 else None,
        "llm_response_duration_ms": round(elapsed * 1000, 1),
        "fallback_used": actual_model == "fallback",
        "response_sent": response_sent,
    }
    if response_obj is not None:
        usage = getattr(response_obj, "usage", None)
        if usage is not None:
            span_output["token_usage"] = {
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
            }
    lf.update_current_span(output=span_output)

    # --- Latency breakdown (#147) ---
    streaming_was_enabled = bool(message is not None and config.streaming_enabled)
    llm_decode_ms: float | None = None
    llm_tps: float | None = None
    llm_queue_ms: float | None = _extract_queue_ms_from_provider_headers(response_obj)

    if streaming_was_enabled and ttft_ms > 0:
        response_duration_ms = elapsed * 1000
        llm_decode_ms = response_duration_ms - ttft_ms
        if llm_decode_ms < 0:
            llm_decode_ms = 0.0
        if completion_tokens is not None and llm_decode_ms > 0:
            llm_tps = completion_tokens / (llm_decode_ms / 1000)

    # Response length metrics (#129)
    answer_words = len(answer.split())
    answer_chars = len(answer)
    question_words = style_info.word_count
    ratio = answer_words / max(question_words, 1)
    response_policy_mode = "enforced" if use_style else ("shadow" if shadow_mode else "disabled")

    return {
        "response": answer,
        "response_sent": response_sent,
        "llm_provider_model": actual_model,
        "llm_ttft_ms": ttft_ms,
        "llm_response_duration_ms": elapsed * 1000,
        "latency_stages": {**state.get("latency_stages", {}), "generate": elapsed},
        # Latency breakdown (#147)
        "llm_decode_ms": llm_decode_ms,
        "llm_tps": llm_tps,
        "llm_queue_ms": llm_queue_ms,
        "llm_timeout": hard_timeout,
        "llm_stream_recovery": stream_recovery,
        "streaming_enabled": streaming_was_enabled,
        # Response length control (#129)
        "response_style": style_info.style,
        "response_difficulty": style_info.difficulty,
        "response_style_reasoning": style_info.reasoning,
        "answer_words": answer_words,
        "answer_chars": answer_chars,
        "answer_to_question_ratio": ratio,
        "response_policy_mode": response_policy_mode,
    }
