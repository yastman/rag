# Langfuse Gold-Set Dataset + Experiments -- Implementation Plan

**Issue:** #126 feat(eval): Langfuse gold-set dataset + experiments
**Milestone:** Stream-E: Quality-Eval
**Blocked by:** #110 (stable baseline + clean runtime)
**Blocks:** #127 (LLM-as-a-Judge поверх experiments)
**Related:** #103, #107, #120, #125
**Date:** 2026-02-11

## Goal

Внедрить Langfuse Dataset + Experiment Runner для regression-gate:
- Dataset `evaluation/goldset-v1` с `input`, `expected_output`, `metadata` в UI.
- `run_experiment(...)` через SDK с item-level и run-level evaluators.
- Make targets для CI-ready запуска.

## Architecture

    ┌──────────────────────┐      ┌────────────────────────┐
    │ validate_queries.py  │      │  ground_truth.json     │
    │ (40+ queries)        │─────>│  (queries + expected)  │
    └──────────────────────┘      └────────────┬───────────┘
                                               │
                                  langfuse_goldset_sync.py
                                               │
                                               ▼
                                  ┌────────────────────────┐
                                  │ Langfuse Dataset       │
                                  │ evaluation/goldset-v1  │
                                  │ items: input,          │
                                  │   expected_output,     │
                                  │   metadata             │
                                  └────────────┬───────────┘
                                               │
                                  langfuse_goldset_run.py
                                  (run_experiment / item.run)
                                               │
                                               ▼
                                  ┌────────────────────────┐
                                  │ Experiment Run in UI   │
                                  │ - traces per item      │
                                  │ - item-level scores    │
                                  │ - run-level aggregates │
                                  └────────────────────────┘

## Current State

### Что есть

1. **scripts/validate_queries.py** (342 LOC):
   - `ValidationQuery` dataclass: `text`, `source`, `difficulty`, `collection`, `expect_rewrite`
   - 3 query sets: `PROPERTY_QUERIES` (14), `LEGAL_QUERIES` (10), `GDRIVE_BGE_QUERIES` (30), `EDGE_CASE_QUERIES` (3)
   - Нет `expected_output` -- только вопросы без эталонных ответов

2. **scripts/validate_traces.py** (821 LOC):
   - Full pipeline runner: warmup -> cold -> cache_hit phases
   - Langfuse enrichment через `enrich_results_from_langfuse()`
   - 12 scores per trace (latency, cache, rerank, etc.)
   - Markdown + JSON reports

3. **tests/baseline/** (conftest.py, collector.py, manager.py):
   - `LangfuseMetricsCollector` -- fetches metrics by tags
   - `BaselineManager` -- snapshot comparison
   - Thresholds in `thresholds.yaml`

4. **telegram_bot/observability.py** (138 LOC):
   - Langfuse v3: `@observe`, `get_client()`, `propagate_attributes`
   - PII masking, conditional enable/disable

5. **Langfuse SDK:** `langfuse>=3.0.0` in pyproject.toml

### Чего не хватает

- `expected_output` в ValidationQuery
- Dataset sync script (create/update items in Langfuse)
- Experiment runner через SDK `run_experiment` / `item.run()`
- Ground truth JSON file
- Make targets

## Dataset Design

### Dataset Name
`evaluation/goldset-v1`

### Item Schema

    input: { "query": "<вопрос>" }
    expected_output: "<эталонный ответ или ключевые факты>"
    metadata:
        item_id: str           # stable ID для upsert
        collection: str        # gdrive_documents_bge | legal_documents
        difficulty: str        # easy | medium | hard
        source: str            # smoke | eval | manual
        language: str          # ru | uk
        intent: str            # price_query | legal_article | comparison | ...
        must_retrieve: bool    # ожидается ли retrieval
        expected_doc_ids: list  # (optional) IDs документов для recall

### Query Source

Переиспользовать существующие queries из `validate_queries.py`:
- Начать с subset: 15-20 queries из `GDRIVE_BGE_QUERIES` (production collection)
- Добавить 5-10 из `LEGAL_QUERIES`
- Написать `expected_output` для каждого (ручная работа, ~1 предложение с ключевыми фактами)
- Постепенно расширять до 40-80 queries

## Implementation Steps

### Step 1: Extend ValidationQuery dataclass (~3 min)

**File:** `scripts/validate_queries.py:12-19`
**What:** Добавить поля `expected_output` и `must_retrieve` в dataclass.

    @dataclass
    class ValidationQuery:
        text: str
        source: str
        difficulty: str
        collection: str
        expect_rewrite: bool = False
        expected_output: str = ""       # NEW: эталонный ответ / ключевые факты
        must_retrieve: bool = True      # NEW: ожидается ли retrieval

Не ломает существующий код -- оба поля optional с defaults.

### Step 2: Create ground truth JSON file (~5 min)

**File:** `scripts/eval/ground_truth.json` (NEW)
**What:** JSON-массив с queries + expected_output + metadata.

Формат:

    [
        {
            "item_id": "gdrive-easy-001",
            "query": "квартира в Несебре",
            "expected_output": "В базе есть квартиры в Несебре...",
            "collection": "gdrive_documents_bge",
            "difficulty": "easy",
            "source": "smoke",
            "language": "ru",
            "intent": "location_search",
            "must_retrieve": true,
            "expected_doc_ids": []
        }
    ]

Начальный набор: 20-25 queries из GDRIVE_BGE_QUERIES + LEGAL_QUERIES.
expected_output: 1-2 предложения с ключевыми фактами, которые ДОЛЖНЫ присутствовать в ответе.

### Step 3: Create dataset sync script (~5 min)

**File:** `scripts/eval/langfuse_goldset_sync.py` (NEW)
**What:** Загрузить ground truth в Langfuse dataset.

Логика:
1. Читает `scripts/eval/ground_truth.json`
2. `langfuse.create_dataset(name="evaluation/goldset-v1", description=..., metadata=...)`
   - Idempotent: если dataset существует, переиспользует
3. Для каждого item:
   `langfuse.create_dataset_item(dataset_name=..., input=..., expected_output=..., metadata=...)`
4. Выводит отчёт: created/updated/total counts

SDK API (из Context7 research):

    langfuse = Langfuse()
    langfuse.create_dataset(name="evaluation/goldset-v1", description="Gold set v1", metadata={...})
    langfuse.create_dataset_item(
        dataset_name="evaluation/goldset-v1",
        input={"query": "квартира в Несебре"},
        expected_output="В базе есть квартиры в Несебре...",
        metadata={"item_id": "gdrive-easy-001", "collection": "gdrive_documents_bge", ...}
    )
    langfuse.flush()

CLI usage:

    uv run python scripts/eval/langfuse_goldset_sync.py
    uv run python scripts/eval/langfuse_goldset_sync.py --dry-run

### Step 4: Create experiment runner (~5 min)

**File:** `scripts/eval/langfuse_goldset_run.py` (NEW)
**What:** Запуск experiment через Langfuse SDK.

Два подхода (из SDK research):

**Подход A: `item.run()` context manager (рекомендуется)**
- Полный контроль над pipeline execution
- Естественная интеграция с существующим `run_single_query()` из validate_traces.py

    dataset = langfuse.get_dataset("evaluation/goldset-v1")
    for item in dataset.items:
        with item.run(
            run_name=f"eval-{git_sha[:8]}-{timestamp}",
            run_description="Regression run",
            run_metadata={"git_sha": git_sha, "collection": collection},
        ) as root_span:
            # Инициализация сервисов (из validate_traces.py init_services)
            # Запуск query через LangGraph pipeline
            output = await run_pipeline(item.input["query"], services)
            root_span.update_trace(input=item.input, output={"response": output})
            # Item-level scoring
            root_span.score_trace(name="latency_total_ms", value=latency_ms)
            root_span.score_trace(name="answer_relevance", value=compute_relevance(output, item.expected_output))

**Подход B: `langfuse.run_experiment()` high-level API**
- Автоматический concurrent execution
- Встроенные evaluators

    def my_task(*, item, **kwargs):
        output = run_pipeline(item["input"]["query"], services)
        return output

    def relevance_evaluator(*, input, output, expected_output, **kwargs):
        from langfuse import Evaluation
        score = compute_relevance(output, expected_output)
        return Evaluation(name="answer_relevance", value=score)

    result = langfuse.run_experiment(
        name=f"eval-{git_sha[:8]}",
        data="evaluation/goldset-v1",  # dataset name
        task=my_task,
        evaluators=[relevance_evaluator, latency_evaluator],
        run_evaluators=[avg_relevance, p95_latency],
    )
    print(result.format())

**Decision:** Использовать **Подход A** (`item.run()`), потому что:
- Pipeline async (run_experiment может не поддерживать async task из коробки)
- Нужна интеграция с `@observe` и `propagate_attributes`
- Больше контроля над initialization/cleanup сервисов
- Можно переиспользовать `init_services()` и `run_single_query()` из validate_traces.py

Структура runner:
1. Argparse: `--collection`, `--run-name`, `--report`
2. `init_services(collection)` -- из validate_traces.py (refactor в shared util)
3. `dataset = langfuse.get_dataset("evaluation/goldset-v1")`
4. Filter items по collection metadata
5. For each item: `item.run()` -> pipeline -> scores
6. Post-run: compute aggregates, print summary
7. Optional: write markdown report

### Step 5: Item-level evaluators (~3 min)

**File:** `scripts/eval/evaluators.py` (NEW)
**What:** Deterministic evaluator functions.

    def compute_latency_score(latency_ms: float) -> dict:
        return {"name": "latency_total_ms", "value": latency_ms}

    def compute_answer_relevance(output: str, expected_output: str) -> dict:
        # Простая keyword overlap metric
        expected_keywords = set(expected_output.lower().split())
        output_keywords = set(output.lower().split())
        if not expected_keywords:
            return {"name": "answer_relevance", "value": 0.0}
        overlap = len(expected_keywords & output_keywords) / len(expected_keywords)
        return {"name": "answer_relevance", "value": overlap}

    def compute_retrieval_recall(
        retrieved_doc_ids: list[str],
        expected_doc_ids: list[str],
    ) -> dict:
        if not expected_doc_ids:
            return {"name": "retrieval_recall_at_k", "value": None}
        hits = sum(1 for d in expected_doc_ids if d in retrieved_doc_ids)
        return {"name": "retrieval_recall_at_k", "value": hits / len(expected_doc_ids)}

### Step 6: Run-level aggregates (~3 min)

**File:** `scripts/eval/langfuse_goldset_run.py` (внутри runner)
**What:** Post-run aggregation и scoring.

    # После прогона всех items:
    latencies = [r["latency_ms"] for r in results]
    relevances = [r["answer_relevance"] for r in results if r["answer_relevance"] is not None]

    run_metrics = {
        "p50_latency_ms": float(np.percentile(latencies, 50)),
        "p95_latency_ms": float(np.percentile(latencies, 95)),
        "avg_answer_relevance": float(np.mean(relevances)) if relevances else 0.0,
        "pass_rate": sum(1 for r in relevances if r >= 0.5) / len(relevances) if relevances else 0.0,
    }

Run-level scores записываются через `langfuse.score()` с trace_id первого item или отдельным trace.

### Step 7: Refactor shared init_services (~3 min)

**File:** `scripts/eval/__init__.py` (NEW), modify `scripts/validate_traces.py`
**What:** Вынести `init_services()` в shared module для reuse.

Текущая `init_services()` в validate_traces.py:167-204 -- перенести в:

    scripts/eval/services.py

И импортировать из обоих скриптов. Минимальный рефакторинг:

    # scripts/eval/services.py
    async def init_services(collection: str) -> dict[str, Any]:
        ... (существующий код из validate_traces.py:167-204)

    # scripts/validate_traces.py
    from scripts.eval.services import init_services

### Step 8: Makefile targets (~2 min)

**File:** `Makefile`
**What:** Добавить make targets.

    eval-langfuse-goldset-sync:
        uv run python scripts/eval/langfuse_goldset_sync.py

    eval-langfuse-goldset-run:
        uv run python scripts/eval/langfuse_goldset_run.py \
            --collection gdrive_documents_bge --report

### Step 9: Unit tests (~5 min)

**File:** `tests/unit/test_goldset_evaluators.py` (NEW)
**What:** Тесты для evaluator functions.

- `test_compute_answer_relevance_exact_match` -- score = 1.0
- `test_compute_answer_relevance_partial` -- 0 < score < 1
- `test_compute_answer_relevance_no_match` -- score = 0.0
- `test_compute_retrieval_recall_full` -- all docs found
- `test_compute_retrieval_recall_partial` -- subset found
- `test_compute_retrieval_recall_no_expected` -- returns None

**File:** `tests/unit/test_goldset_sync.py` (NEW)
**What:** Тесты для sync logic.

- `test_load_ground_truth_json` -- validates schema
- `test_sync_creates_dataset` -- mock Langfuse, verify create_dataset called
- `test_sync_creates_items` -- mock Langfuse, verify create_dataset_item called per item

## Test Strategy

| Layer | What | How |
|-------|------|-----|
| Unit | Evaluator functions | pytest, no external deps |
| Unit | JSON schema validation | pytest, load ground_truth.json |
| Unit | Sync script logic | pytest + mock Langfuse |
| Integration | Sync to real Langfuse | `make eval-langfuse-goldset-sync` (manual, requires running Langfuse) |
| Integration | Full experiment run | `make eval-langfuse-goldset-run` (manual, requires all services) |

## Acceptance Criteria

- [ ] В Langfuse UI создан dataset `evaluation/goldset-v1`
- [ ] Items содержат `input` + `expected_output` + metadata
- [ ] `item.run()` создаёт run с trace per item, видимый в UI
- [ ] Item-level scores: `latency_total_ms`, `answer_relevance`
- [ ] Run-level metrics: `p50_latency_ms`, `p95_latency_ms`, `avg_answer_relevance`, `pass_rate`
- [ ] `make eval-langfuse-goldset-sync` -- syncs dataset
- [ ] `make eval-langfuse-goldset-run` -- runs experiment
- [ ] Unit tests pass: evaluators + sync logic
- [ ] Результаты первого прогона приложены в комментарий к #126

## Effort Estimate

| Step | Time | Complexity |
|------|------|------------|
| 1. Extend ValidationQuery | 3 min | Trivial |
| 2. Ground truth JSON | 5 min | Manual (write expected_output) |
| 3. Sync script | 5 min | Low |
| 4. Experiment runner | 5 min | Medium (async pipeline integration) |
| 5. Evaluators | 3 min | Low |
| 6. Run-level aggregates | 3 min | Low |
| 7. Refactor init_services | 3 min | Low |
| 8. Makefile | 2 min | Trivial |
| 9. Unit tests | 5 min | Low |
| **Total** | **~34 min** | **Medium** |

## Risks

| Risk | Mitigation |
|------|------------|
| Langfuse SDK version incompatible | Проверить `langfuse>=3.0.0`, `run_experiment` доступен с Sept 2025 SDK |
| Dataset name collision | Idempotent `create_dataset` -- SDK не создаёт дубликаты |
| Pipeline failure на отдельных queries | `try/except` per item, log errors, continue |
| expected_output качество | Начать с keyword-based, улучшать итеративно |
| Async + item.run() совместимость | Тестировать: `@observe` внутри `item.run()` context manager |

## References

- Langfuse Experiments via SDK: https://langfuse.com/docs/evaluation/experiments/experiments-via-sdk
- Langfuse Datasets: https://langfuse.com/docs/evaluation/experiments/datasets
- Langfuse Data Model: https://langfuse.com/docs/evaluation/experiments/data-model
- Experiment Runner SDK (Sept 2025): https://langfuse.com/changelog/2025-09-17-experiment-runner-sdk
- Related plan: `docs/plans/2026-02-10-langfuse-llm-judge-goldset-plan.md`
