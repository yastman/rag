"""Live E2E: ColBERT+rerank is active in the full assistant pipeline.

card_9ddd100f0898: GAP #1 — un-stub ColBERT in the live harness.

Verifies that:
  - AssistantResult.rerank_applied is True (ColBERT MaxSim ran)
  - QdrantService._colbert_available is True (collection has colbert vector)
  - The answer is grounded (documents_count > 0)
"""

from __future__ import annotations

import pytest

from src.core.assistant import UserContext, run_assistant_request
from tests.e2e_core.live_harness import (
    LiveBGEEmbeddings,
    LiveBGESparseEmbeddings,
    LiveCoreHarness,
    LiveE2EEnv,
    NoopLiveCache,
    cleanup_collection,
    index_fixture_documents,
    make_qdrant_context,
    recreate_collection,
    require_live_services,
)


pytestmark = [pytest.mark.e2e, pytest.mark.requires_services]


def _build_colbert_harness(
    env: LiveE2EEnv,
    collection_name: str,
) -> LiveCoreHarness:
    """Build CoreDependencies with ColBERT+rerank ENABLED (not stubbed).

    Unlike the default build_live_core_harness which sets reranker=None,
    this variant explicitly enables the ColBERT reranker by setting
    rerank_provider='colbert' in GraphConfig.
    """
    from src.core.assistant import CoreDependencies
    from src.runtime.graph.config import GraphConfig
    from src.runtime.qdrant.service import QdrantService

    embeddings = LiveBGEEmbeddings(env.bge_m3_url)
    sparse_embeddings = LiveBGESparseEmbeddings(env.bge_m3_url)
    qdrant = QdrantService(
        url=env.qdrant_url,
        api_key=env.qdrant_api_key,
        collection_name=collection_name,
        timeout=30,
        prefer_grpc=False,
    )

    # Explicit ColBERT config — NOT FakeLLMConfig, NOT reranker=None
    config = GraphConfig()
    config.rerank_provider = "colbert"  # enable ColBERT MaxSim reranking

    dependencies = CoreDependencies(
        cache=NoopLiveCache(),
        embeddings=embeddings,
        sparse_embeddings=sparse_embeddings,
        qdrant=qdrant,
        reranker=None,  # Qdrant-side ColBERT (server-side, via hybrid_search_rrf_colbert)
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

    Asserts:
    - QdrantService._colbert_available is True (colbert vector present in collection)
    - The pipeline returns a grounded result (documents_count > 0)
    - rerank_applied is True on the AssistantResult (ColBERT MaxSim ran)
    """
    env = LiveE2EEnv.from_env()
    await require_live_services(env)

    context = make_qdrant_context(env)
    harness: LiveCoreHarness | None = None

    try:
        recreate_collection(env, context.collection_name)
        indexed_points = await index_fixture_documents(
            env,
            context.collection_name,
            document_ids=None,  # all fixture docs
        )
        assert indexed_points >= 1, f"Expected at least 1 indexed point, got {indexed_points}"

        harness = _build_colbert_harness(env, context.collection_name)

        # Ensure QdrantService probes the collection for ColBERT capability
        qdrant_svc = harness.dependencies.qdrant
        await qdrant_svc.ensure_collection()  # type: ignore[attr-defined]
        assert qdrant_svc._colbert_available is True, (  # type: ignore[attr-defined]
            "Collection must have a 'colbert' MultiVector — "
            "re-index with ColBERT-enabled writer (not _NoColbertQdrantHybridWriter)"
        )

        result = await run_assistant_request(
            "What are the available apartments?",
            collection=context.collection_name,
            user_context=UserContext(
                user_id="e2e-colbert-test",
                session_id=f"{context.collection_name}:colbert",
                role="client",
            ),
            dependencies=harness.dependencies,
        )

        assert result.error_type is None, f"Pipeline error: {result.error_message}"
        assert result.route == "rag_search", f"Unexpected route: {result.route}"
        assert result.documents_count > 0, "No documents retrieved"

        # ColBERT-specific assertion: rerank must have run
        assert getattr(result, "rerank_applied", None) is True, (
            "rerank_applied is not True — ColBERT MaxSim did not run. "
            "Check that QdrantService.hybrid_search_rrf_colbert was called "
            "and that _colbert_available is True."
        )

    finally:
        if harness is not None:
            await harness.cleanup()
        cleanup_collection(env, context)
