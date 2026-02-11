# Payload Bloat + TTFT Rename Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce Langfuse node payload bloat by 80%+ and rename TTFT criterion to honest semantics.

**Architecture:** Disable auto-capture on 5 heavy LangGraph nodes (`@observe(capture_input=False, capture_output=False)`), replace with curated metadata via `get_client().update_current_span()` (no full state, documents, or embeddings in spans). Rename `ttft_p50_lt_2s` → `generate_p50_lt_2s` in validation Go/No-Go and add a report footnote clarifying this is full generation latency in non-streaming mode.

**Tech Stack:** Python 3.12, Langfuse SDK v3 (`@observe`, `get_client`), pytest, hashlib

**Issue:** [#143](https://github.com/yastman/rag/issues/143)
**Design:** `docs/plans/2026-02-11-payload-bloat-ttft-design.md`

---

### Task 1: Write failing tests for heavy node auto-capture flags

**Files:**
- Create: `tests/unit/graph/test_observe_payloads.py`

**Step 1: Write the test file**

```python
"""Tests: heavy nodes disable @observe auto-capture, curated span has no heavy fields."""

from __future__ import annotations

import hashlib
import importlib
import sys
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Test 1: Heavy nodes use capture_input=False, capture_output=False
# ---------------------------------------------------------------------------


class TestHeavyNodesDisableAutoCapture:
    """Verify @observe(capture_input=False, capture_output=False) on heavy nodes."""

    @pytest.fixture(autouse=True)
    def _patch_observe(self):
        """Mock observe decorator before importing node modules.

        Replaces telegram_bot.observability.observe with a mock that records
        the kwargs passed to @observe(...) and returns the original function.
        """
        self.observe_calls: dict[str, dict] = {}
        original_modules: dict[str, object] = {}

        # Remove cached node modules so re-import picks up our mock
        node_modules = [
            "telegram_bot.graph.nodes.retrieve",
            "telegram_bot.graph.nodes.generate",
            "telegram_bot.graph.nodes.cache",
        ]
        for mod in node_modules:
            if mod in sys.modules:
                original_modules[mod] = sys.modules.pop(mod)

        def fake_observe(**kwargs):
            def decorator(func):
                self.observe_calls[kwargs.get("name", func.__name__)] = kwargs
                return func
            return decorator

        with patch("telegram_bot.observability.observe", side_effect=fake_observe):
            # Force re-import with our mocked observe
            for mod in node_modules:
                importlib.import_module(mod)
            yield

        # Restore original modules
        for mod in node_modules:
            sys.modules.pop(mod, None)
        for mod, original in original_modules.items():
            sys.modules[mod] = original  # type: ignore[assignment]

    def test_retrieve_node_disables_auto_capture(self):
        kwargs = self.observe_calls.get("node-retrieve", {})
        assert kwargs.get("capture_input") is False, "node-retrieve must set capture_input=False"
        assert kwargs.get("capture_output") is False, "node-retrieve must set capture_output=False"

    def test_generate_node_disables_auto_capture(self):
        kwargs = self.observe_calls.get("node-generate", {})
        assert kwargs.get("capture_input") is False, "node-generate must set capture_input=False"
        assert kwargs.get("capture_output") is False, "node-generate must set capture_output=False"

    def test_cache_check_node_disables_auto_capture(self):
        kwargs = self.observe_calls.get("node-cache-check", {})
        assert kwargs.get("capture_input") is False, "node-cache-check must set capture_input=False"
        assert kwargs.get("capture_output") is False, "node-cache-check must set capture_output=False"

    def test_cache_store_node_disables_auto_capture(self):
        kwargs = self.observe_calls.get("node-cache-store", {})
        assert kwargs.get("capture_input") is False, "node-cache-store must set capture_input=False"
        assert kwargs.get("capture_output") is False, "node-cache-store must set capture_output=False"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/graph/test_observe_payloads.py::TestHeavyNodesDisableAutoCapture -v`
Expected: FAIL — `capture_input` is not in kwargs (current decorators don't pass these)

**Step 3: Commit failing tests**

```bash
git add tests/unit/graph/test_observe_payloads.py
git commit -m "test(observability): add failing tests for heavy node auto-capture flags #143"
```

---

### Task 2: Write failing tests for curated span payloads (no heavy fields)

**Files:**
- Modify: `tests/unit/graph/test_observe_payloads.py`

**Step 1: Add curated payload tests to the same file**

Append after `TestHeavyNodesDisableAutoCapture`:

```python
# ---------------------------------------------------------------------------
# Test 2: Curated span payloads contain no heavy fields
# ---------------------------------------------------------------------------

# Forbidden keys — these must NEVER appear in update_current_span input/output
_FORBIDDEN_KEYS = {"documents", "query_embedding", "sparse_embedding", "state", "messages"}


def _extract_span_payloads(mock_lf_client: MagicMock) -> list[dict]:
    """Collect all input/output dicts from update_current_span calls."""
    payloads: list[dict] = []
    for c in mock_lf_client.update_current_span.call_args_list:
        kwargs = c.kwargs if c.kwargs else {}
        if "input" in kwargs and isinstance(kwargs["input"], dict):
            payloads.append(kwargs["input"])
        if "output" in kwargs and isinstance(kwargs["output"], dict):
            payloads.append(kwargs["output"])
    return payloads


def _assert_no_forbidden_keys(payloads: list[dict], node_name: str) -> None:
    """Assert none of the payloads contain forbidden heavy keys."""
    for payload in payloads:
        for key in _FORBIDDEN_KEYS:
            assert key not in payload, (
                f"{node_name}: update_current_span must not contain '{key}', "
                f"found in payload keys: {list(payload.keys())}"
            )


class TestCuratedSpanPayloads:
    """Verify update_current_span calls contain only curated metadata."""

    @pytest.mark.asyncio
    async def test_retrieve_node_curated_payload(self):
        from telegram_bot.graph.nodes.retrieve import retrieve_node
        from telegram_bot.graph.state import make_initial_state

        state = make_initial_state(user_id=1, session_id="s1", query="test query text")
        state["query_type"] = "GENERAL"
        state["query_embedding"] = [0.1] * 1024

        docs = [
            {"id": "1", "text": "Doc content " * 100, "score": 0.9, "metadata": {}},
            {"id": "2", "text": "More content " * 100, "score": 0.7, "metadata": {}},
        ]
        ok_meta = {"backend_error": False, "error_type": None, "error_message": None}

        cache = AsyncMock()
        cache.get_search_results = AsyncMock(return_value=None)
        cache.get_sparse_embedding = AsyncMock(return_value=None)
        cache.store_sparse_embedding = AsyncMock()
        cache.store_search_results = AsyncMock()

        sparse = AsyncMock()
        sparse.aembed_query = AsyncMock(return_value={"indices": [1], "values": [0.5]})

        qdrant = AsyncMock()
        qdrant.hybrid_search_rrf = AsyncMock(return_value=(docs, ok_meta))

        mock_lf = MagicMock()
        with patch("telegram_bot.graph.nodes.retrieve.get_client", return_value=mock_lf):
            await retrieve_node(state, cache=cache, sparse_embeddings=sparse, qdrant=qdrant)

        payloads = _extract_span_payloads(mock_lf)
        assert len(payloads) >= 2, "retrieve_node must call update_current_span for input and output"
        _assert_no_forbidden_keys(payloads, "node-retrieve")

        # Verify expected curated keys exist in input
        input_payload = payloads[0]
        assert "query_preview" in input_payload
        assert len(input_payload["query_preview"]) <= 120
        assert "query_hash" in input_payload
        assert len(input_payload["query_hash"]) == 8

    @pytest.mark.asyncio
    async def test_generate_node_curated_payload(self):
        from unittest.mock import patch as _patch

        from telegram_bot.graph.nodes.generate import generate_node
        from telegram_bot.graph.state import make_initial_state

        state = make_initial_state(user_id=1, session_id="s1", query="test query")
        state["query_type"] = "GENERAL"
        state["documents"] = [
            {"text": "Large doc " * 200, "score": 0.9, "metadata": {"title": "Test"}},
        ]

        mock_choice = MagicMock()
        mock_choice.message.content = "Answer."
        mock_response = MagicMock(choices=[mock_choice])
        mock_response.model = "gpt-4o-mini"

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        mock_config = MagicMock()
        mock_config.domain = "test"
        mock_config.llm_model = "gpt-4o-mini"
        mock_config.llm_temperature = 0.7
        mock_config.generate_max_tokens = 2048
        mock_config.streaming_enabled = False
        mock_config.create_llm.return_value = mock_client

        mock_lf = MagicMock()
        with (
            _patch("telegram_bot.graph.nodes.generate._get_config", return_value=mock_config),
            _patch("telegram_bot.graph.nodes.generate.get_client", return_value=mock_lf),
        ):
            await generate_node(state)

        payloads = _extract_span_payloads(mock_lf)
        assert len(payloads) >= 2, "generate_node must call update_current_span for input and output"
        _assert_no_forbidden_keys(payloads, "node-generate")
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/graph/test_observe_payloads.py::TestCuratedSpanPayloads -v`
Expected: FAIL — nodes don't call `update_current_span` yet (or `get_client` not imported in retrieve)

**Step 3: Commit**

```bash
git add tests/unit/graph/test_observe_payloads.py
git commit -m "test(observability): add failing tests for curated span payloads #143"
```

---

### Task 3: Write failing test for TTFT criterion rename

**Files:**
- Modify: `tests/unit/test_validate_aggregates.py`

**Step 1: Add test to existing file**

Append to `TestEvaluateGoNoGo` class in `tests/unit/test_validate_aggregates.py`:

```python
    def test_uses_generate_p50_key_not_ttft(self):
        """Go/No-Go must use 'generate_p50_lt_2s', not 'ttft_p50_lt_2s'."""
        aggregates = {
            "cold": {
                "latency_p50": 3000,
                "latency_p95": 5000,
                "node_p50": {"generate": 1500},
            },
            "cache_hit": {"latency_p50": 500},
        }
        results = [_make_result(phase="cold", latency=3000)]
        criteria = evaluate_go_no_go(aggregates, results, orphan_rate=0.0)

        assert "generate_p50_lt_2s" in criteria, "Criterion must be named 'generate_p50_lt_2s'"
        assert "ttft_p50_lt_2s" not in criteria, "Old 'ttft_p50_lt_2s' key must not exist"
        assert criteria["generate_p50_lt_2s"]["passed"] is True  # 1500 < 2000
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_validate_aggregates.py::TestEvaluateGoNoGo::test_uses_generate_p50_key_not_ttft -v`
Expected: FAIL — `generate_p50_lt_2s` not in criteria (still named `ttft_p50_lt_2s`)

**Step 3: Commit**

```bash
git add tests/unit/test_validate_aggregates.py
git commit -m "test(validation): add failing test for TTFT criterion rename #143"
```

---

### Task 4: Implement payload bloat fix for retrieve_node

**Files:**
- Modify: `telegram_bot/graph/nodes/retrieve.py:1-15,21`

**Step 1: Add hashlib import and update decorator**

At the top of `retrieve.py`, add `hashlib` to imports:

```python
import hashlib
```

Change the decorator on line 21:

```python
# Before:
@observe(name="node-retrieve")

# After:
@observe(name="node-retrieve", capture_input=False, capture_output=False)
```

**Step 2: Add `get_client` import**

Change line 15:

```python
# Before:
from telegram_bot.observability import observe

# After:
from telegram_bot.observability import get_client, observe
```

**Step 3: Harden query extraction from `messages` + add curated input span (after line 54)**

Replace direct `state["messages"][-1]` indexing with a safe extraction, then add span input metadata:

```python
    messages = state.get("messages") or []
    last_msg = messages[-1] if messages else {}
    query = (
        last_msg.content
        if hasattr(last_msg, "content")
        else (last_msg.get("content", "") if isinstance(last_msg, dict) else "")
    )

    # Curated span metadata (replaces auto-captured full state)
    lf = get_client()
    lf.update_current_span(input={
        "query_preview": query[:120],
        "query_len": len(query),
        "query_hash": hashlib.sha256(query.encode()).hexdigest()[:8],
        "query_type": state.get("query_type"),
        "top_k": top_k,
    })
```

**Step 4: Add curated output span in the search-cache-hit return (before `return` around line 99)**

In the cache-hit early return block (around line 99), insert before the `return`:

```python
        lf.update_current_span(output={
            "results_count": len(cached_results),
            "search_cache_hit": True,
            "duration_ms": round(latency * 1000, 1),
        })
```

**Step 5: Add curated output span in the main return (before the `return update` around line 149)**

Insert before `return update`:

```python
    scores = [d.get("score", 0) for d in results if isinstance(d, dict)]
    lf.update_current_span(output={
        "results_count": len(results),
        "top_score": round(scores[0], 4) if scores else None,
        "min_score": round(scores[-1], 4) if scores else None,
        "search_cache_hit": False,
        "retrieval_backend_error": search_meta.get("backend_error", False),
        "retrieval_error_type": search_meta.get("error_type"),
        "duration_ms": round(latency * 1000, 1),
    })
```

**Step 6: Run tests**

Run: `uv run pytest tests/unit/graph/test_observe_payloads.py::TestHeavyNodesDisableAutoCapture::test_retrieve_node_disables_auto_capture tests/unit/graph/test_observe_payloads.py::TestCuratedSpanPayloads::test_retrieve_node_curated_payload tests/unit/graph/test_retrieve_node.py -v`
Expected: All PASS

**Step 7: Commit**

```bash
git add telegram_bot/graph/nodes/retrieve.py
git commit -m "fix(observability): disable auto-capture on retrieve_node, add curated metadata #143"
```

---

### Task 5: Implement payload bloat fix for generate_node

**Files:**
- Modify: `telegram_bot/graph/nodes/generate.py:196,210-248,332-340`

**Step 1: Update decorator on line 196**

```python
# Before:
@observe(name="node-generate")

# After:
@observe(name="node-generate", capture_input=False, capture_output=False)
```

**Step 2: Add curated input span after state extraction (after line 248, before the `try`)**

Insert after `ttft_ms = 0.0` (line 248):

```python
    # Curated span metadata
    lf = get_client()
    lf.update_current_span(input={
        "query_preview": query[:120],
        "query_len": len(query),
        "query_hash": hashlib.sha256(query.encode()).hexdigest()[:8],
        "context_docs_count": len(documents),
        "streaming_enabled": bool(message is not None and config.streaming_enabled),
    })
```

Note: `get_client` is already imported in generate.py (line 20). Add `import hashlib` if missing.

**Step 3: Add curated output span before the final return (before `return` around line 333)**

Insert before the final `return {` block:

```python
    span_output = {
        "response_length": len(answer),
        "llm_provider_model": actual_model,
        "llm_ttft_ms": ttft_ms if ttft_ms > 0 else None,
        "llm_response_duration_ms": round(elapsed * 1000, 1),
        "fallback_used": actual_model == "fallback",
        "response_sent": response_sent,
    }
    if "response" in locals():
        usage = getattr(response, "usage", None)
        if usage is not None:
            span_output["token_usage"] = {
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
            }
    lf.update_current_span(output=span_output)
```

**Step 4: Run tests**

Run: `uv run pytest tests/unit/graph/test_observe_payloads.py::TestHeavyNodesDisableAutoCapture::test_generate_node_disables_auto_capture tests/unit/graph/test_observe_payloads.py::TestCuratedSpanPayloads::test_generate_node_curated_payload tests/unit/graph/test_generate_node.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add telegram_bot/graph/nodes/generate.py
git commit -m "fix(observability): disable auto-capture on generate_node, add curated metadata #143"
```

---

### Task 6: Implement payload bloat fix for cache nodes

**Files:**
- Modify: `telegram_bot/graph/nodes/cache.py:14,20,92`

**Step 1: Add imports**

Change line 14:

```python
# Before:
from telegram_bot.observability import observe

# After:
from telegram_bot.observability import get_client, observe
```

**Step 2: Update cache_check_node decorator (line 20)**

```python
# Before:
@observe(name="node-cache-check")

# After:
@observe(name="node-cache-check", capture_input=False, capture_output=False)
```

**Step 3: Harden query extraction from `messages` + add curated input span in cache_check_node (after line 42)**

Insert after `query_type = state.get("query_type", "GENERAL")`:

```python
    messages = state.get("messages") or []
    last_msg = messages[-1] if messages else {}
    query = (
        last_msg.content
        if hasattr(last_msg, "content")
        else (last_msg.get("content", "") if isinstance(last_msg, dict) else "")
    )

    lf = get_client()
    lf.update_current_span(input={
        "query_preview": query[:120],
        "query_len": len(query),
        "query_hash": hashlib.sha256(query.encode()).hexdigest()[:8],
        "query_type": query_type,
    })
```

**Step 4: Add curated output span in cache_check_node HIT path (before `return` around line 73)**

Insert before the hit-path `return`:

```python
        lf.update_current_span(output={
            "cache_hit": True,
            "embeddings_cache_hit": embeddings_cache_hit,
            "hit_layer": "semantic",
            "duration_ms": round(latency * 1000, 1),
        })
```

**Step 5: Add curated output span in cache_check_node MISS path (before `return` around line 83)**

Insert before the miss-path `return`:

```python
    lf.update_current_span(output={
        "cache_hit": False,
        "embeddings_cache_hit": embeddings_cache_hit,
        "hit_layer": "none",
        "duration_ms": round(latency * 1000, 1),
    })
```

**Step 6: Update cache_store_node decorator (line 92)**

```python
# Before:
@observe(name="node-cache-store")

# After:
@observe(name="node-cache-store", capture_input=False, capture_output=False)
```

**Step 7: Add curated input span in cache_store_node (after line 117, after `user_id` extraction)**

Insert after `user_id = state.get("user_id", 0)`:

```python
    lf = get_client()
    lf.update_current_span(input={
        "query_preview": query[:120],
        "query_len": len(query),
        "query_hash": hashlib.sha256(query.encode()).hexdigest()[:8],
        "response_length": len(response),
        "search_results_count": state.get("search_results_count", 0),
    })
```

**Step 8: Add curated output span in cache_store_node (before `return` at end)**

The current code has two paths: (1) `if response and embedding:` stores data, (2) falls through.

After the `if response and embedding:` block, before `return {"response": response}`:

```python
    latency = time.perf_counter() - start
    stored = bool(response and embedding)
    lf.update_current_span(output={
        "stored": stored,
        "stored_semantic": stored,
        "stored_conversation": stored,
        "duration_ms": round(latency * 1000, 1),
    })
```

Note: initialize `start = time.perf_counter()` near node start to keep duration semantics consistent.

**Step 9: Run tests**

Run: `uv run pytest tests/unit/graph/test_observe_payloads.py::TestHeavyNodesDisableAutoCapture::test_cache_check_node_disables_auto_capture tests/unit/graph/test_observe_payloads.py::TestHeavyNodesDisableAutoCapture::test_cache_store_node_disables_auto_capture tests/unit/graph/test_cache_nodes.py -v`
Expected: All PASS

**Step 10: Commit**

```bash
git add telegram_bot/graph/nodes/cache.py
git commit -m "fix(observability): disable auto-capture on cache nodes, add curated metadata #143"
```

---

### Task 7: Implement TTFT criterion rename

**Files:**
- Modify: `scripts/validate_traces.py:539-545`

**Step 1: Rename the criterion key and comment (no `note` field inside criteria dict)**

Change lines 539-545 from:

```python
    # 5. TTFT p50 (generate node start) < 2s
    generate_p50 = cold.get("node_p50", {}).get("generate", 99999)
    criteria["ttft_p50_lt_2s"] = {
        "target": "< 2000 ms",
        "actual": f"{generate_p50:.0f} ms",
        "passed": generate_p50 < 2000,
    }
```

To:

```python
    # 5. Generate node p50 < 2s (full generation latency, non-streaming mode)
    generate_p50 = cold.get("node_p50", {}).get("generate", 99999)
    criteria["generate_p50_lt_2s"] = {
        "target": "< 2000 ms",
        "actual": f"{generate_p50:.0f} ms",
        "passed": generate_p50 < 2000,
    }
```

**Step 2: Add report footnote clarifying metric semantics**

In `generate_report()` after the Go/No-Go criteria table, append:

```python
        lines.append(
            "_Note: `generate_p50_lt_2s` measures full generation latency in "
            "non-streaming validation mode; true TTFT requires a streaming phase._"
        )
        lines.append("")
```

This keeps the renderer stable and avoids changing criteria object shape.

**Step 3: Run tests**

Run: `uv run pytest tests/unit/test_validate_aggregates.py -v`
Expected: All PASS (including the new `test_uses_generate_p50_key_not_ttft`)

**Step 4: Commit**

```bash
git add scripts/validate_traces.py
git commit -m "fix(validation): rename ttft_p50_lt_2s → generate_p50_lt_2s for honest semantics #143"
```

---

### Task 8: Run full test suite and lint

**Files:** None (verification only)

**Step 1: Run linter**

Run: `uv run ruff check telegram_bot/graph/nodes/retrieve.py telegram_bot/graph/nodes/generate.py telegram_bot/graph/nodes/cache.py scripts/validate_traces.py tests/unit/graph/test_observe_payloads.py tests/unit/test_validate_aggregates.py`
Expected: No errors

**Step 2: Run formatter**

Run: `uv run ruff format telegram_bot/graph/nodes/retrieve.py telegram_bot/graph/nodes/generate.py telegram_bot/graph/nodes/cache.py tests/unit/graph/test_observe_payloads.py`
Expected: Files formatted (or already formatted)

**Step 3: Run type check on changed files**

Run: `uv run mypy telegram_bot/graph/nodes/retrieve.py telegram_bot/graph/nodes/generate.py telegram_bot/graph/nodes/cache.py --ignore-missing-imports`
Expected: No type errors

**Step 4: Run all related unit tests**

Run: `uv run pytest tests/unit/graph/test_observe_payloads.py tests/unit/graph/test_retrieve_node.py tests/unit/graph/test_generate_node.py tests/unit/graph/test_cache_nodes.py tests/unit/test_validate_aggregates.py -v`
Expected: All PASS

**Step 5: Run graph path integration tests (quick sanity)**

Run: `uv run pytest tests/integration/test_graph_paths.py -v`
Expected: All 6 PASS (~5s)

**Step 6: Commit lint/format fixes if any**

```bash
git add -u
git commit -m "style: format after payload bloat fix #143"
```

---

### Task 9: Create follow-up issue for streaming TTFT

**Files:** None (GitHub only)

**Step 1: Create follow-up issue linked as child/follow-up of #143**

Run:

```bash
gh issue create \
  --title "feat(validation): add streaming phase for real TTFT measurement" \
  --body "$(cat <<'EOF'
## Summary

Follow-up to #143. The `generate_p50_lt_2s` criterion measures full generation latency in non-streaming (headless) mode. For true TTFT measurement, validation needs a streaming phase.

## Proposed Approach

1. Add a `--streaming` flag to `validate_traces.py`
2. Inject a mock `message` object that records TTFT without Telegram delivery
3. Add `ttft_p50_lt_Xms` criterion using real streaming TTFT data
4. Run streaming phase after cold phase (subset of queries)

## Parent Issue

Parent: #143 (payload bloat + TTFT rename).
EOF
)" \
  --label "next"
```

Expected: Issue created successfully

**Step 2: Done — no commit needed**
