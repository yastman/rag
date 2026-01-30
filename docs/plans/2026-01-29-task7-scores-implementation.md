# Task 7: Langfuse Scores on All Exit Paths — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Write all 10 Langfuse scores on every exit path of `handle_query` using accumulator pattern with try/finally.

**Architecture:** Initialize scores dict at function start with defaults (0.0 = miss/not applied). Update scores as pipeline executes. Write all scores in `finally` block — guarantees execution on all 4 exit paths (CHITCHAT, cache hit, no results, LLM success).

**Tech Stack:** Langfuse SDK v3 (`score_current_trace`), Python `time` module for latency.

---

## Task 1: Add Failing Test for All 10 Scores on Cache Hit Path

**Files:**
- Modify: `tests/unit/test_bot_scores.py`

### Step 1: Write the failing test

Add to `tests/unit/test_bot_scores.py`:

```python
EXPECTED_SCORE_NAMES = {
    "query_type",
    "latency_total_ms",
    "semantic_cache_hit",
    "embeddings_cache_hit",
    "search_cache_hit",
    "rerank_applied",
    "rerank_cache_hit",
    "results_count",
    "no_results",
    "llm_used",
}


class TestHandleQueryScoresAllPaths:
    """Tests for scores on all exit paths."""

    @pytest.fixture
    def mock_message(self):
        """Create mock Telegram message."""
        message = MagicMock()
        message.text = "квартиры до 100000 евро"
        message.from_user.id = 123456789
        message.chat.id = 987654321
        message.message_id = 42
        message.answer = AsyncMock()
        message.bot.send_chat_action = AsyncMock()
        return message

    @pytest.fixture
    def bot_handler_full(self):
        """Create PropertyBot handler with all services mocked."""
        from telegram_bot.bot import PropertyBot
        from telegram_bot.config import BotConfig
        from telegram_bot.services import QueryType

        handler = PropertyBot.__new__(PropertyBot)
        handler.config = BotConfig(
            telegram_token="test",
            voyage_api_key="test",
            llm_api_key="test",
            llm_model="test-model",
            cesc_enabled=False,
        )
        handler._cache_initialized = True

        # Mock all services
        handler.cache_service = MagicMock()
        handler.cache_service.initialize = AsyncMock()
        handler.cache_service.get_cached_embedding = AsyncMock(return_value=[0.1] * 1024)
        handler.cache_service.check_semantic_cache = AsyncMock(return_value="Cached answer")
        handler.cache_service.log_metrics = MagicMock()

        return handler

    @pytest.mark.asyncio
    async def test_all_10_scores_on_cache_hit(self, bot_handler_full, mock_message):
        """Cache hit path should write all 10 scores."""
        from telegram_bot.services import QueryType

        with (
            patch("telegram_bot.bot.get_client") as mock_get_client,
            patch("telegram_bot.bot.classify_query") as mock_classify,
        ):
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse
            mock_classify.return_value = QueryType.COMPLEX

            await bot_handler_full.handle_query(mock_message)

            score_names = {
                c.kwargs["name"]
                for c in mock_langfuse.score_current_trace.call_args_list
            }
            assert score_names == EXPECTED_SCORE_NAMES, f"Missing: {EXPECTED_SCORE_NAMES - score_names}"
```

### Step 2: Run test to verify it fails

Run: `pytest tests/unit/test_bot_scores.py::TestHandleQueryScoresAllPaths::test_all_10_scores_on_cache_hit -v`

Expected: FAIL — Missing scores (only 3 written currently)

### Step 3: Commit test

```bash
git add tests/unit/test_bot_scores.py
git commit -m "$(cat <<'EOF'
test(bot): add failing test for all 10 Langfuse scores

Verifies cache hit path writes all expected scores.
Currently fails - only 3 of 10 scores written.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add Scores Accumulator and try/finally Structure

**Files:**
- Modify: `telegram_bot/bot.py:3-5, 169-175`

### Step 1: Add time import

At top of `telegram_bot/bot.py`, add import:

```python
import time
```

### Step 2: Add scores accumulator and try block start

Replace lines 169-175 in `handle_query`:

```python
    @observe(name="telegram-message")
    async def handle_query(self, message: Message):
        """Handle user query with multi-level caching RAG pipeline."""
        start_time = time.time()
        query = message.text or ""
        user_id = message.from_user.id
        logger.info(f"Query from {user_id}: {query}")

        # Scores accumulator - defaults are "miss" / "not applied"
        scores = {
            "semantic_cache_hit": 0.0,
            "embeddings_cache_hit": 0.0,
            "search_cache_hit": 0.0,
            "rerank_applied": 0.0,
            "rerank_cache_hit": 0.0,
            "llm_used": 0.0,
            "no_results": 0.0,
            "results_count": 0.0,
        }
        query_type = QueryType.SIMPLE  # Default for early exceptions

        try:
            # Context fingerprint for cache isolation + trace filtering
            request_id = f"tg:{message.chat.id}:{message.message_id}"
```

### Step 3: Run existing tests to verify no regression

Run: `pytest tests/unit/test_bot_scores.py -v`

Expected: Existing tests still pass (structure change only, no logic change yet)

### Step 4: Commit

```bash
git add telegram_bot/bot.py
git commit -m "$(cat <<'EOF'
refactor(bot): add scores accumulator and try block structure

- Add time import for latency tracking
- Initialize scores dict with defaults (0.0 = miss/not applied)
- Add try block start (finally block in next task)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Add finally Block with Score Writing

**Files:**
- Modify: `telegram_bot/bot.py:408-412`

### Step 1: Replace cache metrics logging with finally block

Replace the end of `handle_query` (after `store_semantic_cache`, around line 408-412):

Old code:
```python
        # Log cache metrics
        self.cache_service.log_metrics()
```

New code:
```python
        finally:
            # Write all scores - guaranteed on ALL exit paths
            langfuse = get_client()
            query_type_map = {"chitchat": 0, "simple": 1, "complex": 2}
            langfuse.score_current_trace(
                name="query_type",
                value=float(query_type_map.get(query_type.value, 1)),
            )
            langfuse.score_current_trace(
                name="latency_total_ms",
                value=(time.time() - start_time) * 1000,
            )
            for name, value in scores.items():
                langfuse.score_current_trace(name=name, value=value)

            self.cache_service.log_metrics()
```

### Step 2: Run test to check progress

Run: `pytest tests/unit/test_bot_scores.py::TestHandleQueryScoresAllPaths::test_all_10_scores_on_cache_hit -v`

Expected: Still FAIL — scores dict values not updated yet

### Step 3: Commit

```bash
git add telegram_bot/bot.py
git commit -m "$(cat <<'EOF'
refactor(bot): add finally block for guaranteed score writing

- Write all 10 scores in finally block
- Includes query_type and latency_total_ms
- Iterates over scores dict for remaining 8 scores

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Update Embeddings Cache Score

**Files:**
- Modify: `telegram_bot/bot.py:229-237`

### Step 1: Update embeddings cache block

Find the embeddings cache block (around line 229-237) and update:

```python
        # 1. Generate embedding (with embeddings cache - Tier 1)
        query_vector = await self.cache_service.get_cached_embedding(query)
        if query_vector is None:
            query_vector = await self.voyage_service.embed_query(query)
            await self.cache_service.store_embedding(query, query_vector)
            logger.info(f"Generated embedding: {len(query_vector)}-dim")
        else:
            scores["embeddings_cache_hit"] = 1.0
            logger.info(f"✓ Using cached embedding: {len(query_vector)}-dim")
```

### Step 2: Run tests

Run: `pytest tests/unit/test_bot_scores.py -v`

Expected: Tests pass (embeddings_cache_hit now updated)

### Step 3: Commit

```bash
git add telegram_bot/bot.py
git commit -m "$(cat <<'EOF'
feat(bot): track embeddings_cache_hit score

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Update Semantic Cache Score and Remove Inline Scores

**Files:**
- Modify: `telegram_bot/bot.py:240-261`

### Step 1: Update semantic cache block

Find the semantic cache block (around line 240-261) and replace:

Old code (with inline scores):
```python
        # 2. Check semantic cache (Tier 1 - highest priority)
        cached_answer = await self.cache_service.check_semantic_cache(query)
        if cached_answer:
            # CESC personalization...
            await message.answer(cached_answer, parse_mode="Markdown")

            # Log scores to Langfuse (cache hit path)
            query_type_map = {"chitchat": 0, "simple": 1, "complex": 2}
            langfuse.score_current_trace(name="semantic_cache_hit", value=1.0)
            langfuse.score_current_trace(
                name="query_type",
                value=float(query_type_map.get(query_type.value, 1)),
            )
            langfuse.score_current_trace(name="results_count", value=0.0)

            self.cache_service.log_metrics()
            return
```

New code (scores via accumulator):
```python
        # 2. Check semantic cache (Tier 1 - highest priority)
        # Uses langcache-embed-v1 (256-dim) for fast cache matching
        cached_answer = await self.cache_service.check_semantic_cache(query)
        if cached_answer:
            scores["semantic_cache_hit"] = 1.0
            # CESC: Personalize only if lazy routing determined it's needed
            if needs_personalization and self.cesc_personalizer.should_personalize(user_context):
                cached_answer = await self.cesc_personalizer.personalize(
                    cached_response=cached_answer,
                    user_context=user_context,
                    query=query,
                )
            await message.answer(cached_answer, parse_mode="Markdown")
            return  # finally block writes scores
```

### Step 2: Run the failing test

Run: `pytest tests/unit/test_bot_scores.py::TestHandleQueryScoresAllPaths::test_all_10_scores_on_cache_hit -v`

Expected: PASS — all 10 scores now written on cache hit path

### Step 3: Run all score tests

Run: `pytest tests/unit/test_bot_scores.py -v`

Expected: All tests pass

### Step 4: Commit

```bash
git add telegram_bot/bot.py
git commit -m "$(cat <<'EOF'
feat(bot): track semantic_cache_hit via accumulator

- Remove inline score_current_trace calls
- Set scores["semantic_cache_hit"] = 1.0 on cache hit
- finally block handles all score writing

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Add Test for Cache Miss + LLM Path

**Files:**
- Modify: `tests/unit/test_bot_scores.py`

### Step 1: Write the test

Add to `TestHandleQueryScoresAllPaths` class:

```python
    @pytest.mark.asyncio
    async def test_all_10_scores_on_llm_path(self, bot_handler_full, mock_message):
        """LLM generation path should write all 10 scores with correct values."""
        from telegram_bot.services import QueryType

        # Configure for cache miss + LLM path
        bot_handler_full.cache_service.check_semantic_cache = AsyncMock(return_value=None)
        bot_handler_full.cache_service.get_cached_analysis = AsyncMock(return_value=None)
        bot_handler_full.cache_service.get_cached_search = AsyncMock(return_value=None)
        bot_handler_full.cache_service.get_cached_sparse_embedding = AsyncMock(return_value=None)
        bot_handler_full.cache_service.get_cached_rerank = AsyncMock(return_value=None)
        bot_handler_full.cache_service.store_analysis = AsyncMock()
        bot_handler_full.cache_service.store_search_results = AsyncMock()
        bot_handler_full.cache_service.store_sparse_embedding = AsyncMock()
        bot_handler_full.cache_service.store_rerank_results = AsyncMock()
        bot_handler_full.cache_service.get_conversation_history = AsyncMock(return_value=[])
        bot_handler_full.cache_service.store_conversation_message = AsyncMock()
        bot_handler_full.cache_service.store_semantic_cache = AsyncMock()

        # Mock query analyzer
        bot_handler_full.query_analyzer = MagicMock()
        bot_handler_full.query_analyzer.analyze = AsyncMock(
            return_value={"filters": {}, "semantic_query": "test"}
        )

        # Mock Qdrant service
        bot_handler_full.qdrant_service = MagicMock()
        bot_handler_full.qdrant_service.hybrid_search_rrf = AsyncMock(
            return_value=[{"text": "Result 1", "id": "1"}, {"text": "Result 2", "id": "2"}]
        )

        # Mock Voyage service
        bot_handler_full.voyage_service = MagicMock()
        bot_handler_full.voyage_service.embed_query = AsyncMock(return_value=[0.1] * 1024)
        bot_handler_full.voyage_service.rerank = AsyncMock(
            return_value=[{"index": 0, "score": 0.9}, {"index": 1, "score": 0.8}]
        )

        # Mock LLM service
        bot_handler_full.llm_service = MagicMock()
        bot_handler_full.llm_service.stream_answer = AsyncMock(
            return_value=AsyncIteratorMock(["Test ", "answer"])
        )

        # Mock BM42 sparse vector
        bot_handler_full._http_client = MagicMock()
        bot_handler_full.bm42_url = "http://test"
        bot_handler_full._get_sparse_vector = AsyncMock(
            return_value={"indices": [1, 2], "values": [0.5, 0.3]}
        )

        with (
            patch("telegram_bot.bot.get_client") as mock_get_client,
            patch("telegram_bot.bot.classify_query") as mock_classify,
            patch("telegram_bot.bot.needs_rerank") as mock_needs_rerank,
        ):
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse
            mock_classify.return_value = QueryType.COMPLEX
            mock_needs_rerank.return_value = True

            # Mock message.answer to return a message for editing
            mock_temp_message = MagicMock()
            mock_temp_message.edit_text = AsyncMock()
            mock_message.answer = AsyncMock(return_value=mock_temp_message)

            await bot_handler_full.handle_query(mock_message)

            score_names = {
                c.kwargs["name"]
                for c in mock_langfuse.score_current_trace.call_args_list
            }
            assert score_names == EXPECTED_SCORE_NAMES

            # Verify LLM-specific scores
            scores_dict = {
                c.kwargs["name"]: c.kwargs["value"]
                for c in mock_langfuse.score_current_trace.call_args_list
            }
            assert scores_dict["llm_used"] == 1.0
            assert scores_dict["semantic_cache_hit"] == 0.0
            assert scores_dict["results_count"] == 2.0


class AsyncIteratorMock:
    """Mock for async iterator (streaming)."""

    def __init__(self, items):
        self.items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.items)
        except StopIteration:
            raise StopAsyncIteration
```

### Step 2: Run test to verify it fails

Run: `pytest tests/unit/test_bot_scores.py::TestHandleQueryScoresAllPaths::test_all_10_scores_on_llm_path -v`

Expected: FAIL — `llm_used` not set yet

### Step 3: Commit test

```bash
git add tests/unit/test_bot_scores.py
git commit -m "$(cat <<'EOF'
test(bot): add failing test for LLM path scores

Verifies cache miss + LLM generation writes all 10 scores.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Update Search Cache and Rerank Scores

**Files:**
- Modify: `telegram_bot/bot.py:274-351`

### Step 1: Update search cache block

Find the search block (around line 274) and update the cache hit case:

```python
        # 4. Search in Qdrant with hybrid search
        results = await self.cache_service.get_cached_search(query_vector, filters)
        if results is not None:
            scores["search_cache_hit"] = 1.0
        else:
```

### Step 2: Update rerank block

Find the rerank block (around line 312) and update:

```python
            ***REMOVED*** rerank with cache (2026 best practice)
            # Skip rerank for simple queries or few results
            if results and needs_rerank(query_type, len(results)):
                scores["rerank_applied"] = 1.0
                doc_ids = [r.get("id", str(i)) for i, r in enumerate(results)]

                # Check rerank cache first
                cached_rerank = await self.cache_service.get_cached_rerank(
                    query_embedding=query_vector,
                    doc_ids=doc_ids,
                    collection=self.config.qdrant_collection,
                )

                if cached_rerank:
                    scores["rerank_cache_hit"] = 1.0
                    # Rebuild results from cached scores
```

### Step 3: Run tests

Run: `pytest tests/unit/test_bot_scores.py -v`

Expected: Tests progress (search/rerank scores now tracked)

### Step 4: Commit

```bash
git add telegram_bot/bot.py
git commit -m "$(cat <<'EOF'
feat(bot): track search_cache_hit, rerank_applied, rerank_cache_hit

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Update No Results and LLM Scores

**Files:**
- Modify: `telegram_bot/bot.py:355-401`

### Step 1: Update results_count after search

After the search/rerank block, before the no results check:

```python
        scores["results_count"] = float(len(results)) if results else 0.0
```

### Step 2: Update no results block

Find the no results block (around line 357) and update:

```python
        if not results:
            scores["no_results"] = 1.0
            await message.answer(
                "😔 Ничего не нашел по вашему запросу.\n\nПопробуйте переформулировать запрос."
            )
            return  # finally block writes scores
```

### Step 3: Update LLM generation block

Before the streaming LLM code (around line 369), add:

```python
        scores["llm_used"] = 1.0

        # 6. Generate answer with LLM STREAMING
        temp_message = await message.answer("🔍 Генерирую ответ...")
```

### Step 4: Run the LLM path test

Run: `pytest tests/unit/test_bot_scores.py::TestHandleQueryScoresAllPaths::test_all_10_scores_on_llm_path -v`

Expected: PASS

### Step 5: Run all tests

Run: `pytest tests/unit/test_bot_scores.py -v`

Expected: All tests pass

### Step 6: Commit

```bash
git add telegram_bot/bot.py
git commit -m "$(cat <<'EOF'
feat(bot): track results_count, no_results, llm_used scores

All 10 scores now tracked on cache miss + LLM path.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Add Tests for No Results and CHITCHAT Paths

**Files:**
- Modify: `tests/unit/test_bot_scores.py`

### Step 1: Add no results test

Add to `TestHandleQueryScoresAllPaths`:

```python
    @pytest.mark.asyncio
    async def test_all_10_scores_on_no_results_path(self, bot_handler_full, mock_message):
        """No results path should write all 10 scores with no_results=1.0."""
        from telegram_bot.services import QueryType

        # Configure for no results path
        bot_handler_full.cache_service.check_semantic_cache = AsyncMock(return_value=None)
        bot_handler_full.cache_service.get_cached_analysis = AsyncMock(return_value=None)
        bot_handler_full.cache_service.get_cached_search = AsyncMock(return_value=None)
        bot_handler_full.cache_service.get_cached_sparse_embedding = AsyncMock(return_value=None)
        bot_handler_full.cache_service.store_analysis = AsyncMock()
        bot_handler_full.cache_service.store_search_results = AsyncMock()
        bot_handler_full.cache_service.store_sparse_embedding = AsyncMock()

        bot_handler_full.query_analyzer = MagicMock()
        bot_handler_full.query_analyzer.analyze = AsyncMock(
            return_value={"filters": {}, "semantic_query": "test"}
        )

        bot_handler_full.qdrant_service = MagicMock()
        bot_handler_full.qdrant_service.hybrid_search_rrf = AsyncMock(return_value=[])

        bot_handler_full.voyage_service = MagicMock()
        bot_handler_full.voyage_service.embed_query = AsyncMock(return_value=[0.1] * 1024)

        bot_handler_full._get_sparse_vector = AsyncMock(
            return_value={"indices": [], "values": []}
        )

        with (
            patch("telegram_bot.bot.get_client") as mock_get_client,
            patch("telegram_bot.bot.classify_query") as mock_classify,
        ):
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse
            mock_classify.return_value = QueryType.SIMPLE

            await bot_handler_full.handle_query(mock_message)

            score_names = {
                c.kwargs["name"]
                for c in mock_langfuse.score_current_trace.call_args_list
            }
            assert score_names == EXPECTED_SCORE_NAMES

            scores_dict = {
                c.kwargs["name"]: c.kwargs["value"]
                for c in mock_langfuse.score_current_trace.call_args_list
            }
            assert scores_dict["no_results"] == 1.0
            assert scores_dict["llm_used"] == 0.0
            assert scores_dict["results_count"] == 0.0
```

### Step 2: Add CHITCHAT test

Add to `TestHandleQueryScoresAllPaths`:

```python
    @pytest.mark.asyncio
    async def test_all_10_scores_on_chitchat_path(self, bot_handler_full, mock_message):
        """CHITCHAT path should write all 10 scores with query_type=0."""
        from telegram_bot.services import QueryType

        mock_message.text = "Привет!"

        with (
            patch("telegram_bot.bot.get_client") as mock_get_client,
            patch("telegram_bot.bot.classify_query") as mock_classify,
            patch("telegram_bot.bot.get_chitchat_response") as mock_chitchat,
        ):
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse
            mock_classify.return_value = QueryType.CHITCHAT
            mock_chitchat.return_value = "Привет! Чем могу помочь?"

            await bot_handler_full.handle_query(mock_message)

            score_names = {
                c.kwargs["name"]
                for c in mock_langfuse.score_current_trace.call_args_list
            }
            assert score_names == EXPECTED_SCORE_NAMES

            scores_dict = {
                c.kwargs["name"]: c.kwargs["value"]
                for c in mock_langfuse.score_current_trace.call_args_list
            }
            assert scores_dict["query_type"] == 0.0  # CHITCHAT
            assert scores_dict["semantic_cache_hit"] == 0.0
            assert scores_dict["llm_used"] == 0.0
```

### Step 3: Run all new tests

Run: `pytest tests/unit/test_bot_scores.py::TestHandleQueryScoresAllPaths -v`

Expected: All 4 tests pass

### Step 4: Commit

```bash
git add tests/unit/test_bot_scores.py
git commit -m "$(cat <<'EOF'
test(bot): add tests for no_results and CHITCHAT paths

Verifies all 10 scores written on all 4 exit paths.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Add Latency Test

**Files:**
- Modify: `tests/unit/test_bot_scores.py`

### Step 1: Add latency test

Add to `TestHandleQueryScoresAllPaths`:

```python
    @pytest.mark.asyncio
    async def test_latency_recorded_positive(self, bot_handler_full, mock_message):
        """latency_total_ms should be > 0."""
        from telegram_bot.services import QueryType

        with (
            patch("telegram_bot.bot.get_client") as mock_get_client,
            patch("telegram_bot.bot.classify_query") as mock_classify,
        ):
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse
            mock_classify.return_value = QueryType.COMPLEX

            await bot_handler_full.handle_query(mock_message)

            latency_calls = [
                c
                for c in mock_langfuse.score_current_trace.call_args_list
                if c.kwargs["name"] == "latency_total_ms"
            ]
            assert len(latency_calls) == 1
            assert latency_calls[0].kwargs["value"] > 0
```

### Step 2: Run test

Run: `pytest tests/unit/test_bot_scores.py::TestHandleQueryScoresAllPaths::test_latency_recorded_positive -v`

Expected: PASS

### Step 3: Commit

```bash
git add tests/unit/test_bot_scores.py
git commit -m "$(cat <<'EOF'
test(bot): add latency_total_ms verification test

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Run Full Test Suite and Lint

**Files:** None (verification only)

### Step 1: Run all unit tests

Run: `pytest tests/unit/ -v`

Expected: All tests pass

### Step 2: Run linter

Run: `make lint`

Expected: No errors

### Step 3: Run type check

Run: `make type-check`

Expected: No new errors

### Step 4: Commit any fixes if needed

```bash
git add -A
git commit -m "$(cat <<'EOF'
chore: fix lint/type issues from scores implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Final Verification and Summary Commit

**Files:** None (verification only)

### Step 1: Run quick check

Run: `make check`

Expected: All checks pass

### Step 2: View git log

Run: `git log --oneline -10`

Expected: See all task commits

### Step 3: Create summary commit (optional squash)

If preferred, squash into single feature commit:

```bash
git add -A
git commit -m "$(cat <<'EOF'
feat(bot): implement all 10 Langfuse scores on all exit paths

Task 7 from Langfuse observability plan complete:
- Accumulator pattern with try/finally for guaranteed score writing
- All 10 scores (query_type, latency_total_ms, semantic_cache_hit,
  embeddings_cache_hit, search_cache_hit, rerank_applied,
  rerank_cache_hit, results_count, no_results, llm_used)
- Coverage: CHITCHAT, cache hit, no results, LLM success paths
- Unit tests for all 4 paths

Closes observability Task 7.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Definition of Done

- [ ] All 10 scores written on cache hit path — Task 5
- [ ] All 10 scores written on cache miss + LLM path — Task 8
- [ ] All 10 scores written on no results path — Task 9
- [ ] All 10 scores written on CHITCHAT path — Task 9
- [ ] `latency_total_ms` > 0 on all traces — Task 10
- [ ] Unit tests pass: `pytest tests/unit/test_bot_scores.py -v` — Task 11
- [ ] Lint passes: `make lint` — Task 11
- [ ] Type check passes: `make type-check` — Task 11
