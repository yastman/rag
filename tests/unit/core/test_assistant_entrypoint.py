"""Unit tests for src.core.assistant — unified assistant entrypoint skeleton.

Covers PR A of #2336: dataclass definitions, request_id handling,
recoverable error shape, and import isolation from
Telegram / FastAPI / Langfuse / OTel.
"""

from __future__ import annotations

import importlib
import logging


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
