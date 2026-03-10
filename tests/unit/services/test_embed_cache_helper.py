"""Unit tests for telegram_bot/services/embed_cache_helper.py.

TDD: Tests written BEFORE implementation (issue #954).

Verifies that embed_and_store() fires cache.store_embedding and
cache.store_sparse_embedding as asyncio background tasks (fire-and-forget),
so they do not block the semantic cache check.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")

from telegram_bot.services.embed_cache_helper import embed_and_store


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cache(
    *,
    dense: list[float] | None = None,
    sparse: dict | None = None,
) -> MagicMock:
    """Return a mock CacheLayerManager."""
    cache = MagicMock()
    cache.get_embedding = AsyncMock(return_value=dense)
    cache.get_sparse_embedding = AsyncMock(return_value=sparse)
    cache.store_embedding = AsyncMock()
    cache.store_sparse_embedding = AsyncMock()
    return cache


def _make_embeddings(
    *,
    dense: list[float] | None = None,
    sparse: dict | None = None,
    colbert: list | None = None,
) -> MagicMock:
    """Return a mock embeddings service that supports aembed_hybrid_with_colbert."""
    emb = MagicMock()
    _dense = dense or [0.1, 0.2, 0.3]
    _sparse = sparse or {"indices": [1], "values": [0.5]}
    _colbert = colbert or [[0.1, 0.2]]
    emb.aembed_hybrid_with_colbert = AsyncMock(return_value=(_dense, _sparse, _colbert))
    emb.aembed_hybrid = AsyncMock(return_value=(_dense, _sparse))
    return emb


# ---------------------------------------------------------------------------
# embed_and_store — background task behaviour
# ---------------------------------------------------------------------------


class TestEmbedAndStoreBackgroundTasks:
    """store_embedding and store_sparse_embedding must be created as background tasks."""

    async def test_store_embedding_is_background_task_not_awaited_sequentially(self):
        """store_embedding must be fired as asyncio.create_task, not awaited inline."""
        created_tasks: list[asyncio.Task] = []

        original_create_task = asyncio.create_task

        def capturing_create_task(coro, **kwargs):
            task = original_create_task(coro, **kwargs)
            created_tasks.append(task)
            return task

        cache = _make_cache()
        embeddings = _make_embeddings()

        with patch("asyncio.create_task", side_effect=capturing_create_task):
            await embed_and_store(
                text="тест",
                cache=cache,
                embeddings=embeddings,
            )

        # At least one task created for store_embedding
        assert len(created_tasks) >= 1, "Expected at least one asyncio.create_task() call"
        # Wait for tasks to complete so teardown is clean
        await asyncio.gather(*created_tasks, return_exceptions=True)

        # store_embedding was eventually called (task ran)
        cache.store_embedding.assert_called_once()

    async def test_store_sparse_is_background_task_not_awaited_sequentially(self):
        """store_sparse_embedding must be fired as asyncio.create_task, not awaited inline."""
        created_tasks: list[asyncio.Task] = []

        original_create_task = asyncio.create_task

        def capturing_create_task(coro, **kwargs):
            task = original_create_task(coro, **kwargs)
            created_tasks.append(task)
            return task

        cache = _make_cache()
        embeddings = _make_embeddings()

        with patch("asyncio.create_task", side_effect=capturing_create_task):
            await embed_and_store(
                text="тест",
                cache=cache,
                embeddings=embeddings,
            )

        # At least two tasks (store_embedding + store_sparse_embedding)
        assert len(created_tasks) >= 2, "Expected create_task() for both store calls"
        await asyncio.gather(*created_tasks, return_exceptions=True)

        cache.store_sparse_embedding.assert_called_once()

    async def test_returns_dense_sparse_colbert_on_cache_miss(self):
        """On embedding cache miss, returns (dense, sparse, colbert) tuple."""
        dense = [0.1, 0.2, 0.3]
        sparse = {"indices": [0], "values": [1.0]}
        colbert = [[0.5, 0.6]]

        cache = _make_cache(dense=None, sparse=None)
        embeddings = _make_embeddings(dense=dense, sparse=sparse, colbert=colbert)

        tasks: list[asyncio.Task] = []
        orig = asyncio.create_task

        def _cap(coro, **kw):
            t = orig(coro, **kw)
            tasks.append(t)
            return t

        with patch("asyncio.create_task", side_effect=_cap):
            result = await embed_and_store(
                text="квартира",
                cache=cache,
                embeddings=embeddings,
            )

        await asyncio.gather(*tasks, return_exceptions=True)

        assert result["dense"] == dense
        assert result["sparse"] == sparse
        assert result["colbert"] == colbert
        assert result["from_cache"] is False

    async def test_returns_from_cache_on_embedding_cache_hit(self):
        """On embedding cache hit, from_cache=True and no embed call is made."""
        dense = [0.9, 0.8, 0.7]
        sparse = {"indices": [2], "values": [0.3]}

        cache = _make_cache(dense=dense, sparse=sparse)
        embeddings = _make_embeddings()

        result = await embed_and_store(
            text="кеш хит",
            cache=cache,
            embeddings=embeddings,
        )

        assert result["dense"] == dense
        assert result["sparse"] == sparse
        assert result["from_cache"] is True
        # No new embeddings computed
        embeddings.aembed_hybrid_with_colbert.assert_not_called()
        embeddings.aembed_hybrid.assert_not_called()
        # No store tasks needed when cache hit
        cache.store_embedding.assert_not_called()
        cache.store_sparse_embedding.assert_not_called()

    async def test_store_tasks_do_not_block_return(self):
        """embed_and_store returns before store tasks complete (fire-and-forget)."""
        import time

        slow_store_called = []

        async def _slow_store(*args, **kwargs):
            await asyncio.sleep(0.05)  # 50ms delay — would block if awaited
            slow_store_called.append(True)

        cache = _make_cache()
        cache.store_embedding = _slow_store
        cache.store_sparse_embedding = _slow_store
        embeddings = _make_embeddings()

        start = time.perf_counter()
        result = await embed_and_store(text="быстро", cache=cache, embeddings=embeddings)
        elapsed = time.perf_counter() - start

        # Should return well before the 50ms store delay
        assert elapsed < 0.04, (
            f"embed_and_store blocked for {elapsed * 1000:.1f}ms — stores not fire-and-forget"
        )
        assert result["dense"] is not None

        # Allow tasks to complete for clean teardown
        await asyncio.sleep(0.1)
        assert slow_store_called, "Store tasks should eventually run"

    async def test_sparse_only_cache_miss_triggers_reembed(self):
        """If dense is cached but sparse is None, re-embeds and stores sparse as background task."""
        dense = [0.1, 0.2]
        cache = _make_cache(dense=dense, sparse=None)

        new_sparse = {"indices": [5], "values": [0.8]}
        new_colbert = [[0.1]]
        embeddings = _make_embeddings(dense=dense, sparse=new_sparse, colbert=new_colbert)

        tasks: list[asyncio.Task] = []
        orig = asyncio.create_task

        def _cap(coro, **kw):
            t = orig(coro, **kw)
            tasks.append(t)
            return t

        with patch("asyncio.create_task", side_effect=_cap):
            result = await embed_and_store(
                text="частичный кеш",
                cache=cache,
                embeddings=embeddings,
            )

        await asyncio.gather(*tasks, return_exceptions=True)

        assert result["dense"] == dense  # from cache
        assert result["sparse"] == new_sparse  # freshly computed
        assert result["from_cache"] is False
        # store_sparse should have been called as task
        cache.store_sparse_embedding.assert_called_once()
        # store_embedding NOT called (dense was in cache)
        cache.store_embedding.assert_not_called()
