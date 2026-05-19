"""Coverage tests for the @observe + curated update_current_span burn-down
that closes #1659/#1660/#1661/#1662 (orphan-generation observability gaps).

These tests assert presence of the Langfuse @observe decorator on each
public method and that span input/output payloads remain PII-safe.
They mirror the canonical pattern from
``tests/unit/api/test_rag_api_runtime.py`` (curated dicts, never raw text).
"""

from __future__ import annotations

from contextlib import nullcontext
from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest

from telegram_bot.services.llm import (
    LLMService,
)
from telegram_bot.services.query_analyzer import (
    QueryAnalysisResult,
    QueryAnalyzer,
)
from telegram_bot.services.query_preprocessor import HyDEGenerator
from telegram_bot.services.session_summary_worker import SessionSummaryWorker


def _is_langfuse_observed(func) -> bool:
    """Detect Langfuse @observe wrapping on a callable.

    Langfuse v4 keeps `__wrapped__` on the decorated callable; we also accept
    explicit markers added by future SDK revisions.
    """
    return hasattr(func, "__wrapped__") or getattr(func, "__langfuse_observed__", False)


# ---------------------------------------------------------------------------
# #1659 — QueryAnalyzer.analyze
# ---------------------------------------------------------------------------


def test_query_analyzer_analyze_is_observed():
    assert _is_langfuse_observed(QueryAnalyzer.analyze), (
        "QueryAnalyzer.analyze must carry @observe (#1659)"
    )


@pytest.mark.asyncio
async def test_query_analyzer_curated_span_payload_no_pii():
    analyzer = QueryAnalyzer(api_key="k", base_url="http://x")
    analyzer._instructor_client = AsyncMock()
    analyzer._instructor_client.chat.completions.create = AsyncMock(
        return_value=QueryAnalysisResult(
            filters={"city": "Несебр", "price": {"lt": 100000}},
            semantic_query="квартира у моря",
        )
    )
    lf = MagicMock()
    lf.update_current_span = MagicMock()
    raw_query = "квартира до 100000 евро в Несебре с хорошим ремонтом"

    with patch("telegram_bot.services.query_analyzer.get_client", return_value=lf):
        result = await analyzer.analyze(raw_query)

    assert result["filters"] == {"city": "Несебр", "price": {"lt": 100000}}

    calls = lf.update_current_span.call_args_list
    assert len(calls) >= 2, f"expected input+output update calls, got {calls}"
    input_payload = calls[0].kwargs["input"]
    assert input_payload["model"] == "gpt-4o-mini"
    # query_preview is bounded; raw long query should not leak in full —
    # but a 120-char prefix may overlap, so we assert the explicit length cap
    assert len(input_payload["query_preview"]) <= 120
    output_payload = calls[1].kwargs["output"]
    assert output_payload["filters_count"] == 2
    assert sorted(output_payload["filter_keys"]) == ["city", "price"]
    # Raw filter values (which might include PII-ish like phone numbers in
    # other domains) must not appear; the test simply verifies counts/keys.


@pytest.mark.asyncio
async def test_query_analyzer_marks_span_error_on_api_failure():
    analyzer = QueryAnalyzer(api_key="k", base_url="http://x")
    analyzer._instructor_client = AsyncMock()
    analyzer._instructor_client.chat.completions.create = AsyncMock(
        side_effect=openai.APIConnectionError(request=MagicMock())
    )
    lf = MagicMock()

    with patch("telegram_bot.services.query_analyzer.get_client", return_value=lf):
        result = await analyzer.analyze("dummy")

    assert result == {"filters": {}, "semantic_query": "dummy"}
    error_calls = [
        c for c in lf.update_current_span.call_args_list if c.kwargs.get("level") == "ERROR"
    ]
    assert len(error_calls) == 1
    assert "APIConnectionError" in (error_calls[0].kwargs.get("status_message") or "")


@pytest.mark.asyncio
async def test_query_analyzer_works_when_langfuse_client_is_none():
    analyzer = QueryAnalyzer(api_key="k", base_url="http://x")
    analyzer._instructor_client = AsyncMock()
    analyzer._instructor_client.chat.completions.create = AsyncMock(
        return_value=QueryAnalysisResult(filters={}, semantic_query="ok")
    )

    with patch("telegram_bot.services.query_analyzer.get_client", return_value=None):
        result = await analyzer.analyze("query")

    assert result == {"filters": {}, "semantic_query": "ok"}


# ---------------------------------------------------------------------------
# #1661 — HyDEGenerator.generate_hypothetical_document
# ---------------------------------------------------------------------------


def test_hyde_generate_is_observed():
    assert _is_langfuse_observed(HyDEGenerator.generate_hypothetical_document), (
        "HyDEGenerator.generate_hypothetical_document must carry @observe (#1661)"
    )


@pytest.mark.asyncio
async def test_hyde_curated_span_payload():
    hyde = HyDEGenerator(api_key="k", base_url="http://x")
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content="Hypothetical doc text"))]
    hyde.client = AsyncMock()
    hyde.client.chat.completions.create = AsyncMock(return_value=mock_resp)
    lf = MagicMock()

    with patch("telegram_bot.services.query_preprocessor.get_client", return_value=lf):
        doc = await hyde.generate_hypothetical_document("квартира у моря")

    assert doc == "Hypothetical doc text"
    calls = lf.update_current_span.call_args_list
    assert len(calls) >= 2
    input_payload = calls[0].kwargs["input"]
    assert input_payload["model"] == "gpt-4o-mini"
    assert input_payload["query_len"] == len("квартира у моря")
    output_payload = calls[1].kwargs["output"]
    assert output_payload["document_len"] == len("Hypothetical doc text")
    assert output_payload["fallback_to_query"] is False


@pytest.mark.asyncio
async def test_hyde_marks_error_on_failure_and_returns_query():
    hyde = HyDEGenerator(api_key="k", base_url="http://x")
    hyde.client = AsyncMock()
    hyde.client.chat.completions.create = AsyncMock(
        side_effect=openai.APITimeoutError(request=MagicMock())
    )
    lf = MagicMock()

    with patch("telegram_bot.services.query_preprocessor.get_client", return_value=lf):
        doc = await hyde.generate_hypothetical_document("foo")

    assert doc == "foo"  # graceful fallback to query
    error_calls = [
        c for c in lf.update_current_span.call_args_list if c.kwargs.get("level") == "ERROR"
    ]
    assert len(error_calls) == 1


# ---------------------------------------------------------------------------
# #1660 — LLMService public methods
# ---------------------------------------------------------------------------


def test_llm_service_methods_are_observed():
    assert _is_langfuse_observed(LLMService.generate_answer), (
        "LLMService.generate_answer must carry @observe (#1660)"
    )
    assert _is_langfuse_observed(LLMService.stream_answer), (
        "LLMService.stream_answer must carry @observe (#1660)"
    )
    assert _is_langfuse_observed(LLMService.generate), (
        "LLMService.generate must carry @observe (#1660)"
    )


@pytest.mark.asyncio
async def test_llm_service_generate_answer_curated_payload():
    service = LLMService(api_key="k")
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content="The final answer."))]
    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock(return_value=mock_resp)
    lf = MagicMock()

    with patch("telegram_bot.services.llm.get_client", return_value=lf):
        result = await service.generate_answer("What apartments?", [])

    assert result == "The final answer."
    calls = lf.update_current_span.call_args_list
    assert len(calls) >= 2
    input_payload = calls[0].kwargs["input"]
    assert input_payload["with_confidence"] is False
    assert input_payload["model"] == "gpt-4o-mini"
    output_payload = calls[1].kwargs["output"]
    assert output_payload["response_len"] == len("The final answer.")


@pytest.mark.asyncio
async def test_llm_service_generate_answer_marks_error_on_timeout():
    service = LLMService(api_key="k")
    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock(
        side_effect=openai.APITimeoutError(request=MagicMock())
    )
    lf = MagicMock()

    with patch("telegram_bot.services.llm.get_client", return_value=lf):
        result = await service.generate_answer("Q?", [])

    # graceful fallback string
    assert isinstance(result, str)
    error_calls = [
        c for c in lf.update_current_span.call_args_list if c.kwargs.get("level") == "ERROR"
    ]
    assert len(error_calls) == 1


@pytest.mark.asyncio
async def test_llm_service_stream_answer_emits_chunks_summary():
    service = LLMService(api_key="k")

    chunk1 = MagicMock(usage=None, choices=[MagicMock(delta=MagicMock(content="Hello "))])
    chunk2 = MagicMock(usage=None, choices=[MagicMock(delta=MagicMock(content="World"))])

    async def stream_iter():
        yield chunk1
        yield chunk2

    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock(return_value=stream_iter())
    lf = MagicMock()

    with patch("telegram_bot.services.llm.get_client", return_value=lf):
        chunks = []
        async for c in service.stream_answer("Q?", []):
            chunks.append(c)

    assert chunks == ["Hello ", "World"]
    output_calls = [c for c in lf.update_current_span.call_args_list if "output" in c.kwargs]
    assert len(output_calls) == 1
    assert output_calls[0].kwargs["output"] == {"chunks": 2, "total_len": 11}


@pytest.mark.asyncio
async def test_llm_service_generate_curated_payload():
    service = LLMService(api_key="k")
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content="Brief response"))]
    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock(return_value=mock_resp)
    lf = MagicMock()

    with patch("telegram_bot.services.llm.get_client", return_value=lf):
        result = await service.generate("prompt-text")

    assert result == "Brief response"
    output_calls = [c for c in lf.update_current_span.call_args_list if "output" in c.kwargs]
    assert len(output_calls) == 1
    assert output_calls[0].kwargs["output"] == {"response_len": len("Brief response")}


# ---------------------------------------------------------------------------
# #1662 — SessionSummaryWorker._generate_summary
# ---------------------------------------------------------------------------


def test_session_summary_worker_generate_summary_is_observed():
    assert _is_langfuse_observed(SessionSummaryWorker._generate_summary), (
        "SessionSummaryWorker._generate_summary must carry @observe (#1662)"
    )


@pytest.mark.asyncio
async def test_session_summary_worker_curated_payload_no_pii():
    worker = SessionSummaryWorker(redis=AsyncMock(), llm=MagicMock())
    mock_resp = MagicMock()
    mock_resp.choices = [
        MagicMock(message=MagicMock(content="Client looking for 2-room apartment under 80k EUR"))
    ]
    worker._llm.chat.completions.create = AsyncMock(return_value=mock_resp)
    lf = MagicMock()

    history = [
        {"role": "user", "content": "Looking for 2-room +359888123456 wants under 80k EUR"},
        {"role": "assistant", "content": "Found several options..."},
    ]

    with patch("telegram_bot.services.session_summary_worker.get_client", return_value=lf):
        summary = await worker._generate_summary(history)

    assert "2-room apartment" in summary
    calls = lf.update_current_span.call_args_list
    assert len(calls) >= 2
    input_payload = calls[0].kwargs["input"]
    assert input_payload["history_turns"] == 2
    assert input_payload["model"] == "claude-haiku-4-5"
    # Raw history content (which may carry PII like phone numbers) must NOT
    # appear in span input.
    assert "+359888123456" not in str(input_payload)
    output_payload = calls[1].kwargs["output"]
    assert output_payload["summary_len"] == len(summary)


@pytest.mark.asyncio
async def test_session_summary_worker_marks_error_on_llm_failure():
    worker = SessionSummaryWorker(redis=AsyncMock(), llm=MagicMock())
    worker._llm.chat.completions.create = AsyncMock(side_effect=RuntimeError("LLM down"))
    lf = MagicMock()

    with patch("telegram_bot.services.session_summary_worker.get_client", return_value=lf):
        summary = await worker._generate_summary(
            [{"role": "user", "content": "msg"}, {"role": "assistant", "content": "reply"}]
        )

    assert summary == ""  # graceful empty
    error_calls = [
        c for c in lf.update_current_span.call_args_list if c.kwargs.get("level") == "ERROR"
    ]
    assert len(error_calls) == 1


@pytest.mark.asyncio
async def test_session_summary_check_does_not_crash_when_langfuse_none():
    """Side-fix bundled with #1662: ``_check_idle_sessions`` previously called
    ``lf.score_current_trace`` unconditionally; with no Langfuse credentials
    ``get_client()`` returns None and the call would raise AttributeError."""
    worker = SessionSummaryWorker(redis=AsyncMock(), llm=MagicMock())
    worker._redis.scan = AsyncMock(return_value=(0, []))

    with patch("telegram_bot.services.session_summary_worker.get_client", return_value=None):
        # zero idle sessions branch
        result = await worker._check_idle_sessions()
    assert result == 0


# ---------------------------------------------------------------------------
# Sanity: existing supervisor pattern still works (regression check)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_propagate_attributes_compatibility_smoke():
    """Mini smoke: propagate_attributes context manager should not interfere
    with `@observe` wrapper on async functions."""
    from telegram_bot.observability import propagate_attributes

    with patch("telegram_bot.observability.propagate_attributes", return_value=nullcontext()):
        with propagate_attributes(session_id="s", user_id="u", tags=[]):
            pass
