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
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)

DEFAULT_DATASET = "rag-gold-set"
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


class _NoopCache:
    """Minimal async cache adapter for offline eval experiments."""

    async def get_embedding(self, query: str) -> None:
        return None

    async def store_embedding(self, query: str, embedding: list[float]) -> None:
        return None

    async def get_sparse_embedding(self, query: str) -> None:
        return None

    async def store_sparse_embedding(self, query: str, sparse: dict[str, Any]) -> None:
        return None

    async def check_semantic(
        self,
        query: str,
        vector: list[float],
        query_type: str,
        language: str = "ru",
        user_id: int | None = None,
    ) -> None:
        return None

    async def store_semantic(
        self,
        query: str,
        response: str,
        vector: list[float],
        query_type: str,
        language: str = "ru",
        user_id: int | None = None,
    ) -> None:
        return None

    async def get_search_results(self, dense_vector: list[float]) -> None:
        return None

    async def store_search_results(
        self,
        dense_vector: list[float],
        filters: dict[str, Any] | None,
        results: list[dict[str, Any]],
    ) -> None:
        return None


def _build_eval_state(question: str) -> dict[str, Any]:
    """Build valid RAG state for non-Telegram experiment execution."""
    from telegram_bot.graph.state import make_initial_state

    return make_initial_state(
        user_id=0,
        session_id=f"eval-{uuid.uuid4().hex[:12]}",
        query=question,
    )


def build_rag_task(graph: Any) -> Any:
    """Build task function that invokes RAG graph for each dataset item.

    Returns a callable compatible with Langfuse dataset.run_experiment().
    """

    def task(*, item: Any, **kwargs: Any) -> dict[str, str]:
        question = item.input.get("query", "") if isinstance(item.input, dict) else str(item.input)
        result = asyncio.run(graph.ainvoke(_build_eval_state(question)))
        return {
            "answer": result.get("response", ""),
            "context": "\n".join(
                d.get("content", "")[:500] for d in result.get("retrieved_context", [])[:5]
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
    from telegram_bot.graph.graph import build_graph
    from telegram_bot.integrations.embeddings import BGEM3HybridEmbeddings, BGEM3SparseEmbeddings
    from telegram_bot.services.colbert_reranker import ColbertRerankerService
    from telegram_bot.services.qdrant import QdrantService

    config = BotConfig()
    cache = _NoopCache()
    embeddings = BGEM3HybridEmbeddings(base_url=config.bge_m3_url)
    sparse = BGEM3SparseEmbeddings(base_url=config.bge_m3_url)
    qdrant = QdrantService(
        url=config.qdrant_url,
        api_key=config.qdrant_api_key or None,
        collection_name=config.qdrant_collection,
        quantization_mode=config.qdrant_quantization_mode,
        timeout=config.qdrant_timeout,
    )
    reranker = (
        ColbertRerankerService(base_url=config.bge_m3_url)
        if config.rerank_provider == "colbert"
        else None
    )

    graph = build_graph(
        cache=cache,
        embeddings=embeddings,
        sparse_embeddings=sparse,
        qdrant=qdrant,
        reranker=reranker,
    )

    langfuse = Langfuse()
    dataset = langfuse.get_dataset(args.dataset)
    exp_name = args.name or f"rag-experiment-{datetime.now():%Y%m%d-%H%M}"

    task = build_rag_task(graph)

    logger.info(
        "Running experiment '%s' on dataset '%s' (%d items)",
        exp_name,
        args.dataset,
        len(getattr(dataset, "items", [])),
    )

    try:
        result = dataset.run_experiment(
            name=exp_name,
            task=task,
        )
        print(f"Experiment '{result.run_name}' complete")
        print(f"URL: {result.dataset_run_url}")
    finally:
        langfuse.flush()
        asyncio.run(qdrant.close())


if __name__ == "__main__":
    main()
