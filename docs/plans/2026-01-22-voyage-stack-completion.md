# Voyage AI Stack Completion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the Voyage AI RAG stack migration, fix RetrieverService filter issue, test full pipeline, and deploy Telegram bot in Docker.

**Architecture:** Telegram bot uses VoyageEmbeddingService (voyage-3-large, 1024-dim) for query embeddings, RetrieverService for dense search in Qdrant, VoyageRerankerService (rerank-2) for result quality improvement, and Cerebras qwen-3-32b for response generation with streaming.

**Tech Stack:** Python 3.12, aiogram 3.x, Voyage AI API, Qdrant, Redis Stack, Docker, pytest

---

## Task 1: Fix RetrieverService Empty Filter Bug

**Files:**
- Modify: `telegram_bot/services/retriever.py:121-163`
- Test: `tests/test_retriever_service.py` (create new)

**Context:** `_build_filter()` returns `models.Filter(must=[])` when filters dict is empty, which may cause issues. Should return `None` for no filter.

**Step 1: Write the failing test**

Create test file:

```python
# tests/test_retriever_service.py
"""Tests for RetrieverService."""

import pytest
from unittest.mock import MagicMock, patch


class TestRetrieverServiceFilters:
    """Test filter building logic."""

    def test_build_filter_returns_none_for_empty_dict(self):
        """Empty filters should return None, not empty Filter."""
        from telegram_bot.services import RetrieverService

        with patch.object(RetrieverService, '__init__', lambda self, *args, **kwargs: None):
            retriever = RetrieverService.__new__(RetrieverService)
            retriever.url = "http://localhost:6333"
            retriever.api_key = ""
            retriever.collection_name = "test"
            retriever.client = None
            retriever._is_healthy = False

            result = retriever._build_filter({})

            assert result is None, "Empty filters should return None"

    def test_build_filter_returns_filter_for_city(self):
        """Filter with city should return proper Filter object."""
        from telegram_bot.services import RetrieverService
        from qdrant_client import models

        with patch.object(RetrieverService, '__init__', lambda self, *args, **kwargs: None):
            retriever = RetrieverService.__new__(RetrieverService)

            result = retriever._build_filter({"city": "Несебр"})

            assert result is not None
            assert isinstance(result, models.Filter)
            assert len(result.must) == 1

    def test_build_base_filter_returns_none(self):
        """Base filter should return None (search all documents)."""
        from telegram_bot.services import RetrieverService

        with patch.object(RetrieverService, '__init__', lambda self, *args, **kwargs: None):
            retriever = RetrieverService.__new__(RetrieverService)

            result = retriever._build_base_filter()

            assert result is None
```

**Step 2: Run test to verify first test fails**

Run: `pytest tests/test_retriever_service.py::TestRetrieverServiceFilters::test_build_filter_returns_none_for_empty_dict -v`

Expected: FAIL - returns Filter object instead of None

**Step 3: Fix _build_filter to return None for empty conditions**

Edit `telegram_bot/services/retriever.py:121-163`:

```python
    def _build_filter(self, filters: dict[str, Any]) -> Optional[models.Filter]:
        """
        Build Qdrant Filter from extracted filters dict.

        Args:
            filters: Dict with extracted filters from QueryAnalyzer
                     Example: {"price": {"lt": 100000}, "city": "Несебр", "rooms": 2}

        Returns:
            Qdrant Filter object with dynamic filters, or None if no filters
        """
        if not filters:
            return None

        conditions = []

        for field, value in filters.items():
            # Exact match for strings and integers
            if isinstance(value, (str, int)):
                conditions.append(
                    models.FieldCondition(
                        key=f"metadata.{field}",
                        match=models.MatchValue(value=value),
                    )
                )
            # Range filter for numeric comparisons
            elif isinstance(value, dict):
                range_params = {}
                if "lt" in value:
                    range_params["lt"] = value["lt"]
                if "lte" in value:
                    range_params["lte"] = value["lte"]
                if "gt" in value:
                    range_params["gt"] = value["gt"]
                if "gte" in value:
                    range_params["gte"] = value["gte"]

                if range_params:
                    conditions.append(
                        models.FieldCondition(
                            key=f"metadata.{field}",
                            range=models.Range(**range_params),
                        )
                    )

        # Return None if no conditions were built
        if not conditions:
            return None

        return models.Filter(must=conditions)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_retriever_service.py -v`

Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add tests/test_retriever_service.py telegram_bot/services/retriever.py
git commit -m "fix(retriever): return None for empty filters

- _build_filter returns None when filters dict is empty
- _build_filter returns None when no conditions are built
- Adds test coverage for filter building logic

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Test Voyage Embedding Service Locally

**Files:**
- Test: existing `tests/test_voyage_embeddings.py`

**Step 1: Run existing embedding tests with mocks**

Run: `pytest tests/test_voyage_embeddings.py -v`

Expected: PASS (all tests use mocks)

**Step 2: Create manual integration test script**

Create `scripts/test_voyage_local.py`:

```python
#!/usr/bin/env python3
"""Manual test for Voyage services against live APIs."""

import asyncio
import os
import sys

# Ensure env is loaded
from dotenv import load_dotenv
load_dotenv()


async def test_embedding():
    """Test VoyageEmbeddingService with real API."""
    from telegram_bot.services import VoyageEmbeddingService

    print("Testing VoyageEmbeddingService...")
    svc = VoyageEmbeddingService()

    query = "квартира в Солнечном береге"
    embedding = await svc.embed_query(query)

    print(f"  Query: {query}")
    print(f"  Embedding dimension: {len(embedding)}")
    print(f"  First 5 values: {embedding[:5]}")

    assert len(embedding) == 1024, f"Expected 1024-dim, got {len(embedding)}"
    print("  ✓ Embedding test PASSED")
    return embedding


async def test_search(query_vector: list[float]):
    """Test RetrieverService with real Qdrant."""
    from telegram_bot.services import RetrieverService

    print("\nTesting RetrieverService...")
    retriever = RetrieverService(
        url=os.getenv("QDRANT_URL", "http://localhost:6333"),
        api_key=os.getenv("QDRANT_API_KEY", ""),
        collection_name=os.getenv("QDRANT_COLLECTION", "contextual_bulgaria_voyage"),
    )

    results = retriever.search(query_vector=query_vector, top_k=10, min_score=0.3)

    print(f"  Results: {len(results)} documents")
    for i, r in enumerate(results[:3], 1):
        print(f"  {i}. Score: {r['score']:.4f} - {r['metadata'].get('topic', 'N/A')[:50]}")

    assert len(results) > 0, "Expected at least 1 result"
    print("  ✓ Search test PASSED")
    return results


async def test_rerank(query: str, results: list):
    """Test VoyageRerankerService with real API."""
    from telegram_bot.services import VoyageRerankerService

    print("\nTesting VoyageRerankerService...")
    reranker = VoyageRerankerService()

    reranked = await reranker.rerank(query=query, documents=results, top_k=5)

    print(f"  Reranked: {len(reranked)} documents")
    for i, r in enumerate(reranked[:3], 1):
        print(f"  {i}. Rerank: {r['rerank_score']:.4f}, Original: {r['original_score']:.4f}")

    assert len(reranked) > 0, "Expected reranked results"
    print("  ✓ Rerank test PASSED")


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Voyage AI Local Integration Tests")
    print("=" * 60)

    query = "квартира в Солнечном береге"

    try:
        embedding = await test_embedding()
        results = await test_search(embedding)
        await test_rerank(query, results)

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED ✓")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
```

**Step 3: Run manual test**

Run: `python scripts/test_voyage_local.py`

Expected output:
```
============================================================
Voyage AI Local Integration Tests
============================================================
Testing VoyageEmbeddingService...
  Query: квартира в Солнечном береге
  Embedding dimension: 1024
  First 5 values: [-0.015..., ...]
  ✓ Embedding test PASSED

Testing RetrieverService...
  Results: 5+ documents
  1. Score: 0.55+ - Локации и способы покупки
  ✓ Search test PASSED

Testing VoyageRerankerService...
  Reranked: 5 documents
  ✓ Rerank test PASSED

============================================================
ALL TESTS PASSED ✓
============================================================
```

**Step 4: Commit**

```bash
git add scripts/test_voyage_local.py
git commit -m "test(voyage): add manual integration test script

- Tests embedding, search, and rerank against live services
- Verifies full pipeline works with real data

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Update .env for Voyage Collection

**Files:**
- Modify: `.env`

**Step 1: Check current .env has correct collection**

Run: `grep QDRANT_COLLECTION .env`

Expected: Should show `QDRANT_COLLECTION=contextual_bulgaria_voyage`

**Step 2: Update if needed**

If not set correctly, add/update:

```bash
# In .env file
QDRANT_COLLECTION=contextual_bulgaria_voyage
```

**Step 3: Verify**

Run: `grep -E "^QDRANT_COLLECTION|^VOYAGE_API_KEY" .env`

Expected:
```
VOYAGE_API_KEY=pa-rQ3NG6opBwcXXSJhy6CJNf12GTidDTTE5taB4_vebSq
QDRANT_COLLECTION=contextual_bulgaria_voyage
```

**Step 4: No commit** (sensitive file)

---

## Task 4: Build Telegram Bot Docker Image

**Files:**
- Use: `telegram_bot/Dockerfile`
- Use: `docker-compose.dev.yml`

**Step 1: Verify Dockerfile exists and is correct**

Run: `cat telegram_bot/Dockerfile | head -20`

Expected: Multi-stage build with python:3.12-slim

**Step 2: Build the image**

Run: `docker compose -f docker-compose.dev.yml build bot`

Expected: Build completes without errors

**Step 3: Verify image created**

Run: `docker images | grep -E "rag-fresh.*bot|dev.*bot"`

Expected: Image listed with recent timestamp

**Step 4: Commit any Dockerfile fixes**

```bash
git add telegram_bot/Dockerfile docker-compose.dev.yml
git commit -m "chore(docker): finalize bot Dockerfile

- Multi-stage build for smaller image
- Health check for import validation
- Non-root user for security

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Start Bot Container

**Files:**
- Use: `docker-compose.dev.yml`

**Step 1: Ensure dependencies are running**

Run: `docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "redis|qdrant"`

Expected: Both dev-redis and dev-qdrant show "Up" and "healthy"

**Step 2: Start bot container**

Run: `docker compose -f docker-compose.dev.yml up -d bot`

Expected: Container starts

**Step 3: Check bot logs**

Run: `docker logs dev-bot 2>&1 | head -30`

Expected: Should show "Starting bot..." and no Python errors

**Step 4: Verify bot is running**

Run: `docker ps --format "table {{.Names}}\t{{.Status}}" | grep bot`

Expected: `dev-bot    Up X seconds (health: starting)` or similar

**Step 5: No commit** (runtime only)

---

## Task 6: Verify Telegram API Connection

**Files:**
- None (API test)

**Step 1: Test Telegram API directly**

Run: `curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe" | python3 -m json.tool`

Expected:
```json
{
    "ok": true,
    "result": {
        "id": 8568271552,
        "is_bot": true,
        "first_name": "...",
        ...
    }
}
```

**Step 2: Check bot responds to /start**

Action: Open Telegram, find the bot, send `/start`

Expected: Bot responds with welcome message about Bulgarian property search

**Step 3: Test search query**

Action: Send message "квартира в Солнечном береге"

Expected: Bot shows "typing" indicator, then returns relevant results from the database

**Step 4: No commit** (manual test)

---

## Task 7: Run Full Test Suite

**Files:**
- All test files in `tests/`

**Step 1: Run all unit tests**

Run: `make test`

Expected: All tests pass (or note which ones fail)

**Step 2: Run Voyage-specific tests**

Run: `pytest tests/test_voyage*.py -v`

Expected: All 52+ Voyage tests pass

**Step 3: Run integration tests**

Run: `pytest tests/test_voyage_integration.py tests/test_hybrid_retriever.py tests/test_cesc_integration.py -v`

Expected: All integration tests pass

**Step 4: Check for any failures**

If any tests fail, note the failures and fix them before proceeding.

**Step 5: Commit test results** (if any fixes made)

```bash
git add tests/
git commit -m "test: fix failing tests after Voyage migration

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Update Documentation

**Files:**
- Modify: `CLAUDE.md` (line ~24 - collection name)
- Modify: `TODO.md`

**Step 1: Update CLAUDE.md with correct collection**

Check current collection reference:

```bash
grep -n "contextual_bulgaria" CLAUDE.md
```

Update any references from `contextual_bulgaria` to `contextual_bulgaria_voyage` where appropriate.

**Step 2: Update TODO.md**

Add completion status for Voyage migration tasks.

**Step 3: Commit documentation updates**

```bash
git add CLAUDE.md TODO.md
git commit -m "docs: update documentation for Voyage migration

- Collection name updated to contextual_bulgaria_voyage
- Voyage migration tasks marked complete

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Final Verification and Cleanup

**Files:**
- None

**Step 1: Verify all containers healthy**

Run: `docker ps --format "table {{.Names}}\t{{.Status}}" | head -10`

Expected: All containers (qdrant, redis, bot) showing "healthy" or "Up"

**Step 2: Verify collection has data**

Run: `curl -s http://localhost:6333/collections/contextual_bulgaria_voyage | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Points: {d[\"result\"][\"points_count\"]}')"`

Expected: `Points: 92`

**Step 3: Test end-to-end in Telegram**

Action: Send test query to bot in Telegram

Expected: Relevant response based on collection data

**Step 4: Final commit**

```bash
git status
git add -A
git commit -m "feat: complete Voyage AI stack migration

- Full pipeline working: embed -> search -> rerank -> LLM
- Bot containerized and responding in Telegram
- All tests passing
- 92 documents indexed with Voyage embeddings

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Success Criteria Checklist

After completing all tasks, verify:

- [ ] `pytest tests/test_retriever_service.py -v` passes
- [ ] `pytest tests/test_voyage*.py -v` passes (52+ tests)
- [ ] `make test` passes
- [ ] `docker ps` shows dev-bot running healthy
- [ ] Bot responds to `/start` in Telegram
- [ ] Search query returns relevant results
- [ ] No API rate limit errors in logs

---

## Rollback Instructions

If issues occur:

1. Stop bot: `docker compose -f docker-compose.dev.yml stop bot`
2. Revert collection: Set `QDRANT_COLLECTION=contextual_bulgaria` in `.env`
3. Old collection with BGE-M3 embeddings still available
4. Git revert: `git revert HEAD~N` (where N is commits to revert)
