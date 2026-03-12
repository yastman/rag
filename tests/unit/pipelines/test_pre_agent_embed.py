"""Tests for two-phase pre-agent embedding — Issue #954.

Phase 1: dense+sparse (no ColBERT) → cache check.
Phase 2: ColBERT only on cache miss.

Saves ~30-50ms ColBERT computation on every cache HIT.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_embeddings() -> MagicMock:
    emb = MagicMock()
    emb.aembed_hybrid = AsyncMock(return_value=([0.1, 0.2], {"indices": [1], "values": [0.5]}))
    emb.aembed_hybrid_with_colbert = AsyncMock(
        return_value=([0.1, 0.2], {"indices": [1], "values": [0.5]}, [[0.1, 0.2]])
    )
    emb.aembed_query = AsyncMock(return_value=[0.1, 0.2])
    return emb


@pytest.fixture
def mock_cache() -> MagicMock:
    cache = MagicMock()
    cache.get_embedding = AsyncMock(return_value=None)
    cache.get_sparse_embedding = AsyncMock(return_value=None)
    cache.store_embedding = AsyncMock()
    cache.store_sparse_embedding = AsyncMock()
    cache.check_semantic = AsyncMock(return_value=None)  # MISS by default
    return cache


async def test_phase1_uses_aembed_hybrid_not_colbert(
    mock_embeddings: MagicMock, mock_cache: MagicMock
) -> None:
    """Phase 1 uses aembed_hybrid (no ColBERT) for initial dense+sparse embed.

    On cache HIT colbert is never computed; on MISS phase 2 computes it.
    This test verifies the cache-HIT path: aembed_hybrid called, colbert never.
    """
    # Cache HIT — so phase 2 (ColBERT) is skipped entirely
    mock_cache.check_semantic = AsyncMock(return_value={"response": "cached"})

    from telegram_bot.pipelines.client import _pre_agent_embed_phases

    await _pre_agent_embed_phases(
        user_text="квартира в Варне",
        embeddings=mock_embeddings,
        cache=mock_cache,
        query_type="GENERAL",
        role="client",
    )

    # Phase 1: aembed_hybrid called (dense+sparse, no ColBERT)
    mock_embeddings.aembed_hybrid.assert_called_once_with("квартира в Варне")
    # ColBERT must NOT be computed on cache HIT
    mock_embeddings.aembed_hybrid_with_colbert.assert_not_called()


async def test_colbert_not_computed_on_cache_hit(
    mock_embeddings: MagicMock, mock_cache: MagicMock
) -> None:
    """ColBERT must NOT be computed when semantic cache returns a hit."""
    mock_cache.check_semantic = AsyncMock(return_value={"response": "Найдено 5 апартаментов"})

    from telegram_bot.pipelines.client import _pre_agent_embed_phases

    result = await _pre_agent_embed_phases(
        user_text="квартира у моря",
        embeddings=mock_embeddings,
        cache=mock_cache,
        query_type="GENERAL",
        role="client",
    )

    # ColBERT must not be computed on hit
    mock_embeddings.aembed_hybrid_with_colbert.assert_not_called()
    assert result["cache_hit"] is True
    assert result["colbert"] is None


async def test_colbert_computed_on_cache_miss(
    mock_embeddings: MagicMock, mock_cache: MagicMock
) -> None:
    """ColBERT must be computed on cache MISS so rag_pipeline can use it."""
    mock_cache.check_semantic = AsyncMock(return_value=None)  # MISS

    from telegram_bot.pipelines.client import _pre_agent_embed_phases

    result = await _pre_agent_embed_phases(
        user_text="трёшка с видом на море",
        embeddings=mock_embeddings,
        cache=mock_cache,
        query_type="GENERAL",
        role="client",
    )

    mock_embeddings.aembed_hybrid_with_colbert.assert_called_once_with("трёшка с видом на море")
    assert result["cache_hit"] is False
    assert result["colbert"] is not None


async def test_result_contains_embedding_and_sparse(
    mock_embeddings: MagicMock, mock_cache: MagicMock
) -> None:
    """Result dict must contain embedding and sparse keys for rag_result_store."""
    from telegram_bot.pipelines.client import _pre_agent_embed_phases

    result = await _pre_agent_embed_phases(
        user_text="студия в Несебре",
        embeddings=mock_embeddings,
        cache=mock_cache,
        query_type="FAQ",
        role="client",
    )

    assert "embedding" in result
    assert "sparse" in result
    assert result["embedding"] is not None


async def test_uses_cached_embedding_skips_api_call(
    mock_embeddings: MagicMock, mock_cache: MagicMock
) -> None:
    """When embedding is already cached, no embedding API call is made in phase 1."""
    mock_cache.get_embedding = AsyncMock(return_value=[0.3, 0.4])
    mock_cache.get_sparse_embedding = AsyncMock(return_value={"indices": [2], "values": [0.8]})
    mock_cache.check_semantic = AsyncMock(return_value=None)  # MISS → triggers phase 2

    from telegram_bot.pipelines.client import _pre_agent_embed_phases

    await _pre_agent_embed_phases(
        user_text="двушка с балконом",
        embeddings=mock_embeddings,
        cache=mock_cache,
        query_type="GENERAL",
        role="client",
    )

    # No phase-1 embedding call needed (already cached)
    mock_embeddings.aembed_hybrid.assert_not_called()
    # But ColBERT still computed on miss
    mock_embeddings.aembed_hybrid_with_colbert.assert_called_once()
