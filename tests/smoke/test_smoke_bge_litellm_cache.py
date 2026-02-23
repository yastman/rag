"""Additional smoke checks for critical service endpoints (#553)."""

from __future__ import annotations

import os
import socket

import httpx
import pytest


def _is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.mark.asyncio
@pytest.mark.skipif(not _is_port_open("localhost", 8000), reason="BGE-M3 not running (8000)")
async def test_bge_dense_health_contract():
    """BGE-M3 /encode/dense returns dense_vecs."""
    base_url = os.getenv("BGE_M3_URL", "http://localhost:8000").rstrip("/")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{base_url}/encode/dense", json={"texts": ["ping"]})
    assert resp.status_code == 200
    payload = resp.json()
    assert "dense_vecs" in payload
    assert isinstance(payload["dense_vecs"], list)


@pytest.mark.asyncio
@pytest.mark.skipif(not _is_port_open("localhost", 8000), reason="BGE-M3 not running (8000)")
async def test_bge_sparse_health_contract():
    """BGE-M3 /encode/sparse returns lexical_weights."""
    base_url = os.getenv("BGE_M3_URL", "http://localhost:8000").rstrip("/")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{base_url}/encode/sparse", json={"texts": ["ping"]})
    assert resp.status_code == 200
    payload = resp.json()
    assert "lexical_weights" in payload
    assert isinstance(payload["lexical_weights"], list)


@pytest.mark.asyncio
@pytest.mark.skipif(not _is_port_open("localhost", 8000), reason="BGE-M3 not running (8000)")
async def test_bge_hybrid_health_contract():
    """BGE-M3 /encode/hybrid returns both dense and sparse outputs."""
    base_url = os.getenv("BGE_M3_URL", "http://localhost:8000").rstrip("/")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{base_url}/encode/hybrid", json={"texts": ["ping"]})
    assert resp.status_code == 200
    payload = resp.json()
    assert "dense_vecs" in payload
    assert "lexical_weights" in payload


@pytest.mark.asyncio
@pytest.mark.skipif(not _is_port_open("localhost", 4000), reason="LiteLLM not running (4000)")
async def test_litellm_models_health():
    """LiteLLM proxy endpoint is reachable (200 or auth-required 401)."""
    base_url = os.getenv("LITELLM_URL", "http://localhost:4000").rstrip("/")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{base_url}/models")
    assert resp.status_code in {200, 401}
    if resp.status_code == 200:
        payload = resp.json()
        assert "data" in payload
        assert isinstance(payload["data"], list)


@pytest.mark.asyncio
async def test_semantic_cache_read_write_cycle(cache_service):
    """Semantic cache store+check roundtrip."""
    vector = [0.01] * 1024
    await cache_service.store_semantic(
        query="smoke ping query",
        response="smoke pong response",
        vector=vector,
        query_type="FAQ",
        user_id=553,
        cache_scope="smoke",
        agent_role="client",
    )

    cached = await cache_service.check_semantic(
        query="smoke ping query",
        vector=vector,
        query_type="FAQ",
        user_id=553,
        cache_scope="smoke",
        agent_role="client",
    )
    assert cached == "smoke pong response"


@pytest.mark.asyncio
async def test_qdrant_hybrid_search_execution(require_live_services, qdrant_service):
    """Qdrant hybrid search path executes without transport/shape errors."""
    try:
        info = await qdrant_service.client.get_collection(qdrant_service.collection_name)
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"Collection unavailable: {exc}")

    try:
        dense_cfg = info.config.params.vectors
        if isinstance(dense_cfg, dict):
            first = next(iter(dense_cfg.values()))
            dense_size = int(getattr(first, "size", 1024))
        else:
            dense_size = int(getattr(dense_cfg, "size", 1024))
    except Exception:
        dense_size = 1024

    results = await qdrant_service.hybrid_search_rrf(
        dense_vector=[0.0] * dense_size,
        sparse_vector=None,
        top_k=1,
    )
    assert isinstance(results, list)
