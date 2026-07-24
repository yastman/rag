"""Live binary-quantization lifecycle: setup -> ingest -> hybrid RRF search.

Requires Qdrant and BGE-M3. Run with ``RUN_INTEGRATION_TESTS=1``.
"""

from __future__ import annotations

import os
from dataclasses import replace

import pytest

from scripts.setup_binary_collection import get_binary_collection_name, setup_binary_collection
from tests.e2e_core.live_harness import (
    LiveE2EEnv,
    build_live_core_harness,
    cleanup_collection,
    index_fixture_documents,
    make_qdrant_context,
    require_live_services,
)


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.requires_services,
    pytest.mark.skipif(
        not os.getenv("RUN_INTEGRATION_TESTS"),
        reason="Set RUN_INTEGRATION_TESTS=1 to run binary quantization live E2E tests",
    ),
]


@pytest.mark.asyncio
async def test_binary_collection_ingest_and_hybrid_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A binary collection accepts real ingestion and returns an RRF result."""
    env = LiveE2EEnv.from_env()
    await require_live_services(env)
    monkeypatch.setenv("QDRANT_URL", env.qdrant_url)
    if env.qdrant_api_key:
        monkeypatch.setenv("QDRANT_API_KEY", env.qdrant_api_key)
    else:
        monkeypatch.delenv("QDRANT_API_KEY", raising=False)

    context = make_qdrant_context(env)
    collection_name = get_binary_collection_name(context.collection_name)
    harness = None

    try:
        assert setup_binary_collection(context.collection_name), "Binary collection setup failed"

        indexed_points = await index_fixture_documents(
            env,
            collection_name,
            document_ids=["sunny_beach_studio", "sunny_beach_2bed"],
        )
        assert indexed_points >= 2

        harness = build_live_core_harness(env, collection_name)
        dense_vector, sparse_vector = await harness.dependencies.embeddings.aembed_hybrid(
            "Sunny Beach studio near the sea"
        )
        results = await harness.dependencies.qdrant.hybrid_search_rrf(
            dense_vector,
            sparse_vector,
            top_k=2,
        )

        assert results
        assert results[0]["metadata"]["file_name"] in {
            "sunny_beach_studio.md",
            "sunny_beach_2bed.md",
        }
    finally:
        if harness is not None:
            await harness.aclose()
        cleanup_collection(env, replace(context, collection_name=collection_name))
