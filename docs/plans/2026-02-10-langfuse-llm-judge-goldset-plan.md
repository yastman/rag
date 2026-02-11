# Langfuse Gold Set + LLM-as-a-Judge Plan (2026 Best Practices)

## Goal
Построить воспроизводимый контур оценки в Langfuse, где в UI видны:
- входные вопросы (`input`),
- эталонные ответы (`expected_output`),
- результаты экспериментов и метрики по каждому item и по всему run,
- автооценки через LLM-as-a-Judge для offline и production контуров.

## Why Now
- Трассировка есть, но нет единого регрессионного evaluation-loop на dataset runs.
- Нужен устойчивый gate перед latency/quality решениями (BGE/ONNX/routing changes).
- По Langfuse best practice: использовать связку `Datasets -> Experiments -> Scores`, а LLM-as-a-Judge применять как масштабируемый слой оценки с калибровкой.

## Sources Reviewed (Context7 + Exa + Official Docs)
- Langfuse Evaluation Overview: https://langfuse.com/docs/evaluation/overview
- Langfuse LLM-as-a-Judge: https://langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge
- Langfuse Datasets: https://langfuse.com/docs/evaluation/experiments/datasets
- Langfuse Experiments via SDK: https://langfuse.com/docs/evaluation/experiments/experiments-via-sdk
- Langfuse Python reference: https://python.reference.langfuse.com/langfuse

## 2026 Best-Practice Principles
1. `SDK-first`:
- Только `langfuse-python` (`create_dataset`, `create_dataset_item`, `get_dataset`, `dataset.run_experiment`).
- Без raw HTTP для eval-flow, где SDK уже покрывает сценарий.

2. Dataset lineage and reproducibility:
- Каждый item хранит `input`, `expected_output`, `metadata`.
- Использовать `source_trace_id`/`source_observation_id` для связывания с продовыми примерами.
- Не перезаписывать "вслепую" датасет; сохранять историю изменений и фиксировать dataset version в run metadata.

3. Two-layer evaluation:
- Layer A: детерминированные/правиловые метрики (latency, retrieval recall, format checks).
- Layer B: LLM-as-a-Judge (correctness, groundedness, relevance, safety).
- Для high-stakes решений использовать human spot-check и agreement-контроль.

4. Judge calibration:
- Отдельный holdout с human labels.
- Периодический контроль согласия judge vs human.
- Любая смена judge-модели/промпта требует повторной калибровки и новой baseline.

5. Cost-aware sampling:
- Для production traces включать sampling/фильтры (не оценивать 100% трафика без необходимости).
- На regression runs по gold set — полный прогон.

## Scope

### In Scope
- Синхронизация gold set из `tests/eval/ground_truth.json` в Langfuse dataset.
- Запуск experiments через SDK с item/run evaluators.
- Настройка LLM-as-a-Judge evaluator templates в UI и mapping переменных.
- Единые метрики и gate-критерии для сравнения runs.
- Make-команды и документация запуска.

### Out of Scope
- Полная замена RAGAS.
- Онлайн human-review workflow как обязательный блокер релиза.

## Target Data Model

Dataset name:
- `evaluation/goldset-v1` (или versioned alias по релизам).

Dataset item fields:
- `input`: `{ "question": "<text>" }`
- `expected_output`: `<gold answer>`
- `metadata`:
  - `item_id`
  - `category`
  - `difficulty`
  - `language`
  - `expected_doc_ids` (optional)
  - `source` (`manual`, `prod_trace`, etc.)

Lineage fields:
- `source_trace_id` (optional)
- `source_observation_id` (optional)

## Metrics Contract

### Item-level
- `latency_total_ms` (NUMERIC)
- `answer_match` (NUMERIC, deterministic/heuristic)
- `retrieval_recall_at_k` (NUMERIC, if `expected_doc_ids` available)
- `judge_correctness` (NUMERIC/CATEGORICAL)
- `judge_groundedness` (NUMERIC/CATEGORICAL)
- `judge_relevance` (NUMERIC/CATEGORICAL)

### Run-level
- `avg_answer_match`
- `avg_retrieval_recall_at_k`
- `avg_judge_correctness`
- `p50_latency_ms`, `p95_latency_ms`
- `pass_rate`

## Execution Plan

### Phase 1: Gold Set Sync (SDK)
1. Add `scripts/eval/langfuse_goldset_sync.py`.
2. Input source: `tests/eval/ground_truth.json`.
3. Upsert strategy:
- stable item id from dataset sample `id`,
- archive items absent in source (optional flag),
- attach metadata and lineage fields.
4. Emit sync report: created/updated/archived counts.

Deliverable:
- Dataset visible in Langfuse UI with `input + expected_output` per item.

### Phase 2: Experiment Runner (SDK)
1. Add `scripts/eval/langfuse_goldset_run.py`.
2. Use `dataset.run_experiment(...)`.
3. Task function:
- runs current RAG pipeline (same env/model config as bot).
4. Evaluators:
- deterministic evaluator(s),
- retrieval evaluator (if expected docs present),
- optional local LLM judge fallback.
5. Run evaluators:
- aggregate metrics + gate decision.

Deliverable:
- Dataset run in UI with item results, trace links, and aggregated scores.

### Phase 3: Managed LLM-as-a-Judge (UI)
1. Configure evaluator in Langfuse UI:
- choose model connection,
- set prompt template,
- map `input`, `output`, `expected_output` (and JSONPath for nested outputs),
- set scope (new traces / existing traces / both),
- configure sampling.
2. Enable judge on:
- experiment traces (offline),
- selected production traces (online sampling).

Deliverable:
- Judge scores visible next to item traces and in score analytics.

### Phase 4: Calibration & Guardrails
1. Create calibration split (20-50 labeled examples).
2. Compare judge vs human labels (agreement tracking).
3. Freeze judge prompt+model version for baseline period.
4. Add fallback policy:
- if judge unavailable/error -> run deterministic metrics only; run flagged as partial.

Deliverable:
- Calibration report + accepted judge config version.

### Phase 5: Ops Integration
1. Add Make targets:
- `make eval-langfuse-goldset-sync`
- `make eval-langfuse-goldset-run`
2. Add docs section with:
- required env vars,
- runbook,
- interpretation of pass/fail.
3. Post results to issue #120 (trace IDs + dataset run URL + metric table).

Deliverable:
- Repeatable evaluation flow for every optimization sprint.

## Acceptance Criteria
- [ ] Gold set dataset создан и виден в Langfuse UI.
- [ ] У каждого item есть `input`, `expected_output`, metadata.
- [ ] `dataset.run_experiment` выполняется из CLI и пишет traces/scores.
- [ ] LLM-as-a-Judge evaluator настроен и применим к experiment traces.
- [ ] Есть калибровка judge vs human и зафиксированный judge config.
- [ ] Результаты прогонов и ссылки на runs добавлены в #120.

## Risks & Mitigations
- Judge drift / inconsistent scoring:
  - Mitigation: calibration set + version pin + periodic re-check.
- High eval cost:
  - Mitigation: sampling in production, full runs only for regression gates.
- Dataset noise:
  - Mitigation: metadata hygiene, lineage fields, archive instead of silent deletion.

## Dependencies
- Existing issue: #126 (base gold set + SDK runner)
- Umbrella: #120, #125
