# Langfuse Real Scores + Error Spans -- Implementation Plan

**Goal:** Finish issue #103 -- add error spans (level=ERROR) to 4 LangGraph nodes (generate, rewrite, rerank, respond) so that degraded/fallback queries are visible in Langfuse UI.

**Issue:** https://github.com/yastman/rag/issues/103

**Status:** P1.1 (cache hit scores) DONE (commit 69c2863). Осталась только P1.2 (error spans).

## Текущее состояние: 12 scores

| # | Score | Source | Статус |
|---|-------|--------|--------|
| 1 | `query_type` | `_QUERY_TYPE_SCORE` mapping | REAL |
| 2 | `latency_total_ms` | `pipeline_wall_ms` (perf_counter) | REAL |
| 3 | `semantic_cache_hit` | `state["cache_hit"]` | REAL |
| 4 | `embeddings_cache_hit` | `state["embeddings_cache_hit"]` | REAL (P1.1) |
| 5 | `search_cache_hit` | `state["search_cache_hit"]` | REAL (P1.1) |
| 6 | `rerank_applied` | `state["rerank_applied"]` | REAL |
| 7 | `rerank_cache_hit` | hardcoded `0.0` | Out of scope (нет rerank cache) |
| 8 | `results_count` | `state["search_results_count"]` | REAL |
| 9 | `no_results` | `search_results_count == 0` | REAL |
| 10 | `llm_used` | `"generate" in latency_stages` | REAL |
| 11 | `confidence_score` | `state["grade_confidence"]` | REAL (P1.1) |
| 12 | `hyde_used` | hardcoded `0.0` | Out of scope (HyDE не включён) |

**Итого:** 10/12 real. 2 hardcoded by design (фича не реализована). Scores -- DONE.

## P1.2: Error Span Tracking

### Langfuse SDK Pattern

Langfuse v3 Python SDK поддерживает `level` и `status_message` для spans:

    from langfuse import get_client

    @observe(name="node-generate")
    async def generate_node(state):
        try:
            ...
        except Exception as e:
            lf = get_client()
            lf.update_current_span(
                level="ERROR",
                status_message=str(e)[:500]
            )
            raise  # или fallback

Уровни: `DEBUG`, `DEFAULT`, `WARNING`, `ERROR`.

В Langfuse UI: можно фильтровать spans по `level=ERROR` для поиска деградированных запросов.

### Шаг 1: generate_node -- error span на LLM failure (3 мин)

**Файл:** `telegram_bot/graph/nodes/generate.py:301-303`

**Текущий код (строки 301-303):**

    except Exception:
        logger.exception("generate_node: LLM call failed, using fallback")
        answer = _build_fallback_response(documents)

**Изменение:** добавить `update_current_span(level="ERROR")` перед fallback:

    except Exception as e:
        logger.exception("generate_node: LLM call failed, using fallback")
        from telegram_bot.observability import get_client
        get_client().update_current_span(
            level="ERROR",
            status_message=f"LLM failed: {str(e)[:200]}"
        )
        answer = _build_fallback_response(documents)

**Примечание:** import `get_client` уже есть в файле через `from telegram_bot.observability import observe` -- нужно добавить `get_client` в import. Проверить: строка 20 (`from telegram_bot.observability import observe`).

**Также:** строки 280-281 (streaming fallback) -- добавить WARNING:

    except Exception:
        logger.warning("Streaming failed, falling back to non-streaming", exc_info=True)
        get_client().update_current_span(
            level="WARNING",
            status_message="Streaming failed, using non-streaming fallback"
        )

### Шаг 2: rewrite_node -- error span на LLM rewrite failure (3 мин)

**Файл:** `telegram_bot/graph/nodes/rewrite.py:79-82`

**Текущий код (строки 79-82):**

    except Exception:
        logger.exception("rewrite_node: LLM rewrite failed, keeping original query")
        rewritten = original_query
        effective = False

**Изменение:**

    except Exception as e:
        logger.exception("rewrite_node: LLM rewrite failed, keeping original query")
        from telegram_bot.observability import get_client
        get_client().update_current_span(
            level="ERROR",
            status_message=f"Rewrite LLM failed: {str(e)[:200]}"
        )
        rewritten = original_query
        effective = False

**Примечание:** import `get_client` нужно добавить. Строка 15: `from telegram_bot.observability import observe` -- добавить `get_client`.

### Шаг 3: rerank_node -- error span на ColBERT failure (3 мин)

**Файл:** `telegram_bot/graph/nodes/rerank.py:79-80`

**Текущий код (строки 79-80):**

    except Exception:
        logger.exception("rerank: ColBERT failed, falling back to score sort")

**Изменение:**

    except Exception as e:
        logger.exception("rerank: ColBERT failed, falling back to score sort")
        from telegram_bot.observability import get_client
        get_client().update_current_span(
            level="ERROR",
            status_message=f"ColBERT rerank failed: {str(e)[:200]}"
        )

**Примечание:** import `get_client` нужно добавить. Строка 14: `from telegram_bot.observability import observe` -- добавить `get_client`.

### Шаг 4: respond_node -- error span на Telegram send failure (3 мин)

**Файл:** `telegram_bot/graph/nodes/respond.py:49-50`

**Текущий код (строки 49-50):**

    except Exception:
        logger.exception("Failed to send response")

**Изменение:**

    except Exception as e:
        logger.exception("Failed to send response")
        from telegram_bot.observability import get_client
        get_client().update_current_span(
            level="ERROR",
            status_message=f"Telegram send failed: {str(e)[:200]}"
        )

**Примечание:** import `get_client` нужно добавить. Строка 12: `from telegram_bot.observability import observe` -- добавить `get_client`.

### Шаг 5: Unit тесты для error spans (5 мин)

**Файл:** `tests/unit/graph/test_error_spans.py` (новый)

4 теста -- по одному на каждый node:

1. **test_generate_node_llm_error_sets_error_span** -- mock LLM raise Exception, verify `update_current_span(level="ERROR", ...)` called
2. **test_rewrite_node_llm_error_sets_error_span** -- mock LLM raise Exception, verify error span
3. **test_rerank_node_colbert_error_sets_error_span** -- mock reranker raise Exception, verify error span
4. **test_respond_node_send_error_sets_error_span** -- mock message.answer raise Exception, verify error span

**Паттерн теста:**

    @pytest.fixture
    def mock_langfuse(monkeypatch):
        mock_client = MagicMock()
        monkeypatch.setattr(
            "telegram_bot.graph.nodes.generate.get_client",
            lambda: mock_client
        )
        return mock_client

    async def test_generate_node_llm_error_sets_error_span(mock_langfuse):
        # ... setup state, mock LLM to raise ...
        result = await generate_node(state)
        mock_langfuse.update_current_span.assert_called_once()
        call_kwargs = mock_langfuse.update_current_span.call_args.kwargs
        assert call_kwargs["level"] == "ERROR"
        assert "LLM failed" in call_kwargs["status_message"]

### Шаг 6: make check + make test-unit (2 мин)

    make check          # ruff + mypy
    make test-unit      # все тесты

## Test Strategy

| Файл | Тесты | Покрытие |
|------|-------|----------|
| `tests/unit/graph/test_error_spans.py` | 4 новых | generate, rewrite, rerank, respond error paths |
| `tests/unit/test_bot_handlers.py` | existing | scores (уже проходят) |
| `tests/integration/test_graph_paths.py` | existing | graph paths (не меняются) |

## Acceptance Criteria

1. 10/12 scores real (2 hardcoded by design -- `rerank_cache_hit`, `hyde_used`)
2. Error spans visible в Langfuse UI для fallback paths (4 nodes)
3. 4 новых error span теста проходят
4. `make check` clean
5. Post-deploy: Langfuse UI filter `level=ERROR` показывает degraded queries

## Effort Estimate

**Size:** S (small)
**Время:** ~20 минут

| Шаг | Время |
|------|-------|
| generate_node error span | 3 мин |
| rewrite_node error span | 3 мин |
| rerank_node error span | 3 мин |
| respond_node error span | 3 мин |
| Unit тесты (4 теста) | 5 мин |
| make check + test | 2 мин |

## Риски

- **Нет:** `_NullLangfuseClient` уже имеет `update_current_span` stub (observability.py:68) -- no-op когда Langfuse disabled
- **Нет:** import не сломает circular -- `get_client` top-level import из observability.py
- **Минимальный:** `str(e)[:200]` может содержать PII -- `mask_pii` применяется на уровне Langfuse client, не здесь

## Файлы для изменения

| Файл | Изменение |
|------|-----------|
| `telegram_bot/graph/nodes/generate.py` | +import get_client, +error span в except (строки 20, 280, 301) |
| `telegram_bot/graph/nodes/rewrite.py` | +import get_client, +error span в except (строки 15, 79) |
| `telegram_bot/graph/nodes/rerank.py` | +import get_client, +error span в except (строки 14, 79) |
| `telegram_bot/graph/nodes/respond.py` | +import get_client, +error span в except (строки 12, 49) |
| `tests/unit/graph/test_error_spans.py` | Новый: 4 теста |
