# P1: Langfuse Error Spans — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `level="ERROR"` spans to all fallback paths in LangGraph nodes so degraded queries are visible in Langfuse UI.

**Architecture:** Each node's `except` block calls `get_client().update_current_span(level="ERROR", status_message=str(exc))` before continuing with fallback logic. This marks the span as errored without breaking the pipeline.

**Tech Stack:** Langfuse Python SDK v3 (`get_client().update_current_span`), pytest

**Ref:** [Issue #103](https://github.com/yastman/rag/issues/103) | Commit 69c2863 (P1.1 done)

---

## Состояние: что уже сделано

Commit `69c2863` закрыл **P1.1 (Cache Hit Tracking)**:

| Элемент | Статус | Файл |
|---------|--------|------|
| `embeddings_cache_hit` в RAGState | ✅ Done | `graph/state.py` |
| `search_cache_hit` в RAGState | ✅ Done | `graph/state.py` |
| `embeddings_cache_hit` в cache_check_node | ✅ Done | `graph/nodes/cache.py` |
| `search_cache_hit` в retrieve_node | ✅ Done | `graph/nodes/retrieve.py` |
| Real scores в `_write_langfuse_scores` | ✅ Done | `bot.py` |
| `confidence_score` из `grade_confidence` | ✅ Done | `bot.py` |
| Тест `test_real_scores_from_state` | ✅ Done | `test_bot_handlers.py` |

## Что осталось: P1.2 (Error Span Tracking)

4 узла имеют fallback-пути где ошибка маскируется — Langfuse показывает "success":

| Node | File:Line | Error scenario | Fallback |
|------|-----------|----------------|----------|
| `generate_node` | `generate.py:301` | LLM call failure | Document summary |
| `rewrite_node` | `rewrite.py:79` | LLM rewrite failure | Keep original query |
| `rerank_node` | `rerank.py:79` | ColBERT failure | Score-based sort |
| `respond_node` | `respond.py:49` | Telegram send failure (both Markdown+plain) | Silent drop |

## Scores ещё не отслеживаемые (вне скоупа)

| Score | Значение | Почему |
|-------|----------|--------|
| `rerank_cache_hit` | `0.0` | Rerank cache не реализован |
| `hyde_used` | `0.0` | HyDE не включён в pipeline |

Эти будут реализованы когда появятся соответствующие фичи.

---

## Task 1: Error span в generate_node

**Files:**
- Modify: `telegram_bot/graph/nodes/generate.py:301` (outer except block)
- Test: `tests/unit/graph/test_generate_node.py`

**Step 1: Write the failing test**

```python
# В class TestGenerateNode в test_generate_node.py
@pytest.mark.asyncio
async def test_error_span_on_llm_failure(self) -> None:
    """generate_node marks Langfuse span as ERROR when LLM fails."""
    from telegram_bot.graph.nodes.generate import generate_node

    mock_config, mock_client = _make_mock_config()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("LLM down"))

    state = _make_state_with_docs()

    with (
        patch("telegram_bot.graph.nodes.generate._get_config", return_value=mock_config),
        patch("telegram_bot.graph.nodes.generate.get_client") as mock_get_client,
    ):
        mock_lf = MagicMock()
        mock_get_client.return_value = mock_lf
        result = await generate_node(state)

    # Fallback response still produced
    assert result["response"] != ""
    # Error span recorded
    mock_lf.update_current_span.assert_called_once_with(
        level="ERROR",
        status_message="LLM down",
    )
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/graph/test_generate_node.py::TestGenerateNode::test_error_span_on_llm_failure -v`
Expected: FAIL — `get_client` not called / `update_current_span` not called

**Step 3: Write minimal implementation**

In `telegram_bot/graph/nodes/generate.py`, add import and error span:

```python
# Add to imports (line 21, after observe import):
from telegram_bot.observability import get_client, observe

# Replace the outer except block (line 301-303):
    except Exception as exc:
        logger.exception("generate_node: LLM call failed, using fallback")
        get_client().update_current_span(level="ERROR", status_message=str(exc))
        answer = _build_fallback_response(documents)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/graph/test_generate_node.py::TestGenerateNode::test_error_span_on_llm_failure -v`
Expected: PASS

**Step 5: Commit**

```bash
git add telegram_bot/graph/nodes/generate.py tests/unit/graph/test_generate_node.py
git commit -m "feat(observability): add error span to generate_node fallback path

Refs #103"
```

---

## Task 2: Error span в rewrite_node

**Files:**
- Modify: `telegram_bot/graph/nodes/rewrite.py:79`
- Test: `tests/unit/graph/test_agentic_nodes.py`

**Step 1: Write the failing test**

```python
# В class TestRewriteNode в test_agentic_nodes.py
@pytest.mark.asyncio
async def test_error_span_on_llm_failure(self):
    """rewrite_node marks Langfuse span as ERROR when LLM fails."""
    from telegram_bot.graph.nodes.rewrite import rewrite_node

    state = make_initial_state(user_id=1, session_id="s", query="original query")

    mock_llm = MagicMock()
    mock_llm.chat.completions.create = AsyncMock(side_effect=RuntimeError("LLM unavailable"))

    with patch("telegram_bot.graph.nodes.rewrite.get_client") as mock_get_client:
        mock_lf = MagicMock()
        mock_get_client.return_value = mock_lf
        result = await rewrite_node(state, llm=mock_llm)

    # Original query preserved
    assert result["messages"][0].content == "original query"
    assert result["rewrite_effective"] is False
    # Error span recorded
    mock_lf.update_current_span.assert_called_once_with(
        level="ERROR",
        status_message="LLM unavailable",
    )
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/graph/test_agentic_nodes.py::TestRewriteNode::test_error_span_on_llm_failure -v`
Expected: FAIL

**Step 3: Write minimal implementation**

In `telegram_bot/graph/nodes/rewrite.py`:

```python
# Add to imports (line 16, after observe):
from telegram_bot.observability import get_client, observe

# Replace except block (line 79-82):
    except Exception as exc:
        logger.exception("rewrite_node: LLM rewrite failed, keeping original query")
        get_client().update_current_span(level="ERROR", status_message=str(exc))
        rewritten = original_query
        effective = False
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/graph/test_agentic_nodes.py::TestRewriteNode::test_error_span_on_llm_failure -v`
Expected: PASS

**Step 5: Commit**

```bash
git add telegram_bot/graph/nodes/rewrite.py tests/unit/graph/test_agentic_nodes.py
git commit -m "feat(observability): add error span to rewrite_node fallback path

Refs #103"
```

---

## Task 3: Error span в rerank_node

**Files:**
- Modify: `telegram_bot/graph/nodes/rerank.py:79`
- Test: `tests/unit/graph/test_agentic_nodes.py`

**Step 1: Write the failing test**

```python
# В class TestRerankNode в test_agentic_nodes.py
@pytest.mark.asyncio
async def test_error_span_on_colbert_failure(self):
    """rerank_node marks Langfuse span as ERROR when ColBERT fails."""
    from telegram_bot.graph.nodes.rerank import rerank_node

    state = make_initial_state(user_id=1, session_id="s", query="test")
    state["documents"] = [
        {"text": "A", "score": 0.2},
        {"text": "B", "score": 0.8},
    ]

    mock_reranker = AsyncMock()
    mock_reranker.rerank.side_effect = RuntimeError("ColBERT unavailable")

    with patch("telegram_bot.graph.nodes.rerank.get_client") as mock_get_client:
        mock_lf = MagicMock()
        mock_get_client.return_value = mock_lf
        result = await rerank_node(state, reranker=mock_reranker, top_k=2)

    # Fallback still works
    assert result["rerank_applied"] is False
    assert result["documents"][0]["text"] == "B"
    # Error span recorded
    mock_lf.update_current_span.assert_called_once_with(
        level="ERROR",
        status_message="ColBERT unavailable",
    )
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/graph/test_agentic_nodes.py::TestRerankNode::test_error_span_on_colbert_failure -v`
Expected: FAIL

**Step 3: Write minimal implementation**

In `telegram_bot/graph/nodes/rerank.py`:

```python
# Add to imports (line 12, after observe):
from telegram_bot.observability import get_client, observe

# Replace except block (line 79-80):
        except Exception as exc:
            logger.exception("rerank: ColBERT failed, falling back to score sort")
            get_client().update_current_span(level="ERROR", status_message=str(exc))
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/graph/test_agentic_nodes.py::TestRerankNode::test_error_span_on_colbert_failure -v`
Expected: PASS

**Step 5: Commit**

```bash
git add telegram_bot/graph/nodes/rerank.py tests/unit/graph/test_agentic_nodes.py
git commit -m "feat(observability): add error span to rerank_node fallback path

Refs #103"
```

---

## Task 4: Error span в respond_node

**Files:**
- Modify: `telegram_bot/graph/nodes/respond.py:49`
- Test: `tests/unit/graph/test_respond_node.py`

**Step 1: Write the failing test**

```python
# В class TestRespondNode в test_respond_node.py
async def test_error_span_on_send_failure(self):
    """respond_node marks Langfuse span as ERROR when Telegram send fails completely."""
    from unittest.mock import MagicMock, patch

    message = AsyncMock()
    # Both Markdown and plain text fail
    message.answer.side_effect = [Exception("Markdown failed"), Exception("Plain failed")]

    state = make_initial_state(user_id=1, session_id="s", query="test")
    state["response"] = "answer"
    state["message"] = message

    with patch("telegram_bot.graph.nodes.respond.get_client") as mock_get_client:
        mock_lf = MagicMock()
        mock_get_client.return_value = mock_lf
        result = await respond_node(state)

    assert "respond" in result["latency_stages"]
    # Error span recorded for complete failure
    mock_lf.update_current_span.assert_called_once()
    call_kwargs = mock_lf.update_current_span.call_args.kwargs
    assert call_kwargs["level"] == "ERROR"
    assert "Plain failed" in call_kwargs["status_message"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/graph/test_respond_node.py::TestRespondNode::test_error_span_on_send_failure -v`
Expected: FAIL

**Step 3: Write minimal implementation**

In `telegram_bot/graph/nodes/respond.py`:

```python
# Add to imports (line 12, after observe):
from telegram_bot.observability import get_client, observe

# Replace the inner except block (line 48-50):
            except Exception as exc:
                logger.exception("Failed to send response")
                get_client().update_current_span(
                    level="ERROR", status_message=str(exc)
                )
```

Важно: error span ставится только на полный провал отправки (обе попытки — Markdown + plain text). Markdown fallback — это нормальное поведение, не ошибка.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/graph/test_respond_node.py::TestRespondNode::test_error_span_on_send_failure -v`
Expected: PASS

**Step 5: Commit**

```bash
git add telegram_bot/graph/nodes/respond.py tests/unit/graph/test_respond_node.py
git commit -m "feat(observability): add error span to respond_node failure path

Refs #103"
```

---

## Task 5: Run full test suite + lint

**Step 1: Run lint**

Run: `make check`
Expected: PASS

**Step 2: Run affected tests**

Run: `uv run pytest tests/unit/graph/test_generate_node.py tests/unit/graph/test_agentic_nodes.py tests/unit/graph/test_respond_node.py -v`
Expected: All pass (existing + 4 new)

**Step 3: Final commit (if any fixes needed)**

---

## Exit Criteria

- [ ] Error span (`level="ERROR"`) в generate_node при LLM failure
- [ ] Error span в rewrite_node при LLM rewrite failure
- [ ] Error span в rerank_node при ColBERT failure
- [ ] Error span в respond_node при полном провале Telegram send
- [ ] 4 новых теста проходят
- [ ] `make check` clean
- [ ] Existing tests не сломаны
