# QdrantService Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace legacy sync RetrieverService with async QdrantService featuring hybrid RRF search, score boosting, and MMR diversity.

**Architecture:** Bot generates dense (Voyage) + sparse (BM42) vectors for each query, executes hybrid RRF search in Qdrant, applies MMR for diversity, then Voyage rerank for final precision. All config parameters are externalized.

**Tech Stack:** qdrant-client (AsyncQdrantClient), fastembed (BM42), VoyageService, pytest

---

## Task 1: Add FastEmbed dependency

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add fastembed to dependencies**

In `pyproject.toml`, find the `dependencies` list and add:

```toml
dependencies = [
    # ... existing deps ...
    "fastembed>=0.3.0",
]
```

**Step 2: Install dependency**

Run: `pip install fastembed`

Expected: Successfully installed fastembed

**Step 3: Verify import works**

Run: `python3 -c "from fastembed import SparseTextEmbedding; print('OK')"`

Expected: `OK`

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add fastembed for BM42 sparse vectors"
```

---

## Task 2: Add hybrid search config parameters

**Files:**
- Modify: `telegram_bot/config.py:47-54`

**Step 1: Read current config**

Current config ends around line 54 with CESC settings.

**Step 2: Add new parameters after CESC section**

Add to `telegram_bot/config.py` after line 54:

```python
    # Hybrid Search Configuration
    hybrid_dense_weight: float = float(os.getenv("HYBRID_DENSE_WEIGHT", "0.6"))
    hybrid_sparse_weight: float = float(os.getenv("HYBRID_SPARSE_WEIGHT", "0.4"))

    # Score Boosting Configuration
    freshness_boost_enabled: bool = os.getenv("FRESHNESS_BOOST", "false").lower() == "true"
    freshness_field: str = os.getenv("FRESHNESS_FIELD", "created_at")
    freshness_scale_days: int = int(os.getenv("FRESHNESS_SCALE_DAYS", "30"))

    # MMR Diversity Configuration
    mmr_enabled: bool = os.getenv("MMR_ENABLED", "true").lower() == "true"
    mmr_lambda: float = float(os.getenv("MMR_LAMBDA", "0.7"))
```

**Step 3: Verify config loads**

Run: `python3 -c "from telegram_bot.config import BotConfig; c = BotConfig(); print(f'MMR lambda: {c.mmr_lambda}')"`

Expected: `MMR lambda: 0.7`

**Step 4: Commit**

```bash
git add telegram_bot/config.py
git commit -m "config: add hybrid search, score boosting, MMR parameters"
```

---

## Task 3: Write integration test for hybrid search in bot

**Files:**
- Create: `tests/test_bot_hybrid_search.py`

**Step 1: Write the failing test**

Create `tests/test_bot_hybrid_search.py`:

```python
"""Integration tests for bot hybrid search pipeline."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestBotHybridSearch:
    """Test bot uses QdrantService for hybrid search."""

    @pytest.mark.asyncio
    async def test_bot_initializes_qdrant_service(self):
        """Bot should initialize QdrantService instead of RetrieverService."""
        from telegram_bot.bot import PropertyBot
        from telegram_bot.config import BotConfig

        with patch("telegram_bot.bot.QdrantService") as mock_qdrant:
            with patch("telegram_bot.bot.VoyageService"):
                with patch("telegram_bot.bot.CacheService"):
                    with patch("telegram_bot.bot.LLMService"):
                        with patch("telegram_bot.bot.QueryAnalyzer"):
                            with patch("telegram_bot.bot.SparseTextEmbedding"):
                                config = BotConfig()
                                config.telegram_token = "test:token"
                                bot = PropertyBot(config)

                                mock_qdrant.assert_called_once()
                                assert hasattr(bot, "qdrant_service")

    @pytest.mark.asyncio
    async def test_bot_initializes_sparse_embedder(self):
        """Bot should initialize SparseTextEmbedding for BM42."""
        from telegram_bot.bot import PropertyBot
        from telegram_bot.config import BotConfig

        with patch("telegram_bot.bot.QdrantService"):
            with patch("telegram_bot.bot.VoyageService"):
                with patch("telegram_bot.bot.CacheService"):
                    with patch("telegram_bot.bot.LLMService"):
                        with patch("telegram_bot.bot.QueryAnalyzer"):
                            with patch("telegram_bot.bot.SparseTextEmbedding") as mock_sparse:
                                config = BotConfig()
                                config.telegram_token = "test:token"
                                bot = PropertyBot(config)

                                mock_sparse.assert_called_once_with(
                                    model_name="Qdrant/bm42-all-minilm-l6-v2-attentions"
                                )
                                assert hasattr(bot, "sparse_embedder")


class TestBotGetSparseVector:
    """Test sparse vector generation."""

    def test_get_sparse_vector_returns_dict(self):
        """_get_sparse_vector should return dict with indices and values."""
        from telegram_bot.bot import PropertyBot
        from telegram_bot.config import BotConfig

        with patch("telegram_bot.bot.QdrantService"):
            with patch("telegram_bot.bot.VoyageService"):
                with patch("telegram_bot.bot.CacheService"):
                    with patch("telegram_bot.bot.LLMService"):
                        with patch("telegram_bot.bot.QueryAnalyzer"):
                            with patch("telegram_bot.bot.SparseTextEmbedding") as mock_sparse:
                                # Mock sparse embedding result
                                mock_result = MagicMock()
                                mock_result.indices.tolist.return_value = [1, 5, 10]
                                mock_result.values.tolist.return_value = [0.5, 0.3, 0.2]
                                mock_sparse.return_value.embed.return_value = iter([mock_result])

                                config = BotConfig()
                                config.telegram_token = "test:token"
                                bot = PropertyBot(config)

                                result = bot._get_sparse_vector("test query")

                                assert "indices" in result
                                assert "values" in result
                                assert result["indices"] == [1, 5, 10]
                                assert result["values"] == [0.5, 0.3, 0.2]
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_bot_hybrid_search.py -v`

Expected: FAIL (bot.py doesn't have QdrantService yet)

---

## Task 4: Update bot.py imports

**Files:**
- Modify: `telegram_bot/bot.py:12-20`

**Step 1: Update imports**

Change the imports section in `telegram_bot/bot.py`:

```python
from fastembed import SparseTextEmbedding

from .config import BotConfig
from .middlewares import setup_error_middleware, setup_throttling_middleware
from .services import (
    CacheService,
    CESCPersonalizer,
    LLMService,
    QdrantService,
    QueryAnalyzer,
    UserContextService,
    VoyageService,
)
```

**Step 2: Verify imports work**

Run: `python3 -c "from telegram_bot.bot import PropertyBot; print('OK')"`

Expected: `OK`

**Step 3: Commit**

```bash
git add telegram_bot/bot.py
git commit -m "refactor(bot): update imports for QdrantService and FastEmbed"
```

---

## Task 5: Replace RetrieverService with QdrantService in __init__

**Files:**
- Modify: `telegram_bot/bot.py:50-54`

**Step 1: Replace service initialization**

In `telegram_bot/bot.py`, replace:

```python
        self.retriever_service = RetrieverService(
            url=config.qdrant_url,
            api_key=config.qdrant_api_key,
            collection_name=config.qdrant_collection,
        )
```

With:

```python
        # Qdrant service with hybrid search, score boosting, MMR
        self.qdrant_service = QdrantService(
            url=config.qdrant_url,
            api_key=config.qdrant_api_key,
            collection_name=config.qdrant_collection,
        )

        # BM42 sparse embedder for hybrid search
        self.sparse_embedder = SparseTextEmbedding(
            model_name="Qdrant/bm42-all-minilm-l6-v2-attentions"
        )
```

**Step 2: Run init tests**

Run: `python3 -m pytest tests/test_bot_hybrid_search.py::TestBotHybridSearch -v`

Expected: PASS (2 tests)

**Step 3: Commit**

```bash
git add telegram_bot/bot.py
git commit -m "refactor(bot): replace RetrieverService with QdrantService"
```

---

## Task 6: Add _get_sparse_vector method

**Files:**
- Modify: `telegram_bot/bot.py` (add method before _format_results)

**Step 1: Add helper method**

Add this method to PropertyBot class (before `_format_results`):

```python
    def _get_sparse_vector(self, text: str) -> dict:
        """Generate BM42 sparse vector for query.

        Args:
            text: Query text

        Returns:
            Dict with 'indices' and 'values' for Qdrant sparse vector
        """
        result = list(self.sparse_embedder.embed([text]))[0]
        return {
            "indices": result.indices.tolist(),
            "values": result.values.tolist(),
        }
```

**Step 2: Run sparse vector test**

Run: `python3 -m pytest tests/test_bot_hybrid_search.py::TestBotGetSparseVector -v`

Expected: PASS

**Step 3: Commit**

```bash
git add telegram_bot/bot.py
git commit -m "feat(bot): add _get_sparse_vector for BM42 embeddings"
```

---

## Task 7: Update handle_query search logic

**Files:**
- Modify: `telegram_bot/bot.py:210-235` (search section)

**Step 1: Replace search logic**

Replace the search section (lines 210-235) with:

```python
        # 4. Search in Qdrant with hybrid search
        results = await self.cache_service.get_cached_search(query_vector, filters)
        if results is None:
            # Generate sparse vector for hybrid search
            sparse_vector = self._get_sparse_vector(query)

            # Hybrid RRF search (dense + sparse)
            results = await self.qdrant_service.hybrid_search_rrf(
                dense_vector=query_vector,
                sparse_vector=sparse_vector,
                filters=filters if filters else None,
                top_k=self.config.search_top_k,
                dense_weight=self.config.hybrid_dense_weight,
                sparse_weight=self.config.hybrid_sparse_weight,
            )

            # MMR diversity reranking (if enabled and enough results)
            if self.config.mmr_enabled and len(results) > self.config.rerank_top_k:
                # Get embeddings for MMR calculation
                result_embeddings = [
                    await self.voyage_service.embed_query(r["text"])
                    for r in results[:20]  # Limit for performance
                ]
                results = self.qdrant_service.mmr_rerank(
                    points=results[:20],
                    embeddings=result_embeddings,
                    lambda_mult=self.config.mmr_lambda,
                    top_k=self.config.rerank_top_k * 2,
                )

            # Voyage rerank for final precision
            if results and len(results) > 1:
                doc_texts = [r["text"] for r in results]
                rerank_results = await self.voyage_service.rerank(
                    query=query,
                    documents=doc_texts,
                    top_k=self.config.rerank_top_k,
                )
                results = [results[r["index"]] for r in rerank_results]
                logger.info(f"Reranked to top {len(results)} results")

            await self.cache_service.store_search_results(query_vector, filters, results)
```

**Step 2: Run all bot tests**

Run: `python3 -m pytest tests/test_bot_hybrid_search.py -v`

Expected: PASS (all tests)

**Step 3: Commit**

```bash
git add telegram_bot/bot.py
git commit -m "feat(bot): implement hybrid RRF search with MMR diversity"
```

---

## Task 8: Add close method for QdrantService

**Files:**
- Modify: `telegram_bot/bot.py` (update close method if exists, or the cleanup)

**Step 1: Check if bot has cleanup**

Look for `async def close` or cleanup in bot.py.

**Step 2: Add QdrantService cleanup if needed**

If there's a close method, add:

```python
        await self.qdrant_service.close()
```

**Step 3: Commit if changes made**

```bash
git add telegram_bot/bot.py
git commit -m "fix(bot): add QdrantService cleanup"
```

---

## Task 9: Remove RetrieverService import from __init__.py

**Files:**
- Modify: `telegram_bot/services/__init__.py`

**Step 1: Check current state**

RetrieverService may still be exported. Check if it's needed elsewhere.

**Step 2: Keep or remove based on usage**

If only used in bot.py (now replaced), remove from exports. Otherwise keep for backward compatibility.

**Step 3: Commit if changes made**

```bash
git add telegram_bot/services/__init__.py
git commit -m "refactor: update service exports"
```

---

## Task 10: Run full test suite

**Files:**
- None (verification only)

**Step 1: Run all tests**

Run: `python3 -m pytest tests/test_voyage_service.py tests/test_qdrant_service.py tests/test_bot_hybrid_search.py -v`

Expected: All tests PASS

**Step 2: Run linting**

Run: `ruff check telegram_bot/bot.py`

Expected: No errors

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete QdrantService integration with hybrid search

- Hybrid RRF search (dense + sparse BM42)
- MMR diversity reranking (lambda=0.7)
- Configurable parameters via env vars
- Replaced legacy RetrieverService

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 11: Push and verify

**Step 1: Push changes**

Run: `git push`

**Step 2: Verify bot starts (if Docker available)**

Run: `docker compose -f docker-compose.dev.yml build bot && docker compose -f docker-compose.dev.yml up -d bot`

**Step 3: Check logs**

Run: `docker logs dev-bot --tail 20`

Expected: No import errors, services initialized

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Add FastEmbed dependency | `pyproject.toml` |
| 2 | Add config parameters | `config.py` |
| 3 | Write integration tests | `test_bot_hybrid_search.py` |
| 4 | Update bot imports | `bot.py` |
| 5 | Replace RetrieverService | `bot.py` |
| 6 | Add sparse vector method | `bot.py` |
| 7 | Update search logic | `bot.py` |
| 8 | Add cleanup | `bot.py` |
| 9 | Update exports | `__init__.py` |
| 10 | Run tests | verification |
| 11 | Push and verify | verification |

**Estimated commits:** 8-10
