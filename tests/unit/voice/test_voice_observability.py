"""Tests for voice observability helpers."""

from __future__ import annotations

import inspect
from unittest.mock import patch

from src.voice.observability import (
    build_voice_trace_metadata,
    trace_voice_session,
    update_voice_trace,
    voice_session_id,
)


def test_voice_session_id_handles_missing_call_id() -> None:
    assert voice_session_id(None) == "voice-unknown"
    assert voice_session_id("  123 ") == "voice-123"


def test_build_voice_trace_metadata_omits_optional_fields_when_empty() -> None:
    assert build_voice_trace_metadata(call_id="c1", status="answered") == {
        "call_id": "c1",
        "status": "answered",
    }


def test_update_voice_trace_sets_trace_context() -> None:
    with patch("src.voice.observability.update_lifecycle_trace") as update_trace:
        update_voice_trace(call_id="call-42", status="completed", duration_sec=9)

    update_trace.assert_called_once_with(
        family="voice",
        span_name="voice-session",
        session_id="voice-call-42",
        user_id="voice-agent",
        tags=["voice", "call-lifecycle"],
        metadata={"call_id": "call-42", "status": "completed", "duration_sec": 9},
        trace_id=None,
    )


def test_trace_voice_session_is_not_wrapped_in_second_observation_layer() -> None:
    assert not hasattr(trace_voice_session, "__wrapped__")
    assert inspect.iscoroutinefunction(trace_voice_session)


# ---------------------------------------------------------------------------
# #2160 — voice-session traces never materialize; tool unwrapped
# ---------------------------------------------------------------------------


def test_search_knowledge_base_decorator_stack_is_function_tool_then_observe() -> None:
    """``search_knowledge_base`` must be wrapped with both ``@function_tool`` and ``@observe``.

    Decorator stacking: outer ``@function_tool()`` keeps LiveKit's tool-schema
    wrapper on top so the LLM can call this tool, while the inner ``@observe``
    adds a Langfuse span (``voice-tool-search-knowledge-base``) under the
    active ``voice-session`` parent. Closes #2160.
    """
    import inspect
    import textwrap

    # Read source from the agent module without importing livekit.
    import src.voice.agent as agent_mod

    src = textwrap.dedent(inspect.getsource(agent_mod.VoiceBot))
    # Find the search_knowledge_base method block.
    method_start = src.index("async def search_knowledge_base")
    # Search backwards for decorators on consecutive lines above the def.
    method_section = src[max(0, method_start - 400) : method_start]
    # Outer decorator must be @function_tool (LiveKit must see the tool).
    assert "@function_tool" in method_section, (
        "search_knowledge_base must be wrapped with @function_tool() so the "
        "LLM can invoke it as a tool"
    )
    # Inner decorator must be @observe (Langfuse trace).
    assert "@observe" in method_section, (
        "search_knowledge_base must also be wrapped with @observe so the tool "
        "call lands as a `voice-tool-search-knowledge-base` Langfuse span"
    )
    # Lock the span name + PII-safe capture flags.
    assert 'name="voice-tool-search-knowledge-base"' in method_section
    assert "capture_input=False" in method_section
    assert "capture_output=False" in method_section
    # Stacking order: @function_tool above @observe (closer to def).
    function_tool_idx = method_section.rindex("@function_tool")
    observe_idx = method_section.rindex("@observe")
    assert function_tool_idx < observe_idx, (
        "Decorator stacking must be @function_tool() outermost, @observe "
        "innermost — LiveKit's @function_tool() wraps a coroutine, and "
        "@observe must wrap the body so the span captures the actual call"
    )


def test_entrypoint_opens_voice_session_via_start_as_current_observation() -> None:
    """The voice ``entrypoint`` must open a ``voice-session`` span context.

    Without an outer ``start_as_current_observation(name="voice-session")``,
    inner ``@observe`` spans (``voice-tool-search-knowledge-base``,
    downstream ``rag-api-query`` propagated via ``langfuse_trace_id``)
    would either become orphaned top-level traces or materialize against a
    different OTEL provider than the SDK singleton, which is the failure
    mode reported in #2160.
    """
    import inspect
    import textwrap

    import src.voice.agent as agent_mod

    src = textwrap.dedent(inspect.getsource(agent_mod.entrypoint))
    # Must use the SDK-native context-manager helper to open the session
    # span — not raw OTEL TracerProvider.start_span calls.
    assert "start_as_current_observation" in src, (
        "entrypoint must open a voice-session via "
        "lf.start_as_current_observation(name='voice-session', as_type='span') "
        "so child @observe spans nest under it"
    )
    assert "voice-session" in src, "entrypoint must name the outer span exactly 'voice-session'"
