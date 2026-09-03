"""Shared LLM response generation service for text/voice pipelines.

Public API: generate_response, GenerationDeps.
Internal implementation is split across:
  - _response_formatting.py  (context formatting, sanitization, fallback)
  - _streaming_context.py    (Stage 1: prompt/context assembly)
  - _stream_execution.py     (Stage 2: streaming delivery and recovery)
"""

from __future__ import annotations

import dataclasses
import logging
import time
from collections.abc import Callable
from typing import Any

from src.runtime.generation import GenerationRequest, generate_answer
from src.runtime.integrations.prompt_manager import (
    get_prompt,
    get_prompt_with_config,
    get_prompt_with_object,
)
from src.runtime.integrations.prompt_templates import (
    build_system_prompt_with_manager,
    get_token_limit,
)
from src.runtime.services.metrics import PipelineMetrics
from src.runtime.services.response_style_detector import ResponseStyleDetector

from ._response_formatting import (
    _MAX_CONTEXT_DOCS,
)
from ._response_formatting import (
    build_fallback_response as _build_fallback_response,
)
from ._response_formatting import (
    format_context as _format_context,
)
from ._response_formatting import (
    sanitize_response_text as _sanitize_response_text,
)
from ._stream_execution import (
    StreamResult,
)
from ._stream_execution import (
    generate_streaming as _generate_streaming,
)
from ._stream_execution import (
    run_stream_with_recovery as _run_stream_with_recovery,
)
from ._streaming_context import (
    _CITATION_INSTRUCTION,
    _GENERATE_FALLBACK,
    StreamingContext,
    _build_system_prompt_with_config,
)
from ._streaming_context import (
    ensure_history_instruction as _ensure_history_instruction,
)
from ._streaming_context import (
    prepare_streaming_context as _prepare_streaming_context,
)
from ._streaming_context import (
    select_recent_history as _select_recent_history,
)


logger = logging.getLogger(__name__)


def _extract_sent_message_ref(sent_msg: Any) -> dict[str, int] | None:
    """Build serializable Telegram message reference for checkpointer state."""
    chat = getattr(sent_msg, "chat", None)
    chat_id = getattr(chat, "id", None)
    message_id = getattr(sent_msg, "message_id", None)
    if isinstance(chat_id, int) and isinstance(message_id, int):
        return {"chat_id": chat_id, "message_id": message_id}
    return None


def _get_graph_config() -> Any:
    from src.runtime.config import GraphConfig

    return GraphConfig.from_env()


def _build_system_prompt(domain: str) -> str:
    return get_prompt("generate", fallback=_GENERATE_FALLBACK, variables={"domain": domain})


def _extract_queue_ms_from_provider_headers(response_obj: Any | None) -> float | None:
    """Return provider-reported queue time in ms, or None if unavailable/unreliable."""
    return None


def _ensure_generation_signal_defaults(result: dict[str, Any]) -> dict[str, Any]:
    """Normalize raw cacheability signals across every generation return path."""
    llm_provider_model = str(result.get("llm_provider_model", "") or "")
    result.setdefault("fallback_used", llm_provider_model == "fallback")
    result.setdefault("safe_fallback_used", False)
    result.setdefault("llm_timeout", False)
    return result


def _compute_latency_metrics(
    *,
    sr: StreamResult,
    elapsed_ms: float,
) -> tuple[float | None, float | None, float | None]:
    llm_decode_ms: float | None = elapsed_ms - sr.ttft_ms if sr.ttft_ms > 0 else None
    if llm_decode_ms is not None and llm_decode_ms < 0:
        llm_decode_ms = 0.0
    llm_tps: float | None = None
    if sr.completion_tokens is not None and llm_decode_ms is not None and llm_decode_ms > 0:
        llm_tps = sr.completion_tokens / (llm_decode_ms / 1000)
    llm_ttft_drift_ms: float | None = (
        max(0.0, sr.ttft_ms - sr.stream_only_ttft_ms)
        if (sr.stream_only_ttft_ms is not None and sr.ttft_ms > 0)
        else None
    )
    return llm_decode_ms, llm_tps, llm_ttft_drift_ms


def _build_generation_signal(
    *,
    ctx: StreamingContext,
    sr: StreamResult,
    t0: float,
    latency_stages: dict[str, float] | None,
    llm_call_count: int,
    grounding_mode: str,
    extract_sent_message_ref: Callable[[Any], dict[str, int] | None],
) -> dict[str, Any]:
    """Stage 3: Compute metrics, build and return result dict."""
    elapsed = time.monotonic() - t0
    PipelineMetrics.get().record("generate", elapsed * 1000)
    llm_decode_ms, llm_tps, llm_ttft_drift_ms = _compute_latency_metrics(
        sr=sr, elapsed_ms=elapsed * 1000
    )
    answer_words = len(sr.answer.split())
    answer_chars = len(sr.answer)
    ratio = answer_words / max(ctx.style_info.word_count, 1)
    sent_message_ref = (
        extract_sent_message_ref(sr.sent_msg)
        if sr.response_sent and sr.sent_msg is not None
        else None
    )
    current_latency = latency_stages or {}
    current_llm_calls = max(0, int(llm_call_count))
    return _ensure_generation_signal_defaults(
        {
            "response": sr.answer,
            "response_sent": sr.response_sent,
            "sent_message": sent_message_ref,
            "llm_provider_model": sr.actual_model,
            "llm_ttft_ms": sr.ttft_ms,
            "llm_response_duration_ms": elapsed * 1000,
            "llm_stream_only_ttft_ms": sr.stream_only_ttft_ms,
            "llm_ttft_drift_ms": llm_ttft_drift_ms,
            "llm_call_count": current_llm_calls + 1,
            "latency_stages": {**current_latency, "generate": elapsed},
            "llm_decode_ms": llm_decode_ms,
            "llm_tps": llm_tps,
            "llm_queue_ms": None,
            "llm_timeout": sr.hard_timeout,
            "llm_stream_recovery": sr.stream_recovery,
            "streaming_enabled": True,
            "response_style": ctx.style_info.style,
            "response_difficulty": ctx.style_info.difficulty,
            "response_style_reasoning": ctx.style_info.reasoning,
            "answer_words": answer_words,
            "answer_chars": answer_chars,
            "answer_to_question_ratio": ratio,
            "response_policy_mode": "coverage"
            if ctx.effective_needs_coverage
            else (
                "enforced"
                if (ctx.style_enabled and not ctx.shadow_mode)
                else ("shadow" if ctx.shadow_mode else "disabled")
            ),
            "grounding_mode": grounding_mode,
            "safe_fallback_used": False,
            "grounded": True,
            "legal_answer_safe": ctx.legal_answer_safe,
            "semantic_cache_safe_reuse": ctx.legal_answer_safe,
            "needs_coverage": ctx.effective_needs_coverage,
        }
    )


async def _generate_streaming_response(
    *,
    req: GenerationRequest,
    t0: float,
    query: str,
    needs_coverage: bool,
    documents: list[dict[str, Any]],
    raw_messages: list[Any] | None,
    latency_stages: dict[str, float] | None,
    llm_call_count: int,
    grounding_mode: str,
    grade_confidence: float | None,
    message: Any,
    config: Any,
    max_context_docs: int,
    format_context: Callable[..., str],
    select_recent_history: Callable[[list[Any], int], list[Any]],
    ensure_history_instruction: Callable[[str], str],
    build_fallback_response: Callable[[list[dict[str, Any]]], str],
    generate_streaming: Callable[..., Any],
    style_detector: ResponseStyleDetector | None,
    style_prompt_builder: Callable[..., str],
    style_token_limit: Callable[[Any, str], int],
    extract_sent_message_ref: Callable[[Any], dict[str, int] | None],
    citation_instruction: str,
) -> dict[str, Any]:
    """Generate and deliver a streaming Telegram response."""
    ctx = _prepare_streaming_context(
        query=query,
        needs_coverage=needs_coverage,
        documents=documents,
        raw_messages=raw_messages,
        grounding_mode=grounding_mode,
        grade_confidence=grade_confidence,
        config=config,
        max_context_docs=max_context_docs,
        format_context=format_context,
        select_recent_history=select_recent_history,
        ensure_history_instruction=ensure_history_instruction,
        style_detector=style_detector,
        style_prompt_builder=style_prompt_builder,
        style_token_limit=style_token_limit,
        citation_instruction=citation_instruction,
    )
    sr = await _run_stream_with_recovery(
        req=req,
        ctx=ctx,
        config=config,
        message=message,
        build_fallback_response=build_fallback_response,
        generate_streaming_fn=generate_streaming,
        sanitize_fn=lambda text, sources_enabled: _sanitize_response_text(
            text, sources_enabled=sources_enabled
        ),
    )
    return _build_generation_signal(
        ctx=ctx,
        sr=sr,
        t0=t0,
        latency_stages=latency_stages,
        llm_call_count=llm_call_count,
        grounding_mode=grounding_mode,
        extract_sent_message_ref=extract_sent_message_ref,
    )


@dataclasses.dataclass
class GenerationDeps:
    """Grouped injectable dependencies for generate_response (#2958)."""

    max_context_docs: int = _MAX_CONTEXT_DOCS
    format_context: Callable[..., str] = dataclasses.field(default_factory=lambda: _format_context)
    select_recent_history: Callable[[list[Any], int], list[Any]] = dataclasses.field(
        default_factory=lambda: _select_recent_history
    )
    build_system_prompt: Callable[[str], str] = dataclasses.field(
        default_factory=lambda: _build_system_prompt
    )
    ensure_history_instruction: Callable[[str], str] = dataclasses.field(
        default_factory=lambda: _ensure_history_instruction
    )
    build_fallback_response: Callable[[list[dict[str, Any]]], str] = dataclasses.field(
        default_factory=lambda: _build_fallback_response
    )
    generate_streaming: Callable[..., Any] = dataclasses.field(
        default_factory=lambda: _generate_streaming
    )
    style_detector: ResponseStyleDetector | None = None
    style_prompt_builder: Callable[..., str] = dataclasses.field(
        default_factory=lambda: build_system_prompt_with_manager
    )
    style_token_limit: Callable[[Any, str], int] = dataclasses.field(
        default_factory=lambda: get_token_limit
    )
    extract_queue_ms: Callable[[Any | None], float | None] = dataclasses.field(
        default_factory=lambda: _extract_queue_ms_from_provider_headers
    )
    extract_sent_message_ref: Callable[[Any], dict[str, int] | None] = dataclasses.field(
        default_factory=lambda: _extract_sent_message_ref
    )
    citation_instruction: str = _CITATION_INSTRUCTION


async def generate_response(
    *,
    query: str,
    needs_coverage: bool = False,
    documents: list[dict[str, Any]],
    retrieved_context: list[dict[str, Any]] | None = None,
    raw_messages: list[Any] | None = None,
    latency_stages: dict[str, float] | None = None,
    llm_call_count: int = 0,
    grounding_mode: str = "normal",
    grade_confidence: float | None = None,
    message: Any | None = None,
    config: Any | None = None,
    get_config: Callable[[], Any] | None = None,
    deps: GenerationDeps | None = None,
) -> dict[str, Any]:
    """Generate an LLM answer from retrieved context with optional Telegram streaming."""
    t0 = time.monotonic()
    d = deps if deps is not None else GenerationDeps()

    if config is None:
        config = get_config() if get_config is not None else _get_graph_config()

    req = GenerationRequest(
        query=query,
        documents=documents,
        retrieved_context=retrieved_context,
        raw_messages=raw_messages,
        latency_stages=latency_stages,
        llm_call_count=llm_call_count,
        grounding_mode=grounding_mode,
        grade_confidence=grade_confidence,
        config=config,
        extra_kwargs={
            "needs_coverage": needs_coverage,
            "max_context_docs": d.max_context_docs,
            "format_context": d.format_context,
            "select_recent_history": d.select_recent_history,
            "build_system_prompt": d.build_system_prompt,
            "ensure_history_instruction": d.ensure_history_instruction,
            "build_fallback_response": d.build_fallback_response,
            "style_detector": d.style_detector,
            "style_prompt_builder": d.style_prompt_builder,
            "style_token_limit": d.style_token_limit,
            "extract_queue_ms": d.extract_queue_ms,
            "citation_instruction": d.citation_instruction,
            "get_prompt": get_prompt,
            "get_prompt_with_config": get_prompt_with_config,
            "get_prompt_with_object": get_prompt_with_object,
            "logger": logger,
            "build_system_prompt_with_config": _build_system_prompt_with_config,
        },
    )

    if message is not None and config.streaming_enabled:
        return await _generate_streaming_response(
            req=req,
            t0=t0,
            query=query,
            needs_coverage=needs_coverage,
            documents=documents,
            raw_messages=raw_messages,
            latency_stages=latency_stages,
            llm_call_count=llm_call_count,
            grounding_mode=grounding_mode,
            grade_confidence=grade_confidence,
            message=message,
            config=config,
            max_context_docs=d.max_context_docs,
            format_context=d.format_context,
            select_recent_history=d.select_recent_history,
            ensure_history_instruction=d.ensure_history_instruction,
            build_fallback_response=d.build_fallback_response,
            generate_streaming=d.generate_streaming,
            style_detector=d.style_detector,
            style_prompt_builder=d.style_prompt_builder,
            style_token_limit=d.style_token_limit,
            extract_sent_message_ref=d.extract_sent_message_ref,
            citation_instruction=d.citation_instruction,
        )

    # Non-streaming path: directly call generate_answer()
    gen_res = await generate_answer(req)
    return gen_res.payload
