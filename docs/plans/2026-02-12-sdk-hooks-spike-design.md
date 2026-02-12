# SDK Hooks Spike — Design Document (Issue #162)

**Date:** 2026-02-12
**Author:** Claude Opus 4.6
**Status:** Draft
**Branch:** `chore/parallel-backlog/hooks-162`
**Related:** #159 (proxy approach), #143 (payload bloat prevention)

---

## Problem Statement

Текущий pipeline использует LangGraph StateGraph с AsyncRedisSaver для conversation persistence.
Каждый `graph.ainvoke()` вызов порождает несколько checkpoint операций:

1. **Load** — `aget_tuple()` загружает предыдущий state при входе
2. **Save** — `aput()` сохраняет state после каждого node execution
3. **Put writes** — `aput_writes()` сохраняет промежуточные writes (pending sends)

Для 10-node pipeline (classify -> cache_check -> retrieve -> grade -> rerank -> generate -> cache_store -> respond, плюс опционально transcribe и summarize) это означает 10-12 save операций + 1 load per invocation.

Нам нужны per-operation метрики (latency, success/failure) для:
- Идентификации bottlenecks (load vs save)
- Трендов деградации при росте checkpoint size
- Alerting при аномальных latency
- Корректного attribution overhead (вместо proxy)

---

## Current State: Proxy Approach (#159)

Файл: `telegram_bot/bot.py:47-55`

    def _compute_checkpointer_overhead_proxy_ms(result, ainvoke_wall_ms):
        stages_ms = sum(float(v) * 1000 for v in result.get("latency_stages", {}).values())
        return max(0.0, ainvoke_wall_ms - stages_ms)

**Как работает:**
- `ainvoke_wall_ms` = `time.perf_counter()` вокруг `graph.ainvoke()`
- `latency_stages` = dict с per-node timing (classify: 0.01s, retrieve: 0.5s, ...)
- Delta = wall_time - sum(stages) = proxy для checkpointer + orchestration overhead

**Проблемы:**
1. Delta включает LangGraph orchestration (edge routing, state merge) — не только checkpointer
2. Нет breakdown load vs save — один число на весь invocation
3. asyncio scheduling jitter и GC pauses искажают measurement
4. При streaming (generate_node) timing менее точный
5. Для summarize_node overhead не учитывается (summarize post-respond)

**Текущий Langfuse score:** `checkpointer_overhead_proxy_ms` (NUMERIC) — пишется в trace.

---

## Option 1: Upstream PR к langgraph-checkpoint-redis

### Что предлагается

Добавить callback/hook mechanism в BaseCheckpointSaver или в AsyncRedisSaver:

    class BaseCheckpointSaver:
        on_before_put: Optional[Callable] = None
        on_after_put: Optional[Callable] = None
        on_before_get: Optional[Callable] = None
        on_after_get: Optional[Callable] = None

### Feasibility

**Низкая.** Анализ показывает:

1. `BaseCheckpointSaver` определён в `langgraph-checkpoint` (core package, LangChain org).
   langgraph-checkpoint-redis — отдельный repo (`redis-developer/langgraph-redis`).
   Hook mechanism нужен в core, а не в Redis implementation.

2. **Нет прецедента:** ни один checkpoint saver (Postgres, MongoDB, SQLite, Redis) не имеет hooks.
   Ни одного issue/PR с запросом hooks не найдено в upstream repos.

3. **Архитектурный конфликт:** LangGraph runtime вызывает checkpointer methods напрямую
   (внутри `Pregel.ainvoke()`). Hooks нарушают принцип single-responsibility и могут
   замедлить hot path для всех пользователей.

4. **Timeline:** Upstream PR review cycle — недели/месяцы. Core team может отклонить
   из-за принципиальных возражений (observability не должна быть в checkpointer layer).

### Pros
- Чистое, стандартное решение
- Benefit для всего community
- Нет maintenance burden на нашей стороне

### Cons
- Практически нереализуемо в разумные сроки
- Может быть отклонено (architectural concerns)
- Зависимость от upstream release cycle
- Блокирует прогресс по #162

### Вердикт: NOT RECOMMENDED

---

## Option 2: AsyncShallowRedisSaver

### Что это

`AsyncShallowRedisSaver` — memory-optimized variant из langgraph-checkpoint-redis.
Хранит **только последний checkpoint** per thread (вместо полной истории).

Import: `from langgraph.checkpoint.redis.ashallow import AsyncShallowRedisSaver`

### Как уменьшает overhead

| Аспект | AsyncRedisSaver | AsyncShallowRedisSaver |
|--------|----------------|----------------------|
| Checkpoints per thread | All (unbounded) | 1 (latest only) |
| Storage growth | Linear with interactions | Constant |
| `alist()` result | All history | Single item |
| `aput()` | Insert new | Upsert (replace) |
| Cleanup | Manual / TTL | Automatic |

**langgraph-redis 0.1.0 benchmarks:**
- get_tuple: 2,950 ops/sec (0.34ms) — уже быстрее чем Postgres/MySQL
- put: 1,647 ops/sec (0.61ms)
- Shallow variant: ожидаемо ещё быстрее (меньше данных, нет cleanup overhead)

### Impact на наш pipeline

Текущий `create_redis_checkpointer()` с TTL 7 дней уже ограничивает retention.
Для chatbot use case (Bulgarian property, Ukrainian Criminal Code) полная checkpoint
history не используется — бот не делает time-travel или rollback.

SummarizationNode (langmem) работает с `messages` в state, не с checkpoint history.
Переход на shallow не сломает summarization.

### Migration Path

    # memory.py — одна строка
    from langgraph.checkpoint.redis.ashallow import AsyncShallowRedisSaver
    # вместо
    from langgraph.checkpoint.redis.aio import AsyncRedisSaver

API полностью совместим (same BaseCheckpointSaver interface).

### Pros
- Drop-in замена (1 import change)
- Уменьшает storage и latency
- Официально поддерживается (same repo)
- Нет coupling к internals

### Cons
- **Не решает основную задачу** — per-operation tracing. Overhead станет меньше,
  но мы всё равно не знаем latency каждой load/save операции.
- Потеря checkpoint history (невозможен rollback, хотя мы его не используем)
- Может маскировать проблемы (overhead маленький = незаметный = не мониторится)

### Вердикт: COMPLEMENTARY — хорошее независимое улучшение, но не решает #162

---

## Option 3: Custom Subclass + @observe Wrappers

### Что предлагается

Создать `InstrumentedAsyncRedisSaver` — subclass `AsyncRedisSaver` с Langfuse tracing
на каждой checkpoint операции.

### Implementation Sketch

    from langgraph.checkpoint.redis.aio import AsyncRedisSaver
    from telegram_bot.observability import observe, get_client
    import time

    class InstrumentedAsyncRedisSaver(AsyncRedisSaver):

        @observe(name="checkpoint-load", capture_input=False, capture_output=False)
        async def aget_tuple(self, config):
            t0 = time.perf_counter()
            result = await super().aget_tuple(config)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            lf = get_client()
            lf.update_current_span(
                output={"elapsed_ms": elapsed_ms, "found": result is not None}
            )
            return result

        @observe(name="checkpoint-save", capture_input=False, capture_output=False)
        async def aput(self, config, checkpoint, metadata, new_versions):
            t0 = time.perf_counter()
            result = await super().aput(config, checkpoint, metadata, new_versions)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            lf = get_client()
            lf.update_current_span(
                output={"elapsed_ms": elapsed_ms, "step": metadata.get("step")}
            )
            return result

        @observe(name="checkpoint-put-writes", capture_input=False, capture_output=False)
        async def aput_writes(self, config, writes, task_id, *args, **kwargs):
            t0 = time.perf_counter()
            result = await super().aput_writes(config, writes, task_id, *args, **kwargs)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            lf = get_client()
            lf.update_current_span(
                output={"elapsed_ms": elapsed_ms, "writes_count": len(writes)}
            )
            return result

### Langfuse Trace Tree (expected)

    telegram-rag-query (root)
      node-classify (0.01s)
        checkpoint-save (0.5ms)       <-- NEW
      node-cache-check (0.05s)
        checkpoint-save (0.4ms)       <-- NEW
      node-retrieve (0.5s)
        checkpoint-save (0.6ms)       <-- NEW
      ...
      checkpoint-load (0.3ms)         <-- NEW (at start of ainvoke)

### Coupling Risks

1. **Method signatures:** `aput`, `aget_tuple`, `aput_writes` — public API из BaseCheckpointSaver.
   Стабильны (не менялись с langgraph-checkpoint 2.0.24+). Риск breakage: **низкий**.

2. **Internal methods:** Мы НЕ override-им `_aload_pending_sends`, `_dump_checkpoint` и т.п.
   Только public interface. Community subclass (Issue #5074) override-ит internals — это
   рискованнее.

3. **langgraph-redis 0.1.0 breaking changes:** Storage format поменялся, но public API
   (`aput`, `aget_tuple`) сохранён. Наш subclass бы пережил upgrade.

4. **@observe context:** LangGraph runtime вызывает checkpointer methods из `Pregel.ainvoke()`.
   `@observe` использует `contextvars` — spans будут корректно вложены в parent trace,
   если `propagate_attributes` / `traced_pipeline` активны (а они есть в bot.py).

### Maintenance Burden

- При обновлении langgraph-checkpoint-redis: проверить что method signatures не изменились
- При обновлении Langfuse SDK: проверить @observe compatibility
- Estimated: 1-2 часа при каждом major version bump

### Performance Overhead

- `time.perf_counter()`: ~100ns per call (negligible)
- `@observe` decorator: создаёт Langfuse span (~50-100us), async, batched flush
- `get_client().update_current_span()`: in-memory, batched
- **Total overhead per operation: ~0.1-0.2ms** (при checkpoint ops 0.3-0.6ms это 20-50%)
- **Mitigation:** `capture_input=False, capture_output=False` исключает сериализацию state

### Conditional Enable

    # memory.py
    if LANGFUSE_ENABLED:
        from telegram_bot.integrations.instrumented_checkpointer import (
            InstrumentedAsyncRedisSaver,
        )
        # use InstrumentedAsyncRedisSaver instead of AsyncRedisSaver
    else:
        from langgraph.checkpoint.redis.aio import AsyncRedisSaver
        # use plain AsyncRedisSaver

Zero overhead when Langfuse is disabled — same pattern as observability.py.

### Pros
- Per-operation metrics (load, save, put_writes) с Langfuse integration
- Чистый subclass pattern — только public API override
- Conditional — zero overhead без Langfuse
- Уже есть community precedent (Issue #5074)
- Можно реализовать за 1 день

### Cons
- Tight coupling к AsyncRedisSaver (при switch на другой backend нужен новый subclass)
- 20-50% overhead per checkpoint operation при включённом Langfuse
- Maintenance при SDK updates (хотя public API стабилен)
- Не будет работать с MemorySaver fallback (нужен отдельный InstrumentedMemorySaver или skip)

### Вердикт: RECOMMENDED

---

## Recommendation

**Option 3 (Custom subclass + @observe)** — primary approach.
**Option 2 (AsyncShallowRedisSaver)** — complementary optimization (отдельный PR).

### Обоснование

1. Option 3 решает core problem (#162) — per-operation checkpoint metrics
2. Реализуемо за 1 день, без upstream зависимостей
3. Coupling risk приемлем — public API стабилен, есть community precedent
4. Conditional enable — zero cost без Langfuse
5. Option 2 (Shallow) ортогонален — можно сделать параллельно для уменьшения baseline overhead

### Комбинированная стратегия

    InstrumentedAsyncShallowRedisSaver(AsyncShallowRedisSaver):
        # @observe на aput, aget_tuple, aput_writes
        # Shallow для меньшего baseline overhead
        # @observe для visibility

Или: инструментировать любой subclass через mixin.

---

## Next Steps

1. **Создать Issue для implementation:**
   `feat(observability): InstrumentedAsyncRedisSaver with @observe checkpoint tracing`

2. **Implementation plan:**
   - `telegram_bot/integrations/instrumented_checkpointer.py` — InstrumentedAsyncRedisSaver
   - Update `memory.py` — conditional factory
   - Unit tests — mock Redis, verify @observe spans created
   - Integration test — verify Langfuse trace tree structure

3. **Отдельный PR для AsyncShallowRedisSaver:**
   `perf(memory): switch to AsyncShallowRedisSaver for chatbot use case`

4. **Deprecate proxy metric:**
   После внедрения Option 3, `checkpointer_overhead_proxy_ms` можно заменить
   агрегатом из checkpoint-load + checkpoint-save spans.

5. **Benchmark:**
   Сравнить latency с/без @observe wrappers, с/без Shallow variant.
   Acceptance criteria: overhead < 1ms per invocation.
