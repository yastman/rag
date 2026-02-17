"""Integration tests for voice pipeline (requires Docker voice profile)."""

from __future__ import annotations

import httpx
import pytest


RAG_URL = "http://localhost:8080"


@pytest.mark.integration
async def test_rag_api_health():
    """RAG API should return healthy status."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{RAG_URL}/health", timeout=5.0)
        except httpx.ConnectError:
            pytest.skip("RAG API not running")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


@pytest.mark.integration
async def test_rag_api_query():
    """RAG API should return a response for a query."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{RAG_URL}/query",
                json={"query": "тестовый запрос", "channel": "api"},
                timeout=30.0,
            )
        except httpx.ConnectError:
            pytest.skip("RAG API not running")
        assert resp.status_code == 200
        data = resp.json()
        assert "response" in data
        assert "query_type" in data
        assert "latency_ms" in data


@pytest.mark.integration
async def test_livekit_server_health():
    """LiveKit server should be running."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get("http://localhost:7880", timeout=5.0)
            # LiveKit returns 200 on root
            assert resp.status_code in (200, 404)
        except httpx.ConnectError:
            pytest.skip("LiveKit server not running")
