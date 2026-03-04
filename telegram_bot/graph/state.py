"""RAGState schema for LangGraph pipeline.

Defines the state passed between graph nodes and the initial state factory.
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


class RAGState(TypedDict):
    """State schema for the RAG LangGraph pipeline."""

    messages: Annotated[list, add_messages]
    user_id: int
    session_id: str
    query_type: str
    cache_hit: bool
    cached_response: str | None
    query_embedding: list[float] | None
    sparse_embedding: dict[str, Any] | None
    colbert_query: list[list[float]] | None
    documents: list[dict[str, Any]]
    documents_relevant: bool
    rewrite_count: int
    rewrite_effective: bool
    max_rewrite_attempts: int
    response: str
    latency_stages: dict[str, float]
    search_results_count: int
    rerank_applied: bool
    rerank_cache_hit: bool
    grade_confidence: float
    skip_rerank: bool
    response_sent: bool
    embeddings_cache_hit: bool
    search_cache_hit: bool
    score_improved: bool
    retrieval_backend_error: bool
    retrieval_error_type: str | None
    # Embedding resilience (#210)
    embedding_error: bool
    embedding_error_type: str | None
    rewrite_provider_model: str
    llm_provider_model: str
    llm_ttft_ms: float
    llm_response_duration_ms: float
    llm_stream_only_ttft_ms: float | None
    llm_ttft_drift_ms: float | None
    # Latency breakdown (#147)
    llm_decode_ms: float | None
    llm_tps: float | None
    llm_queue_ms: float | None
    llm_timeout: bool
    llm_stream_recovery: bool
    streaming_enabled: bool
    # Response length control (#129)
    response_style: str
    response_difficulty: str
    response_style_reasoning: str
    answer_words: int
    answer_chars: int
    answer_to_question_ratio: float
    # Voice transcription (#151)
    voice_audio: bytes | None
    voice_duration_s: float | None
    stt_text: str | None
    stt_duration_ms: float | None
    input_type: str  # "text" or "voice"
    # LLM-as-a-Judge evaluation context
    retrieved_context: list[dict[str, Any]]
    # Source attribution (#225)
    show_sources: bool
    sources_count: int
    # Content filtering (#227)
    guard_blocked: bool
    guard_reason: str | None
    # User feedback (#229)
    trace_id: str
    sent_message: dict[str, int] | None  # {"chat_id": int, "message_id": int}
    # Prompt injection defense (#226)
    injection_detected: bool
    injection_risk_score: float
    injection_pattern: str | None
    # Call limits (#374)
    llm_call_count: int
    max_llm_calls: int
    # End-to-end latency alignment (pre-agent + pipeline)
    pre_agent_ms: float
    e2e_latency_ms: float


def make_initial_state(user_id: int, session_id: str, query: str) -> dict[str, Any]:
    """Create initial state for a new RAG pipeline invocation."""
    return {
        "messages": [{"role": "user", "content": query}],
        "user_id": user_id,
        "session_id": session_id,
        "query_type": "",
        "cache_hit": False,
        "cached_response": None,
        "query_embedding": None,
        "sparse_embedding": None,
        "colbert_query": None,
        "documents": [],
        "documents_relevant": False,
        "rewrite_count": 0,
        "rewrite_effective": True,
        "max_rewrite_attempts": 1,
        "response": "",
        "latency_stages": {},
        "search_results_count": 0,
        "rerank_applied": False,
        "rerank_cache_hit": False,
        "grade_confidence": 0.0,
        "skip_rerank": False,
        "response_sent": False,
        "embeddings_cache_hit": False,
        "search_cache_hit": False,
        "score_improved": True,
        "retrieval_backend_error": False,
        "retrieval_error_type": None,
        # Embedding resilience (#210)
        "embedding_error": False,
        "embedding_error_type": None,
        "rewrite_provider_model": "",
        "llm_provider_model": "",
        "llm_ttft_ms": 0.0,
        "llm_response_duration_ms": 0.0,
        "llm_stream_only_ttft_ms": None,
        "llm_ttft_drift_ms": None,
        # Latency breakdown (#147)
        "llm_decode_ms": None,
        "llm_tps": None,
        "llm_queue_ms": None,
        "llm_timeout": False,
        "llm_stream_recovery": False,
        "streaming_enabled": False,
        # Response length control (#129)
        "response_style": "",
        "response_difficulty": "",
        "response_style_reasoning": "",
        "answer_words": 0,
        "answer_chars": 0,
        "answer_to_question_ratio": 0.0,
        # Voice transcription (#151)
        "voice_audio": None,
        "voice_duration_s": None,
        "stt_text": None,
        "stt_duration_ms": None,
        "input_type": "text",
        # LLM-as-a-Judge evaluation context
        "retrieved_context": [],
        # Source attribution (#225)
        "show_sources": False,
        "sources_count": 0,
        # Content filtering (#227)
        "guard_blocked": False,
        "guard_reason": None,
        # User feedback (#229)
        "trace_id": "",
        "sent_message": None,
        # Prompt injection defense (#226)
        "injection_detected": False,
        "injection_risk_score": 0.0,
        "injection_pattern": None,
        # Call limits (#374)
        "llm_call_count": 0,
        "max_llm_calls": 5,
        # End-to-end latency alignment
        "pre_agent_ms": 0.0,
        "e2e_latency_ms": 0.0,
    }
