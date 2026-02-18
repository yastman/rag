"""Langfuse score-writing utilities shared by bot handler and RAG agent tool (***REMOVED***310).

Extracted from bot.py to avoid circular imports between bot.py and agents/rag_agent.py.
"""

from __future__ import annotations

from typing import Any


***REMOVED*** --- Query type mapping for scores ---
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


def write_langfuse_scores(lf: Any, result: dict) -> None:
    """Write Langfuse scores (14 + latency breakdown + 4 response length) from graph result state.

    Args:
        lf: Langfuse client (from get_client(), may be _NullLangfuseClient).
        result: State dict returned by graph.ainvoke().
    """
    latency_stages = result.get("latency_stages", {})
    total_ms = result.get("pipeline_wall_ms", 0.0)

    scores = {
        "query_type": _QUERY_TYPE_SCORE.get(result.get("query_type", ""), 1.0),
        "latency_total_ms": result.get("user_perceived_wall_ms", total_ms),
        "semantic_cache_hit": 1.0 if result.get("cache_hit") else 0.0,
        "embeddings_cache_hit": 1.0 if result.get("embeddings_cache_hit") else 0.0,
        "search_cache_hit": 1.0 if result.get("search_cache_hit") else 0.0,
        "rerank_applied": 1.0 if result.get("rerank_applied") else 0.0,
        "rerank_cache_hit": 0.0,  ***REMOVED*** Tracked when rerank cache implemented
        "results_count": float(result.get("search_results_count", 0)),
        "no_results": 1.0 if result.get("search_results_count", 0) == 0 else 0.0,
        "llm_used": 1.0 if "generate" in latency_stages else 0.0,
        "confidence_score": float(result.get("grade_confidence", 0.0)),
        "hyde_used": 0.0,  ***REMOVED*** HyDE not implemented in current pipeline
        "llm_ttft_ms": float(result.get("llm_ttft_ms", 0.0)),
        "llm_response_duration_ms": float(result.get("llm_response_duration_ms", 0.0)),
    }

    for name, value in scores.items():
        lf.score_current_trace(name=name, value=value)

    ***REMOVED*** --- Latency breakdown (***REMOVED***147) ---
    ***REMOVED*** Always-written BOOLEAN flags
    lf.score_current_trace(
        name="streaming_enabled",
        value=1 if result.get("streaming_enabled") else 0,
        data_type="BOOLEAN",
    )
    lf.score_current_trace(
        name="llm_timeout",
        value=1 if result.get("llm_timeout") else 0,
        data_type="BOOLEAN",
    )
    lf.score_current_trace(
        name="llm_stream_recovery",
        value=1 if result.get("llm_stream_recovery") else 0,
        data_type="BOOLEAN",
    )

    ***REMOVED*** Conditional NUMERIC + paired unavailable BOOLEAN flags
    decode_ms = result.get("llm_decode_ms")
    if decode_ms is not None:
        lf.score_current_trace(name="llm_decode_ms", value=float(decode_ms))
    else:
        lf.score_current_trace(name="llm_decode_unavailable", value=1, data_type="BOOLEAN")

    tps = result.get("llm_tps")
    if tps is not None:
        lf.score_current_trace(name="llm_tps", value=float(tps))
    else:
        lf.score_current_trace(name="llm_tps_unavailable", value=1, data_type="BOOLEAN")

    queue_ms = result.get("llm_queue_ms")
    if queue_ms is not None:
        lf.score_current_trace(name="llm_queue_ms", value=float(queue_ms))
    else:
        lf.score_current_trace(name="llm_queue_unavailable", value=1, data_type="BOOLEAN")

    ***REMOVED*** --- Response length control (***REMOVED***129) ---
    if "answer_words" in result:
        lf.score_current_trace(name="answer_words", value=float(result["answer_words"]))
    if "answer_chars" in result:
        lf.score_current_trace(name="answer_chars", value=float(result["answer_chars"]))
    if "answer_to_question_ratio" in result:
        lf.score_current_trace(
            name="answer_to_question_ratio",
            value=float(result["answer_to_question_ratio"]),
        )
    policy_mode = str(result.get("response_policy_mode", "disabled"))
    response_style = str(result.get("response_style", "")).strip()
    if response_style and policy_mode == "enforced":
        style_map = {"short": 0, "balanced": 1, "detailed": 2}
        lf.score_current_trace(
            name="response_style_applied",
            value=float(style_map.get(response_style, 1)),
        )

    ***REMOVED*** --- Voice transcription scores (***REMOVED***151) ---
    input_type = result.get("input_type", "text")
    lf.score_current_trace(name="input_type", value=input_type, data_type="CATEGORICAL")

    stt_ms = result.get("stt_duration_ms")
    if stt_ms is not None:
        lf.score_current_trace(name="stt_duration_ms", value=float(stt_ms))

    voice_dur = result.get("voice_duration_s")
    if voice_dur is not None:
        lf.score_current_trace(name="voice_duration_s", value=float(voice_dur))

    ***REMOVED*** --- Embedding resilience (***REMOVED***210) ---
    lf.score_current_trace(
        name="bge_embed_error",
        value=1 if result.get("embedding_error") else 0,
        data_type="BOOLEAN",
    )
    cache_check_s = result.get("latency_stages", {}).get("cache_check")
    if cache_check_s is not None:
        lf.score_current_trace(
            name="bge_embed_latency_ms",
            value=round(cache_check_s * 1000, 1),
        )

    ***REMOVED*** --- Conversation memory (***REMOVED***154, ***REMOVED***159) ---
    summarize_ms = result.get("latency_stages", {}).get("summarize", 0) * 1000
    if summarize_ms > 0:
        lf.score_current_trace(name="summarize_ms", value=summarize_ms)

    ***REMOVED*** Memory scores (***REMOVED***159)
    messages = result.get("messages", [])
    lf.score_current_trace(name="memory_messages_count", value=float(len(messages)))
    lf.score_current_trace(
        name="summarization_triggered",
        value=1 if summarize_ms > 0 else 0,
        data_type="BOOLEAN",
    )

    ***REMOVED*** Checkpointer overhead proxy (***REMOVED***159)
    if "checkpointer_overhead_proxy_ms" in result:
        lf.score_current_trace(
            name="checkpointer_overhead_proxy_ms",
            value=float(result["checkpointer_overhead_proxy_ms"]),
        )

    ***REMOVED*** --- Source attribution (***REMOVED***225) ---
    sources_count = int(result.get("sources_count", 0) or 0)
    lf.score_current_trace(
        name="sources_shown",
        value=1 if sources_count > 0 else 0,
        data_type="BOOLEAN",
    )
    if sources_count > 0:
        lf.score_current_trace(name="sources_count", value=float(sources_count))
