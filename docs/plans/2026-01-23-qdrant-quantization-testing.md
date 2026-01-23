# Qdrant Binary Quantization Testing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add comprehensive tests for QdrantService binary quantization features and update documentation.

**Architecture:** Unit tests for quantization parameters, integration tests for A/B testing workflow, mock-based tests for API calls.

**Tech Stack:** pytest, pytest-asyncio, unittest.mock, AsyncQdrantClient mocks

---

## Summary of New Features in This Branch

The branch `claude/search-claude-markdown-Jwzwc` adds:

1. **Binary Quantization Support** (`telegram_bot/services/qdrant.py`):
   - `use_quantization` parameter (default: True) - 40x faster search
   - `quantization_rescore` parameter (default: True) - maintains accuracy
   - `quantization_oversampling` parameter (default: 2.0) - fetch 2x candidates

2. **A/B Testing Support**:
   - `quantization_ignore` parameter per-request - override quantization on/off
   - Enables comparison of quantized vs non-quantized search

3. **New Methods**:
   - `enable_binary_quantization()` - one-time collection setup
   - `get_collection_info()` - check quantization status

4. **Configuration** (`telegram_bot/config.py`):
   - `QDRANT_USE_QUANTIZATION` env var
   - `QDRANT_QUANTIZATION_RESCORE` env var
   - `QDRANT_QUANTIZATION_OVERSAMPLING` env var
   - `QDRANT_QUANTIZATION_ALWAYS_RAM` env var

5. **Cache Service Changes** (`telegram_bot/services/cache.py`):
   - Removed `UserBaseVectorizer` class
   - Switched to `VoyageAITextVectorizer` from redisvl

---

## Task 1: Create QdrantService Unit Tests

**Files:**
- Create: `tests/test_qdrant_service.py`

**Step 1: Create test file with fixtures**

```python
"""Tests for QdrantService with binary quantization support."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.services.qdrant import QdrantService


@pytest.fixture
def mock_qdrant_client():
    """Create mock AsyncQdrantClient."""
    client = AsyncMock()
    client.query_points = AsyncMock()
    client.update_collection = AsyncMock()
    client.get_collection = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.fixture
def qdrant_service(mock_qdrant_client):
    """Create QdrantService with mocked client."""
    with patch("telegram_bot.services.qdrant.AsyncQdrantClient", return_value=mock_qdrant_client):
        service = QdrantService(
            url="http://localhost:6333",
            collection_name="test_collection",
        )
        service._client = mock_qdrant_client
        return service
```

**Step 2: Run test to verify fixture works**

Run: `pytest tests/test_qdrant_service.py -v`
Expected: 0 tests collected (no tests yet)

**Step 3: Add test for quantization defaults**

```python
class TestQdrantServiceInit:
    """Test QdrantService initialization."""

    def test_default_quantization_enabled(self, qdrant_service):
        """Quantization should be enabled by default."""
        assert qdrant_service._use_quantization is True
        assert qdrant_service._quantization_rescore is True
        assert qdrant_service._quantization_oversampling == 2.0

    def test_quantization_disabled(self, mock_qdrant_client):
        """Test creating service with quantization disabled."""
        with patch("telegram_bot.services.qdrant.AsyncQdrantClient", return_value=mock_qdrant_client):
            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
                use_quantization=False,
            )
            assert service._use_quantization is False
```

**Step 4: Run tests**

Run: `pytest tests/test_qdrant_service.py -v`
Expected: PASS

**Step 5: Add hybrid_search_rrf quantization tests**

```python
class TestHybridSearchRRF:
    """Test hybrid_search_rrf with quantization."""

    @pytest.mark.asyncio
    async def test_search_with_quantization_enabled(self, qdrant_service, mock_qdrant_client):
        """Search should include quantization params when enabled."""
        # Setup mock response
        mock_point = MagicMock()
        mock_point.id = "test-id"
        mock_point.score = 0.95
        mock_point.payload = {"text": "test content", "metadata": {}}
        mock_qdrant_client.query_points.return_value = MagicMock(points=[mock_point])

        # Execute search
        results = await qdrant_service.hybrid_search_rrf(
            dense_vector=[0.1] * 1024,
            sparse_vector={"indices": [1, 2], "values": [0.5, 0.3]},
            top_k=5,
        )

        # Verify quantization params were passed
        call_kwargs = mock_qdrant_client.query_points.call_args.kwargs
        assert call_kwargs["search_params"] is not None
        assert call_kwargs["search_params"].quantization.ignore is False
        assert call_kwargs["search_params"].quantization.rescore is True
        assert call_kwargs["search_params"].quantization.oversampling == 2.0

    @pytest.mark.asyncio
    async def test_search_with_quantization_ignore(self, qdrant_service, mock_qdrant_client):
        """Test A/B testing with quantization_ignore=True."""
        mock_point = MagicMock()
        mock_point.id = "test-id"
        mock_point.score = 0.95
        mock_point.payload = {"text": "test", "metadata": {}}
        mock_qdrant_client.query_points.return_value = MagicMock(points=[mock_point])

        # Execute search with quantization disabled
        await qdrant_service.hybrid_search_rrf(
            dense_vector=[0.1] * 1024,
            sparse_vector={"indices": [1], "values": [0.5]},
            top_k=5,
            quantization_ignore=True,
        )

        # Verify quantization was disabled
        call_kwargs = mock_qdrant_client.query_points.call_args.kwargs
        assert call_kwargs["search_params"].quantization.ignore is True
```

**Step 6: Run tests**

Run: `pytest tests/test_qdrant_service.py::TestHybridSearchRRF -v`
Expected: PASS

**Step 7: Add enable_binary_quantization test**

```python
class TestBinaryQuantization:
    """Test binary quantization management."""

    @pytest.mark.asyncio
    async def test_enable_binary_quantization_success(self, qdrant_service, mock_qdrant_client):
        """Test enabling binary quantization on collection."""
        mock_qdrant_client.update_collection.return_value = None

        result = await qdrant_service.enable_binary_quantization(always_ram=True)

        assert result is True
        mock_qdrant_client.update_collection.assert_called_once()

    @pytest.mark.asyncio
    async def test_enable_binary_quantization_failure(self, qdrant_service, mock_qdrant_client):
        """Test graceful failure when enabling quantization."""
        mock_qdrant_client.update_collection.side_effect = Exception("Collection not found")

        result = await qdrant_service.enable_binary_quantization()

        assert result is False

    @pytest.mark.asyncio
    async def test_get_collection_info(self, qdrant_service, mock_qdrant_client):
        """Test getting collection info with quantization status."""
        mock_info = MagicMock()
        mock_info.points_count = 100
        mock_info.vectors_count = 100
        mock_info.status.value = "green"
        mock_info.config.quantization_config = "BinaryQuantization"
        mock_qdrant_client.get_collection.return_value = mock_info

        info = await qdrant_service.get_collection_info()

        assert info["name"] == "test_collection"
        assert info["points_count"] == 100
        assert info["quantization"] == "BinaryQuantization"
```

**Step 8: Run all tests**

Run: `pytest tests/test_qdrant_service.py -v`
Expected: All tests PASS

**Step 9: Commit**

```bash
git add tests/test_qdrant_service.py
git commit -m "test(qdrant): add unit tests for binary quantization features"
```

---

## Task 2: Add Config Tests

**Files:**
- Create: `tests/test_bot_config.py`

**Step 1: Write failing test for config defaults**

```python
"""Tests for BotConfig quantization settings."""

import os
from unittest.mock import patch

import pytest

from telegram_bot.config import BotConfig


class TestBotConfigQuantization:
    """Test quantization configuration."""

    def test_quantization_defaults(self):
        """Test default quantization settings."""
        config = BotConfig()
        assert config.qdrant_use_quantization is True
        assert config.qdrant_quantization_rescore is True
        assert config.qdrant_quantization_oversampling == 2.0
        assert config.qdrant_quantization_always_ram is True

    def test_quantization_from_env(self):
        """Test quantization settings from environment."""
        with patch.dict(os.environ, {
            "QDRANT_USE_QUANTIZATION": "false",
            "QDRANT_QUANTIZATION_RESCORE": "false",
            "QDRANT_QUANTIZATION_OVERSAMPLING": "3.5",
            "QDRANT_QUANTIZATION_ALWAYS_RAM": "false",
        }):
            # Need to reimport to pick up env vars
            from importlib import reload
            from telegram_bot import config
            reload(config)

            new_config = config.BotConfig()
            assert new_config.qdrant_use_quantization is False
            assert new_config.qdrant_quantization_rescore is False
            assert new_config.qdrant_quantization_oversampling == 3.5
            assert new_config.qdrant_quantization_always_ram is False
```

**Step 2: Run test**

Run: `pytest tests/test_bot_config.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_bot_config.py
git commit -m "test(config): add tests for quantization environment variables"
```

---

## Task 3: Add Cache Service Tests (VoyageAITextVectorizer)

**Files:**
- Create: `tests/test_cache_service.py`

**Step 1: Write test for VoyageAITextVectorizer usage**

```python
"""Tests for CacheService with VoyageAITextVectorizer."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from telegram_bot.services.cache import CacheService


class TestCacheServiceVectorizer:
    """Test CacheService uses VoyageAITextVectorizer."""

    def test_cache_service_uses_voyage_vectorizer(self):
        """Verify CacheService creates VoyageAITextVectorizer."""
        with patch("telegram_bot.services.cache.VoyageAITextVectorizer") as mock_vectorizer:
            with patch("telegram_bot.services.cache.redis.Redis"):
                with patch("telegram_bot.services.cache.SemanticCache"):
                    mock_vectorizer.return_value = MagicMock()

                    service = CacheService(
                        redis_url="redis://localhost:6379",
                        voyage_api_key="test-key",
                    )

                    mock_vectorizer.assert_called()
```

**Step 2: Run test**

Run: `pytest tests/test_cache_service.py -v`
Expected: PASS (or adjust based on actual CacheService implementation)

**Step 3: Commit**

```bash
git add tests/test_cache_service.py
git commit -m "test(cache): add tests for VoyageAITextVectorizer integration"
```

---

## Task 4: Run Full Test Suite and Verify

**Step 1: Run all new tests**

Run: `pytest tests/test_qdrant_service.py tests/test_bot_config.py tests/test_cache_service.py -v`
Expected: All PASS

**Step 2: Run lint check**

Run: `make lint`
Expected: No errors

**Step 3: Run type check**

Run: `make type-check`
Expected: No errors (or documented exclusions)

**Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: resolve lint/type issues in new tests"
```

---

## Task 5: Update .env.example

**Files:**
- Modify: `.env.example`

**Step 1: Add quantization variables to .env.example**

Add these lines to the Qdrant section:

```bash
# Qdrant Binary Quantization (2026 best practice)
QDRANT_USE_QUANTIZATION=true          # Enable binary quantization (40x faster)
QDRANT_QUANTIZATION_RESCORE=true      # Rescore with original vectors for accuracy
QDRANT_QUANTIZATION_OVERSAMPLING=2.0  # Fetch 2x candidates, rescore top_k
QDRANT_QUANTIZATION_ALWAYS_RAM=true   # Keep quantized vectors in RAM
```

**Step 2: Verify file**

Run: `grep -A4 QUANTIZATION .env.example`
Expected: Shows the new variables

**Step 3: Commit**

```bash
git add .env.example
git commit -m "docs: add quantization env vars to .env.example"
```

---

## Task 6: Final Verification

**Step 1: Run full test suite**

Run: `make test`
Expected: All tests pass

**Step 2: Run pre-commit checks**

Run: `make pre-commit`
Expected: All checks pass

**Step 3: Review branch status**

Run: `git log --oneline main..HEAD`
Expected: Shows original commits + new test commits

---

## Files Changed Summary

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_qdrant_service.py` | Create | Unit tests for quantization |
| `tests/test_bot_config.py` | Create | Config tests for env vars |
| `tests/test_cache_service.py` | Create | Cache service vectorizer tests |
| `.env.example` | Modify | Document new env vars |
