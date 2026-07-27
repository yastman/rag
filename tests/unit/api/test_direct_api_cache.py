"""Direct local API cache transition tests."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


pytest.importorskip("fastapi", reason="src.api.main needs FastAPI; install --extra bge-extras")
pytestmark = pytest.mark.requires_extras

from src.api.main import app, query
from src.api.schemas import QueryRequest
from src.runtime.integrations.cache import CACHE_VERSION, CacheLayerManager
from src.runtime.llm.direct import DirectLiteLlmProvider


class _RedisSeam:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.get_keys: list[str] = []
        self.setex_calls: list[tuple[str, int, str]] = []

    async def get(self, key: str) -> str | None:
        self.get_keys.append(key)
        return self.values.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.setex_calls.append((key, ttl, value))
        self.values[key] = value


class _DirectGraph:
    def __init__(self, provider: DirectLiteLlmProvider) -> None:
        self.provider = provider

    async def ainvoke(self, state: dict) -> dict:
        await self.provider.acompletion(messages=[{"role": "user", "content": state["query"]}])
        return {
            "response": "cached answer",
            "query_type": "GENERAL",
            "cache_hit": False,
            "search_results_count": 1,
            "rerank_applied": False,
            "retrieved_context": [{"source": "local"}],
        }


async def test_direct_api_uses_redis_exact_cache_before_direct_litellm_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    namespace = f"issue-07-{uuid4().hex}"
    session_id = f"session-{uuid4().hex}"
    redis = _RedisSeam()
    cache = CacheLayerManager(redis_url="redis://unused")
    cache.redis = redis
    provider = DirectLiteLlmProvider()
    provider_call = AsyncMock(return_value=SimpleNamespace())
    monkeypatch.setattr(provider, "acompletion", provider_call)
    monkeypatch.setenv("LLM_BACKEND", "direct")
    monkeypatch.setattr(app.state, "graph", _DirectGraph(provider), raising=False)
    monkeypatch.setattr(app.state, "cache", cache, raising=False)
    monkeypatch.setattr(app.state, "api_cache_namespace", namespace, raising=False)
    monkeypatch.setattr(app.state, "max_rewrite_attempts", 1, raising=False)
    request = QueryRequest(query="exact local question", user_id=7, session_id=session_id)

    first = await query(request)
    second = await query(request)

    cache_key = f"api_response:{CACHE_VERSION}:{cache._api_response_key(namespace, session_id, request.query)}"
    assert cache._api_response_key(namespace, session_id, request.query) != cache._api_response_key(
        f"{namespace}-other", session_id, request.query
    )
    assert redis.get_keys == [cache_key, cache_key]
    assert len(redis.setex_calls) == 1
    assert redis.setex_calls[0][0] == cache_key
    assert json.loads(redis.setex_calls[0][2])["response"] == "cached answer"
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.answer == first.answer == "cached answer"
    provider_call.assert_awaited_once()


async def test_router_api_does_not_use_direct_response_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = SimpleNamespace(
        get_api_response=AsyncMock(),
        store_api_response=AsyncMock(),
    )
    graph = SimpleNamespace(
        ainvoke=AsyncMock(
            return_value={
                "response": "router answer",
                "query_type": "GENERAL",
                "cache_hit": False,
                "search_results_count": 1,
                "rerank_applied": False,
                "retrieved_context": [],
            }
        )
    )
    monkeypatch.setenv("LLM_BACKEND", "router")
    monkeypatch.setattr(app.state, "graph", graph, raising=False)
    monkeypatch.setattr(app.state, "cache", cache, raising=False)
    monkeypatch.setattr(app.state, "max_rewrite_attempts", 1, raising=False)
    request = QueryRequest(query="router question", user_id=7, session_id="router-session")

    await query(request)
    await query(request)

    cache.get_api_response.assert_not_awaited()
    cache.store_api_response.assert_not_awaited()
    assert graph.ainvoke.await_count == 2
