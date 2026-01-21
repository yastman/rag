# Voyage Unified RAG Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate from local BGE-M3/langcache embeddings to Voyage AI unified ecosystem for improved quality (nDCG +13%), reduced RAM (~200MB vs ~2.5GB), and native RedisVL integration.

**Architecture:** Single-vendor approach using Voyage AI for dense embeddings (search + cache) and reranking, with local FastEmbed BM42 for sparse vectors. New `VoyageClient` wraps API with retry logic. New `QueryPreprocessor` handles translit normalization and dynamic RRF weights. Modified `CacheService` uses `VoyageAITextVectorizer`.

**Tech Stack:** Voyage AI API (voyage-3-large, voyage-3-lite, rerank-2), FastEmbed BM42, RedisVL, Qdrant, tenacity, Python 3.12+

---

## Task 1: Add Voyage AI Dependencies

**Files:**
- Modify: `pyproject.toml`

### Step 1: Add dependencies to pyproject.toml

Add to `[project.dependencies]` section:

```toml
voyageai = ">=0.3.0"
tenacity = ">=8.2.0"
```

### Step 2: Install dependencies

Run: `pip install voyageai tenacity`
Expected: Successfully installed voyageai-0.3.x tenacity-8.x.x

### Step 3: Verify installation

Run: `python -c "import voyageai; import tenacity; print('OK')"`
Expected: `OK`

### Step 4: Commit

```bash
git add pyproject.toml
git commit -m "chore(deps): add voyageai and tenacity dependencies"
```

---

## Task 2: Add Voyage Configuration

**Files:**
- Modify: `telegram_bot/config.py`
- Modify: `.env.example`

### Step 1: Add Voyage settings to BotConfig

Add after line 38 in `telegram_bot/config.py`:

```python
    # Voyage AI Configuration
    voyage_api_key: str = os.getenv("VOYAGE_API_KEY", "")
    voyage_embed_model: str = os.getenv("VOYAGE_EMBED_MODEL", "voyage-3-large")
    voyage_cache_model: str = os.getenv("VOYAGE_CACHE_MODEL", "voyage-3-lite")
    voyage_rerank_model: str = os.getenv("VOYAGE_RERANK_MODEL", "rerank-2")

    # Search Configuration
    search_top_k: int = int(os.getenv("SEARCH_TOP_K", "50"))
    rerank_top_k: int = int(os.getenv("RERANK_TOP_K", "5"))
```

### Step 2: Verify config loads

Run: `python -c "from telegram_bot.config import BotConfig; c = BotConfig(); print(f'voyage_embed_model: {c.voyage_embed_model}')"`
Expected: `voyage_embed_model: voyage-3-large`

### Step 3: Update .env.example

Add to `.env.example`:

```bash
# Voyage AI
VOYAGE_API_KEY=your_voyage_api_key_here
VOYAGE_EMBED_MODEL=voyage-3-large
VOYAGE_CACHE_MODEL=voyage-3-lite
VOYAGE_RERANK_MODEL=rerank-2
```

### Step 4: Commit

```bash
git add telegram_bot/config.py .env.example
git commit -m "feat(config): add Voyage AI configuration settings"
```

---

## Task 3: Create VoyageClient with Retry Logic

**Files:**
- Create: `telegram_bot/services/voyage_client.py`
- Create: `tests/test_voyage_client.py`

### Step 1: Write failing tests

Create `tests/test_voyage_client.py`:

```python
"""Tests for VoyageClient."""

import pytest
from unittest.mock import MagicMock, patch


class TestVoyageClientUnit:
    """Unit tests for VoyageClient (no API calls)."""

    def test_singleton_returns_same_instance(self):
        """Test singleton pattern returns same instance."""
        from telegram_bot.services.voyage_client import VoyageClient

        # Reset singleton for clean test
        VoyageClient._instance = None

        with patch.dict('os.environ', {'VOYAGE_API_KEY': 'test-key'}):
            client1 = VoyageClient.get_instance()
            client2 = VoyageClient.get_instance()

            assert client1 is client2

        # Cleanup
        VoyageClient._instance = None

    def test_init_raises_without_api_key(self):
        """Test initialization fails without API key."""
        from telegram_bot.services.voyage_client import VoyageClient

        VoyageClient._instance = None

        with patch.dict('os.environ', {'VOYAGE_API_KEY': ''}):
            with pytest.raises(ValueError, match="VOYAGE_API_KEY"):
                VoyageClient()

        VoyageClient._instance = None

    def test_embed_calls_client_with_correct_params(self):
        """Test embed passes correct parameters."""
        from telegram_bot.services.voyage_client import VoyageClient

        VoyageClient._instance = None

        with patch.dict('os.environ', {'VOYAGE_API_KEY': 'test-key'}):
            with patch('voyageai.Client') as mock_client_class:
                mock_client = MagicMock()
                mock_client.embed.return_value = MagicMock(
                    embeddings=[[0.1] * 1024, [0.2] * 1024]
                )
                mock_client_class.return_value = mock_client

                client = VoyageClient()
                result = client.embed_sync(["text1", "text2"], model="voyage-3-large")

                mock_client.embed.assert_called_once_with(
                    texts=["text1", "text2"],
                    model="voyage-3-large",
                    input_type="document",
                )
                assert len(result) == 2

        VoyageClient._instance = None

    def test_embed_query_uses_query_input_type(self):
        """Test embed_query uses input_type='query'."""
        from telegram_bot.services.voyage_client import VoyageClient

        VoyageClient._instance = None

        with patch.dict('os.environ', {'VOYAGE_API_KEY': 'test-key'}):
            with patch('voyageai.Client') as mock_client_class:
                mock_client = MagicMock()
                mock_client.embed.return_value = MagicMock(
                    embeddings=[[0.1] * 1024]
                )
                mock_client_class.return_value = mock_client

                client = VoyageClient()
                client.embed_query_sync("test query")

                call_kwargs = mock_client.embed.call_args[1]
                assert call_kwargs['input_type'] == 'query'

        VoyageClient._instance = None

    def test_rerank_returns_sorted_indices(self):
        """Test rerank returns indices and scores."""
        from telegram_bot.services.voyage_client import VoyageClient

        VoyageClient._instance = None

        with patch.dict('os.environ', {'VOYAGE_API_KEY': 'test-key'}):
            with patch('voyageai.Client') as mock_client_class:
                mock_client = MagicMock()
                # Mock rerank result
                mock_result1 = MagicMock()
                mock_result1.index = 2
                mock_result1.relevance_score = 0.95
                mock_result2 = MagicMock()
                mock_result2.index = 0
                mock_result2.relevance_score = 0.80

                mock_client.rerank.return_value = MagicMock(
                    results=[mock_result1, mock_result2]
                )
                mock_client_class.return_value = mock_client

                client = VoyageClient()
                result = client.rerank_sync("query", ["doc0", "doc1", "doc2"])

                assert result[0]["index"] == 2
                assert result[0]["score"] == 0.95
                assert result[1]["index"] == 0

        VoyageClient._instance = None

    def test_rerank_empty_documents(self):
        """Test rerank with empty documents returns empty list."""
        from telegram_bot.services.voyage_client import VoyageClient

        VoyageClient._instance = None

        with patch.dict('os.environ', {'VOYAGE_API_KEY': 'test-key'}):
            with patch('voyageai.Client'):
                client = VoyageClient()
                result = client.rerank_sync("query", [])

                assert result == []

        VoyageClient._instance = None
```

### Step 2: Run tests to verify they fail

Run: `pytest tests/test_voyage_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'telegram_bot.services.voyage_client'`

### Step 3: Implement VoyageClient

Create `telegram_bot/services/voyage_client.py`:

```python
"""Voyage AI client with retry logic for embeddings and reranking."""

import os
import logging
from typing import Optional

import voyageai
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

logger = logging.getLogger(__name__)


class VoyageClient:
    """Unified Voyage AI client for RAG pipeline.

    Provides embeddings and reranking with automatic retry on rate limits.
    Uses singleton pattern to reuse client across requests.
    """

    _instance: Optional["VoyageClient"] = None

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Voyage client.

        Args:
            api_key: Voyage API key. Falls back to VOYAGE_API_KEY env var.

        Raises:
            ValueError: If no API key provided or found in environment.
        """
        self._api_key = api_key or os.getenv("VOYAGE_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "VOYAGE_API_KEY not set. "
                "Provide api_key parameter or set VOYAGE_API_KEY environment variable."
            )

        self._client = voyageai.Client(api_key=self._api_key)
        logger.info("VoyageClient initialized")

    @classmethod
    def get_instance(cls, api_key: Optional[str] = None) -> "VoyageClient":
        """Get singleton instance.

        Args:
            api_key: Optional API key (used only on first call).

        Returns:
            Shared VoyageClient instance.
        """
        if cls._instance is None:
            cls._instance = cls(api_key)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing)."""
        cls._instance = None

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        reraise=True,
    )
    def embed_sync(
        self,
        texts: list[str],
        model: str = "voyage-3-large",
        input_type: str = "document",
    ) -> list[list[float]]:
        """Generate embeddings with retry on rate limits (sync).

        Args:
            texts: List of texts to embed.
            model: Voyage model name.
            input_type: "document" or "query".

        Returns:
            List of embedding vectors.
        """
        result = self._client.embed(
            texts=texts,
            model=model,
            input_type=input_type,
        )
        return result.embeddings

    def embed_query_sync(
        self, query: str, model: str = "voyage-3-large"
    ) -> list[float]:
        """Embed single query (sync).

        Args:
            query: Query text.
            model: Voyage model name.

        Returns:
            Single embedding vector.
        """
        embeddings = self.embed_sync([query], model=model, input_type="query")
        return embeddings[0]

    def embed_for_cache_sync(self, text: str) -> list[float]:
        """Embed for cache using lighter model (sync).

        Args:
            text: Text to embed.

        Returns:
            Embedding vector from voyage-3-lite.
        """
        embeddings = self.embed_sync([text], model="voyage-3-lite", input_type="query")
        return embeddings[0]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
    )
    def rerank_sync(
        self,
        query: str,
        documents: list[str],
        model: str = "rerank-2",
        top_k: int = 5,
    ) -> list[dict]:
        """Rerank documents by relevance (sync).

        Args:
            query: Search query.
            documents: List of document texts.
            model: Reranker model name.
            top_k: Number of top results to return.

        Returns:
            List of dicts with 'index' and 'score' keys, sorted by relevance.
        """
        if not documents:
            return []

        result = self._client.rerank(
            query=query,
            documents=documents,
            model=model,
            top_k=top_k,
        )

        return [
            {"index": r.index, "score": r.relevance_score}
            for r in result.results
        ]

    # Async wrappers for compatibility with async code
    async def embed(
        self,
        texts: list[str],
        model: str = "voyage-3-large",
        input_type: str = "document",
    ) -> list[list[float]]:
        """Generate embeddings (async wrapper)."""
        return self.embed_sync(texts, model, input_type)

    async def embed_query(
        self, query: str, model: str = "voyage-3-large"
    ) -> list[float]:
        """Embed single query (async wrapper)."""
        return self.embed_query_sync(query, model)

    async def embed_for_cache(self, text: str) -> list[float]:
        """Embed for cache (async wrapper)."""
        return self.embed_for_cache_sync(text)

    async def rerank(
        self,
        query: str,
        documents: list[str],
        model: str = "rerank-2",
        top_k: int = 5,
    ) -> list[dict]:
        """Rerank documents (async wrapper)."""
        return self.rerank_sync(query, documents, model, top_k)
```

### Step 4: Run tests to verify they pass

Run: `pytest tests/test_voyage_client.py -v`
Expected: All 6 tests PASS

### Step 5: Commit

```bash
git add telegram_bot/services/voyage_client.py tests/test_voyage_client.py
git commit -m "feat(voyage): add VoyageClient with retry logic and singleton pattern"
```

---

## Task 4: Create QueryPreprocessor for Translit and RRF Weights

**Files:**
- Create: `telegram_bot/services/query_preprocessor.py`
- Create: `tests/test_query_preprocessor.py`

### Step 1: Write failing tests

Create `tests/test_query_preprocessor.py`:

```python
"""Tests for QueryPreprocessor."""

import pytest
from telegram_bot.services.query_preprocessor import QueryPreprocessor


class TestQueryPreprocessorTranslit:
    """Tests for transliteration normalization."""

    def test_normalize_burgas(self):
        """Test Burgas transliteration."""
        preprocessor = QueryPreprocessor()
        result = preprocessor.normalize_translit("apartments in Burgas")
        assert "Бургас" in result

    def test_normalize_sunny_beach(self):
        """Test Sunny Beach transliteration."""
        preprocessor = QueryPreprocessor()
        result = preprocessor.normalize_translit("Sunny Beach apartments")
        assert "Солнечный берег" in result

    def test_normalize_sveti_vlas(self):
        """Test Sveti Vlas transliteration."""
        preprocessor = QueryPreprocessor()
        result = preprocessor.normalize_translit("villa in Sveti Vlas")
        assert "Святой Влас" in result

    def test_normalize_preserves_cyrillic(self):
        """Test cyrillic text is preserved."""
        preprocessor = QueryPreprocessor()
        result = preprocessor.normalize_translit("квартиры в Бургасе")
        assert result == "квартиры в Бургасе"

    def test_normalize_case_insensitive(self):
        """Test case insensitive matching."""
        preprocessor = QueryPreprocessor()
        result = preprocessor.normalize_translit("BURGAS apartment")
        assert "Бургас" in result


class TestQueryPreprocessorRRFWeights:
    """Tests for dynamic RRF weight calculation."""

    def test_default_weights_for_general_query(self):
        """Test default RRF weights for general queries."""
        preprocessor = QueryPreprocessor()
        dense, sparse = preprocessor.get_rrf_weights("квартиры у моря")
        assert dense == 0.6
        assert sparse == 0.4

    def test_sparse_favored_for_id_query(self):
        """Test RRF weights favor sparse for ID queries."""
        preprocessor = QueryPreprocessor()
        dense, sparse = preprocessor.get_rrf_weights("квартира ID 12345")
        assert dense == 0.2
        assert sparse == 0.8

    def test_sparse_favored_for_corpus_query(self):
        """Test RRF weights favor sparse for corpus/block queries."""
        preprocessor = QueryPreprocessor()
        dense, sparse = preprocessor.get_rrf_weights("ЖК Елените корпус 5")
        assert dense == 0.2
        assert sparse == 0.8

    def test_sparse_favored_for_floor_query(self):
        """Test RRF weights favor sparse for floor queries."""
        preprocessor = QueryPreprocessor()
        dense, sparse = preprocessor.get_rrf_weights("квартира этаж 3")
        assert dense == 0.2
        assert sparse == 0.8


class TestQueryPreprocessorCacheThreshold:
    """Tests for adaptive cache threshold."""

    def test_default_threshold(self):
        """Test default cache threshold."""
        preprocessor = QueryPreprocessor()
        threshold = preprocessor.get_cache_threshold("квартиры в центре")
        assert threshold == 0.10

    def test_strict_threshold_for_numbers(self):
        """Test strict threshold for queries with numbers."""
        preprocessor = QueryPreprocessor()
        threshold = preprocessor.get_cache_threshold("цена квартиры 12345")
        assert threshold == 0.05

    def test_strict_threshold_for_corpus(self):
        """Test strict threshold for corpus queries."""
        preprocessor = QueryPreprocessor()
        threshold = preprocessor.get_cache_threshold("корпус А цена")
        assert threshold == 0.05


class TestQueryPreprocessorAnalyze:
    """Tests for full analysis."""

    def test_analyze_returns_all_fields(self):
        """Test analyze returns complete dict."""
        preprocessor = QueryPreprocessor()
        result = preprocessor.analyze("apartments in Burgas ID 123")

        assert "original_query" in result
        assert "normalized_query" in result
        assert "rrf_weights" in result
        assert "cache_threshold" in result
        assert "is_exact" in result

    def test_analyze_combines_translit_and_weights(self):
        """Test analyze applies both translit and weight calculation."""
        preprocessor = QueryPreprocessor()
        result = preprocessor.analyze("Sunny Beach корпус 5")

        assert "Солнечный берег" in result["normalized_query"]
        assert result["rrf_weights"]["sparse"] == 0.8
        assert result["is_exact"] is True
```

### Step 2: Run tests to verify they fail

Run: `pytest tests/test_query_preprocessor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'telegram_bot.services.query_preprocessor'`

### Step 3: Implement QueryPreprocessor

Create `telegram_bot/services/query_preprocessor.py`:

```python
"""Query preprocessing for RAG pipeline optimization."""

import re
import logging
from typing import Any

logger = logging.getLogger(__name__)


class QueryPreprocessor:
    """Preprocesses queries for optimal search and caching.

    Handles:
    - Transliteration normalization (Latin → Cyrillic place names)
    - Dynamic RRF weight calculation based on query type
    - Adaptive cache threshold selection

    Note: This is separate from QueryAnalyzer which uses LLM for filter extraction.
    QueryPreprocessor is rule-based and runs before QueryAnalyzer.
    """

    # Transliteration map: Latin -> Cyrillic (Bulgarian cities and resorts)
    TRANSLIT_MAP = {
        # Cities
        "Burgas": "Бургас",
        "Varna": "Варна",
        "Sofia": "София",
        "Plovdiv": "Пловдив",
        # Resorts
        "Nesebar": "Несебър",
        "Nessebar": "Несебър",
        "Sozopol": "Созопол",
        "Pomorie": "Поморие",
        "Sunny Beach": "Солнечный берег",
        "Sveti Vlas": "Святой Влас",
        "Svyati Vlas": "Святой Влас",
        "St Vlas": "Святой Влас",
        "Elenite": "Елените",
        "Ravda": "Равда",
        "Sarafovo": "Сарафово",
        "Primorsko": "Приморско",
        "Tsarevo": "Царево",
        "Lozenets": "Лозенец",
        "Golden Sands": "Золотые пески",
        "Albena": "Албена",
        "Balchik": "Балчик",
        "Kavarna": "Каварна",
        "Obzor": "Обзор",
        "Byala": "Бяла",
    }

    # Patterns indicating exact search (favor sparse vectors)
    EXACT_PATTERNS = [
        r"\bID\s*\d+",  # "ID 12345"
        r"\b\d{5,}\b",  # Long numbers (IDs)
        r"корпус\s*\d+",  # "корпус 5"
        r"корпус\s*[А-Яа-яA-Za-z]",  # "корпус А"
        r"блок\s*\d+",  # "блок 3"
        r"блок\s*[А-Яа-яA-Za-z]",  # "блок Б"
        r"секция\s*\d+",  # "секция 2"
        r"этаж\s*\d+",  # "этаж 5"
        r"ЖК\s+\w+",  # "ЖК Елените"
    ]

    # Patterns requiring strict cache threshold
    STRICT_CACHE_PATTERNS = [
        r"\b\d{3,}\b",  # Numbers 3+ digits
        r"корпус",
        r"блок",
        r"секция",
        r"этаж",
        r"\bID\b",
    ]

    def normalize_translit(self, query: str) -> str:
        """Convert Latin place names to Cyrillic for BM42 sparse search.

        Args:
            query: User query (may contain Latin transliterations).

        Returns:
            Query with Latin place names converted to Cyrillic.
        """
        normalized = query

        for latin, cyrillic in self.TRANSLIT_MAP.items():
            # Case-insensitive replacement
            pattern = re.compile(re.escape(latin), re.IGNORECASE)
            normalized = pattern.sub(cyrillic, normalized)

        if normalized != query:
            logger.debug(f"Translit normalized: '{query}' -> '{normalized}'")

        return normalized

    def get_rrf_weights(self, query: str) -> tuple[float, float]:
        """Calculate RRF fusion weights based on query type.

        For exact queries (IDs, corpus numbers), favor sparse (keyword) search.
        For semantic queries, favor dense (embedding) search.

        Args:
            query: User query.

        Returns:
            Tuple of (dense_weight, sparse_weight) summing to 1.0.
        """
        for pattern in self.EXACT_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                logger.debug(f"Exact query detected, using sparse-favored weights")
                return (0.2, 0.8)  # Favor sparse for exact matches

        return (0.6, 0.4)  # Default: favor dense for semantic queries

    def get_cache_threshold(self, query: str) -> float:
        """Get cache similarity threshold based on query type.

        Stricter threshold for queries with specific identifiers
        to avoid false positive cache hits.

        Args:
            query: User query.

        Returns:
            Distance threshold (lower = stricter matching required).
        """
        for pattern in self.STRICT_CACHE_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                logger.debug(f"Strict cache threshold for query with identifiers")
                return 0.05  # 95% similarity required

        return 0.10  # Default 90% similarity

    def has_exact_identifier(self, query: str) -> bool:
        """Check if query contains exact identifiers.

        Args:
            query: User query.

        Returns:
            True if query contains IDs, corpus numbers, etc.
        """
        for pattern in self.EXACT_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                return True
        return False

    def analyze(self, query: str) -> dict[str, Any]:
        """Perform full query preprocessing analysis.

        Args:
            query: User query.

        Returns:
            Dict containing:
            - original_query: Original input
            - normalized_query: After translit normalization
            - rrf_weights: {"dense": float, "sparse": float}
            - cache_threshold: float
            - is_exact: bool
        """
        normalized = self.normalize_translit(query)
        dense_w, sparse_w = self.get_rrf_weights(query)

        return {
            "original_query": query,
            "normalized_query": normalized,
            "rrf_weights": {"dense": dense_w, "sparse": sparse_w},
            "cache_threshold": self.get_cache_threshold(query),
            "is_exact": self.has_exact_identifier(query),
        }
```

### Step 4: Run tests to verify they pass

Run: `pytest tests/test_query_preprocessor.py -v`
Expected: All 14 tests PASS

### Step 5: Commit

```bash
git add telegram_bot/services/query_preprocessor.py tests/test_query_preprocessor.py
git commit -m "feat(search): add QueryPreprocessor for translit normalization and dynamic RRF"
```

---

## Task 5: Migrate CacheService to VoyageAI

**Files:**
- Modify: `telegram_bot/services/cache.py`
- Modify: `tests/test_redis_cache.py` (if needed)

### Step 1: Read current cache.py to understand structure

Run: `head -150 telegram_bot/services/cache.py`

### Step 2: Replace HFTextVectorizer import

In `telegram_bot/services/cache.py`, change:

```python
# OLD (line ~17):
from redisvl.utils.vectorize import HFTextVectorizer

# NEW:
from redisvl.utils.vectorize import VoyageAITextVectorizer
```

### Step 3: Update SemanticCache initialization

In the `initialize` method, replace HFTextVectorizer with VoyageAITextVectorizer:

```python
# OLD (lines ~103-112):
os.environ["CUDA_VISIBLE_DEVICES"] = ""
logger.info("Loading SemanticCache vectorizer (redis/langcache-embed-v1) on CPU...")
vectorizer = await asyncio.to_thread(
    HFTextVectorizer, model="redis/langcache-embed-v1"
)

# NEW:
voyage_api_key = os.getenv("VOYAGE_API_KEY", "")
if not voyage_api_key:
    logger.warning("VOYAGE_API_KEY not set, SemanticCache disabled")
    self.semantic_cache = None
    return

logger.info("Initializing SemanticCache with VoyageAI (voyage-3-lite)...")
vectorizer = VoyageAITextVectorizer(
    model="voyage-3-lite",
    api_config={"api_key": voyage_api_key}
)
```

### Step 4: Add threshold_override parameter to check_semantic_cache

Modify `check_semantic_cache` method signature:

```python
async def check_semantic_cache(
    self,
    query: str,
    user_id: Optional[int] = None,
    language: str = "ru",
    threshold_override: Optional[float] = None,  # NEW parameter
) -> Optional[str]:
```

And use it in the method:

```python
# Use override if provided, otherwise use default
effective_threshold = threshold_override if threshold_override is not None else self.distance_threshold
```

### Step 5: Remove CUDA environment variable hack

Remove these lines (no longer needed without local model):

```python
# DELETE:
import os
os.environ["CUDA_VISIBLE_DEVICES"] = ""
```

### Step 6: Run existing cache tests

Run: `pytest tests/test_redis_cache.py -v`
Expected: Tests pass (or skip if Redis not available)

### Step 7: Commit

```bash
git add telegram_bot/services/cache.py
git commit -m "feat(cache): migrate SemanticCache to VoyageAITextVectorizer

- Replace HFTextVectorizer with VoyageAITextVectorizer
- Use voyage-3-lite model for cache (faster, cheaper)
- Add threshold_override parameter for adaptive caching
- Remove CUDA environment hack (no local model needed)"
```

---

## Task 6: Update Services Exports

**Files:**
- Modify: `telegram_bot/services/__init__.py`

### Step 1: Add new exports

Add to `telegram_bot/services/__init__.py`:

```python
from .query_preprocessor import QueryPreprocessor
from .voyage_client import VoyageClient
```

And update `__all__`:

```python
__all__ = [
    "CESCPersonalizer",
    "CacheService",
    "EmbeddingService",
    "LLMService",
    "QueryAnalyzer",
    "QueryPreprocessor",  # NEW
    "RetrieverService",
    "UserContextService",
    "VoyageClient",  # NEW
]
```

### Step 2: Verify imports work

Run: `python -c "from telegram_bot.services import VoyageClient, QueryPreprocessor; print('OK')"`
Expected: `OK`

### Step 3: Commit

```bash
git add telegram_bot/services/__init__.py
git commit -m "feat(services): export VoyageClient and QueryPreprocessor"
```

---

## Task 7: Run Full Test Suite and QA

### Step 1: Run linting

Run: `make lint`
Expected: No errors (or only pre-existing ones)

### Step 2: Run type checking

Run: `make type-check`
Expected: No new errors

### Step 3: Run all tests

Run: `make test`
Expected: All tests pass

### Step 4: Manual smoke test

Run:
```bash
python -c "
from telegram_bot.services import VoyageClient, QueryPreprocessor

# Test QueryPreprocessor
pp = QueryPreprocessor()
result = pp.analyze('apartments in Sunny Beach корпус 5')
print(f'QueryPreprocessor: {result}')
assert 'Солнечный берег' in result['normalized_query']
assert result['rrf_weights']['sparse'] == 0.8
print('QueryPreprocessor: OK')

# Test VoyageClient initialization (without actual API call)
print('VoyageClient: requires VOYAGE_API_KEY to test')
print('All smoke tests passed!')
"
```
Expected: `All smoke tests passed!`

### Step 5: Final commit

```bash
git add -A
git commit -m "chore(voyage): complete Phase 1 of Voyage Unified migration

Phase 1 complete:
- VoyageClient with retry logic
- QueryPreprocessor for translit/RRF
- CacheService migrated to VoyageAITextVectorizer
- All tests passing"
```

---

## Success Criteria

- [ ] `voyageai` and `tenacity` dependencies installed
- [ ] `BotConfig` has Voyage settings
- [ ] `VoyageClient` handles API with retry (5 tests pass)
- [ ] `QueryPreprocessor` normalizes translit and calculates RRF weights (14 tests pass)
- [ ] `CacheService` uses `VoyageAITextVectorizer` instead of `HFTextVectorizer`
- [ ] All services exported from `__init__.py`
- [ ] All existing tests still pass
- [ ] Linting and type checking pass

---

## Phase 2 (Future Tasks)

After Phase 1 is complete:

1. **Task 8:** Create `VoyageEmbeddingService` to replace `EmbeddingService`
2. **Task 9:** Update `RetrieverService` to use Voyage + dynamic RRF
3. **Task 10:** Add Voyage Reranking to pipeline
4. **Task 11:** Integration tests with real Voyage API
5. **Task 12:** Performance benchmarking

---

## References

- [Voyage AI Documentation](https://docs.voyageai.com/)
- [RedisVL VoyageAITextVectorizer](https://docs.redisvl.com/)
- [Tenacity Retry Library](https://tenacity.readthedocs.io/)
- Design document: `docs/plans/2026-01-21-voyage-unified-rag-design.md`
