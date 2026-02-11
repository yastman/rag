# LLM-as-a-Judge Calibration + Regression Gate — Implementation Plan

## Goal

Внедрить managed LLM-as-a-Judge evaluators в Langfuse для стабильных quality-оценок experiment runs
и production traces, с калибровкой по human labels и regression gate в validate pipeline.

**Issue:** https://github.com/yastman/rag/issues/127
**Blocked by:** #126 (gold set dataset + experiment runner)
**Related:** #110 (trace validation), #120 (umbrella), #125
**Milestone:** Stream-E: Quality-Eval
**Reference plan:** `docs/plans/2026-02-10-langfuse-llm-judge-goldset-plan.md` (Phases 3-4)

## Architecture

    ┌─────────────────────────────────────────────────────────────┐
    │ Langfuse UI                                                 │
    │ ┌───────────────┐  ┌──────────────────┐  ┌──────────────┐  │
    │ │ LLM Connection│  │ Evaluator Config │  │ Score        │  │
    │ │ (LiteLLM→OSS) │→ │ correctness      │→ │ Analytics    │  │
    │ │               │  │ groundedness     │  │              │  │
    │ │               │  │ relevance        │  │              │  │
    │ └───────────────┘  └──────────────────┘  └──────────────┘  │
    └────────────────────────┬────────────────────────────────────┘
                             │ auto-scores on experiment runs
                             ▼
    ┌────────────────────────────────────────────────────────────┐
    │ SDK Pipeline (Python)                                      │
    │                                                            │
    │ goldset_sync.py → goldset_run.py → calibration_check.py   │
    │      (#126)           (#126)            (#127)             │
    │                                                            │
    │ validate_traces.py ← regression gate ← judge thresholds   │
    │      (#110)              (#127)            (#127)          │
    └────────────────────────────────────────────────────────────┘

## Sources Reviewed

- **Microsoft Foundry:** "Evaluating AI Agents: Can LLM-as-a-Judge Evaluators Be Trusted?" (Jan 2026) — ключевые риски: overconfidence, position bias, verbosity bias
- **GoDaddy:** "Calibrating Scores of LLM-as-a-Judge" (Nov 2025) — методология калибровки: holdout set, drift detection, re-calibration triggers
- **ICLR 2026 (7664):** "Overconfidence in LLM-as-a-Judge" — TH-Score metric для confidence-accuracy alignment, LLM-as-a-Fuser ensemble
- **Langfuse docs (Context7):** managed evaluators setup, LLM connections, variable mapping, experiments via SDK, score analytics
- **Langfuse changelog:** managed LLM-as-a-judge for dataset experiments (Nov 2024), evaluator migration guide (observation-level)

## Evaluator Design

### Критерии оценки (3 evaluators)

| Evaluator | Score Name | Type | Scale | Prompt Template |
|-----------|-----------|------|-------|-----------------|
| Correctness | `judge_correctness` | NUMERIC | 0.0-1.0 | "Is the answer factually correct given the expected output?" |
| Groundedness | `judge_groundedness` | NUMERIC | 0.0-1.0 | "Is the answer grounded in the retrieved context without hallucination?" |
| Relevance | `judge_relevance` | NUMERIC | 0.0-1.0 | "Is the answer relevant and helpful for the user's question?" |

### Модель для judge

- **Primary:** `gpt-4o-mini` через LiteLLM (дешёвый, поддерживает tool calling)
- **LLM Connection:** создать в Langfuse UI → Project Settings → LLM Connections
- **Base URL:** `http://litellm:4000` (внутренний proxy)
- **Temperature:** 0 (детерминированность)
- **Max tokens:** 256 (достаточно для score + reasoning)

### Variable Mapping

    input         → {{input}}         → item.input.question (JSONPath: $.question)
    output        → {{output}}        → run output (response text)
    expected_output → {{expected_output}} → item.expected_output
    context       → {{context}}       → run metadata.retrieved_docs (для groundedness)

### Sampling Policy

| Scope | Sampling | Rationale |
|-------|----------|-----------|
| Experiment runs (offline) | 100% | Полный прогон gold set (~50-100 items) |
| Production traces (online) | 5% | Cost-aware, ~$0.01/eval × 5% traffic |
| Delay after trace | 30s | Дождаться flush всех spans |

## Calibration Process

### Шаг 1: Создать calibration holdout (20-30 items)

Файл: `tests/eval/calibration_labels.json`

    [
        {
            "item_id": "cal-001",
            "question": "...",
            "expected_output": "...",
            "model_output": "...",
            "human_correctness": 1.0,
            "human_groundedness": 0.8,
            "human_relevance": 1.0,
            "annotator": "human-1",
            "date": "2026-02-12"
        }
    ]

### Шаг 2: Прогнать judge по calibration set

Скрипт: `scripts/eval/calibration_check.py`

- Загрузить calibration items
- Прогнать через judge (те же промты что в Langfuse UI)
- Сравнить judge vs human scores

### Шаг 3: Метрики согласия

| Metric | Threshold | Action if below |
|--------|-----------|-----------------|
| Cohen's Kappa (binarized) | >= 0.6 | Re-calibrate prompt |
| Mean Absolute Error | <= 0.15 | Acceptable drift |
| Correlation (Pearson) | >= 0.7 | Judge tracks human |
| Max disagreement | <= 3 items (из 20) | Review outliers |

### Шаг 4: Версионирование judge config

Файл: `tests/eval/judge_config.json`

    {
        "version": "v1",
        "model": "gpt-4o-mini",
        "temperature": 0,
        "prompts": {
            "correctness": "<prompt hash>",
            "groundedness": "<prompt hash>",
            "relevance": "<prompt hash>"
        },
        "calibration_date": "2026-02-12",
        "calibration_kappa": 0.72,
        "calibration_mae": 0.11,
        "baseline_thresholds": {
            "judge_correctness_mean": 0.75,
            "judge_groundedness_mean": 0.80,
            "judge_relevance_mean": 0.70
        }
    }

### Re-calibration Triggers (Runbook)

1. Смена judge-модели → полная re-calibration
2. Изменение judge-промта → partial re-calibration (affected evaluator)
3. Quarterly review → drift check (прогнать calibration set, сравнить с baseline)
4. Human disagreement rate > 15% → immediate re-calibration

## Regression Gate

### Интеграция в validate_traces.py

Текущая структура (`scripts/validate_traces.py`):
- `run_validation()` → `compute_aggregates()` → `generate_report()`
- Go/No-Go section в report (строки 652-660) — сейчас ручной чеклист

Новый gate добавляет judge scores в automated decision:

    Go/No-Go Gate Criteria:
    ┌──────────────────────────────┬────────────┐
    │ Metric                       │ Threshold  │
    ├──────────────────────────────┼────────────┤
    │ Cold p50 latency             │ <= 3000 ms │
    │ Cold p95 latency             │ <= 5000 ms │
    │ Rewrite rate                 │ <= 20%     │
    │ judge_correctness mean       │ >= 0.75    │
    │ judge_groundedness mean      │ >= 0.80    │
    │ judge_relevance mean         │ >= 0.70    │
    │ No single item correctness=0 │ <= 2 items │
    └──────────────────────────────┴────────────┘

    Result: PASS (all met) | WARN (1-2 missed) | FAIL (3+ missed)

### Report Integration

Добавить секцию в `generate_report()`:
- Таблица judge scores per item
- Aggregate judge scores per run
- Automated PASS/WARN/FAIL verdict

## Шаги реализации

### Step 1: LLM Connection в Langfuse UI (2 мин)

**Действие:** Ручная настройка через UI
1. Langfuse UI → Project Settings → LLM Connections
2. Add connection: name=`litellm-judge`, provider=OpenAI-compatible
3. Base URL: `http://litellm:4000`, API key: из env
4. Model: `gpt-4o-mini`, test connection

**Deliverable:** Working LLM connection для evaluators

### Step 2: Evaluator Templates в Langfuse UI (5 мин)

**Действие:** Ручная настройка через UI
1. Evaluation → LLM-as-a-Judge → + Set up Evaluator
2. Создать 3 evaluators:
   - `judge_correctness` (managed template "Correctness" или custom)
   - `judge_groundedness` (managed template "Hallucination" inverted или custom)
   - `judge_relevance` (managed template "Relevance" или custom)
3. Для каждого:
   - Model: `litellm-judge` connection
   - Map variables: input → `{{input}}`, output → `{{output}}`, expected_output → `{{expected_output}}`
   - Scope: Dataset experiments → `evaluation/goldset-v1`
   - Sampling: 100% (experiments), 5% (production)
   - Delay: 30s

**Deliverable:** 3 active evaluators, auto-scoring experiment runs

### Step 3: Calibration Data File (3 мин)

**Файл:** `tests/eval/calibration_labels.json`
- Создать 20-30 entries с human labels
- Формат: item_id, question, expected_output, model_output, human_{correctness,groundedness,relevance}
- Источник: вручную из production traces в Langfuse + gold set items

**Deliverable:** Calibration holdout файл

### Step 4: Calibration Check Script (5 мин)

**Файл:** `scripts/eval/calibration_check.py`
**Зависимости:** `langfuse>=3.0.0`, `numpy`, `scipy` (для correlation)

Логика:
1. Загрузить `tests/eval/calibration_labels.json`
2. Для каждого item — вызвать LLM judge через OpenAI SDK (тот же промт что в UI)
3. Собрать judge scores
4. Вычислить agreement metrics: Cohen's Kappa, MAE, Pearson r
5. Сравнить с thresholds из `tests/eval/judge_config.json`
6. Вывести report: PASS/FAIL + per-evaluator breakdown
7. Сохранить результат в `tests/eval/calibration_report.json`

**Deliverable:** `uv run python scripts/eval/calibration_check.py` — работает, выводит agreement report

### Step 5: Judge Config Version File (2 мин)

**Файл:** `tests/eval/judge_config.json`
- Зафиксировать model, temperature, prompt versions
- Зафиксировать calibration metrics (kappa, mae, correlation)
- Зафиксировать baseline thresholds для gate

**Deliverable:** Immutable config file для текущей версии judge

### Step 6: Regression Gate в validate_traces.py (5 мин)

**Файл:** `scripts/validate_traces.py`

Изменения:
1. **Строка ~407-447** (`enrich_results_from_langfuse`): уже читает scores из trace — judge scores попадут автоматически если evaluator отработал
2. **Строка ~479-561** (`compute_aggregates`): добавить агрегацию judge scores
   - `judge_correctness_mean`, `judge_groundedness_mean`, `judge_relevance_mean`
   - Подсчитать из `r.scores` dict по каждому TraceResult
3. **Строка ~564-664** (`generate_report`): добавить секцию "Judge Scores" и "Regression Gate"
   - Таблица judge aggregates
   - Automated verdict: PASS / WARN / FAIL
4. **Новая функция** `evaluate_gate()`:
   - Принимает aggregates dict
   - Проверяет все criteria (latency + rewrite + judge)
   - Возвращает verdict + details

**Deliverable:** `make validate-traces-fast` включает judge gate в report

### Step 7: Gate Thresholds Config (3 мин)

**Файл:** `tests/baseline/thresholds.yaml`

Добавить секцию:

    judge_gate:
      judge_correctness_mean:
        min: 0.75
        warn: 0.70
      judge_groundedness_mean:
        min: 0.80
        warn: 0.75
      judge_relevance_mean:
        min: 0.70
        warn: 0.65
      max_zero_correctness_items: 2

**Deliverable:** Единый файл thresholds для latency + judge gate

### Step 8: Make Targets + Docs (3 мин)

**Файл:** `Makefile`

Добавить:

    eval-calibration-check:
        uv run python scripts/eval/calibration_check.py

**Файл:** `CLAUDE.md` (Quick Reference)

Добавить:

    make eval-calibration-check    # Judge calibration vs human labels

**Deliverable:** Документированные команды

## Test Strategy

1. **Unit test** `scripts/eval/calibration_check.py`:
   - Mock LLM responses, проверить agreement calculation
   - Файл: `tests/unit/test_calibration_check.py`

2. **Unit test** gate logic в `validate_traces.py`:
   - Mock aggregates с разными judge scores → проверить PASS/WARN/FAIL
   - Файл: `tests/unit/test_validate_gate.py`

3. **Integration test** (manual):
   - Запустить `make eval-langfuse-goldset-run` → проверить judge scores в Langfuse UI
   - Запустить `make eval-calibration-check` → проверить agreement report

## Acceptance Criteria

- [ ] LLM Connection создан в Langfuse UI, работает с LiteLLM proxy
- [ ] 3 evaluators (correctness, groundedness, relevance) активны для experiment traces
- [ ] Scores от evaluators попадают в trace/item/run analytics в UI
- [ ] Calibration holdout file (`tests/eval/calibration_labels.json`) создан с 20+ items
- [ ] `scripts/eval/calibration_check.py` выдаёт agreement report (kappa, MAE, correlation)
- [ ] Judge config version зафиксирован в `tests/eval/judge_config.json`
- [ ] Re-calibration runbook документирован
- [ ] `validate_traces.py` включает judge scores в aggregates и report
- [ ] Automated Go/No-Go gate: PASS / WARN / FAIL на основе latency + judge thresholds
- [ ] Gate criteria: p50 <= 3.0s, p95 <= 5.0s, rewrite_rate <= 20%, judge_score_mean >= threshold

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Judge overconfidence (ICLR 2026) | Ложные PASS | Калибровка holdout, TH-Score мониторинг |
| Judge drift при обновлении модели | Несопоставимые runs | Version pin в judge_config.json, re-cal trigger |
| LiteLLM/model unavailability | Gate не работает | Fallback: deterministic-only gate с WARN |
| High eval cost при масштабировании | Budget overrun | 5% sampling production, 100% только gold set |
| Position/verbosity bias | Скошенные scores | Randomize variable order в prompt, fixed format |

## Effort Estimate

| Step | Time | Dependency |
|------|------|------------|
| Step 1: LLM Connection | 2 мин | LiteLLM running |
| Step 2: Evaluator Templates | 5 мин | Step 1 |
| Step 3: Calibration Data | 3 мин | Gold set from #126 |
| Step 4: Calibration Script | 5 мин | Step 3 |
| Step 5: Judge Config | 2 мин | Step 4 |
| Step 6: Regression Gate | 5 мин | Steps 2, 5 |
| Step 7: Thresholds Config | 3 мин | Step 6 |
| Step 8: Make + Docs | 3 мин | Step 7 |
| **Total** | **~28 мин** | Blocked by #126 |
