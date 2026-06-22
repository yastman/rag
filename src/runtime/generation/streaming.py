"""generate_answer_stream internals (#3015)."""

from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from src.adapters.llm.base import LLMConnectionError
from src.runtime.grounding.policy import should_safe_fallback

from .contracts import GenerationRequest
from .llm_call import _chat_create_with_optional_name
from .policy import (
    _build_fallback_response,
    _coerce_positive_number,
    _ensure_generation_signal_defaults,
    _extract_usage_details,
)
from .prompts import _build_prompt_and_messages, _format_generation_context
from .setup import _get_dynamic_modules, _resolve_generation_setup


logger = logging.getLogger(__name__)


def _apply_stream_safe_fallback(
    *,
    request: GenerationRequest,
    metadata_out: dict[str, Any],
    docs: list[dict[str, Any]],
    style_info: Any,
    dyn: dict[str, Any],
    extra: dict[str, Any],
    t0: float,
    needs_coverage: bool,
) -> str:
    """Apply the pre-stream strict-grounding safe fallback branch."""
    elapsed = time.monotonic() - t0
    with contextlib.suppress(Exception):
        dyn["PipelineMetrics"].get().record("generate", elapsed * 1000)
    answer: str = extra.get("build_fallback_response", _build_fallback_response)(docs)
    current_latency = request.latency_stages or {}
    metadata_out.update(
        _ensure_generation_signal_defaults(
            {
                "response": answer,
                "response_sent": False,
                "sent_message": None,
                "llm_provider_model": "safe_fallback",
                "llm_ttft_ms": 0.0,
                "llm_response_duration_ms": elapsed * 1000,
                "llm_stream_only_ttft_ms": None,
                "llm_ttft_drift_ms": None,
                "llm_call_count": max(0, int(request.llm_call_count)),
                "latency_stages": {**current_latency, "generate": elapsed},
                "llm_decode_ms": None,
                "llm_tps": None,
                "llm_queue_ms": None,
                "llm_timeout": False,
                "llm_stream_recovery": False,
                "streaming_enabled": True,
                "response_style": style_info.style,
                "response_difficulty": style_info.difficulty,
                "response_style_reasoning": style_info.reasoning,
                "answer_words": len(answer.split()),
                "answer_chars": len(answer),
                "answer_to_question_ratio": len(answer.split()) / max(style_info.word_count, 1),
                "response_policy_mode": "safe_fallback",
                "grounding_mode": request.grounding_mode,
                "safe_fallback_used": True,
                "grounded": False,
                "legal_answer_safe": False,
                "semantic_cache_safe_reuse": False,
                "needs_coverage": needs_coverage,
            }
        )
    )
    return answer


async def generate_answer_stream(
    request: GenerationRequest,
    metadata_out: dict[str, Any],
) -> AsyncIterator[str]:
    """Stream LLM response and output metadata upon completion."""
    t0 = time.monotonic()
    config = request.config
    extra = request.extra_kwargs or {}
    if config is None:
        raise ValueError("GenerationRequest.config must be set")

    extra.get("logger") or logging.getLogger(__name__)
    dyn = _get_dynamic_modules(extra)

    docs = request.documents or []
    raw_history = request.raw_messages or []

    setup = _resolve_generation_setup(request, dyn)
    effective_query = setup.effective_query
    style_info = setup.style_info
    needs_coverage = setup.needs_coverage
    sources_enabled = setup.sources_enabled
    legal_answer_safe = setup.legal_answer_safe

    if should_safe_fallback(
        grounding_mode=request.grounding_mode,
        documents=docs,
        sources_enabled=sources_enabled,
        grade_confidence=request.grade_confidence,
        legal_answer_safe=legal_answer_safe,
    ):
        answer = _apply_stream_safe_fallback(
            request=request,
            metadata_out=metadata_out,
            docs=docs,
            style_info=style_info,
            dyn=dyn,
            extra=extra,
            t0=t0,
            needs_coverage=needs_coverage,
        )
        yield answer
        return

    context = _format_generation_context(
        docs, needs_coverage=needs_coverage, sources_enabled=sources_enabled, extra=extra
    )
    pm = _build_prompt_and_messages(
        config=config,
        needs_coverage=needs_coverage,
        sources_enabled=sources_enabled,
        docs=docs,
        style_info=style_info,
        raw_history=raw_history,
        effective_query=effective_query,
        context=context,
        dyn=dyn,
        extra=extra,
    )
    max_tokens = pm.max_tokens
    response_policy_mode = pm.response_policy_mode
    effective_temperature = pm.effective_temperature
    llm_messages = pm.llm_messages

    actual_model = config.llm_model
    ttft_ms = 0.0
    stream_only_ttft_ms: float | None = None
    completion_tokens: float | None = None
    usage_details: dict[str, int] | None = None
    accumulated = ""
    llm = config.create_llm(auto_trace=False)
    t_request_start = time.monotonic()

    stream_create_kwargs: dict[str, Any] = {
        "model": config.llm_model,
        "messages": llm_messages,
        "temperature": effective_temperature,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
        **config.get_reasoning_kwargs(),
    }

    try:
        stream = await _chat_create_with_optional_name(
            llm,
            observation_name="generate-answer",
            **stream_create_kwargs,
        )
        t_stream_start = time.monotonic()

        async for chunk in stream:
            if hasattr(chunk, "usage") and chunk.usage is not None:
                chunk_usage = _extract_usage_details(chunk.usage)
                if chunk_usage:
                    usage_details = {**(usage_details or {}), **chunk_usage}
                maybe_tokens = _coerce_positive_number(
                    getattr(chunk.usage, "completion_tokens", None)
                )
                if maybe_tokens is not None:
                    completion_tokens = maybe_tokens

            if not getattr(chunk, "choices", None):
                continue

            delta = chunk.choices[0].delta
            text = delta.content if delta else None
            if not text:
                text = getattr(delta, "reasoning_content", None) or getattr(
                    delta, "reasoning", None
                )

            if text:
                if ttft_ms == 0.0:
                    first_token_at = time.monotonic()
                    ttft_ms = (first_token_at - t_request_start) * 1000
                    stream_only_ttft_ms = (first_token_at - t_stream_start) * 1000
                accumulated += text
                yield text

            if hasattr(chunk, "model") and chunk.model:
                actual_model = chunk.model
    except Exception as exc:
        from litellm.exceptions import APIConnectionError as _LiteLLMConnErr

        if isinstance(exc, _LiteLLMConnErr):
            logger.exception("LLM connection error during streaming: %s", exc)
            raise LLMConnectionError(str(exc), raw_error=exc) from exc
        raise

    if not accumulated:
        raise ValueError("Streaming produced empty response")

    elapsed = time.monotonic() - t0
    with contextlib.suppress(Exception):
        dyn["PipelineMetrics"].get().record("generate", elapsed * 1000)

    llm_decode_ms = (elapsed * 1000) - ttft_ms if ttft_ms > 0 else None
    if llm_decode_ms is not None and llm_decode_ms < 0:
        llm_decode_ms = 0.0

    llm_tps: float | None = None
    if completion_tokens is not None and llm_decode_ms is not None and llm_decode_ms > 0:
        llm_tps = completion_tokens / (llm_decode_ms / 1000)

    llm_ttft_drift_ms = (
        max(0.0, ttft_ms - stream_only_ttft_ms)
        if (stream_only_ttft_ms is not None and ttft_ms > 0)
        else None
    )

    answer_words = len(accumulated.split())
    answer_chars = len(accumulated)
    question_words = style_info.word_count
    ratio = answer_words / max(question_words, 1)

    current_latency = request.latency_stages or {}
    current_llm_calls = max(0, int(request.llm_call_count))

    metadata_out.update(
        _ensure_generation_signal_defaults(
            {
                "response": accumulated,
                "response_sent": False,
                "sent_message": None,
                "llm_provider_model": actual_model,
                "llm_ttft_ms": ttft_ms,
                "llm_response_duration_ms": elapsed * 1000,
                "llm_stream_only_ttft_ms": stream_only_ttft_ms,
                "llm_ttft_drift_ms": llm_ttft_drift_ms,
                "llm_call_count": current_llm_calls + 1,
                "latency_stages": {**current_latency, "generate": elapsed},
                "llm_decode_ms": llm_decode_ms,
                "llm_tps": llm_tps,
                "llm_queue_ms": None,
                "llm_timeout": False,
                "llm_stream_recovery": False,
                "streaming_enabled": True,
                "response_style": style_info.style,
                "response_difficulty": style_info.difficulty,
                "response_style_reasoning": style_info.reasoning,
                "answer_words": answer_words,
                "answer_chars": answer_chars,
                "answer_to_question_ratio": ratio,
                "response_policy_mode": response_policy_mode,
                "grounding_mode": request.grounding_mode,
                "safe_fallback_used": False,
                "grounded": True,
                "legal_answer_safe": legal_answer_safe,
                "semantic_cache_safe_reuse": legal_answer_safe,
                "needs_coverage": needs_coverage,
            }
        )
    )
