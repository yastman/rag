"""Unit tests for src.core.assistant — unified assistant entrypoint skeleton.

Covers PR A of #2336: dataclass definitions, request_id handling,
recoverable error shape, and import isolation from
Telegram / FastAPI / Langfuse / OTel.
"""

from __future__ import annotations

import importlib
import logging
from unittest.mock import AsyncMock, patch


# =============================================================================
# Import isolation — must pass BEFORE the module is imported by other tests.
# =============================================================================


def test_module_imports_no_telegram_or_fastapi() -> None:
    """The assistant module must not import Telegram, FastAPI, Langfuse, or OTel."""
    import src.core.assistant  # noqa: F401 — trigger first import

    mod_src = importlib.import_module("src.core.assistant")
    for forbidden in (
        "langfuse",
        "opentelemetry",
        "otel",
        "fastapi",
        "telegram",
        "aiogram",
    ):
        assert forbidden not in mod_src.__dict__, f"src.core.assistant must not import {forbidden}"


# =============================================================================
# UserContext
# =============================================================================


class TestUserContext:
    """Tests for the UserContext dataclass."""

    def test_defaults_are_empty(self) -> None:
        """All UserContext fields should have sensible defaults."""
        from src.core.assistant import UserContext

        ctx = UserContext()

        assert ctx.user_id == ""
        assert ctx.session_id == ""
        assert ctx.role == "client"
        assert ctx.filters is None
        assert ctx.language == "ru"

    def test_custom_values_accepted(self) -> None:
        """UserContext must accept custom values for all fields."""
        from src.core.assistant import UserContext

        ctx = UserContext(
            user_id="u-1",
            session_id="s-1",
            role="manager",
            filters={"city": "Sofia"},
            language="en",
        )

        assert ctx.user_id == "u-1"
        assert ctx.session_id == "s-1"
        assert ctx.role == "manager"
        assert ctx.filters == {"city": "Sofia"}
        assert ctx.language == "en"

    def test_is_standard_library_dataclass(self) -> None:
        """UserContext must be a stdlib @dataclass, not a Pydantic model."""
        from dataclasses import is_dataclass

        from src.core.assistant import UserContext

        assert is_dataclass(UserContext)
        assert not hasattr(UserContext, "model_validate")
        assert "pydantic" not in UserContext.__module__


# =============================================================================
# CoreDependencies
# =============================================================================


class TestCoreDependencies:
    """Tests for explicit runtime dependency injection."""

    def test_accepts_required_runtime_dependencies(self) -> None:
        """CoreDependencies should hold existing RAG runtime collaborators."""
        from src.core.assistant import CoreDependencies

        deps = CoreDependencies(
            cache=object(),
            embeddings=object(),
            sparse_embeddings=object(),
            qdrant=object(),
        )

        assert deps.cache is not None
        assert deps.embeddings is not None
        assert deps.sparse_embeddings is not None
        assert deps.qdrant is not None
        assert deps.reranker is None
        assert deps.llm is None
        assert deps.config is None


# =============================================================================
# AssistantResult
# =============================================================================


class TestAssistantResult:
    """Tests for the AssistantResult dataclass."""

    def test_defaults(self) -> None:
        """AssistantResult should have sensible defaults for optional fields."""
        from src.core.assistant import AssistantResult

        result = AssistantResult(response_text="")

        assert result.response_text == ""
        assert result.route == ""
        assert result.request_type == ""
        assert result.retrieved_doc_ids == []
        assert result.retrieved_sources == []
        assert result.documents_count == 0
        assert result.latency_ms == 0.0
        assert result.error_type is None
        assert result.error_message is None
        assert result.proposed_crm_action is None
        assert result.request_id == ""
        assert result.cache_hit is False
        assert result.llm_model is None
        assert result.llm_call_count == 0
        assert result.rerank_applied is False

    def test_error_type_and_message_set(self) -> None:
        """Error fields should be settable for recoverable error results."""
        from src.core.assistant import AssistantResult

        result = AssistantResult(
            response_text="",
            route="error",
            error_type="llm_timeout",
            error_message="LLM request timed out after 30s",
        )

        assert result.error_type == "llm_timeout"
        assert result.error_message == "LLM request timed out after 30s"
        assert result.route == "error"

    def test_crm_action_set(self) -> None:
        """proposed_crm_action should accept a CrmAction dataclass instance."""
        from src.core.assistant import AssistantResult, CrmAction

        action = CrmAction(
            action_type="create_lead",
            payload={"client": "Alice"},
            summary="Create lead for Alice",
        )
        result = AssistantResult(
            response_text="",
            proposed_crm_action=action,
        )

        assert result.proposed_crm_action is action
        assert result.proposed_crm_action.action_type == "create_lead"

    def test_is_standard_library_dataclass(self) -> None:
        """AssistantResult must be a stdlib @dataclass, not Pydantic."""
        from dataclasses import is_dataclass

        from src.core.assistant import AssistantResult

        assert is_dataclass(AssistantResult)
        assert not hasattr(AssistantResult, "model_validate")

    def test_all_fields_accessible(self) -> None:
        """Every field defined in the design contract must be accessible."""
        from src.core.assistant import AssistantResult

        result = AssistantResult(
            response_text="Hello",
            route="rag_search",
            request_type="GENERAL",
            retrieved_doc_ids=["doc-1"],
            retrieved_sources=[{"url": "http://x", "title": "X"}],
            documents_count=1,
            latency_ms=42.5,
            error_type=None,
            error_message=None,
            proposed_crm_action=None,
            request_id="req-1",
            cache_hit=True,
            llm_model="gpt-4o-mini",
            llm_call_count=1,
            rerank_applied=True,
        )

        assert result.response_text == "Hello"
        assert result.route == "rag_search"
        assert result.request_type == "GENERAL"
        assert result.retrieved_doc_ids == ["doc-1"]
        assert result.retrieved_sources == [{"url": "http://x", "title": "X"}]
        assert result.documents_count == 1
        assert result.latency_ms == 42.5
        assert result.error_type is None
        assert result.error_message is None
        assert result.proposed_crm_action is None
        assert result.request_id == "req-1"
        assert result.cache_hit is True
        assert result.llm_model == "gpt-4o-mini"
        assert result.llm_call_count == 1
        assert result.rerank_applied is True


# =============================================================================
# CrmAction
# =============================================================================


class TestCrmAction:
    """Tests for the CrmAction dataclass."""

    def test_creation(self) -> None:
        """CrmAction must accept action_type, payload, and summary."""
        from src.core.assistant import CrmAction

        action = CrmAction(
            action_type="create_lead",
            payload={"name": "John", "source": "telegram"},
            summary="Create lead for John (Telegram)",
        )

        assert action.action_type == "create_lead"
        assert action.payload == {"name": "John", "source": "telegram"}
        assert action.summary == "Create lead for John (Telegram)"

    def test_is_standard_library_dataclass(self) -> None:
        """CrmAction must be a stdlib @dataclass."""
        from dataclasses import is_dataclass

        from src.core.assistant import CrmAction

        assert is_dataclass(CrmAction)
        assert not hasattr(CrmAction, "model_validate")


# =============================================================================
# AssistantError
# =============================================================================


class TestAssistantError:
    """Tests for the AssistantError exception class."""

    def test_is_runtime_error(self) -> None:
        """AssistantError must inherit from RuntimeError."""
        from src.core.assistant import AssistantError

        err = AssistantError("fatal config error")
        assert isinstance(err, RuntimeError)

    def test_default_error_type(self) -> None:
        """AssistantError should default error_type to 'internal'."""
        from src.core.assistant import AssistantError

        err = AssistantError("something went wrong")
        assert err.error_type == "internal"

    def test_custom_error_type(self) -> None:
        """AssistantError must accept a custom error_type."""
        from src.core.assistant import AssistantError

        err = AssistantError("no qdrant client", error_type="qdrant_unavailable")
        assert err.error_type == "qdrant_unavailable"

    def test_message_stored(self) -> None:
        """AssistantError must store the message via the parent init."""
        from src.core.assistant import AssistantError

        err = AssistantError("fatal error")
        assert str(err) == "fatal error"


# =============================================================================
# run_assistant_request — skeleton validation
# =============================================================================


class TestRunAssistantRequest:
    """Tests for the async run_assistant_request() skeleton."""

    def test_is_async_function(self) -> None:
        """run_assistant_request must be an async function."""
        import inspect

        from src.core.assistant import run_assistant_request

        assert inspect.iscoroutinefunction(run_assistant_request), (
            "run_assistant_request must be async def"
        )

    async def test_generates_request_id_when_none(self) -> None:
        """When request_id is not provided, a fresh UUID4 must be generated."""
        from src.core.assistant import run_assistant_request

        result = await run_assistant_request("hello", collection="test")

        assert result.request_id != ""
        assert len(result.request_id) == 36  # standard UUID4 string length
        assert result.request_id.count("-") == 4

    async def test_preserves_caller_request_id(self) -> None:
        """When request_id is provided by the caller, it must be preserved."""
        from src.core.assistant import run_assistant_request

        result = await run_assistant_request("hello", collection="test", request_id="e2e-beach-001")

        assert result.request_id == "e2e-beach-001"

    async def test_two_calls_produce_different_request_ids(self) -> None:
        """Two calls without explicit request_id must produce different UUIDs."""
        from src.core.assistant import run_assistant_request

        r1 = await run_assistant_request("q1", collection="test")
        r2 = await run_assistant_request("q2", collection="test")

        assert r1.request_id != r2.request_id

    async def test_returns_structured_result(self) -> None:
        """The skeleton must return a valid AssistantResult, not raise."""
        from src.core.assistant import AssistantResult, run_assistant_request

        result = await run_assistant_request("test query", collection="my_collection")

        assert isinstance(result, AssistantResult)

    async def test_skeleton_returns_recoverable_error(self) -> None:
        """Skeleton execution must return AssistantResult with error fields set."""
        from src.core.assistant import run_assistant_request

        result = await run_assistant_request(
            "any query", collection="any_collection", user_context=None
        )

        # Skeleton: no live services, so the result is a recoverable error.
        assert result.route == "error"
        assert result.error_type is not None
        assert result.error_message is not None
        # response_text must still have a value; no exception raised.
        assert isinstance(result.response_text, str)

    async def test_pass_user_context(self) -> None:
        """UserContext is accepted without error."""
        from src.core.assistant import UserContext, run_assistant_request

        ctx = UserContext(user_id="u-1", session_id="s-1")
        result = await run_assistant_request("q", collection="c", user_context=ctx)

        assert isinstance(result.response_text, str)


# =============================================================================
# log_event integration — testable without live dependencies
# =============================================================================


class TestLogEventIntegration:
    """Verify that the skeleton emits product events via log_event."""

    async def test_skeleton_emits_started_event(self, caplog) -> None:
        """The assistant_request_started event must appear in logs."""
        from src.core.assistant import run_assistant_request

        with caplog.at_level(logging.INFO, logger="src.utils.product_events"):
            await run_assistant_request("hello", collection="test")

        events = [
            r
            for r in caplog.records
            if hasattr(r, "event") and r.event == "assistant_request_started"
        ]
        assert len(events) == 1

    async def test_skeleton_emits_completed_event(self, caplog) -> None:
        """The assistant_request_completed event must appear in logs."""
        from src.core.assistant import run_assistant_request

        with caplog.at_level(logging.INFO, logger="src.utils.product_events"):
            await run_assistant_request("q", collection="c")

        events = [
            r
            for r in caplog.records
            if hasattr(r, "event") and r.event == "assistant_request_completed"
        ]
        assert len(events) == 1

    async def test_event_includes_request_id(self, caplog) -> None:
        """Both events must carry the same request_id."""
        from src.core.assistant import run_assistant_request

        with caplog.at_level(logging.INFO, logger="src.utils.product_events"):
            result = await run_assistant_request("q", collection="c", request_id="e2e-001")

        for r in caplog.records:
            if hasattr(r, "event"):
                assert getattr(r, "request_id", None) == result.request_id

    async def test_started_event_includes_route(self, caplog) -> None:
        """The started event should include route for contract-compatible logs."""
        from src.core.assistant import run_assistant_request

        with caplog.at_level(logging.INFO, logger="src.utils.product_events"):
            await run_assistant_request("q", collection="c", request_id="e2e-route")

        started = next(
            r
            for r in caplog.records
            if hasattr(r, "event") and r.event == "assistant_request_started"
        )
        assert getattr(started, "route", None) == "unknown"


# =============================================================================
# run_assistant_request — dependency-backed runtime
# =============================================================================


class TestRunAssistantRequestRuntime:
    """Tests for the real Stage 2 runtime branch with mocked dependencies."""

    def _deps(self):
        from src.core.assistant import CoreDependencies

        return CoreDependencies(
            cache=object(),
            embeddings=object(),
            sparse_embeddings=object(),
            qdrant=object(),
            reranker=object(),
            llm=object(),
            config=object(),
        )

    async def test_calls_existing_rag_and_generation_pipeline(self) -> None:
        """Runtime branch must reuse existing rag_pipeline and generate_response."""
        from src.core.assistant import UserContext, run_assistant_request

        docs = [
            {
                "content": "Sunny Beach studio costs 110000 EUR.",
                "metadata": {
                    "source_id": "sunny_beach_studio",
                    "title": "Sunny Beach Studio",
                    "url": "fixture://sunny_beach_studio",
                },
                "score": 0.91,
            }
        ]
        rag = AsyncMock(
            return_value={
                "documents": docs,
                "cache_hit": False,
                "search_results_count": 1,
                "rerank_applied": True,
                "query_type": "GENERAL",
            }
        )
        gen = AsyncMock(
            return_value={
                "response": "Sunny Beach Studio is available for 110000 EUR.",
                "llm_provider_model": "gpt-4o-mini",
                "usage_details": {"input": 10, "output": 12},
            }
        )
        deps = self._deps()

        with (
            patch("src.runtime.graph.nodes.classify.classify_query", return_value="GENERAL"),
            patch("telegram_bot.agents.rag_pipeline.rag_pipeline", rag),
            patch("telegram_bot.services.generate_response.generate_response", gen),
        ):
            result = await run_assistant_request(
                "Найди студию у моря до 120000",
                collection="e2e_core_abc",
                user_context=UserContext(
                    user_id="42", session_id="s-1", filters={"city": "Sunny Beach"}
                ),
                request_id="e2e-beach",
                dependencies=deps,
            )

        rag.assert_awaited_once()
        rag_kwargs = rag.await_args.kwargs
        assert rag_kwargs["query"] == "Найди студию у моря до 120000"
        assert rag_kwargs["user_id"] == 42
        assert rag_kwargs["session_id"] == "s-1"
        assert rag_kwargs["query_type"] == "GENERAL"
        assert rag_kwargs["cache"] is deps.cache
        assert rag_kwargs["embeddings"] is deps.embeddings
        assert rag_kwargs["sparse_embeddings"] is deps.sparse_embeddings
        assert rag_kwargs["qdrant"] is deps.qdrant
        assert rag_kwargs["reranker"] is deps.reranker
        assert rag_kwargs["llm"] is deps.llm
        assert rag_kwargs["state_contract"]["filters"] == {"city": "Sunny Beach"}

        gen.assert_awaited_once()
        assert gen.await_args.kwargs["query"] == "Найди студию у моря до 120000"
        assert gen.await_args.kwargs["documents"] == docs

        assert result.route == "rag_search"
        assert result.error_type is None
        assert result.response_text == "Sunny Beach Studio is available for 110000 EUR."
        assert result.request_type == "GENERAL"
        assert result.retrieved_doc_ids == ["sunny_beach_studio"]
        assert result.retrieved_sources == [
            {"title": "Sunny Beach Studio", "url": "fixture://sunny_beach_studio"}
        ]
        assert result.documents_count == 1
        assert result.rerank_applied is True
        assert result.llm_model == "gpt-4o-mini"
        assert result.llm_call_count == 1

    async def test_cache_hit_skips_generation(self) -> None:
        """Semantic cache hits should return cached text without calling LLM generation."""
        from src.core.assistant import run_assistant_request

        rag = AsyncMock(
            return_value={
                "response": "Cached answer",
                "documents": [],
                "cache_hit": True,
                "query_type": "FAQ",
                "latency_stages": {"cache_check": 0.01},
            }
        )
        gen = AsyncMock()

        with (
            patch("src.runtime.graph.nodes.classify.classify_query", return_value="FAQ"),
            patch("telegram_bot.agents.rag_pipeline.rag_pipeline", rag),
            patch("telegram_bot.services.generate_response.generate_response", gen),
        ):
            result = await run_assistant_request(
                "Какие условия рассрочки?",
                collection="e2e_core_abc",
                request_id="e2e-cache",
                dependencies=self._deps(),
            )

        gen.assert_not_awaited()
        assert result.route == "cache_hit"
        assert result.cache_hit is True
        assert result.response_text == "Cached answer"
        assert result.llm_call_count == 0
        assert result.error_type is None

    async def test_runtime_dependency_failure_returns_recoverable_error(self) -> None:
        """Dependency failures should be returned as AssistantResult errors, not raised."""
        from src.core.assistant import run_assistant_request

        rag = AsyncMock(side_effect=TimeoutError("qdrant timed out"))

        with (
            patch("src.runtime.graph.nodes.classify.classify_query", return_value="GENERAL"),
            patch("telegram_bot.agents.rag_pipeline.rag_pipeline", rag),
        ):
            result = await run_assistant_request(
                "Найди квартиру",
                collection="e2e_core_abc",
                request_id="e2e-failure",
                dependencies=self._deps(),
            )

        assert result.route == "error"
        assert result.error_type == "dependency_failed"
        assert "qdrant timed out" in (result.error_message or "")
        assert result.request_id == "e2e-failure"

    async def test_runtime_emits_product_events_with_request_id(self, caplog) -> None:
        """Runtime events should be correlated by caller-provided request_id."""
        from src.core.assistant import run_assistant_request

        rag = AsyncMock(
            return_value={
                "documents": [{"metadata": {"source_id": "doc-1"}, "content": "fact"}],
                "cache_hit": False,
                "query_type": "GENERAL",
            }
        )
        gen = AsyncMock(return_value={"response": "answer", "llm_provider_model": "test-model"})

        with (
            patch("src.runtime.graph.nodes.classify.classify_query", return_value="GENERAL"),
            patch("telegram_bot.agents.rag_pipeline.rag_pipeline", rag),
            patch("telegram_bot.services.generate_response.generate_response", gen),
            caplog.at_level(logging.INFO, logger="src.utils.product_events"),
        ):
            await run_assistant_request(
                "q",
                collection="c",
                request_id="e2e-events",
                dependencies=self._deps(),
            )

        events = [r for r in caplog.records if hasattr(r, "event")]
        event_names = [r.event for r in events]
        assert event_names == [
            "assistant_request_started",
            "search_completed",
            "llm_completed",
            "assistant_request_completed",
        ]
        for record in events:
            assert getattr(record, "request_id", None) == "e2e-events"
