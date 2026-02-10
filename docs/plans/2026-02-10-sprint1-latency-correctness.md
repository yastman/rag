# Sprint 1: Latency & Correctness — Implementation Plan

**Goal:** Fix P0 latency bottlenecks and broken correctness: BGE-M3 hybrid embedding (2x speedup), broken latency score, wrong grade threshold for RRF scores, and hardcoded Langfuse scores.

**Architecture:** 4 focused tasks touching embeddings layer, score writing, grade threshold, and Langfuse score implementation. Each task is TDD: write failing test -> implement -> verify.
Tasks are **not fully independent** (Task 1 and Task 4 overlap in `cache/retrieve/bot`), so preferred execution order is: **Task 2 -> Task 3 -> Task 1 -> Task 4 -> Task 5**.

**Tech Stack:** pytest, httpx (mocked), LangGraph StateGraph, Langfuse SDK v3, BGE-M3 `/encode/hybrid` endpoint.

**SDK-first requirement (Context7-aligned):**
- Keep retrieval path on **Qdrant Python SDK Query API** (`prefetch + RRF`) and avoid raw HTTP search calls.
- Keep observability verification on **Langfuse SDK v3** (`api.trace.list/get`) and avoid dashboard-only validation.
- ONNX migration spike (later phase) must use official SDK path (`optimum + onnxruntime`) with parity tests.

**Issues:** #103, #105, #106, #107, #109, #110

---

## Task 1: BGEM3HybridEmbeddings + Connection Pooling

**Цель:** Один вызов `/encode/hybrid` вместо двух отдельных (dense+sparse). Shared httpx client.

**Files:**
- Edit: `telegram_bot/integrations/embeddings.py`
- Edit: `telegram_bot/graph/nodes/retrieve.py`
- Edit: `telegram_bot/graph/nodes/cache.py:20-76` (cache_check_node)
- Edit: `telegram_bot/graph/graph.py:17-28,60-69` (build_graph signature + retrieve partial)
- Edit: `telegram_bot/bot.py:106-116` (PropertyBot.__init__ service init)
- Edit: `telegram_bot/bot.py:297-305` (PropertyBot.stop cleanup for shared httpx clients)
- Edit: `telegram_bot/graph/config.py:96-112` (factory methods)
- Test: `tests/unit/integrations/test_embeddings.py`
- Test: `tests/unit/graph/test_retrieve_node.py`
- Test: `tests/unit/graph/test_cache_nodes.py`
- Test: `tests/unit/test_bot_handlers.py` (mock init patches for new hybrid class)

### Step 1: Write failing test for BGEM3HybridEmbeddings

В `tests/unit/integrations/test_embeddings.py` добавить:

```python
class TestBGEM3HybridEmbeddings:
    async def test_aembed_hybrid_returns_dense_and_sparse(self):
        """Hybrid embed returns both dense_vecs and lexical_weights from one call."""
        hybrid_response = {
            "dense_vecs": [[0.1, 0.2, 0.3]],
            "lexical_weights": [{"indices": [1, 5], "values": [0.1, 0.5]}],
        }
        mock_response = httpx.Response(
            200,
            json=hybrid_response,
            request=httpx.Request("POST", "http://fake:8000/encode/hybrid"),
        )
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            from telegram_bot.integrations.embeddings import BGEM3HybridEmbeddings

            emb = BGEM3HybridEmbeddings(base_url="http://fake:8000")
            dense, sparse = await emb.aembed_hybrid("test query")
        assert dense == [0.1, 0.2, 0.3]
        assert sparse == {"indices": [1, 5], "values": [0.1, 0.5]}

    async def test_posts_to_hybrid_endpoint(self):
        hybrid_response = {
            "dense_vecs": [[0.1]],
            "lexical_weights": [{"indices": [1], "values": [0.1]}],
        }
        mock_response = httpx.Response(
            200,
            json=hybrid_response,
            request=httpx.Request("POST", "http://fake:8000/encode/hybrid"),
        )
        with patch(
            "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response
        ) as mock_post:
            from telegram_bot.integrations.embeddings import BGEM3HybridEmbeddings

            emb = BGEM3HybridEmbeddings(base_url="http://fake:8000")
            await emb.aembed_hybrid("test")
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "/encode/hybrid" in call_args[0][0]

    async def test_shared_client_reused(self):
        """Client is created once and reused across calls."""
        hybrid_response = {
            "dense_vecs": [[0.1]],
            "lexical_weights": [{"indices": [1], "values": [0.1]}],
        }
        mock_response = httpx.Response(
            200,
            json=hybrid_response,
            request=httpx.Request("POST", "http://fake:8000/encode/hybrid"),
        )
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            from telegram_bot.integrations.embeddings import BGEM3HybridEmbeddings

            emb = BGEM3HybridEmbeddings(base_url="http://fake:8000")
            await emb.aembed_hybrid("test1")
            await emb.aembed_hybrid("test2")
            # Same client instance used (shared)
            assert emb._client is not None

    async def test_aembed_query_delegates_to_hybrid(self):
        """aembed_query returns only dense part from hybrid call."""
        hybrid_response = {
            "dense_vecs": [[0.1, 0.2]],
            "lexical_weights": [{"indices": [1], "values": [0.5]}],
        }
        mock_response = httpx.Response(
            200,
            json=hybrid_response,
            request=httpx.Request("POST", "http://fake:8000/encode/hybrid"),
        )
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            from telegram_bot.integrations.embeddings import BGEM3HybridEmbeddings

            emb = BGEM3HybridEmbeddings(base_url="http://fake:8000")
            result = await emb.aembed_query("test")
        assert result == [0.1, 0.2]
```

### Step 2: Run test to verify it fails

```bash
uv run pytest tests/unit/integrations/test_embeddings.py::TestBGEM3HybridEmbeddings -v
```

Expected: `ImportError: cannot import name 'BGEM3HybridEmbeddings'`

### Step 3: Implement BGEM3HybridEmbeddings

В `telegram_bot/integrations/embeddings.py` добавить после `BGEM3SparseEmbeddings`:

```python
class BGEM3HybridEmbeddings(Embeddings):
    """Combined dense+sparse embedding via BGE-M3 /encode/hybrid.

    Single HTTP call returns both dense and sparse vectors.
    Uses shared httpx.AsyncClient for connection pooling.
    """

    def __init__(
        self,
        base_url: str = "http://bge-m3:8000",
        timeout: float = 120.0,
        max_length: int = 512,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_length = max_length
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._client

    @observe(name="bge-m3-hybrid-embed")
    async def aembed_hybrid(self, text: str) -> tuple[list[float], dict[str, Any]]:
        """Embed text via /encode/hybrid, returning (dense, sparse)."""
        client = self._get_client()
        response = await client.post(
            f"{self.base_url}/encode/hybrid",
            json={"texts": [text], "max_length": self.max_length},
        )
        response.raise_for_status()
        data = response.json()
        dense = data["dense_vecs"][0]
        sparse = data["lexical_weights"][0]
        return dense, sparse

    @observe(name="bge-m3-hybrid-embed-batch")
    async def aembed_hybrid_batch(
        self, texts: list[str]
    ) -> tuple[list[list[float]], list[dict[str, Any]]]:
        """Batch embed via /encode/hybrid."""
        if not texts:
            return [], []
        client = self._get_client()
        response = await client.post(
            f"{self.base_url}/encode/hybrid",
            json={"texts": texts, "max_length": self.max_length},
        )
        response.raise_for_status()
        data = response.json()
        return data["dense_vecs"], data["lexical_weights"]

    async def aembed_query(self, text: str) -> list[float]:
        dense, _ = await self.aembed_hybrid(text)
        return dense

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        dense_vecs, _ = await self.aembed_hybrid_batch(texts)
        return dense_vecs

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return asyncio.get_event_loop().run_until_complete(self.aembed_documents(texts))

    def embed_query(self, text: str) -> list[float]:
        return asyncio.get_event_loop().run_until_complete(self.aembed_query(text))

    async def aclose(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
```

### Step 4: Run test to verify it passes

```bash
uv run pytest tests/unit/integrations/test_embeddings.py -v
```

Expected: all tests PASS, including new `TestBGEM3HybridEmbeddings`.

### Step 5: Update GraphConfig factories

В `telegram_bot/graph/config.py` добавить метод:

```python
    def create_hybrid_embeddings(self) -> Any:
        """Create BGEM3HybridEmbeddings instance."""
        from telegram_bot.integrations.embeddings import BGEM3HybridEmbeddings

        return BGEM3HybridEmbeddings(
            base_url=self.bge_m3_url,
            timeout=self.bge_m3_timeout,
        )
```

### Step 6: Update PropertyBot to use hybrid embeddings

В `telegram_bot/bot.py:106-116` заменить инициализацию:

```python
        from .integrations.embeddings import (
            BGEM3Embeddings,
            BGEM3HybridEmbeddings,
            BGEM3SparseEmbeddings,
        )

        self._cache = CacheLayerManager(redis_url=config.redis_url)
        self._hybrid = BGEM3HybridEmbeddings(
            base_url=config.bge_m3_url,
        )
        # Use hybrid as primary embeddings provider
        self._embeddings = self._hybrid
        self._sparse = BGEM3SparseEmbeddings(
            base_url=config.bge_m3_url,
        )
```

### Step 6.1: Close shared clients on shutdown

В `telegram_bot/bot.py:297-305` добавить cleanup:

```python
    async def stop(self):
        """Stop bot and cleanup."""
        logger.info("Stopping bot...")
        await self._redis_monitor.stop()
        await self._cache.close()
        await self._qdrant.close()
        if hasattr(self._embeddings, "aclose"):
            await self._embeddings.aclose()
        if hasattr(self._sparse, "aclose"):
            await self._sparse.aclose()
        if self._reranker and hasattr(self._reranker, "close"):
            await self._reranker.close()
        await self.bot.session.close()
```

### Step 7: Update retrieve_node to use hybrid when re-embedding

В `telegram_bot/graph/nodes/retrieve.py:56-78`, заменить parallel dense+sparse блок:

```python
    # After rewrite, query_embedding is None — re-embed via hybrid
    if dense_vector is None and embeddings is not None:
        dense_vector = await cache.get_embedding(query)
        if dense_vector is None:
            sparse_cached = await cache.get_sparse_embedding(query)
            if sparse_cached is not None:
                # Dense miss, sparse cached → just compute dense
                dense_vector = await embeddings.aembed_query(query)
                await cache.store_embedding(query, dense_vector)
                sparse_vector = sparse_cached
            elif hasattr(embeddings, "aembed_hybrid"):
                # Hybrid: single call for both dense + sparse
                dense_vector, sparse_vector = await embeddings.aembed_hybrid(query)
                await cache.store_embedding(query, dense_vector)
                await cache.store_sparse_embedding(query, sparse_vector)
            else:
                # Fallback: parallel dense + sparse (old path)
                import asyncio

                async def _get_dense() -> list[float]:
                    vec: list[float] = await embeddings.aembed_query(query)
                    await cache.store_embedding(query, vec)
                    return vec

                async def _get_sparse() -> Any:
                    vec = await sparse_embeddings.aembed_query(query)
                    await cache.store_sparse_embedding(query, vec)
                    return vec

                dense_vector, sparse_vector = await asyncio.gather(
                    _get_dense(), _get_sparse()
                )
```

### Step 8: Update cache_check_node to use hybrid for initial embedding

В `telegram_bot/graph/nodes/cache.py:45-49`, заменить embedding computation:

```python
    # Step 1: Get or compute dense embedding (prefer hybrid for efficiency)
    embedding = await cache.get_embedding(query)
    if embedding is None:
        if hasattr(embeddings, "aembed_hybrid"):
            # Hybrid: get both dense + sparse in one call, cache both
            embedding, sparse = await embeddings.aembed_hybrid(query)
            await cache.store_embedding(query, embedding)
            await cache.store_sparse_embedding(query, sparse)
        else:
            embedding = await embeddings.aembed_query(query)
            await cache.store_embedding(query, embedding)
```

### Step 9: Run all graph tests

```bash
uv run pytest tests/unit/graph/ tests/unit/integrations/test_embeddings.py tests/unit/test_bot_handlers.py -v
```

Expected: all PASS.

### Step 10: Lint + commit

```bash
uv run ruff check telegram_bot/integrations/embeddings.py telegram_bot/graph/nodes/retrieve.py telegram_bot/graph/nodes/cache.py telegram_bot/bot.py telegram_bot/graph/config.py tests/unit/integrations/test_embeddings.py tests/unit/test_bot_handlers.py --output-format=concise
git add telegram_bot/integrations/embeddings.py telegram_bot/graph/nodes/retrieve.py telegram_bot/graph/nodes/cache.py telegram_bot/bot.py telegram_bot/graph/config.py tests/unit/integrations/test_embeddings.py tests/unit/test_bot_handlers.py
git commit -m "perf(embeddings): add BGEM3HybridEmbeddings with /encode/hybrid + connection pooling

Single HTTP call for dense+sparse instead of two separate calls.
Shared httpx.AsyncClient for connection reuse.
cache_check_node and retrieve_node prefer hybrid when available.

Refs #106, #105"
```

---

## Task 2: Fix latency_total_ms Score

**Цель:** Использовать wall-time вместо `sum(latency_stages.values())` — inflated 300x+ при rewrite loops.

**Files:**
- Edit: `telegram_bot/bot.py:38-65` (_write_langfuse_scores + handle_query)
- Test: `tests/unit/test_bot_handlers.py`

### Step 1: Write failing test

В `tests/unit/test_bot_handlers.py` добавить (после существующих тестов):

```python
class TestWriteLangfuseScores:
    def test_latency_total_ms_uses_wall_time(self):
        """latency_total_ms should use pipeline_wall_ms from state, not sum of stages."""
        from telegram_bot.bot import _write_langfuse_scores

        mock_lf = MagicMock()
        result = {
            "query_type": "GENERAL",
            "cache_hit": False,
            "search_results_count": 20,
            "rerank_applied": False,
            "latency_stages": {"cache_check": 5.0, "retrieve": 8.0, "generate": 3.0},
            "pipeline_wall_ms": 7500.0,  # wall-time set by handle_query
        }
        _write_langfuse_scores(mock_lf, result)
        # Find the latency_total_ms call
        calls = {c.kwargs["name"]: c.kwargs["value"] for c in mock_lf.score_current_trace.call_args_list}
        assert calls["latency_total_ms"] == 7500.0

    def test_latency_total_ms_fallback_zero(self):
        """Without pipeline_wall_ms, latency_total_ms should be 0."""
        from telegram_bot.bot import _write_langfuse_scores

        mock_lf = MagicMock()
        result = {"query_type": "FAQ", "latency_stages": {}}
        _write_langfuse_scores(mock_lf, result)
        calls = {c.kwargs["name"]: c.kwargs["value"] for c in mock_lf.score_current_trace.call_args_list}
        assert calls["latency_total_ms"] == 0.0
```

### Step 2: Run test to verify it fails

```bash
uv run pytest tests/unit/test_bot_handlers.py::TestWriteLangfuseScores -v
```

Expected: FAIL — `pipeline_wall_ms` not used yet.

### Step 3: Fix _write_langfuse_scores to use wall-time

В `telegram_bot/bot.py:38-46` заменить:

```python
def _write_langfuse_scores(lf: Any, result: dict) -> None:
    """Write 12 Langfuse scores from graph result state."""
    total_ms = result.get("pipeline_wall_ms", 0.0)

    scores = {
        "query_type": _QUERY_TYPE_SCORE.get(result.get("query_type", ""), 1.0),
        "latency_total_ms": total_ms,
```

### Step 4: Set pipeline_wall_ms in handle_query

В `telegram_bot/bot.py:226-258`, добавить timing:

```python
    @observe(name="telegram-rag-query")
    async def handle_query(self, message: Message):
        """Handle user query via LangGraph RAG pipeline."""
        import time

        pipeline_start = time.perf_counter()
        # ... existing code ...
        assert message.bot is not None
        assert message.from_user is not None
        bot = message.bot
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")

        state = make_initial_state(
            user_id=message.from_user.id,
            session_id=make_session_id("chat", message.chat.id),
            query=message.text or "",
        )
        state["max_rewrite_attempts"] = self._graph_config.max_rewrite_attempts

        with propagate_attributes(
            session_id=state["session_id"],
            user_id=str(state["user_id"]),
            tags=["telegram", "rag"],
        ):
            graph = build_graph(
                cache=self._cache,
                embeddings=self._embeddings,
                sparse_embeddings=self._sparse,
                qdrant=self._qdrant,
                reranker=self._reranker,
                llm=self._llm,
                message=message,
            )

            async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
                result = await graph.ainvoke(state)

            # Wall-time for accurate latency_total_ms
            result["pipeline_wall_ms"] = (time.perf_counter() - pipeline_start) * 1000

            # Update trace with input/output and metadata
            lf = get_client()
            # ... rest unchanged ...
```

### Step 5: Run test to verify it passes

```bash
uv run pytest tests/unit/test_bot_handlers.py -v
```

Expected: all PASS.

### Step 6: Lint + commit

```bash
uv run ruff check telegram_bot/bot.py tests/unit/test_bot_handlers.py --output-format=concise
git add telegram_bot/bot.py tests/unit/test_bot_handlers.py
git commit -m "fix(observability): use wall-time for latency_total_ms score

sum(latency_stages) was inflated 300x+ on rewrite loops due to
dict accumulation. Use perf_counter wall-time set by handle_query.

Fixes #107"
```

---

## Task 3: Recalibrate Grade Threshold for RRF Scores

**Цель:** RRF scores = 1/(k+rank) ≈ 0.01-0.02. Текущий порог 0.3 = ничего не relevant → вечные rewrites.

**Files:**
- Edit: `telegram_bot/graph/nodes/grade.py:18`
- Edit: `telegram_bot/graph/config.py` (add configurable `relevance_threshold_rrf`, default `0.005`)
- Test: `tests/unit/graph/test_agentic_nodes.py`
- Test: `tests/unit/graph/test_edges.py`

### Step 1: Write failing test for RRF-scale scores

В `tests/unit/graph/test_agentic_nodes.py` добавить:

```python
class TestGradeNodeRRFScores:
    async def test_rrf_scores_are_relevant(self):
        """RRF scores ~0.016 should be considered relevant (not irrelevant)."""
        state = make_initial_state(user_id=1, session_id="s", query="квартиры")
        state["documents"] = [
            {"score": 0.016, "text": "doc1"},  # RRF rank 1: 1/61 ≈ 0.016
            {"score": 0.015, "text": "doc2"},
            {"score": 0.014, "text": "doc3"},
        ]
        result = await grade_node(state)
        assert result["documents_relevant"] is True

    async def test_very_low_scores_are_not_relevant(self):
        """Scores near zero should still be irrelevant."""
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["documents"] = [
            {"score": 0.001, "text": "garbage"},
        ]
        result = await grade_node(state)
        assert result["documents_relevant"] is False
```

### Step 2: Run test to verify it fails

```bash
uv run pytest tests/unit/graph/test_agentic_nodes.py::TestGradeNodeRRFScores -v
```

Expected: FAIL — `0.016 > 0.3` is False, documents_relevant=False.

### Step 3: Fix RELEVANCE_THRESHOLD

В `telegram_bot/graph/config.py` добавить:

```python
    relevance_threshold_rrf: float = 0.005
```

и загрузку из env в `from_env()`:

```python
            relevance_threshold_rrf=float(os.getenv("RELEVANCE_THRESHOLD_RRF", "0.005")),
```

В `telegram_bot/graph/nodes/grade.py` использовать значение из `GraphConfig`:

```python
# RRF scores = 1/(k+rank), k=60 → rank 1 = ~0.016, rank 10 = ~0.014
# Threshold must be below typical top-1 RRF score
config = GraphConfig.from_env()
relevance_threshold = config.relevance_threshold_rrf
relevant = top_score > relevance_threshold
```

Логика:
- RRF rank 1: 1/61 = 0.0164 → relevant
- RRF rank 100: 1/160 = 0.00625 → relevant
- Garbage: < 0.005 → not relevant

### Step 4: Run test to verify it passes

```bash
uv run pytest tests/unit/graph/test_agentic_nodes.py -v
```

Expected: all PASS.

### Step 5: Keep `skip_rerank_threshold` unchanged for Sprint 1

RRF scores are ~0.01-0.02, so `skip_rerank_threshold=0.85` is unreachable.
For Sprint 1 leave it as-is to restore correctness first (relevant docs -> rerank).
Threshold retuning (or normalized confidence) is a separate optimization task after fresh traces.

### Step 6: Run edge tests (regression)

```bash
uv run pytest tests/unit/graph/test_edges.py -v
```

Expected: all PASS (edge tests use explicit state values, not RELEVANCE_THRESHOLD).

### Step 7: Lint + commit

```bash
uv run ruff check telegram_bot/graph/nodes/grade.py telegram_bot/graph/config.py tests/unit/graph/test_agentic_nodes.py --output-format=concise
git add telegram_bot/graph/nodes/grade.py telegram_bot/graph/config.py tests/unit/graph/test_agentic_nodes.py
git commit -m "fix(grade): recalibrate RELEVANCE_THRESHOLD for RRF score scale

RRF scores are 1/(k+rank) ≈ 0.005-0.016. Old threshold 0.3 was
unreachable → all docs marked irrelevant → infinite rewrite loops.
Lower to 0.005 so RRF results are properly graded.

Fixes #109"
```

---

## Task 4: Implement Real Langfuse Scores (5 hardcoded → real values)

**Цель:** Заменить 5 hardcoded 0.0 scores реальными значениями из state.

**Files:**
- Edit: `telegram_bot/bot.py:52-60` (_write_langfuse_scores)
- Edit: `telegram_bot/graph/state.py` (add fields)
- Edit: `telegram_bot/graph/nodes/cache.py` (set cache hit flags)
- Edit: `telegram_bot/graph/nodes/retrieve.py` (set search_cache_hit)
- Test: `tests/unit/test_bot_handlers.py`
- Test: `tests/unit/graph/test_cache_nodes.py`

### Step 1: Write failing tests

В `tests/unit/test_bot_handlers.py::TestWriteLangfuseScores` добавить:

```python
    def test_real_scores_from_state(self):
        """Hardcoded scores should now use real state values."""
        from telegram_bot.bot import _write_langfuse_scores

        mock_lf = MagicMock()
        result = {
            "query_type": "FAQ",
            "cache_hit": False,
            "search_results_count": 20,
            "rerank_applied": True,
            "latency_stages": {"generate": 1.0},
            "pipeline_wall_ms": 5000.0,
            "embeddings_cache_hit": True,
            "search_cache_hit": False,
            "grade_confidence": 0.016,
        }
        _write_langfuse_scores(mock_lf, result)
        calls = {c.kwargs["name"]: c.kwargs["value"] for c in mock_lf.score_current_trace.call_args_list}
        assert calls["embeddings_cache_hit"] == 1.0
        assert calls["search_cache_hit"] == 0.0
        assert calls["confidence_score"] == 0.016
```

### Step 2: Run test to verify it fails

```bash
uv run pytest tests/unit/test_bot_handlers.py::TestWriteLangfuseScores::test_real_scores_from_state -v
```

Expected: FAIL — `embeddings_cache_hit` is always 0.0.

### Step 3: Add state fields

В `telegram_bot/graph/state.py`, добавить в `RAGState`:

```python
    embeddings_cache_hit: bool
    search_cache_hit: bool
```

В `make_initial_state()` добавить:

```python
        "embeddings_cache_hit": False,
        "search_cache_hit": False,
```

### Step 4: Set embeddings_cache_hit in cache_check_node

В `telegram_bot/graph/nodes/cache.py:45-49`, после получения embedding:

```python
    embedding = await cache.get_embedding(query)
    embeddings_cache_hit = embedding is not None
    if embedding is None:
        if hasattr(embeddings, "aembed_hybrid"):
            embedding, sparse = await embeddings.aembed_hybrid(query)
            await cache.store_embedding(query, embedding)
            await cache.store_sparse_embedding(query, sparse)
        else:
            embedding = await embeddings.aembed_query(query)
            await cache.store_embedding(query, embedding)
```

И добавить `"embeddings_cache_hit": embeddings_cache_hit` в оба return dict (hit и miss).

### Step 5: Set search_cache_hit in retrieve_node

В `telegram_bot/graph/nodes/retrieve.py:86-97`, в cached_results return:

```python
        return {
            "documents": cached_results,
            "search_results_count": len(cached_results),
            "search_cache_hit": True,
            "latency_stages": {**state.get("latency_stages", {}), "retrieve": latency},
            "retrieval_backend_error": False,
            "retrieval_error_type": None,
        }
```

И в основном return (line 121-132) добавить `"search_cache_hit": False`.

### Step 6: Update _write_langfuse_scores

В `telegram_bot/bot.py:48-61` заменить hardcoded scores:

```python
    scores = {
        "query_type": _QUERY_TYPE_SCORE.get(result.get("query_type", ""), 1.0),
        "latency_total_ms": total_ms,
        "semantic_cache_hit": 1.0 if result.get("cache_hit") else 0.0,
        "embeddings_cache_hit": 1.0 if result.get("embeddings_cache_hit") else 0.0,
        "search_cache_hit": 1.0 if result.get("search_cache_hit") else 0.0,
        "rerank_applied": 1.0 if result.get("rerank_applied") else 0.0,
        "rerank_cache_hit": 0.0,  # Tracked when rerank cache implemented
        "results_count": float(result.get("search_results_count", 0)),
        "no_results": 1.0 if result.get("search_results_count", 0) == 0 else 0.0,
        "llm_used": 1.0 if "generate" in latency_stages else 0.0,
        "confidence_score": float(result.get("grade_confidence", 0.0)),
        "hyde_used": 0.0,  # HyDE not implemented in current pipeline
    }
```

### Step 7: Run all tests

```bash
uv run pytest tests/unit/test_bot_handlers.py tests/unit/graph/test_cache_nodes.py tests/unit/graph/test_retrieve_node.py tests/unit/graph/test_state.py -v
```

Expected: all PASS.

### Step 8: Lint + commit

```bash
uv run ruff check telegram_bot/bot.py telegram_bot/graph/state.py telegram_bot/graph/nodes/cache.py telegram_bot/graph/nodes/retrieve.py tests/unit/test_bot_handlers.py --output-format=concise
git add telegram_bot/bot.py telegram_bot/graph/state.py telegram_bot/graph/nodes/cache.py telegram_bot/graph/nodes/retrieve.py tests/unit/test_bot_handlers.py
git commit -m "feat(observability): implement real Langfuse scores for cache hits and confidence

Replace 3 hardcoded 0.0 scores with real values from pipeline state:
embeddings_cache_hit, search_cache_hit, confidence_score.

Refs #103"
```

---

## Task 5: Integration Verification (after Tasks 1-4 merge)

**Цель:** Убедиться что все изменения работают вместе.

**Files:**
- N/A (verification only)

### Step 1: Run full unit test suite

```bash
uv run pytest tests/unit/ -n auto -q
```

Expected: no new failures vs baseline on `main` (regression-free).

### Step 2: Run integration tests

```bash
uv run pytest tests/integration/test_graph_paths.py -v
```

Expected: all 6 path tests PASS.

### Step 3: Lint + types

```bash
uv run ruff check src telegram_bot tests services --output-format=concise
uv run mypy src telegram_bot --ignore-missing-imports
```

Expected: both clean for changed modules; if unrelated baseline debt exists, attach diff vs `main`.

### Step 3.1: Validate via SDK + traces (required)

```bash
# 1) Rebuild + restart stack
docker compose -f docker-compose.dev.yml up -d --build bge-m3 bot

# 2) Produce fresh traces (smoke / real prompts)
# 3) Validate with Langfuse SDK script
E2E_VALIDATE_LANGFUSE=1 uv run python scripts/e2e/runner.py --group smoke
```

Expected:
- `latency_total_ms` close to wall-time (ratio ~0.8-1.2 on root traces)
- rerank path appears for relevant RRF scores
- orphan traces reduced or explicitly filtered in analysis

### Step 4: Post results to #120

```bash
gh issue comment 120 --body "## Sprint 1 Complete

### Changes
- perf(embeddings): BGEM3HybridEmbeddings — /encode/hybrid + connection pooling (#106)
- fix(observability): wall-time latency_total_ms (#107)
- fix(grade): RELEVANCE_THRESHOLD 0.3 → 0.005 for RRF scores (#109)
- feat(observability): real Langfuse scores (#103)

### Test Results
<paste unit test output>

### Expected Impact
- BGE-M3 embed: 2x speedup (1 call vs 2)
- latency_total_ms: correct values in all traces
- Rewrite loops: eliminated (scores now correctly graded)
- Rerank: will fire for relevant documents
- 3 more Langfuse scores with real data"
```
