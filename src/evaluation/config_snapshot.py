#!/usr/bin/env python3
"""
Configuration Snapshot for Reproducible Evaluation

This module captures all configuration parameters used in evaluation runs
to ensure reproducibility across time and environments.

Usage:
    python config_snapshot.py  # Print current config and hash

Integration:
    from config_snapshot import CONFIG_SNAPSHOT, get_config_hash

    # Include hash in evaluation reports
    report["config_hash"] = get_config_hash()
"""

import hashlib
import json
from typing import Any


CONFIG_SNAPSHOT = {
    "metadata": {
        "version": "2.0.1",
        "date": "2025-10-23",
        "description": "DBSF + ColBERT production configuration",
    },
    "infrastructure": {
        "qdrant_version": "1.15.5",
        "python_version": "3.9+",
        "os": "Linux",
    },
    "models": {
        "embedder": {
            "name": "BAAI/bge-m3",
            "url": "http://localhost:8001",
            "dense_dim": 1024,
            "sparse_enabled": True,
            "colbert_enabled": True,
        },
        "tokenizer": "XLMRobertaTokenizerFast",
    },
    "dependencies": {
        "flagembedding": "1.3.5",
        "scipy": "1.11.4",
        "pandas": "2.3.3",
        "numpy": "1.26.4",
        "aiohttp": "3.13.1",
    },
    "search_engines": {
        "baseline": {
            "type": "dense_only",
            "score_threshold": 0.5,
            "hnsw_ef": 128,
            "limit": 10,
        },
        "hybrid_rrf": {
            "type": "dense_sparse_rrf",
            "score_threshold": 0.3,
            "hnsw_ef": 256,
            "rrf_k": 60,
            "limit": 10,
        },
        "dbsf_colbert": {
            "type": "dense_sparse_dbsf_colbert",
            "stage1_dense_limit": 100,
            "stage1_sparse_limit": 100,
            "stage1_score_threshold": 0.3,
            "stage1_hnsw_ef": 256,
            "stage2_fusion": "dbsf",
            "stage3_colbert_limit": 10,
            "stage3_colbert_threshold": 0.4,
            "stage3_rescore_enabled": True,
        },
    },
    "collection": {
        "name": "uk_civil_code_v2",
        "points_count": 132,
        "vector_size": 1024,
        "distance": "Cosine",
        "quantization": "int8",
        "on_disk": True,
        "payload_indexes": [
            "article_number",
            "chapter_number",
            "section_number",
            "book_number",
        ],
    },
    "evaluation": {
        "queries_file": "data/queries_testset.json",
        "total_queries": 150,
        "ground_truth_file": "data/ground_truth_articles.json",
        "metrics": ["Recall@K", "NDCG@K", "MRR", "Precision@K", "Failure Rate@K"],
        "k_values": [1, 3, 5, 10],
    },
    "performance": {
        "target_slo": {
            "p50_latency_ms": 400,
            "p95_latency_ms": 800,
            "p99_latency_ms": 1200,
            "precision_at_1_min": 0.90,
            "recall_at_10_min": 0.95,
        },
        "baseline_results": {
            "recall_at_1": 0.913,
            "recall_at_10": 1.000,
            "ndcg_at_10": 0.9619,
            "mrr": 0.9491,
            "avg_latency_ms": 673,
        },
        "dbsf_colbert_results": {
            "recall_at_1": 0.940,
            "recall_at_10": 0.993,
            "ndcg_at_10": 0.9711,
            "mrr": 0.9636,
            "avg_latency_ms": 690,
        },
    },
}


def get_config_hash() -> str:
    """
    Generate SHA256 hash of configuration for reproducibility tracking.

    Returns:
        First 12 characters of config hash (e.g., "a3f5c7d9e2b1")

    Example:
        >>> hash_val = get_config_hash()
        >>> print(f"Config: {hash_val}")
        Config: a3f5c7d9e2b1
    """
    config_json = json.dumps(CONFIG_SNAPSHOT, sort_keys=True)
    return hashlib.sha256(config_json.encode()).hexdigest()[:12]


def get_config_summary() -> dict[str, Any]:
    """
    Get human-readable configuration summary.

    Returns:
        Dictionary with key config parameters
    """
    return {
        "version": CONFIG_SNAPSHOT["metadata"]["version"], # type: ignore[index]
        "date": CONFIG_SNAPSHOT["metadata"]["date"], # type: ignore[index]
        "config_hash": get_config_hash(),
        "models": {
            "embedder": CONFIG_SNAPSHOT["models"]["embedder"]["name"], # type: ignore[index]
            "dense_dim": CONFIG_SNAPSHOT["models"]["embedder"]["dense_dim"], # type: ignore[index]
        },
        "collection": {
            "name": CONFIG_SNAPSHOT["collection"]["name"], # type: ignore[index]
            "points": CONFIG_SNAPSHOT["collection"]["points_count"], # type: ignore[index]
        },
        "best_engine": {
            "name": "dbsf_colbert",
            "recall_at_1": CONFIG_SNAPSHOT["performance"]["dbsf_colbert_results"][ # type: ignore[index]
                "recall_at_1"
            ],
            "ndcg_at_10": CONFIG_SNAPSHOT["performance"]["dbsf_colbert_results"][ # type: ignore[index]
                "ndcg_at_10"
            ],
        },
    }


def validate_config() -> bool:
    """
    Validate configuration snapshot against current environment.

    Returns:
        True if validation passes, False otherwise

    Raises:
        ValueError: If critical parameters are missing or invalid
    """
    # Check required keys
    required_keys = ["metadata", "models", "search_engines", "collection", "evaluation"]
    for key in required_keys:
        if key not in CONFIG_SNAPSHOT:
            raise ValueError(f"Missing required config key: {key}")

    # Validate collection points count
    if CONFIG_SNAPSHOT["collection"]["points_count"] <= 0: # type: ignore[index]
        raise ValueError("Collection points_count must be positive")

    # Validate evaluation queries
    if CONFIG_SNAPSHOT["evaluation"]["total_queries"] <= 0: # type: ignore[index]
        raise ValueError("Total queries must be positive")

    return True


if __name__ == "__main__":
    print("=" * 80)
    print("CONFIGURATION SNAPSHOT")
    print("=" * 80)

    validate_config()

    summary = get_config_summary()
    print(f"\n📌 Version: {summary['version']}")
    print(f"📅 Date: {summary['date']}")
    print(f"🔑 Config Hash: {summary['config_hash']}")

    print("\n🤖 Model:")
    print(f"   Embedder: {summary['models']['embedder']}")
    print(f"   Dimension: {summary['models']['dense_dim']}")

    print("\n📦 Collection:")
    print(f"   Name: {summary['collection']['name']}")
    print(f"   Points: {summary['collection']['points']}")

    print(f"\n⭐ Best Engine: {summary['best_engine']['name']}")
    print(f"   Recall@1: {summary['best_engine']['recall_at_1']:.1%}")
    print(f"   NDCG@10: {summary['best_engine']['ndcg_at_10']:.4f}")

    print("\n" + "=" * 80)
    print("FULL CONFIGURATION")
    print("=" * 80)
    print(json.dumps(CONFIG_SNAPSHOT, indent=2))

    print("\n" + "=" * 80)
    print("✅ Configuration validated successfully!")
    print(f"🔑 Use this hash for reproducibility: {get_config_hash()}")
    print("=" * 80)
