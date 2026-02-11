# Re-Baseline Latency + Go/No-Go Gate — Implementation Plan

**Issue:** [#101](https://github.com/yastman/rag/issues/101) — perf: re-baseline latency & Go/No-Go gate after rewrite optimization
**Parent:** #97 | **Epic:** #58
**Milestone:** Gate: Re-Baseline
**Date:** 2026-02-11

## Goal

Запустить полный цикл валидации latency после оптимизаций Phase 1, зафиксировать baseline,
принять решение Go/No-Go для Phase 2.

## Prerequisites (MUST be closed before baseline)

Из roadmap (`docs/plans/2026-02-11-parallel-execution-roadmap.md`, строки 109-127):

| Stream | Issue | Title | Status |
|--------|-------|-------|--------|
| A | #124 | TTFT variance + provider metadata | MUST |
| A | #106a | BGE quick fix (prewarm/keep-warm) | MUST |
| B | #108 | Rewrite stop-guard | MUST |
| C | #103 | Cache hit scores + error spans | MUST |
| C | #123 | Orphan traces + propagate_attributes | MUST |
| D | #121 | Redis hardening | MUST |
| D | #122 | Qdrant timeout + FormulaQuery | MUST |

**Check command:**

    gh issue list --milestone "Gate: Re-Baseline" --state open --json number,title,state

Если хотя бы один MUST-issue открыт — baseline невалиден, отложить.

## Процедура

### Query Set

Используется `scripts/validate_queries.py` — `GDRIVE_BGE_QUERIES` (коллекция `gdrive_documents_bge`):
- 10 easy + 10 medium + 10 hard = **30 cold queries**
- 3 edge cases (manual) = **33 cold total**
- 10 cache-hit (повтор: 4 easy + 3 medium + 3 hard)
- 3 warmup (отбрасываются)

**Итого:** 3 warmup + 33 cold + 10 cache = **46 запросов** через pipeline.

Типы покрыты: SIMPLE, GENERAL, STRUCTURED (classify_node маппит → ENTITY/COMPLEX/FAQ).

### Фазы выполнения

1. **Warmup** (3 запроса) — прогрев connections, LLM, BGE-M3. Результаты отбрасываются.
2. **Flush Redis** — `_flush_redis_caches()` удаляет `embeddings:v3:*`, `sparse:v3:*`, `search:v3:*`, `analysis:v3:*`, `rerank:v3:*`, `conversation:*` + semantic cache.
3. **Cold run** (33 запроса) — true cold measurement без кешей.
4. **Cache-hit run** (10 запросов) — повтор для измерения cache path.
5. **Langfuse enrichment** — `enrich_results_from_langfuse()` дотягивает scores + node_spans_ms.
6. **Report generation** — markdown + JSON в `docs/reports/`.

## Go/No-Go Criteria

Из issue #101 + roadmap Gate 1:

| # | Condition | Target | Source |
|---|-----------|--------|--------|
| 1 | Cold p50 total | < 5s | roadmap |
| 2 | Cold p90 total (telegram-rag-query) | < 8s | issue #101 |
| 3 | Cold queries >10s | < 15% | issue #101 |
| 4 | Cache-hit p50 | < 1.5s | roadmap |
| 5 | p50 TTFT (generate node start) | < 2s | roadmap |
| 6 | rewrite calls >= 2 | <= 10% | issue #101 |
| 7 | rewrite-query completion_tokens p50 | <= 96 | issue #101 |
| 8 | ERROR observations | 0 new | issue #101 |
| 9 | Orphan traces | 0% | roadmap |

### Как проверить каждый критерий

**1-3: Latency** — из `aggregates["cold"]` в JSON-отчёте:
- `latency_p50`, `latency_p95` (p90 ≈ p95 при n=33)
- Считать `len([r for r in cold if r.latency_wall_ms > 10000]) / len(cold)`

**4: Cache-hit** — из `aggregates["cache_hit"]["latency_p50"]`

**5: TTFT** — из `node_p50["generate"]` (time to first token ≈ generate node start latency).
Если streaming enabled, нужно отдельно замерить TTFT из Langfuse observation.

**6-7: Rewrite** — из `aggregates["cold"]["rewrite_rate"]` и Langfuse scores.
`rewrite_count >= 2` означает двойной rewrite (после #108 guard это должно быть 0%).
`rewrite-query completion_tokens` — из Langfuse observation `node-rewrite` → usage.

**8: ERROR** — фильтр Langfuse observations с `level=ERROR` для run traces.

**9: Orphan traces** — после #123 fix, проверить через Langfuse API:
traces без `session_id` или без `propagate_attributes` metadata.

## Фиксация baseline trace IDs

После успешного run:

1. Сохранить `run_id` в issue #101 comment
2. Обновить `REFERENCE_TRACE_ID` в `scripts/validate_traces.py:48` на лучший cold trace
3. JSON-отчёт (`docs/reports/YYYY-MM-DD-validation-{run_id}.json`) содержит все `trace_id`
4. Прикрепить ссылку на Langfuse dashboard с фильтром `tags=["validation", run_id]`

## Contingency Path (если Go/No-Go = FAIL)

Trigger #102 (contingency A/B):
- **Contingency A:** Профилировать top-3 slowest nodes, точечные оптимизации
- **Contingency B:** Снизить quality (disable rerank, reduce top_k) для latency target
- Документировать какой критерий провалился и на сколько

## Шаги реализации

### Шаг 1: Preflight check (2 мин)

Проверить что все prerequisite issues закрыты:

    gh issue list --milestone "Gate: Re-Baseline" --state open

Проверить что Docker сервисы содержат ПОСЛЕДНИЙ код:

    docker compose --profile core --profile bot --profile ml ps

Файлы:
- Не требуется изменений

### Шаг 2: Rebuild + Deploy (5 мин)

Пересобрать bot, litellm, bge-m3 с последним кодом:

    docker compose build --no-cache bot litellm bge-m3
    docker compose --profile core --profile bot --profile ml up -d --wait --force-recreate

Подождать health checks (bot, redis, qdrant, litellm, bge-m3).

Файлы:
- Не требуется изменений

### Шаг 3: Добавить Go/No-Go автоматику в report (5 мин)

Файл: `scripts/validate_traces.py:653-660`

Заменить placeholder Go/No-Go секцию на автоматическую проверку критериев.
Добавить функцию `evaluate_go_no_go(aggregates, results) -> dict[str, bool]` которая:
- Проверяет cold_p50 < 5000, cold_p90 < 8000
- Считает % queries > 10s
- Проверяет cache_hit_p50 < 1500
- Проверяет rewrite_rate (count >= 2) <= 10%
- Возвращает dict с pass/fail по каждому критерию

Вывод в report: таблица с чекбоксами [x] pass / [ ] FAIL.

### Шаг 4: Добавить orphan trace check (3 мин)

Файл: `scripts/validate_traces.py` — новая функция после `enrich_results_from_langfuse()`

Добавить `check_orphan_traces(results) -> float` которая:
- Для каждого trace_id проверяет наличие `session_id` в Langfuse trace metadata
- Возвращает % orphan traces

Включить результат в Go/No-Go критерий #9.

### Шаг 5: Run validation (5 мин)

    make validate-traces

Или для fast mode (без rebuild):

    make validate-traces-fast

Скрипт выполнит 46 запросов, сгенерирует markdown + JSON report.

Файлы:
- Output: `docs/reports/YYYY-MM-DD-validation-{run_id}.md`
- Output: `docs/reports/YYYY-MM-DD-validation-{run_id}.json`

### Шаг 6: Review + Decision (3 мин)

1. Открыть markdown report
2. Проверить Go/No-Go таблицу
3. Если ALL pass:
   - Комментарий в #101 с ссылкой на report
   - Обновить `REFERENCE_TRACE_ID` в `scripts/validate_traces.py:48`
   - Закрыть #101
   - Закрыть #105 (parent)
   - Начать Phase 2: #106b (ONNX), #75 (astream), #74 (PostgresSaver)
4. Если ANY fail:
   - Комментарий в #101 с деталями провала
   - Открыть #102 (contingency) с конкретными метриками
   - НЕ закрывать #101

### Шаг 7: Commit report (2 мин)

    git add docs/reports/YYYY-MM-DD-validation-*.md
    git add docs/reports/YYYY-MM-DD-validation-*.json
    git add scripts/validate_traces.py  # если были изменения в шагах 3-4
    git commit -m "perf(baseline): re-baseline validation run [#101]"

## Effort Estimate

| Шаг | Время | Тип |
|-----|-------|-----|
| 1. Preflight | 2 мин | manual check |
| 2. Rebuild | 5 мин | docker build (tmux) |
| 3. Go/No-Go автоматика | 5 мин | code change |
| 4. Orphan trace check | 3 мин | code change |
| 5. Run validation | 5 мин | automated script |
| 6. Review + Decision | 3 мин | manual review |
| 7. Commit | 2 мин | git |
| **Total** | **~25 мин** | |

## Risks

- BGE-M3 cold start после rebuild может дать завышенный warmup — 3 warmup queries должны покрыть
- Langfuse API enrichment может быть медленным — 5s sleep уже есть в скрипте
- Если Qdrant collection `gdrive_documents_bge` не найдена — скрипт fallback на доступные
- p90 vs p95: при 33 queries разница минимальна, используем p95 как conservative estimate
