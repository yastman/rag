#!/usr/bin/env python3
"""
Evaluation Framework for RAG Pipeline
Metrics: Recall@K, NDCG@K, Failure Rate
"""

import json

import numpy as np
import requests

from config import (
    BGE_M3_URL,
    EVALUATION_QUERIES_FILE,
    QDRANT_API_KEY,
    QDRANT_URL,
)


def recall_at_k(retrieved_ids: list[int], relevant_ids: list[int], k: int) -> float:
    """Recall@K: % of relevant items found in top-K."""
    top_k = set(retrieved_ids[:k])
    relevant = set(relevant_ids)
    if len(relevant) == 0:
        return 0.0
    return len(top_k.intersection(relevant)) / len(relevant)


def ndcg_at_k(retrieved_ids: list[int], ground_truth: dict[int, int], k: int) -> float:
    """NDCG@K: Normalized Discounted Cumulative Gain."""
    relevances = [ground_truth.get(id, 0) for id in retrieved_ids[:k]]
    dcg = sum(rel / np.log2(i + 2) for i, rel in enumerate(relevances))

    ideal_relevances = sorted(ground_truth.values(), reverse=True)[:k]
    idcg = sum(rel / np.log2(i + 2) for i, rel in enumerate(ideal_relevances))

    return dcg / idcg if idcg > 0 else 0.0


def hybrid_search(collection_name: str, query: str, limit: int = 10) -> list[dict]:
    """Perform hybrid search on Qdrant collection."""
    # Get embeddings for query
    embed_resp = requests.post(f"{BGE_M3_URL}/encode/hybrid", json={"texts": [query]}, timeout=30)
    embed_resp.raise_for_status()
    embed = embed_resp.json()

    # Hybrid search with ColBERT reranking
    search_payload = {
        "prefetch": [
            {
                "query": {
                    "indices": embed["lexical_weights"][0]["indices"],
                    "values": embed["lexical_weights"][0]["values"],
                },
                "using": "sparse",
                "limit": 20,
            },
            {"query": embed["dense_vecs"][0], "using": "dense", "limit": 20},
        ],
        "query": embed["colbert_vecs"][0],
        "using": "colbert",
        "limit": limit,
        "with_payload": True,
    }

    search_resp = requests.post(
        f"{QDRANT_URL}/collections/{collection_name}/points/query",
        json=search_payload,
        headers={"api-key": QDRANT_API_KEY},
        timeout=30,
    )
    search_resp.raise_for_status()
    return search_resp.json()["result"]["points"]


def evaluate_collection(collection_name: str, eval_file: str = EVALUATION_QUERIES_FILE) -> dict:
    """Run full evaluation on a collection."""
    with open(eval_file) as f:
        eval_set = json.load(f)

    results = []

    for query_data in eval_set["queries"]:
        query = query_data["query"]
        ground_truth_list = [g["chunk_id"] for g in query_data["ground_truth"]]
        ground_truth_dict = {g["chunk_id"]: g["relevance"] for g in query_data["ground_truth"]}

        # Search
        search_results = hybrid_search(collection_name, query, limit=10)
        retrieved_ids = [r["id"] for r in search_results]

        results.append(
            {
                "query_id": query_data["id"],
                "query": query,
                "type": query_data["type"],
                "retrieved": retrieved_ids,
                "relevant": ground_truth_list,
                "ground_truth": ground_truth_dict,
            }
        )

    # Calculate metrics
    metrics = {}
    for k in [1, 3, 5, 10]:
        metrics[f"recall@{k}"] = np.mean(
            [recall_at_k(r["retrieved"], r["relevant"], k) for r in results]
        )
        metrics[f"ndcg@{k}"] = np.mean(
            [ndcg_at_k(r["retrieved"], r["ground_truth"], k) for r in results]
        )
        failures = sum(1 for r in results if recall_at_k(r["retrieved"], r["relevant"], k) == 0)
        metrics[f"failure_rate@{k}"] = failures / len(results)

    return {"metrics": metrics, "details": results}


if __name__ == "__main__":
    print("Evaluation module ready. Import and use evaluate_collection() function.")
