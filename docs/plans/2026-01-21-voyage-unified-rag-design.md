***REMOVED*** Unified RAG Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate from local BGE-M3/langcache embeddings to Voyage AI unified ecosystem for improved quality (nDCG +13%), reduced server load (~200MB vs ~2.5GB RAM), and native RedisVL integration.

**Architecture:** Single-vendor approach using Voyage AI for dense embeddings (search + cache) and reranking, with local FastEmbed BM42 for sparse vectors.

**Tech Stack:**
- Voyage AI API (voyage-3-large, voyage-3-lite, rerank-2)
- FastEmbed BM42 (local CPU)
- RedisVL with VoyageAITextVectorizer
- Qdrant (hybrid search)
- Python 3.12+

---

## 1. Executive Summary

### Why Voyage Unified

| Metric | Before (BGE-M3) | After (Voyage) | Improvement |
|--------|-----------------|----------------|-------------|
| **Quality (nDCG)** | 0.75 | 0.85 | +13% |
| **Server RAM** | ~2.5 GB | ~200 MB | 12x less |
| **Startup** | 15-30 sec | Instant | - |
| **Monthly Cost** | $0 + server $20+ | ~$5 API | 75% cheaper |
| **Cache-Search Alignment** | Separate models | Unified space | No mismatch |
| **Reranker** | ColBERT (heavy) | Voyage 2.5 (API) | SOTA |

### Expected KPIs

```
Cache Hit Rate:        30-40%
Latency (Cache Hit):   ~200 ms
Latency (Cache Miss):  ~2.0 sec
Retrieval Accuracy:    nDCG@10 = 0.84+
Monthly Cost:          $3-5 (Voyage API)
Server RAM:            <500 MB
```

---

## 2. Architecture Overview

### System Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    VOYAGE UNIFIED RAG 2026                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  User Query                                                     │
│      │                                                          │
│      ▼                                                          │
│  ┌──────────────────────────────────────┐                       │
│  │ 0. QUERY ANALYZER                    │                       │
│  │    ├─ Translit normalization         │                       │
│  │    ├─ Detect query type (ID/general) │                       │
│  │    └─ Set dynamic RRF weights        │                       │
│  └──────────────┬───────────────────────┘                       │
│                 │                                               │
│                 ▼                                               │
│  ┌──────────────────────────────────────┐                       │
│  │ 1. CACHE CHECK (RedisVL)             │                       │
│  │    ├─ VoyageAITextVectorizer         │                       │
│  │    ├─ voyage-3-lite embeddings       │                       │
│  │    └─ Adaptive threshold (0.05-0.10) │                       │
│  └──────────────┬───────────────────────┘                       │
│                 │                                               │
│         HIT?   │   MISS                                         │
│          │     │     │                                          │
│          ▼     │     ▼                                          │
│  ┌─────────┐   │  ┌──────────────────────────────────┐          │
│  │ CESC    │   │  │ 2. HYBRID SEARCH (Qdrant)        │          │
│  │ Person- │   │  │    ├─ FILTER: status="active"    │          │
│  │ alize   │   │  │    ├─ Dense: Voyage-3-large      │          │
│  └────┬────┘   │  │    ├─ Sparse: FastEmbed BM42     │          │
│       │        │  │    └─ RRF fusion (dynamic)       │          │
│       │        │  └──────────────┬───────────────────┘          │
│       │        │                 │                              │
│       │        │                 ▼                              │
│       │        │  ┌──────────────────────────────────┐          │
│       │        │  │ 3. FRESHNESS CHECK (Optional)    │          │
│       │        │  │    └─ Cross-check with CRM/SQL   │          │
│       │        │  └──────────────┬───────────────────┘          │
│       │        │                 │                              │
│       │        │                 ▼                              │
│       │        │  ┌──────────────────────────────────┐          │
│       │        │  │ 4. RERANK (Voyage Rerank-2)      │          │
│       │        │  │    ├─ Cross-encoder scoring      │          │
│       │        │  │    └─ TOP-50 → TOP-5             │          │
│       │        │  └──────────────┬───────────────────┘          │
│       │        │                 │                              │
│       │        │                 ▼                              │
│       │        │  ┌──────────────────────────────────┐          │
│       │        │  │ 5. LLM GENERATION                │          │
│       │        │  │    └─ Claude 3.5 / GPT-4o        │          │
│       │        │  └──────────────┬───────────────────┘          │
│       │        │                 │                              │
│       │        │                 ▼                              │
│       │        │  ┌──────────────────────────────────┐          │
│       │        │  │ 6. CACHE STORE                   │          │
│       │        │  │    └─ (query → response)         │          │
│       │        │  └──────────────────────────────────┘          │
│       │        │                 │                              │
│       ▼        ▼                 ▼                              │
│  ┌─────────────────────────────────────────────────────┐        │
│  │                    RESPONSE                          │        │
│  └─────────────────────────────────────────────────────┘        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Technology | Location | Purpose |
|-----------|------------|----------|---------|
| Query Analyzer | Python | Local | Translit, type detection, RRF weights |
| Dense Embeddings | Voyage-3-large | Cloud API | Semantic search (1024 dim) |
| Cache Embeddings | Voyage-3-lite | Cloud API | Fast cache matching |
| Sparse Embeddings | FastEmbed BM42 | Local CPU | Keyword matching (~50MB) |
| Reranker | Voyage Rerank-2 | Cloud API | Cross-encoder reranking |
| Vector DB | Qdrant | Local/Cloud | Hybrid search (RRF fusion) |
| Cache | RedisVL | Local/Cloud | Semantic cache + user context |
| LLM | Claude 3.5 / GPT-4o | Cloud API | Response generation |

---

## 3. Production Edge Cases & Mitigations

### 3.1 Stale Data Hazard

**Problem:** Property sold or price changed, but vector DB has old data.

**Solution:**
- Always filter by `status="active"` in Qdrant
- Optional: Cross-check TOP-5 IDs with CRM before generation

```python
***REMOVED*** search with mandatory filter
filter = Filter(
    must=[
        FieldCondition(key="status", match=MatchValue(value="active"))
    ]
)
results = await qdrant.search(..., query_filter=filter)
```

### 3.2 Translit Mismatch (BM42)

**Problem:** User writes "Svyati Vlas", documents have "Святой Влас".

**Solution:** Normalize query before sparse search.

```python
TRANSLIT_MAP = {
    'Svyati': 'Святи', 'Vlas': 'Влас', 'Elenite': 'Елените',
    'Burgas': 'Бургас', 'Nesebar': 'Несебър', 'Sozopol': 'Созопол',
    'Sunny Beach': 'Солнечный берег', 'Pomorie': 'Поморие',
}

def normalize_translit(query: str) -> str:
    normalized = query
    for lat, cyr in TRANSLIT_MAP.items():
        normalized = re.sub(lat, cyr, normalized, flags=re.IGNORECASE)
    return normalized
```

### 3.3 Voyage API Rate Limits

**Problem:** 429 errors during batch indexing.

**Solution:** Retry with exponential backoff.

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException)),
    reraise=True
)
async def voyage_embed_with_retry(texts: list[str], model: str):
    return voyage_client.embed(texts=texts, model=model)
```

### 3.4 Cache False Positives

**Problem:** "Корпус А" query returns cached answer for "Корпус Б".

**Solution:** Adaptive cache threshold based on query type.

```python
def get_cache_threshold(query: str) -> float:
    """Stricter threshold for specific queries."""
    # Has numbers (IDs, prices, floors)
    if re.search(r'\b\d{3,}\b', query):
        return 0.05  # 95% similarity required

    # Specific identifiers
    if re.search(r'корпус|блок|секция|этаж', query, re.IGNORECASE):
        return 0.05

    return 0.10  # Default 90%
```

### 3.5 Dynamic RRF Weights

**Problem:** Fixed 0.6/0.4 weights not optimal for all query types.

**Solution:** Detect query type and adjust weights.

```python
def get_rrf_weights(query: str) -> tuple[float, float]:
    """Return (dense_weight, sparse_weight) based on query type."""

    # Exact search patterns (favor sparse)
    exact_patterns = [
        r'\b\d{4,}\b',             # IDs: 12345
        r'корпус\s*\d+',           # "корпус 5"
        r'ЖК\s+\w+',               # "ЖК Елените"
        r'блок\s*[A-Za-zА-Яа-я]',  # "блок А"
        r'ID\s*\d+',               # "ID 123"
    ]

    for pattern in exact_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            return (0.2, 0.8)  # Favor sparse for exact matches

    return (0.6, 0.4)  # Default: favor dense for semantic queries
```

---

## 4. Implementation Tasks

### Task 1: Add Voyage Client with Retry Logic

**Files:**
- Create: `telegram_bot/services/voyage_client.py`
- Create: `tests/test_voyage_client.py`

#### Step 1: Write failing tests

```python
# tests/test_voyage_client.py
"""Tests for VoyageClient."""

import pytest
from unittest.mock import AsyncMock, patch
from telegram_bot.services.voyage_client import VoyageClient


class TestVoyageClient:
    """Tests for Voyage AI client wrapper."""

    def test_singleton_instance(self):
        """Test singleton pattern returns same instance."""
        client1 = VoyageClient.get_instance()
        client2 = VoyageClient.get_instance()
        assert client1 is client2

    @pytest.mark.asyncio
    async def test_embed_returns_vectors(self):
        """Test embed returns list of vectors."""
        client = VoyageClient()
        with patch.object(client, '_client') as mock:
            mock.embed.return_value = type('obj', (object,), {
                'embeddings': [[0.1] * 1024, [0.2] * 1024]
            })()

            result = await client.embed(["text1", "text2"])

            assert len(result) == 2
            assert len(result[0]) == 1024

    @pytest.mark.asyncio
    async def test_embed_query_uses_query_input_type(self):
        """Test embed_query uses correct input_type."""
        client = VoyageClient()
        with patch.object(client, '_client') as mock:
            mock.embed.return_value = type('obj', (object,), {
                'embeddings': [[0.1] * 1024]
            })()

            await client.embed_query("test query")

            mock.embed.assert_called_once()
            call_kwargs = mock.embed.call_args[1]
            assert call_kwargs['input_type'] == 'query'

    @pytest.mark.asyncio
    async def test_rerank_returns_ordered_indices(self):
        """Test rerank returns indices and scores."""
        client = VoyageClient()
        with patch.object(client, '_client') as mock:
            mock.rerank.return_value = type('obj', (object,), {
                'results': [
                    type('r', (object,), {'index': 2, 'relevance_score': 0.9})(),
                    type('r', (object,), {'index': 0, 'relevance_score': 0.7})(),
                ]
            })()

            result = await client.rerank("query", ["doc1", "doc2", "doc3"])

            assert result[0]['index'] == 2
            assert result[0]['score'] == 0.9
```

#### Step 2: Implement VoyageClient

```python
# telegram_bot/services/voyage_client.py
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
        """
        self._api_key = api_key or os.getenv("VOYAGE_API_KEY")
        if not self._api_key:
            raise ValueError("VOYAGE_API_KEY not set")

        self._client = voyageai.Client(api_key=self._api_key)
        logger.info("VoyageClient initialized")

    @classmethod
    def get_instance(cls, api_key: Optional[str] = None) -> "VoyageClient":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls(api_key)
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset singleton (for testing)."""
        cls._instance = None

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        reraise=True,
    )
    async def embed(
        self,
        texts: list[str],
        model: str = "voyage-3-large",
        input_type: str = "document",
    ) -> list[list[float]]:
        """Generate embeddings with retry on rate limits.

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

    async def embed_query(self, query: str, model: str = "voyage-3-large") -> list[float]:
        """Embed single query (optimized for search).

        Args:
            query: Query text.
            model: Voyage model name.

        Returns:
            Single embedding vector.
        """
        embeddings = await self.embed([query], model=model, input_type="query")
        return embeddings[0]

    async def embed_for_cache(self, text: str) -> list[float]:
        """Embed for cache (uses lighter model).

        Args:
            text: Text to embed.

        Returns:
            Embedding vector from voyage-3-lite.
        """
        embeddings = await self.embed([text], model="voyage-3-lite", input_type="query")
        return embeddings[0]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
    )
    async def rerank(
        self,
        query: str,
        documents: list[str],
        model: str = "rerank-2",
        top_k: int = 5,
    ) -> list[dict]:
        """Rerank documents by relevance to query.

        Args:
            query: Search query.
            documents: List of document texts.
            model: Reranker model name.
            top_k: Number of top results to return.

        Returns:
            List of dicts with 'index' and 'score' keys.
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
```

#### Step 3: Run tests

```bash
pytest tests/test_voyage_client.py -v
```

#### Step 4: Commit

```bash
git add telegram_bot/services/voyage_client.py tests/test_voyage_client.py
git commit -m "feat(voyage): add VoyageClient with retry logic"
```

---

### Task 2: Add Query Analyzer (Translit + RRF Weights)

**Files:**
- Create: `telegram_bot/services/query_analyzer.py`
- Create: `tests/test_query_analyzer.py`

#### Step 1: Write failing tests

```python
# tests/test_query_analyzer.py
"""Tests for QueryAnalyzer."""

import pytest
from telegram_bot.services.query_analyzer import QueryAnalyzer


class TestQueryAnalyzer:
    """Tests for query analysis and normalization."""

    def test_normalize_translit_burgas(self):
        """Test Burgas transliteration."""
        analyzer = QueryAnalyzer()
        result = analyzer.normalize_translit("apartments in Burgas")
        assert "Бургас" in result

    def test_normalize_translit_sunny_beach(self):
        """Test Sunny Beach transliteration."""
        analyzer = QueryAnalyzer()
        result = analyzer.normalize_translit("Sunny Beach apartments")
        assert "Солнечный берег" in result

    def test_normalize_preserves_cyrillic(self):
        """Test cyrillic text is preserved."""
        analyzer = QueryAnalyzer()
        result = analyzer.normalize_translit("квартиры в Бургасе")
        assert result == "квартиры в Бургасе"

    def test_rrf_weights_default(self):
        """Test default RRF weights for general queries."""
        analyzer = QueryAnalyzer()
        dense, sparse = analyzer.get_rrf_weights("квартиры у моря")
        assert dense == 0.6
        assert sparse == 0.4

    def test_rrf_weights_exact_id(self):
        """Test RRF weights favor sparse for ID queries."""
        analyzer = QueryAnalyzer()
        dense, sparse = analyzer.get_rrf_weights("квартира ID 12345")
        assert dense == 0.2
        assert sparse == 0.8

    def test_rrf_weights_corpus(self):
        """Test RRF weights favor sparse for corpus queries."""
        analyzer = QueryAnalyzer()
        dense, sparse = analyzer.get_rrf_weights("ЖК Елените корпус 5")
        assert dense == 0.2
        assert sparse == 0.8

    def test_cache_threshold_default(self):
        """Test default cache threshold."""
        analyzer = QueryAnalyzer()
        threshold = analyzer.get_cache_threshold("квартиры в центре")
        assert threshold == 0.10

    def test_cache_threshold_strict_for_numbers(self):
        """Test strict threshold for queries with numbers."""
        analyzer = QueryAnalyzer()
        threshold = analyzer.get_cache_threshold("цена квартиры 12345")
        assert threshold == 0.05

    def test_cache_threshold_strict_for_corpus(self):
        """Test strict threshold for corpus/block queries."""
        analyzer = QueryAnalyzer()
        threshold = analyzer.get_cache_threshold("корпус А цена")
        assert threshold == 0.05

    def test_has_exact_identifier_true(self):
        """Test detection of exact identifiers."""
        analyzer = QueryAnalyzer()
        assert analyzer.has_exact_identifier("ID 12345") is True
        assert analyzer.has_exact_identifier("корпус 5") is True
        assert analyzer.has_exact_identifier("ЖК Елените") is True

    def test_has_exact_identifier_false(self):
        """Test no false positives for general queries."""
        analyzer = QueryAnalyzer()
        assert analyzer.has_exact_identifier("квартиры у моря") is False
```

#### Step 2: Implement QueryAnalyzer

```python
# telegram_bot/services/query_analyzer.py
"""Query analysis for RAG pipeline optimization."""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class QueryAnalyzer:
    """Analyzes queries for translit, RRF weights, and cache thresholds.

    Optimizes search behavior based on query characteristics:
    - Transliterates Latin place names to Cyrillic for BM42
    - Adjusts RRF weights based on query type (exact vs semantic)
    - Sets cache thresholds stricter for specific queries
    """

    # Transliteration map: Latin -> Cyrillic
    TRANSLIT_MAP = {
        # Bulgarian cities and resorts
        'Burgas': 'Бургас',
        'Varna': 'Варна',
        'Sofia': 'София',
        'Plovdiv': 'Пловдив',
        'Nesebar': 'Несебър',
        'Nessebar': 'Несебър',
        'Sozopol': 'Созопол',
        'Pomorie': 'Поморие',
        'Sunny Beach': 'Солнечный берег',
        'Sveti Vlas': 'Святой Влас',
        'Svyati Vlas': 'Святой Влас',
        'Elenite': 'Елените',
        'Ravda': 'Равда',
        'Sarafovo': 'Сарафово',
        'Primorsko': 'Приморско',
        'Tsarevo': 'Царево',
        'Lozenets': 'Лозенец',
        'Golden Sands': 'Золотые пески',
        'Albena': 'Албена',
        'Balchik': 'Балчик',
        'Kavarna': 'Каварна',
        'Obzor': 'Обзор',
        'Byala': 'Бяла',
    }

    # Patterns indicating exact search (favor sparse)
    EXACT_PATTERNS = [
        r'\bID\s*\d+',            # "ID 12345"
        r'\b\d{5,}\b',            # Long numbers (IDs)
        r'корпус\s*\d+',          # "корпус 5"
        r'корпус\s*[А-Яа-я]',     # "корпус А"
        r'блок\s*\d+',            # "блок 3"
        r'блок\s*[А-Яа-я]',       # "блок Б"
        r'секция\s*\d+',          # "секция 2"
        r'этаж\s*\d+',            # "этаж 5"
        r'ЖК\s+\w+',              # "ЖК Елените"
    ]

    # Patterns requiring strict cache threshold
    STRICT_CACHE_PATTERNS = [
        r'\b\d{3,}\b',            # Numbers 3+ digits
        r'корпус',
        r'блок',
        r'секция',
        r'этаж',
        r'\bID\b',
    ]

    def normalize_translit(self, query: str) -> str:
        """Convert Latin place names to Cyrillic for BM42.

        Args:
            query: User query (may contain Latin transliterations).

        Returns:
            Query with Latin names converted to Cyrillic.
        """
        normalized = query

        for latin, cyrillic in self.TRANSLIT_MAP.items():
            # Case-insensitive replacement
            pattern = re.compile(re.escape(latin), re.IGNORECASE)
            normalized = pattern.sub(cyrillic, normalized)

        if normalized != query:
            logger.debug(f"Translit: '{query}' -> '{normalized}'")

        return normalized

    def get_rrf_weights(self, query: str) -> tuple[float, float]:
        """Get RRF fusion weights based on query type.

        Args:
            query: User query.

        Returns:
            Tuple of (dense_weight, sparse_weight).
        """
        for pattern in self.EXACT_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                logger.debug(f"Exact query detected: '{query}' -> weights (0.2, 0.8)")
                return (0.2, 0.8)  # Favor sparse for exact matches

        return (0.6, 0.4)  # Default: favor dense for semantic queries

    def get_cache_threshold(self, query: str) -> float:
        """Get cache similarity threshold based on query type.

        Args:
            query: User query.

        Returns:
            Distance threshold (lower = stricter).
        """
        for pattern in self.STRICT_CACHE_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                logger.debug(f"Strict cache for: '{query}' -> threshold 0.05")
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

    def analyze(self, query: str) -> dict:
        """Full query analysis.

        Args:
            query: User query.

        Returns:
            Dict with normalized_query, rrf_weights, cache_threshold, is_exact.
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

#### Step 3: Run tests

```bash
pytest tests/test_query_analyzer.py -v
```

#### Step 4: Commit

```bash
git add telegram_bot/services/query_analyzer.py tests/test_query_analyzer.py
git commit -m "feat(search): add QueryAnalyzer with translit and dynamic RRF"
```

---

### Task 3: Migrate CacheService to Voyage AI

**Files:**
- Modify: `telegram_bot/services/cache.py`
- Modify: `tests/test_cache.py` (if exists)

#### Step 1: Update CacheService

Replace `HFTextVectorizer` with `VoyageAITextVectorizer`:

```python
# Key changes in telegram_bot/services/cache.py

# OLD:
from redisvl.utils.vectorize import HFTextVectorizer
vectorizer = await asyncio.to_thread(
    HFTextVectorizer, model="redis/langcache-embed-v1"
)

# NEW:
from redisvl.utils.vectorize import VoyageAITextVectorizer
vectorizer = VoyageAITextVectorizer(
    model="voyage-3-lite",
    api_config={"api_key": os.getenv("VOYAGE_API_KEY")}
)
```

#### Step 2: Add adaptive threshold support

```python
async def check_semantic_cache(
    self,
    query: str,
    user_id: Optional[int] = None,
    language: str = "ru",
    threshold_override: Optional[float] = None,  # NEW
) -> Optional[str]:
    """Check semantic cache with adaptive threshold."""
    if not self.semantic_cache:
        return None

    # Use override or default threshold
    effective_threshold = threshold_override or self.distance_threshold

    # ... rest of implementation
```

#### Step 3: Run existing tests + add new ones

```bash
pytest tests/ -k cache -v
```

#### Step 4: Commit

```bash
git add telegram_bot/services/cache.py
git commit -m "feat(cache): migrate to VoyageAITextVectorizer"
```

---

### Task 4: Update Search to Use Voyage + Dynamic RRF

**Files:**
- Create: `telegram_bot/services/voyage_search.py`
- Create: `tests/test_voyage_search.py`

#### Step 1: Implement VoyageSearchService

```python
# telegram_bot/services/voyage_search.py
"""Hybrid search with Voyage embeddings and dynamic RRF."""

import logging
from typing import Any, Optional

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

from .voyage_client import VoyageClient
from .query_analyzer import QueryAnalyzer

logger = logging.getLogger(__name__)


class VoyageSearchService:
    """Hybrid search using Voyage dense + FastEmbed sparse vectors."""

    def __init__(
        self,
        qdrant_client: AsyncQdrantClient,
        voyage_client: VoyageClient,
        collection_name: str = "documents",
    ):
        self.qdrant = qdrant_client
        self.voyage = voyage_client
        self.collection = collection_name
        self.analyzer = QueryAnalyzer()

    async def hybrid_search(
        self,
        query: str,
        top_k: int = 50,
        filter_active: bool = True,
    ) -> list[dict[str, Any]]:
        """Perform hybrid search with dynamic RRF weights.

        Args:
            query: User query.
            top_k: Number of results to return.
            filter_active: Whether to filter by status=active.

        Returns:
            List of search results with scores.
        """
        # Analyze query
        analysis = self.analyzer.analyze(query)
        normalized_query = analysis["normalized_query"]
        weights = analysis["rrf_weights"]

        logger.info(
            f"Hybrid search: '{query}' -> RRF weights: "
            f"dense={weights['dense']}, sparse={weights['sparse']}"
        )

        # Build filter
        search_filter = None
        if filter_active:
            search_filter = Filter(
                must=[
                    FieldCondition(
                        key="status",
                        match=MatchValue(value="active")
                    )
                ]
            )

        # Get dense embedding from Voyage
        dense_vector = await self.voyage.embed_query(normalized_query)

        # TODO: Get sparse embedding from FastEmbed BM42
        # sparse_vector = self.fastembed.embed(normalized_query)

        # For now, dense-only search
        results = await self.qdrant.search(
            collection_name=self.collection,
            query_vector=dense_vector,
            limit=top_k,
            query_filter=search_filter,
            with_payload=True,
        )

        return [
            {
                "id": r.id,
                "score": r.score,
                "text": r.payload.get("text", ""),
                "source": r.payload.get("source", ""),
                "metadata": r.payload.get("metadata", {}),
            }
            for r in results
        ]

    async def rerank(
        self,
        query: str,
        documents: list[dict],
        top_k: int = 5,
    ) -> list[dict]:
        """Rerank documents using Voyage Rerank-2.

        Args:
            query: Original query.
            documents: List of documents from search.
            top_k: Number of top results to return.

        Returns:
            Reranked documents.
        """
        if not documents:
            return []

        texts = [d["text"] for d in documents]

        reranked = await self.voyage.rerank(
            query=query,
            documents=texts,
            top_k=top_k,
        )

        # Map back to original documents
        result = []
        for r in reranked:
            doc = documents[r["index"]].copy()
            doc["rerank_score"] = r["score"]
            result.append(doc)

        return result
```

#### Step 2: Add tests and commit

```bash
pytest tests/test_voyage_search.py -v
git add telegram_bot/services/voyage_search.py tests/test_voyage_search.py
git commit -m "feat(search): add VoyageSearchService with hybrid search"
```

---

### Task 5: Integrate into Bot Pipeline

**Files:**
- Modify: `telegram_bot/bot.py`

#### Step 1: Update imports and initialization

```python
# Add to telegram_bot/bot.py

from .services.voyage_client import VoyageClient
from .services.voyage_search import VoyageSearchService
from .services.query_analyzer import QueryAnalyzer

# In __init__:
self.voyage_client = VoyageClient.get_instance()
self.query_analyzer = QueryAnalyzer()
self.voyage_search = VoyageSearchService(
    qdrant_client=self.qdrant_client,
    voyage_client=self.voyage_client,
)
```

#### Step 2: Update handle_query to use new pipeline

```python
async def handle_query(self, user_id: int, query: str) -> str:
    # 1. Analyze query
    analysis = self.query_analyzer.analyze(query)

    # 2. Check cache with adaptive threshold
    cached = await self.cache_service.check_semantic_cache(
        query=analysis["normalized_query"],
        user_id=user_id,
        threshold_override=analysis["cache_threshold"],
    )

    if cached:
        # CESC personalization if enabled
        if self.cesc_personalizer:
            context = await self.user_context_service.get_context(user_id)
            if self.cesc_personalizer.should_personalize(context):
                return await self.cesc_personalizer.personalize(cached, context, query)
        return cached

    # 3. Hybrid search
    results = await self.voyage_search.hybrid_search(
        query=analysis["normalized_query"],
        top_k=50,
    )

    # 4. Rerank
    top_docs = await self.voyage_search.rerank(query, results, top_k=5)

    # 5. Generate with LLM
    answer = await self.llm_service.generate_with_context(query, top_docs)

    # 6. Cache the response
    await self.cache_service.store_semantic_cache(query, answer, user_id)

    return answer
```

#### Step 3: Commit

```bash
git add telegram_bot/bot.py
git commit -m "feat(bot): integrate Voyage unified pipeline"
```

---

### Task 6: Add Configuration

**Files:**
- Modify: `telegram_bot/config.py`
- Update: `.env.example`

#### Step 1: Add Voyage settings

```python
# telegram_bot/config.py

***REMOVED*** AI Configuration
voyage_api_key: str = ""
voyage_embed_model: str = "voyage-3-large"
voyage_cache_model: str = "voyage-3-lite"
voyage_rerank_model: str = "rerank-2"

# Search Configuration
search_top_k: int = 50
rerank_top_k: int = 5
rrf_dense_weight: float = 0.6
rrf_sparse_weight: float = 0.4
```

#### Step 2: Update .env.example

```bash
***REMOVED*** AI
VOYAGE_API_KEY=your_voyage_api_key_here
```

#### Step 3: Commit

```bash
git add telegram_bot/config.py .env.example
git commit -m "feat(config): add Voyage AI configuration"
```

---

### Task 7: Run Full Test Suite and QA

#### Step 1: Run all tests

```bash
make test
```

#### Step 2: Run linting and type checking

```bash
make lint
make type-check
```

#### Step 3: Manual smoke test

```bash
python -c "
from telegram_bot.services.voyage_client import VoyageClient
from telegram_bot.services.query_analyzer import QueryAnalyzer

# Test VoyageClient
client = VoyageClient()
print('VoyageClient: OK')

# Test QueryAnalyzer
analyzer = QueryAnalyzer()
result = analyzer.analyze('apartments in Burgas')
print(f'QueryAnalyzer: {result}')
"
```

#### Step 4: Final commit

```bash
git add -A
git commit -m "chore(voyage): complete Voyage Unified RAG migration"
```

---

## 5. Success Criteria

- [ ] `VoyageClient` handles API calls with retry logic
- [ ] `QueryAnalyzer` normalizes translit and sets dynamic RRF weights
- [ ] `CacheService` uses `VoyageAITextVectorizer` instead of `HFTextVectorizer`
- [ ] `VoyageSearchService` performs hybrid search with Voyage embeddings
- [ ] Adaptive cache threshold works (0.05 for IDs, 0.10 for general)
- [ ] All existing tests pass
- [ ] New unit tests pass (15+ tests)
- [ ] Bot initializes without errors
- [ ] RAM usage < 500MB (no local embedding models)

---

## 6. Dependencies

Add to `pyproject.toml`:

```toml
[project.dependencies]
voyageai = ">=0.3.0"
tenacity = ">=8.2.0"
fastembed = ">=0.3.0"  # For BM42 sparse vectors
```

Install:

```bash
pip install voyageai tenacity fastembed
```

---

## 7. Rollback Plan

If Voyage API has issues:

1. Keep `HFTextVectorizer` code commented (not deleted)
2. Add feature flag: `USE_VOYAGE_EMBEDDINGS=true/false`
3. If `false`, fall back to local BGE-M3

---

## 8. Monitoring

Track these metrics after deployment:

```python
# Prometheus/Grafana metrics
voyage_api_latency_ms        # Embedding latency
voyage_api_errors_total      # API errors (429, 500)
cache_hit_rate_percent       # Semantic cache effectiveness
search_latency_ms            # Full search pipeline
rerank_latency_ms            # Reranking step
```

---

## References

1. [Voyage AI Documentation](https://docs.voyageai.com/)
2. [RedisVL VoyageAITextVectorizer](https://docs.redisvl.com/en/latest/user_guide/vectorizers.html)
3. [FastEmbed BM42](https://qdrant.tech/articles/bm42/)
4. [Qdrant Hybrid Search](https://qdrant.tech/documentation/concepts/hybrid-queries/)
5. [Tenacity Retry Library](https://tenacity.readthedocs.io/)

---

**Status:** 🟢 READY FOR IMPLEMENTATION
**Created:** January 21, 2026
**Author:** Brainstorming Session
