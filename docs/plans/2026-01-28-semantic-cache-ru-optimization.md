# Semantic Cache RU Optimization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Optimize semantic cache hit rate for Russian language queries by replacing voyage-3-lite with local deepvk/USER-base model and adjusting threshold.

**Architecture:** Replace VoyageAI vectorizer in CacheService with custom HTTP vectorizer that calls local USER-base service (port 8003). This eliminates API costs, reduces latency (~30ms → ~5ms), and improves RU paraphrase matching (ruMTEB #1 model).

**Tech Stack:** RedisVL, FastAPI (USER-base service), sentence-transformers, httpx

---

## Task 1: Create Custom Vectorizer for USER-base

**Files:**
- Create: `telegram_bot/services/vectorizers.py`
- Test: `tests/unit/test_vectorizers.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_vectorizers.py
"""Tests for custom vectorizers."""

import pytest
from unittest.mock import AsyncMock, patch

from telegram_bot.services.vectorizers import UserBaseVectorizer


class TestUserBaseVectorizer:
    """Tests for UserBaseVectorizer."""

    def test_init_with_default_url(self):
        """Should initialize with default USER-base URL."""
        vectorizer = UserBaseVectorizer()
        assert vectorizer.base_url == "http://localhost:8003"
        assert vectorizer.dims == 768

    def test_init_with_custom_url(self):
        """Should accept custom URL."""
        vectorizer = UserBaseVectorizer(base_url="http://user-base:8003")
        assert vectorizer.base_url == "http://user-base:8003"

    @pytest.mark.asyncio
    async def test_embed_single_text(self):
        """Should return 768-dim embedding for single text."""
        vectorizer = UserBaseVectorizer()

        mock_response = {"embedding": [0.1] * 768}

        with patch.object(vectorizer, "_client") as mock_client:
            mock_client.post = AsyncMock(return_value=AsyncMock(
                json=lambda: mock_response,
                raise_for_status=lambda: None
            ))

            result = await vectorizer.aembed("тестовый запрос")

            assert len(result) == 768
            mock_client.post.assert_called_once()

    def test_embed_sync(self):
        """Should provide sync wrapper."""
        vectorizer = UserBaseVectorizer()
        assert hasattr(vectorizer, "embed")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_vectorizers.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'telegram_bot.services.vectorizers'"

**Step 3: Write minimal implementation**

```python
# telegram_bot/services/vectorizers.py
"""Custom vectorizers for semantic cache.

UserBaseVectorizer: Local Russian embedding model (deepvk/USER-base).
Best-in-class for RU semantic matching (STS 74.35 on ruMTEB).
"""

import asyncio
import logging
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)


class UserBaseVectorizer:
    """Vectorizer using local USER-base service for Russian embeddings.

    Connects to USER-base FastAPI service running on port 8003.
    Returns 768-dimensional embeddings optimized for Russian text.

    Advantages over Voyage API:
    - Zero API cost (local)
    - Lower latency (~5ms vs ~30ms)
    - Best Russian semantic matching (ruMTEB #1)
    - On-premise (privacy)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8003",
        timeout: float = 5.0,
    ):
        """Initialize USER-base vectorizer.

        Args:
            base_url: URL of USER-base service
            timeout: Request timeout in seconds
        """
        self.base_url = base_url
        self.timeout = timeout
        self.dims = 768  # USER-base output dimension
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    async def aembed(self, text: str) -> List[float]:
        """Generate embedding for single text (async).

        Args:
            text: Text to embed

        Returns:
            768-dimensional embedding vector
        """
        client = await self._get_client()
        response = await client.post("/embed", json={"text": text})
        response.raise_for_status()
        data = response.json()
        return data["embedding"]

    async def aembed_many(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts (async).

        Args:
            texts: List of texts to embed

        Returns:
            List of 768-dimensional embedding vectors
        """
        client = await self._get_client()
        response = await client.post("/embed_batch", json={"texts": texts})
        response.raise_for_status()
        data = response.json()
        return data["embeddings"]

    def embed(self, text: str) -> List[float]:
        """Generate embedding for single text (sync wrapper).

        Args:
            text: Text to embed

        Returns:
            768-dimensional embedding vector
        """
        return asyncio.run(self.aembed(text))

    def embed_many(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts (sync wrapper).

        Args:
            texts: List of texts to embed

        Returns:
            List of 768-dimensional embedding vectors
        """
        return asyncio.run(self.aembed_many(texts))

    async def aclose(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_vectorizers.py -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add telegram_bot/services/vectorizers.py tests/unit/test_vectorizers.py
git commit -m "feat(cache): add UserBaseVectorizer for Russian semantic cache"
```

---

## Task 2: Create RedisVL-Compatible Wrapper

**Files:**
- Modify: `telegram_bot/services/vectorizers.py`
- Test: `tests/unit/test_vectorizers.py`

**Step 1: Write the failing test**

```python
# Add to tests/unit/test_vectorizers.py

class TestUserBaseVectorizerRedisVL:
    """Tests for RedisVL compatibility."""

    def test_has_redisvl_interface(self):
        """Should implement RedisVL vectorizer interface."""
        vectorizer = UserBaseVectorizer()

        # RedisVL expects these methods
        assert hasattr(vectorizer, "embed")
        assert hasattr(vectorizer, "embed_many")
        assert callable(vectorizer.embed)
        assert callable(vectorizer.embed_many)

    def test_dims_property(self):
        """Should expose dims for RedisVL SemanticCache."""
        vectorizer = UserBaseVectorizer()
        assert vectorizer.dims == 768
```

**Step 2: Run test to verify it passes (already implemented)**

Run: `pytest tests/unit/test_vectorizers.py::TestUserBaseVectorizerRedisVL -v`
Expected: PASS (interface already matches)

**Step 3: Commit**

```bash
git add tests/unit/test_vectorizers.py
git commit -m "test(cache): verify RedisVL interface compatibility"
```

---

## Task 3: Update CacheService to Use USER-base

**Files:**
- Modify: `telegram_bot/services/cache.py:119-150`
- Test: `tests/unit/test_cache_service.py`

**Step 1: Write the failing test**

```python
# Add to tests/unit/test_cache_service.py

class TestCacheServiceUserBase:
    """Tests for USER-base integration in CacheService."""

    @pytest.mark.asyncio
    async def test_semantic_cache_uses_userbase_when_configured(self):
        """Should use UserBaseVectorizer when USE_LOCAL_EMBEDDINGS=true."""
        with patch.dict(os.environ, {"USE_LOCAL_EMBEDDINGS": "true", "USER_BASE_URL": "http://localhost:8003"}):
            cache = CacheService(redis_url="redis://localhost:6379")
            # Check that the vectorizer type would be UserBaseVectorizer
            assert os.getenv("USE_LOCAL_EMBEDDINGS") == "true"

    def test_default_threshold_is_relaxed(self):
        """Should use 0.20 threshold for better RU paraphrase matching."""
        cache = CacheService(redis_url="redis://localhost:6379")
        assert cache.distance_threshold == 0.20
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_cache_service.py::TestCacheServiceUserBase -v`
Expected: FAIL with "AssertionError: 0.15 != 0.20"

**Step 3: Modify CacheService**

```python
# telegram_bot/services/cache.py

# Change line 47 (default threshold):
# FROM:
distance_threshold: float = 0.15,  # cosine distance threshold (0.15 ≈ 85% similarity)

# TO:
distance_threshold: float = 0.20,  # cosine distance threshold (0.20 ≈ 80% similarity, better for RU paraphrases)


# Change lines 119-150 (vectorizer initialization):
# FROM:
try:
    voyage_api_key = os.getenv("VOYAGE_API_KEY", "")
    if not voyage_api_key:
        logger.warning("VOYAGE_API_KEY not set, SemanticCache disabled")
        self.semantic_cache = None
    else:
        logger.info("Initializing SemanticCache with VoyageAI (voyage-3-lite)...")
        vectorizer = VoyageAITextVectorizer(
            model="voyage-3-lite",
            api_config={"api_key": voyage_api_key},
        )

# TO:
try:
    use_local = os.getenv("USE_LOCAL_EMBEDDINGS", "false").lower() == "true"

    if use_local:
        # Use local USER-base for Russian semantic matching (ruMTEB #1)
        from telegram_bot.services.vectorizers import UserBaseVectorizer

        user_base_url = os.getenv("USER_BASE_URL", "http://localhost:8003")
        logger.info(f"Initializing SemanticCache with USER-base ({user_base_url})...")
        vectorizer = UserBaseVectorizer(base_url=user_base_url)
    else:
        # Fallback to Voyage API
        voyage_api_key = os.getenv("VOYAGE_API_KEY", "")
        if not voyage_api_key:
            logger.warning("VOYAGE_API_KEY not set and USE_LOCAL_EMBEDDINGS=false, SemanticCache disabled")
            self.semantic_cache = None
            return

        logger.info("Initializing SemanticCache with VoyageAI (voyage-multilingual-2)...")
        vectorizer = VoyageAITextVectorizer(
            model="voyage-multilingual-2",  # Changed from voyage-3-lite for better RU support
            api_config={"api_key": voyage_api_key},
        )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_cache_service.py::TestCacheServiceUserBase -v`
Expected: PASS

**Step 5: Commit**

```bash
git add telegram_bot/services/cache.py tests/unit/test_cache_service.py
git commit -m "feat(cache): integrate USER-base for RU semantic cache

- Add USE_LOCAL_EMBEDDINGS env flag
- Change default threshold 0.15 → 0.20 for RU paraphrases
- Fallback to voyage-multilingual-2 if local disabled"
```

---

## Task 4: Update SemanticMessageHistory to Use USER-base

**Files:**
- Modify: `telegram_bot/services/cache.py:166-186`

**Step 1: Modify message history vectorizer**

```python
# telegram_bot/services/cache.py lines 166-186

# FROM:
try:
    voyage_api_key = os.getenv("VOYAGE_API_KEY", "")
    if voyage_api_key:
        history_vectorizer = VoyageAITextVectorizer(
            model="voyage-3-lite",
            api_config={"api_key": voyage_api_key},
        )

# TO:
try:
    if use_local:
        # Reuse USER-base for conversation history
        from telegram_bot.services.vectorizers import UserBaseVectorizer

        user_base_url = os.getenv("USER_BASE_URL", "http://localhost:8003")
        history_vectorizer = UserBaseVectorizer(base_url=user_base_url)
        logger.info("✓ SemanticMessageHistory initialized (USER-base)")
    else:
        voyage_api_key = os.getenv("VOYAGE_API_KEY", "")
        if voyage_api_key:
            history_vectorizer = VoyageAITextVectorizer(
                model="voyage-multilingual-2",  # Changed from voyage-3-lite
                api_config={"api_key": voyage_api_key},
            )
            logger.info("✓ SemanticMessageHistory initialized (voyage-multilingual-2)")
```

**Step 2: Run existing tests**

Run: `pytest tests/unit/test_cache_service.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add telegram_bot/services/cache.py
git commit -m "feat(cache): use USER-base for SemanticMessageHistory"
```

---

## Task 5: Update .env.example

**Files:**
- Modify: `.env.example`

**Step 1: Update environment variables**

```bash
# .env.example — add/modify these lines:

***REMOVED*** AI (updated models)
VOYAGE_API_KEY=your_voyage_api_key_here
VOYAGE_EMBED_MODEL=voyage-4-large
VOYAGE_CACHE_MODEL=voyage-multilingual-2
VOYAGE_RERANK_MODEL=rerank-2.5

# Local Embeddings (Russian-optimized)
USE_LOCAL_EMBEDDINGS=true
USER_BASE_URL=http://localhost:8003
```

**Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: update .env.example with USER-base and voyage-4 models"
```

---

## Task 6: Update docker-compose.dev.yml

**Files:**
- Modify: `docker-compose.dev.yml:273-288`

**Step 1: Add USE_LOCAL_EMBEDDINGS to bot service**

```yaml
# docker-compose.dev.yml — bot service environment section

# Add these lines:
      # Local Embeddings (Russian-optimized)
      USE_LOCAL_EMBEDDINGS: "true"
      USER_BASE_URL: http://user-base:8000
```

**Step 2: Commit**

```bash
git add docker-compose.dev.yml
git commit -m "feat(docker): enable local USER-base embeddings for bot"
```

---

## Task 7: Export UserBaseVectorizer in __init__.py

**Files:**
- Modify: `telegram_bot/services/__init__.py`

**Step 1: Add export**

```python
# telegram_bot/services/__init__.py — add to imports and __all__:

from telegram_bot.services.vectorizers import UserBaseVectorizer

__all__ = [
    # ... existing exports
    "UserBaseVectorizer",
]
```

**Step 2: Run import test**

Run: `python -c "from telegram_bot.services import UserBaseVectorizer; print('OK')"`
Expected: "OK"

**Step 3: Commit**

```bash
git add telegram_bot/services/__init__.py
git commit -m "feat(services): export UserBaseVectorizer"
```

---

## Task 8: Integration Test

**Files:**
- Create: `tests/integration/test_userbase_cache.py`

**Step 1: Write integration test**

```python
# tests/integration/test_userbase_cache.py
"""Integration tests for USER-base semantic cache."""

import os
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("USER_BASE_URL") is None,
    reason="USER_BASE_URL not set (requires running user-base service)"
)


class TestUserBaseCacheIntegration:
    """Integration tests requiring running services."""

    @pytest.mark.asyncio
    async def test_russian_paraphrase_matching(self):
        """Should match Russian paraphrases with USER-base."""
        from telegram_bot.services.vectorizers import UserBaseVectorizer

        vectorizer = UserBaseVectorizer(
            base_url=os.getenv("USER_BASE_URL", "http://localhost:8003")
        )

        # Test RU paraphrases
        query1 = "двухкомнатная квартира с видом на море"
        query2 = "двушка с морским видом"

        emb1 = await vectorizer.aembed(query1)
        emb2 = await vectorizer.aembed(query2)

        # Cosine similarity
        import numpy as np
        similarity = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))

        # Should be high for paraphrases (> 0.8)
        assert similarity > 0.8, f"Paraphrase similarity too low: {similarity}"

        await vectorizer.aclose()
```

**Step 2: Run integration test (requires docker services)**

Run: `docker compose -f docker-compose.dev.yml up -d user-base && pytest tests/integration/test_userbase_cache.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/integration/test_userbase_cache.py
git commit -m "test(integration): add Russian paraphrase matching test"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Create UserBaseVectorizer | `vectorizers.py`, `test_vectorizers.py` |
| 2 | Verify RedisVL compatibility | `test_vectorizers.py` |
| 3 | Update CacheService (threshold + vectorizer) | `cache.py`, `test_cache_service.py` |
| 4 | Update SemanticMessageHistory | `cache.py` |
| 5 | Update .env.example | `.env.example` |
| 6 | Update docker-compose | `docker-compose.dev.yml` |
| 7 | Export in __init__.py | `__init__.py` |
| 8 | Integration test | `test_userbase_cache.py` |

**Total commits:** 8
**Estimated time:** 30-45 minutes
