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
    documents: list[dict[str, Any]]
    documents_relevant: bool
    rewrite_count: int
    rewrite_effective: bool
    max_rewrite_attempts: int
    response: str
    latency_stages: dict[str, float]
    search_results_count: int
    rerank_applied: bool
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
    # User feedback (#229)
    trace_id: str
    sent_message: dict[str, int] | None  # {"chat_id": int, "message_id": int}


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
        "documents": [],
        "documents_relevant": False,
        "rewrite_count": 0,
        "rewrite_effective": True,
        "max_rewrite_attempts": 1,
        "response": "",
        "latency_stages": {},
        "search_results_count": 0,
        "rerank_applied": False,
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
        # User feedback (#229)
        "trace_id": "",
        "sent_message": None,
    }
