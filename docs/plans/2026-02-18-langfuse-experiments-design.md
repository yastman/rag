# Langfuse Experiments: Gold Set + Automated Regression Testing

**Дата:** 2026-02-18
**Статус:** Draft
**Цель:** Синтетический gold set из Qdrant → Langfuse Dataset → `run_experiment()` для regression testing после изменений в RAG pipeline.

---

## Точечный Review Patch (2026-02-18)

1. API `langfuse` сверен на версии из lockfile: для версионного датасета используется `langfuse.get_dataset(name=..., version=<UTC datetime>)`, а в `dataset.run_experiment(...)` доступны `run_name`, `max_concurrency`, `metadata`.
2. Для `retrieval_recall` читаем `chunk_location` из top-level поля контекста (`doc["chunk_location"]`), так как именно его добавляем в API-ответ.
3. Upload gold set должен быть idempotent: `create_dataset` вызывать только при отсутствии датасета, а `create_dataset_item` лучше делать со стабильным `id` для dedupe.
4. В MVP этого issue не включаем CLI-флаги `--append` и `--cross-document-only` (вынести в follow-up после базового pipeline).
5. В `Makefile` не хардкодим датасет по дате; передаём `DATASET=...` явно при запуске.

---

## Контекст

### Текущее состояние

| Компонент | Что есть | Чего нет |
|-----------|----------|----------|
| `scripts/export_traces_to_dataset.py` | Экспорт low-scoring traces в Langfuse Dataset | Экспорт high-scoring traces |
| `telegram_bot/evaluation/judges.py` | RAG Triad (faithfulness, relevance, context) | Обёртка как experiment evaluators |
| `scripts/validate_traces.py` | 4-phase validation с Go/No-Go | Прогон по фиксированному gold set |
| `tests/baseline/` | Regression detection по метрикам | Regression detection по качеству ответов |
| Langfuse SDK v3 | `create_dataset`, `create_dataset_item`, `run_experiment()`, `get_dataset(version=...)` | стабильный процесс экспериментов для текущего проекта |

### Qdrant: gdrive_documents_bge

- **278 чанков**, **14 документов** (болгарская недвижимость, ВНЖ, евро, фирмы)
- Payload: `page_content`, `metadata.file_id`, `metadata.order`, `metadata.source`, `metadata.section`
- Vectors: dense (BGE-M3, 1024-dim) + sparse (BM42)

---

## Архитектура

```
┌─────────────────────────────────────────────────────┐
│                 GENERATION (однократно)               │
│                                                       │
│  Qdrant scroll (278 чанков)                          │
│       ↓                                               │
│  Группировка по file_id (14 документов)              │
│       ↓                                               │
│  LLM генерация per-document:                         │
│    - N = max(3, round(chunks/4)) вопросов            │
│    - Типы: factual, comparative, practical           │
│    - Эталонные ответы строго из текста               │
│       ↓                                               │
│  Groundedness validation (LLM проверка)              │
│       ↓                                               │
│  Cross-document вопросы (5-10 штук)                  │
│       ↓                                               │
│  Upload → Langfuse Dataset + JSONL бэкап             │
│  (~90-120 items)                                     │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│              EXPERIMENT RUN (после изменений)         │
│                                                       │
│  langfuse.get_dataset("rag-gold-set-v1")             │
│       ↓                                               │
│  dataset.run_experiment(                              │
│      name="after-prompt-v2",                         │
│      task=rag_task,           ← LangGraph pipeline   │
│      evaluators=[                                     │
│          faithfulness_eval,   ← обёртка judges.py    │
│          relevance_eval,                              │
│          context_eval,                                │
│          retrieval_recall,    ← новый: нашли чанки?  │
│      ],                                               │
│      run_evaluators=[avg_scores],                    │
│      max_concurrency=5,                               │
│      metadata={...config...}                         │
│  )                                                    │
│       ↓                                               │
│  result.format()  → CLI таблица                      │
│  result.dataset_run_url → Langfuse UI сравнение      │
└─────────────────────────────────────────────────────┘
```

---

## Компонент 1: Gold Set Generator

### Скрипт: `scripts/generate_gold_set.py`

**Вход:** Qdrant collection `gdrive_documents_bge` (278 чанков, 14 документов)

**Выход:** Langfuse Dataset + `data/gold_set.jsonl` бэкап

### Алгоритм

1. **Scroll** — вычитать все 278 чанков из Qdrant (без векторов, только payload)
2. **Группировка** — собрать чанки по `metadata.file_id`, отсортировать по `metadata.order`
3. **Склейка** — для каждого документа собрать полный текст из `page_content`
4. **Генерация** — для каждого документа вызвать LLM:
   - Количество вопросов: `N = max(3, round(chunk_count / 4))`
   - Промпт генерирует JSON массив `[{query, answer, difficulty, type, source_chunks}]`
   - Типы вопросов: `factual` (факт из текста), `comparative` (сравнение), `practical` (как сделать?)
   - Difficulty: `easy` (прямой ответ из 1 чанка), `medium` (синтез 2-3 чанков), `hard` (требует понимания контекста)
5. **Валидация** — LLM-проверка: "Ответ полностью следует из текста? Нет ли выдуманных фактов?"
6. **Cross-document** — сгенерировать 5-10 вопросов, требующих информации из 2+ документов
7. **Upload** — `langfuse.create_dataset()` + `create_dataset_item()` для каждого item
8. **Бэкап** — сохранить в `data/gold_set.jsonl`

### Масштабирование по размеру документа

| Документ | Чанков | Вопросов |
|----------|--------|----------|
| AIRBNB/Booking запреты | 82 | ~20 |
| Польша vs Болгария | 44 | ~11 |
| ВНЖ/ПМЖ правила 2026 | 18 | ~5 |
| Купить квартиру | 18 | ~5 |
| Не потерять деньги | 15 | ~4 |
| Digital Nomad виза | 15 | ~4 |
| Евро прогноз | 14 | ~4 |
| ВНЖ для иностранцев | 13 | ~3 |
| Ошибка ценой в квартиру | 12 | ~3 |
| Такса поддержки | 12 | ~3 |
| Деньги на границе | 12 | ~3 |
| Старите Къщи | 10 | ~3 |
| Открыть фирму | 7 | ~3 |
| Демо дом.xlsx | 6 | ~3 |
| **Cross-document** | — | ~8 |
| **Итого** | **278** | **~82 + 8 = ~90** |

### Dataset Item Structure

```python
langfuse.create_dataset_item(
    dataset_name="rag-gold-set-v1",
    input={"query": "Какие документы нужны покупателю квартиры в Болгарии?"},
    expected_output={
        "answer": "Покупателю нужны: загранпаспорт, ИНН (ЕГН для иностранцев), ..."
    },
    metadata={
        "source_doc": "Как купить квартиру в Болгарии...",
        "source_file_id": "a1b2c3d4e5f6g7h8",
        "source_chunks": ["seq_3", "seq_5", "seq_7"],
        "difficulty": "medium",
        "type": "factual",
        "generated_by": "cerebras/llama-3.3-70b",
        "generated_at": "2026-02-18T12:00:00Z"
    }
)
```

### CLI

```bash
# Полная генерация + upload в Langfuse
uv run python scripts/generate_gold_set.py --collection gdrive_documents_bge

# Dry-run: генерация без upload, только JSONL
uv run python scripts/generate_gold_set.py --dry-run --output data/gold_set.jsonl

# Кастомное количество вопросов на документ
uv run python scripts/generate_gold_set.py --questions-per-doc 10
```

### LLM промпт для генерации

```
Ты эксперт по недвижимости и иммиграции в Болгарии.

Ниже — текст документа. Сгенерируй {n} вопросов, которые клиент
реально задал бы в Telegram-чате на русском языке.

Требования:
- Вопросы должны быть разнообразными: фактические, сравнительные, практические
- Ответ СТРОГО на основе текста, никаких выдуманных фактов
- Сложность: easy (1 чанк), medium (2-3 чанка), hard (весь документ)
- source_chunks: список chunk_location тех чанков, где есть ответ

Формат JSON:
[
  {
    "query": "вопрос на русском",
    "answer": "полный ответ на основе текста",
    "difficulty": "easy|medium|hard",
    "type": "factual|comparative|practical",
    "source_chunks": ["seq_3", "seq_5"]
  }
]

ТЕКСТ ДОКУМЕНТА:
{document_text}
```

---

## Компонент 2: Experiment Runner

### Скрипт: `scripts/run_experiment.py`

**Вход:** Langfuse Dataset name + конфигурация эксперимента

**Выход:** Langfuse Dataset Run + CLI таблица результатов

### Task Function

```python
from langfuse import get_client

langfuse = get_client()

async def rag_task(*, item, **kwargs):
    """Прогоняет один item через RAG pipeline."""
    query = item.input["query"]

    # Вызов LangGraph pipeline (тот же что в боте)
    result = await run_rag_pipeline(query)

    return {
        "response": result["response"],
        "context": result.get("retrieved_context", []),
        "scores": result.get("scores", {}),
        "latency_ms": result.get("latency_ms"),
    }
```

### Evaluators

**Item-level** (оценка каждого Q&A):

```python
from langfuse import Evaluation
from telegram_bot.evaluation.judges import (
    judge_answer_relevance,
    judge_context_relevance,
    judge_faithfulness,
)

def _context_to_text(context_items):
    return "\n\n".join(
        str(doc.get("content", ""))
        for doc in context_items
        if isinstance(doc, dict) and doc.get("content")
    )

async def faithfulness_eval(*, input, output, expected_output, metadata, **kwargs):
    """Обёртка над существующим judge_faithfulness из judges.py."""
    result = await judge_faithfulness(
        client=judge_client,  # AsyncOpenAI/LiteLLM client
        model=judge_model,
        query=input["query"],
        answer=output["response"],
        context=_context_to_text(output.get("context", [])),
    )
    return Evaluation(name="faithfulness", value=result.score or 0.0, comment=result.reasoning)

async def answer_relevance_eval(*, input, output, expected_output, metadata, **kwargs):
    """Обёртка над judge_answer_relevance."""
    result = await judge_answer_relevance(
        client=judge_client,
        model=judge_model,
        query=input["query"],
        answer=output["response"],
    )
    return Evaluation(name="answer_relevance", value=result.score or 0.0, comment=result.reasoning)

async def context_relevance_eval(*, input, output, expected_output, metadata, **kwargs):
    """Обёртка над judge_context_relevance."""
    result = await judge_context_relevance(
        client=judge_client,
        model=judge_model,
        query=input["query"],
        context=_context_to_text(output.get("context", [])),
    )
    return Evaluation(name="context_relevance", value=result.score or 0.0, comment=result.reasoning)

def retrieval_recall_eval(*, input, output, expected_output, metadata, **kwargs):
    """Новый: проверяет нашёл ли retrieval нужные source_chunks."""
    expected_chunks = set(metadata.get("source_chunks", []))
    if not expected_chunks:
        return Evaluation(name="retrieval_recall", value=1.0, comment="no expected chunks")

    retrieved_chunks = set()
    for doc in output.get("context", []):
        loc = doc.get("chunk_location", "")
        if loc:
            retrieved_chunks.add(loc)

    found = expected_chunks & retrieved_chunks
    recall = len(found) / len(expected_chunks)
    return Evaluation(
        name="retrieval_recall",
        value=recall,
        comment=f"Found {len(found)}/{len(expected_chunks)}: {found}"
    )
```

**Run-level** (агрегация по всему эксперименту):

```python
def avg_scores_evaluator(*, item_results, **kwargs):
    """Средние скоры по всем items."""
    metrics = {}
    for name in ["faithfulness", "answer_relevance", "context_relevance", "retrieval_recall"]:
        values = [
            e.value for r in item_results
            for e in r.evaluations
            if e.name == name and e.value is not None
        ]
        if values:
            metrics[name] = sum(values) / len(values)

    # Возвращаем composite score
    avg_all = sum(metrics.values()) / len(metrics) if metrics else 0
    return Evaluation(
        name="composite_score",
        value=round(avg_all, 3),
        comment=f"Averages: {metrics}"
    )
```

### Запуск эксперимента

```python
dataset = langfuse.get_dataset("rag-gold-set-v1")

result = dataset.run_experiment(
    name="after-prompt-change-v2",
    description="Тест после изменения system prompt generate_node",
    task=rag_task,
    evaluators=[
        faithfulness_eval,
        answer_relevance_eval,
        context_relevance_eval,
        retrieval_recall_eval,
    ],
    run_evaluators=[avg_scores_evaluator],
    max_concurrency=5,
    metadata={
        "model": "cerebras/llama-3.3-70b",
        "change": "updated system prompt v2",
        "collection": "gdrive_documents_bge",
        "git_sha": get_git_sha(),
    }
)

print(result.format())
print(f"Langfuse UI: {result.dataset_run_url}")
```

### CLI

```bash
# Запуск эксперимента
uv run python scripts/run_experiment.py --dataset rag-gold-set-v1 --name "baseline-v1"

# С описанием изменений
uv run python scripts/run_experiment.py \
    --dataset rag-gold-set-v1 \
    --name "prompt-v2" \
    --description "Updated system prompt" \
    --concurrency 3

# На версированном датасете
uv run python scripts/run_experiment.py \
    --dataset rag-gold-set-v1 \
    --version "2026-02-18T12:00:00Z" \
    --name "regression-check"
```

### Makefile

```makefile
eval-gold-gen:          ## Generate gold set from Qdrant → Langfuse Dataset
	uv run python scripts/generate_gold_set.py --collection gdrive_documents_bge

eval-gold-gen-dry:      ## Dry-run gold set generation (JSONL only)
	uv run python scripts/generate_gold_set.py --dry-run --output data/gold_set.jsonl

eval-experiment:        ## Run experiment on gold set (usage: make eval-experiment DATASET=rag-gold-set-v1)
	uv run python scripts/run_experiment.py --dataset $(DATASET)

eval-experiment-named:  ## Run named experiment (NAME=prompt-v2 make eval-experiment-named)
	uv run python scripts/run_experiment.py --dataset $(DATASET) --name $(NAME)
```

---

## Компонент 3: Интеграция с существующей инфраструктурой

### Переиспользование кода

| Существующий модуль | Как используем |
|---------------------|----------------|
| `telegram_bot/evaluation/judges.py` | `judge_*()` async функции → обёртки в experiment evaluators |
| `telegram_bot/evaluation/prompts.py` | Промпты для faithfulness/relevance/context judges |
| `telegram_bot/services/qdrant.py` | `QdrantService` для scroll чанков при генерации gold set |
| `telegram_bot/graph/` | LangGraph pipeline как `task` в `run_experiment()` |
| `telegram_bot/integrations/langfuse.py` | Langfuse client init |
| `tests/baseline/thresholds.yaml` | Пороги для judge scores |

### Новые файлы

```
scripts/
├── generate_gold_set.py    # Генерация gold set из Qdrant
├── run_experiment.py       # Запуск экспериментов через Langfuse SDK
data/
├── gold_set.jsonl          # JSONL бэкап gold set (gitignored)
```

### Конфигурация (thresholds.yaml — дополнение)

```yaml
# Добавить в tests/baseline/thresholds.yaml
experiment:
  faithfulness_mean_gte: 0.75
  answer_relevance_mean_gte: 0.70
  context_relevance_mean_gte: 0.65
  retrieval_recall_mean_gte: 0.60
  composite_score_gte: 0.65
```

---

## Компонент 4: Data Flow

```
                    GENERATION (once)
                    ═══════════════

  ┌──────────┐     ┌──────────────┐     ┌─────────────┐
  │  Qdrant  │────→│ generate_    │────→│  Langfuse   │
  │  278     │     │ gold_set.py  │     │  Dataset    │
  │  chunks  │     │              │     │  ~90 items  │
  └──────────┘     │  LLM gen +   │     └──────┬──────┘
                   │  validation  │            │
                   └──────┬───────┘            │
                          │                    │
                          ▼                    │
                   ┌──────────────┐            │
                   │ gold_set.    │            │
                   │ jsonl        │            │
                   │ (backup)     │            │
                   └──────────────┘            │
                                               │
                    EXPERIMENT (per change)     │
                    ══════════════════════      │
                                               │
  ┌──────────┐     ┌──────────────┐     ┌──────┴──────┐
  │ RAG      │◄────│ run_         │◄────│  Dataset    │
  │ Pipeline │     │ experiment.  │     │  items      │
  │ LangGraph│     │ py           │     └─────────────┘
  └──────────┘     │              │
                   │  evaluators: │     ┌─────────────┐
                   │  - faith.    │────→│  Langfuse   │
                   │  - relevance │     │  Dataset    │
                   │  - context   │     │  Run        │
                   │  - recall    │     │  (compare   │
                   └──────────────┘     │   in UI)    │
                                        └─────────────┘
```

---

## Workflow для разработчика

```
1. Изменил prompt / retrieval / model
       ↓
2. make eval-experiment  (или с именем: NAME=prompt-v2 make eval-experiment-named)
       ↓
3. CLI выводит таблицу:
   ┌────────────────────┬───────┬────────┐
   │ Metric             │ Value │ Status │
   ├────────────────────┼───────┼────────┤
   │ faithfulness (avg) │ 0.82  │ PASS   │
   │ answer_relevance   │ 0.78  │ PASS   │
   │ context_relevance  │ 0.71  │ PASS   │
   │ retrieval_recall   │ 0.65  │ PASS   │
   │ composite_score    │ 0.74  │ PASS   │
   └────────────────────┴───────┴────────┘
       ↓
4. Langfuse UI → Datasets → rag-gold-set-v1 → Runs
   Сравниваешь baseline-v1 vs prompt-v2 визуально
```

---

## Ограничения и риски

| Риск | Митигация |
|------|-----------|
| LLM генерирует некорректные ответы | Groundedness validation + ручная проверка первого батча |
| Gold set устаревает при обновлении Qdrant | Регенерация: `make eval-gold-gen` после ingestion |
| Evaluator LLM дорогой | Используем cerebras (бесплатный tier), max_concurrency=5 |
| Experiment run долгий (~90 items × LLM) | ~15-20 минут, запуск в tmux |
| Langfuse SDK breaking changes | Версия зафиксирована в pyproject.toml |

---

## Зависимости

- `langfuse` Python SDK v3 (уже в проекте)
- `qdrant-client` (уже в проекте)
- LiteLLM для генерации и evaluation (уже в проекте)
- Qdrant запущен с данными (`make docker-up`)

## Тесты

- `tests/unit/test_generate_gold_set.py` — генерация, группировка, валидация
- `tests/unit/test_run_experiment.py` — evaluators, task function, CLI args
