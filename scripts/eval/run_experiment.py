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

    Returns a callable compatible with Langfuse dataset.run_experiment().
    """

    def task(*, item: Any, **kwargs: Any) -> dict[str, str]:
        question = (
            item.input.get("question", "") if isinstance(item.input, dict) else str(item.input)
        )
        result = asyncio.run(graph.ainvoke({"query": question}))
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
    from telegram_bot.services.qdrant_service import QdrantService

    from telegram_bot.config import BotConfig
    from telegram_bot.graph.graph import build_graph
    from telegram_bot.services.bge_m3_client import BGEM3HybridEmbeddings, BGEM3SparseEmbeddings
    from telegram_bot.services.colbert_reranker import ColbertRerankerService

    config = BotConfig()
    embeddings = BGEM3HybridEmbeddings(base_url=config.bge_m3_url)
    sparse = BGEM3SparseEmbeddings(base_url=config.bge_m3_url)
    qdrant = QdrantService(url=config.qdrant_url, collection_name=config.get_collection_name())
    reranker = ColbertRerankerService(base_url=config.bge_m3_url)

    graph = build_graph(
        cache=None,
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
        len(dataset.items),
    )

    result = dataset.run_experiment(
        name=exp_name,
        task=task,
    )

    print(f"Experiment '{result.run_name}' complete")
    print(f"URL: {result.dataset_run_url}")
    langfuse.flush()


if __name__ == "__main__":
    main()
