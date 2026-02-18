# Managed Evaluators Migration — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Перевести LLM-as-a-Judge с кастомного кода на Langfuse managed evaluators (observation-level), удалить дублирующий код, добавить gold set experiments и quality gate.

**Architecture:** Langfuse managed evaluators автоматически запускаются на каждом observation (span) при ingestion. Промты хранятся в Langfuse UI. Кастомный код judges/runner удаляется. Gold set sync + `run_experiment()` SDK для регрессии. Judge scores интегрируются в `validate_traces.py` Go/No-Go gate.

**Tech Stack:** Langfuse Python SDK v3 (OTel), Langfuse UI evaluators, pytest, Makefile

**Design doc:** `docs/plans/2026-02-18-managed-evaluators-migration.md`

---

## Task 1: Ensure `propagate_attributes` passes tags to observations

Langfuse observation-level evaluators фильтруют по trace-level атрибутам (tags, userId). Нужно убедиться что `propagate_attributes()` вызывается на всех entry points с правильными tags.

**Files:**
- Verify: `telegram_bot/observability.py:146-161`
- Verify: `telegram_bot/bot.py:563-567`
- Verify: `scripts/validate_traces.py` (поиск `propagate_attributes`)

**Step 1: Проверить что bot.py передаёт tags**

Прочитать `telegram_bot/bot.py:563-567` — убедиться что `propagate_attributes` вызывается с `tags=["telegram", "rag", "supervisor"]`.

Run: `grep -n "propagate_attributes" telegram_bot/bot.py`
Expected: Вызов с session_id, user_id, tags.

**Step 2: Проверить что validate_traces.py передаёт tags**

Run: `grep -n "propagate_attributes\|traced_pipeline" scripts/validate_traces.py`
Expected: Вызов с `tags=["validation"]` или аналогичным.

**Step 3: Если validate_traces.py не передаёт tag "validation" — добавить**

Нужен tag `validation` чтобы Langfuse managed evaluators могли фильтровать validation runs (100% sampling) отдельно от production (10% sampling).

Найти в `scripts/validate_traces.py` где вызывается `traced_pipeline` или `propagate_attributes` и добавить `tags=["validation", "rag"]`.

**Step 4: Запустить тест**

Run: `uv run pytest tests/unit/test_validate_queries.py tests/unit/test_validate_aggregates.py -v -n auto`
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/validate_traces.py
git commit -m "feat(eval): add validation tag to trace propagation for managed evaluators (#386)"
```

---

## Task 2: Export judge prompts to JSON for Langfuse UI setup

Промты из `telegram_bot/evaluation/prompts.py` нужно перенести в Langfuse UI как Custom evaluator templates. Создаём JSON-файл с промтами для документации и ручного копирования в UI.

**Files:**
- Read: `telegram_bot/evaluation/prompts.py`
- Create: `docs/eval/managed-evaluator-templates.json`

**Step 1: Создать JSON с промтами для Langfuse UI**

```json
{
  "evaluators": [
    {
      "name": "faithfulness",
      "description": "Проверяет что ответ основан на контексте (no hallucinations)",
      "target": "observation",
      "observation_filter": {
        "type": "SPAN",
        "name": "node-generate"
      },
      "scoring": {
        "type": "NUMERIC",
        "min": 0,
        "max": 1
      },
      "prompt": "Ты — судья качества ответов RAG-системы.\nОцени, насколько ответ основан ТОЛЬКО на предоставленном контексте.\nНе додумывай — оценивай строго по фактам из контекста.\n\nКОНТЕКСТ:\n{{context}}\n\nВОПРОС: {{input}}\nОТВЕТ: {{output}}\n\nШкала:\n- 1.0 — все утверждения в ответе подтверждены контекстом\n- 0.7 — большинство подтверждено, мелкие неточности\n- 0.5 — часть утверждений не подтверждена контекстом\n- 0.3 — существенные утверждения выдуманы\n- 0.0 — ответ полностью выдуман или противоречит контексту\n\nВерни ТОЛЬКО JSON: {\"score\": <float 0-1>, \"reasoning\": \"<1-2 предложения>\"}",
      "variable_mapping": {
        "input": "$.input.query_preview",
        "output": "$.output.response_length",
        "context": "$.input.context_docs_count"
      },
      "notes": "IMPORTANT: node-generate curated span has limited data (capture_input/output=False). Variable mapping needs adaptation — see Task 3."
    },
    {
      "name": "context_relevance",
      "description": "Проверяет релевантность найденных документов вопросу",
      "target": "observation",
      "observation_filter": {
        "type": "SPAN",
        "name": "node-retrieve"
      },
      "scoring": {
        "type": "NUMERIC",
        "min": 0,
        "max": 1
      },
      "prompt": "Оцени, насколько найденные документы релевантны вопросу.\n\nВОПРОС: {{input}}\n\nДОКУМЕНТЫ:\n{{output}}\n\nШкала:\n- 1.0 — все документы высоко релевантны вопросу\n- 0.7 — большинство релевантны, 1-2 нерелевантных\n- 0.5 — примерно половина релевантна\n- 0.3 — мало релевантных документов\n- 0.0 — ни один документ не релевантен\n\nВерни ТОЛЬКО JSON: {\"score\": <float 0-1>, \"reasoning\": \"<1-2 предложения>\"}",
      "variable_mapping": {
        "input": "$.input.query_preview",
        "output": "$.output"
      }
    },
    {
      "name": "answer_relevance",
      "description": "Проверяет что ответ релевантен и полезен для вопроса",
      "target": "trace",
      "scoring": {
        "type": "NUMERIC",
        "min": 0,
        "max": 1
      },
      "prompt": "Оцени, насколько ответ релевантен и полезен для заданного вопроса.\n\nВОПРОС: {{input}}\nОТВЕТ: {{output}}\n\nШкала:\n- 1.0 — ответ полностью отвечает на вопрос, конкретен и полезен\n- 0.7 — отвечает на вопрос, но неполно или с лишней информацией\n- 0.5 — частично релевантен, но упускает ключевые аспекты\n- 0.3 — слабо связан с вопросом\n- 0.0 — не отвечает на вопрос или отвечает на другой вопрос\n\nВерни ТОЛЬКО JSON: {\"score\": <float 0-1>, \"reasoning\": \"<1-2 предложения>\"}",
      "variable_mapping": {
        "input": "$.input.query",
        "output": "$.output.response"
      }
    }
  ],
  "sampling": {
    "production": "10%",
    "validation_tag": "100%"
  },
  "model": "gpt-4o-mini",
  "notes": "Скопировать промты в Langfuse UI → Evaluation → LLM-as-a-Judge → Set up Evaluator"
}
```

**Step 2: Создать директорию и файл**

Run: `mkdir -p docs/eval`
Write file `docs/eval/managed-evaluator-templates.json` с содержимым из Step 1.

**Step 3: Commit**

```bash
git add docs/eval/managed-evaluator-templates.json
git commit -m "docs(eval): export judge prompts as managed evaluator templates (#386)"
```

---

## Task 3: Expose full query/answer/context in curated spans for evaluators

**Проблема:** `node-generate` и `node-retrieve` используют `capture_input=False, capture_output=False` и записывают только curated metadata (query_preview, results_count и т.д.). Managed evaluators нужен ПОЛНЫЙ input/output для оценки.

**Решение:** Добавить отдельные поля `eval_input`/`eval_output` в curated metadata, содержащие полные данные для evaluators (с ограничением длины для cost control).

**Files:**
- Modify: `telegram_bot/graph/nodes/generate.py` (curated span)
- Modify: `telegram_bot/graph/nodes/retrieve.py` (curated span)
- Test: `tests/unit/graph/test_generate_node.py`
- Test: `tests/unit/graph/test_retrieve_node.py`

**Step 1: Прочитать generate_node для понимания curated span**

Read `telegram_bot/graph/nodes/generate.py` — найти где вызывается `lf.update_current_span(output={...})`.

**Step 2: Добавить eval_query и eval_answer в generate_node output metadata**

В `generate_node`, после генерации ответа, в вызов `lf.update_current_span(output={...})` добавить:

```python
lf.update_current_span(output={
    # ... existing curated fields ...
    "response_length": len(response),
    "llm_provider_model": model_name,
    # NEW: full data for managed evaluators
    "eval_query": state.get("query", "")[:2000],
    "eval_answer": response[:3000],
    "eval_context": "\n\n".join(
        f"[{d.get('score', 0):.2f}] {d.get('content', '')[:500]}"
        for d in state.get("retrieved_context", [])[:5]
    ),
})
```

**Step 3: Добавить eval_query и eval_docs в retrieve_node output metadata**

В `retrieve_node`, в вызов `lf.update_current_span(output={...})` добавить:

```python
lf.update_current_span(output={
    # ... existing curated fields ...
    "results_count": len(results),
    # NEW: full data for managed evaluators
    "eval_query": state.get("query", "")[:2000],
    "eval_docs": "\n\n".join(
        f"[{doc.get('score', 0):.2f}] {doc.get('content', '')[:500]}"
        for doc in retrieved_context[:5]
    ),
})
```

**Step 4: Написать тест для generate_node eval fields**

В `tests/unit/graph/test_generate_node.py` добавить тест:

```python
async def test_generate_node_includes_eval_fields(mock_llm, mock_state):
    """Verify eval_query, eval_answer, eval_context in curated span."""
    # ... setup mock state with query, retrieved_context ...
    result = await generate_node(mock_state, config)
    # Assert update_current_span was called with eval_ fields
    span_call = mock_langfuse.update_current_span.call_args
    output = span_call.kwargs.get("output", {})
    assert "eval_query" in output
    assert "eval_answer" in output
    assert "eval_context" in output
```

**Step 5: Написать тест для retrieve_node eval fields**

Аналогичный тест в `tests/unit/graph/test_retrieve_node.py`.

**Step 6: Запустить тесты**

Run: `uv run pytest tests/unit/graph/test_generate_node.py tests/unit/graph/test_retrieve_node.py -v -n auto`
Expected: PASS

**Step 7: Commit**

```bash
git add telegram_bot/graph/nodes/generate.py telegram_bot/graph/nodes/retrieve.py tests/unit/graph/test_generate_node.py tests/unit/graph/test_retrieve_node.py
git commit -m "feat(eval): expose eval_query/eval_answer/eval_context in curated spans (#386)"
```

---

## Task 4: Remove online judge sampling code from rag_agent.py

Custom online sampling больше не нужен — managed evaluators заменяют эту функциональность.

**Files:**
- Modify: `telegram_bot/agents/rag_agent.py:95-129`
- Modify: `telegram_bot/bot.py:556-559` (configurable judge_* params)
- Test: `tests/unit/evaluation/test_online_sampling.py`

**Step 1: Удалить online judge sampling из rag_agent.py**

В `telegram_bot/agents/rag_agent.py`, удалить строки 95-129 (от `# Online LLM-as-a-Judge sampling` до конца блока `_judge_task`).

Также удалить неиспользуемые imports:
- `import random` (line 14)
- `import asyncio` (line 12, если не используется больше)

**Step 2: Удалить judge config из bot.py configurable**

В `telegram_bot/bot.py:552-561`, убрать из `config["configurable"]`:
```python
"judge_sample_rate": self.config.judge_sample_rate,
"judge_model": self.config.judge_model,
"llm_base_url": self.config.llm_base_url,
```

Оставить `llm_base_url` только если используется где-то ещё.

**Step 3: Обновить тест online_sampling**

В `tests/unit/evaluation/test_online_sampling.py` — тест проверял что `run_online_judge` вызывается. Теперь этот тест не нужен. Удалить файл или пометить `@pytest.mark.skip(reason="Migrated to managed evaluators #386")`.

**Step 4: Запустить тесты**

Run: `uv run pytest tests/unit/agents/ -v -n auto`
Expected: PASS (no import errors from removed code)

**Step 5: Commit**

```bash
git add telegram_bot/agents/rag_agent.py telegram_bot/bot.py tests/unit/evaluation/test_online_sampling.py
git commit -m "refactor(eval): remove online judge sampling, replaced by managed evaluators (#386)"
```

---

## Task 5: Remove custom judge code (judges.py, prompts.py, runner.py)

Полное удаление кастомного judge кода. Промты уже экспортированы (Task 2).

**Files:**
- Delete: `telegram_bot/evaluation/judges.py`
- Delete: `telegram_bot/evaluation/prompts.py`
- Delete: `telegram_bot/evaluation/runner.py`
- Modify: `telegram_bot/evaluation/__init__.py`
- Delete: `scripts/evaluate_judge.py`
- Delete: `tests/unit/evaluation/test_judges.py`
- Delete: `tests/unit/evaluation/test_runner.py`
- Delete: `tests/unit/evaluation/test_online_sampling.py` (если не удалён в Task 4)

**Step 1: Удалить judge файлы**

```bash
rm telegram_bot/evaluation/judges.py
rm telegram_bot/evaluation/prompts.py
rm telegram_bot/evaluation/runner.py
rm scripts/evaluate_judge.py
rm tests/unit/evaluation/test_judges.py
rm tests/unit/evaluation/test_runner.py
rm -f tests/unit/evaluation/test_online_sampling.py
```

**Step 2: Обновить __init__.py**

```python
"""LLM-as-a-Judge evaluation — managed by Langfuse evaluators (observation-level).

Custom judge code removed in #386. Prompts live in Langfuse UI.
See docs/eval/managed-evaluator-templates.json for prompt reference.
"""
```

**Step 3: Проверить что ничего не импортирует удалённый код**

Run: `grep -rn "from telegram_bot.evaluation" --include="*.py" | grep -v __pycache__ | grep -v test_`
Expected: Только `__init__.py` и возможно `export_traces_to_dataset.py`.

Если `export_traces_to_dataset.py` импортирует из evaluation — исправить.

**Step 4: Запустить все юнит-тесты**

Run: `uv run pytest tests/unit/ -n auto --timeout=30 -q`
Expected: PASS (no import errors)

**Step 5: Запустить линтер**

Run: `make check`
Expected: PASS

**Step 6: Commit**

```bash
git add -A
git commit -m "refactor(eval): remove custom judge code, replaced by Langfuse managed evaluators (#386)"
```

---

## Task 6: Remove judge config from BotConfig

Config поля `judge_sample_rate` и `judge_model` больше не нужны.

**Files:**
- Modify: `telegram_bot/config.py:348-358`

**Step 1: Удалить поля из BotConfig**

В `telegram_bot/config.py`, удалить:

```python
# LLM-as-a-Judge online sampling
judge_sample_rate: float = Field(
    default=0.0,
    validation_alias=AliasChoices("JUDGE_SAMPLE_RATE", "judge_sample_rate"),
    description="Fraction of queries to evaluate with LLM-as-a-Judge (0.0 = off, 0.2 = 20%)",
)
judge_model: str = Field(
    default="gpt-4o-mini-cerebras-glm",
    validation_alias=AliasChoices("JUDGE_MODEL", "judge_model"),
    description="LLM model for judge evaluation",
)
```

**Step 2: Проверить нет ли ссылок на удалённые поля**

Run: `grep -rn "judge_sample_rate\|judge_model" --include="*.py" | grep -v __pycache__ | grep -v ".pyc"`
Expected: Никаких ссылок (уже удалены в Tasks 4-5).

**Step 3: Запустить тесты конфигурации**

Run: `uv run pytest tests/unit/test_settings.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add telegram_bot/config.py
git commit -m "refactor(eval): remove judge_sample_rate/judge_model config fields (#386)"
```

---

## Task 7: Update Makefile eval targets

Заменить `make eval-judge` и `make eval-judge-sample` на ссылки в документацию.

**Files:**
- Modify: `Makefile`

**Step 1: Прочитать текущие eval targets в Makefile**

Run: `grep -A2 "eval-judge" Makefile`

**Step 2: Заменить targets**

Удалить:
```makefile
eval-judge:
	uv run python scripts/evaluate_judge.py --hours 24 --tag rag

eval-judge-sample:
	uv run python scripts/evaluate_judge.py --hours 48 --sample-rate 0.5
```

**Step 3: Commit**

```bash
git add Makefile
git commit -m "refactor(eval): remove eval-judge Makefile targets, now managed by Langfuse UI (#386)"
```

---

## Task 8: Create gold set sync script

Sync `tests/eval/ground_truth.json` → Langfuse dataset для experiments.

**Files:**
- Create: `scripts/eval/goldset_sync.py`
- Test: `tests/unit/evaluation/test_goldset_sync.py`

**Step 1: Написать failing тест**

```python
# tests/unit/evaluation/test_goldset_sync.py
"""Tests for gold set sync to Langfuse dataset."""

from unittest.mock import MagicMock, patch

import pytest


def test_load_ground_truth_returns_samples():
    from scripts.eval.goldset_sync import load_ground_truth

    samples = load_ground_truth("tests/eval/ground_truth.json")
    assert len(samples) == 55
    assert "question" in samples[0]
    assert "ground_truth" in samples[0]


def test_sync_creates_dataset_items(tmp_path):
    from scripts.eval.goldset_sync import sync_to_langfuse

    mock_langfuse = MagicMock()
    mock_dataset = MagicMock()
    mock_langfuse.get_dataset.side_effect = Exception("not found")
    mock_langfuse.create_dataset.return_value = mock_dataset

    samples = [
        {"id": 1, "question": "Q1", "ground_truth": "A1", "category": "test", "difficulty": "easy"}
    ]
    sync_to_langfuse(mock_langfuse, "test-dataset", samples)

    mock_langfuse.create_dataset.assert_called_once_with(name="test-dataset")
    mock_dataset.create_item.assert_called_once()
```

**Step 2: Запустить тест, убедиться что падает**

Run: `uv run pytest tests/unit/evaluation/test_goldset_sync.py -v`
Expected: FAIL (ImportError — модуль не существует)

**Step 3: Реализовать goldset_sync.py**

```python
#!/usr/bin/env python3
"""Sync ground truth JSON to Langfuse dataset for experiments.

Usage:
    uv run python scripts/eval/goldset_sync.py
    uv run python scripts/eval/goldset_sync.py --dataset-name rag-gold-set-v2
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_GROUND_TRUTH = "tests/eval/ground_truth.json"
DEFAULT_DATASET_NAME = "rag-gold-set"


def load_ground_truth(path: str) -> list[dict[str, Any]]:
    """Load ground truth samples from JSON file."""
    data = json.loads(Path(path).read_text())
    return data["samples"]


def sync_to_langfuse(
    langfuse: Any,
    dataset_name: str,
    samples: list[dict[str, Any]],
) -> int:
    """Sync samples to Langfuse dataset. Creates dataset if not exists.

    Returns number of items created.
    """
    try:
        dataset = langfuse.get_dataset(dataset_name)
        logger.info("Found existing dataset: %s", dataset_name)
    except Exception:
        dataset = langfuse.create_dataset(name=dataset_name)
        logger.info("Created new dataset: %s", dataset_name)

    created = 0
    for sample in samples:
        dataset.create_item(
            input={"question": sample["question"]},
            expected_output={"answer": sample["ground_truth"]},
            metadata={
                "id": sample.get("id"),
                "category": sample.get("category", ""),
                "difficulty": sample.get("difficulty", ""),
                "expected_topics": sample.get("expected_topics", []),
            },
        )
        created += 1

    langfuse.flush()
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync gold set to Langfuse dataset")
    parser.add_argument(
        "--ground-truth", default=DEFAULT_GROUND_TRUTH, help="Path to ground truth JSON"
    )
    parser.add_argument(
        "--dataset-name", default=DEFAULT_DATASET_NAME, help="Langfuse dataset name"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from langfuse import Langfuse

    langfuse = Langfuse()
    samples = load_ground_truth(args.ground_truth)
    count = sync_to_langfuse(langfuse, args.dataset_name, samples)
    print(f"Synced {count} items to dataset '{args.dataset_name}'")


if __name__ == "__main__":
    main()
```

**Step 4: Запустить тест**

Run: `uv run pytest tests/unit/evaluation/test_goldset_sync.py -v`
Expected: PASS

**Step 5: Commit**

```bash
mkdir -p scripts/eval
git add scripts/eval/goldset_sync.py tests/unit/evaluation/test_goldset_sync.py
git commit -m "feat(eval): add gold set sync script for Langfuse experiments (#386)"
```

---

## Task 9: Create experiment runner script

Запускает experiment на gold set dataset с `run_experiment()` SDK.

**Files:**
- Create: `scripts/eval/run_experiment.py`
- Test: `tests/unit/evaluation/test_run_experiment.py`

**Step 1: Написать failing тест**

```python
# tests/unit/evaluation/test_run_experiment.py
"""Tests for experiment runner."""

from unittest.mock import MagicMock

import pytest


def test_build_rag_task_returns_callable():
    from scripts.eval.run_experiment import build_rag_task

    mock_graph = MagicMock()
    task = build_rag_task(mock_graph)
    assert callable(task)
```

**Step 2: Запустить тест, убедиться что падает**

Run: `uv run pytest tests/unit/evaluation/test_run_experiment.py -v`
Expected: FAIL

**Step 3: Реализовать run_experiment.py**

```python
#!/usr/bin/env python3
"""Run RAG experiment on Langfuse gold set dataset.

Usage:
    uv run python scripts/eval/run_experiment.py
    uv run python scripts/eval/run_experiment.py --dataset rag-gold-set --name "prompt-v2"
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_DATASET = "rag-gold-set"


def build_rag_task(graph: Any) -> Any:
    """Build task function that invokes RAG graph for each dataset item.

    Returns a callable compatible with Langfuse run_experiment().
    """

    def task(*, item: Any, **kwargs: Any) -> dict[str, str]:
        question = item.input.get("question", "") if isinstance(item.input, dict) else str(item.input)
        result = asyncio.get_event_loop().run_until_complete(
            graph.ainvoke({"query": question})
        )
        return {
            "answer": result.get("response", ""),
            "context": "\n".join(
                d.get("content", "")[:500]
                for d in result.get("retrieved_context", [])[:5]
            ),
        }

    return task


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RAG experiment on gold set")
    parser.add_argument("--dataset", default=DEFAULT_DATASET, help="Langfuse dataset name")
    parser.add_argument("--name", default=None, help="Experiment name (default: auto-generated)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from langfuse import Langfuse

    from telegram_bot.config import BotConfig
    from telegram_bot.graph.config import GraphConfig
    from telegram_bot.graph.graph import build_graph

    config = BotConfig()
    graph_config = GraphConfig()

    # Build services
    from telegram_bot.services.bge_m3_client import BGEM3HybridEmbeddings, BGEM3SparseEmbeddings
    from telegram_bot.services.qdrant_service import QdrantService

    embeddings = BGEM3HybridEmbeddings(base_url=config.bge_m3_url)
    sparse = BGEM3SparseEmbeddings(base_url=config.bge_m3_url)
    qdrant = QdrantService(url=config.qdrant_url, collection_name=config.get_collection_name())

    graph = build_graph(
        cache=None,
        embeddings=embeddings,
        sparse_embeddings=sparse,
        qdrant=qdrant,
    )

    langfuse = Langfuse()
    dataset = langfuse.get_dataset(args.dataset)
    exp_name = args.name or f"rag-experiment-{datetime.now():%Y%m%d-%H%M}"

    task = build_rag_task(graph)

    logger.info("Running experiment '%s' on dataset '%s' (%d items)", exp_name, args.dataset, len(dataset.items))

    result = dataset.run_experiment(
        name=exp_name,
        task=task,
    )

    print(f"Experiment '{result.run_name}' complete")
    print(f"URL: {result.dataset_run_url}")
    langfuse.flush()


if __name__ == "__main__":
    main()
```

**Step 4: Запустить тест**

Run: `uv run pytest tests/unit/evaluation/test_run_experiment.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/eval/run_experiment.py tests/unit/evaluation/test_run_experiment.py
git commit -m "feat(eval): add experiment runner for gold set regression testing (#386)"
```

---

## Task 10: Add Makefile targets for gold set and experiments

**Files:**
- Modify: `Makefile`

**Step 1: Добавить targets**

```makefile
eval-goldset-sync:
	uv run python scripts/eval/goldset_sync.py

eval-experiment:
	uv run python scripts/eval/run_experiment.py
```

**Step 2: Commit**

```bash
git add Makefile
git commit -m "feat(eval): add eval-goldset-sync and eval-experiment Makefile targets (#386)"
```

---

## Task 11: Integrate judge scores into validate_traces.py Go/No-Go gate

Добавить агрегацию judge scores и проверку thresholds в Go/No-Go gate.

**Files:**
- Modify: `scripts/validate_traces.py` (функции `compute_aggregates` и `evaluate_go_no_go`)
- Reference: `tests/baseline/thresholds.yaml:42-46`
- Test: `tests/unit/test_validate_aggregates.py`

**Step 1: Прочитать текущую реализацию compute_aggregates**

Read `scripts/validate_traces.py` — найти `compute_aggregates` и `evaluate_go_no_go`.

**Step 2: Написать failing тест**

```python
# В tests/unit/test_validate_aggregates.py добавить:

def test_compute_aggregates_includes_judge_scores():
    """Judge scores from enriched traces should be aggregated."""
    from scripts.validate_traces import compute_aggregates

    results = [make_result(scores={
        "judge_faithfulness": 0.8,
        "judge_answer_relevance": 0.7,
        "judge_context_relevance": 0.6,
    })]
    agg = compute_aggregates(results)
    assert "judge_faithfulness_mean" in agg
    assert agg["judge_faithfulness_mean"] == 0.8


def test_go_no_go_fails_on_low_judge_scores():
    """Go/No-Go should fail if judge scores below threshold."""
    from scripts.validate_traces import evaluate_go_no_go

    agg = {
        "judge_faithfulness_mean": 0.5,  # below 0.75
        "judge_answer_relevance_mean": 0.8,
        "judge_context_relevance_mean": 0.7,
        # ... other required fields
    }
    criteria = evaluate_go_no_go(agg, thresholds)
    judge_criteria = [c for c in criteria if "judge" in c.name]
    assert any(not c.passed for c in judge_criteria)
```

**Step 3: Запустить тест, убедиться что падает**

Run: `uv run pytest tests/unit/test_validate_aggregates.py -v -k "judge"`
Expected: FAIL

**Step 4: Добавить judge агрегацию в compute_aggregates**

В `compute_aggregates()`, после существующих агрегаций:

```python
# Judge score aggregation
for judge_name in ("judge_faithfulness", "judge_answer_relevance", "judge_context_relevance"):
    vals = [r.scores.get(judge_name) for r in results if r.scores.get(judge_name) is not None]
    if vals:
        agg[f"{judge_name}_mean"] = round(sum(vals) / len(vals), 3)
        agg[f"{judge_name}_count"] = len(vals)
```

**Step 5: Добавить judge проверку в evaluate_go_no_go**

В `evaluate_go_no_go()`, добавить 3 критерия:

```python
judge_thresholds = thresholds.get("judge", {})
for metric, key in [
    ("judge_faithfulness_mean", "faithfulness_mean_gte"),
    ("judge_answer_relevance_mean", "answer_relevance_mean_gte"),
    ("judge_context_relevance_mean", "context_relevance_mean_gte"),
]:
    threshold = judge_thresholds.get(key)
    value = aggregates.get(metric)
    if threshold is not None and value is not None:
        criteria.append(GoNoGoCriterion(
            name=metric,
            passed=value >= threshold,
            value=value,
            threshold=threshold,
            description=f"{metric} >= {threshold}",
        ))
```

**Step 6: Запустить тест**

Run: `uv run pytest tests/unit/test_validate_aggregates.py -v -n auto`
Expected: PASS

**Step 7: Commit**

```bash
git add scripts/validate_traces.py tests/unit/test_validate_aggregates.py
git commit -m "feat(eval): integrate judge scores into Go/No-Go gate (#386)"
```

---

## Task 12: Update CLAUDE.md and documentation

Обновить документацию, отражающую миграцию.

**Files:**
- Modify: `CLAUDE.md` (eval targets, architecture)
- Modify: `.claude/rules/features/evaluation.md`
- Modify: `.claude/rules/observability.md`

**Step 1: В CLAUDE.md обновить Quick Reference**

Заменить:
```
make eval-judge              # LLM-as-a-Judge batch (24h traces, RAG Triad)
make eval-judge-sample       # LLM-as-a-Judge 50% sample (48h)
```
На:
```
make eval-goldset-sync       # Sync gold set to Langfuse dataset
make eval-experiment         # Run RAG experiment on gold set
```

**Step 2: В evaluation.md обновить LLM-as-a-Judge секцию**

Заменить описание кастомных judges на managed evaluators. Обновить "Key Files" — удалить `judges.py`, `prompts.py`, `runner.py`, добавить `scripts/eval/goldset_sync.py`, `scripts/eval/run_experiment.py`.

**Step 3: В observability.md обновить Judge Scores секцию**

Обновить описание: "Written by Langfuse managed evaluators (observation-level)" вместо "Written by `run_online_judge()`".

**Step 4: Commit**

```bash
git add CLAUDE.md .claude/rules/features/evaluation.md .claude/rules/observability.md
git commit -m "docs(eval): update docs for managed evaluators migration (#386)"
```

---

## Task 13: Run full test suite and lint

Финальная проверка что ничего не сломано.

**Step 1: Линтер**

Run: `make check`
Expected: PASS

**Step 2: Юнит-тесты**

Run: `uv run pytest tests/unit/ -n auto --timeout=30 -q`
Expected: PASS (все тесты, включая новые)

**Step 3: Integration тесты**

Run: `uv run pytest tests/integration/test_graph_paths.py -v`
Expected: PASS

**Step 4: Если что-то падает — исправить и закоммитить фиксы**

---

## Summary

| Task | Описание | Commit message |
|------|----------|---------------|
| 1 | Проверить propagate_attributes tags | `feat(eval): add validation tag to trace propagation` |
| 2 | Экспортировать промты в JSON | `docs(eval): export judge prompts as managed evaluator templates` |
| 3 | Добавить eval_ поля в curated spans | `feat(eval): expose eval_query/eval_answer/eval_context in curated spans` |
| 4 | Удалить online judge sampling | `refactor(eval): remove online judge sampling` |
| 5 | Удалить custom judge code | `refactor(eval): remove custom judge code` |
| 6 | Удалить judge config из BotConfig | `refactor(eval): remove judge config fields` |
| 7 | Обновить Makefile targets | `refactor(eval): remove eval-judge Makefile targets` |
| 8 | Gold set sync script | `feat(eval): add gold set sync script` |
| 9 | Experiment runner script | `feat(eval): add experiment runner` |
| 10 | Makefile targets для gold set | `feat(eval): add eval-goldset-sync and eval-experiment targets` |
| 11 | Judge scores в Go/No-Go gate | `feat(eval): integrate judge scores into Go/No-Go gate` |
| 12 | Обновить документацию | `docs(eval): update docs for managed evaluators migration` |
| 13 | Финальная проверка | (no commit if clean) |
