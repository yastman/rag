"""Tests for typed voice RAG API client."""

from __future__ import annotations

import pytest

from src.voice.rag_api_client import RagApiClient, RagApiClientError, RagQueryRequest


def test_query_request_payload_includes_optional_trace_id():
    req = RagQueryRequest(
        query="test",
        session_id="voice-1",
        langfuse_trace_id="trace-1",
    )
    payload = req.to_payload()
    assert payload["query"] == "test"
    assert payload["session_id"] == "voice-1"
    assert payload["channel"] == "voice"
    assert payload["langfuse_trace_id"] == "trace-1"


def test_query_request_payload_omits_empty_trace_id():
    req = RagQueryRequest(query="test", session_id="voice-1")
    payload = req.to_payload()
    assert "langfuse_trace_id" not in payload


async def test_search_knowledge_base_success(httpx_mock):
    client = RagApiClient(base_url="http://rag-api:8080")
    httpx_mock.add_response(
        url="http://rag-api:8080/query",
        method="POST",
        json={"response": "answer"},
    )

    answer = await client.search_knowledge_base(RagQueryRequest(query="q", session_id="s1"))
    assert answer == "answer"
    await client.close()


async def test_search_knowledge_base_http_error_raises_domain_error(httpx_mock):
    client = RagApiClient(base_url="http://rag-api:8080")
    httpx_mock.add_response(
        url="http://rag-api:8080/query",
        method="POST",
        status_code=500,
        json={"detail": "error"},
    )

    with pytest.raises(RagApiClientError):
        await client.search_knowledge_base(RagQueryRequest(query="q", session_id="s1"))
    await client.close()


async def test_client_property_reuses_shared_async_client():
    client = RagApiClient(base_url="http://rag-api:8080")
    first = client.client
    second = client.client
    assert first is second
    await client.close()


async def test_close_resets_client_instance():
    client = RagApiClient(base_url="http://rag-api:8080")
    old = client.client
    await client.close()
    new = client.client
    assert new is not old
    await client.close()
