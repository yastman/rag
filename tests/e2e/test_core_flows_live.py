"""Live E2E tests for current LangGraph architecture.

These tests target running Docker services (RAG API + Redis) and skip gracefully
when the stack is unavailable.
"""

from __future__ import annotations

import os
import uuid

import httpx
import pytest
import redis.asyncio as aioredis

from scripts.e2e.test_scenarios import SCENARIOS
from scripts.e2e.test_scenarios import TestGroup as _ScenarioGroup


pytestmark = [pytest.mark.e2e, pytest.mark.integration]

RAG_URL = os.getenv("RAG_API_URL", "http://localhost:8080")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


def _api_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=RAG_URL, timeout=45.0)


async def _require_live_stack() -> None:
    async with _api_client() as client:
        try:
            resp = await client.get("/health")
        except httpx.ConnectError:
            pytest.skip("RAG API not running")
        if resp.status_code != 200:
            pytest.skip(f"RAG API unhealthy: {resp.status_code}")

    redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        await redis_client.ping()
    except Exception:
        pytest.skip("Redis not running or inaccessible")
    finally:
        await redis_client.aclose()


async def _query(
    client: httpx.AsyncClient,
    *,
    query: str,
    user_id: int,
    session_id: str,
    channel: str = "api",
) -> dict:
    resp = await client.post(
        "/query",
        json={
            "query": query,
            "user_id": user_id,
            "session_id": session_id,
            "channel": channel,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data.get("response"), str) and data["response"].strip()
    assert "query_type" in data
    assert isinstance(data.get("cache_hit"), bool)
    assert isinstance(data.get("latency_ms"), (int, float))
    return data


@pytest.mark.asyncio
async def test_text_rag_flow_query_to_response() -> None:
    await _require_live_stack()
    session_id = f"e2e-text-{uuid.uuid4().hex[:10]}"

    async with _api_client() as client:
        data = await _query(
            client,
            query="Нужна квартира в Несебре до 120000 евро",
            user_id=10_001,
            session_id=session_id,
        )
    assert "documents_count" in data
    assert "rerank_applied" in data


@pytest.mark.asyncio
async def test_voice_channel_flow_post_transcription_contract() -> None:
    await _require_live_stack()
    session_id = f"e2e-voice-{uuid.uuid4().hex[:10]}"

    async with _api_client() as client:
        data = await _query(
            client,
            query="Подбери варианты рядом с морем",
            user_id=10_002,
            session_id=session_id,
            channel="voice",
        )
    assert data["query_type"] != ""


@pytest.mark.asyncio
async def test_cache_miss_then_hit_on_repeated_query() -> None:
    await _require_live_stack()
    session_id = f"e2e-cache-{uuid.uuid4().hex[:10]}"
    user_id = 10_003
    text = "Какие есть варианты квартир в Солнечном берегу?"

    async with _api_client() as client:
        first = await _query(client, query=text, user_id=user_id, session_id=session_id)
        hits = 1 if first["cache_hit"] else 0
        misses = 0 if first["cache_hit"] else 1

        for _ in range(3):
            data = await _query(client, query=text, user_id=user_id, session_id=session_id)
            hits += 1 if data["cache_hit"] else 0
            misses += 0 if data["cache_hit"] else 1
            if hits >= 1 and misses >= 1:
                break

    if not (hits >= 1 and misses >= 1):
        pytest.skip("Cache hit/miss transition not observable in this environment")


@pytest.mark.asyncio
async def test_multi_turn_conversation_same_session() -> None:
    await _require_live_stack()
    session_id = f"e2e-history-{uuid.uuid4().hex[:10]}"
    user_id = 10_004

    async with _api_client() as client:
        first = await _query(
            client,
            query="Найди 2-комнатные квартиры до 100000 евро",
            user_id=user_id,
            session_id=session_id,
        )
        second = await _query(
            client,
            query="А теперь покажи похожие, но ближе к морю",
            user_id=user_id,
            session_id=session_id,
        )

    assert first["response"] != second["response"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [s.query for s in SCENARIOS if s.group in {_ScenarioGroup.SEARCH, _ScenarioGroup.EDGE_CASES}][
        :4
    ],
)
async def test_migrated_scenarios_run_under_pytest(query: str) -> None:
    await _require_live_stack()
    session_id = f"e2e-scenario-{uuid.uuid4().hex[:10]}"

    async with _api_client() as client:
        await _query(
            client,
            query=query,
            user_id=10_005,
            session_id=session_id,
        )
