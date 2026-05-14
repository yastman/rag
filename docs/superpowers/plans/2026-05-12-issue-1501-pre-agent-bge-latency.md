# Issue 1501 Pre-Agent BGE Latency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce avoidable pre-agent BGE-M3 latency by deferring sparse and ColBERT query vector generation until after semantic cache MISS, while keeping downstream retrieval and Langfuse observability contracts intact.

**Architecture:** Split the bot supervisor pre-agent flow into two phases: dense-only semantic cache lookup first, then retrieval-vector preparation only on MISS. Preserve the existing `rag_result_store` and `state_contract` handoff to `run_client_pipeline()`, and add observability safeguards so Langfuse does not capture raw embedding vectors.

**Tech Stack:** Python 3.12, aiogram bot supervisor, RedisVL semantic/embedding caches, BGE-M3 HTTP client, Qdrant hybrid RRF+ColBERT retrieval, Langfuse Python SDK v4, pytest.

---

## Spec And Evidence

- GitHub issue: `#1501` (`perf: reduce pre-agent BGE latency in client-direct RAG traces`).
- Local trace evidence checked with `langfuse --env .env api traces get ...`:
  - `09906e1d08e2dcb3add7745f325e8596`: root `4.151s`; `bge-m3-hybrid-colbert-embed=2.421s`; inner `bge-m3-encode-hybrid.processing_time=2.369s`; Qdrant `0.238s`.
  - `9bd0dd8525ba4f9e0f52270a7ad93bca`: root `2.307s`; `bge-m3-hybrid-colbert-embed=1.255s`; inner `processing_time=1.228s`; Qdrant `0.121s`.
  - Cache HIT samples `cc036d4ab2586d62e8f713f89871c16f`, `dfc6c7d5ed168842e1f23c7aa66120d0`, `0c5406af3e89e0df8216c254728a673c`: root `0.218-0.267s`, no BGE hybrid spans.
- SDK docs checked:
  - Langfuse `@observe` captures input/output by default; disable with `capture_input=False, capture_output=False` for large payloads.
  - Qdrant best practice: use `query_points`, prefetch, RRF, and ColBERT multivectors as a later reranking stage, not before knowing retrieval is needed.
  - RedisVL supports embedding and semantic cache reuse; semantic cache lookup only needs the dense query vector in this repo.
- `litellm-acompletion` trace `fff64889-26e8-4d0b-b20e-434f0012f018` is a LiteLLM proxy callback trace, not the #1501 root cause. Keep as separate follow-up unless product wants proxy traces disabled or parented.

## File Structure

- Modify: `telegram_bot/bot.py`
  - Owns supervisor pre-agent semantic cache path.
  - Add small private helpers near existing pre-agent/state-contract helpers.
  - Reorder dense lookup, semantic cache check, and MISS-only retrieval vector prep.
- Modify: `telegram_bot/integrations/embeddings.py`
  - Suppress Langfuse input/output capture on BGE wrapper spans.
  - Add a dense-query helper that can expose BGE service `processing_time` without changing legacy tuple-return methods.
- Modify: `telegram_bot/scoring.py`
  - Keep `bge_embed_latency_ms` backward-compatible.
  - Add separate score(s) for model/server processing time when available.
- Modify: `telegram_bot/pipelines/client.py`
  - Propagate any new pre-agent BGE processing metadata from `rag_result_store` into the result that is scored.
- Modify: `tests/unit/test_bot_handlers.py`
  - Add regression tests for cache HIT deferral and MISS vector handoff.
- Modify: `tests/unit/integrations/test_embeddings.py`
  - Add dense result helper tests and preserve legacy wrapper behavior.
- Modify: `tests/unit/test_observability_span_metadata.py`
  - Add AST test coverage for `telegram_bot/integrations/embeddings.py` wrapper spans.
- Modify: `tests/unit/test_bot_scores.py` or `tests/unit/test_bot_handlers.py`
  - Add score coverage for the new BGE model processing score.
- Optional docs follow-up only if behavior changes operator workflow:
  - `docs/runbooks/README.md` or cache/Langfuse runbook notes.

Do not modify Qdrant retrieval ranking, collection schema, prompt behavior, LiteLLM proxy callbacks, or production environment defaults in this plan.

## Swarm Execution Map

This plan is suitable for `tmux-swarm-orchestration` as `sequential` with one optional parallel lane. Do not launch overlapping workers against the same files.

Recommended worker waves:

1. **W-1501-bot-vector-deferral** (`pr-worker`, required OpenCode skill: `swarm-pr-finish`)
   - Reserved files:
     - `telegram_bot/bot.py`
     - `tests/unit/test_bot_handlers.py`
   - Owns Tasks 1, 2, and 5.
   - Focused checks:
     - `uv run pytest tests/unit/test_bot_handlers.py::TestPreAgentCacheCheck -q`

2. **W-1501-embedding-observe** (`pr-worker`, required OpenCode skill: `swarm-pr-finish`)
   - Can run after Wave 1 starts only if it does not edit `tests/unit/test_bot_handlers.py`.
   - Reserved files:
     - `telegram_bot/integrations/embeddings.py`
     - `tests/unit/integrations/test_embeddings.py`
     - `tests/unit/test_observability_span_metadata.py`
   - Owns Task 3.
   - Focused checks:
     - `uv run pytest tests/unit/integrations/test_embeddings.py::TestBGEM3HybridEmbeddings -q`
     - `uv run pytest tests/unit/test_observability_span_metadata.py::TestBGEIntegrationWrapperSpanMetadata -q`

3. **W-1501-bge-scoring** (`pr-worker`, required OpenCode skill: `swarm-pr-finish`)
   - Launch after Wave 1 and Wave 2 have landed if using a shared branch, because it depends on `bge_model_processing_ms` being written by bot/embedding code.
   - Reserved files:
     - `telegram_bot/scoring.py`
     - `telegram_bot/pipelines/client.py`
     - `tests/unit/test_bot_scores.py`
     - `tests/unit/test_bot_handlers.py` only if the chosen scoring test lives there; otherwise do not reserve it.
   - Owns Task 4.

4. **W-1501-runtime-trace-check** (`pr-review` or quick validation worker, read-only unless explicitly fixing test flake)
   - Launch after code tests pass.
   - Reserved files: none.
   - Owns Task 6 evidence collection.
   - Runtime workers count as 2 swarm slots because they contend for Docker/Langfuse services.

Each worker must write a DONE/FAILED/BLOCKED signal with command evidence. Runtime/code PRs still need an independent read-only PR review worker on the final head SHA before merge.

---

### Task 1: Add Bot Pre-Agent Deferral Regression Tests

**Files:**
- Modify: `tests/unit/test_bot_handlers.py`

- [ ] **Step 1: Add cache HIT dense-miss test**

Add this test inside `class TestPreAgentCacheCheck` near the existing pre-agent hybrid tests:

```python
async def test_pre_agent_cache_hit_dense_miss_does_not_compute_colbert(self, mock_config):
    """Semantic HIT must not compute sparse/ColBERT before returning cached answer."""
    bot, _ = _create_bot(mock_config)

    dense = [0.5] * 10
    sparse = {"indices": [1], "values": [0.7]}
    colbert = [[0.2] * 10]

    bot._cache.get_embedding = AsyncMock(return_value=None)
    bot._cache.get_sparse_embedding = AsyncMock(return_value=None)
    bot._cache.store_embedding = AsyncMock()
    bot._cache.store_sparse_embedding = AsyncMock()
    bot._cache.check_semantic = AsyncMock(return_value="Cached answer")
    bot._embeddings.aembed_dense_query = AsyncMock(return_value=(dense, 0.123))
    bot._embeddings.aembed_query = AsyncMock(return_value=dense)
    bot._embeddings.aembed_hybrid = AsyncMock(return_value=(dense, sparse))
    bot._embeddings.aembed_hybrid_with_colbert = AsyncMock(return_value=(dense, sparse, colbert))
    bot._embeddings.aembed_colbert_query = AsyncMock(return_value=colbert)

    mock_lf = MagicMock()
    mock_lf.get_current_trace_id = MagicMock(return_value="trace-hit-dense")
    mock_agent = AsyncMock()

    with (
        patch("telegram_bot.bot.create_bot_agent", return_value=mock_agent),
        patch("telegram_bot.bot.get_client", return_value=mock_lf),
        patch("telegram_bot.bot.propagate_attributes"),
        patch("telegram_bot.bot.create_callback_handler", return_value=None),
        patch("telegram_bot.bot.classify_query", return_value="FAQ"),
        patch("telegram_bot.bot.score"),
    ):
        message = _make_text_message("документы для ВНЖ")
        with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
            mock_cas.typing.return_value = _make_typing_cm()
            await bot.handle_query(message)

    mock_agent.ainvoke.assert_not_called()
    bot._cache.check_semantic.assert_awaited_once()
    bot._embeddings.aembed_dense_query.assert_awaited_once()
    bot._embeddings.aembed_query.assert_not_awaited()
    bot._embeddings.aembed_hybrid_with_colbert.assert_not_awaited()
    bot._embeddings.aembed_colbert_query.assert_not_awaited()
    bot._cache.store_sparse_embedding.assert_not_awaited()
```

- [ ] **Step 2: Add TTL-desync cache HIT test**

Add this test next to `test_pre_agent_ttl_desync_heals_sparse_via_hybrid_colbert`:

```python
async def test_pre_agent_ttl_desync_cache_hit_does_not_heal_sparse_before_hit(
    self, mock_config
):
    """If dense exists and semantic cache hits, missing sparse must not be healed."""
    bot, _ = _create_bot(mock_config)

    cached_dense = [0.5] * 10
    healed_sparse = {"indices": [2], "values": [0.9]}
    healed_colbert = [[0.3] * 10]

    bot._cache.get_embedding = AsyncMock(return_value=cached_dense)
    bot._cache.get_sparse_embedding = AsyncMock(return_value=None)
    bot._cache.store_sparse_embedding = AsyncMock()
    bot._cache.check_semantic = AsyncMock(return_value="Cached answer")
    bot._embeddings.aembed_hybrid_with_colbert = AsyncMock(
        return_value=(cached_dense, healed_sparse, healed_colbert)
    )
    bot._embeddings.aembed_dense_query = AsyncMock(return_value=([0.9] * 10, 0.123))
    bot._embeddings.aembed_colbert_query = AsyncMock(return_value=healed_colbert)

    mock_lf = MagicMock()
    mock_lf.get_current_trace_id = MagicMock(return_value="trace-ttl-hit")
    mock_agent = AsyncMock()

    with (
        patch("telegram_bot.bot.create_bot_agent", return_value=mock_agent),
        patch("telegram_bot.bot.get_client", return_value=mock_lf),
        patch("telegram_bot.bot.propagate_attributes"),
        patch("telegram_bot.bot.create_callback_handler", return_value=None),
        patch("telegram_bot.bot.classify_query", return_value="FAQ"),
        patch("telegram_bot.bot.score"),
    ):
        message = _make_text_message("квартиры у моря")
        with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
            mock_cas.typing.return_value = _make_typing_cm()
            await bot.handle_query(message)

    mock_agent.ainvoke.assert_not_called()
    bot._cache.check_semantic.assert_awaited_once()
    bot._embeddings.aembed_hybrid_with_colbert.assert_not_awaited()
    bot._embeddings.aembed_dense_query.assert_not_awaited()
    bot._embeddings.aembed_colbert_query.assert_not_awaited()
    bot._cache.store_sparse_embedding.assert_not_awaited()
```

- [ ] **Step 3: Add MISS vector-prep test**

Update or add a MISS test that proves sparse/ColBERT are prepared after cache MISS and reach `rag_result_store`:

```python
async def test_pre_agent_cache_miss_prepares_sparse_and_colbert_after_lookup(
    self, mock_config
):
    bot, _ = _create_bot(mock_config)

    dense = [0.5] * 10
    sparse = {"indices": [1], "values": [0.7]}
    colbert = [[0.2] * 10]

    bot._cache.get_embedding = AsyncMock(return_value=None)
    bot._cache.get_sparse_embedding = AsyncMock(return_value=None)
    bot._cache.store_embedding = AsyncMock()
    bot._cache.store_sparse_embedding = AsyncMock()
    bot._cache.check_semantic = AsyncMock(return_value=None)
    bot._embeddings.aembed_dense_query = AsyncMock(return_value=(dense, 0.123))
    bot._embeddings.aembed_query = AsyncMock(return_value=dense)
    bot._embeddings.aembed_hybrid_with_colbert = AsyncMock(return_value=(dense, sparse, colbert))
    bot._embeddings.aembed_colbert_query = AsyncMock(return_value=[[0.9] * 10])

    stashed_store: dict = {}

    async def _capture_invoke(*args, **kwargs):
        stashed_store.update(kwargs["config"]["configurable"]["rag_result_store"])
        return _mock_agent_result()

    mock_agent = AsyncMock()
    mock_agent.ainvoke = _capture_invoke

    with (
        patch("telegram_bot.bot.create_bot_agent", return_value=mock_agent),
        patch("telegram_bot.bot.get_client", return_value=MagicMock()),
        patch("telegram_bot.bot.propagate_attributes"),
        patch("telegram_bot.bot.create_callback_handler", return_value=None),
        patch("telegram_bot.bot.classify_query", return_value="FAQ"),
    ):
        message = _make_text_message("документы для ВНЖ")
        with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
            mock_cas.typing.return_value = _make_typing_cm()
            await bot.handle_query(message)

    bot._cache.check_semantic.assert_awaited_once()
    bot._embeddings.aembed_dense_query.assert_awaited_once()
    bot._embeddings.aembed_query.assert_not_awaited()
    bot._embeddings.aembed_hybrid_with_colbert.assert_awaited_once()
    bot._embeddings.aembed_colbert_query.assert_not_awaited()
    assert stashed_store["cache_key_embedding"] == dense
    assert stashed_store["cache_key_sparse"] == sparse
    assert stashed_store["cache_key_colbert"] == colbert
    assert stashed_store["state_contract"]["dense_vector"] == dense
    assert stashed_store["state_contract"]["sparse_vector"] == sparse
    assert stashed_store["state_contract"]["colbert_query"] == colbert
```

- [ ] **Step 4: Run tests and confirm RED**

Run:

```bash
uv run pytest \
  tests/unit/test_bot_handlers.py::TestPreAgentCacheCheck::test_pre_agent_cache_hit_dense_miss_does_not_compute_colbert \
  tests/unit/test_bot_handlers.py::TestPreAgentCacheCheck::test_pre_agent_ttl_desync_cache_hit_does_not_heal_sparse_before_hit \
  tests/unit/test_bot_handlers.py::TestPreAgentCacheCheck::test_pre_agent_cache_miss_prepares_sparse_and_colbert_after_lookup \
  -q
```

Expected before implementation: at least the two HIT tests fail because current code calls `aembed_hybrid_with_colbert()` before semantic lookup.

---

### Task 2: Split Bot Pre-Agent Dense Lookup From MISS Vector Preparation

**Files:**
- Modify: `telegram_bot/bot.py:2878-3115`
- Test: `tests/unit/test_bot_handlers.py`

- [ ] **Step 1: Add private helper for coroutine capability checks**

Add near the existing private helper section in `telegram_bot/bot.py`:

```python
def _has_async_method(obj: Any, name: str) -> bool:
    method = getattr(obj, name, None)
    return callable(method) and asyncio.iscoroutinefunction(method)
```

If a same-purpose helper already exists in this file, reuse it instead of adding a duplicate.

Test hardening note: after extracting helpers, do not rely on implicit `MagicMock` child attributes for embedding capabilities. Tests should explicitly set unavailable async methods to `None` or explicitly stub `aembed_dense_query` / `aembed_query` / `aembed_hybrid_with_colbert` so capability checks exercise the intended path.

- [ ] **Step 2: Add dense-only pre-agent helper**

Add a helper that only returns the dense vector needed for semantic cache lookup:

```python
async def _get_or_compute_pre_agent_dense(
    *,
    cache: Any,
    embeddings: Any,
    query: str,
    result_store: dict[str, Any],
) -> list[float] | None:
    embed_start = time.perf_counter()
    embedding = await cache.get_embedding(query)
    if embedding is None:
        if _has_async_method(embeddings, "aembed_dense_query"):
            dense_result = await embeddings.aembed_dense_query(query)
            if isinstance(dense_result, tuple):
                embedding = dense_result[0]
                processing_s = dense_result[1] if len(dense_result) > 1 else None
            else:
                embedding = dense_result
                processing_s = None
        else:
            embedding = await embeddings.aembed_query(query)
            processing_s = None
        await cache.store_embedding(query, embedding)
        if isinstance(processing_s, int | float):
            result_store["bge_model_processing_ms"] = float(processing_s) * 1000

    result_store["pre_agent_embed_ms"] = (time.perf_counter() - embed_start) * 1000
    return embedding
```

Notes:
- The helper intentionally does not call `get_sparse_embedding()`.
- The helper intentionally does not call `aembed_hybrid()` or `aembed_hybrid_with_colbert()` directly.
- If `aembed_query()` currently computes sparse internally for a specific embedding implementation, Task 3 adds `aembed_dense_query()` so the bot can avoid that path.

- [ ] **Step 3: Add MISS-only retrieval vector helper**

Add a helper that runs only after semantic cache MISS:

```python
async def _prepare_pre_agent_retrieval_vectors(
    *,
    cache: Any,
    embeddings: Any,
    query: str,
    dense: list[float] | None,
    result_store: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[list[float]] | None]:
    vector_start = time.perf_counter()
    sparse = await cache.get_sparse_embedding(query)
    colbert: list[list[float]] | None = None

    if sparse is None:
        if _has_async_method(embeddings, "aembed_hybrid_with_colbert"):
            try:
                _dense_from_hybrid, sparse_from_hybrid, colbert_from_hybrid = (
                    await embeddings.aembed_hybrid_with_colbert(query)
                )
                if sparse_from_hybrid is not None:
                    sparse = sparse_from_hybrid
                    await cache.store_sparse_embedding(query, sparse_from_hybrid)
                colbert = colbert_from_hybrid
            except Exception:
                logger.debug("Pre-agent hybrid ColBERT encode failed, skipping", exc_info=True)
        elif _has_async_method(embeddings, "aembed_hybrid"):
            try:
                _dense_from_hybrid, sparse_from_hybrid = await embeddings.aembed_hybrid(query)
                if sparse_from_hybrid is not None:
                    sparse = sparse_from_hybrid
                    await cache.store_sparse_embedding(query, sparse_from_hybrid)
            except Exception:
                logger.debug("Pre-agent hybrid encode failed, skipping", exc_info=True)

    if colbert is None and _has_async_method(embeddings, "aembed_colbert_query"):
        try:
            colbert = await embeddings.aembed_colbert_query(query)
        except Exception:
            logger.debug("Pre-agent ColBERT encode failed, skipping", exc_info=True)

    result_store["cache_key_embedding"] = dense
    result_store["cache_key_sparse"] = sparse
    result_store["cache_key_colbert"] = colbert
    result_store["pre_agent_retrieval_vector_ms"] = (
        time.perf_counter() - vector_start
    ) * 1000
    return sparse, colbert
```

Important:
- If dense and sparse are both cached but ColBERT is missing, prefer `aembed_colbert_query()` if available.
- If sparse is missing and `aembed_hybrid_with_colbert()` is available, use it once to fill sparse and ColBERT.
- If `aembed_hybrid_with_colbert()` is unavailable and sparse is missing, keep the existing `aembed_hybrid()` fallback to fill sparse, then still call `aembed_colbert_query()` when available.
- Keep exceptions non-fatal, matching current behavior.

- [ ] **Step 4: Replace the inline pre-agent embedding block**

In `handle_query()`, replace the block from `embed_start = time.perf_counter()` through the sparse healing logic with:

```python
embedding = await _get_or_compute_pre_agent_dense(
    cache=self._cache,
    embeddings=self._embeddings,
    query=user_text,
    result_store=rag_result_store,
)
```

Keep the existing topic hint, grounding mode, filter extraction, contextual query, and `check_semantic()` logic unchanged.

- [ ] **Step 5: On cache HIT, do not stash sparse/ColBERT**

In the cache HIT branch, keep:

```python
rag_result_store["cache_hit"] = True
rag_result_store["query_type"] = query_type
rag_result_store["cache_key_embedding"] = embedding
```

Remove or avoid setting `cache_key_sparse` on HIT. Do not call the MISS vector helper on HIT.

- [ ] **Step 6: On MISS, call retrieval vector helper before building state contract**

Replace the existing MISS vector-prep block with:

```python
logger.debug("Pre-agent cache MISS (type=%s): %.60s", query_type, user_text)
rag_result_store["query_type"] = query_type
sparse, colbert = await _prepare_pre_agent_retrieval_vectors(
    cache=self._cache,
    embeddings=self._embeddings,
    query=user_text,
    dense=embedding,
    result_store=rag_result_store,
)
topic_hint = get_query_topic_hint(user_text)
rag_result_store["state_contract"] = _build_pre_agent_state_contract(
    rag_result_store=rag_result_store,
    query_type=query_type,
    topic_hint=topic_hint.value if topic_hint is not None else None,
    dense_vector=embedding,
    sparse_vector=sparse if isinstance(sparse, dict) else None,
    colbert_query=colbert,
    grounding_mode=rag_result_store.get("grounding_mode", "normal"),
    filters=extracted_filters or None,
)
```

Do not build `state_contract` before semantic cache MISS is known. `rag_pipeline()` treats `cache_checked=True`, `cache_hit=False`, and `embedding_bundle_ready=True` as authoritative and skips another semantic cache lookup.

- [ ] **Step 7: Run bot pre-agent focused tests**

Run:

```bash
uv run pytest tests/unit/test_bot_handlers.py::TestPreAgentCacheCheck -q
```

Expected: all `TestPreAgentCacheCheck` tests pass after updating old expectations that intentionally asserted ColBERT on cache HIT.

- [ ] **Step 8: Run client pipeline contract tests**

Run:

```bash
uv run pytest \
  tests/unit/pipelines/test_client_pipeline.py::TestClientPipeline::test_pipeline_passes_semantic_cache_already_checked_to_rag_pipeline \
  tests/unit/pipelines/test_client_pipeline.py::TestClientPipeline::test_passes_sparse_and_colbert_from_rag_result_store \
  -q
```

If class names differ, locate exact node ids with:

```bash
uv run pytest tests/unit/pipelines/test_client_pipeline.py --collect-only -q | rg "semantic_cache_already_checked|sparse_and_colbert"
```

---

### Task 3: Add Dense Query Helper And Suppress Wrapper Span Payloads

**Files:**
- Modify: `telegram_bot/integrations/embeddings.py`
- Modify: `tests/unit/integrations/test_embeddings.py`
- Modify: `tests/unit/test_observability_span_metadata.py`

- [ ] **Step 1: Add failing AST test for wrapper span capture**

In `tests/unit/test_observability_span_metadata.py`, add a new class:

```python
class TestBGEIntegrationWrapperSpanMetadata:
    """BGE integration wrapper spans must not capture raw vector payloads."""

    @pytest.fixture(scope="class")
    def wrapper_spans(self):
        path = REPO_ROOT / "telegram_bot" / "integrations" / "embeddings.py"
        return _collect_observe_decorators(path)

    @pytest.mark.parametrize(
        "span_name",
        [
            "bge-m3-dense-embed",
            "bge-m3-dense-query-embed",
            "bge-m3-sparse-embed",
            "bge-m3-sparse-embed-batch",
            "bge-m3-hybrid-embed",
            "bge-m3-hybrid-colbert-embed",
            "bge-m3-colbert-query-embed",
            "bge-m3-hybrid-embed-batch",
        ],
    )
    def test_wrapper_span_capture_disabled(self, wrapper_spans, span_name):
        assert span_name in wrapper_spans, f"Span {span_name!r} not found"
        info = wrapper_spans[span_name]
        assert info["capture_input"] is False
        assert info["capture_output"] is False
```

- [ ] **Step 2: Run AST test and confirm RED**

Run:

```bash
uv run pytest tests/unit/test_observability_span_metadata.py::TestBGEIntegrationWrapperSpanMetadata -q
```

Expected before implementation: fails because wrapper decorators omit capture flags.

- [ ] **Step 3: Add dense helper test**

In `tests/unit/integrations/test_embeddings.py`, add:

```python
async def test_aembed_dense_query_uses_dense_endpoint_and_returns_processing_time(self):
    from telegram_bot.services.bge_m3_client import BGEM3Client, DenseResult

    mock_client = AsyncMock(spec=BGEM3Client)
    mock_client.encode_dense = AsyncMock(
        return_value=DenseResult(vectors=[[0.1] * 1024], processing_time=0.123)
    )

    emb = BGEM3HybridEmbeddings(client=mock_client)
    dense, processing_time = await emb.aembed_dense_query("test query")

    assert dense == [0.1] * 1024
    assert processing_time == 0.123
    mock_client.encode_dense.assert_awaited_once_with(["test query"])
```

- [ ] **Step 4: Run dense helper test and confirm RED**

Run:

```bash
uv run pytest tests/unit/integrations/test_embeddings.py::TestBGEM3HybridEmbeddings::test_aembed_dense_query_uses_dense_endpoint_and_returns_processing_time -q
```

Expected before implementation: fails because `aembed_dense_query()` does not exist.

- [ ] **Step 5: Update wrapper decorators**

In `telegram_bot/integrations/embeddings.py`, update every BGE wrapper `@observe` decorator to include capture suppression:

```python
@observe(name="bge-m3-hybrid-colbert-embed", capture_input=False, capture_output=False)
```

Apply this to:
- `bge-m3-dense-embed`
- `bge-m3-dense-query-embed`
- `bge-m3-sparse-embed`
- `bge-m3-sparse-embed-batch`
- `bge-m3-hybrid-embed`
- `bge-m3-hybrid-colbert-embed`
- `bge-m3-colbert-query-embed`
- `bge-m3-hybrid-embed-batch`

- [ ] **Step 6: Add `aembed_dense_query()` to `BGEM3HybridEmbeddings`**

Add this method before `aembed_hybrid()`:

```python
@observe(name="bge-m3-dense-query-embed", capture_input=False, capture_output=False)
async def aembed_dense_query(self, text: str) -> tuple[list[float], float | None]:
    """Embed text via /encode/dense for semantic cache lookup only."""
    result = await self._client.encode_dense([text])
    return result.vectors[0], result.processing_time
```

Do not change legacy return types for `aembed_hybrid()`, `aembed_hybrid_with_colbert()`, or `aembed_colbert_query()`.

- [ ] **Step 7: Run embedding and span tests**

Run:

```bash
uv run pytest \
  tests/unit/integrations/test_embeddings.py::TestBGEM3HybridEmbeddings::test_aembed_dense_query_uses_dense_endpoint_and_returns_processing_time \
  tests/unit/integrations/test_embeddings.py::TestBGEM3HybridEmbeddings::test_aembed_hybrid_with_colbert \
  tests/unit/integrations/test_embeddings.py::TestBGEM3HybridEmbeddings::test_aembed_hybrid_with_colbert_fallback_to_encode_colbert \
  tests/unit/test_observability_span_metadata.py::TestBGEIntegrationWrapperSpanMetadata \
  -q
```

Expected: PASS.

---

### Task 4: Add Separate BGE Model Processing Score

**Files:**
- Modify: `telegram_bot/scoring.py`
- Modify: `telegram_bot/pipelines/client.py`
- Modify: `tests/unit/test_bot_handlers.py` or `tests/unit/test_bot_scores.py`

- [ ] **Step 1: Add failing scoring test**

Use the existing score test style. In `tests/unit/test_bot_handlers.py::TestWriteLangfuseScores` or `tests/unit/test_bot_scores.py::TestScoreWriting`, add:

```python
def test_writes_bge_model_processing_latency_separately(self):
    from telegram_bot.scoring import write_langfuse_scores

    mock_lf = MagicMock()
    result = {
        "query_type": "FAQ",
        "cache_hit": False,
        "pre_agent_embed_ms": 321.5,
        "bge_model_processing_ms": 123.4,
    }

    write_langfuse_scores(mock_lf, result, trace_id=self._TID)

    calls = {c.kwargs["name"]: c.kwargs["value"] for c in mock_lf.create_score.call_args_list}
    assert calls["bge_embed_latency_ms"] == 321.5
    assert calls["bge_model_processing_ms"] == 123.4
```

- [ ] **Step 2: Run scoring test and confirm RED**

Run:

```bash
uv run pytest tests/unit/test_bot_handlers.py::TestWriteLangfuseScores::test_writes_bge_model_processing_latency_separately -q
```

If the test lives in `test_bot_scores.py`, use that node id instead. Expected before implementation: fails because `bge_model_processing_ms` is not scored.

- [ ] **Step 3: Update `write_langfuse_scores()`**

In `telegram_bot/scoring.py`, after the existing `bge_embed_latency_ms` score:

```python
bge_processing_ms = result.get("bge_model_processing_ms")
if bge_processing_ms is not None:
    score(
        lf,
        trace_id,
        name="bge_model_processing_ms",
        value=float(bge_processing_ms),
    )
```

Do not rename `bge_embed_latency_ms` in this task because dashboards may depend on it.

- [ ] **Step 4: Propagate metadata through client pipeline**

In `telegram_bot/pipelines/client.py`, near the existing pre-agent timing propagation:

```python
bge_model_processing_ms = _store.get("bge_model_processing_ms")
if isinstance(bge_model_processing_ms, Real):
    result["bge_model_processing_ms"] = float(bge_model_processing_ms)
```

Also include it in final trace metadata if a nearby metadata payload already lists pre-agent timing fields.

- [ ] **Step 5: Run scoring and client pipeline tests**

Run:

```bash
uv run pytest \
  tests/unit/test_bot_handlers.py::TestWriteLangfuseScores::test_prefers_pre_agent_embed_latency_over_cache_check \
  tests/unit/test_bot_handlers.py::TestWriteLangfuseScores::test_writes_bge_model_processing_latency_separately \
  tests/unit/pipelines/test_client_pipeline.py -k "pre_agent or bge_model_processing" \
  -q
```

Expected: PASS.

---

### Task 5: Update Existing Pre-Agent Tests That Encode Old Behavior

**Files:**
- Modify: `tests/unit/test_bot_handlers.py`

- [ ] **Step 1: Update cache HIT tests with old ColBERT expectations**

Revise these existing tests because they currently encode the behavior #1501 is fixing:

- `test_pre_agent_uses_hybrid_when_available`
- `test_pre_agent_uses_hybrid_with_colbert_and_stashes_all_three`
- `test_pre_agent_hybrid_stash_on_cache_hit`
- `test_pre_agent_cache_hit_stashes_colbert_on_hybrid_colbert_path`

Expected new assertions:

```python
mock_agent.ainvoke.assert_not_called()
bot._cache.check_semantic.assert_awaited_once()
bot._embeddings.aembed_hybrid_with_colbert.assert_not_awaited()
bot._embeddings.aembed_colbert_query.assert_not_awaited()
bot._cache.store_sparse_embedding.assert_not_awaited()
```

If a test is now a MISS-only behavior, rename and update it instead of weakening the assertion:

- `test_pre_agent_miss_uses_hybrid_when_sparse_missing`
- `test_pre_agent_miss_uses_hybrid_with_colbert_and_stashes_all_three`

If a test is now a HIT behavior, rename it to:

- `test_pre_agent_cache_hit_defers_hybrid_sparse`
- `test_pre_agent_cache_hit_defers_hybrid_colbert`

New expected split:
- HIT tests assert dense-only lookup and no sparse/ColBERT preparation.
- MISS tests assert dense lookup first, semantic lookup second, then sparse/ColBERT preparation and `state_contract` population.

- [ ] **Step 2: Keep MISS tests strict**

Keep or update:

- `test_pre_agent_miss_prefers_hybrid_colbert`
- `test_pre_agent_miss_falls_back_to_colbert_query_when_hybrid_unavailable`
- `test_pre_agent_miss_colbert_query_exception_graceful`
- `test_pre_agent_miss_colbert_unavailable_stays_none`

The new rule:
- MISS can call `aembed_hybrid_with_colbert()` when sparse is missing.
- MISS can call `aembed_colbert_query()` when sparse is already present and ColBERT is missing.
- HIT must not call either.

Intentional exclusions from the rename/update block:
- Keep TTL-desync MISS tests as MISS tests. They should still prove sparse healing happens after semantic MISS.
- Keep ColBERT unavailable/exception MISS tests as MISS tests. They should still prove graceful degradation and state contract shape.

- [ ] **Step 3: Run full bot handler unit file**

Run:

```bash
uv run pytest tests/unit/test_bot_handlers.py -q
```

Expected: PASS. Warnings about deprecated trace-level IO are acceptable if pre-existing.

---

### Task 6: Runtime Trace Validation

**Files:**
- No code changes.
- Use local runtime and Langfuse CLI.

- [ ] **Step 1: Start required local services**

Run:

```bash
make local-up
make docker-ml-up
make test-bot-health
```

Expected:
- Redis, Qdrant, BGE-M3, LiteLLM, and Langfuse are reachable.
- If Redis auth fails after `.env` changes, run `make local-redis-recreate` and retry.

- [ ] **Step 2: Start bot in a separate terminal/session**

Run:

```bash
make bot
```

Expected: bot starts and preflight passes. Do not use production credentials or real CRM write paths.

- [ ] **Step 3: Produce one semantic MISS trace**

Send a cacheable RAG query that is unlikely to be cached, for example a unique phrasing around a known doc topic.

Then inspect latest trace:

```bash
langfuse --env .env api traces list \
  --name telegram-message \
  --limit 3 \
  --order-by timestamp.desc \
  --fields core,metrics,scores \
  --json | jq '.body.data[] | {id,timestamp,latency,scores}'
```

Fetch the selected trace:

```bash
langfuse --env .env api traces get <TRACE_ID> --json | jq '.body | {
  id,
  latency,
  top_observations:(.observations|sort_by(.latency // 0)|reverse|map({
    name,type,latency,processing_time:(.output.processing_time? // null)
  })[:12]),
  scores:(.scores|map(select(.name|test("bge_embed_latency_ms|bge_model_processing_ms|semantic_cache_hit|pre_agent_cache_hit"))|{name,value,stringValue,dataType}))
}'
```

Expected MISS:
- `semantic_cache_hit=0`.
- `bge-m3-hybrid-colbert-embed` may appear after semantic MISS.
- `qdrant-hybrid-search-rrf-colbert` still appears.
- `bge_model_processing_ms` score appears if BGE returned `processing_time`.

- [ ] **Step 4: Produce one semantic HIT trace**

Repeat the same user-facing query after the answer has been cached.

Expected HIT:
- `pre_agent_cache_hit=True`.
- `semantic_cache_hit=1`.
- No `bge-m3-hybrid-colbert-embed` before returning cached answer.
- No `qdrant-hybrid-search-rrf-colbert`.
- Root trace around the existing fast-hit range, roughly `0.2-0.3s` in local samples.

- [ ] **Step 5: Check `litellm-acompletion` does not regress app traces**

Run:

```bash
langfuse --env .env api traces list \
  --name litellm-acompletion \
  --limit 3 \
  --order-by timestamp.desc \
  --fields core,metrics \
  --json | jq '.body.data[] | {id,name,timestamp,latency,totalCost}'
```

Expected:
- These traces may still exist because `docker/litellm/config.yaml` has `success_callback: ["langfuse"]`.
- They are not counted as application trace coverage.
- Do not change LiteLLM callbacks in this task.

---

### Task 7: Final Verification

**Files:**
- No code changes unless previous steps reveal failures.

- [ ] **Step 1: Run focused checks**

Run:

```bash
uv run pytest tests/unit/test_bot_handlers.py::TestPreAgentCacheCheck -q
uv run pytest tests/unit/integrations/test_embeddings.py::TestBGEM3HybridEmbeddings -q
uv run pytest tests/unit/test_observability_span_metadata.py::TestBGEIntegrationWrapperSpanMetadata -q
uv run pytest tests/unit/pipelines/test_client_pipeline.py -k "pre_agent or sparse_and_colbert or semantic_cache_already_checked" -q
```

Expected: PASS.

- [ ] **Step 2: Run required bot-area checks from `telegram_bot/AGENTS.override.md`**

Run:

```bash
make check
PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit
```

Expected: PASS.

- [ ] **Step 3: Run local runtime health**

Run:

```bash
make test-bot-health
```

Expected: PASS, or document any skipped service with exact reason.

- [ ] **Step 4: Document validation evidence in PR/issue comment**

Include:
- Focused pytest commands and PASS output summary.
- Whether full `make check` and `make test-unit` passed.
- HIT and MISS Langfuse trace IDs.
- Confirmation that HIT skips `bge-m3-hybrid-colbert-embed`.
- Confirmation that MISS still reaches `qdrant-hybrid-search-rrf-colbert`.

---

## Out Of Scope / Follow-Ups

- Do not remove LiteLLM proxy Langfuse callbacks in this issue. `litellm-acompletion` traces are useful for proxy-level cost/debug, but they are currently separate root traces. If this becomes noisy, open a follow-up to either propagate trace context into LiteLLM proxy metadata or disable proxy callbacks in local-only config.
- Do not change Qdrant collection schema, vector names, RRF constants, ColBERT reranking behavior, or cache thresholds.
- Do not rename `bge_embed_latency_ms` until dashboards and trace contracts are migrated.

## Commit Plan

Commit after each task or pair of tightly coupled tasks:

```bash
git add tests/unit/test_bot_handlers.py
git commit -m "test: cover pre-agent cache vector deferral"

git add telegram_bot/bot.py tests/unit/test_bot_handlers.py
git commit -m "fix: defer pre-agent retrieval vectors until cache miss"

git add telegram_bot/integrations/embeddings.py tests/unit/integrations/test_embeddings.py tests/unit/test_observability_span_metadata.py
git commit -m "fix: suppress BGE wrapper trace payloads"

git add telegram_bot/scoring.py telegram_bot/pipelines/client.py tests/unit/test_bot_handlers.py tests/unit/test_bot_scores.py
git commit -m "feat: score BGE model processing latency"
```
