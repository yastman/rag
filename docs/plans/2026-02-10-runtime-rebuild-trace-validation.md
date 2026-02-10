# Runtime Rebuild & Trace Validation Design

**Issue:** [#110](https://github.com/yastman/rag/issues/110)
**Parent:** [#105](https://github.com/yastman/rag/issues/105) (latency tracker)
**Date:** 2026-02-10

## Goal

Валидировать, что недавние изменения кода (hybrid embeddings, skip_rerank recalibration,
RRF fixes, streaming fallback) устраняют проблемы латентности из trace `c2b95d86`.
Создать reusable `make validate-traces` target для повторных проверок.

## Environment

- Local WSL2 Docker Compose
- Collections: `legal_documents` (BGE-M3) + `contextual_bulgaria_voyage` (Voyage, if available)

## Step 1 — Rebuild & Restart

```bash
# Full rebuild (no cache)
docker compose build --no-cache telegram-bot litellm bge-m3
docker compose --profile core --profile bot --profile ml up -d --wait

# Fast restart (cached build, для повторных прогонов)
docker compose build telegram-bot litellm bge-m3
docker compose --profile core --profile bot --profile ml up -d --wait
```

`--wait` использует нативные healthcheck'и Docker, без кастомного polling.

### Collection availability check

Перед запуском:
1. Qdrant: `collection_exists()` API call
2. Voyage: проверка `VOYAGE_API_KEY` env var
3. Skip с явным логом: `"Skipping contextual_bulgaria_voyage: collection not found in Qdrant"`

## Step 2 — Query Set (mix)

| Source | Queries | Domain | Purpose |
|--------|---------|--------|---------|
| `tests/smoke/queries.py` | 14 (без chitchat) | Bulgarian property | Simple + Complex paths |
| `src/evaluation/smoke_test.py` | 10 (выборка) | Criminal Code | Hard + Medium |
| Manual edge cases | 3-5 | Оба | Rewrite trigger, cache hit, empty results |

**Total:** ~25-30 queries per collection (where available).

## Step 3 — Execution Flow

### Trace wrapper

Каждый `graph.ainvoke` оборачивается в `@observe(name="validation-run")` с
`propagate_attributes(session_id=validation_run_id, tags=["validation"])`.

### Trace metadata (на каждом trace)

- `validation_run_id` — uuid, один на весь прогон
- `git_sha` — `git rev-parse HEAD`
- `collection` — имя коллекции
- `query_set` — источник (smoke/eval/manual)
- `query_difficulty` — easy/medium/hard
- `skip_rerank_threshold` — из env/GraphConfig (не хардкод)

### Phases

| Phase | Queries | Включать в метрики |
|-------|---------|-------------------|
| Warmup | 3-5 random | Нет |
| Cold run | Все ~25-30 уникальных | Да, группа `cold` |
| Cache-hit run | 5-7 дубликатов из cold | Да, группа `cache_hit` |

### Post-run

```
sleep 5s → flush Langfuse queue
pull metrics via Langfuse API by validation_run_id
compute aggregates → generate report
```

## Step 4 — Metrics

### Per-trace (из Langfuse scores, все бинарные поля — 1.0/0.0)

| Score | Type | Source |
|-------|------|--------|
| `latency_total_ms` | float | `bot.py` score |
| `semantic_cache_hit` | 1.0/0.0 | `bot.py` score |
| `search_cache_hit` | 1.0/0.0 | `bot.py` score |
| `embeddings_cache_hit` | 1.0/0.0 | `bot.py` score |
| `rerank_applied` | 1.0/0.0 | `bot.py` score |
| `results_count` | float | `bot.py` score |
| `confidence_score` | float | `bot.py` score |
| `query_type` | float | `bot.py` score |
| `llm_used` | 1.0/0.0 | `bot.py` score |
| Node durations | float (ms) | Langfuse span durations |
| `rewrite_count` | int | Из span count (rewrite node) |

**`skip_rerank_reason`** — не score, выводится в скрипте:
если `rerank_applied=0` и `confidence_score >= skip_rerank_threshold` (из env/metadata) → "threshold skip".
Порог берётся из `SKIP_RERANK_THRESHOLD` env или `GraphConfig.skip_rerank_threshold`, не хардкод.

### Aggregates (отдельно по cold / cache_hit)

- p50, p95, mean, max — `latency_total_ms`
- p50, p95 — per-node durations
- rate — `cache_hit_rate`, `rerank_rate`, `rewrite_rate` (доли по бинарным scores)

### Comparative table

| Metric | Trace c2b95d86 | Cold (n=?) | Cold p50 | Cold p95 | Cache (n=?) | Cache p50 |
|--------|---------------|------------|----------|----------|-------------|-----------|
| latency_total_ms | ? | | ? | ? | | ? |
| rewrite_count | ? | | ? | ? | | — |
| rerank_applied rate | ? | | ? | — | | ? |
| results_count | ? | | ? | ? | | ? |

`n` указывается явно для каждой группы.
Значения из trace `c2b95d86` подтягиваются через Langfuse API автоматически.

## Step 5 — Output

### Report

`docs/plans/YYYY-MM-DD-runtime-rebuild-trace-validation.md` (этот файл обновляется результатами)
или отдельный `docs/reports/YYYY-MM-DD-validation-run-<run_id>.md`.

Содержит:
- Команды выполнения
- Все trace IDs
- Таблица метрик (cold / cache / reference trace)
- Go/No-Go рекомендация

### Go/No-Go Decision Gate

- **If reproducible:** proceed with #107/#108/#109 implementation
- **If not reproducible:** close or narrow scope with evidence

## File Structure

```
scripts/validate_traces.py       # Main validation script
scripts/validate_queries.py      # Query sets (importable)
Makefile                         # targets: validate-traces, validate-traces-fast
```

## Makefile Targets

```makefile
validate-traces:                 ## Full rebuild + validation + report
	docker compose build --no-cache telegram-bot litellm bge-m3
	docker compose --profile core --profile bot --profile ml up -d --wait
	uv run python scripts/validate_traces.py --report

validate-traces-fast:            ## Cached build + validation + report (no --no-cache)
	docker compose build telegram-bot litellm bge-m3
	docker compose --profile core --profile bot --profile ml up -d --wait
	uv run python scripts/validate_traces.py --report
```

## Script CLI

```bash
# Full cycle (rebuild + run + report)
make validate-traces

# Fast (cached build)
make validate-traces-fast

# Only run (stack already up)
uv run python scripts/validate_traces.py --report

# Specific collection
uv run python scripts/validate_traces.py --collection legal_documents --report
```
