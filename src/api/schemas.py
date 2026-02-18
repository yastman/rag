"""Pydantic schemas for the RAG API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """POST /query request body."""

    query: str = Field(..., min_length=1, max_length=4096, description="User query text")
    user_id: int = Field(default=0, description="Optional user identifier")
    session_id: str = Field(default="", description="Optional session identifier")
    channel: str = Field(default="api", description="Source channel: api, voice, telegram")
    langfuse_trace_id: str | None = Field(
        default=None, description="Optional Langfuse trace ID for cross-trace linking"
    )


class QueryResponse(BaseModel):
    """POST /query response body."""

    response: str = Field(..., description="Generated answer")
    query_type: str = Field(default="", description="Classified query type")
    cache_hit: bool = Field(default=False, description="Whether semantic cache was hit")
    documents_count: int = Field(default=0, description="Number of retrieved documents")
    rerank_applied: bool = Field(default=False, description="Whether reranking was applied")
    latency_ms: float = Field(default=0.0, description="Total pipeline latency in milliseconds")
    context: list[dict] = Field(
        default_factory=list,
        description="Retrieved context documents (for evaluation)",
    )
