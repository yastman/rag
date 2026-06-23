"""Unit tests for src/api/schemas.py data models."""

import pytest
from pydantic import ValidationError

from src.api.schemas import QueryRequest, QueryResponse


class TestQueryRequest:
    def test_valid_request_minimal(self):
        req = QueryRequest(query="test query")
        assert req.query == "test query"
        assert req.user_id == 0
        assert req.session_id == ""
        assert req.channel == "api"
        assert req.langfuse_trace_id is None

    def test_valid_request_full(self):
        req = QueryRequest(
            query="квартиры в Несебр",
            user_id=12345,
            session_id="sess-abc",
            channel="telegram",
            langfuse_trace_id="trace-xyz",
        )
        assert req.query == "квартиры в Несебр"
        assert req.user_id == 12345
        assert req.session_id == "sess-abc"
        assert req.channel == "telegram"
        assert req.langfuse_trace_id == "trace-xyz"

    def test_query_min_length_1(self):
        with pytest.raises(ValidationError):
            QueryRequest(query="")

    def test_query_max_length_4096(self):
        with pytest.raises(ValidationError):
            QueryRequest(query="x" * 4097)

    def test_query_exactly_max_length_ok(self):
        req = QueryRequest(query="x" * 4096)
        assert len(req.query) == 4096

    def test_user_id_default(self):
        req = QueryRequest(query="test")
        assert req.user_id == 0

    def test_channel_default(self):
        req = QueryRequest(query="test")
        assert req.channel == "api"

    def test_langfuse_trace_id_optional(self):
        req = QueryRequest(query="test")
        assert req.langfuse_trace_id is None

        req2 = QueryRequest(query="test", langfuse_trace_id="trace-abc")
        assert req2.langfuse_trace_id == "trace-abc"


class TestQueryResponse:
    def test_valid_response_minimal(self):
        resp = QueryResponse(response="Ответ на вопрос")
        assert resp.response == "Ответ на вопрос"
        assert resp.query_type == ""
        assert resp.cache_hit is False
        assert resp.documents_count == 0
        assert resp.rerank_applied is False
        assert resp.latency_ms == 0.0
        assert resp.context == []

    def test_valid_response_full(self):
        context_docs = [{"text": "doc1", "score": 0.95}]
        resp = QueryResponse(
            response="Полный ответ",
            query_type="legal",
            cache_hit=True,
            documents_count=5,
            rerank_applied=True,
            latency_ms=350.5,
            context=context_docs,
        )
        assert resp.response == "Полный ответ"
        assert resp.query_type == "legal"
        assert resp.cache_hit is True
        assert resp.documents_count == 5
        assert resp.rerank_applied is True
        assert resp.latency_ms == 350.5
        assert resp.context == context_docs

    def test_response_required_field(self):
        with pytest.raises(ValidationError):
            QueryResponse()
