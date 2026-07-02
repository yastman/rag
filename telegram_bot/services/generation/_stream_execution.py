"""Stream execution mechanics — Stage 2 of the generation pipeline.

Handles streaming delivery, partial-delivery recovery, and non-streaming fallback.
"""

from __future__ import annotations

import contextlib
import dataclasses
import inspect
import logging
import time
from collections.abc import Callable
from typing import Any

from src.runtime.generation import GenerationRequest, generate_answer_stream
from telegram_bot.services.generation.telegram_formatting import (
    build_reply_parameters,
    format_answer_html,
)


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connection-error detection (#1408)
# ---------------------------------------------------------------------------

_CONNECTION_ERROR_TYPES: tuple[type[BaseException], ...]
_HTTPX_CONNECT_ERROR: type[BaseException] | None
try:
    from httpx import ConnectError

    _HTTPX_CONNECT_ERROR = ConnectError
except ImportError:  # pragma: no cover
    _HTTPX_CONNECT_ERROR = None

_OPENAI_API_CONNECTION_ERROR: type[BaseException] | None
try:
    from openai import APIConnectionError

    _OPENAI_API_CONNECTION_ERROR = APIConnectionError
except ImportError:  # pragma: no cover
    _OPENAI_API_CONNECTION_ERROR = None

_conn_errors: list[type[BaseException]] = []
if _HTTPX_CONNECT_ERROR is not None:
    _conn_errors.append(_HTTPX_CONNECT_ERROR)
if _OPENAI_API_CONNECTION_ERROR is not None:
    _conn_errors.append(_OPENAI_API_CONNECTION_ERROR)
_CONNECTION_ERROR_TYPES = tuple(_conn_errors)


def is_connection_error(exc: BaseException) -> bool:
    """Return True when *exc* is a known LLM connection failure (#1408)."""
    if not _CONNECTION_ERROR_TYPES:
        return False
    return isinstance(exc, _CONNECTION_ERROR_TYPES)


class StreamingPartialDeliveryError(Exception):
    """Raised when streaming delivered partial content to user then failed."""

    def __init__(self, sent_msg: Any, partial_text: str):
        self.sent_msg = sent_msg
        self.partial_text = partial_text
        super().__init__(f"Streaming failed after delivering {len(partial_text)} chars")


_DRAFT_INTERVAL = 0.2  # 200ms — sendMessageDraft has no rate limit


def _make_draft_id(chat_id: int) -> int:
    """Return a positive draft_id unique to this chat and moment."""
    raw = abs(hash(f"{chat_id}:{time.monotonic_ns()}")) % (2**31)
    return raw if raw != 0 else 1


def _coerce_positive_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        num = float(value)
        return num if num > 0 else None
    return None


def _extract_usage_details(usage: Any | None) -> dict[str, int] | None:
    if usage is None:
        return None
    details: dict[str, int] = {}
    for target_key, source_attr in (
        ("input", "prompt_tokens"),
        ("output", "completion_tokens"),
        ("total", "total_tokens"),
        ("input", "input_tokens"),
        ("output", "output_tokens"),
    ):
        if target_key in details:
            continue
        raw = getattr(usage, source_attr, None)
        value = _coerce_positive_number(raw)
        if value is not None:
            details[target_key] = int(value)
    return details or None


def _is_unsupported_name_kwarg(exc: TypeError) -> bool:
    message = str(exc)
    return "unexpected keyword argument" in message and "'name'" in message


async def _chat_create_with_optional_name(
    llm: Any,
    *,
    observation_name: str,
    **kwargs: Any,
) -> Any:
    create_fn = llm.chat.completions.create
    try:
        return await create_fn(name=observation_name, **kwargs)
    except TypeError as exc:
        if not _is_unsupported_name_kwarg(exc):
            raise
        logger.debug("LLM client does not support `name`; retrying without it")
        return await create_fn(**kwargs)


async def non_streaming_llm_call(
    *,
    llm: Any,
    config: Any,
    llm_messages: list[dict[str, str]],
    effective_temperature: float,
    max_tokens: int,
    prompt_obj: Any | None,
    sources_enabled: bool,
    sanitize_fn: Callable[[str, bool], str],
) -> tuple[str, str, float, float | None, dict[str, int] | None]:
    """Run a single non-streaming LLM call and return (answer, model, ttft_ms, completion_tokens, usage_details)."""
    t_start = time.monotonic()
    create_kwargs: dict[str, Any] = {
        "model": config.llm_model,
        "messages": llm_messages,
        "temperature": effective_temperature,
        "max_tokens": max_tokens,
        **config.get_reasoning_kwargs(),
    }
    response_obj = await _chat_create_with_optional_name(
        llm,
        observation_name="generate-answer",
        **create_kwargs,
    )
    t_end = time.monotonic()
    answer = response_obj.choices[0].message.content or ""
    answer = sanitize_fn(answer, sources_enabled)
    actual_model = getattr(response_obj, "model", config.llm_model) or config.llm_model
    ttft_ms = (t_end - t_start) * 1000
    usage = getattr(response_obj, "usage", None)
    usage_details: dict[str, int] | None = None
    completion_tokens: float | None = None
    if usage is not None:
        usage_details = _extract_usage_details(usage)
        completion_tokens = _coerce_positive_number(getattr(usage, "completion_tokens", None))
    return answer, actual_model, ttft_ms, completion_tokens, usage_details


def _build_streaming_request(
    llm_messages: list[dict[str, str]],
    config: Any,
    sanitize_response: Callable[[str], str] | None,
) -> GenerationRequest:
    query = ""
    if llm_messages:
        last_msg = llm_messages[-1]
        query = (
            last_msg.get("content", "")
            if isinstance(last_msg, dict)
            else getattr(last_msg, "content", "")
        )
        if "Вопрос:" in query:
            parts = query.split("Вопрос:")
            if len(parts) > 1:
                query = parts[1].split("\n")[0].strip()
    return GenerationRequest(
        query=query,
        documents=[],
        config=config,
        extra_kwargs={
            "sanitize_response": sanitize_response,
        },
    )


async def _handle_stream_error(
    message: Any,
    accumulated: str,
    sanitize_response: Callable[[str], str] | None,
) -> None:
    if not accumulated:
        return
    final_text = sanitize_response(accumulated) if sanitize_response else accumulated
    sent_msg = None
    with contextlib.suppress(Exception):
        sent_msg = await message.answer(
            format_answer_html(final_text),
            parse_mode="HTML",
            reply_parameters=build_reply_parameters(message, getattr(message, "text", "") or ""),
        )
    raise StreamingPartialDeliveryError(sent_msg, final_text) from None


async def _deliver_final_message(message: Any, final_text: str) -> Any:
    reply_parameters = build_reply_parameters(message, getattr(message, "text", "") or "")
    try:
        return await message.answer(
            format_answer_html(final_text),
            parse_mode="HTML",
            reply_parameters=reply_parameters,
        )
    except Exception:
        try:
            return await message.answer(final_text, reply_parameters=reply_parameters)
        except Exception:
            logger.warning("Failed to send final streaming message")
            return None


def _extract_stream_metadata(
    metadata_out: dict[str, Any],
    config: Any,
) -> tuple[str, float, float | None, dict[str, int] | None, int | None]:
    actual_model: str = metadata_out.get("llm_provider_model", config.llm_model)
    ttft_ms: float = metadata_out.get("llm_ttft_ms", 0.0)
    stream_only_ttft_ms: float | None = metadata_out.get("llm_stream_only_ttft_ms")
    usage_details: dict[str, int] | None = metadata_out.get("usage_details")
    completion_tokens: int | None = metadata_out.get("token_usage", {}).get("completion_tokens")
    if completion_tokens is None and usage_details:
        completion_tokens = usage_details.get("output")
    return actual_model, ttft_ms, stream_only_ttft_ms, usage_details, completion_tokens


async def generate_streaming(
    llm: Any,
    config: Any,
    llm_messages: list[dict[str, str]],
    message: Any,
    max_tokens: int = 0,
    temperature: float = 0.7,
    sanitize_response: Callable[[str], str] | None = None,
    *,
    request: GenerationRequest | None = None,
) -> tuple[str, str, float, float | None, float | None, dict[str, int] | None, Any]:
    """Stream LLM response to Telegram via native sendMessageDraft (Bot API 9.5)."""
    if request is None:
        request = _build_streaming_request(llm_messages, config, sanitize_response)

    accumulated = ""
    last_draft = 0.0
    chat_id = message.chat.id
    bot = message.bot
    draft_id = _make_draft_id(chat_id)

    metadata_out: dict[str, Any] = {}

    try:
        stream_gen = generate_answer_stream(request, metadata_out)
        async for chunk in stream_gen:
            accumulated += chunk
            now = time.monotonic()
            if now - last_draft >= _DRAFT_INTERVAL:
                with contextlib.suppress(Exception):
                    await bot.send_message_draft(
                        chat_id=chat_id, draft_id=draft_id, text=accumulated
                    )
                last_draft = now
    except Exception:
        await _handle_stream_error(message, accumulated, sanitize_response)
        raise

    if not accumulated:
        raise ValueError("Streaming produced empty response")

    final_text = sanitize_response(accumulated) if sanitize_response else accumulated
    sent_msg = await _deliver_final_message(message, final_text)

    actual_model, ttft_ms, stream_only_ttft_ms, usage_details, completion_tokens = (
        _extract_stream_metadata(metadata_out, config)
    )

    return (
        final_text,
        actual_model,
        ttft_ms,
        completion_tokens,
        stream_only_ttft_ms,
        usage_details,
        sent_msg,
    )


def _unpack_stream_result(
    stream_result: Any,
) -> tuple[str, str, float, float | None, float | None, dict[str, int] | None, Any]:
    if len(stream_result) == 5:
        answer, actual_model, ttft_ms, completion_tokens, sent_msg = stream_result
        stream_only_ttft_ms = None
        usage_details = None
    elif len(stream_result) == 6:
        answer, actual_model, ttft_ms, completion_tokens, stream_only_ttft_ms, sent_msg = (
            stream_result
        )
        usage_details = None
    else:
        (
            answer,
            actual_model,
            ttft_ms,
            completion_tokens,
            stream_only_ttft_ms,
            usage_details,
            sent_msg,
        ) = stream_result
    return (
        answer,
        actual_model,
        ttft_ms,
        completion_tokens,
        stream_only_ttft_ms,
        usage_details,
        sent_msg,
    )


@dataclasses.dataclass
class StreamResult:
    """Result of streaming LLM execution (happy path or recovery)."""

    answer: str
    actual_model: str
    ttft_ms: float
    completion_tokens: float | None
    stream_only_ttft_ms: float | None
    usage_details: dict[str, int] | None
    sent_msg: Any
    response_sent: bool
    stream_recovery: bool
    hard_timeout: bool


async def run_stream_with_recovery(
    *,
    req: GenerationRequest,
    ctx: Any,  # StreamingContext — avoid circular import
    config: Any,
    message: Any,
    build_fallback_response: Callable[[list[dict[str, Any]]], str],
    generate_streaming_fn: Callable[..., Any],
    sanitize_fn: Callable[[str, bool], str],
) -> StreamResult:
    """Stage 2: Execute stream, handle partial-delivery and full-failure recovery."""
    answer = ""
    actual_model = config.llm_model
    ttft_ms = 0.0
    stream_only_ttft_ms: float | None = None
    completion_tokens: float | None = None
    usage_details: dict[str, int] | None = None
    stream_recovery = False
    hard_timeout = False
    response_sent = False
    sent_msg: Any = None

    try:
        llm = config.create_llm(auto_trace=False)
        stream_kwargs: dict[str, Any] = {}
        params = inspect.signature(generate_streaming_fn).parameters
        if "request" in params:
            stream_kwargs["request"] = req
        if "temperature" in params:
            stream_kwargs["temperature"] = ctx.effective_temperature
        if "sanitize_response" in params:
            stream_kwargs["sanitize_response"] = lambda text: sanitize_fn(text, ctx.sources_enabled)

        stream_result = await generate_streaming_fn(
            llm,
            config,
            ctx.llm_messages,
            message,
            ctx.max_tokens,
            **stream_kwargs,
        )

        (
            answer,
            actual_model,
            ttft_ms,
            completion_tokens,
            stream_only_ttft_ms,
            usage_details,
            sent_msg,
        ) = _unpack_stream_result(stream_result)
        response_sent = sent_msg is not None

    except Exception as stream_exc:
        try:
            if hasattr(stream_exc, "sent_msg") and hasattr(stream_exc, "partial_text"):
                _partial_len = len(getattr(stream_exc, "partial_text", ""))
                if is_connection_error(stream_exc.__cause__ or stream_exc):
                    logger.warning(
                        "Streaming failed after partial delivery (%d chars) due to connection error, falling back to non-streaming",
                        _partial_len,
                    )
                else:
                    logger.warning(
                        "Streaming failed after partial delivery (%d chars), falling back to non-streaming with edit",
                        _partial_len,
                        exc_info=True,
                    )
                sent_msg = getattr(stream_exc, "sent_msg", None)
                (
                    answer,
                    actual_model,
                    ttft_ms,
                    completion_tokens,
                    usage_details,
                ) = await non_streaming_llm_call(
                    llm=llm,
                    config=config,
                    llm_messages=ctx.llm_messages,
                    effective_temperature=ctx.effective_temperature,
                    max_tokens=ctx.max_tokens,
                    prompt_obj=ctx.prompt_obj,
                    sources_enabled=ctx.sources_enabled,
                    sanitize_fn=sanitize_fn,
                )
                stream_recovery = True
                delivered = False
                if sent_msg is not None:
                    try:
                        await sent_msg.edit_text(format_answer_html(answer), parse_mode="HTML")
                        delivered = True
                    except Exception:
                        try:
                            await sent_msg.edit_text(answer)
                            delivered = True
                        except Exception:
                            logger.warning(
                                "Failed to edit partial streaming message; sending recovery answer as new message",
                                exc_info=True,
                            )
                if not delivered:
                    try:
                        sent_msg = await message.answer(
                            format_answer_html(answer),
                            parse_mode="HTML",
                            reply_parameters=build_reply_parameters(
                                message, getattr(message, "text", "") or ctx.effective_query
                            ),
                        )
                        delivered = True
                    except Exception:
                        try:
                            sent_msg = await message.answer(answer)
                            delivered = True
                        except Exception:
                            logger.warning(
                                "Failed to deliver fallback answer after partial stream; respond_node will send final answer",
                                exc_info=True,
                            )
                response_sent = delivered
            else:
                if is_connection_error(stream_exc):
                    logger.warning(
                        "Streaming failed due to connection error, falling back to non-streaming"
                    )
                else:
                    logger.warning("Streaming failed, falling back to non-streaming", exc_info=True)
                (
                    answer,
                    actual_model,
                    ttft_ms,
                    completion_tokens,
                    usage_details,
                ) = await non_streaming_llm_call(
                    llm=llm,
                    config=config,
                    llm_messages=ctx.llm_messages,
                    effective_temperature=ctx.effective_temperature,
                    max_tokens=ctx.max_tokens,
                    prompt_obj=ctx.prompt_obj,
                    sources_enabled=ctx.sources_enabled,
                    sanitize_fn=sanitize_fn,
                )
                stream_recovery = True
        except Exception as e:
            if is_connection_error(e):
                logger.warning(
                    "generate_response: LLM connection failed (%s), using fallback",
                    type(e).__name__,
                )
            else:
                logger.exception("generate_response: LLM call failed, using fallback")
            answer = build_fallback_response(ctx.docs)
            actual_model = "fallback"
            ttft_ms = 0.0
            completion_tokens = None
            usage_details = None
            stream_only_ttft_ms = None
            response_sent = False
            hard_timeout = True
            stream_recovery = False

    return StreamResult(
        answer=answer,
        actual_model=actual_model,
        ttft_ms=ttft_ms,
        completion_tokens=completion_tokens,
        stream_only_ttft_ms=stream_only_ttft_ms,
        usage_details=usage_details,
        sent_msg=sent_msg,
        response_sent=response_sent,
        stream_recovery=stream_recovery,
        hard_timeout=hard_timeout,
    )
