"""Integration test for ``create_voice_agent`` (Slice 3 / #2051).

Verifies that the factory wires the three voice middleware layers in the
correct order and that the compiled agent honours the
``SemanticCacheMiddleware`` cache-HIT short-circuit end-to-end (no real
LLM is hit on a cache hit, so the test runs offline).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain.messages import HumanMessage

from telegram_bot.agents.voice_agent import VoiceAgentState, create_voice_agent


@pytest.fixture
def cache_hit_stub(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Stub rag_core so the cache-middleware reports a HIT deterministically."""
    embedding = [0.42] * 8
    cached_response = "Готовый ответ из кэша."
    compute = AsyncMock(return_value=(embedding, None, None, False))
    check = AsyncMock(return_value=(True, cached_response))
    monkeypatch.setattr("telegram_bot.graph.middleware.cache.compute_query_embedding", compute)
    monkeypatch.setattr("telegram_bot.graph.middleware.cache.check_semantic_cache", check)
    monkeypatch.setattr("telegram_bot.graph.middleware.cache.is_contextual_query", lambda _q: False)
    fake_signal = MagicMock()
    fake_signal.is_filter_sensitive = False
    monkeypatch.setattr(
        "telegram_bot.graph.middleware.cache.detect_filter_sensitive_query",
        lambda _q: fake_signal,
    )
    monkeypatch.setattr(
        "telegram_bot.graph.middleware.cache.resolve_semantic_cache_signature",
        lambda **_: None,
    )
    fake_lf = MagicMock()
    fake_lf.update_current_span = MagicMock()
    monkeypatch.setattr("telegram_bot.graph.middleware.cache.get_client", lambda: fake_lf)
    monkeypatch.setattr("telegram_bot.graph.middleware.classify.classify_query", lambda _q: "FAQ")
    monkeypatch.setattr("telegram_bot.graph.middleware.classify.get_client", lambda: fake_lf)
    monkeypatch.setattr(
        "telegram_bot.graph.middleware.guard.detect_injection", lambda _q: (False, 0.0, None)
    )
    return {"embedding": embedding, "cached": cached_response}


@pytest.fixture
def chat_openai_stub(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace ``ChatOpenAI`` with a stub so factory creation is offline."""
    fake_llm = MagicMock(name="FakeLLM")
    fake_llm.bind_tools = MagicMock(return_value=fake_llm)
    fake_llm.with_structured_output = MagicMock(return_value=fake_llm)
    fake_llm.invoke = MagicMock()
    fake_llm.ainvoke = AsyncMock()

    fake_class = MagicMock(return_value=fake_llm)
    monkeypatch.setattr("telegram_bot.agents.voice_agent.ChatOpenAI", fake_class)
    return fake_class


@pytest.mark.asyncio
async def test_factory_returns_compiled_agent_with_three_middleware(
    chat_openai_stub: MagicMock,
) -> None:
    cache = MagicMock()
    embeddings = MagicMock()
    captured: dict[str, Any] = {}

    real_create_agent = __import__("langchain.agents", fromlist=["create_agent"]).create_agent

    def spy_create_agent(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return real_create_agent(**kwargs)

    with patch("telegram_bot.agents.voice_agent.create_agent", side_effect=spy_create_agent):
        agent = create_voice_agent(
            cache=cache,
            embeddings=embeddings,
            model="openai/gpt-test",
        )

    assert agent is not None
    assert "middleware" in captured
    middleware_names = [type(m).__name__ for m in captured["middleware"]]
    assert middleware_names == [
        "GuardMiddleware",
        "ClassifyMiddleware",
        "SemanticCacheMiddleware",
    ]
    assert captured["state_schema"] is VoiceAgentState
    assert chat_openai_stub.called


@pytest.mark.asyncio
async def test_factory_short_circuits_on_cache_hit(
    cache_hit_stub: dict[str, Any],
    chat_openai_stub: MagicMock,
) -> None:
    """End-to-end smoke: build the compiled graph and run a single
    ``ainvoke``. With the cache stubbed to HIT, the agent must not
    hit the LLM (the stub would record the call) — the cached AI
    message is returned via ``jump_to=end``.
    """
    cache = MagicMock()
    embeddings = MagicMock()

    agent = create_voice_agent(
        cache=cache,
        embeddings=embeddings,
        model="openai/gpt-test",
    )

    result = await agent.ainvoke({"messages": [HumanMessage(content="что нужно для прописки?")]})

    # The cached response is the latest message.
    assert result["messages"][-1].content == cache_hit_stub["cached"]
    # The model was never called because before_agent (cache) jumped to end.
    fake_llm = chat_openai_stub.return_value
    assert not fake_llm.invoke.called
    assert not fake_llm.ainvoke.called


def test_state_schema_includes_voice_input_fields() -> None:
    annotations = VoiceAgentState.__annotations__
    for field in ("voice_audio", "voice_duration_s", "stt_text", "trace_id"):
        assert field in annotations
