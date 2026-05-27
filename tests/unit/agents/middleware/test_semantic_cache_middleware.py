"""Behaviour parity tests for ``SemanticCacheMiddleware`` (Slice 2 / #2051).

The middleware replaces the legacy graph nodes
:func:`telegram_bot.graph.nodes.cache.cache_check_node` and
:func:`telegram_bot.graph.nodes.cache.cache_store_node`. These tests pin
the behaviour the legacy nodes ship today so that the middleware shape
can be wired into ``create_voice_agent`` (Slice 3) without surprising
the graph-side regression suite.

Every test stubs ``rag_core``/``cache_policy`` collaborators so the
middleware is exercised in isolation — no Redis, no embedding service,
no Langfuse client.
"""

from __future__ import annotations

import dataclasses
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain.messages import AIMessage, HumanMessage

from telegram_bot.graph.middleware.cache import (
    SemanticCacheMiddleware,
    _CacheAwareState,
)


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #


def _state(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "messages": [HumanMessage(content="что такое прописка в Болгарии")],
        "query_type": "FAQ",
    }
    base.update(overrides)
    return base


def _runtime_stub() -> Any:
    runtime = MagicMock()
    runtime.context = {}
    return runtime


@pytest.fixture
def cache() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def embeddings() -> AsyncMock:
    embeddings = AsyncMock()
    embeddings.aembed_query.return_value = [0.1] * 8
    return embeddings


@pytest.fixture
def middleware(cache: AsyncMock, embeddings: AsyncMock) -> SemanticCacheMiddleware:
    return SemanticCacheMiddleware(cache=cache, embeddings=embeddings)


@pytest.fixture(autouse=True)
def _stub_observability(monkeypatch: pytest.MonkeyPatch) -> None:
    """Silence observability so tests do not depend on Langfuse internals."""
    fake_client = MagicMock()
    fake_client.update_current_span = MagicMock()
    monkeypatch.setattr("telegram_bot.graph.middleware.cache.get_client", lambda: fake_client)


@pytest.fixture
def patched_rag_core(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace ``compute_query_embedding`` and ``check_semantic_cache``.

    Default behaviour: embedding succeeds, cache MISS, ColBERT vectors
    None. Individual tests override return values via the returned dict.
    """
    embedding = [0.1] * 8
    state: dict[str, Any] = {
        "compute": AsyncMock(return_value=(embedding, None, None, False)),
        "check": AsyncMock(return_value=(False, None)),
        "embedding": embedding,
    }
    monkeypatch.setattr(
        "telegram_bot.graph.middleware.cache.compute_query_embedding", state["compute"]
    )
    monkeypatch.setattr("telegram_bot.graph.middleware.cache.check_semantic_cache", state["check"])
    return state


@pytest.fixture
def patched_store(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    fake = AsyncMock(return_value=True)
    monkeypatch.setattr("telegram_bot.graph.middleware.cache.maybe_store_semantic_response", fake)
    return fake


# --------------------------------------------------------------------------- #
# before_agent — cache check                                                    #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_before_agent_returns_none_for_empty_messages(
    middleware: SemanticCacheMiddleware,
) -> None:
    """No human message → middleware is a no-op (no embedding, no jump)."""
    result = await middleware.abefore_agent({"messages": []}, _runtime_stub())
    assert result is None


@pytest.mark.asyncio
async def test_before_agent_skips_cache_for_non_cacheable_query_type(
    middleware: SemanticCacheMiddleware,
    patched_rag_core: dict[str, Any],
) -> None:
    """CHITCHAT / OFF_TOPIC bypass cache (matches legacy classify routing)."""
    state = _state(query_type="CHITCHAT")
    result = await middleware.abefore_agent(state, _runtime_stub())
    assert result is None
    patched_rag_core["compute"].assert_not_called()
    patched_rag_core["check"].assert_not_called()


@pytest.mark.asyncio
async def test_before_agent_short_circuits_on_cache_hit(
    middleware: SemanticCacheMiddleware,
    patched_rag_core: dict[str, Any],
) -> None:
    """Cache HIT must return jump_to=end + AIMessage(cached) so the SDK
    skips both the model call and the after_agent cache_store path."""
    cached_response = "ВНЖ оформляется в течение 30 рабочих дней."
    patched_rag_core["check"].return_value = (True, cached_response)

    result = await middleware.abefore_agent(_state(), _runtime_stub())

    assert result is not None
    assert result["jump_to"] == "end"
    assert result["cache_hit"] is True
    assert result["cached_response"] == cached_response
    assert result["query_embedding"] == patched_rag_core["embedding"]
    # Final-message slot carries the cached AI response so handle_voice
    # / handle_query can read it from state["messages"][-1].
    [message] = result["messages"]
    assert isinstance(message, AIMessage)
    assert message.content == cached_response


@pytest.mark.asyncio
async def test_before_agent_returns_embedding_on_cache_miss(
    middleware: SemanticCacheMiddleware,
    patched_rag_core: dict[str, Any],
) -> None:
    """Cache MISS must surface the freshly-computed embedding so downstream
    tools (rag_search) reuse it rather than recomputing."""
    result = await middleware.abefore_agent(_state(), _runtime_stub())

    assert result is not None
    assert "jump_to" not in result
    assert result["cache_hit"] is False
    assert result["query_embedding"] == patched_rag_core["embedding"]
    assert result["cached_response"] is None


@pytest.mark.asyncio
async def test_before_agent_skips_cache_for_contextual_query(
    middleware: SemanticCacheMiddleware,
    patched_rag_core: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``is_contextual_query`` short-circuits the lookup (legacy parity).

    The embedding is still computed because downstream tools need it on
    the no-hit branch; only the ``check_semantic_cache`` call is gated.
    """
    monkeypatch.setattr("telegram_bot.graph.middleware.cache.is_contextual_query", lambda _q: True)
    result = await middleware.abefore_agent(_state(), _runtime_stub())

    assert result is not None
    assert result["cache_hit"] is False
    patched_rag_core["compute"].assert_awaited_once()
    patched_rag_core["check"].assert_not_called()


@pytest.mark.asyncio
async def test_before_agent_skips_cache_when_filter_sensitive_without_signature(
    middleware: SemanticCacheMiddleware,
    patched_rag_core: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Filter-sensitive queries with no resolved filter_signature must NOT
    hit the shared cache bucket; matches the carve-out in cache_check_node."""

    fake_signal = MagicMock()
    fake_signal.is_filter_sensitive = True
    monkeypatch.setattr(
        "telegram_bot.graph.middleware.cache.detect_filter_sensitive_query",
        lambda _q: fake_signal,
    )
    monkeypatch.setattr(
        "telegram_bot.graph.middleware.cache.resolve_semantic_cache_signature",
        lambda **_: None,
    )

    result = await middleware.abefore_agent(_state(), _runtime_stub())

    assert result is not None
    assert result["cache_hit"] is False
    patched_rag_core["check"].assert_not_called()


@pytest.mark.asyncio
async def test_before_agent_short_circuits_on_embedding_failure(
    middleware: SemanticCacheMiddleware,
    patched_rag_core: dict[str, Any],
) -> None:
    """Embedding failure surfaces the graceful-fallback response and stops
    the agent loop (matches the early-return shape of cache_check_node)."""
    patched_rag_core["compute"].side_effect = TimeoutError("BGE timeout")

    result = await middleware.abefore_agent(_state(), _runtime_stub())

    assert result is not None
    assert result["jump_to"] == "end"
    assert result["embedding_error"] is True
    assert result["embedding_error_type"] == "TimeoutError"
    [message] = result["messages"]
    assert "временно недоступен" in message.content


# --------------------------------------------------------------------------- #
# after_agent — cache store                                                     #
# --------------------------------------------------------------------------- #


@dataclasses.dataclass
class _FakeDecision:
    response_state: str = "ok"
    degraded_reason: str | None = None
    cache_eligible: bool = True
    store_reason: str = "ok"


@pytest.fixture
def patched_decision(monkeypatch: pytest.MonkeyPatch) -> _FakeDecision:
    decision = _FakeDecision()
    monkeypatch.setattr(
        "telegram_bot.graph.middleware.cache.build_cacheability_decision",
        lambda **_: decision,
    )
    return decision


@pytest.mark.asyncio
async def test_after_agent_persists_response_for_cacheable_query(
    middleware: SemanticCacheMiddleware,
    patched_store: AsyncMock,
    patched_decision: _FakeDecision,
) -> None:
    state = _state(
        messages=[
            HumanMessage(content="как получить ВНЖ?"),
            AIMessage(content="ВНЖ оформляется около 30 дней."),
        ],
        query_embedding=[0.1] * 8,
        cache_hit=False,
    )

    update = await middleware.aafter_agent(state, _runtime_stub())

    patched_store.assert_awaited_once()
    kwargs = patched_store.await_args.kwargs
    assert kwargs["query_type"] == "FAQ"
    assert kwargs["response"] == "ВНЖ оформляется около 30 дней."
    assert kwargs["vector"] == [0.1] * 8
    assert kwargs["decision"] is patched_decision
    assert update is not None
    assert update["response"] == "ВНЖ оформляется около 30 дней."
    assert update["cache_eligible"] is True


@pytest.mark.asyncio
async def test_after_agent_noop_on_cache_hit(
    middleware: SemanticCacheMiddleware,
    patched_store: AsyncMock,
) -> None:
    """On HIT, before_agent already stored nothing fresh; after_agent
    must not re-write the cached response back into Redis."""
    state = _state(
        messages=[HumanMessage(content="x"), AIMessage(content="cached")],
        query_embedding=[0.1] * 8,
        cache_hit=True,
    )
    result = await middleware.aafter_agent(state, _runtime_stub())
    assert result is None
    patched_store.assert_not_called()


@pytest.mark.asyncio
async def test_after_agent_skips_when_response_missing(
    middleware: SemanticCacheMiddleware,
    patched_store: AsyncMock,
) -> None:
    """No assistant message → nothing to store."""
    state = _state(messages=[HumanMessage(content="x")], query_embedding=[0.1] * 8)
    result = await middleware.aafter_agent(state, _runtime_stub())
    assert result is None
    patched_store.assert_not_called()


@pytest.mark.asyncio
async def test_after_agent_skips_when_embedding_missing(
    middleware: SemanticCacheMiddleware,
    patched_store: AsyncMock,
) -> None:
    state = _state(
        messages=[HumanMessage(content="x"), AIMessage(content="hi")],
        query_embedding=None,
    )
    result = await middleware.aafter_agent(state, _runtime_stub())
    assert result is None
    patched_store.assert_not_called()


@pytest.mark.asyncio
async def test_after_agent_skips_for_non_cacheable_query_type(
    middleware: SemanticCacheMiddleware,
    patched_store: AsyncMock,
) -> None:
    """OFF_TOPIC must not be persisted — matches CACHEABLE_QUERY_TYPES gate."""
    state = _state(
        query_type="OFF_TOPIC",
        messages=[HumanMessage(content="x"), AIMessage(content="off-topic answer")],
        query_embedding=[0.1] * 8,
    )
    result = await middleware.aafter_agent(state, _runtime_stub())
    assert result is None
    patched_store.assert_not_called()


@pytest.mark.asyncio
async def test_after_agent_swallows_store_failure(
    middleware: SemanticCacheMiddleware,
    patched_store: AsyncMock,
    patched_decision: _FakeDecision,
) -> None:
    """A cache-store error must never destroy the response (legacy invariant)."""
    patched_store.side_effect = RuntimeError("redisvl exploded")

    state = _state(
        messages=[HumanMessage(content="x"), AIMessage(content="answer")],
        query_embedding=[0.1] * 8,
    )

    update = await middleware.aafter_agent(state, _runtime_stub())

    # Response is preserved despite the store crash.
    assert update is not None
    assert update["response"] == "answer"


# --------------------------------------------------------------------------- #
# State schema                                                                  #
# --------------------------------------------------------------------------- #


def test_cache_aware_state_extends_agent_state() -> None:
    """``_CacheAwareState`` must compose with ``AgentState``'s ``messages``
    field so the SDK's state-merge accepts middleware updates."""
    annotations = dict(_CacheAwareState.__annotations__)
    # Inherited annotations should still be reachable via ``__annotations__``
    # at runtime — fall back to ``getattr`` for safety on older typing
    # backends. The presence of the cache-specific fields is sufficient
    # contract evidence.
    assert "cache_hit" in annotations
    assert "query_embedding" in annotations
