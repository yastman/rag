# Task 7: Langfuse Scores on All Exit Paths

> Design plan for completing Task 7 from `docs/plans/2026-01-29-langfuse-full-observability-design.md`

## Problem Statement

Current `handle_query` writes Langfuse scores only on semantic cache hit path (1 of 4 exit paths). E2E validator expects 10 scores on every trace.

**Current state:**
- Scores written: 3 (`semantic_cache_hit`, `query_type`, `results_count`)
- Path coverage: 1/4 (cache hit only)

**Required state:**
- Scores written: 10 (per `scripts/e2e/langfuse_trace_validator.py:20-31`)
- Path coverage: 4/4 (all exit paths)

## Exit Paths Analysis

| # | Path | Line | Variables Available | Current Scores |
|---|------|------|---------------------|----------------|
| 1 | CHITCHAT | 207 | `query_type` | ❌ None |
| 2 | Cache hit | 261 | `query_type`, `cached_answer` | ✓ 3 scores |
| 3 | No results | 361 | `query_type`, `results=[]` | ❌ None |
| 4 | LLM success | 411 | `query_type`, `results`, `answer` | ❌ None |

## Required Scores

From `scripts/e2e/langfuse_trace_validator.py`:

```python
SCORE_NAMES = {
    "query_type",           # 0=CHITCHAT, 1=SIMPLE, 2=COMPLEX
    "latency_total_ms",     # End-to-end latency
    "semantic_cache_hit",   # 1.0 if cache hit, 0.0 otherwise
    "embeddings_cache_hit", # 1.0 if embedding from cache
    "search_cache_hit",     # 1.0 if search results from cache
    "rerank_applied",       # 1.0 if rerank was performed
    "rerank_cache_hit",     # 1.0 if rerank results from cache
    "results_count",        # Number of results returned
    "no_results",           # 1.0 if no results found
    "llm_used",             # 1.0 if LLM generated answer
}
```

## Design: Accumulator Pattern with try/finally

### Rationale

1. **Single source of truth** — all scores defined once at function start
2. **Guaranteed execution** — `finally` block runs on all exit paths
3. **No code duplication** — scores written in one place
4. **SDK-friendly** — Langfuse SDK v3 batches scores automatically (batch_size=15, interval=1s)

### Implementation

```python
@observe(name="telegram-message")
async def handle_query(self, message: Message):
    import time
    start_time = time.time()
    langfuse = get_client()

    # Initialize scores accumulator with defaults (miss/not applied)
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
    query_type = QueryType.SIMPLE  # Default, will be set by classify_query

    try:
        # ... existing pipeline logic ...

        # Update scores as pipeline executes:
        query_type = classify_query(query)

        # Path 1: CHITCHAT - early return removed, use flag instead
        if query_type == QueryType.CHITCHAT:
            chitchat_response = get_chitchat_response(query)
            if chitchat_response:
                await message.answer(chitchat_response)
                return  # finally block will write scores

        # Embeddings cache check
        query_vector = await self.cache_service.get_cached_embedding(query)
        if query_vector is not None:
            scores["embeddings_cache_hit"] = 1.0
        else:
            query_vector = await self.voyage_service.embed_query(query)
            await self.cache_service.store_embedding(query, query_vector)

        # Semantic cache check
        cached_answer = await self.cache_service.check_semantic_cache(query)
        if cached_answer:
            scores["semantic_cache_hit"] = 1.0
            await message.answer(cached_answer, parse_mode="Markdown")
            return  # finally block will write scores

        # Search cache check
        results = await self.cache_service.get_cached_search(query_vector, filters)
        if results is not None:
            scores["search_cache_hit"] = 1.0
        else:
            # ... hybrid search ...
            results = await self.qdrant_service.hybrid_search_rrf(...)

            # Rerank (if applied)
            if results and needs_rerank(query_type, len(results)):
                scores["rerank_applied"] = 1.0
                cached_rerank = await self.cache_service.get_cached_rerank(...)
                if cached_rerank:
                    scores["rerank_cache_hit"] = 1.0
                else:
                    # ... rerank via Voyage ...

        scores["results_count"] = float(len(results)) if results else 0.0

        # Path 3: No results
        if not results:
            scores["no_results"] = 1.0
            await message.answer("😔 Ничего не нашел...")
            return  # finally block will write scores

        # Path 4: LLM generation
        scores["llm_used"] = 1.0
        # ... streaming LLM ...

    finally:
        # Write all scores - guaranteed on ALL paths
        query_type_map = {"chitchat": 0, "simple": 1, "complex": 2}
        langfuse.score_current_trace(
            name="query_type",
            value=float(query_type_map.get(query_type.value, 1))
        )
        langfuse.score_current_trace(
            name="latency_total_ms",
            value=(time.time() - start_time) * 1000
        )
        for name, value in scores.items():
            langfuse.score_current_trace(name=name, value=value)

        self.cache_service.log_metrics()
```

## Changes Required

### File: `telegram_bot/bot.py`

| Location | Change |
|----------|--------|
| Line 1-10 | Add `import time` |
| Line 170-175 | Initialize `start_time` and `scores` dict |
| Line 200-207 | Keep CHITCHAT logic, remove scores from here |
| Line 230-236 | Update `scores["embeddings_cache_hit"]` |
| Line 240-261 | Update `scores["semantic_cache_hit"]`, remove inline scores |
| Line 274-295 | Update `scores["search_cache_hit"]` |
| Line 312-351 | Update `scores["rerank_applied"]`, `scores["rerank_cache_hit"]` |
| Line 355-361 | Update `scores["no_results"]`, `scores["results_count"]` |
| Line 375-401 | Update `scores["llm_used"]` |
| Line 408-411 | Replace with `finally` block |

### File: `tests/unit/test_bot_scores.py`

Add tests for:
1. Cache miss path scores
2. No results path scores
3. CHITCHAT path scores
4. `latency_total_ms` is recorded
5. All 10 scores present on each path

## Test Plan

### Unit Tests (new)

```python
class TestHandleQueryScoresAllPaths:
    """Tests for scores on all exit paths."""

    @pytest.mark.asyncio
    async def test_scores_cache_miss_llm_path(self, bot_handler, mock_message):
        """Should write all 10 scores on LLM generation path."""
        bot_handler.cache_service.check_semantic_cache = AsyncMock(return_value=None)
        bot_handler.cache_service.get_cached_search = AsyncMock(return_value=None)
        # ... mock full pipeline ...

        with patch("telegram_bot.bot.get_client") as mock_get_client:
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse

            await bot_handler.handle_query(mock_message)

            score_names = {c.kwargs["name"] for c in mock_langfuse.score_current_trace.call_args_list}
            assert score_names == EXPECTED_SCORE_NAMES  # All 10

            # Verify specific values
            llm_score = next(c for c in mock_langfuse.score_current_trace.call_args_list
                           if c.kwargs["name"] == "llm_used")
            assert llm_score.kwargs["value"] == 1.0

    @pytest.mark.asyncio
    async def test_scores_no_results_path(self, bot_handler, mock_message):
        """Should write no_results=1.0 when search returns empty."""
        # ... mock empty results ...

    @pytest.mark.asyncio
    async def test_scores_chitchat_path(self, bot_handler, mock_message):
        """Should write query_type=0 for CHITCHAT."""
        mock_message.text = "Привет!"
        # ...

    @pytest.mark.asyncio
    async def test_latency_recorded(self, bot_handler, mock_message):
        """Should record latency_total_ms > 0."""
        # ...
```

### E2E Validation

```bash
# Should pass with all scores present
E2E_VALIDATE_LANGFUSE=1 make e2e-test
```

## Implementation Steps

1. **Add time import and scores accumulator** — Initialize at function start
2. **Update embeddings cache block** — Set `embeddings_cache_hit`
3. **Update semantic cache block** — Set `semantic_cache_hit`, remove inline scores
4. **Update search cache block** — Set `search_cache_hit`
5. **Update rerank block** — Set `rerank_applied`, `rerank_cache_hit`
6. **Update no results block** — Set `no_results`, `results_count`
7. **Update LLM block** — Set `llm_used`
8. **Add finally block** — Write all scores
9. **Add unit tests** — Cover all 4 paths
10. **Run E2E validation** — Verify with Langfuse

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| `finally` runs on exceptions too | Scores will be written with partial data — acceptable, better than no data |
| `query_type` not set on early exception | Initialize to `QueryType.SIMPLE` as default |
| Performance impact of 10+ score calls | Langfuse SDK batches automatically — no overhead |

## Definition of Done

- [ ] All 10 scores written on cache hit path
- [ ] All 10 scores written on cache miss + LLM path
- [ ] All 10 scores written on no results path
- [ ] All 10 scores written on CHITCHAT path
- [ ] `latency_total_ms` > 0 on all traces
- [ ] Unit tests pass: `pytest tests/unit/test_bot_scores.py -v`
- [ ] E2E validation passes: `E2E_VALIDATE_LANGFUSE=1 make e2e-test`
- [ ] Langfuse UI shows all scores on sample traces
