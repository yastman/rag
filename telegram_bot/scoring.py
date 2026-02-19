"""Langfuse score-writing utilities shared by bot handler and RAG agent tool (#310).

Extracted from bot.py to avoid circular imports between bot.py and agents/rag_agent.py.

All scores use create_score(trace_id=...) for explicit trace scoping (#435).
"""

from __future__ import annotations

from typing import Any


# --- Query type mapping for scores ---
_QUERY_TYPE_SCORE = {
    "CHITCHAT": 0.0,
    "OFF_TOPIC": 0.0,
    "SIMPLE": 1.0,
    "GENERAL": 1.0,
    "FAQ": 1.0,
    "ENTITY": 1.0,
    "STRUCTURED": 2.0,
    "COMPLEX": 2.0,
}


def compute_checkpointer_overhead_proxy_ms(result: dict[str, Any], ainvoke_wall_ms: float) -> float:
    """Compute proxy for checkpointer overhead: ainvoke wall-time minus sum of stage latencies.

    Returns max(0, delta) to clamp negative values from timing jitter.
    """
    stages_ms = sum(float(v) * 1000 for v in result.get("latency_stages", {}).values())
    return max(0.0, ainvoke_wall_ms - stages_ms)


def _score(lf: Any, trace_id: str, *, name: str, value: Any, **kwargs: Any) -> None:
    """Write a single score with explicit trace_id and idempotency key (#435)."""
    lf.create_score(
        trace_id=trace_id,
        name=name,
        value=value,
        id=f"{trace_id}-{name}",
        **kwargs,
    )


def write_langfuse_scores(lf: Any, result: dict, *, trace_id: str = "") -> None:
    """Write Langfuse scores from graph result state.

    All scores use create_score(trace_id=...) for explicit trace scoping (#435).

    Args:
        lf: Langfuse client (from get_client(), may be _NullLangfuseClient).
        result: State dict returned by graph.ainvoke().
        trace_id: Explicit trace ID for score isolation. Falls back to
            lf.get_current_trace_id() if empty.
    """
    if not trace_id:
        trace_id = lf.get_current_trace_id()
    if not trace_id:
        return  # No trace context — skip scoring

    latency_stages = result.get("latency_stages", {})
    total_ms = result.get("pipeline_wall_ms", 0.0)

    scores = {
        "query_type": _QUERY_TYPE_SCORE.get(result.get("query_type", ""), 1.0),
        "latency_total_ms": result.get("user_perceived_wall_ms", total_ms),
        "semantic_cache_hit": 1.0 if result.get("cache_hit") else 0.0,
        "embeddings_cache_hit": 1.0 if result.get("embeddings_cache_hit") else 0.0,
        "search_cache_hit": 1.0 if result.get("search_cache_hit") else 0.0,
        "rerank_applied": 1.0 if result.get("rerank_applied") else 0.0,
        "rerank_cache_hit": 0.0,  # Tracked when rerank cache implemented
        "results_count": float(result.get("search_results_count", 0)),
        "no_results": 1.0 if result.get("search_results_count", 0) == 0 else 0.0,
        "llm_used": 1.0 if "generate" in latency_stages else 0.0,
        "confidence_score": float(result.get("grade_confidence", 0.0)),
        "hyde_used": 0.0,  # HyDE not implemented in current pipeline
        "llm_ttft_ms": float(result.get("llm_ttft_ms", 0.0)),
        "llm_response_duration_ms": float(result.get("llm_response_duration_ms", 0.0)),
    }

    for name, value in scores.items():
        _score(lf, trace_id, name=name, value=value)

    # --- Latency breakdown (#147) ---
    # Always-written BOOLEAN flags
    _score(
        lf,
        trace_id,
        name="streaming_enabled",
        value=1 if result.get("streaming_enabled") else 0,
        data_type="BOOLEAN",
    )
    _score(
        lf,
        trace_id,
        name="llm_timeout",
        value=1 if result.get("llm_timeout") else 0,
        data_type="BOOLEAN",
    )
    _score(
        lf,
        trace_id,
        name="llm_stream_recovery",
        value=1 if result.get("llm_stream_recovery") else 0,
        data_type="BOOLEAN",
    )

    # Conditional NUMERIC + paired unavailable BOOLEAN flags
    decode_ms = result.get("llm_decode_ms")
    if decode_ms is not None:
        _score(lf, trace_id, name="llm_decode_ms", value=float(decode_ms))
    else:
        _score(lf, trace_id, name="llm_decode_unavailable", value=1, data_type="BOOLEAN")

    tps = result.get("llm_tps")
    if tps is not None:
        _score(lf, trace_id, name="llm_tps", value=float(tps))
    else:
        _score(lf, trace_id, name="llm_tps_unavailable", value=1, data_type="BOOLEAN")

    queue_ms = result.get("llm_queue_ms")
    if queue_ms is not None:
        _score(lf, trace_id, name="llm_queue_ms", value=float(queue_ms))
    else:
        _score(lf, trace_id, name="llm_queue_unavailable", value=1, data_type="BOOLEAN")

    # --- Response length control (#129) ---
    if "answer_words" in result:
        _score(lf, trace_id, name="answer_words", value=float(result["answer_words"]))
    if "answer_chars" in result:
        _score(lf, trace_id, name="answer_chars", value=float(result["answer_chars"]))
    if "answer_to_question_ratio" in result:
        _score(
            lf,
            trace_id,
            name="answer_to_question_ratio",
            value=float(result["answer_to_question_ratio"]),
        )
    policy_mode = str(result.get("response_policy_mode", "disabled"))
    response_style = str(result.get("response_style", "")).strip()
    if response_style and policy_mode == "enforced":
        style_map = {"short": 0, "balanced": 1, "detailed": 2}
        _score(
            lf,
            trace_id,
            name="response_style_applied",
            value=float(style_map.get(response_style, 1)),
        )

    # --- Voice transcription scores (#151) ---
    input_type = result.get("input_type", "text")
    _score(lf, trace_id, name="input_type", value=input_type, data_type="CATEGORICAL")

    stt_ms = result.get("stt_duration_ms")
    if stt_ms is not None:
        _score(lf, trace_id, name="stt_duration_ms", value=float(stt_ms))

    voice_dur = result.get("voice_duration_s")
    if voice_dur is not None:
        _score(lf, trace_id, name="voice_duration_s", value=float(voice_dur))

    # --- Embedding resilience (#210) ---
    _score(
        lf,
        trace_id,
        name="bge_embed_error",
        value=1 if result.get("embedding_error") else 0,
        data_type="BOOLEAN",
    )
    cache_check_s = result.get("latency_stages", {}).get("cache_check")
    if cache_check_s is not None:
        _score(
            lf,
            trace_id,
            name="bge_embed_latency_ms",
            value=round(cache_check_s * 1000, 1),
        )

    # --- Prompt injection defense (#226) ---
    _score(
        lf,
        trace_id,
        name="security_alert",
        value=1 if result.get("injection_detected") else 0,
        data_type="BOOLEAN",
    )
    injection_risk = float(result.get("injection_risk_score", 0.0) or 0.0)
    if injection_risk > 0:
        _score(lf, trace_id, name="injection_risk_score", value=injection_risk)
    injection_pattern = result.get("injection_pattern")
    if injection_pattern:
        _score(
            lf,
            trace_id,
            name="injection_pattern",
            value=str(injection_pattern),
            data_type="CATEGORICAL",
        )
    guard_ml_score = float(result.get("guard_ml_score", 0.0) or 0.0)
    if guard_ml_score > 0:
        _score(lf, trace_id, name="guard_ml_score", value=guard_ml_score)
    guard_ml_latency = float(result.get("guard_ml_latency_ms", 0.0) or 0.0)
    if guard_ml_latency > 0:
        _score(lf, trace_id, name="guard_ml_latency_ms", value=guard_ml_latency)
    _score(
        lf,
        trace_id,
        name="guard_ml_available",
        value=1 if guard_ml_latency > 0 else 0,
        data_type="BOOLEAN",
    )

    # --- Call limits (#374) ---
    llm_calls = result.get("llm_call_count", 0)
    if llm_calls > 0:
        _score(lf, trace_id, name="llm_calls_total", value=float(llm_calls))

    # --- Conversation memory (#154, #159) ---
    summarize_ms = result.get("latency_stages", {}).get("summarize", 0) * 1000
    if summarize_ms > 0:
        _score(lf, trace_id, name="summarize_ms", value=summarize_ms)

    # Memory scores (#159)
    messages = result.get("messages", [])
    _score(lf, trace_id, name="memory_messages_count", value=float(len(messages)))
    _score(
        lf,
        trace_id,
        name="summarization_triggered",
        value=1 if summarize_ms > 0 else 0,
        data_type="BOOLEAN",
    )

    # Checkpointer overhead proxy (#159)
    if "checkpointer_overhead_proxy_ms" in result:
        _score(
            lf,
            trace_id,
            name="checkpointer_overhead_proxy_ms",
            value=float(result["checkpointer_overhead_proxy_ms"]),
        )

    # --- Nurturing + funnel analytics (#390) ---
    if "nurturing_batch_size" in result:
        _score(
            lf, trace_id, name="nurturing_batch_size", value=float(result["nurturing_batch_size"])
        )
    if "nurturing_sent_count" in result:
        _score(
            lf, trace_id, name="nurturing_sent_count", value=float(result["nurturing_sent_count"])
        )
    if "funnel_conversion_rate" in result:
        _score(
            lf,
            trace_id,
            name="funnel_conversion_rate",
            value=float(result["funnel_conversion_rate"]),
        )
    if "funnel_dropoff_rate" in result:
        _score(lf, trace_id, name="funnel_dropoff_rate", value=float(result["funnel_dropoff_rate"]))

    # --- Source attribution (#225) ---
    sources_count = int(result.get("sources_count", 0) or 0)
    _score(
        lf,
        trace_id,
        name="sources_shown",
        value=1 if sources_count > 0 else 0,
        data_type="BOOLEAN",
    )
    if sources_count > 0:
        _score(lf, trace_id, name="sources_count", value=float(sources_count))


def write_crm_scores(lf: Any, messages: list, *, trace_id: str) -> None:
    """Write CRM tool usage scores from agent result messages (#440).

    Inspects ToolMessage objects for CRM tool calls (name starts with ``crm_``),
    counts successes vs errors, and writes 4 Langfuse scores.

    Args:
        lf: Langfuse client.
        messages: Agent result message list (HumanMessage, AIMessage, ToolMessage, ...).
        trace_id: Explicit trace ID for score isolation.
    """
    if not trace_id:
        return

    crm_total = 0
    crm_success = 0
    crm_error = 0

    for msg in messages:
        if getattr(msg, "type", None) != "tool":
            continue
        name = getattr(msg, "name", "") or ""
        if not name.startswith("crm_"):
            continue

        crm_total += 1
        content = getattr(msg, "content", "") or ""
        if "Ошибка при" in content or content == "CRM недоступен. Обратитесь к администратору.":
            crm_error += 1
        else:
            crm_success += 1

    _score(lf, trace_id, name="crm_tool_used", value=1 if crm_total > 0 else 0, data_type="BOOLEAN")
    _score(lf, trace_id, name="crm_tools_count", value=float(crm_total))
    _score(lf, trace_id, name="crm_tools_success", value=float(crm_success))
    _score(lf, trace_id, name="crm_tools_error", value=float(crm_error))
