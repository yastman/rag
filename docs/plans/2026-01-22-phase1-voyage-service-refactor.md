# Phase 1: Voyage Service Refactoring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Consolidate voyage_client.py, voyage_embeddings.py, voyage_reranker.py into a unified voyage.py with tenacity retries and asyncio.to_thread

**Architecture:** Smart Gateway pattern - single entry point for all Voyage AI operations with proper async support, batching, and retry logic per official Voyage AI documentation

**Tech Stack:** Python 3.12, voyageai SDK, tenacity, asyncio, pytest

---

## Pre-Implementation Checklist

- [ ] Ensure Docker services are running: `make docker-up`
- [ ] Run existing tests to verify baseline: `pytest tests/test_voyage*.py -v`
- [ ] Verify VOYAGE_API_KEY is set in environment

---

## Task 1: Create VoyageService Tests (TDD)

**Files:**
- Create: `tests/test_voyage_service.py`

**Step 1: Write failing tests for VoyageService**

```python
"""Tests for unified VoyageService."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest


class TestVoyageServiceUnit:
    """Unit tests for VoyageService (no API calls)."""

    def test_init_creates_client_with_api_key(self):
        """Test initialization creates voyageai.Client."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client") as mock_client_class:
            service = VoyageService(api_key="test-key")

            mock_client_class.assert_called_once_with(api_key="test-key")
            assert service._model_docs == "voyage-4-large"
            assert service._model_queries == "voyage-4-lite"
            assert service._model_rerank == "rerank-2.5"

    def test_init_with_custom_models(self):
        """Test initialization with custom model names."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client"):
            service = VoyageService(
                api_key="test-key",
                model_docs="voyage-3-large",
                model_queries="voyage-3-lite",
                model_rerank="rerank-2",
            )

            assert service._model_docs == "voyage-3-large"
            assert service._model_queries == "voyage-3-lite"
            assert service._model_rerank == "rerank-2"

    @pytest.mark.asyncio
    async def test_embed_documents_batches_large_input(self):
        """Test embed_documents splits into batches of 128."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client") as mock_client_class:
            mock_client = MagicMock()
            # Return different embeddings for each batch
            mock_client.embed.return_value = MagicMock(
                embeddings=[[0.1] * 1024] * 128
            )
            mock_client_class.return_value = mock_client

            service = VoyageService(api_key="test-key")

            # 200 texts should result in 2 batches (128 + 72)
            texts = [f"text_{i}" for i in range(200)]
            result = await service.embed_documents(texts)

            # Should be called twice (2 batches)
            assert mock_client.embed.call_count == 2
            # First batch: 128 texts
            first_call = mock_client.embed.call_args_list[0]
            assert len(first_call[1]["texts"]) == 128
            # Second batch: 72 texts
            second_call = mock_client.embed.call_args_list[1]
            assert len(second_call[1]["texts"]) == 72

    @pytest.mark.asyncio
    async def test_embed_documents_uses_document_model(self):
        """Test embed_documents uses model_docs."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
            mock_client_class.return_value = mock_client

            service = VoyageService(api_key="test-key", model_docs="voyage-4-large")
            await service.embed_documents(["test"])

            call_kwargs = mock_client.embed.call_args[1]
            assert call_kwargs["model"] == "voyage-4-large"
            assert call_kwargs["input_type"] == "document"

    @pytest.mark.asyncio
    async def test_embed_query_uses_query_model(self):
        """Test embed_query uses model_queries (asymmetric retrieval)."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
            mock_client_class.return_value = mock_client

            service = VoyageService(api_key="test-key", model_queries="voyage-4-lite")
            await service.embed_query("test query")

            call_kwargs = mock_client.embed.call_args[1]
            assert call_kwargs["model"] == "voyage-4-lite"
            assert call_kwargs["input_type"] == "query"

    @pytest.mark.asyncio
    async def test_embed_documents_empty_list(self):
        """Test embed_documents with empty list returns empty."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client"):
            service = VoyageService(api_key="test-key")
            result = await service.embed_documents([])

            assert result == []

    @pytest.mark.asyncio
    async def test_rerank_returns_formatted_results(self):
        """Test rerank returns list of dicts with index and score."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_result = MagicMock()
            mock_result.index = 1
            mock_result.relevance_score = 0.95
            mock_result.document = "doc1"
            mock_client.rerank.return_value = MagicMock(results=[mock_result])
            mock_client_class.return_value = mock_client

            service = VoyageService(api_key="test-key")
            result = await service.rerank("query", ["doc0", "doc1"])

            assert len(result) == 1
            assert result[0]["index"] == 1
            assert result[0]["relevance_score"] == 0.95
            assert result[0]["document"] == "doc1"

    @pytest.mark.asyncio
    async def test_rerank_empty_documents(self):
        """Test rerank with empty documents returns empty list."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client"):
            service = VoyageService(api_key="test-key")
            result = await service.rerank("query", [])

            assert result == []

    @pytest.mark.asyncio
    async def test_rerank_uses_rerank_model(self):
        """Test rerank uses model_rerank."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.rerank.return_value = MagicMock(results=[])
            mock_client_class.return_value = mock_client

            service = VoyageService(api_key="test-key", model_rerank="rerank-2.5")
            await service.rerank("query", ["doc"])

            call_kwargs = mock_client.rerank.call_args[1]
            assert call_kwargs["model"] == "rerank-2.5"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_voyage_service.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'telegram_bot.services.voyage'"

**Step 3: Commit test file**

```bash
git add tests/test_voyage_service.py
git commit -m "test: add failing tests for unified VoyageService

TDD approach - tests define expected interface:
- embed_documents with batching (128)
- embed_query with asymmetric model (voyage-4-lite)
- rerank with structured output
- Empty input handling

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Create VoyageService Implementation

**Files:**
- Create: `telegram_bot/services/voyage.py`

**Step 1: Write VoyageService implementation**

```python
"""Unified Voyage AI service for embeddings and reranking.

Smart Gateway pattern - single entry point for all Voyage AI operations.
Validated by: Voyage AI official documentation (January 2026)
"""

import asyncio
import logging
from typing import List, Optional

import voyageai
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

logger = logging.getLogger(__name__)


class VoyageService:
    """Unified Smart Gateway for Voyage AI.

    Provides:
    - Embeddings for documents (voyage-4-large by default)
    - Embeddings for queries (voyage-4-lite by default, asymmetric retrieval)
    - Reranking (rerank-2.5 by default, 32K context)

    Features:
    - Automatic batching (128 texts per request)
    - Retry with exponential backoff (6 attempts, official recommendation)
    - asyncio.to_thread for non-blocking async calls
    """

    # Batch size for embeddings (Voyage AI recommendation)
    BATCH_SIZE = 128

    def __init__(
        self,
        api_key: str,
        model_docs: str = "voyage-4-large",
        model_queries: str = "voyage-4-lite",
        model_rerank: str = "rerank-2.5",
    ):
        """Initialize Voyage service.

        Args:
            api_key: Voyage AI API key
            model_docs: Model for document embeddings (indexed once)
            model_queries: Model for query embeddings (used continuously)
            model_rerank: Model for reranking (32K context with rerank-2.5)

        Asymmetric Retrieval:
            Documents are embedded with voyage-4-large (high quality, one-time cost).
            Queries are embedded with voyage-4-lite (fast, cheap, continuous).
            Shared embedding space makes this possible.
        """
        self._client = voyageai.Client(api_key=api_key)
        self._model_docs = model_docs
        self._model_queries = model_queries
        self._model_rerank = model_rerank
        logger.info(
            f"VoyageService initialized: docs={model_docs}, "
            f"queries={model_queries}, rerank={model_rerank}"
        )

    @retry(
        retry=retry_if_exception_type(
            (
                voyageai.error.RateLimitError,
                voyageai.error.ServiceUnavailableError,
                voyageai.error.TimeoutError,
            )
        ),
        wait=wait_random_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(6),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    async def embed_documents(
        self,
        texts: List[str],
        input_type: str = "document",
    ) -> List[List[float]]:
        """Generate embeddings for documents with automatic batching.

        Uses voyage-4-large by default for maximum quality.
        Documents are typically indexed once, so quality matters more than speed.

        Args:
            texts: List of document texts to embed
            input_type: Voyage input type ("document" or "query")

        Returns:
            List of embedding vectors (1024-dim for voyage-4-large)
        """
        if not texts:
            return []

        all_embeddings = []

        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i : i + self.BATCH_SIZE]

            # asyncio.to_thread for non-blocking async (best practice)
            response = await asyncio.to_thread(
                self._client.embed,
                texts=batch,
                model=self._model_docs,
                input_type=input_type,
            )
            all_embeddings.extend(response.embeddings)

        logger.info(f"Embedded {len(all_embeddings)} documents with {self._model_docs}")
        return all_embeddings

    @retry(
        retry=retry_if_exception_type(
            (
                voyageai.error.RateLimitError,
                voyageai.error.ServiceUnavailableError,
                voyageai.error.TimeoutError,
            )
        ),
        wait=wait_random_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(6),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    async def embed_query(self, text: str) -> List[float]:
        """Generate embedding for a single query.

        Uses voyage-4-lite by default for fast, cheap embeddings.
        Queries are processed continuously, so speed matters.

        Asymmetric retrieval: voyage-4-lite queries can search
        voyage-4-large document index (shared embedding space).

        Args:
            text: Query text to embed

        Returns:
            Single embedding vector
        """
        response = await asyncio.to_thread(
            self._client.embed,
            texts=[text],
            model=self._model_queries,
            input_type="query",
        )
        return response.embeddings[0]

    @retry(
        retry=retry_if_exception_type(
            (
                voyageai.error.RateLimitError,
                voyageai.error.ServiceUnavailableError,
            )
        ),
        wait=wait_random_exponential(multiplier=1, max=10),
        stop=stop_after_attempt(3),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: Optional[int] = None,
    ) -> List[dict]:
        """Rerank documents by relevance to query.

        Uses rerank-2.5 by default (32K context window).

        Args:
            query: Search query
            documents: List of document texts to rerank
            top_k: Number of top results to return (None = all)

        Returns:
            List of dicts with 'index', 'relevance_score', 'document' keys,
            sorted by relevance (highest first).
        """
        if not documents:
            return []

        response = await asyncio.to_thread(
            self._client.rerank,
            query=query,
            documents=documents,
            model=self._model_rerank,
            top_k=top_k,
        )

        return [
            {
                "index": r.index,
                "relevance_score": r.relevance_score,
                "document": r.document,
            }
            for r in response.results
        ]

    # Sync methods for compatibility with existing code
    def embed_documents_sync(
        self,
        texts: List[str],
        input_type: str = "document",
    ) -> List[List[float]]:
        """Sync wrapper for embed_documents."""
        return asyncio.run(self.embed_documents(texts, input_type))

    def embed_query_sync(self, text: str) -> List[float]:
        """Sync wrapper for embed_query."""
        return asyncio.run(self.embed_query(text))

    def rerank_sync(
        self,
        query: str,
        documents: List[str],
        top_k: Optional[int] = None,
    ) -> List[dict]:
        """Sync wrapper for rerank."""
        return asyncio.run(self.rerank(query, documents, top_k))
```

**Step 2: Run tests to verify they pass**

Run: `pytest tests/test_voyage_service.py -v`
Expected: PASS (all 9 tests)

**Step 3: Commit implementation**

```bash
git add telegram_bot/services/voyage.py
git commit -m "feat: add unified VoyageService with tenacity retries

Smart Gateway pattern for Voyage AI:
- embed_documents: batching (128), voyage-4-large
- embed_query: asymmetric retrieval, voyage-4-lite
- rerank: rerank-2.5 with 32K context
- tenacity retries per official Voyage AI docs
- asyncio.to_thread for non-blocking async

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Update Services __init__.py

**Files:**
- Modify: `telegram_bot/services/__init__.py`

**Step 1: Add VoyageService to exports**

```python
"""Services for Telegram RAG bot."""

from .cache import CacheService
from .cesc import CESCPersonalizer
from .embeddings import EmbeddingService
from .hybrid_retriever import HybridRetrieverService
from .llm import LLMService
from .query_analyzer import QueryAnalyzer
from .query_preprocessor import QueryPreprocessor
from .retriever import RetrieverService
from .user_context import UserContextService
from .voyage import VoyageService
from .voyage_client import VoyageClient
from .voyage_embeddings import VoyageEmbeddingService
from .voyage_reranker import VoyageRerankerService


__all__ = [
    "CESCPersonalizer",
    "CacheService",
    "EmbeddingService",
    "HybridRetrieverService",
    "LLMService",
    "QueryAnalyzer",
    "QueryPreprocessor",
    "RetrieverService",
    "UserContextService",
    "VoyageClient",
    "VoyageEmbeddingService",
    "VoyageRerankerService",
    "VoyageService",  # NEW: unified service
]
```

**Step 2: Run all voyage tests to verify no regressions**

Run: `pytest tests/test_voyage*.py -v`
Expected: PASS (all tests including new ones)

**Step 3: Commit update**

```bash
git add telegram_bot/services/__init__.py
git commit -m "feat: export VoyageService from services module

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Add Backward Compatibility Tests

**Files:**
- Modify: `tests/test_voyage_service.py`

**Step 1: Add backward compatibility tests**

```python
class TestVoyageServiceBackwardCompatibility:
    """Tests to ensure VoyageService can replace existing services."""

    @pytest.mark.asyncio
    async def test_can_replace_voyage_embedding_service(self):
        """Test VoyageService provides same interface as VoyageEmbeddingService."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
            mock_client_class.return_value = mock_client

            ***REMOVED***Service should have same methods as VoyageEmbeddingService
            service = VoyageService(api_key="test-key")

            # embed_query (async) - primary method used in bot.py
            result = await service.embed_query("test")
            assert len(result) == 1024

            # embed_documents (async) - used for indexing
            result = await service.embed_documents(["test"])
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_can_replace_voyage_reranker_service(self):
        """Test VoyageService provides same interface as VoyageRerankerService."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_result = MagicMock()
            mock_result.index = 0
            mock_result.relevance_score = 0.9
            mock_result.document = "doc"
            mock_client.rerank.return_value = MagicMock(results=[mock_result])
            mock_client_class.return_value = mock_client

            service = VoyageService(api_key="test-key")

            # rerank (async) - primary method used in bot.py
            result = await service.rerank("query", ["doc"])
            assert len(result) == 1
            assert "relevance_score" in result[0]

    def test_sync_methods_work(self):
        """Test sync wrappers for non-async code."""
        from telegram_bot.services.voyage import VoyageService

        with patch("voyageai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
            mock_client_class.return_value = mock_client

            service = VoyageService(api_key="test-key")

            # embed_query_sync
            result = service.embed_query_sync("test")
            assert len(result) == 1024

            # embed_documents_sync
            result = service.embed_documents_sync(["test"])
            assert len(result) == 1
```

**Step 2: Run tests**

Run: `pytest tests/test_voyage_service.py::TestVoyageServiceBackwardCompatibility -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_voyage_service.py
git commit -m "test: add backward compatibility tests for VoyageService

Ensures VoyageService can replace:
- VoyageEmbeddingService
- VoyageRerankerService

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Run Full Test Suite

**Files:**
- None (validation only)

**Step 1: Run all tests**

Run: `pytest tests/ -v --tb=short`
Expected: PASS (all tests)

**Step 2: Run type checking**

Run: `make type-check`
Expected: No errors in voyage.py

**Step 3: Run linting**

Run: `make lint`
Expected: No errors

---

## Task 6: Update bot.py to Use VoyageService (Optional)

> **Note:** This task is optional for Phase 1. Can be deferred to Phase 2 when we switch to voyage-4 models.

**Files:**
- Modify: `telegram_bot/bot.py`

**Step 1: Replace VoyageEmbeddingService and VoyageRerankerService**

Change lines 44-51 from:
```python
***REMOVED*** AI embeddings (replaces BGE-M3)
self.embedding_service = VoyageEmbeddingService(model=config.voyage_embed_model)
...
***REMOVED*** AI reranker for better relevance
self.reranker_service = VoyageRerankerService(model=config.voyage_rerank_model)
```

To:
```python
***REMOVED*** AI unified service (embeddings + reranker)
self.voyage_service = VoyageService(
    api_key=config.voyage_api_key,
    model_docs=config.voyage_model_docs,
    model_queries=config.voyage_model_queries,
    model_rerank=config.voyage_model_rerank,
)
```

**Step 2: Update handle_query to use VoyageService**

Change embedding call from:
```python
query_vector = await self.embedding_service.embed_query(query)
```

To:
```python
query_vector = await self.voyage_service.embed_query(query)
```

Change rerank call from:
```python
results = await self.reranker_service.rerank(...)
```

To:
```python
rerank_results = await self.voyage_service.rerank(...)
```

---

## Summary

| Task | Description | Status |
|------|-------------|--------|
| 1 | Create VoyageService tests (TDD) | Pending |
| 2 | Implement VoyageService | Pending |
| 3 | Update __init__.py exports | Pending |
| 4 | Add backward compatibility tests | Pending |
| 5 | Run full test suite | Pending |
| 6 | Update bot.py (optional) | Pending |

**Total estimated commits:** 5-6
**Affected files:** 3 new/modified

---

**Plan complete and saved.**
