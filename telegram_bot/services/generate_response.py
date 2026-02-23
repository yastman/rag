"""Shared LLM response generation service for text/voice pipelines."""

from __future__ import annotations

import contextlib
import hashlib
import logging
import time
from collections.abc import Callable
from typing import Any

from telegram_bot.integrations.prompt_manager import get_prompt
from telegram_bot.integrations.prompt_templates import (
    build_system_prompt_with_manager,
    get_token_limit,
)
from telegram_bot.observability import get_client, observe
from telegram_bot.services.metrics import PipelineMetrics
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
_GENERATE_FALLBACK = (
    "Ты — ассистент по {{domain}}.\n\n"
    "Отвечай на вопросы пользователя на основе предоставленного контекста.\n"
    f"{_HISTORY_INSTRUCTION}\n"
    "Если информации недостаточно, честно скажи об этом.\n"
    "Всегда указывай цены в евро и расстояния в метрах.\n"
    "Будь вежливым и полезным.\n\n"
    "Форматируй ответ с Markdown: используй **жирный** для важного, • для списков."
)


def _extract_sent_message_ref(sent_msg: Any) -> dict[str, int] | None:
    """Build serializable Telegram message reference for checkpointer state."""
    chat = getattr(sent_msg, "chat", None)
    chat_id = getattr(chat, "id", None)
    message_id = getattr(sent_msg, "message_id", None)
    if isinstance(chat_id, int) and isinstance(message_id, int):
        return {"chat_id": chat_id, "message_id": message_id}
    return None


def _get_graph_config() -> Any:
    """Get GraphConfig from environment."""
    from telegram_bot.graph.config import GraphConfig

    return GraphConfig.from_env()


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


def _coerce_positive_number(value: Any) -> float | None:
    """Normalize provider token metrics to a positive numeric value."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        num = float(value)
        return num if num > 0 else None
    return None


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
) -> tuple[str, str, float, float | None, Any]:
    """Stream LLM response directly to Telegram via message editing."""
    sent_msg = await message.answer(_STREAM_PLACEHOLDER)

    accumulated = ""
    last_edit = 0.0
    ttft_ms = 0.0
    actual_model = config.llm_model
    completion_tokens: float | None = None

    effective_max_tokens = max_tokens if max_tokens > 0 else int(config.generate_max_tokens)
    stream = await llm.chat.completions.create(
        model=config.llm_model,
        messages=llm_messages,
        temperature=config.llm_temperature,
        max_tokens=effective_max_tokens,
        stream=True,
        stream_options={"include_usage": True},
        name="generate-answer",  # type: ignore[call-overload]  # langfuse kwarg
    )

    t_stream_start = time.monotonic()
    try:
        async for chunk in stream:
            if hasattr(chunk, "usage") and chunk.usage is not None:
                ct = getattr(chunk.usage, "completion_tokens", None)
                maybe_tokens = _coerce_positive_number(ct)
                if maybe_tokens is not None:
                    completion_tokens = maybe_tokens
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


@observe(name="service-generate-response", capture_input=False, capture_output=False)
async def generate_response(
    *,
    query: str,
    documents: list[dict[str, Any]],
    retrieved_context: list[dict[str, Any]] | None = None,
    raw_messages: list[Any] | None = None,
    latency_stages: dict[str, float] | None = None,
    llm_call_count: int = 0,
    message: Any | None = None,
    config: Any | None = None,
    get_config: Callable[[], Any] | None = None,
    lf_client: Any | None = None,
    get_lf_client: Callable[[], Any] | None = None,
    max_context_docs: int = _MAX_CONTEXT_DOCS,
    format_context: Callable[[list[dict[str, Any]], int], str] = _format_context,
    select_recent_history: Callable[[list[Any], int], list[Any]] = _select_recent_history,
    build_system_prompt: Callable[[str], str] = _build_system_prompt,
    ensure_history_instruction: Callable[[str], str] = _ensure_history_instruction,
    build_fallback_response: Callable[[list[dict[str, Any]]], str] = _build_fallback_response,
    generate_streaming: Callable[..., Any] = _generate_streaming,
    style_detector: ResponseStyleDetector | None = None,
    style_prompt_builder: Callable[..., str] = build_system_prompt_with_manager,
    style_token_limit: Callable[[Any, str], int] = get_token_limit,
    extract_queue_ms: Callable[
        [Any | None], float | None
    ] = _extract_queue_ms_from_provider_headers,
    extract_sent_message_ref: Callable[[Any], dict[str, int] | None] = _extract_sent_message_ref,
    citation_instruction: str = _CITATION_INSTRUCTION,
) -> dict[str, Any]:
    """Generate an LLM answer from retrieved context with optional Telegram streaming."""
    t0 = time.monotonic()

    if config is None:
        config = get_config() if get_config is not None else _get_graph_config()
    if lf_client is None:
        lf_client = get_lf_client() if get_lf_client is not None else get_client()

    docs = documents or []
    raw_history = raw_messages or []
    messages = select_recent_history(raw_history, _MAX_HISTORY_MESSAGES)
    context = format_context(docs, max_context_docs)

    # Derive query from last message if caller didn't pass explicit query.
    effective_query = query
    if not effective_query and messages:
        last_msg = messages[-1]
        effective_query = (
            last_msg.get("content", "")
            if isinstance(last_msg, dict)
            else getattr(last_msg, "content", "")
        )

    detector = style_detector or _detector
    style_info = detector.detect(effective_query)
    style_enabled = bool(getattr(config, "response_style_enabled", False))
    shadow_mode = bool(getattr(config, "response_style_shadow_mode", False))
    legacy_max_tokens = int(config.generate_max_tokens)
    use_style = style_enabled and not shadow_mode

    if use_style:
        style_system_prompt = style_prompt_builder(
            style=style_info.style,
            difficulty=style_info.difficulty,
            domain=config.domain,
        )
        style_budget = style_token_limit(style_info.style, style_info.difficulty)
        system_prompt = style_system_prompt
        max_tokens = min(style_budget, legacy_max_tokens)
    else:
        system_prompt = build_system_prompt(config.domain)
        max_tokens = legacy_max_tokens

    system_prompt = ensure_history_instruction(system_prompt)

    # Citation instruction (#225) — only when sources are enabled
    if getattr(config, "show_sources", False) and docs:
        separator = "\n" if system_prompt.endswith("\n") else "\n\n"
        system_prompt = f"{system_prompt}{separator}{citation_instruction}"

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

    user_content = f"Контекст:\n{context}\n\nВопрос: {effective_query}\n\nОтветь на вопрос на основе контекста выше."
    llm_messages.append({"role": "user", "content": user_content})

    response_sent = False
    actual_model = config.llm_model
    ttft_ms = 0.0
    response_obj: Any | None = None
    completion_tokens: float | None = None
    stream_recovery = False
    hard_timeout = False
    sent_msg: Any = None

    # Curated span metadata
    lf_client.update_current_span(
        input={
            "query_preview": effective_query[:120],
            "query_len": len(effective_query),
            "query_hash": hashlib.sha256(effective_query.encode()).hexdigest()[:8],
            "context_docs_count": len(docs),
            "streaming_enabled": bool(message is not None and config.streaming_enabled),
        }
    )

    try:
        llm = config.create_llm()

        # Streaming path: deliver directly to Telegram
        if message is not None and config.streaming_enabled:
            try:
                (
                    answer,
                    actual_model,
                    ttft_ms,
                    completion_tokens,
                    sent_msg,
                ) = await generate_streaming(
                    llm,
                    config,
                    llm_messages,
                    message,
                    max_tokens,
                )
                response_sent = True
            except Exception as stream_exc:
                if hasattr(stream_exc, "sent_msg") and hasattr(stream_exc, "partial_text"):
                    logger.warning(
                        "Streaming failed after partial delivery (%d chars), "
                        "falling back to non-streaming with edit",
                        len(getattr(stream_exc, "partial_text", "")),
                        exc_info=True,
                    )
                    sent_msg = getattr(stream_exc, "sent_msg", None)
                    t_llm_start = time.monotonic()
                    response_obj = await llm.chat.completions.create(
                        model=config.llm_model,
                        messages=llm_messages,
                        temperature=config.llm_temperature,
                        max_tokens=max_tokens,
                        name="generate-answer",  # type: ignore[call-overload]
                    )
                    t_llm_end = time.monotonic()
                    answer = response_obj.choices[0].message.content or ""
                    actual_model = (
                        getattr(response_obj, "model", config.llm_model) or config.llm_model
                    )
                    ttft_ms = (t_llm_end - t_llm_start) * 1000
                    usage = getattr(response_obj, "usage", None)
                    if usage is not None:
                        completion_tokens = _coerce_positive_number(
                            getattr(usage, "completion_tokens", None)
                        )
                    stream_recovery = True
                    delivered = False
                    if sent_msg is not None:
                        try:
                            await sent_msg.edit_text(answer, parse_mode="Markdown")
                            delivered = True
                        except Exception:
                            try:
                                await sent_msg.edit_text(answer)
                                delivered = True
                            except Exception:
                                logger.warning(
                                    "Failed to deliver fallback edit after partial stream; "
                                    "respond_node will send final answer",
                                    exc_info=True,
                                )
                    response_sent = delivered
                else:
                    logger.warning("Streaming failed, falling back to non-streaming", exc_info=True)
                    lf_client.update_current_span(
                        level="WARNING",
                        status_message="Streaming failed, using non-streaming fallback",
                    )
                    t_llm_start = time.monotonic()
                    response_obj = await llm.chat.completions.create(
                        model=config.llm_model,
                        messages=llm_messages,
                        temperature=config.llm_temperature,
                        max_tokens=max_tokens,
                        name="generate-answer",  # type: ignore[call-overload]
                    )
                    t_llm_end = time.monotonic()
                    answer = response_obj.choices[0].message.content or ""
                    actual_model = (
                        getattr(response_obj, "model", config.llm_model) or config.llm_model
                    )
                    ttft_ms = (t_llm_end - t_llm_start) * 1000
                    usage = getattr(response_obj, "usage", None)
                    if usage is not None:
                        completion_tokens = _coerce_positive_number(
                            getattr(usage, "completion_tokens", None)
                        )
                    stream_recovery = True
        else:
            # Non-streaming path
            t_llm_start = time.monotonic()
            response_obj = await llm.chat.completions.create(
                model=config.llm_model,
                messages=llm_messages,
                temperature=config.llm_temperature,
                max_tokens=max_tokens,
                name="generate-answer",  # type: ignore[call-overload]  # langfuse kwarg
            )
            t_llm_end = time.monotonic()
            answer = response_obj.choices[0].message.content or ""
            actual_model = getattr(response_obj, "model", config.llm_model) or config.llm_model
            # For non-streaming: TTFT = entire call duration (one-shot completion)
            ttft_ms = (t_llm_end - t_llm_start) * 1000
            usage = getattr(response_obj, "usage", None)
            if usage is not None:
                completion_tokens = _coerce_positive_number(
                    getattr(usage, "completion_tokens", None)
                )
    except Exception as e:
        logger.exception("generate_response: LLM call failed, using fallback")
        lf_client.update_current_span(
            level="ERROR",
            status_message=f"LLM failed: {str(e)[:200]}",
        )
        answer = build_fallback_response(docs)
        actual_model = "fallback"
        ttft_ms = 0.0
        hard_timeout = True
        stream_recovery = False

    elapsed = time.monotonic() - t0
    PipelineMetrics.get().record("generate", elapsed * 1000)

    # Build eval context for managed evaluators (#386)
    retrieved_ctx = retrieved_context or []
    eval_context = "\n\n".join(
        f"[{d.get('score', 0):.2f}] {d.get('content', '')[:500]}"
        for d in retrieved_ctx[:5]
        if isinstance(d, dict)
    )

    span_output: dict[str, Any] = {
        "response_length": len(answer),
        "llm_provider_model": actual_model,
        "llm_ttft_ms": ttft_ms if ttft_ms > 0 else None,
        "llm_response_duration_ms": round(elapsed * 1000, 1),
        "fallback_used": actual_model == "fallback",
        "response_sent": response_sent,
        "eval_query": effective_query[:2000],
        "eval_answer": answer[:3000],
        "eval_context": eval_context,
    }
    if response_obj is not None:
        usage = getattr(response_obj, "usage", None)
        if usage is not None:
            span_output["token_usage"] = {
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
            }
    lf_client.update_current_span(output=span_output)

    # --- Latency breakdown (#147) ---
    streaming_was_enabled = bool(message is not None and config.streaming_enabled)
    llm_decode_ms: float | None = None
    llm_tps: float | None = None
    llm_queue_ms: float | None = extract_queue_ms(response_obj)

    if streaming_was_enabled and ttft_ms > 0:
        response_duration_ms = elapsed * 1000
        llm_decode_ms = response_duration_ms - ttft_ms
        if llm_decode_ms < 0:
            llm_decode_ms = 0.0
        if completion_tokens is not None and llm_decode_ms > 0:
            llm_tps = completion_tokens / (llm_decode_ms / 1000)
    elif not streaming_was_enabled and ttft_ms > 0:
        # Non-streaming: no decode/prefill distinction; compute TPS from total call time
        if completion_tokens is not None and ttft_ms > 0:
            llm_tps = completion_tokens / (ttft_ms / 1000)

    # Response length metrics (#129)
    answer_words = len(answer.split())
    answer_chars = len(answer)
    question_words = style_info.word_count
    ratio = answer_words / max(question_words, 1)
    response_policy_mode = "enforced" if use_style else ("shadow" if shadow_mode else "disabled")

    sent_message_ref = (
        extract_sent_message_ref(sent_msg) if response_sent and sent_msg is not None else None
    )
    current_latency = latency_stages or {}
    current_llm_calls = max(0, int(llm_call_count))

    return {
        "response": answer,
        "response_sent": response_sent,
        "sent_message": sent_message_ref,
        "llm_provider_model": actual_model,
        "llm_ttft_ms": ttft_ms,
        "llm_response_duration_ms": elapsed * 1000,
        "llm_call_count": current_llm_calls + 1,
        "latency_stages": {**current_latency, "generate": elapsed},
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
