# Миграция на Langfuse Managed Evaluators (observation-level)

> **Дата:** 2026-02-18
> **Статус:** Draft
> **Ветка:** feat/new-work

## Проблема

Текущие custom judge-функции (`telegram_bot/evaluation/judges.py`, `runner.py`) дублируют то, что Langfuse теперь предлагает из коробки. Код требует maintenance, деплоя, мониторинга. Batch runner работает минутами, online sampling — fire-and-forget без retry.

С 13 февраля 2026 Langfuse поддерживает **observation-level evaluators** — оценка отдельных spans (retrieve, generate) вместо целого trace. Это быстрее (секунды vs минуты), точнее и не требует кастомного кода.

## Решение

Перевести LLM-as-a-Judge с кастомного кода на Langfuse managed evaluators. Четыре фазы:

### Фаза 1: Managed Evaluators в Langfuse UI

**Цель:** Заменить `telegram_bot/evaluation/` на managed evaluators.

**Шаги:**
1. Настроить LLM Connection в Langfuse (модель с structured output, напр. `gpt-4o-mini`)
2. Создать 3 Custom evaluator templates (русскоязычные промты из `prompts.py`):
   - **faithfulness** → target: observation `node-generate` (type=GENERATION)
   - **context_relevance** → target: observation `node-retrieve` (type=SPAN)
   - **answer_relevance** → target: trace level (нужен input + output)
3. Настроить variable mapping через JSONPath:
   - `{{input}}` → `observation.input` / `trace.input`
   - `{{output}}` → `observation.output` / `trace.output`
   - `{{context}}` → `observation.output.documents` (для retrieve)
4. Установить sampling: 10% для production, 100% для `validation` tag
5. Добавить `propagate_attributes()` в instrumentation code (уже есть в `observability.py`)

**Результат:** Автоматическая оценка каждого trace без кастомного кода.

### Фаза 2: Калибровка

**Цель:** Убедиться что managed evaluators дают scores сопоставимые с human judgment.

**Шаги:**
1. Собрать 30 примеров из production traces (10 хороших, 10 средних, 10 плохих)
2. Human labeling по тем же критериям (faithfulness, relevance, context)
3. Сравнить managed judge scores vs human labels
4. Целевые метрики: TPR > 90%, TNR > 90%
5. Если расхождение — скорректировать промты evaluators

**Артефакт:** `tests/eval/calibration_labels.json`

### Фаза 3: Gold Set + Experiments

**Цель:** Regression testing при изменении промтов/моделей.

**Шаги:**
1. Sync gold set в Langfuse dataset (`langfuse.create_dataset()`)
2. Реализовать `scripts/eval/run_experiment.py` — обёртка над `dataset.run_experiment()`
3. Task function: вызывает RAG graph, evaluators запускаются автоматически через Langfuse
4. Makefile targets: `make eval-experiment`, `make eval-goldset-sync`
5. CI: запускать experiment на PR-ах с изменениями промтов

**SDK код:**
```python
dataset = langfuse.get_dataset("rag-gold-set")

def rag_task(*, item, **kwargs):
    result = await rag_graph.ainvoke({"query": item.input["question"]})
    return {"answer": result["response"], "context": result["context"]}

result = dataset.run_experiment(
    name=f"rag-experiment-{datetime.now():%Y%m%d}",
    task=rag_task,
    evaluators=[],  # managed evaluators запускаются автоматически
)
```

### Фаза 4: Judge в Go/No-Go Gate

**Цель:** Блокировать deploy если качество ниже порога.

**Шаги:**
1. Добавить `judge_gate` в `tests/baseline/thresholds.yaml`:
   ```yaml
   judge_gate:
     faithfulness_mean_gte: 0.75
     answer_relevance_mean_gte: 0.70
     context_relevance_mean_gte: 0.65
   ```
2. В `validate_traces.py` → `compute_aggregates()`: агрегировать judge scores
3. В `evaluate_go_no_go()`: добавить проверку judge thresholds
4. CI integration: `make validate-traces-fast` теперь блокирует на quality

## Что удаляем после миграции

| Файл | Действие |
|------|----------|
| `telegram_bot/evaluation/judges.py` | Удалить (заменён managed evaluators) |
| `telegram_bot/evaluation/prompts.py` | Перенести в Langfuse UI templates, удалить |
| `telegram_bot/evaluation/runner.py` | Удалить (batch + online заменены) |
| `scripts/evaluate_judge.py` | Удалить (`make eval-judge` → managed) |
| `rag_agent.py` online sampling code | Удалить (lines 95-129) |
| `config.py` judge_sample_rate/judge_model | Удалить |

**Сохраняем:** `scoring.py` (40+ метрик), `export_traces_to_dataset.py`, `validate_traces.py`.

## Зависимости

- Langfuse Python SDK v3+ (OTel-based) — **уже используется**
- `propagate_attributes()` — **уже есть** в `observability.py`
- LLM Connection в Langfuse UI — настроить вручную
- Structured output support в judge model

## Риски

| Риск | Митигация |
|------|-----------|
| Русскоязычные промты хуже работают в managed mode | Калибровка (фаза 2) покажет расхождения |
| Langfuse observation-level — beta | Trace-level fallback, custom code как backup |
| Latency managed evaluators | Async, не блокирует пользователя |
| Стоимость judge model на 100% traces | Sampling 5-10% в production |

## Ссылки

- [Langfuse LLM-as-a-Judge docs](https://langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge)
- [Observation-level evals (2026-02-13)](https://langfuse.com/changelog/2026-02-13-observation-level-evals)
- [Migration guide](https://langfuse.com/faq/all/llm-as-a-judge-migration)
- Существующие планы: `docs/plans/2026-02-10-langfuse-llm-judge-goldset-plan.md`, `docs/plans/2026-02-11-llm-judge-plan.md`
