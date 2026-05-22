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
import hashlib
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
    logger.info("Generated %d/%d Q&A for '%s'", len(items), n_questions, doc.get("source", "?"))
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
        f.writelines(
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
            for item in items
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
    try:
        langfuse.get_dataset(name=dataset_name)
    except Exception:
        langfuse.create_dataset(name=dataset_name)
    for item in items:
        langfuse.create_dataset_item(
            dataset_name=dataset_name,
            input={"query": item["query"]},
            expected_output={"answer": item["answer"]},
            id=(
                f"{item.get('source_file_id', 'na')}::"
                f"{hashlib.sha256(item['query'].encode()).hexdigest()[:16]}"
            ),
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
            items = await validate_groundedness(llm, llm_model, assemble_document_text(doc), items)
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
