"""Observability helpers extracted from ``telegram_bot/bot.py`` (#1265 Slice 1 PR-2).

Two helpers used by both the text and voice handlers:

* :func:`_build_trace_metadata` — pure dict transform that flattens the
  per-query graph state into the metadata payload Langfuse expects.
* :func:`_write_voice_error_scores` — writes a minimal Langfuse score set
  on voice paths that exit early (transcription empty / recursion limit /
  pipeline failure). Voice dashboards rely on every voice trace carrying
  at least ``input_type=voice`` plus an error reason.

Both functions are byte-for-byte the bodies that previously lived in
``bot.py``; ``telegram_bot/bot.py`` re-exports them via thin wrappers so
existing callers (and the contract tests in
``tests/unit/observability/test_trace_contracts.py``) continue to resolve
``telegram_bot.bot._build_trace_metadata`` / ``_write_voice_error_scores``
to the same callable signature.

The module avoids ``aiogram`` / ``langgraph`` / ``fastapi`` imports so it
stays cheap to import and easy to unit-test in isolation.
"""

from __future__ import annotations

from typing import Any

from .scoring import score


def _build_trace_metadata(result: dict[str, Any]) -> dict[str, Any]:
    """Build shared metadata dict for Langfuse trace (text + voice handlers)."""
    return {
        "input_type": result.get("input_type", "text"),
        "query_type": result.get("query_type", ""),
        "topic_hint": result.get("topic_hint", ""),
        "grounding_mode": result.get("grounding_mode", ""),
        "grade_confidence": float(result.get("grade_confidence", 0.0) or 0.0),
        "pipeline_wall_ms": result.get("pipeline_wall_ms"),
        "pre_agent_ms": result.get("pre_agent_ms"),
        "e2e_latency_ms": result.get("e2e_latency_ms"),
        "cache_hit": result.get("cache_hit", False),
        "search_results_count": result.get("search_results_count", 0),
        "rerank_applied": result.get("rerank_applied", False),
        "llm_provider_model": result.get("llm_provider_model", ""),
        "llm_ttft_ms": result.get("llm_ttft_ms", 0.0),
        # Response length control (#129)
        "response_style": result.get("response_style"),
        "response_difficulty": result.get("response_difficulty"),
        "response_style_reasoning": result.get("response_style_reasoning"),
        "response_policy_mode": result.get("response_policy_mode"),
        "answer_words": result.get("answer_words"),
        "answer_to_question_ratio": result.get("answer_to_question_ratio"),
        "sources_count": int(result.get("sources_count", 0) or 0),
        "grounded": result.get("grounded", True),
        "legal_answer_safe": result.get("legal_answer_safe", True),
        "semantic_cache_safe_reuse": result.get("semantic_cache_safe_reuse", True),
        "safe_fallback_used": result.get("safe_fallback_used", False),
        # Voice transcription (#151)
        "stt_duration_ms": result.get("stt_duration_ms"),
        # Embedding resilience (#210)
        "embedding_error": result.get("embedding_error", False),
        "embedding_error_type": result.get("embedding_error_type"),
        # Conversation memory (#159)
        "memory_messages_count": len(result.get("messages", [])),
        "checkpointer_overhead_proxy_ms": result.get("checkpointer_overhead_proxy_ms"),
        # Voice post-pipeline cleanup diagnostics (#205)
        "pipeline_cleanup_error": result.get("pipeline_cleanup_error", False),
        "pipeline_cleanup_error_type": result.get("pipeline_cleanup_error_type"),
    }


def _write_voice_error_scores(
    lf: Any,
    *,
    trace_id: str = "",
    voice_duration_s: float | None = None,
    error_reason: str = "pipeline_error",
) -> None:
    """Write minimal Langfuse scores for voice traces that exit early (error paths).

    Ensures all voice traces have at least input_type and error context for dashboards.
    Uses explicit trace_id for score isolation (#435).
    """
    if not trace_id:
        trace_id = lf.get_current_trace_id()
    if not trace_id:
        return
    score(lf, trace_id, name="input_type", value="voice", data_type="CATEGORICAL")
    score(lf, trace_id, name="voice_error_reason", value=error_reason, data_type="CATEGORICAL")
    if voice_duration_s is not None:
        score(lf, trace_id, name="voice_duration_s", value=float(voice_duration_s))


__all__ = [
    "_build_trace_metadata",
    "_write_voice_error_scores",
]
