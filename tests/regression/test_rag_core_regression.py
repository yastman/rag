"""Core RAG regression suite — guards the assistant retrieval/generation path.

Issue: #2624 — add small core RAG regression suite.

These tests are deterministic (no live services, no extras) and run in the
test-core tier.  They guard against regressions in:
  - grounded answer shape and retrieved_doc_ids wiring
  - no-data / no-fabrication path (empty retrieval)
  - cache-hit routing returning the cached response
  - error fallback shape (safe error text, error_type set)
  - latency_ms budget (field is populated and > 0)

Add this suite to make test-core by including tests/regression/ in that target.
"""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.regression

from unittest.mock import AsyncMock, patch

from src.core.contracts import (
    CoreDependencies,
)
from src.runtime.generation import GenerationResult


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_DOC_BEACH_STUDIO = {
    "content": "Sunny Beach studio 110000 EUR, sea view, pool.",
    "metadata": {
        "source_id": "sunny_beach_studio",
        "title": "Sunny Beach Studio",
        "url": "fixture://sunny_beach_studio",
    },
    "score": 0.92,
}

_DOC_SERVICES = {
    "content": "Cleaning service: 25 EUR, advance booking 48 hours.",
    "metadata": {
        "source_id": "services_cleaning",
        "title": "Services: Cleaning",
        "url": "fixture://services_cleaning",
    },
    "score": 0.88,
}


def _fake_deps() -> CoreDependencies:
    return CoreDependencies(
        cache=object(),
        embeddings=object(),
        sparse_embeddings=object(),
        qdrant=object(),
    )


def _rag_mock(docs: list[dict], *, cache_hit: bool = False, response: str = "") -> AsyncMock:
    return AsyncMock(
        return_value={
            "documents": docs,
            "cache_hit": cache_hit,
            "response": response,
            "search_results_count": len(docs),
            "rerank_applied": False,
            "query_type": "GENERAL",
        }
    )


def _gen_mock(text: str) -> AsyncMock:
    return AsyncMock(
        return_value=GenerationResult(
            payload={
                "response": text,
                "llm_provider_model": "test-model",
                "usage_details": {"input": 5, "output": 10},
            }
        )
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGroundedAnswer:
    """Grounded answer: retrieved docs surface in result."""

    @pytest.mark.asyncio
    async def test_retrieved_doc_ids_wired_from_rag_pipeline(self) -> None:
        """retrieved_doc_ids must contain the source_id from retrieved docs."""
        from src.core.assistant import run_assistant_request

        rag = _rag_mock([_DOC_BEACH_STUDIO])
        gen = _gen_mock("Sunny Beach Studio is 110 000 EUR.")

        with (
            patch("src.runtime.graph.nodes.classify.classify_query", return_value="GENERAL"),
            patch("src.runtime.pipeline.assistant_pipeline.rag_pipeline", rag),
            patch("src.runtime.pipeline.assistant_pipeline.generate_answer", gen),
        ):
            result = await run_assistant_request(
                "Найди студию у моря до 120000",
                collection="test_collection",
                dependencies=_fake_deps(),
                request_id="reg-grounded-001",
            )

        assert result.route == "rag_search"
        assert result.error_type is None
        assert "sunny_beach_studio" in result.retrieved_doc_ids
        assert result.documents_count == 1

    @pytest.mark.asyncio
    async def test_response_text_comes_from_generation(self) -> None:
        """response_text must be taken from the generation result, not raw rag output."""
        from src.core.assistant import run_assistant_request

        expected = "Студия стоит 110 000 EUR."
        rag = _rag_mock([_DOC_BEACH_STUDIO])
        gen = _gen_mock(expected)

        with (
            patch("src.runtime.graph.nodes.classify.classify_query", return_value="GENERAL"),
            patch("src.runtime.pipeline.assistant_pipeline.rag_pipeline", rag),
            patch("src.runtime.pipeline.assistant_pipeline.generate_answer", gen),
        ):
            result = await run_assistant_request(
                "Сколько стоит студия?",
                collection="test_collection",
                dependencies=_fake_deps(),
            )

        assert result.response_text == expected


class TestNoDataNoFabrication:
    """No-data path: empty retrieval must not fabricate facts."""

    @pytest.mark.asyncio
    async def test_empty_retrieval_route_still_rag_search(self) -> None:
        """Pipeline must complete with rag_search route even when no docs retrieved."""
        from src.core.assistant import run_assistant_request

        rag = _rag_mock([])
        gen = _gen_mock("Данных не найдено.")

        with (
            patch("src.runtime.graph.nodes.classify.classify_query", return_value="GENERAL"),
            patch("src.runtime.pipeline.assistant_pipeline.rag_pipeline", rag),
            patch("src.runtime.pipeline.assistant_pipeline.generate_answer", gen),
        ):
            result = await run_assistant_request(
                "Найди замок с вертолётной площадкой",
                collection="test_collection",
                dependencies=_fake_deps(),
            )

        assert result.route == "rag_search"
        assert result.documents_count == 0
        assert result.retrieved_doc_ids == []

    @pytest.mark.asyncio
    async def test_empty_retrieval_response_text_from_generation(self) -> None:
        """Even with no docs, response_text comes from generation (not fabricated inline)."""
        from src.core.assistant import run_assistant_request

        no_data_reply = "К сожалению, данных не найдено."
        rag = _rag_mock([])
        gen = _gen_mock(no_data_reply)

        with (
            patch("src.runtime.graph.nodes.classify.classify_query", return_value="GENERAL"),
            patch("src.runtime.pipeline.assistant_pipeline.rag_pipeline", rag),
            patch("src.runtime.pipeline.assistant_pipeline.generate_answer", gen),
        ):
            result = await run_assistant_request(
                "Найди что-то чего нет",
                collection="test_collection",
                dependencies=_fake_deps(),
            )

        assert result.response_text == no_data_reply


class TestCacheHitPath:
    """Cache hit: response served from cache, generation skipped."""

    @pytest.mark.asyncio
    async def test_pipeline_cache_hit_returns_cached_response(self) -> None:
        """When rag_pipeline signals cache_hit, result route is cache_hit."""
        from src.core.assistant import run_assistant_request

        cached_text = "Кэшированный ответ о студии."
        rag = _rag_mock([], cache_hit=True, response=cached_text)
        gen = _gen_mock("should not be called")

        with (
            patch("src.runtime.graph.nodes.classify.classify_query", return_value="GENERAL"),
            patch("src.runtime.pipeline.assistant_pipeline.rag_pipeline", rag),
            patch("src.runtime.pipeline.assistant_pipeline.generate_answer", gen),
        ):
            result = await run_assistant_request(
                "Найди студию у моря",
                collection="test_collection",
                dependencies=_fake_deps(),
            )

        assert result.route == "cache_hit"
        assert result.cache_hit is True
        assert result.response_text == cached_text

    @pytest.mark.asyncio
    async def test_pipeline_cache_hit_skips_generation(self) -> None:
        """generate_answer must NOT be called when cache_hit is True."""
        from src.core.assistant import run_assistant_request

        rag = _rag_mock([], cache_hit=True, response="cached")
        gen = AsyncMock(return_value=GenerationResult(payload={}))

        with (
            patch("src.runtime.graph.nodes.classify.classify_query", return_value="GENERAL"),
            patch("src.runtime.pipeline.assistant_pipeline.rag_pipeline", rag),
            patch("src.runtime.pipeline.assistant_pipeline.generate_answer", gen),
        ):
            await run_assistant_request(
                "Найди студию",
                collection="test_collection",
                dependencies=_fake_deps(),
            )

        gen.assert_not_awaited()


class TestErrorFallback:
    """Error fallback: dependency failure returns safe error shape."""

    @pytest.mark.asyncio
    async def test_rag_pipeline_exception_returns_error_result(self) -> None:
        """If rag_pipeline raises, result must have route=error and error_type set."""
        from src.core.assistant import run_assistant_request

        rag = AsyncMock(side_effect=RuntimeError("qdrant unavailable"))

        with (
            patch("src.runtime.graph.nodes.classify.classify_query", return_value="GENERAL"),
            patch("src.runtime.pipeline.assistant_pipeline.rag_pipeline", rag),
        ):
            result = await run_assistant_request(
                "Найди студию",
                collection="test_collection",
                dependencies=_fake_deps(),
            )

        assert result.route == "error"
        assert result.error_type == "dependency_failed"
        assert result.response_text != ""

    @pytest.mark.asyncio
    async def test_error_result_does_not_expose_internal_exception_message(self) -> None:
        """Safe error text must not leak raw exception detail to response_text."""
        from src.core.assistant import run_assistant_request

        rag = AsyncMock(side_effect=RuntimeError("secret-internal-detail-XYZ"))

        with (
            patch("src.runtime.graph.nodes.classify.classify_query", return_value="GENERAL"),
            patch("src.runtime.pipeline.assistant_pipeline.rag_pipeline", rag),
        ):
            result = await run_assistant_request(
                "Запрос",
                collection="test_collection",
                dependencies=_fake_deps(),
            )

        assert "secret-internal-detail-XYZ" not in result.response_text
        assert result.error_message is not None  # internal detail lives here


class TestLatencyBudget:
    """Latency budget: latency_ms is populated and within local tolerance."""

    @pytest.mark.asyncio
    async def test_latency_ms_populated_on_success(self) -> None:
        """AssistantResult.latency_ms must be > 0 on successful execution."""
        from src.core.assistant import run_assistant_request

        rag = _rag_mock([_DOC_BEACH_STUDIO])
        gen = _gen_mock("answer")

        with (
            patch("src.runtime.graph.nodes.classify.classify_query", return_value="GENERAL"),
            patch("src.runtime.pipeline.assistant_pipeline.rag_pipeline", rag),
            patch("src.runtime.pipeline.assistant_pipeline.generate_answer", gen),
        ):
            result = await run_assistant_request(
                "Сколько стоит студия?",
                collection="test_collection",
                dependencies=_fake_deps(),
            )

        assert result.latency_ms > 0

    @pytest.mark.asyncio
    async def test_latency_ms_populated_on_error(self) -> None:
        """AssistantResult.latency_ms must be > 0 even on error path."""
        from src.core.assistant import run_assistant_request

        rag = AsyncMock(side_effect=RuntimeError("fail"))

        with (
            patch("src.runtime.graph.nodes.classify.classify_query", return_value="GENERAL"),
            patch("src.runtime.pipeline.assistant_pipeline.rag_pipeline", rag),
        ):
            result = await run_assistant_request(
                "Запрос",
                collection="test_collection",
                dependencies=_fake_deps(),
            )

        assert result.latency_ms > 0

    @pytest.mark.asyncio
    async def test_local_mock_latency_under_budget_ms(self) -> None:
        """Mocked pipeline must complete within 500 ms (local mock budget)."""
        from src.core.assistant import run_assistant_request

        rag = _rag_mock([_DOC_BEACH_STUDIO])
        gen = _gen_mock("answer")

        with (
            patch("src.runtime.graph.nodes.classify.classify_query", return_value="GENERAL"),
            patch("src.runtime.pipeline.assistant_pipeline.rag_pipeline", rag),
            patch("src.runtime.pipeline.assistant_pipeline.generate_answer", gen),
        ):
            result = await run_assistant_request(
                "Тест",
                collection="test_collection",
                dependencies=_fake_deps(),
            )

        assert result.latency_ms < 500, (
            f"Mock pipeline latency {result.latency_ms}ms exceeds 500ms budget"
        )


class TestMultipleDocRetrieval:
    """Multiple documents: all source_ids surfaced in retrieved_doc_ids."""

    @pytest.mark.asyncio
    async def test_multiple_docs_all_ids_present(self) -> None:
        """All retrieved source_ids must appear in result.retrieved_doc_ids."""
        from src.core.assistant import run_assistant_request

        rag = _rag_mock([_DOC_BEACH_STUDIO, _DOC_SERVICES])
        gen = _gen_mock("Два результата найдено.")

        with (
            patch("src.runtime.graph.nodes.classify.classify_query", return_value="GENERAL"),
            patch("src.runtime.pipeline.assistant_pipeline.rag_pipeline", rag),
            patch("src.runtime.pipeline.assistant_pipeline.generate_answer", gen),
        ):
            result = await run_assistant_request(
                "Покажи всё",
                collection="test_collection",
                dependencies=_fake_deps(),
            )

        assert "sunny_beach_studio" in result.retrieved_doc_ids
        assert "services_cleaning" in result.retrieved_doc_ids
        assert result.documents_count == 2
