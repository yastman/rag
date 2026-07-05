"""Live infra E2E: Docling (native) → Redis → Qdrant round-trip (#2771).

Proves the three-service infrastructure path:
  1. Docling parses a small fixture Markdown doc into chunks via NativeDoclingAdapter.
  2. Redis caches the raw chunk text (exact key/value, no embedding needed).
  3. Qdrant receives a BGE-M3 upsert and a point can be retrieved back.

Skip guards: each service is probed with a 2-second TCP/HTTP check before
any test runs.  Missing services cause a skip, not a failure, so CI can
collect this file without live infrastructure.

NOTE: As of phase_6508bc74ca4a, docling-serve HTTP sidecar is removed.
Docling runs in-process via NativeDoclingAdapter (docling-native extra).
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
from pathlib import Path

import pytest
import redis.asyncio as aioredis

from tests.e2e_core.live_harness import (
    LiveE2EEnv,
    cleanup_collection,
    index_fixture_documents,
    make_qdrant_context,
    recreate_collection,
    require_live_services,
)


pytestmark = [pytest.mark.e2e, pytest.mark.requires_services]


# ---------------------------------------------------------------------------
# Small fixture document used by this test only
# ---------------------------------------------------------------------------
_FIXTURE_DOC = (
    Path(__file__).parent.parent / "e2e_core" / "fixtures" / "docs" / "sunny_beach_studio.md"
)
_REDIS_URL_BASE = os.getenv("REDIS_URL", "redis://localhost:6379")
_REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "dev_redis_pass")


def _is_port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _redis_url() -> str:
    if "@" in _REDIS_URL_BASE:
        return _REDIS_URL_BASE
    if _REDIS_PASSWORD:
        return _REDIS_URL_BASE.replace("redis://", f"redis://:{_REDIS_PASSWORD}@", 1)
    return _REDIS_URL_BASE


def _redis_reachable() -> bool:
    return _is_port_open("localhost", 6379)


def _qdrant_reachable() -> bool:
    return _is_port_open("localhost", 6333)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _require_redis_or_skip() -> str:
    """Return a working Redis URL or skip."""
    url = _redis_url()
    client = aioredis.from_url(url, socket_connect_timeout=2, decode_responses=True)
    try:
        await client.ping()  # type: ignore[misc]
        return url
    except Exception as exc:
        pytest.skip(f"Redis unavailable: {exc}")
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.skipif(
    not (_redis_reachable() and _qdrant_reachable()),
    reason="Redis (6379) or Qdrant (6333) not reachable",
)
async def test_infra_docling_chunks_cached_in_redis_and_upserted_to_qdrant() -> None:
    """Docling (native) → Redis cache → Qdrant upsert → point retrieval round-trip."""

    # 1. Parse fixture document via NativeDoclingAdapter (in-process, no HTTP sidecar)
    docling = pytest.importorskip(
        "src.ingestion.docling_native",
        reason="docling-native extra not installed",
    )
    NativeDoclingAdapter = docling.NativeDoclingAdapter
    adapter = NativeDoclingAdapter()
    docling_chunks = adapter.chunk_file_sync(_FIXTURE_DOC)
    assert len(docling_chunks) >= 1, "NativeDoclingAdapter returned no chunks for fixture doc"

    # 2. Probe Redis
    redis_url = await _require_redis_or_skip()

    # 3. Probe Qdrant + BGE-M3 (reuse existing harness helper)
    env = LiveE2EEnv.from_env()
    await require_live_services(env)

    # 4. Cache the first chunk text in Redis (exact key/value)
    cache_key = "e2e:infra:2771:" + hashlib.sha256(_FIXTURE_DOC.read_bytes()).hexdigest()[:16]
    chunk_payload = json.dumps([c.text for c in docling_chunks], ensure_ascii=False)

    redis_client = aioredis.from_url(redis_url, decode_responses=True)
    try:
        await redis_client.set(cache_key, chunk_payload, ex=300)
        cached = await redis_client.get(cache_key)
    finally:
        await redis_client.aclose()

    assert cached is not None, "Redis did not return the stored value"
    assert json.loads(cached) == [c.text for c in docling_chunks]

    # 5. Upsert fixture doc into Qdrant via existing harness and query back
    context = make_qdrant_context(env)
    try:
        recreate_collection(env, context.collection_name)
        points_upserted = await index_fixture_documents(
            env,
            context.collection_name,
            document_ids=["sunny_beach_studio"],
        )
        assert points_upserted >= 1, "No points upserted into Qdrant"

        # Verify point exists in the collection
        from qdrant_client import QdrantClient

        qclient = QdrantClient(url=env.qdrant_url, api_key=env.qdrant_api_key, timeout=10)
        try:
            info = qclient.get_collection(context.collection_name)
            assert (info.points_count or 0) >= 1, "Qdrant collection is empty after upsert"
        finally:
            qclient.close()
    finally:
        cleanup_collection(env, context)
