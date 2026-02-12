# SDK Hooks Spike — Research Plan (Issue #162)

**Date:** 2026-02-12
**Branch:** `chore/parallel-backlog/hooks-162`
**Context:** Deferred from #159 — SDK не предоставляет callback hooks для checkpoint load/save.

## Цель исследования

Определить лучший подход для получения per-operation метрик checkpoint load/save в LangGraph pipeline,
вместо текущего proxy-подхода (wall-time минус сумма stages).

## Текущее состояние (из #159)

- `bot.py:_compute_checkpointer_overhead_proxy_ms()` — вычисляет `ainvoke_wall_ms - sum(latency_stages)`.
- Проблема: proxy включает не только checkpointer, но и LangGraph orchestration overhead,
  GC pauses, asyncio scheduling jitter. Нет breakdown по отдельным операциям (load vs save vs put_writes).
- `integrations/memory.py` — использует `AsyncRedisSaver` из SDK напрямую, без кастомизации.
- Checkpointer передаётся в `build_graph(checkpointer=...)` -> `workflow.compile(checkpointer=...)`.

## Исследованные источники

### Context7 (LangGraph + langgraph-checkpoint-redis)

1. **BaseCheckpointSaver interface** — 4 основных метода + async варианты:
   - `put/aput` — сохранение checkpoint
   - `put_writes/aput_writes` — промежуточные записи (pending writes)
   - `get_tuple/aget_tuple` — загрузка checkpoint tuple
   - `list/alist` — список checkpoints
   - `delete_thread/adelete_thread` — удаление
   - **Нет hooks/callbacks/events.** Интерфейс чисто функциональный.

2. **AsyncRedisSaver** (`langgraph.checkpoint.redis.aio`):
   - Создаётся через `AsyncRedisSaver(redis_url=...)` или `.from_conn_string()`
   - Методы: `asetup()`, `aput()`, `aget_tuple()`, `alist()`, `adelete_thread()`
   - Внутренне использует RediSearch + RedisJSON
   - **Нет публичных hooks/events для instrumentation.**

3. **AsyncShallowRedisSaver** (`langgraph.checkpoint.redis.ashallow`):
   - Хранит только последний checkpoint per thread
   - Подходит для chatbot-сценариев (без полной истории)
   - Меньше данных = быстрее операции, меньше storage

4. **Custom subclass pattern** — уже применяется в community:
   - Issue #5074: `AlphaAsyncRedisSaver` — subclass для фикса `_aload_pending_sends`
   - Issue #1134: custom checkpointer с `put_writes` / `aput_writes`
   - Паттерн: override конкретных методов, вызов `super()`, добавление логики

### Exa (web search + code context)

5. **langgraph-redis 0.1.0** (Aug 2025) — major performance redesign:
   - Denormalized storage (inline channel values)
   - Sorted sets для write tracking
   - Aggressive pipelining (O(3) вместо O(n) round-trips)
   - **Benchmarks:** get_tuple 12.4x faster (0.34ms), list 31.6x faster (1.44ms)
   - **Нет упоминания hooks/instrumentation.**

6. **Upstream repo** (`redis-developer/langgraph-redis`):
   - 190 stars, MIT license, active maintenance
   - 1 open issue (на момент проверки)
   - Нет issues/PRs с тегами instrumentation/hooks/callbacks/tracing

7. **Langfuse + LangGraph integration:**
   - Langfuse `@observe` decorator — контекстный, thread-local
   - Существующие проблемы с multi-worker spans (Discussion #9236)
   - **Нет готового рецепта для checkpoint-level tracing**

## Три варианта для Design Doc

| # | Вариант | Feasibility | Risk |
|---|---------|-------------|------|
| 1 | Upstream PR (hooks в SDK) | Низкая (нет прецедента, медленный цикл) | Низкий |
| 2 | AsyncShallowRedisSaver | Средняя (drop-in замена, меньше overhead) | Средний (потеря истории) |
| 3 | Custom subclass + @observe | Высокая (уже есть community примеры) | Средний (coupling к internals) |

## Следующий шаг

Написать Design Doc с детальным анализом каждого варианта и рекомендацией.
