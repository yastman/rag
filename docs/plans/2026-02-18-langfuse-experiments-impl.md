# Langfuse Experiments Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Синтетический gold set из Qdrant → Langfuse Dataset → `dataset.run_experiment()` для regression testing RAG pipeline.

**Architecture:** Максимально SDK-based. `task` = HTTP POST к RAG API (:8080). Judge evaluators — Langfuse UI managed (0 кода). Единственный code evaluator — `retrieval_recall`. Gold set генерация — Qdrant scroll → LLM Q&A gen → groundedness validation → Langfuse Dataset + JSONL backup.

**Tech Stack:** Langfuse Python SDK v3 (`get_client`, `Evaluation`, `run_experiment`), qdrant-client, httpx, LiteLLM (OpenAI SDK)

**Issue:** #383 | **Design doc:** `docs/plans/2026-02-18-langfuse-experiments-design.md`

**Worktree:** `.worktrees/langfuse-experiments-383` | **Branch:** `feat/langfuse-experiments-383`

---

## Task 1: Extend RAG API — add context to QueryResponse

RAG API (`src/api/`) не возвращает `retrieved_context`. Нужен для `retrieval_recall` evaluator. Два изменения: (1) `_build_retrieved_context` добавить `chunk_location`, (2) `QueryResponse` добавить `context` поле.

**Files:**
- Modify: `telegram_bot/graph/nodes/retrieve.py:24-40`
- Modify: `src/api/schemas.py:20-28`
- Modify: `src/api/main.py:148-155`
- Test: `tests/unit/api/test_rag_api.py` (существующие тесты)

**Step 1: Write the failing test**

File: `tests/unit/api/test_rag_api.py` — добавить тест на `context` поле:

```python
class TestQueryResponseContext:
    """Test that QueryResponse includes retrieved context."""

    def test_context_field_default_empty(self):
        from src.api.schemas import QueryResponse

        resp = QueryResponse(response="answer")
        assert resp.context == []

    def test_context_field_with_data(self):
        from src.api.schemas import QueryResponse

        ctx = [{"content": "text", "score": 0.5, "chunk_location": "seq_3"}]
        resp = QueryResponse(response="answer", context=ctx)
        assert len(resp.context) == 1
        assert resp.context[0]["chunk_location"] == "seq_3"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/api/test_rag_api.py::TestQueryResponseContext -v`
Expected: FAIL — `QueryResponse` has no field `context`

**Step 3: Add `chunk_location` to `_build_retrieved_context`**

File: `telegram_bot/graph/nodes/retrieve.py:24-40` — текущий код:

```python
def _build_retrieved_context(
    results: list[dict[str, Any]],
    limit: int = 5,
) -> list[dict[str, str | float]]:
    """Build curated context snippets for LLM-as-a-Judge evaluation."""
    ctx: list[dict[str, str | float]] = []
    for doc in results[:limit]:
        if not isinstance(doc, dict):
            continue
        text = doc.get("text", "")
        ctx.append(
            {
                "content": text[:_MAX_CONTEXT_SNIPPET],
                "score": doc.get("score", 0),
            }
        )
    return ctx
```

Заменить на:

```python
def _build_retrieved_context(
    results: list[dict[str, Any]],
    limit: int = 5,
) -> list[dict[str, str | float]]:
    """Build curated context snippets for LLM-as-a-Judge evaluation."""
    ctx: list[dict[str, str | float]] = []
    for doc in results[:limit]:
        if not isinstance(doc, dict):
            continue
        text = doc.get("text", "")
        meta = doc.get("metadata", {})
        ctx.append(
            {
                "content": text[:_MAX_CONTEXT_SNIPPET],
                "score": doc.get("score", 0),
                "chunk_location": meta.get("chunk_location", ""),
            }
        )
    return ctx
```

**Step 4: Add `context` field to `QueryResponse`**

File: `src/api/schemas.py:20-28` — добавить поле после `latency_ms`:

```python
class QueryResponse(BaseModel):
    """POST /query response body."""

    response: str = Field(..., description="Generated answer")
    query_type: str = Field(default="", description="Classified query type")
    cache_hit: bool = Field(default=False, description="Whether semantic cache was hit")
    documents_count: int = Field(default=0, description="Number of retrieved documents")
    rerank_applied: bool = Field(default=False, description="Whether reranking was applied")
    latency_ms: float = Field(default=0.0, description="Total pipeline latency in milliseconds")
    context: list[dict] = Field(
        default_factory=list,
        description="Retrieved context documents (for evaluation)",
    )
```

**Step 5: Populate `context` in API endpoint**

File: `src/api/main.py:148-155` — текущий return:

```python
    return QueryResponse(
        response=result.get("response", ""),
        query_type=result.get("query_type", ""),
        cache_hit=result.get("cache_hit", False),
        documents_count=result.get("search_results_count", 0),
        rerank_applied=result.get("rerank_applied", False),
        latency_ms=round(elapsed_ms, 1),
    )
```

Заменить на:

```python
    return QueryResponse(
        response=result.get("response", ""),
        query_type=result.get("query_type", ""),
        cache_hit=result.get("cache_hit", False),
        documents_count=result.get("search_results_count", 0),
        rerank_applied=result.get("rerank_applied", False),
        latency_ms=round(elapsed_ms, 1),
        context=result.get("retrieved_context", []),
    )
```

**Step 6: Run tests**

Run: `uv run pytest tests/unit/api/ -v`
Expected: All PASS

**Step 7: Commit**

```bash
git add telegram_bot/graph/nodes/retrieve.py src/api/schemas.py src/api/main.py tests/unit/api/test_rag_api.py
git commit -m "feat(api): add context field to QueryResponse for experiment evaluation (#383)"
```

---

## Task 2: Experiment thresholds in thresholds.yaml

**Files:**
- Modify: `tests/baseline/thresholds.yaml` (append after `judge:` section, line 47)

**Step 1: Add experiment section**

Append to end of `tests/baseline/thresholds.yaml`:

```yaml

# Experiment quality thresholds (run_experiment evaluators)
experiment:
  faithfulness_mean_gte: 0.75
  answer_relevance_mean_gte: 0.70
  context_relevance_mean_gte: 0.65
  retrieval_recall_mean_gte: 0.60
  composite_score_gte: 0.65
```

**Step 2: Verify YAML is valid**

Run: `python -c "import yaml; yaml.safe_load(open('tests/baseline/thresholds.yaml')); print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add tests/baseline/thresholds.yaml
git commit -m "feat(eval): add experiment quality thresholds (#383)"
```

---

## Task 3: Gold set generator — tests

**Files:**
- Create: `tests/unit/test_generate_gold_set.py`

**Step 1: Write all tests**

File: `tests/unit/test_generate_gold_set.py`

```python
"""Tests for gold set generator."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_point(file_id: str, order: int, text: str, source: str = "doc.md") -> SimpleNamespace:
    """Create a mock Qdrant point with payload."""
    return SimpleNamespace(
        payload={
            "page_content": text,
            "metadata": {
                "file_id": file_id,
                "order": order,
                "source": source,
                "chunk_location": f"seq_{order}",
                "file_name": source,
                "section": "",
            },
        },
    )


class TestScrollCollection:
    async def test_returns_all_points(self):
        from scripts.generate_gold_set import scroll_collection

        mock_client = AsyncMock()
        mock_client.scroll.return_value = (
            [_make_point("f1", 0, "text1"), _make_point("f1", 1, "text2")],
            None,
        )
        points = await scroll_collection(mock_client, "test_col")
        assert len(points) == 2

    async def test_pagination(self):
        from scripts.generate_gold_set import scroll_collection

        mock_client = AsyncMock()
        mock_client.scroll.side_effect = [
            ([_make_point("f1", 0, "t1")], "offset2"),
            ([_make_point("f1", 1, "t2")], None),
        ]
        points = await scroll_collection(mock_client, "test_col", batch_size=1)
        assert len(points) == 2
        assert mock_client.scroll.call_count == 2


class TestGroupByDocument:
    def test_groups_and_sorts(self):
        from scripts.generate_gold_set import group_by_document

        points = [
            _make_point("f1", 2, "C"),
            _make_point("f1", 0, "A"),
            _make_point("f2", 0, "X"),
            _make_point("f1", 1, "B"),
        ]
        docs = group_by_document(points)
        assert len(docs) == 2
        assert [c["text"] for c in docs["f1"]["chunks"]] == ["A", "B", "C"]

    def test_single_document(self):
        from scripts.generate_gold_set import group_by_document

        points = [_make_point("f1", 0, "only")]
        docs = group_by_document(points)
        assert len(docs) == 1
        assert docs["f1"]["chunks"][0]["text"] == "only"


class TestCalculateQuestionsCount:
    @pytest.mark.parametrize(
        ("chunks", "expected_min"),
        [(1, 3), (6, 3), (12, 3), (20, 5), (44, 11), (82, 21)],
    )
    def test_formula_min_3(self, chunks: int, expected_min: int):
        from scripts.generate_gold_set import calculate_questions_count

        result = calculate_questions_count(chunks)
        assert result >= 3
        assert result >= expected_min


class TestExportToJsonl:
    def test_writes_valid_jsonl(self, tmp_path: Path):
        from scripts.generate_gold_set import export_to_jsonl

        items = [
            {
                "query": "Вопрос?",
                "answer": "Ответ",
                "source_doc": "doc.md",
                "source_file_id": "f1",
                "source_chunks": ["seq_0"],
                "difficulty": "easy",
                "type": "factual",
            },
        ]
        out = tmp_path / "gold.jsonl"
        export_to_jsonl(out, items)

        lines = out.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["input"]["query"] == "Вопрос?"
        assert data["expected_output"]["answer"] == "Ответ"
        assert data["metadata"]["source_chunks"] == ["seq_0"]

    def test_multiple_items(self, tmp_path: Path):
        from scripts.generate_gold_set import export_to_jsonl

        items = [
            {"query": f"q{i}", "answer": f"a{i}", "source_doc": "d", "source_file_id": "f",
             "source_chunks": [], "difficulty": "easy", "type": "factual"}
            for i in range(3)
        ]
        out = tmp_path / "gold.jsonl"
        export_to_jsonl(out, items)
        assert len(out.read_text().strip().split("\n")) == 3


class TestUploadToLangfuse:
    def test_creates_dataset_and_items(self):
        from scripts.generate_gold_set import upload_to_langfuse

        mock_lf = MagicMock()
        items = [
            {
                "query": "q?",
                "answer": "a",
                "source_doc": "d",
                "source_file_id": "f1",
                "source_chunks": ["seq_0"],
                "difficulty": "easy",
                "type": "factual",
            },
        ]
        count = upload_to_langfuse(mock_lf, "test-ds", items)
        assert count == 1
        mock_lf.create_dataset.assert_called_once_with(name="test-ds")
        mock_lf.create_dataset_item.assert_called_once()

    def test_empty_items(self):
        from scripts.generate_gold_set import upload_to_langfuse

        mock_lf = MagicMock()
        count = upload_to_langfuse(mock_lf, "test-ds", [])
        assert count == 0


class TestAssembleDocumentText:
    def test_joins_chunks(self):
        from scripts.generate_gold_set import assemble_document_text

        doc = {"chunks": [{"text": "A"}, {"text": "B"}, {"text": "C"}]}
        result = assemble_document_text(doc)
        assert result == "A\n\nB\n\nC"
```

**Step 2: Run tests — expect ImportError**

Run: `uv run pytest tests/unit/test_generate_gold_set.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.generate_gold_set'`

**Step 3: Commit test file**

```bash
git add tests/unit/test_generate_gold_set.py
git commit -m "test(eval): add gold set generator tests — RED phase (#383)"
```

---

## Task 4: Gold set generator — implementation

**Files:**
- Create: `scripts/generate_gold_set.py`

**Step 1: Write implementation**

File: `scripts/generate_gold_set.py`

```python
#!/usr/bin/env python3
"""Generate synthetic gold set from Qdrant for Langfuse experiments.

Scrolls chunks from Qdrant, groups by document, generates Q&A via LLM,
validates groundedness, uploads to Langfuse Dataset + JSONL backup.

Usage:
    uv run python scripts/generate_gold_set.py --collection gdrive_documents_bge
    uv run python scripts/generate_gold_set.py --dry-run --output data/gold_set.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_COLLECTION = "gdrive_documents_bge"
DEFAULT_DATASET_PREFIX = "rag-gold-set"
SCROLL_BATCH_SIZE = 100

# ---------------------------------------------------------------------------
# LLM prompts
# ---------------------------------------------------------------------------

GENERATION_PROMPT = """\
Ты эксперт по недвижимости и иммиграции в Болгарии.

Ниже — текст документа. Сгенерируй {n} вопросов, которые клиент
реально задал бы в Telegram-чате на русском языке.

Требования:
- Вопросы разнообразные: фактические, сравнительные, практические
- Ответ СТРОГО на основе текста, никаких выдуманных фактов
- Сложность: easy (1 чанк), medium (2-3 чанка), hard (весь документ)
- source_chunks: список chunk_location тех чанков, где есть ответ

Доступные chunk_location: {chunk_locations}

Верни ТОЛЬКО JSON массив:
[{{"query": "вопрос", "answer": "ответ", "difficulty": "easy|medium|hard", \
"type": "factual|comparative|practical", "source_chunks": ["seq_3"]}}]

ТЕКСТ ДОКУМЕНТА:
{document_text}"""

GROUNDEDNESS_PROMPT = """\
Проверь, полностью ли ответ основан на тексте документа.

ТЕКСТ: {document_text}

ВОПРОС: {query}
ОТВЕТ: {answer}

Верни ТОЛЬКО JSON: {{"grounded": true|false, "reasoning": "1-2 предложения"}}"""


# ---------------------------------------------------------------------------
# Qdrant scroll
# ---------------------------------------------------------------------------


async def scroll_collection(
    client: Any, collection_name: str, batch_size: int = SCROLL_BATCH_SIZE
) -> list[Any]:
    """Scroll all points from Qdrant (no vectors, payload only)."""
    all_points: list[Any] = []
    offset = None
    while True:
        points, next_offset = await client.scroll(
            collection_name=collection_name,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        all_points.extend(points)
        if next_offset is None:
            break
        offset = next_offset
    logger.info("Scrolled %d points from '%s'", len(all_points), collection_name)
    return all_points


# ---------------------------------------------------------------------------
# Group & assemble
# ---------------------------------------------------------------------------


def group_by_document(points: list[Any]) -> dict[str, dict[str, Any]]:
    """Group points by file_id, sort chunks by order."""
    docs: dict[str, dict[str, Any]] = {}
    for point in points:
        payload = point.payload if hasattr(point, "payload") else point
        meta = payload.get("metadata", {})
        fid = meta.get("file_id", "unknown")
        if fid not in docs:
            docs[fid] = {
                "source": meta.get("source", "unknown"),
                "file_id": fid,
                "chunks": [],
            }
        docs[fid]["chunks"].append(
            {
                "text": payload.get("page_content", ""),
                "order": meta.get("order", 0),
                "chunk_location": meta.get("chunk_location", ""),
                "section": meta.get("section", ""),
            }
        )
    for doc in docs.values():
        doc["chunks"].sort(key=lambda c: c["order"])
    return docs


def assemble_document_text(doc: dict[str, Any]) -> str:
    """Join chunk texts into full document."""
    return "\n\n".join(c["text"] for c in doc["chunks"])


def calculate_questions_count(chunk_count: int) -> int:
    """Scale questions by document size: max(3, round(chunks/4))."""
    return max(3, round(chunk_count / 4))


# ---------------------------------------------------------------------------
# LLM generation
# ---------------------------------------------------------------------------


async def generate_qa_for_document(
    client: Any, model: str, doc: dict[str, Any], n_questions: int
) -> list[dict[str, Any]]:
    """Generate Q&A pairs for a single document via LLM."""
    doc_text = assemble_document_text(doc)
    chunk_locations = [c["chunk_location"] for c in doc["chunks"]]
    prompt = GENERATION_PROMPT.format(
        n=n_questions,
        chunk_locations=json.dumps(chunk_locations),
        document_text=doc_text[:15000],
    )

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "[]"
    except Exception:
        logger.warning("LLM generation failed for '%s'", doc.get("source"), exc_info=True)
        return []

    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            parsed = parsed.get("items", parsed.get("questions", []))
        if not isinstance(parsed, list):
            return []
    except json.JSONDecodeError:
        return []

    items = []
    for qa in parsed:
        if not isinstance(qa, dict) or not qa.get("query") or not qa.get("answer"):
            continue
        items.append(
            {
                "query": qa["query"],
                "answer": qa["answer"],
                "difficulty": qa.get("difficulty", "medium"),
                "type": qa.get("type", "factual"),
                "source_chunks": qa.get("source_chunks", []),
                "source_doc": doc.get("source", ""),
                "source_file_id": doc.get("file_id", ""),
            }
        )
    logger.info(
        "Generated %d/%d Q&A for '%s'", len(items), n_questions, doc.get("source", "?")
    )
    return items


async def validate_groundedness(
    client: Any, model: str, doc_text: str, items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Filter items where answer is not grounded in document text."""
    validated = []
    for item in items:
        prompt = GROUNDEDNESS_PROMPT.format(
            document_text=doc_text[:10000], query=item["query"], answer=item["answer"]
        )
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=256,
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content or "{}")
            if result.get("grounded", False):
                validated.append(item)
            else:
                logger.info(
                    "Filtered: '%s' — %s",
                    item["query"][:60],
                    result.get("reasoning", ""),
                )
        except Exception:
            validated.append(item)  # keep on error
    logger.info("Groundedness: %d/%d passed", len(validated), len(items))
    return validated


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def export_to_jsonl(output_path: Path, items: list[dict[str, Any]]) -> None:
    """Write items to JSONL file in Langfuse dataset format."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for item in items:
            f.write(
                json.dumps(
                    {
                        "input": {"query": item["query"]},
                        "expected_output": {"answer": item["answer"]},
                        "metadata": {
                            "source_doc": item.get("source_doc", ""),
                            "source_file_id": item.get("source_file_id", ""),
                            "source_chunks": item.get("source_chunks", []),
                            "difficulty": item.get("difficulty", ""),
                            "type": item.get("type", ""),
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    logger.info("Exported %d items to %s", len(items), output_path)


def upload_to_langfuse(
    langfuse: Any,
    dataset_name: str,
    items: list[dict[str, Any]],
    model_name: str = "",
) -> int:
    """Upload items to Langfuse Dataset."""
    if not items:
        return 0
    langfuse.create_dataset(name=dataset_name)
    for item in items:
        langfuse.create_dataset_item(
            dataset_name=dataset_name,
            input={"query": item["query"]},
            expected_output={"answer": item["answer"]},
            metadata={
                "source_doc": item.get("source_doc", ""),
                "source_file_id": item.get("source_file_id", ""),
                "source_chunks": item.get("source_chunks", []),
                "difficulty": item.get("difficulty", ""),
                "type": item.get("type", ""),
                "generated_by": model_name,
                "generated_at": datetime.now(UTC).isoformat(),
            },
        )
    langfuse.flush()
    logger.info("Uploaded %d items to Langfuse '%s'", len(items), dataset_name)
    return len(items)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def make_dataset_name(prefix: str = DEFAULT_DATASET_PREFIX) -> str:
    """Generate versioned dataset name."""
    return f"{prefix}-v{datetime.now(UTC).strftime('%Y%m%d')}"


async def run_pipeline(args: argparse.Namespace) -> None:
    """Main pipeline: scroll → group → generate → validate → export."""
    from openai import AsyncOpenAI
    from qdrant_client import AsyncQdrantClient

    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    llm_url = os.getenv("LITELLM_BASE_URL", "http://localhost:4000")
    llm_model = os.getenv("JUDGE_MODEL", "gpt-4o-mini")

    qdrant = AsyncQdrantClient(url=qdrant_url)
    points = await scroll_collection(qdrant, args.collection)
    await qdrant.close()
    if not points:
        logger.error("No points in '%s'", args.collection)
        sys.exit(1)

    docs = group_by_document(points)
    logger.info("Found %d documents (%d chunks)", len(docs), len(points))

    llm = AsyncOpenAI(api_key="not-needed", base_url=llm_url)
    all_items: list[dict[str, Any]] = []

    for doc in docs.values():
        n = args.questions_per_doc or calculate_questions_count(len(doc["chunks"]))
        items = await generate_qa_for_document(llm, llm_model, doc, n)
        if items:
            items = await validate_groundedness(
                llm, llm_model, assemble_document_text(doc), items
            )
        all_items.extend(items)

    logger.info("Total: %d items from %d documents", len(all_items), len(docs))
    if not all_items:
        logger.error("No items generated")
        sys.exit(1)

    export_to_jsonl(Path(args.output), all_items)

    if not args.dry_run:
        from langfuse import Langfuse

        lf = Langfuse()
        dataset_name = args.dataset_name or make_dataset_name()
        upload_to_langfuse(lf, dataset_name, all_items, model_name=llm_model)
    else:
        logger.info("DRY RUN: %d items → %s (no Langfuse upload)", len(all_items), args.output)


def main() -> None:
    """CLI entry point."""
    load_dotenv()
    parser = argparse.ArgumentParser(description="Generate gold set from Qdrant")
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--dataset-name", default=None)
    parser.add_argument("--output", default="data/gold_set.jsonl")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--questions-per-doc", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(run_pipeline(args))


if __name__ == "__main__":
    main()
```

**Step 2: Run tests — expect PASS**

Run: `uv run pytest tests/unit/test_generate_gold_set.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add scripts/generate_gold_set.py
git commit -m "feat(eval): add gold set generator — Qdrant scroll, LLM gen, groundedness (#383)"
```

---

## Task 5: Experiment runner — tests

**Files:**
- Create: `tests/unit/test_run_experiment.py`

**Step 1: Write all tests**

File: `tests/unit/test_run_experiment.py`

```python
"""Tests for experiment runner evaluators."""

from __future__ import annotations

from types import SimpleNamespace


class TestRetrievalRecallEval:
    def test_full_recall(self):
        from scripts.run_experiment import retrieval_recall_eval

        result = retrieval_recall_eval(
            input={"query": "q"},
            output={
                "response": "a",
                "context": [
                    {"chunk_location": "seq_0", "content": "t", "score": 0.5},
                    {"chunk_location": "seq_1", "content": "t", "score": 0.4},
                ],
            },
            expected_output={"answer": "a"},
            metadata={"source_chunks": ["seq_0", "seq_1"]},
        )
        assert result.value == 1.0
        assert result.name == "retrieval_recall"

    def test_partial_recall(self):
        from scripts.run_experiment import retrieval_recall_eval

        result = retrieval_recall_eval(
            input={"query": "q"},
            output={
                "response": "a",
                "context": [{"chunk_location": "seq_0", "content": "t", "score": 0.5}],
            },
            expected_output={"answer": "a"},
            metadata={"source_chunks": ["seq_0", "seq_1"]},
        )
        assert result.value == 0.5

    def test_zero_recall(self):
        from scripts.run_experiment import retrieval_recall_eval

        result = retrieval_recall_eval(
            input={"query": "q"},
            output={"response": "a", "context": [{"chunk_location": "seq_99"}]},
            expected_output={"answer": "a"},
            metadata={"source_chunks": ["seq_0", "seq_1"]},
        )
        assert result.value == 0.0

    def test_no_expected_chunks(self):
        from scripts.run_experiment import retrieval_recall_eval

        result = retrieval_recall_eval(
            input={"query": "q"},
            output={"response": "a", "context": []},
            expected_output={"answer": "a"},
            metadata={},
        )
        assert result.value == 1.0


class TestAvgScoresEvaluator:
    def test_computes_average(self):
        from scripts.run_experiment import avg_scores_evaluator

        item_results = [
            SimpleNamespace(
                evaluations=[SimpleNamespace(name="retrieval_recall", value=1.0)]
            ),
            SimpleNamespace(
                evaluations=[SimpleNamespace(name="retrieval_recall", value=0.5)]
            ),
        ]
        result = avg_scores_evaluator(item_results=item_results)
        assert result.name == "composite_score"
        assert result.value == 0.75

    def test_empty_results(self):
        from scripts.run_experiment import avg_scores_evaluator

        result = avg_scores_evaluator(item_results=[])
        assert result.value == 0

    def test_ignores_other_metrics(self):
        from scripts.run_experiment import avg_scores_evaluator

        item_results = [
            SimpleNamespace(
                evaluations=[
                    SimpleNamespace(name="retrieval_recall", value=0.8),
                    SimpleNamespace(name="other_metric", value=0.1),
                ]
            ),
        ]
        result = avg_scores_evaluator(item_results=item_results)
        assert result.value == 0.8
```

**Step 2: Run tests — expect ImportError**

Run: `uv run pytest tests/unit/test_run_experiment.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Commit test file**

```bash
git add tests/unit/test_run_experiment.py
git commit -m "test(eval): add experiment runner tests — RED phase (#383)"
```

---

## Task 6: Experiment runner — implementation

**Files:**
- Create: `scripts/run_experiment.py`

**Step 1: Write implementation**

File: `scripts/run_experiment.py`

```python
#!/usr/bin/env python3
"""Run Langfuse experiment on gold set — SDK-based.

Task = HTTP POST to RAG API. Judge evaluators = Langfuse UI managed.
Only retrieval_recall is a code evaluator.

Usage:
    uv run python scripts/run_experiment.py --dataset rag-gold-set-v20260218 --name baseline
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
from datetime import UTC, datetime
from typing import Any

import httpx
from dotenv import load_dotenv
from langfuse import Evaluation

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Task: HTTP call to RAG API
# ---------------------------------------------------------------------------


def rag_task(*, item: Any, **kwargs: Any) -> dict[str, Any]:
    """Call RAG API for each dataset item. Returns response + context."""
    rag_api_url = os.getenv("RAG_API_URL", "http://localhost:8080")
    query = item.input["query"] if hasattr(item, "input") else item["input"]["query"]

    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            f"{rag_api_url}/query",
            json={"query": query, "user_id": 0, "channel": "experiment"},
        )
        resp.raise_for_status()
        data = resp.json()

    return {
        "response": data.get("response", ""),
        "context": data.get("context", []),
        "query_type": data.get("query_type", ""),
        "cache_hit": data.get("cache_hit", False),
        "documents_count": data.get("documents_count", 0),
    }


# ---------------------------------------------------------------------------
# Evaluators (only retrieval_recall in code; judges → Langfuse UI)
# ---------------------------------------------------------------------------


def retrieval_recall_eval(
    *, input: dict, output: dict, expected_output: dict, metadata: dict, **kwargs: Any
) -> Evaluation:
    """Check if retrieval found the expected source_chunks."""
    expected = set(metadata.get("source_chunks", []))
    if not expected:
        return Evaluation(
            name="retrieval_recall", value=1.0, comment="no expected chunks"
        )

    found = {
        doc.get("chunk_location", "")
        for doc in output.get("context", [])
        if isinstance(doc, dict)
    }
    recall = len(expected & found) / len(expected)
    return Evaluation(
        name="retrieval_recall",
        value=recall,
        comment=f"{len(expected & found)}/{len(expected)}",
    )


def avg_scores_evaluator(*, item_results: list[Any], **kwargs: Any) -> Evaluation:
    """Run-level: average retrieval_recall across all items."""
    values = [
        e.value
        for r in item_results
        for e in r.evaluations
        if e.name == "retrieval_recall" and e.value is not None
    ]
    avg = sum(values) / len(values) if values else 0
    return Evaluation(
        name="composite_score",
        value=round(avg, 3),
        comment=f"avg of {len(values)} items",
    )


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True, timeout=5
        ).strip()
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point."""
    load_dotenv()
    parser = argparse.ArgumentParser(description="Run Langfuse experiment on gold set")
    parser.add_argument("--dataset", required=True, help="Langfuse dataset name")
    parser.add_argument("--name", default=None, help="Experiment run name")
    parser.add_argument("--description", default="", help="Description")
    parser.add_argument("--concurrency", type=int, default=5)
    args = parser.parse_args()

    from langfuse import get_client

    langfuse = get_client()
    dataset = langfuse.get_dataset(name=args.dataset)
    logger.info("Dataset '%s': %d items", args.dataset, len(dataset.items))

    run_name = args.name or f"exp-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"

    result = dataset.run_experiment(
        name=run_name,
        description=args.description or f"Experiment {run_name}",
        task=rag_task,
        evaluators=[retrieval_recall_eval],
        run_evaluators=[avg_scores_evaluator],
        metadata={
            "model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
            "collection": os.getenv("QDRANT_COLLECTION", "gdrive_documents_bge"),
            "git_sha": _git_sha(),
        },
    )

    print(result.format())
    logger.info("Experiment '%s' complete", run_name)


if __name__ == "__main__":
    main()
```

**Step 2: Run tests — expect PASS**

Run: `uv run pytest tests/unit/test_run_experiment.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add scripts/run_experiment.py
git commit -m "feat(eval): add SDK-based experiment runner — HTTP task + retrieval recall (#383)"
```

---

## Task 7: Makefile targets + gitignore

**Files:**
- Modify: `Makefile` (append after `eval-judge-sample` target, ~line 633)
- Modify: `.gitignore` (add `data/` if not covered)

**Step 1: Add targets to Makefile**

Найти строку `eval-judge-sample:` (line ~631) и после всего блока добавить:

```makefile

.PHONY: eval-gold-gen eval-gold-gen-dry eval-experiment eval-experiment-named

eval-gold-gen: ## Generate gold set from Qdrant → Langfuse Dataset + JSONL
	@echo "$(BLUE)Generating gold set from Qdrant...$(NC)"
	uv run python scripts/generate_gold_set.py --collection gdrive_documents_bge

eval-gold-gen-dry: ## Dry-run gold set generation (JSONL only, no Langfuse)
	@echo "$(BLUE)Generating gold set (dry-run)...$(NC)"
	uv run python scripts/generate_gold_set.py --dry-run --output data/gold_set.jsonl

eval-experiment: ## Run experiment on latest gold set dataset
	@echo "$(BLUE)Running experiment on gold set...$(NC)"
	uv run python scripts/run_experiment.py --dataset $(or $(DATASET),rag-gold-set-v20260218)

eval-experiment-named: ## Run named experiment (NAME=prompt-v2 make eval-experiment-named)
	@echo "$(BLUE)Running experiment '$(NAME)'...$(NC)"
	uv run python scripts/run_experiment.py --dataset $(or $(DATASET),rag-gold-set-v20260218) --name $(NAME)
```

**Step 2: Check `.gitignore` covers `data/`**

Run: `grep -n "^data" .gitignore || echo "NOT FOUND"`

Если `data/` не в `.gitignore`, добавить:

```
data/
```

**Step 3: Verify make targets parse**

Run: `make -n eval-gold-gen-dry 2>&1 | head -3`
Expected: Выводит команду без ошибок

**Step 4: Commit**

```bash
git add Makefile .gitignore
git commit -m "feat(eval): add Makefile targets — eval-gold-gen, eval-experiment (#383)"
```

---

## Task 8: Lint + full test suite

**Step 1: Lint new files**

Run: `uv run ruff check scripts/generate_gold_set.py scripts/run_experiment.py --fix`
Run: `uv run ruff format scripts/generate_gold_set.py scripts/run_experiment.py`

**Step 2: Lint test files**

Run: `uv run ruff check tests/unit/test_generate_gold_set.py tests/unit/test_run_experiment.py --fix`
Run: `uv run ruff format tests/unit/test_generate_gold_set.py tests/unit/test_run_experiment.py`

**Step 3: Run new tests**

Run: `uv run pytest tests/unit/test_generate_gold_set.py tests/unit/test_run_experiment.py -v`
Expected: All PASS

**Step 4: Run full unit test suite (no regressions)**

Run: `uv run pytest tests/unit/ -n auto --timeout=30 -q`
Expected: All PASS, no regressions

**Step 5: Commit lint fixes if any**

```bash
git add -u
git diff --cached --stat
git commit -m "style(eval): lint and format experiment scripts (#383)"
```

---

## Task 9: Smoke test — gold set dry-run

**Requires:** Docker services running (Qdrant + LiteLLM): `make docker-up`

**Step 1: Run dry-run in tmux**

```bash
mkdir -p logs
tmux new-window -n "W-GOLDSET" -c /home/user/projects/rag-fresh/.worktrees/langfuse-experiments-383
tmux send-keys -t "W-GOLDSET" "uv run python scripts/generate_gold_set.py --dry-run 2>&1 | tee logs/gold-set-gen.log; echo '[COMPLETE]'" Enter
```

**Step 2: Monitor and verify**

```bash
tail -f logs/gold-set-gen.log
# Expected output:
# Scrolled 278 points from 'gdrive_documents_bge'
# Found 14 documents (278 chunks)
# Generated X/N Q&A for 'document_name'
# Groundedness: X/Y passed
# Total: ~90 items from 14 documents
# Exported ~90 items to data/gold_set.jsonl
# DRY RUN: ~90 items → data/gold_set.jsonl (no Langfuse upload)
```

**Step 3: Validate JSONL output**

```bash
wc -l data/gold_set.jsonl
head -1 data/gold_set.jsonl | python3 -m json.tool
```

Expected: 60-120 lines, valid JSON with `input.query`, `expected_output.answer`, `metadata.source_chunks`

---

## Task 10: Configure Langfuse UI managed evaluators

**No code.** Configure in Langfuse web UI (http://localhost:3001).

**Step 1:** Open Langfuse UI → Settings → Evaluators

**Step 2:** Create 3 managed evaluators:

| Name | Type | Model | Threshold |
|------|------|-------|-----------|
| `faithfulness` | LLM-as-a-judge | gpt-4o-mini | ≥0.75 |
| `answer_relevance` | LLM-as-a-judge | gpt-4o-mini | ≥0.70 |
| `context_relevance` | LLM-as-a-judge | gpt-4o-mini | ≥0.65 |

Use prompts from `telegram_bot/evaluation/prompts.py` (FAITHFULNESS_PROMPT, ANSWER_RELEVANCE_PROMPT, CONTEXT_RELEVANCE_PROMPT) adapted for Langfuse evaluator template format.

These auto-run on experiment traces, scoring via the same prompts as `judges.py`.

**Step 3:** Verify — run `make eval-experiment` and check scores appear in Langfuse UI.

---

## Summary

| Task | What | Custom code | SDK calls |
|------|------|-------------|-----------|
| 1 | RAG API context field | ~10 lines | — |
| 2 | Thresholds YAML | 6 lines | — |
| 3 | Gold set tests | ~120 lines | — |
| 4 | Gold set generator | ~180 lines | `create_dataset`, `create_dataset_item` |
| 5 | Runner tests | ~90 lines | — |
| 6 | Experiment runner | ~80 lines | `get_dataset`, `run_experiment`, `Evaluation` |
| 7 | Makefile | 15 lines | — |
| 8 | Lint + tests | — | — |
| 9 | Smoke test | — | — |
| 10 | Langfuse UI evaluators | **0 lines** | Managed evaluators |
| **Total** | | **~500 lines** (incl. tests) | |
