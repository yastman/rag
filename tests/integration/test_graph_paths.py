"""Imperative graph-facade integration tests.

stale_test classification: the previous tests in this file exercised legacy
LangGraph node routing, checkpointer, and summarization wiring. That wiring was
removed by Worker B (#2405 / #2427) and is intentionally not part of the
imperative compatibility surface (#2495). Useful adapter-facing behavior is kept
below: callers can still build a graph-like object, call ``ainvoke`` /
``with_config``, send voice or text state, and receive graph-shaped output from
the imperative assistant pipeline.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.contracts import AssistantRequest, AssistantResult, CoreDependencies
from telegram_bot.graph.graph import ImperativeGraph, build_graph
from telegram_bot.graph.state import make_initial_state


pytestmark = pytest.mark.no_services

STALE_TEST_CLASSIFICATION = "stale_test"
STALE_TEST_REFERENCES = ("#2405", "#2427", "#2495")


def _make_dependencies() -> dict[str, Any]:
    cache = MagicMock(name="cache")
    embeddings = MagicMock(name="embeddings")
    sparse_embeddings = MagicMock(name="sparse_embeddings")
    qdrant = MagicMock(name="qdrant")
    reranker = MagicMock(name="reranker")
    llm = MagicMock(name="llm")
    telemetry = MagicMock(name="telemetry")
    message = MagicMock(name="message")
    message.answer = AsyncMock()
    return {
        "cache": cache,
        "embeddings": embeddings,
        "sparse_embeddings": sparse_embeddings,
        "qdrant": qdrant,
        "reranker": reranker,
        "llm": llm,
        "telemetry": telemetry,
        "message": message,
        "collection": "apartments-test",
    }


def _assistant_result(**overrides: Any) -> AssistantResult:
    defaults: dict[str, Any] = {
        "response_text": "Императивный ответ",
        "route": "rag",
        "request_type": "REAL_ESTATE",
        "documents_count": 2,
        "latency_ms": 123.0,
        "cache_hit": False,
        "rerank_applied": True,
        "error_type": None,
    }
    defaults.update(overrides)
    return AssistantResult(**defaults)


@pytest.mark.integration
def test_legacy_graph_tests_are_classified_stale_after_langgraph_removal() -> None:
    """Document that legacy routing assertions were retired, not silently lost."""

    assert STALE_TEST_CLASSIFICATION == "stale_test"
    assert STALE_TEST_REFERENCES == ("#2405", "#2427", "#2495")


@pytest.mark.integration
def test_build_graph_returns_imperative_facade_with_old_fluent_shape() -> None:
    """build_graph keeps the adapter-facing object shape without LangGraph."""

    graph = build_graph(**_make_dependencies())

    assert isinstance(graph, ImperativeGraph)
    assert graph.with_config(tags=["legacy-call-site"]) is graph


@pytest.mark.integration
async def test_ainvoke_maps_text_state_through_imperative_pipeline() -> None:
    """Text state is converted into an AssistantRequest and graph-shaped result."""

    dependencies = _make_dependencies()
    graph = build_graph(**dependencies)
    state = make_initial_state(user_id=42, session_id="text-session", query="Квартира в Варне")
    state["filters"] = {"city": "Varna"}

    pipeline_result = _assistant_result(response_text="Нашёл варианты в Варне")
    with patch(
        "telegram_bot.graph.graph.run_assistant_pipeline",
        new=AsyncMock(return_value=pipeline_result),
    ) as run_pipeline:
        result = await graph.ainvoke(state, config={"request_id": "req-text"})

    run_pipeline.assert_awaited_once()
    request = run_pipeline.await_args.kwargs.get("request") or run_pipeline.await_args.args[0]
    core_deps = run_pipeline.await_args.kwargs["dependencies"]

    assert isinstance(request, AssistantRequest)
    assert request.query == "Квартира в Варне"
    assert request.collection == "apartments-test"
    assert request.request_id == "req-text"
    assert request.user_context.user_id == "42"
    assert request.user_context.session_id == "text-session"
    assert request.user_context.filters == {"city": "Varna"}

    assert isinstance(core_deps, CoreDependencies)
    assert core_deps.cache is dependencies["cache"]
    assert core_deps.embeddings is dependencies["embeddings"]
    assert core_deps.sparse_embeddings is dependencies["sparse_embeddings"]
    assert core_deps.qdrant is dependencies["qdrant"]
    assert core_deps.reranker is dependencies["reranker"]
    assert core_deps.llm is dependencies["llm"]
    assert core_deps.telemetry is dependencies["telemetry"]

    assert result["response"] == "Нашёл варианты в Варне"
    assert result["query_type"] == "REAL_ESTATE"
    assert result["cache_hit"] is False
    assert result["sources_count"] == 2
    assert result["search_results_count"] == 2
    assert result["rerank_applied"] is True
    assert result["retrieval_error_type"] is None
    assert result["latency_stages"]["imperative"] == pytest.approx(0.123)
    assert result["documents"] == []
    dependencies["message"].answer.assert_awaited_once_with("Нашёл варианты в Варне")


@pytest.mark.integration
async def test_ainvoke_uses_trace_id_as_request_id_when_config_omits_one() -> None:
    """The facade preserves existing trace-id fallback behavior for old callers."""

    dependencies = _make_dependencies()
    graph = build_graph(**dependencies)
    state = make_initial_state(user_id=7, session_id="trace-session", query="Цены в Бургасе")
    state["trace_id"] = "trace-123"

    with patch(
        "telegram_bot.graph.graph.run_assistant_pipeline",
        new=AsyncMock(return_value=_assistant_result()),
    ) as run_pipeline:
        await graph.ainvoke(state)

    request = run_pipeline.await_args.kwargs.get("request") or run_pipeline.await_args.args[0]
    assert request.request_id == "trace-123"


@pytest.mark.integration
async def test_ainvoke_transcribes_voice_before_pipeline_request() -> None:
    """Voice state still passes through the transcribe node before core pipeline."""

    dependencies = _make_dependencies()
    graph = build_graph(**dependencies)
    state = make_initial_state(user_id=9, session_id="voice-session", query="")
    state["input_type"] = "voice"
    state["voice_audio"] = b"fake-ogg"

    async def fake_transcribe(working_state: dict[str, Any]) -> dict[str, Any]:
        assert working_state["voice_audio"] == b"fake-ogg"
        return {"stt_text": "Покажи апартаменты у моря", "input_type": "voice"}

    make_transcribe = MagicMock(return_value=fake_transcribe)
    with (
        patch("telegram_bot.graph.graph.make_transcribe_node", new=make_transcribe),
        patch(
            "telegram_bot.graph.graph.run_assistant_pipeline",
            new=AsyncMock(return_value=_assistant_result(response_text="Голос обработан")),
        ) as run_pipeline,
    ):
        result = await graph.ainvoke(state)

    make_transcribe.assert_called_once_with(
        llm=dependencies["llm"],
        voice_language="ru",
        stt_model="whisper",
        show_transcription=True,
        message=dependencies["message"],
    )
    request = run_pipeline.await_args.kwargs.get("request") or run_pipeline.await_args.args[0]
    assert request.query == "Покажи апартаменты у моря"
    assert result["stt_text"] == "Покажи апартаменты у моря"
    assert result["input_type"] == "voice"
    assert result["response"] == "Голос обработан"
