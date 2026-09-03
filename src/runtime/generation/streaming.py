"""generate_answer_stream internals (#3015)."""

from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from src.runtime.grounding.policy import should_safe_fallback
from src.runtime.llm import normalize_connection_error

from .contracts import GenerationRequest
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


def _update_chunk_usage(
    chunk: Any,
    usage_details: dict[str, int] | None,
    completion_tokens: float | None,
) -> tuple[dict[str, int] | None, float | None]:
    """Update usage_details and completion_tokens from a streaming chunk's usage field.

    Returns updated (usage_details, completion_tokens).
    """
    if not (hasattr(chunk, "usage") and chunk.usage is not None):
        return usage_details, completion_tokens
    chunk_usage = _extract_usage_details(chunk.usage)
    if chunk_usage:
        usage_details = {**(usage_details or {}), **chunk_usage}
    maybe_tokens = _coerce_positive_number(getattr(chunk.usage, "completion_tokens", None))
    if maybe_tokens is not None:
        completion_tokens = maybe_tokens
    return usage_details, completion_tokens


def _extract_chunk_text(chunk: Any) -> str | None:
    """Extract text content from a streaming chunk's delta, or None if absent."""
    if not getattr(chunk, "choices", None):
        return None
    delta = chunk.choices[0].delta
    text = delta.content if delta else None
    if not text:
        text = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
    return text or None


def _compute_stream_timing(
    *,
    ttft_ms: float,
    stream_only_ttft_ms: float | None,
    elapsed_ms: float,
    completion_tokens: float | None,
) -> tuple[float | None, float | None, float | None]:
    """Derive decode_ms, tps, and ttft_drift_ms from raw timing values.

    Returns (llm_decode_ms, llm_tps, llm_ttft_drift_ms).
    """
    llm_decode_ms: float | None = None
    if ttft_ms > 0:
        llm_decode_ms = max(0.0, elapsed_ms - ttft_ms)

    llm_tps: float | None = None
    if completion_tokens is not None and llm_decode_ms is not None and llm_decode_ms > 0:
        llm_tps = completion_tokens / (llm_decode_ms / 1000)

    llm_ttft_drift_ms: float | None = None
    if stream_only_ttft_ms is not None and ttft_ms > 0:
        llm_ttft_drift_ms = max(0.0, ttft_ms - stream_only_ttft_ms)

    return llm_decode_ms, llm_tps, llm_ttft_drift_ms


def _write_stream_metadata(
    *,
    request: GenerationRequest,
    metadata_out: dict[str, Any],
    accumulated: str,
    style_info: Any,
    actual_model: str,
    ttft_ms: float,
    stream_only_ttft_ms: float | None,
    elapsed: float,
    llm_decode_ms: float | None,
    llm_tps: float | None,
    llm_ttft_drift_ms: float | None,
    response_policy_mode: str,
    legal_answer_safe: bool,
    needs_coverage: bool,
) -> None:
    """Write final streaming metadata into metadata_out dict."""
    answer_words = len(accumulated.split())
    answer_chars = len(accumulated)
    ratio = answer_words / max(style_info.word_count, 1)
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
        stream = await llm.stream(
            observation_name="generate-answer",
            **stream_create_kwargs,
        )
        t_stream_start = time.monotonic()

        async for chunk in stream:
            usage_details, completion_tokens = _update_chunk_usage(
                chunk, usage_details, completion_tokens
            )
            text = _extract_chunk_text(chunk)
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
        normalized = normalize_connection_error(exc)
        if normalized is not None:
            logger.exception("LLM connection error during streaming: %s", exc)
            raise normalized from exc
        raise

    if not accumulated:
        raise ValueError("Streaming produced empty response")

    elapsed = time.monotonic() - t0
    with contextlib.suppress(Exception):
        dyn["PipelineMetrics"].get().record("generate", elapsed * 1000)

    llm_decode_ms, llm_tps, llm_ttft_drift_ms = _compute_stream_timing(
        ttft_ms=ttft_ms,
        stream_only_ttft_ms=stream_only_ttft_ms,
        elapsed_ms=elapsed * 1000,
        completion_tokens=completion_tokens,
    )

    _write_stream_metadata(
        request=request,
        metadata_out=metadata_out,
        accumulated=accumulated,
        style_info=style_info,
        actual_model=actual_model,
        ttft_ms=ttft_ms,
        stream_only_ttft_ms=stream_only_ttft_ms,
        elapsed=elapsed,
        llm_decode_ms=llm_decode_ms,
        llm_tps=llm_tps,
        llm_ttft_drift_ms=llm_ttft_drift_ms,
        response_policy_mode=response_policy_mode,
        legal_answer_safe=legal_answer_safe,
        needs_coverage=needs_coverage,
    )
