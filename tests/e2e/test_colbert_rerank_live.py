"""Live E2E: ColBERT+rerank is active in the full assistant pipeline.

card_9ddd100f0898: GAP #1 — un-stub ColBERT in the live harness.

Uses the EXISTING live collection (QDRANT_COLLECTION env var, default
'file_documents_bge') which has real ColBERT multivectors indexed.
Adds a ColBERT-enabled embeddings adapter (aembed_hybrid_with_colbert)
so the pipeline takes the ColBERT branch instead of the stubbed RRF path.

Verifies that:
  - QdrantService._colbert_available is True (colbert vector in collection)
  - The pipeline returns a grounded result (documents_count > 0)
  - rerank_applied is True on the AssistantResult (ColBERT MaxSim ran)
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from src.core.assistant import UserContext, run_assistant_request
from tests.e2e_core.live_harness import (
    FakeLLMConfig,
    LiveCoreHarness,
    LiveE2EEnv,
    NoopLiveCache,
    require_live_services,
)


pytestmark = [pytest.mark.e2e, pytest.mark.requires_services]


class _ColbertEnabledBGEEmbeddings:
    """BGE embeddings adapter WITH ColBERT support.

    Unlike LiveBGEEmbeddings (which omits aembed_hybrid_with_colbert so
    the pipeline skips the ColBERT branch), this adapter implements
    aembed_hybrid_with_colbert so the pipeline uses hybrid_search_rrf_colbert.
    """

    def __init__(self, base_url: str) -> None:
        from src.services.bge_m3_client import BGEM3Client

        self._client = BGEM3Client(base_url=base_url, timeout=120.0)

    async def aembed_hybrid(self, text: str) -> tuple[list[float], dict[str, Any]]:
        result = await self._client.encode_hybrid([text])
        return result.dense_vecs[0], result.lexical_weights[0]

    async def aembed_query(self, text: str) -> list[float]:
        result = await self._client.encode_dense([text])
        return result.vectors[0]

    async def aembed_hybrid_with_colbert(
        self,
        text: str,
    ) -> tuple[list[float], dict[str, Any], list[list[float]]]:
        """Return (dense, sparse_weights, colbert_vecs) in a single call.

        The pipeline calls this when the embeddings object exposes it,
        enabling the ColBERT branch (hybrid_search_rrf_colbert).
        """
        h_result = await self._client.encode_hybrid([text])
        c_result = await self._client.encode_colbert([text])
        dense = h_result.dense_vecs[0]
        sparse = h_result.lexical_weights[0]
        colbert = c_result.colbert_vecs[0] if c_result.colbert_vecs else []
        return dense, sparse, colbert

    async def aclose(self) -> None:
        await self._client.aclose()


class _SparseBGEEmbeddings:
    def __init__(self, base_url: str) -> None:
        from src.services.bge_m3_client import BGEM3Client

        self._client = BGEM3Client(base_url=base_url, timeout=120.0)

    async def aembed_query(self, text: str) -> dict[str, Any]:
        result = await self._client.encode_sparse([text])
        return result.weights[0]

    async def aclose(self) -> None:
        await self._client.aclose()


def _build_colbert_harness(
    env: LiveE2EEnv,
    collection_name: str,
) -> LiveCoreHarness:
    """Build CoreDependencies with ColBERT-enabled embeddings and existing collection."""
    from src.core.assistant import CoreDependencies
    from src.runtime.qdrant.service import QdrantService

    embeddings = _ColbertEnabledBGEEmbeddings(env.bge_m3_url)
    sparse_embeddings = _SparseBGEEmbeddings(env.bge_m3_url)
    qdrant = QdrantService(
        url=env.qdrant_url,
        api_key=env.qdrant_api_key,
        collection_name=collection_name,
        timeout=30,
        prefer_grpc=False,
    )

    # FakeLLM so no API key needed — we only test retrieval+rerank
    config = FakeLLMConfig()

    dependencies = CoreDependencies(
        cache=NoopLiveCache(),
        embeddings=embeddings,
        sparse_embeddings=sparse_embeddings,
        qdrant=qdrant,
        reranker=None,  # Qdrant-side ColBERT (server-side via hybrid_search_rrf_colbert)
        config=config,
    )

    async def _cleanup() -> None:
        await embeddings.aclose()
        await sparse_embeddings.aclose()
        await qdrant.close()

    return LiveCoreHarness(dependencies=dependencies, cleanup=_cleanup)


@pytest.mark.asyncio
async def test_colbert_rerank_active_in_full_pipeline() -> None:
    """ColBERT reranking is active in run_assistant_request with live collection.

    Uses the existing seeded collection (QDRANT_COLLECTION env var) which
    has real ColBERT multivectors. The _ColbertEnabledBGEEmbeddings adapter
    exposes aembed_hybrid_with_colbert so the pipeline takes the ColBERT branch.

    Asserts:
    - QdrantService._colbert_available is True
    - The pipeline returns a grounded result (documents_count > 0)
    - rerank_applied is True (ColBERT MaxSim ran via hybrid_search_rrf_colbert)
    """
    env = LiveE2EEnv.from_env()
    await require_live_services(env)

    collection_name = os.environ.get("QDRANT_COLLECTION", "file_documents_bge")
    harness: LiveCoreHarness | None = None

    try:
        harness = _build_colbert_harness(env, collection_name)

        # Probe collection capabilities — must have colbert vector
        qdrant_svc = harness.dependencies.qdrant
        await qdrant_svc.ensure_collection()  # type: ignore[attr-defined]
        assert qdrant_svc._colbert_available is True, (  # type: ignore[attr-defined]
            f"Collection '{collection_name}' must have a 'colbert' MultiVector. "
            f"qdrant_url={env.qdrant_url}"
        )

        result = await run_assistant_request(
            "What documents are available?",
            collection=collection_name,
            user_context=UserContext(
                user_id="e2e-colbert-test",
                session_id="e2e-colbert-test:colbert",
                role="client",
            ),
            dependencies=harness.dependencies,
        )

        assert result.error_type is None, f"Pipeline error: {result.error_message}"
        assert result.route == "rag_search", f"Unexpected route: {result.route}"
        assert result.documents_count > 0, "No documents retrieved"

        # ColBERT assertion: rerank must have run (Qdrant-side MaxSim)
        assert result.rerank_applied is True, (
            f"rerank_applied is False — ColBERT MaxSim did not run. "
            f"_colbert_available={qdrant_svc._colbert_available} "  # type: ignore[attr-defined]
            f"(check aembed_hybrid_with_colbert is available on embeddings)"
        )

    finally:
        if harness is not None:
            await harness.cleanup()
