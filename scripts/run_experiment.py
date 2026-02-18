#!/usr/bin/env python3
"""Run Langfuse experiment on gold set — SDK-based.

Task = HTTP POST to RAG API. Judge evaluators = Langfuse UI managed.
Only retrieval_recall is a code evaluator.

Usage:
    uv run python scripts/run_experiment.py --dataset rag-gold-set-v1 --name baseline
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
        return Evaluation(name="retrieval_recall", value=1.0, comment="no expected chunks")

    found = {
        doc.get("chunk_location", "") for doc in output.get("context", []) if isinstance(doc, dict)
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
    parser.add_argument(
        "--version",
        default=None,
        help="Dataset version timestamp in ISO 8601 UTC, e.g. 2026-02-18T12:00:00Z",
    )
    args = parser.parse_args()

    from langfuse import get_client

    langfuse = get_client()
    version_dt = None
    if args.version:
        version_dt = datetime.fromisoformat(args.version).astimezone(UTC)

    dataset = langfuse.get_dataset(name=args.dataset, version=version_dt)
    logger.info("Dataset '%s': %d items", args.dataset, len(dataset.items))

    run_name = args.name or f"exp-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"

    result = dataset.run_experiment(
        name="rag-gold-set-regression",
        run_name=run_name,
        description=args.description or f"Experiment {run_name}",
        task=rag_task,
        evaluators=[retrieval_recall_eval],
        run_evaluators=[avg_scores_evaluator],
        max_concurrency=args.concurrency,
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
