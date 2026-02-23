"""Chaos tests for Redis/BGE/Kommo resilience scenarios (#549)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from tenacity import wait_none

from telegram_bot.integrations.cache import CacheLayerManager
from telegram_bot.services.bge_m3_client import BGEM3Client
from telegram_bot.services.kommo_client import KommoClient


@pytest.mark.asyncio
async def test_semantic_cache_timeout_gracefully_bypasses():
    """Redis semantic cache timeout should return miss, not crash pipeline."""
    cache = CacheLayerManager(redis_url="redis://localhost:6379")
    cache.semantic_cache = AsyncMock()

    async def _slow_check(*args, **kwargs):
        await asyncio.sleep(0.05)
        return [{"response": "cached"}]

    cache.semantic_cache.acheck = AsyncMock(side_effect=_slow_check)

    cached = await cache.check_semantic(
        query="ping",
        vector=[0.01] * 1024,
        query_type="FAQ",
        cache_timeout=0.001,
    )
    assert cached is None


@pytest.mark.asyncio
async def test_semantic_cache_exception_gracefully_bypasses():
    """Redis semantic cache backend error should degrade to cache miss."""
    cache = CacheLayerManager(redis_url="redis://localhost:6379")
    cache.semantic_cache = AsyncMock()
    cache.semantic_cache.acheck = AsyncMock(side_effect=RuntimeError("redis unavailable"))

    cached = await cache.check_semantic(
        query="ping",
        vector=[0.01] * 1024,
        query_type="FAQ",
    )
    assert cached is None


@pytest.mark.asyncio
async def test_bge_timeout_retries_and_recovers():
    """BGE-M3 timeout should retry and recover when backend becomes available."""
    client = BGEM3Client(base_url="http://localhost:8000")

    ok_resp = MagicMock()
    ok_resp.status_code = 200
    ok_resp.raise_for_status = MagicMock()
    ok_resp.json.return_value = {"dense_vecs": [[0.1] * 1024]}

    mock_http = AsyncMock()
    mock_http.post = AsyncMock(
        side_effect=[
            httpx.ConnectTimeout("timeout-1"),
            httpx.ConnectTimeout("timeout-2"),
            ok_resp,
        ]
    )
    mock_http.is_closed = False
    client._client = mock_http

    with patch.object(client.encode_dense.retry, "wait", wait_none()):
        result = await client.encode_dense(["hello"])

    assert len(result.vectors) == 1
    assert mock_http.post.await_count == 3


@pytest.mark.asyncio
async def test_kommo_429_retries_then_succeeds():
    """Kommo 429 should retry with backoff and eventually succeed."""
    token_store = AsyncMock()
    token_store.get_valid_token = AsyncMock(return_value="token")
    token_store.force_refresh = AsyncMock(return_value="refreshed")
    client = KommoClient(subdomain="testcompany", token_store=token_store)

    req = httpx.Request("GET", "https://testcompany.kommo.com/api/v4/leads")
    resp_429 = httpx.Response(429, request=req)
    resp_200 = httpx.Response(
        200,
        json={"_embedded": {"leads": [{"id": 1, "name": "Lead A"}]}},
        request=req,
    )

    with (
        patch.object(client._request.retry, "wait", wait_none()),
        patch.object(client._client, "request", side_effect=[resp_429, resp_200]),
    ):
        leads = await client.search_leads(responsible_user_id=7, limit=5)

    assert len(leads) == 1
    assert leads[0].id == 1


@pytest.mark.asyncio
async def test_kommo_401_refreshes_token_and_recovers():
    """Kommo 401 should force token refresh and retry request."""
    token_store = AsyncMock()
    token_store.get_valid_token = AsyncMock(return_value="expired")
    token_store.force_refresh = AsyncMock(return_value="fresh-token")
    client = KommoClient(subdomain="testcompany", token_store=token_store)

    req = httpx.Request("GET", "https://testcompany.kommo.com/api/v4/leads")
    resp_401 = httpx.Response(401, request=req)
    resp_200 = httpx.Response(
        200,
        json={"_embedded": {"leads": [{"id": 2, "name": "Lead B"}]}},
        request=req,
    )

    with patch.object(client._client, "request", side_effect=[resp_401, resp_200]):
        leads = await client.search_leads(responsible_user_id=7, limit=5)

    assert len(leads) == 1
    assert leads[0].id == 2
    token_store.force_refresh.assert_awaited_once()
