"""Runtime generation service — thin coordinator and public entrypoints (#3015).

Helpers split into focused modules:
  messages.py  — history selection and LLM message assembly
  setup.py     — _GenerationSetup, _resolve_generation_setup, _get_dynamic_modules
  prompts.py   — _PromptConfig, _PromptAndMessages, prompt/message building
  streaming.py — generate_answer_stream and safe-fallback helper
"""

from __future__ import annotations

import contextlib
import logging
import time
from typing import Any

from src.runtime.grounding.policy import should_safe_fallback

from .contracts import GenerationCallable, GenerationRequest, GenerationResult
from .messages import (
    _build_llm_messages,  # noqa: F401 – re-export for tests
)
from .policy import (
    _build_fallback_response,
    _coerce_positive_number,
    _ensure_generation_signal_defaults,
    _extract_usage_details,
    _sanitize_response_text,
)
from .prompts import (
    _build_prompt_and_messages,
    _format_generation_context,
    _select_prompt_config,  # noqa: F401 – re-export for tests
)
from .setup import (
    _get_dynamic_modules,
    _resolve_generation_setup,
)
from .streaming import generate_answer_stream


logger = logging.getLogger(__name__)


async def generate_answer(
    request: GenerationRequest,
    *,
    generate: GenerationCallable | None = None,
) -> GenerationResult:
    """Generate an LLM answer from retrieved context using a transport-free request contract."""
    t0 = time.monotonic()

    config = request.config
    extra = request.extra_kwargs or {}
    if config is None:
        raise ValueError("GenerationRequest.config must be set")

    if generate is not None:
        res = await generate(
            query=request.query,
            documents=request.documents,
            retrieved_context=request.retrieved_context,
            raw_messages=request.raw_messages,
            latency_stages=request.latency_stages,
            llm_call_count=request.llm_call_count,
            grounding_mode=request.grounding_mode,
            grade_confidence=request.grade_confidence,
            config=config,
            **extra,
        )
        if isinstance(res, dict):
            return GenerationResult(payload=res)
        return res

    logger = extra.get("logger") or logging.getLogger(__name__)
    dyn = _get_dynamic_modules(extra)

    docs = request.documents or []
    raw_history = request.raw_messages or []

    setup = _resolve_generation_setup(request, dyn)
    effective_query = setup.effective_query
    style_info = setup.style_info
    needs_coverage = setup.needs_coverage
    sources_enabled = setup.sources_enabled
    legal_answer_safe = setup.legal_answer_safe

    context = _format_generation_context(
        docs, needs_coverage=needs_coverage, sources_enabled=sources_enabled, extra=extra
    )

    if should_safe_fallback(
        grounding_mode=request.grounding_mode,
        documents=docs,
        sources_enabled=sources_enabled,
        grade_confidence=request.grade_confidence,
        legal_answer_safe=legal_answer_safe,
    ):
        elapsed = time.monotonic() - t0
        with contextlib.suppress(Exception):
            dyn["PipelineMetrics"].get().record("generate", elapsed * 1000)
        answer = extra.get("build_fallback_response", _build_fallback_response)(docs)
        current_latency = request.latency_stages or {}
        return GenerationResult(
            payload=_ensure_generation_signal_defaults(
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
                    "streaming_enabled": False,
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
    response_obj: Any | None = None
    completion_tokens: float | None = None
    usage: Any | None = None
    hard_timeout = False

    try:
        llm = config.create_llm(auto_trace=False)
        t_llm_start_ns = time.perf_counter_ns()
        create_kwargs = {
            "model": config.llm_model,
            "messages": llm_messages,
            "temperature": effective_temperature,
            "max_tokens": max_tokens,
            **config.get_reasoning_kwargs(),
        }

        response_obj = await llm.completion(
            observation_name="generate-answer",
            **create_kwargs,
        )
        llm_elapsed_ns = max(time.perf_counter_ns() - t_llm_start_ns, 1)
        answer = response_obj.choices[0].message.content or ""
        sanitize_response = extra.get("sanitize_response") or (
            lambda t: _sanitize_response_text(t, sources_enabled=sources_enabled)
        )
        answer = sanitize_response(answer)
        actual_model = getattr(response_obj, "model", config.llm_model) or config.llm_model
        if not answer.strip():
            # #3360: content that is None, empty, whitespace-only, or emptied
            # by sanitization is not a grounded success. Reuse the terminal
            # fallback semantics so the caller always receives a sendable,
            # non-empty response that is never cached as reusable.
            logger.warning("generate_answer: empty provider output, using fallback")
            answer = extra.get("build_fallback_response", _build_fallback_response)(docs)
            actual_model = "fallback"
            ttft_ms = 0.0
            hard_timeout = True
        ttft_ms = llm_elapsed_ns / 1_000_000
        usage = getattr(response_obj, "usage", None)
        if usage is not None:
            completion_tokens = _coerce_positive_number(getattr(usage, "completion_tokens", None))

    except Exception as e:
        from .policy import _is_connection_error

        if _is_connection_error(e):
            logger.warning(
                "generate_answer: LLM connection failed (%s), using fallback", type(e).__name__
            )
        else:
            logger.exception("generate_answer: LLM call failed, using fallback")
        answer = extra.get("build_fallback_response", _build_fallback_response)(docs)
        actual_model = "fallback"
        ttft_ms = 0.0
        hard_timeout = True

    elapsed = time.monotonic() - t0
    with contextlib.suppress(Exception):
        dyn["PipelineMetrics"].get().record("generate", elapsed * 1000)

    llm_tps: float | None = None
    if ttft_ms > 0 and completion_tokens is not None:
        llm_tps = completion_tokens / (ttft_ms / 1000)

    llm_queue_ms: float | None = None
    extract_queue_ms = extra.get("extract_queue_ms")
    if extract_queue_ms is not None:
        llm_queue_ms = extract_queue_ms(response_obj)

    answer_words = len(answer.split())
    answer_chars = len(answer)
    question_words = style_info.word_count
    ratio = answer_words / max(question_words, 1)

    current_latency = request.latency_stages or {}
    current_llm_calls = max(0, int(request.llm_call_count))

    return GenerationResult(
        payload=_ensure_generation_signal_defaults(
            {
                "response": answer,
                "response_sent": False,
                "sent_message": None,
                "llm_provider_model": actual_model,
                "llm_ttft_ms": ttft_ms,
                "llm_response_duration_ms": elapsed * 1000,
                "llm_stream_only_ttft_ms": None,
                "llm_ttft_drift_ms": None,
                "llm_call_count": current_llm_calls + 1,
                "latency_stages": {**current_latency, "generate": elapsed},
                "llm_decode_ms": None,
                "llm_tps": llm_tps,
                "llm_queue_ms": llm_queue_ms,
                "llm_timeout": hard_timeout,
                "llm_stream_recovery": False,
                "streaming_enabled": False,
                "response_style": style_info.style,
                "response_difficulty": style_info.difficulty,
                "response_style_reasoning": style_info.reasoning,
                "answer_words": answer_words,
                "answer_chars": answer_chars,
                "answer_to_question_ratio": ratio,
                "response_policy_mode": response_policy_mode,
                "grounding_mode": request.grounding_mode,
                "safe_fallback_used": False,
                "grounded": actual_model != "fallback",
                "legal_answer_safe": legal_answer_safe,
                # #3360: provider model/usage are diagnostics, never proof of
                # grounded success — fallback results are never cache-safe.
                "semantic_cache_safe_reuse": (
                    legal_answer_safe if actual_model != "fallback" else False
                ),
                "needs_coverage": needs_coverage,
                "usage_details": _extract_usage_details(usage),
            }
        )
    )


# Make generate_answer_stream available from this module for backward compatibility
__all__ = ["generate_answer", "generate_answer_stream"]
