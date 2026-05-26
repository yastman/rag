"""Full-graph orchestration integration tests for the RAG LangGraph pipeline.

Coverage for issue #1089: voice subgraph + parent-graph orchestration paths
that the existing per-node and per-edge tests don't reach.

What this file adds on top of the existing suite (do NOT duplicate):
  * Voice entry path (route_start → transcribe → classify → ... → respond)
    exercised end-to-end through ``graph.ainvoke``.
  * Rewrite/retrieve loop bounding via ``max_rewrite_attempts``,
    ``max_llm_calls``, and the LangGraph ``recursion_limit=15`` guard.
  * Parent-graph RAGState shape transitions (documents, response,
    llm_call_count, latency_stages, message accumulation).
  * HITL state preservation across ``interrupt()`` / ``Command(resume=...)``
    via :class:`langgraph.checkpoint.memory.MemorySaver`.

Strategy
--------
Per-node logic is already covered in ``tests/unit/graph/nodes/*`` and
``tests/unit/graph/test_*_node.py``. Here we replace each node *body*
with a deterministic async stub via ``monkeypatch.setattr`` on the
module attributes that ``build_graph`` resolves at call time. The real
LangGraph machinery (StateGraph, conditional edges, recursion_limit,
checkpointer) is left untouched — that is exactly what we want to test.

No real LLM, Qdrant, Redis, or Whisper calls fire from this file.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from telegram_bot.graph.graph import build_graph
from telegram_bot.graph.state import RAGState, make_initial_state


# ---------------------------------------------------------------------------
# Shared stub-node installer
# ---------------------------------------------------------------------------


_DEFAULT_DOCS: list[dict[str, Any]] = [
    {
        "text": "Квартира в Несебре, 85000€",
        "score": 0.9,
        "id": "doc-1",
        "metadata": {"title": "Квартира", "city": "Несебр"},
    },
    {
        "text": "Студия в Солнечном береге, 60000€",
        "score": 0.8,
        "id": "doc-2",
        "metadata": {"title": "Студия", "city": "Солнечный берег"},
    },
]


def _install_stub_nodes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    classify_type: str = "GENERAL",
    cache_hit: bool = False,
    documents: list[dict[str, Any]] | None = None,
    documents_relevant: bool = True,
    grade_score_improved: bool = True,
    grade_rewrite_effective: bool = True,
    transcribed_query: str = "Что есть в Несебре?",
    response_text: str = "Stubbed LLM answer.",
    classify_capture: list[str] | None = None,
) -> None:
    """Replace every node body that ``build_graph`` resolves with a stub.

    All stubs return minimal valid state updates that keep the graph's
    routing predicates happy. ``latency_stages`` is merged (not replaced)
    so the assertion that all expected stages were visited works without
    a reducer on the field.

    Args:
        monkeypatch: pytest monkeypatch fixture.
        classify_type: query_type set by the classify stub.
        cache_hit: cache_hit flag set by cache_check stub.
        documents: documents returned by retrieve stub
            (default: 2 relevant docs).
        documents_relevant: documents_relevant flag set by grade stub.
        grade_score_improved: score_improved flag (controls rewrite loop).
        grade_rewrite_effective: rewrite_effective flag (controls rewrite loop).
        transcribed_query: query produced by the transcribe stub.
        response_text: answer produced by the generate stub.
        classify_capture: optional list to record the query classify saw.
    """
    docs = list(documents) if documents is not None else list(_DEFAULT_DOCS)

    async def transcribe_stub(state: dict[str, Any]) -> dict[str, Any]:
        return {
            "stt_text": transcribed_query,
            "stt_duration_ms": 1.0,
            "query": transcribed_query,
            "messages": [HumanMessage(content=transcribed_query)],
            "voice_audio": None,
            "input_type": "voice",
            "latency_stages": {**state.get("latency_stages", {}), "transcribe": 0.001},
        }

    monkeypatch.setattr(
        "src.runtime.graph.nodes.transcribe.make_transcribe_node",
        lambda **_kw: transcribe_stub,
    )

    async def classify_stub(state: dict[str, Any], runtime: Any) -> dict[str, Any]:
        messages = state.get("messages") or []
        if classify_capture is not None and messages:
            last = messages[-1]
            content = last.content if hasattr(last, "content") else last.get("content", "")
            classify_capture.append(content)
        update: dict[str, Any] = {
            "query_type": classify_type,
            "llm_call_count": state.get("llm_call_count", 0) + 1,
            "latency_stages": {**state.get("latency_stages", {}), "classify": 0.001},
        }
        if classify_type in ("CHITCHAT", "OFF_TOPIC"):
            update["response"] = "Hi! How can I help with real estate?"
        return update

    monkeypatch.setattr("src.runtime.graph.nodes.classify.classify_node", classify_stub)

    async def guard_stub(state: dict[str, Any], runtime: Any) -> dict[str, Any]:
        return {
            "guard_blocked": False,
            "guard_reason": None,
            "injection_detected": False,
            "injection_risk_score": 0.0,
            "injection_pattern": None,
            "latency_stages": {**state.get("latency_stages", {}), "guard": 0.001},
        }

    monkeypatch.setattr("src.runtime.graph.nodes.guard.guard_node", guard_stub)

    async def cache_check_stub(state: dict[str, Any], runtime: Any) -> dict[str, Any]:
        update: dict[str, Any] = {
            "cache_hit": cache_hit,
            "cached_response": "cached response" if cache_hit else None,
            "query_embedding": [0.1, 0.2, 0.3],
            "embeddings_cache_hit": False,
            "embedding_error": False,
            "embedding_error_type": None,
            "latency_stages": {**state.get("latency_stages", {}), "cache_check": 0.001},
        }
        if cache_hit:
            update["response"] = "cached response"
        return update

    monkeypatch.setattr("telegram_bot.graph.nodes.cache.cache_check_node", cache_check_stub)

    async def retrieve_stub(state: dict[str, Any], runtime: Any) -> dict[str, Any]:
        return {
            "documents": list(docs),
            "search_results_count": len(docs),
            "rerank_applied": False,
            "search_cache_hit": False,
            "retrieval_backend_error": False,
            "retrieval_error_type": None,
            "retrieved_context": [],
            "latency_stages": {**state.get("latency_stages", {}), "retrieve": 0.001},
        }

    monkeypatch.setattr("telegram_bot.graph.nodes.retrieve.retrieve_node", retrieve_stub)

    async def grade_stub(state: dict[str, Any]) -> dict[str, Any]:
        return {
            "documents_relevant": documents_relevant,
            "grade_confidence": 0.9 if documents_relevant else 0.0,
            "skip_rerank": False,
            "score_improved": grade_score_improved,
            "rewrite_effective": grade_rewrite_effective,
            "latency_stages": {**state.get("latency_stages", {}), "grade": 0.001},
        }

    monkeypatch.setattr("telegram_bot.graph.nodes.grade.grade_node", grade_stub)

    async def rerank_stub(state: dict[str, Any], runtime: Any) -> dict[str, Any]:
        return {
            "documents": list(docs)[:5],
            "rerank_applied": True,
            "rerank_cache_hit": False,
            "llm_call_count": state.get("llm_call_count", 0) + 1,
            "latency_stages": {**state.get("latency_stages", {}), "rerank": 0.001},
        }

    monkeypatch.setattr("telegram_bot.graph.nodes.rerank.rerank_node", rerank_stub)

    async def generate_stub(state: dict[str, Any]) -> dict[str, Any]:
        return {
            "response": response_text,
            "messages": [{"role": "assistant", "content": response_text}],
            "llm_call_count": state.get("llm_call_count", 0) + 1,
            "latency_stages": {**state.get("latency_stages", {}), "generate": 0.001},
        }

    monkeypatch.setattr("telegram_bot.graph.nodes.generate.generate_node", generate_stub)

    async def rewrite_stub(state: dict[str, Any], runtime: Any) -> dict[str, Any]:
        new_count = state.get("rewrite_count", 0) + 1
        return {
            "messages": [HumanMessage(content=f"rewritten query #{new_count}")],
            "rewrite_count": new_count,
            "rewrite_effective": True,
            "query_embedding": None,
            "sparse_embedding": None,
            "rewrite_provider_model": "stub-model",
            "llm_call_count": state.get("llm_call_count", 0) + 1,
            "latency_stages": {**state.get("latency_stages", {}), "rewrite": 0.001},
        }

    monkeypatch.setattr("telegram_bot.graph.nodes.rewrite.rewrite_node", rewrite_stub)

    async def cache_store_stub(state: dict[str, Any], runtime: Any) -> dict[str, Any]:
        return {"response": state.get("response", "")}

    monkeypatch.setattr("telegram_bot.graph.nodes.cache.cache_store_node", cache_store_stub)

    async def respond_stub(state: dict[str, Any]) -> dict[str, Any]:
        response = state.get("response", "")
        return {
            "messages": [{"role": "assistant", "content": response}],
            "latency_stages": {**state.get("latency_stages", {}), "respond": 0.001},
        }

    monkeypatch.setattr("telegram_bot.graph.nodes.respond.respond_node", respond_stub)


def _build_test_graph(checkpointer: Any | None = None) -> Any:
    """Build the real graph with mocked service dependencies.

    Node bodies are expected to have been monkeypatched via
    :func:`_install_stub_nodes` *before* calling this helper.
    """
    return build_graph(
        cache=AsyncMock(),
        embeddings=AsyncMock(),
        sparse_embeddings=AsyncMock(),
        qdrant=AsyncMock(),
        reranker=AsyncMock(),
        llm=MagicMock(),
        message=None,  # respond/generate take their non-streaming branch
        checkpointer=checkpointer,
        content_filter_enabled=True,
    )


def _voice_state(audio: bytes = b"fake-ogg-bytes") -> dict[str, Any]:
    state = make_initial_state(user_id=42, session_id="voice-session-1", query="")
    state["voice_audio"] = audio
    state["voice_duration_s"] = 3.2
    state["input_type"] = "voice"
    return state


def _text_state(query: str = "Что есть в Несебре?") -> dict[str, Any]:
    return make_initial_state(user_id=7, session_id="text-session-1", query=query)


# ---------------------------------------------------------------------------
# 1. Voice subgraph end-to-end
# ---------------------------------------------------------------------------


class TestVoiceSubgraphEndToEnd:
    """Voice-entry path: route_start → transcribe → classify → ... → respond.

    Per-node tests already cover ``transcribe_node`` in isolation; these tests
    exercise the orchestration that the unit tests cannot reach.
    """

    async def test_voice_path_runs_through_full_pipeline(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Voice entry runs to END through transcribe + GENERAL pipeline."""
        _install_stub_nodes(monkeypatch, classify_type="GENERAL", documents_relevant=True)
        graph = _build_test_graph()

        result = await graph.ainvoke(_voice_state())

        # Routed via voice path (route_start) and reached respond.
        assert "transcribe" in result["latency_stages"]
        assert "classify" in result["latency_stages"]
        assert "retrieve" in result["latency_stages"]
        assert "respond" in result["latency_stages"]

        # Final response produced and surfaced into messages.
        assert result["response"] == "Stubbed LLM answer."
        last_msg = result["messages"][-1]
        last_content = (
            last_msg.content if hasattr(last_msg, "content") else last_msg.get("content", "")
        )
        assert last_content == "Stubbed LLM answer."

    async def test_voice_path_propagates_transcribed_query_to_classify(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The transcript produced by transcribe_node reaches classify_node."""
        captured: list[str] = []
        _install_stub_nodes(
            monkeypatch,
            classify_type="GENERAL",
            transcribed_query="Apartment in Nessebar?",
            classify_capture=captured,
        )
        graph = _build_test_graph()

        await graph.ainvoke(_voice_state())

        # classify saw the transcribed text (last message), not the empty
        # initial query.
        assert captured, "classify_node was never invoked"
        assert captured[-1] == "Apartment in Nessebar?"

    async def test_voice_path_falls_back_to_respond_for_chitchat(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Voice → transcribe → classify(CHITCHAT) → respond skips retrieval."""
        _install_stub_nodes(monkeypatch, classify_type="CHITCHAT")
        graph = _build_test_graph()

        result = await graph.ainvoke(_voice_state())

        # Visited transcribe + classify + respond, but skipped retrieve+grade.
        stages = result["latency_stages"]
        assert "transcribe" in stages
        assert "classify" in stages
        assert "respond" in stages
        assert "retrieve" not in stages
        assert "grade" not in stages
        assert "generate" not in stages

        assert result["query_type"] == "CHITCHAT"


# ---------------------------------------------------------------------------
# 2. Rewrite/retrieve loop bounding
# ---------------------------------------------------------------------------


class TestRewriteRetrieveLoopBound:
    """Verify the rewrite→retrieve loop is genuinely bounded.

    Three exits guard the loop:
      1. ``rewrite_count >= max_rewrite_attempts`` (per #374 rewrite guard).
      2. ``llm_call_count >= max_llm_calls`` (per #374 LLM cap).
      3. ``recursion_limit=15`` super-step ceiling (LangGraph built-in).
    """

    async def test_rewrite_loop_terminates_at_max_rewrite_attempts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """rewrite_count reaches max_rewrite_attempts and loop exits cleanly.

        Note: ``recursion_limit`` is bumped above the default 15 here so the
        cap we are actually testing is ``max_rewrite_attempts`` (route_grade
        guard), not the LangGraph step ceiling. The 15-step ceiling has its
        own dedicated test below.
        """
        _install_stub_nodes(
            monkeypatch,
            classify_type="GENERAL",
            documents=[],  # retrieve always returns 0 docs
            documents_relevant=False,  # grade always not relevant
            grade_score_improved=True,
            grade_rewrite_effective=True,
        )
        graph = _build_test_graph()

        state = _text_state("Find apartments")
        state["max_rewrite_attempts"] = 3
        state["max_llm_calls"] = 100  # Don't hit the LLM cap first

        result = await graph.ainvoke(state, config={"recursion_limit": 50})

        # Loop terminated cleanly (no GraphRecursionError) and was bounded
        # by max_rewrite_attempts (route_grade returns "generate" once
        # rewrite_count >= max_rewrite_attempts).
        assert result["rewrite_count"] <= 3
        assert result["rewrite_count"] == 3, (
            f"Expected exactly max_rewrite_attempts rewrites, got {result['rewrite_count']}"
        )
        assert "respond" in result["latency_stages"]

    async def test_rewrite_loop_terminates_at_llm_call_limit_when_attempts_higher(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """llm_call_count cap halts the loop before max_rewrite_attempts."""
        _install_stub_nodes(
            monkeypatch,
            classify_type="GENERAL",
            documents=[],
            documents_relevant=False,
            grade_score_improved=True,
            grade_rewrite_effective=True,
        )
        graph = _build_test_graph()

        state = _text_state("Find apartments")
        state["max_rewrite_attempts"] = 10  # Plenty of attempts
        state["max_llm_calls"] = 5  # But the LLM cap binds first

        result = await graph.ainvoke(state, config={"recursion_limit": 50})

        # The LLM cap (5) is checked in route_grade — once the prior nodes
        # have ticked llm_call_count to >= 5, route_grade returns "generate".
        # classify(+1) + each rewrite(+1) + final generate(+1) are the only
        # contributors on this path (rerank doesn't fire since
        # documents_relevant=False).
        assert result["llm_call_count"] <= state["max_llm_calls"] + 2  # +classify +generate slack
        assert result["rewrite_count"] < 10
        assert "respond" in result["latency_stages"]

    async def test_rewrite_loop_does_not_exceed_recursion_limit_15(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An ``max_rewrite_attempts`` set absurdly high triggers the
        LangGraph recursion_limit=15 guard, raising GraphRecursionError."""
        _install_stub_nodes(
            monkeypatch,
            classify_type="GENERAL",
            documents=[],
            documents_relevant=False,
            grade_score_improved=True,
            grade_rewrite_effective=True,
        )
        graph = _build_test_graph()

        state = _text_state("Find apartments")
        state["max_rewrite_attempts"] = 20  # Above recursion budget
        state["max_llm_calls"] = 100  # Don't let the LLM cap intervene

        with pytest.raises(GraphRecursionError):
            await graph.ainvoke(state)


# ---------------------------------------------------------------------------
# 3. Parent-graph RAGState transitions
# ---------------------------------------------------------------------------


class TestParentGraphRAGStateTransitions:
    """End-to-end happy path: verify RAGState shape evolves correctly."""

    async def test_full_pipeline_text_path_state_transitions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Text query → state acquires documents, response, latency_stages."""
        _install_stub_nodes(monkeypatch, classify_type="GENERAL", documents_relevant=True)
        graph = _build_test_graph()

        initial_state = _text_state("Find a 2-bedroom in Nessebar")
        # Sanity: initial state has no documents and llm_call_count=0
        assert initial_state["documents"] == []
        assert initial_state["llm_call_count"] == 0
        assert initial_state["response"] == ""

        result = await graph.ainvoke(initial_state)

        # Documents populated by retrieve.
        assert len(result["documents"]) == 2
        # Response produced by generate.
        assert result["response"] == "Stubbed LLM answer."
        # llm_call_count ticked up (classify + rerank + generate at minimum).
        assert result["llm_call_count"] > 0
        # latency_stages got real entries from each visited node.
        assert {"classify", "cache_check", "retrieve", "grade", "respond"}.issubset(
            result["latency_stages"].keys()
        )

    async def test_state_preserves_session_id_throughout_pipeline(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """session_id and user_id are read-only metadata; nodes don't clobber."""
        _install_stub_nodes(monkeypatch, classify_type="GENERAL", documents_relevant=True)
        graph = _build_test_graph()

        state = make_initial_state(user_id=999, session_id="my-special-session", query="Hello")

        result = await graph.ainvoke(state)

        assert result["session_id"] == "my-special-session"
        assert result["user_id"] == 999

    async def test_messages_appended_not_replaced(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The messages reducer (add_messages) appends; never overwrites prior turns."""
        _install_stub_nodes(monkeypatch, classify_type="GENERAL", documents_relevant=True)
        graph = _build_test_graph()

        state = _text_state("New query")
        # Pretend an earlier conversational turn exists in state.messages.
        state["messages"] = [
            HumanMessage(content="Previous user turn"),
            HumanMessage(content="New query"),
        ]

        result = await graph.ainvoke(state)

        # add_messages preserved the prior turn AND appended the new ones.
        contents = [
            (m.content if hasattr(m, "content") else m.get("content", ""))
            for m in result["messages"]
        ]
        assert "Previous user turn" in contents
        assert "New query" in contents
        # The generate stub's assistant response is also appended.
        assert "Stubbed LLM answer." in contents


# ---------------------------------------------------------------------------
# 4. HITL state preservation via checkpointer
# ---------------------------------------------------------------------------


def _build_hitl_test_graph(checkpointer: Any) -> Any:
    """Minimal StateGraph with a single interrupting node.

    A full RAG graph isn't needed to prove the LangGraph contract that
    interrupt() pauses with a payload and Command(resume=...) restores
    pre-interrupt state. The contract is graph-shape-agnostic; reusing
    the full pipeline would just add noise.
    """

    class _HitlState(RAGState, total=False):
        pass

    async def hitl_node(state: dict[str, Any]) -> dict[str, Any]:
        # Snapshot fields BEFORE the interrupt to assert preservation.
        pre_count = state.get("llm_call_count", 0)
        decision = interrupt(
            {
                "tool": "crm_create_lead",
                "preview": "Создать сделку: name=Test",
                "args": {"name": "Test"},
            }
        )
        # Resume continues from here with the value passed via Command(resume=...).
        return {
            "response": f"action={decision.get('action')}",
            "messages": [{"role": "assistant", "content": f"action={decision.get('action')}"}],
            # Show that pre-interrupt state was readable on resume.
            "llm_call_count": pre_count,
        }

    workflow = StateGraph(_HitlState)
    workflow.add_node("hitl", hitl_node)  # type: ignore[type-var]
    workflow.add_edge(START, "hitl")
    workflow.add_edge("hitl", END)
    return workflow.compile(checkpointer=checkpointer)


class TestHITLStatePreservationViaCheckpointer:
    """Cover the resume path that's currently not tested at graph level.

    The unit test ``tests/unit/agents/test_hitl.py`` covers ``hitl_guard()``
    in isolation by patching ``interrupt``. These tests exercise the real
    LangGraph interrupt/resume contract end-to-end through a compiled
    graph + ``MemorySaver`` checkpointer.
    """

    async def test_hitl_interrupt_pauses_graph_and_returns_payload(self) -> None:
        """First ``ainvoke`` call surfaces ``__interrupt__`` with the payload."""
        graph = _build_hitl_test_graph(MemorySaver())

        config = {"configurable": {"thread_id": "hitl-thread-1"}}
        initial = make_initial_state(user_id=1, session_id="s", query="q")

        result = await graph.ainvoke(initial, config=config)

        assert "__interrupt__" in result, "Graph should pause and surface __interrupt__"
        interrupts = result["__interrupt__"]
        assert interrupts, "__interrupt__ must contain at least one entry"
        payload = interrupts[0].value
        assert payload["tool"] == "crm_create_lead"
        assert payload["args"] == {"name": "Test"}
        # Pre-interrupt state was checkpointed without producing a final response.
        assert not result.get("response")

    @pytest.mark.parametrize(
        ("action", "expected_response"),
        [("approve", "action=approve"), ("cancel", "action=cancel")],
    )
    async def test_hitl_resume_restores_pre_interrupt_state(
        self, action: str, expected_response: str
    ) -> None:
        """Resuming with Command(resume=...) yields the post-interrupt state and
        preserves the snapshotted pre-interrupt fields.

        Parametrized to cover both approve and cancel actions in one place,
        which doubles as ``test_hitl_cancel_resumes_with_cancel_action``.
        """
        graph = _build_hitl_test_graph(MemorySaver())
        config = {"configurable": {"thread_id": f"hitl-thread-{action}"}}

        initial = make_initial_state(user_id=1, session_id="s", query="q")
        # Set a non-default field so we can prove it survived the pause.
        initial["llm_call_count"] = 4

        # 1. Trigger the interrupt.
        first = await graph.ainvoke(initial, config=config)
        assert "__interrupt__" in first
        # State on pause shows messages unchanged (no assistant turn yet).
        msgs_before = first["messages"]
        contents_before = [
            (m.content if hasattr(m, "content") else m.get("content", "")) for m in msgs_before
        ]
        assert "action=approve" not in contents_before
        assert "action=cancel" not in contents_before

        # 2. Resume.
        second = await graph.ainvoke(Command(resume={"action": action}), config=config)

        # Post-interrupt state present.
        assert second["response"] == expected_response
        # Pre-interrupt llm_call_count survived the pause+resume.
        assert second["llm_call_count"] == 4
        # The pre-interrupt human message is still there (add_messages reducer
        # never dropped it).
        contents_after = [
            (m.content if hasattr(m, "content") else m.get("content", ""))
            for m in second["messages"]
        ]
        assert "q" in contents_after
        assert expected_response in contents_after

    async def test_hitl_cancel_resumes_with_cancel_action(self) -> None:
        """Standalone cancel-path test (parametrized cousin still covers it,
        but #1089 explicitly asks for a named test for the cancel branch)."""
        graph = _build_hitl_test_graph(MemorySaver())
        config = {"configurable": {"thread_id": "hitl-cancel"}}

        initial = make_initial_state(user_id=1, session_id="s", query="q")
        first = await graph.ainvoke(initial, config=config)
        assert "__interrupt__" in first

        second = await graph.ainvoke(Command(resume={"action": "cancel"}), config=config)
        assert second["response"] == "action=cancel"
