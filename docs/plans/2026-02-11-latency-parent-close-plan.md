# Latency Parent Issue Close — Implementation Plan

**Date:** 2026-02-11
**Issue:** [#105](https://github.com/yastman/rag/issues/105) — bug(latency): trace-driven fixes for rewrite loops + incorrect latency_total_ms
**Milestone:** Gate: Re-Baseline
**Effort:** S (trivial — это tracking issue, закрытие после проверки)

## Goal

Закрыть parent tracking issue #105 после того, как все child issues решены и Gate 1 (re-baseline #101) пройден.

## Чеклист подзадач (child issues)

| # | Issue | Status | Notes |
|---|-------|--------|-------|
| 107 | fix(observability): normalize latency_stages units | CLOSED | Единицы нормализованы |
| 109 | fix(grade): recalibrate relevance logic for RRF | CLOSED | Threshold пересчитан |
| 108 | perf(graph): rewrite stop-guard | OPEN | План есть, реализация pending |

## Зависимости из Roadmap

Согласно `docs/plans/2026-02-11-parallel-execution-roadmap.md`:

    #105 закрывается ПОСЛЕ Gate 1 (#101 re-baseline) pass

Gate 1 (#101) требует завершения:

| Stream | Issues | Status |
|--------|--------|--------|
| A: Latency-LLM+Embed | #124 (TTFT), #106a (BGE quick fix) | check |
| B: Latency-Graph | #108 (rewrite guard) | OPEN |
| C: Observability | #103 (scores), #123 (orphan traces) | check |
| D: Infra-Perf | #121 (Redis), #122 (Qdrant timeout) | check |

## Блокеры

1. **#108** — единственный OPEN child issue. Должен быть реализован и закрыт
2. **#101** — Gate 1 re-baseline. Должен пройти Go/No-Go проверку

## Верификация перед закрытием

### Step 1: Проверить все child issues закрыты (2 мин)

    gh issue list --milestone "Gate: Re-Baseline" --state open --json number,title

Ожидание: #108 closed, все child issues #105 resolved.

### Step 2: Проверить Gate 1 metrics (3 мин)

Условия из roadmap:

| Condition | Target |
|-----------|--------|
| p50 total | < 5s |
| p90 total | < 8s |
| p50 TTFT | < 2s |
| cache hit | < 1.5s |
| orphan traces | 0% |

Проверка: make validate-traces-fast — должен пройти без ошибок.

### Step 3: Проверить acceptance criteria из issue body (2 мин)

- [ ] latency_total_ms aligns with trace latency in ms (±10%)
- [ ] Rewrite cycles reduced for FAQ/entity queries without quality regression
- [ ] tests/unit/graph/* remain green

Команды:

    uv run pytest tests/unit/graph/ -v
    # Проверить последние трейсы в Langfuse: latency_total_ms vs trace duration

### Step 4: Проверить unit tests (2 мин)

    make test-unit

### Step 5: Закрыть issue (1 мин)

    gh issue close 105 --comment "All child issues resolved (#107, #108, #109). Gate 1 (#101) passed. Acceptance criteria met:
    - latency_total_ms normalized and aligned with trace latency
    - Rewrite loops reduced via stop-guard and RRF threshold recalibration
    - All unit tests green"

## Шаги выполнения

| # | Действие | Время | Блокер |
|---|----------|-------|--------|
| 1 | Дождаться закрытия #108 (rewrite stop-guard) | - | #108 |
| 2 | Дождаться прохождения Gate 1 (#101) | - | #101 |
| 3 | Проверить child issues closed | 2 мин | Step 2 |
| 4 | Проверить Gate 1 metrics | 3 мин | Step 3 |
| 5 | Прогнать unit tests | 2 мин | Step 4 |
| 6 | Закрыть issue #105 с комментарием | 1 мин | Step 5 |

## Текущий статус

- **Готово:** #107 (closed), #109 (closed)
- **В ожидании:** #108 (open — реализация), #101 (open — gate)
- **Вывод:** #105 НЕ может быть закрыт сейчас. Ждём #108 → #101 → #105
