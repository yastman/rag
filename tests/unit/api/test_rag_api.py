"""Unit tests for RAG API schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.api.schemas import QueryRequest, QueryResponse


class TestQueryRequest:
    """Tests for QueryRequest schema."""

    def test_minimal_request(self):
        req = QueryRequest(query="test question")
        assert req.query == "test question"
        assert req.user_id == 0
        assert req.session_id == ""
        assert req.channel == "api"
        assert req.langfuse_trace_id is None

    def test_full_request(self):
        req = QueryRequest(
            query="test question",
            user_id=123,
            session_id="sess-1",
            channel="voice",
            langfuse_trace_id="trace-abc",
        )
        assert req.user_id == 123
        assert req.session_id == "sess-1"
        assert req.channel == "voice"
        assert req.langfuse_trace_id == "trace-abc"

    def test_empty_query_rejected(self):
        with pytest.raises(ValidationError):
            QueryRequest(query="")

    def test_query_too_long_rejected(self):
        with pytest.raises(ValidationError):
            QueryRequest(query="x" * 4097)

    def test_max_length_query_accepted(self):
        req = QueryRequest(query="x" * 4096)
        assert len(req.query) == 4096


class TestQueryResponse:
    """Tests for QueryResponse schema."""

    def test_minimal_response(self):
        resp = QueryResponse(response="answer text")
        assert resp.response == "answer text"
        assert resp.query_type == ""
        assert resp.cache_hit is False
        assert resp.documents_count == 0
        assert resp.rerank_applied is False
        assert resp.latency_ms == 0.0

    def test_full_response(self):
        resp = QueryResponse(
            response="answer",
            query_type="ENTITY",
            cache_hit=True,
            documents_count=5,
            rerank_applied=True,
            latency_ms=123.4,
        )
        assert resp.query_type == "ENTITY"
        assert resp.cache_hit is True
        assert resp.documents_count == 5
        assert resp.rerank_applied is True
        assert resp.latency_ms == 123.4

    def test_response_required(self):
        with pytest.raises(ValidationError):
            QueryResponse()  # type: ignore[call-arg]


class TestQueryResponseContext:
    """Test that QueryResponse includes retrieved context."""

    def test_context_field_default_empty(self):
        resp = QueryResponse(response="answer")
        assert resp.context == []

    def test_context_field_with_data(self):
        ctx = [{"content": "text", "score": 0.5, "chunk_location": "seq_3"}]
        resp = QueryResponse(response="answer", context=ctx)
        assert len(resp.context) == 1
        assert resp.context[0]["chunk_location"] == "seq_3"
