"""Tests for compute_query_embedding BGE-M3 bundle cache behaviour.

Covers the bundle-first path in telegram_bot.services.rag_core.
"""

from unittest.mock import AsyncMock, MagicMock

from telegram_bot.services.bge_m3_query_bundle import BgeM3QueryVectorBundle
from telegram_bot.services.rag_core import compute_query_embedding


class TestComputeQueryEmbeddingBundle:
    """Tests for compute_query_embedding bundle cache path."""

    async def test_bundle_cache_hit_returns_bundle_vectors(self):
        """Bundle cache hit returns dense, sparse, colbert and from_cache=True."""
        bundle = BgeM3QueryVectorBundle(
            dense=[0.1] * 1024,
            sparse={"indices": [1, 2], "values": [0.5, 0.6]},
            colbert=[[0.2] * 1024] * 4,
        )

        cache = AsyncMock()
        cache.get_bge_m3_query_bundle = AsyncMock(return_value=bundle)
        cache.get_embedding = AsyncMock(return_value=None)

        embeddings = AsyncMock()

        dense, sparse, colbert, from_cache = await compute_query_embedding(
            "test query", cache=cache, embeddings=embeddings
        )

        assert dense == bundle.dense
        assert sparse == bundle.sparse
        assert colbert == bundle.colbert
        assert from_cache is True
        cache.get_bge_m3_query_bundle.assert_awaited_once_with("test query")
        cache.get_embedding.assert_not_awaited()
        embeddings.aembed_hybrid_with_colbert.assert_not_awaited()

    async def test_bundle_cache_miss_computes_and_stores_bundle(self):
        """Bundle miss with aembed_hybrid_with_colbert computes, stores bundle + legacy."""
        cache = AsyncMock()
        cache.get_bge_m3_query_bundle = AsyncMock(return_value=None)
        cache.store_bge_m3_query_bundle = AsyncMock()
        cache.store_embedding = AsyncMock()
        cache.store_sparse_embedding = AsyncMock()

        dense_vec = [0.3] * 1024
        sparse_vec = {"indices": [1], "values": [0.8]}
        colbert_vec = [[0.4] * 1024] * 3

        embeddings = AsyncMock()
        embeddings.aembed_hybrid_with_colbert = AsyncMock(
            return_value=(dense_vec, sparse_vec, colbert_vec)
        )

        dense, sparse, colbert, from_cache = await compute_query_embedding(
            "test query", cache=cache, embeddings=embeddings
        )

        assert dense == dense_vec
        assert sparse == sparse_vec
        assert colbert == colbert_vec
        assert from_cache is False

        embeddings.aembed_hybrid_with_colbert.assert_awaited_once_with("test query")
        cache.store_bge_m3_query_bundle.assert_awaited_once()
        # Verify bundle contents
        stored_bundle = cache.store_bge_m3_query_bundle.call_args[0][1]
        assert isinstance(stored_bundle, BgeM3QueryVectorBundle)
        assert stored_bundle.dense == dense_vec
        assert stored_bundle.sparse == sparse_vec
        assert stored_bundle.colbert == colbert_vec

        # Legacy caches also populated
        cache.store_embedding.assert_awaited_once_with("test query", dense_vec)
        cache.store_sparse_embedding.assert_awaited_once_with("test query", sparse_vec)

    async def test_bundle_miss_without_store_api_still_computes(self):
        """Missing store_bge_m3_query_bundle still computes and returns colbert."""
        cache = AsyncMock(
            spec=[
                "get_bge_m3_query_bundle",
                "get_embedding",
                "store_embedding",
                "store_sparse_embedding",
            ]
        )
        cache.get_bge_m3_query_bundle = AsyncMock(return_value=None)
        cache.get_embedding = AsyncMock(return_value=None)
        cache.store_embedding = AsyncMock()
        cache.store_sparse_embedding = AsyncMock()

        dense_vec = [0.3] * 1024
        sparse_vec = {"indices": [1], "values": [0.8]}
        colbert_vec = [[0.4] * 1024] * 3

        embeddings = AsyncMock()
        embeddings.aembed_hybrid_with_colbert = AsyncMock(
            return_value=(dense_vec, sparse_vec, colbert_vec)
        )

        dense, sparse, colbert, from_cache = await compute_query_embedding(
            "test query", cache=cache, embeddings=embeddings
        )

        assert dense == dense_vec
        assert sparse == sparse_vec
        assert colbert == colbert_vec
        assert from_cache is False

        # store_bge_m3_query_bundle not called because API absent (spec excludes it)
        assert not hasattr(cache, "store_bge_m3_query_bundle")
        # But legacy caches still populated
        cache.store_embedding.assert_awaited_once()
        cache.store_sparse_embedding.assert_awaited_once()

    async def test_pre_computed_bypasses_bundle(self):
        """Pre-computed vectors bypass all cache and model calls."""
        cache = AsyncMock()
        embeddings = AsyncMock()
        pre_dense = [0.1] * 10
        pre_sparse = {"indices": [1], "values": [0.5]}
        pre_colbert = [[0.1] * 10]

        dense, sparse, colbert, from_cache = await compute_query_embedding(
            "query",
            cache=cache,
            embeddings=embeddings,
            pre_computed=pre_dense,
            pre_computed_sparse=pre_sparse,
            pre_computed_colbert=pre_colbert,
        )

        assert dense == pre_dense
        assert sparse == pre_sparse
        assert colbert == pre_colbert
        assert from_cache is False
        cache.get_bge_m3_query_bundle.assert_not_awaited()
        embeddings.aembed_hybrid_with_colbert.assert_not_awaited()

    async def test_legacy_dense_cache_when_no_bundle_api(self):
        """Cache without bundle API falls back to legacy dense cache."""
        cache = AsyncMock()
        cache.get_embedding = AsyncMock(return_value=[0.2] * 1024)
        # No get_bge_m3_query_bundle → _has_bundle_get checks getattr with default None
        # For AsyncMock, getattr returns AsyncMock, but we test with a real-ish object
        # that lacks the method.
        del cache.get_bge_m3_query_bundle

        embeddings = AsyncMock()

        dense, sparse, colbert, from_cache = await compute_query_embedding(
            "test query", cache=cache, embeddings=embeddings
        )

        assert dense == [0.2] * 1024
        assert sparse is None
        assert colbert is None
        assert from_cache is True
        cache.get_embedding.assert_awaited_once_with("test query")
        embeddings.aembed_hybrid_with_colbert.assert_not_awaited()

    async def test_legacy_dense_compute_when_no_hybrid_colbert(self):
        """Embeddings without aembed_hybrid_with_colbert falls back to legacy compute."""
        cache = AsyncMock()
        cache.get_embedding = AsyncMock(return_value=None)
        cache.store_embedding = AsyncMock()
        cache.store_sparse_embedding = AsyncMock()
        del cache.get_bge_m3_query_bundle

        dense_vec = [0.4] * 1024
        sparse_vec = {"indices": [2], "values": [0.9]}

        embeddings = MagicMock()
        embeddings.aembed_hybrid = AsyncMock(return_value=(dense_vec, sparse_vec))
        # aembed_hybrid_with_colbert not present

        dense, sparse, colbert, from_cache = await compute_query_embedding(
            "test query", cache=cache, embeddings=embeddings
        )

        assert dense == dense_vec
        assert sparse == sparse_vec
        assert colbert is None
        assert from_cache is False
        embeddings.aembed_hybrid.assert_awaited_once_with("test query")
        cache.store_embedding.assert_awaited_once_with("test query", dense_vec)
        cache.store_sparse_embedding.assert_awaited_once_with("test query", sparse_vec)

    async def test_bundle_hit_does_not_call_get_embedding(self):
        """Bundle cache hit must not touch legacy dense cache."""
        bundle = BgeM3QueryVectorBundle(
            dense=[0.1] * 1024,
            sparse={"indices": [1], "values": [0.5]},
            colbert=[[0.2] * 1024] * 4,
        )

        cache = AsyncMock()
        cache.get_bge_m3_query_bundle = AsyncMock(return_value=bundle)
        cache.get_embedding = AsyncMock(return_value=[0.99] * 1024)

        embeddings = AsyncMock()

        await compute_query_embedding("test query", cache=cache, embeddings=embeddings)

        cache.get_embedding.assert_not_awaited()

    async def test_bundle_store_exception_is_non_critical(self):
        """Bundle store failure must not raise or prevent returning vectors."""
        cache = AsyncMock()
        cache.get_bge_m3_query_bundle = AsyncMock(return_value=None)
        cache.store_bge_m3_query_bundle = AsyncMock(side_effect=RuntimeError("store failed"))
        cache.store_embedding = AsyncMock()
        cache.store_sparse_embedding = AsyncMock()

        dense_vec = [0.3] * 1024
        sparse_vec = {"indices": [1], "values": [0.8]}
        colbert_vec = [[0.4] * 1024] * 3

        embeddings = AsyncMock()
        embeddings.aembed_hybrid_with_colbert = AsyncMock(
            return_value=(dense_vec, sparse_vec, colbert_vec)
        )

        dense, sparse, colbert, from_cache = await compute_query_embedding(
            "test query", cache=cache, embeddings=embeddings
        )

        assert dense == dense_vec
        assert sparse == sparse_vec
        assert colbert == colbert_vec
        assert from_cache is False

    async def test_mock_without_real_bundle_support_falls_back_to_legacy(self):
        """Plain AsyncMock (no real bundle/colbert) falls back to legacy dense cache."""
        cache = AsyncMock()
        cache.get_embedding = AsyncMock(return_value=[0.5] * 1024)

        embeddings = AsyncMock()

        dense, sparse, colbert, from_cache = await compute_query_embedding(
            "test query", cache=cache, embeddings=embeddings
        )

        assert dense == [0.5] * 1024
        assert sparse is None
        assert colbert is None
        assert from_cache is True

    async def test_mock_without_real_bundle_and_no_legacy_cache_computes_dense(self):
        """Plain AsyncMock with cache miss falls back to aembed_query."""
        cache = AsyncMock()
        cache.get_embedding = AsyncMock(return_value=None)
        cache.store_embedding = AsyncMock()

        embeddings = AsyncMock(spec=["aembed_query"])
        embeddings.aembed_query = AsyncMock(return_value=[0.6] * 1024)

        dense, sparse, colbert, from_cache = await compute_query_embedding(
            "test query", cache=cache, embeddings=embeddings
        )

        assert dense == [0.6] * 1024
        assert sparse is None
        assert colbert is None
        assert from_cache is False
        embeddings.aembed_query.assert_awaited_once_with("test query")
