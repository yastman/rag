# BGE-M3 Embedding Retry & Resilience — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the BGE-M3 embedding call resilient to transient failures (RemoteProtocolError, timeouts, restarts) with retry/backoff, graceful fallback, observability scores, and alerting.

**Architecture:** SDK-first transport config in `httpx.AsyncClient` (`AsyncHTTPTransport(retries=1)` + granular `httpx.Timeout`) handles connection-level flakiness. Tenacity wraps `BGEM3HybridEmbeddings` methods for transient protocol/read/connect failures with exponential backoff + jitter. `cache_check_node` marks explicit embedding error flags, and `route_cache` short-circuits to `respond` via `embedding_error` (without overloading `cache_hit`). New Langfuse scores track embedding error/latency. Loki rules alert on retry/error signals from bot logs.

**Tech Stack:** tenacity (already in pyproject.toml, unused), httpx.Timeout, httpx.AsyncHTTPTransport, Langfuse scores, Loki alert rules

**Issue:** [#210](https://github.com/yastman/rag/issues/210)

---

## Evidence Base (Context7 + Exa, verified 2026-02-12)

- LangGraph BaseCheckpointSaver contract confirms async saver method surface (`aput`, `aput_writes`, `aget_tuple`, `alist`) and supports subclass extension at saver layer: https://github.com/langchain-ai/langgraph/blob/main/libs/checkpoint/README.md
- `langgraph-redis` docs confirm `AsyncRedisSaver` / `AsyncShallowRedisSaver` async usage patterns and compatibility with async graph execution: https://github.com/redis-developer/langgraph-redis/blob/main/README.md
- HTTPX transport docs: transport-level retries are connection-level (`ConnectError`, `ConnectTimeout`) and not a full retry policy for read/protocol/status failures: https://www.python-httpx.org/advanced/transports/
- HTTPX timeout docs: recommended granular `connect/read/write/pool` timeout configuration over one flat timeout: https://www.python-httpx.org/advanced/timeouts/
- Tenacity API: `retry_if_exception_type`, `wait_exponential_jitter`, `stop_after_attempt`, `before_sleep_log`, `reraise` are first-class primitives for bounded async retries: https://tenacity.readthedocs.io/en/latest/api.html
- Langfuse Python decorator docs: nested spans with `@observe`, and safe payload control via `capture_input=False, capture_output=False` plus `update_current_span`: https://langfuse.com/docs/observability/sdk/python/decorators
- Grafana/Loki query guidance: prefer narrow selectors and simple filters over broad regex for reliable alert queries: https://grafana.com/docs/loki/latest/query/bp-query/

---

## Summary of Changes

| File | Action | Purpose |
|------|--------|---------|
| `telegram_bot/integrations/embeddings.py` | Modify | Add tenacity retry + granular timeout |
| `telegram_bot/graph/nodes/cache.py` | Modify | try/except fallback on embedding error |
| `telegram_bot/graph/state.py` | Modify | Add `embedding_error`, `embedding_error_type` fields |
| `telegram_bot/graph/edges.py` | Modify | Route embedding failures directly to `respond` without marking cache hit |
| `telegram_bot/bot.py` | Modify | Write 2 new Langfuse scores |
| `docker/monitoring/rules/infrastructure.yaml` | Modify | Add 2 BGE-M3 alert rules |
| `tests/unit/integrations/test_embeddings.py` | Modify | Add retry + timeout tests |
| `tests/unit/graph/test_cache_nodes.py` | Modify | Add embedding error fallback tests |
| `tests/unit/graph/test_edges.py` | Modify | Add route test for `embedding_error` short-circuit |
| `tests/unit/test_bot_handlers.py` | Modify | Add embedding error score tests |

---

## Task 1: Tenacity Retry + Granular Timeout on BGEM3HybridEmbeddings

**Files:**
- Modify: `telegram_bot/integrations/embeddings.py:113-188`
- Test: `tests/unit/integrations/test_embeddings.py`

**Design:**
- SDK transport retry in client: `httpx.AsyncHTTPTransport(retries=1)` for connection setup failures
- `@retry` decorator on `aembed_hybrid` and `aembed_hybrid_batch` (between existing `@observe` and method body)
- Retry only on transient transport errors: `httpx.RemoteProtocolError`, `httpx.ConnectError`, `httpx.ReadTimeout`, `httpx.ConnectTimeout`
- Do NOT retry on `httpx.HTTPStatusError` (4xx/5xx from BGE-M3 = a real bug, not transient)
- `wait_exponential_jitter(initial=0.5, max=4, jitter=1)` — keeps total wait under 10s for 3 attempts
- `stop_after_attempt(3)`
- `before_sleep_log(logger, logging.WARNING)` — logs each retry for Loki alerting
- `reraise=True` — preserves original exception type for callers
- Replace `timeout=120.0` with `httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)` — 30s read is enough for BGE-M3 on CPU; 120s was hiding hung service

**Decorator stacking order:**
```python
@observe(name="bge-m3-hybrid-embed")   # outer — one Langfuse span per call
@retry(...)                             # inner — retries are hidden inside the span
async def aembed_hybrid(self, text):
```

**Step 1: Write failing tests for retry behavior**

Add to `tests/unit/integrations/test_embeddings.py`:

```python
import httpx
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from telegram_bot.integrations.embeddings import BGEM3HybridEmbeddings


class TestBGEM3HybridRetry:
    """Tests for retry behavior on transient errors."""

    async def test_retries_on_remote_protocol_error(self):
        """Retries on RemoteProtocolError and succeeds on second attempt."""
        hybrid_ok = {
            "dense_vecs": [[0.1, 0.2]],
            "lexical_weights": [{"1": 0.5}],
        }
        ok_response = httpx.Response(
            200, json=hybrid_ok,
            request=httpx.Request("POST", "http://fake:8000/encode/hybrid"),
        )
        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.RemoteProtocolError(
                    "Server disconnected without sending a response"
                )
            return ok_response

        with patch("httpx.AsyncClient.post", side_effect=mock_post):
            emb = BGEM3HybridEmbeddings(base_url="http://fake:8000")
            dense, sparse = await emb.aembed_hybrid("test")

        assert dense == [0.1, 0.2]
        assert call_count == 2  # 1 fail + 1 success

    async def test_raises_after_max_retries(self):
        """Raises original exception after all retries exhausted."""
        async def always_fail(*args, **kwargs):
            raise httpx.RemoteProtocolError(
                "Server disconnected without sending a response"
            )

        with patch("httpx.AsyncClient.post", side_effect=always_fail):
            emb = BGEM3HybridEmbeddings(base_url="http://fake:8000")
            with pytest.raises(httpx.RemoteProtocolError):
                await emb.aembed_hybrid("test")

    async def test_no_retry_on_http_status_error(self):
        """Does NOT retry on HTTP 500 (status error = not transient transport)."""
        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            response = httpx.Response(
                500,
                request=httpx.Request("POST", "http://fake:8000/encode/hybrid"),
            )
            response.raise_for_status()

        with patch("httpx.AsyncClient.post", side_effect=mock_post):
            emb = BGEM3HybridEmbeddings(base_url="http://fake:8000")
            with pytest.raises(httpx.HTTPStatusError):
                await emb.aembed_hybrid("test")

        assert call_count == 1  # No retries

    async def test_retries_on_connect_timeout(self):
        """Retries on ConnectTimeout."""
        hybrid_ok = {
            "dense_vecs": [[0.1]],
            "lexical_weights": [{"1": 0.5}],
        }
        ok_response = httpx.Response(
            200, json=hybrid_ok,
            request=httpx.Request("POST", "http://fake:8000/encode/hybrid"),
        )
        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ConnectTimeout("Connection timed out")
            return ok_response

        with patch("httpx.AsyncClient.post", side_effect=mock_post):
            emb = BGEM3HybridEmbeddings(base_url="http://fake:8000")
            dense, sparse = await emb.aembed_hybrid("test")

        assert call_count == 2


class TestBGEM3HybridTimeout:
    """Tests for granular timeout configuration."""

    async def test_uses_granular_timeout(self):
        """Client uses httpx.Timeout with separate connect/read values."""
        emb = BGEM3HybridEmbeddings(base_url="http://fake:8000")
        client = emb._get_client()
        timeout = client.timeout
        assert timeout.connect == 5.0
        assert timeout.read == 30.0
        assert timeout.write == 5.0
        assert timeout.pool == 5.0

    async def test_custom_timeout_override(self):
        """Custom timeout parameter is respected (backward compat)."""
        emb = BGEM3HybridEmbeddings(base_url="http://fake:8000", timeout=60.0)
        client = emb._get_client()
        # When float is passed, all components use that value
        assert client.timeout.read == 60.0
```

**Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/unit/integrations/test_embeddings.py::TestBGEM3HybridRetry -v
uv run pytest tests/unit/integrations/test_embeddings.py::TestBGEM3HybridTimeout -v
```

Expected: FAIL — no retry behavior, flat 120s timeout.

**Step 3: Implement retry + timeout in embeddings.py**

In `telegram_bot/integrations/embeddings.py`, modify `BGEM3HybridEmbeddings`:

```python
import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

# Transient transport errors worth retrying
_RETRYABLE_ERRORS = (
    httpx.RemoteProtocolError,
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.ConnectTimeout,
)

_embed_retry = retry(
    retry=retry_if_exception_type(_RETRYABLE_ERRORS),
    wait=wait_exponential_jitter(initial=0.5, max=4, jitter=1),
    stop=stop_after_attempt(3),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


class BGEM3HybridEmbeddings(Embeddings):
    def __init__(
        self,
        base_url: str = "http://bge-m3:8000",
        timeout: float | httpx.Timeout | None = None,
        max_length: int = 512,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.max_length = max_length
        if timeout is None:
            self._timeout = httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)
        elif isinstance(timeout, (int, float)):
            self._timeout = httpx.Timeout(timeout)
        else:
            self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                transport=httpx.AsyncHTTPTransport(retries=1),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._client

    @observe(name="bge-m3-hybrid-embed")
    @_embed_retry
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
    @_embed_retry
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
```

**Note:** Remove the old `self.timeout = timeout` attribute. The `timeout` constructor param now accepts `float | httpx.Timeout | None`. Backward compat: passing `float` wraps in `httpx.Timeout(val)`. Default: granular.

**Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/unit/integrations/test_embeddings.py -v
```

Expected: ALL PASS.

**Step 5: Run full unit suite to check no regressions**

```bash
uv run pytest tests/unit/ -n auto --timeout=30
```

**Step 6: Commit**

```bash
git add telegram_bot/integrations/embeddings.py tests/unit/integrations/test_embeddings.py
git commit -m "fix(embeddings): add tenacity retry + granular timeout for BGE-M3 #210"
```

---

## Task 2: Graceful Fallback in cache_check_node

**Files:**
- Modify: `telegram_bot/graph/state.py:13-119` (add 2 fields)
- Modify: `telegram_bot/graph/nodes/cache.py:25-125` (try/except + fallback)
- Modify: `telegram_bot/graph/edges.py:34-40` (route by `embedding_error`)
- Test: `tests/unit/graph/test_cache_nodes.py`
- Test: `tests/unit/graph/test_edges.py`

**Design:**
- Add `embedding_error: bool` and `embedding_error_type: str | None` to RAGState + make_initial_state
- In cache_check_node, wrap the embedding call in try/except
- On failure: set `embedding_error=True`, `response` to user-friendly message, `cache_hit=False`
- `route_cache` checks `embedding_error` first and routes to `respond` (explicit error path)
- This keeps `semantic_cache_hit` and cache-hit analytics correct (no false cache hits on failures)
- The user sees: "Сервис временно недоступен. Пожалуйста, повторите через минуту."

**Step 1: Write failing tests**

Add to `tests/unit/graph/test_cache_nodes.py`:

```python
import httpx


class TestCacheCheckEmbeddingError:
    """Test cache_check_node graceful fallback on embedding failure."""

    @pytest.mark.asyncio
    async def test_embedding_error_sets_error_state(self):
        """When embedding fails, sets embedding_error and user-friendly response."""
        state = make_initial_state(user_id=1, session_id="s1", query="test query")
        state["query_type"] = "FAQ"

        cache = AsyncMock()
        cache.get_embedding = AsyncMock(return_value=None)  # cache miss

        embeddings = MagicMock()
        embeddings.aembed_hybrid = AsyncMock(
            side_effect=httpx.RemoteProtocolError("Server disconnected")
        )

        result = await cache_check_node(state, cache=cache, embeddings=embeddings)

        assert result["embedding_error"] is True
        assert result["embedding_error_type"] == "RemoteProtocolError"
        assert result["cache_hit"] is False
        assert "недоступен" in result["response"]
        assert result["query_embedding"] is None

    @pytest.mark.asyncio
    async def test_embedding_error_on_read_timeout(self):
        """ReadTimeout also triggers graceful fallback."""
        state = make_initial_state(user_id=1, session_id="s1", query="test query")
        state["query_type"] = "GENERAL"

        cache = AsyncMock()
        cache.get_embedding = AsyncMock(return_value=None)

        embeddings = MagicMock()
        embeddings.aembed_hybrid = AsyncMock(
            side_effect=httpx.ReadTimeout("Read timed out")
        )

        result = await cache_check_node(state, cache=cache, embeddings=embeddings)

        assert result["embedding_error"] is True
        assert result["cache_hit"] is False

    @pytest.mark.asyncio
    async def test_cached_embedding_skips_bge_call(self):
        """When embedding cache hits, no BGE-M3 call — no error possible."""
        state = make_initial_state(user_id=1, session_id="s1", query="test query")
        state["query_type"] = "FAQ"

        cache = AsyncMock()
        cache.get_embedding = AsyncMock(return_value=[0.1] * 1024)
        cache.check_semantic = AsyncMock(return_value=None)

        embeddings = MagicMock()
        # aembed_hybrid should NOT be called
        embeddings.aembed_hybrid = AsyncMock(
            side_effect=Exception("should not be called")
        )

        result = await cache_check_node(state, cache=cache, embeddings=embeddings)

        assert result["embedding_error"] is False
        assert result["cache_hit"] is False
        embeddings.aembed_hybrid.assert_not_awaited()
```

**Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/unit/graph/test_cache_nodes.py::TestCacheCheckEmbeddingError -v
```

Expected: FAIL — no `embedding_error` key in result, no try/except.

**Step 3: Add state fields in state.py**

In `telegram_bot/graph/state.py`, add to RAGState class:

```python
    # Embedding resilience (#210)
    embedding_error: bool
    embedding_error_type: str | None
```

And in `make_initial_state()`:

```python
        # Embedding resilience (#210)
        "embedding_error": False,
        "embedding_error_type": None,
```

**Step 4: Implement fallback in cache_check_node**

In `telegram_bot/graph/nodes/cache.py`, wrap the embedding section (lines 63-77):

```python
    # Step 1: Get or compute dense embedding (prefer hybrid for efficiency)
    embedding = await cache.get_embedding(query)
    embeddings_cache_hit = embedding is not None
    embedding_error = False
    embedding_error_type: str | None = None

    if embedding is None:
        try:
            _has_hybrid = callable(
                getattr(embeddings, "aembed_hybrid", None)
            ) and asyncio.iscoroutinefunction(embeddings.aembed_hybrid)
            if _has_hybrid:
                embedding, sparse = await embeddings.aembed_hybrid(query)
                await cache.store_embedding(query, embedding)
                await cache.store_sparse_embedding(query, sparse)
            else:
                embedding = await embeddings.aembed_query(query)
                await cache.store_embedding(query, embedding)
        except Exception as exc:
            embedding_error = True
            embedding_error_type = type(exc).__name__
            logger.error("Embedding failed after retries: %s: %s", embedding_error_type, exc)
            latency = time.perf_counter() - start
            lf.update_current_span(
                level="ERROR",
                output={
                    "embedding_error": True,
                    "embedding_error_type": embedding_error_type,
                    "error_message": str(exc)[:200],
                    "duration_ms": round(latency * 1000, 1),
                },
            )
            return {
                "cache_hit": False,
                "cached_response": None,
                "query_embedding": None,
                "embeddings_cache_hit": False,
                "embedding_error": True,
                "embedding_error_type": embedding_error_type,
                "response": "Сервис временно недоступен. Пожалуйста, повторите через минуту.",
                "latency_stages": {**state.get("latency_stages", {}), "cache_check": latency},
            }
```

**Step 5: Update route_cache for explicit embedding error path**

In `telegram_bot/graph/edges.py`, update `route_cache`:

```python
def route_cache(
    state: dict[str, Any],
) -> Literal["respond", "retrieve"]:
    """Route after cache check: embedding error/hit → respond, miss → retrieve."""
    if state.get("embedding_error", False):
        return "respond"
    if state.get("cache_hit", False):
        return "respond"
    return "retrieve"
```

Add test in `tests/unit/graph/test_edges.py`:

```python
def test_embedding_error_routes_to_respond(self):
    state = make_initial_state(user_id=1, session_id="s", query="test")
    state["embedding_error"] = True
    state["cache_hit"] = False
    assert route_cache(state) == "respond"
```

**Step 6: Run tests — verify they pass**

```bash
uv run pytest tests/unit/graph/test_cache_nodes.py -v
uv run pytest tests/unit/graph/test_edges.py::TestRouteCache -v
```

Expected: ALL PASS.

**Step 7: Commit**

```bash
git add telegram_bot/graph/state.py telegram_bot/graph/nodes/cache.py telegram_bot/graph/edges.py tests/unit/graph/test_cache_nodes.py tests/unit/graph/test_edges.py
git commit -m "fix(cache): explicit embedding error route without false cache-hit metrics #210"
```

---

## Task 3: Langfuse Scores for Embedding Errors

**Files:**
- Modify: `telegram_bot/bot.py:58-176` (add 2 scores)
- Test: `tests/unit/test_bot_handlers.py` (if score tests exist; otherwise add to existing test)

**Design:**
- `bge_embed_error` — BOOLEAN, 1 when embedding failed
- `bge_embed_latency_ms` — NUMERIC, from `latency_stages["cache_check"]` (cache_check includes the embedding call)

**Step 1: Write failing test for score writing**

Add a test that verifies `_write_langfuse_scores` writes `bge_embed_error`:

```python
def test_writes_embedding_error_score():
    """_write_langfuse_scores writes bge_embed_error when embedding failed."""
    from telegram_bot.bot import _write_langfuse_scores

    lf = MagicMock()
    result = {
        "query_type": "FAQ",
        "cache_hit": True,
        "embedding_error": True,
        "embedding_error_type": "RemoteProtocolError",
        "latency_stages": {"cache_check": 5.123},
        "pipeline_wall_ms": 5200.0,
        "user_perceived_wall_ms": 5200.0,
    }
    _write_langfuse_scores(lf, result)

    calls = {
        c.kwargs["name"]: c.kwargs.get("value")
        for c in lf.score_current_trace.call_args_list
        if "name" in c.kwargs
    }
    assert calls["bge_embed_error"] == 1
    assert "bge_embed_latency_ms" in calls
```

**Step 2: Run — verify fail**

```bash
uv run pytest tests/unit/test_bot_handlers.py::test_writes_embedding_error_score -v
```

**Step 3: Add scores to _write_langfuse_scores**

In `telegram_bot/bot.py`, after the voice transcription scores section (~line 155), add:

```python
    # --- Embedding resilience (#210) ---
    lf.score_current_trace(
        name="bge_embed_error",
        value=1 if result.get("embedding_error") else 0,
        data_type="BOOLEAN",
    )
    cache_check_s = result.get("latency_stages", {}).get("cache_check")
    if cache_check_s is not None:
        lf.score_current_trace(
            name="bge_embed_latency_ms",
            value=round(cache_check_s * 1000, 1),
        )
```

**Step 4: Run — verify pass**

```bash
uv run pytest tests/unit/test_bot_handlers.py -v
```

**Step 5: Commit**

```bash
git add telegram_bot/bot.py tests/unit/test_bot_handlers.py
git commit -m "feat(observability): add Langfuse scores for BGE-M3 embedding errors #210"
```

---

## Task 4: Loki Alert Rules for BGE-M3 Latency

**Files:**
- Modify: `docker/monitoring/rules/infrastructure.yaml`

**Design:**
- `BGEEmbedRetry` — warning when bot logs contain tenacity retry messages (before_sleep_log pattern: `Retrying ... in ... seconds`)
- `BGEEmbedTimeout` — warning when bot logs contain embedding error messages
- These fire from **bot container logs** (not bge-m3 container) — because the retry/error logging happens in the bot

**Step 1: Add alert rules**

Append to `docker/monitoring/rules/infrastructure.yaml` under EMBEDDING SERVICES section:

```yaml
      # BGE-M3 embedding latency and retries (from bot logs, #210)
      - alert: BGEEmbedRetryFromBot
        expr: |
          count_over_time({container="dev-bot"} |= "Retrying telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings.aembed_hybrid" [5m]) > 3
        for: 3m
        labels:
          severity: warning
          service: bge-m3
        annotations:
          summary: "BGE-M3 embedding retries detected in bot"
          description: "Bot is retrying BGE-M3 embedding calls — service may be degraded"

      - alert: BGEEmbedErrorFromBot
        expr: |
          count_over_time({container="dev-bot"} |= "Embedding failed after retries" [5m]) > 0
        for: 1m
        labels:
          severity: critical
          service: bge-m3
        annotations:
          summary: "BGE-M3 embedding failures in bot"
          description: "Bot embedding calls failing after all retries exhausted"
```

**Step 2: Verify rules syntax**

```bash
# Restart monitoring to pick up rules
docker compose -f docker-compose.dev.yml restart loki 2>/dev/null || echo "Loki not running (OK for dev)"
```

**Step 3: Commit**

```bash
git add docker/monitoring/rules/infrastructure.yaml
git commit -m "feat(alerts): add Loki rules for BGE-M3 embed retries and failures #210"
```

---

## Task 5: Final Verification

**Step 1: Run full unit test suite**

```bash
uv run pytest tests/unit/ -n auto --timeout=30
```

Expected: ALL PASS, no regressions.

**Step 2: Run graph path integration tests**

```bash
uv run pytest tests/integration/test_graph_paths.py -v
```

Expected: ALL 6 PASS (no changes to graph routing for happy paths).

**Step 3: Run lint + types**

```bash
make check
```

Expected: Clean.

**Step 4: Verify tenacity retry log format matches Loki rule**

The `before_sleep_log(logger, logging.WARNING)` format from tenacity is:
```
Retrying telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings.aembed_hybrid in X.XX seconds...
```

This matches the LogQL line filter for `Retrying telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings.aembed_hybrid`. Verify by checking tenacity log output in bot logs.

---

## Architecture Notes

### Why SDK-first (`AsyncHTTPTransport`) + tenacity?
- `AsyncHTTPTransport(retries=N)` is low-overhead SDK retry for connect-level failures
- HTTPX transport retries do not cover `RemoteProtocolError` / `ReadTimeout` and do not provide backoff/jitter policies for those paths
- tenacity adds bounded retries with jitter + logging for transient protocol/read failures
- Combined approach keeps client config idiomatic while covering real failure modes seen in traces

### Why catch Exception (not specific types) in cache_check_node?
- The retry decorator already filters retryable errors. If the exception reaches cache_check_node, either:
  - All retries exhausted (3 attempts failed) — `RemoteProtocolError` etc.
  - Non-retryable error — `HTTPStatusError` (BGE-M3 bug), unexpected errors
- Both cases should trigger graceful fallback. Catching `Exception` is correct here.

### Why not overload `cache_hit` on embedding failure?
- `cache_hit=True` on errors pollutes semantic cache metrics and downstream dashboards
- Explicit `embedding_error=True` keeps error and cache semantics separate
- `route_cache` can still short-circuit to `respond` with one extra condition and minimal code
- User behavior is unchanged (same graceful error message), observability quality is better

### Timeout rationale
| Component | Old | New | Why |
|-----------|-----|-----|-----|
| connect | 120s | 5s | TCP connect should be instant on local Docker network |
| read | 120s | 30s | BGE-M3 cold inference on CPU can take 5-15s; 30s is generous |
| write | 120s | 5s | Sending a short JSON payload |
| pool | N/A | 5s | Get connection from pool quickly |

### Future work (not in this PR)
- Apply same retry pattern to `ColbertRerankerService` (same vulnerability)
- Apply same retry pattern to `BGEM3Embeddings` and `BGEM3SparseEmbeddings` (legacy classes)
- Circuit breaker pattern if BGE-M3 is down for extended period (skip retries, fail fast)
- BGE-M3 API health endpoint for proactive checks
