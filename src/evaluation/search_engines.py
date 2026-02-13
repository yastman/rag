#!/usr/bin/env python3
"""
Search engines for evaluation:
1. BaselineSearchEngine - Dense-only (BGE-M3 dense vectors)
2. HybridSearchEngine - Dense + Sparse + ColBERT with RRF
"""

import os
import sys
from abc import ABC, abstractmethod
from functools import lru_cache

import numpy as np
import requests  # type: ignore[import-untyped]

from src.config import HSNWParameters, RetrievalStages, Settings, ThresholdValues


# Load Qdrant config without failing module import in test environments.
try:
    _settings = Settings()
    QDRANT_URL = _settings.qdrant_url
    QDRANT_API_KEY = _settings.qdrant_api_key or ""
except ValueError:
    QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")

# Load constants
HNSW_EF_HIGH_PRECISION = HSNWParameters.EF_HIGH_PRECISION
SCORE_THRESHOLD_HYBRID = ThresholdValues.HYBRID
RETRIEVAL_LIMIT_STAGE1 = RetrievalStages.STAGE1_CANDIDATES
RETRIEVAL_LIMIT_STAGE2 = RetrievalStages.STAGE2_FINAL
PAYLOAD_FIELDS_MINIMAL = ["article_number", "chapter", "text"]


def convert_to_python_types(obj):
    """Convert numpy types to native Python types for JSON serialization."""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.float32, np.float64)):
        return float(obj)
    if isinstance(obj, (np.int32, np.int64)):
        return int(obj)
    if isinstance(obj, dict):
        return {k: convert_to_python_types(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_to_python_types(item) for item in obj]
    return obj


class SearchEngine(ABC):
    """Abstract base class for search engines."""

    def __init__(self, collection_name: str):
        self.collection_name = collection_name
        self.qdrant_url = _qdrant_url()
        self.headers = {"api-key": _qdrant_api_key()}

    @abstractmethod
    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """
        Search for relevant documents.

        Args:
            query: Search query text
            top_k: Number of results to return

        Returns:
            List of dicts with keys: point_id, score, article_number, text
        """

    def _extract_article_number(self, payload: dict) -> str:
        """Extract article number from point payload."""
        return str(payload.get("article_number", ""))


class BaselineSearchEngine(SearchEngine):
    """
    Baseline search using dense vectors only (BGE-M3).
    Simple vector similarity search without any optimization.
    """

    def __init__(self, collection_name: str, embedding_model):
        super().__init__(collection_name)
        self.embedding_model = embedding_model

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """
        Search using dense vectors only.

        Uses BGE-M3 dense embeddings (1024D INT8) for simple similarity search.
        """
        # Generate dense embedding for query
        query_embedding = self.embedding_model.encode(
            query, return_dense=True, return_sparse=False, return_colbert_vecs=False
        )

        # Search using dense vector only
        search_payload = {
            "vector": {"name": "dense", "vector": query_embedding["dense_vecs"].tolist()},
            "limit": top_k,
            "with_payload": True,
            "with_vector": False,
        }

        response = requests.post(
            f"{self.qdrant_url}/collections/{self.collection_name}/points/search",
            json=search_payload,
            headers=self.headers,
        )
        response.raise_for_status()

        results = []
        for point in response.json()["result"]:
            results.append(
                {
                    "point_id": point["id"],
                    "score": point["score"],
                    "article_number": self._extract_article_number(point["payload"]),
                    "text": point["payload"].get("text", "")[:200] + "...",
                }
            )

        return results


class HybridSearchEngine(SearchEngine):
    """
    Hybrid search using Dense + Sparse (BM25) with Reciprocal Rank Fusion (RRF).

    This implements Qdrant's hybrid search with RRF fusion:
    - Dense: BGE-M3 dense vectors (1024D INT8)
    - Sparse: BM25 with IDF weighting
    - Fusion: RRF combines both scores

    Note: ColBERT multi-vector matching is disabled for now.
    """

    def __init__(self, collection_name: str, embedding_model):
        super().__init__(collection_name)
        self.embedding_model = embedding_model

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """
        Search using hybrid approach with RRF fusion.

        Uses Qdrant's query API with prefetch and RRF fusion:
        1. Dense vector search
        2. Sparse BM25 search
        3. ColBERT multi-vector search
        4. RRF combines all three result sets
        """
        # Generate all embeddings for query
        query_embeddings = self.embedding_model.encode(
            query, return_dense=True, return_sparse=True, return_colbert_vecs=True
        )

        # Convert sparse to Qdrant format
        # lexical_weights is a dict, need to convert to lists
        lexical_weights = query_embeddings["lexical_weights"]
        if hasattr(lexical_weights, "indices"):
            # Scipy sparse format
            sparse_indices = lexical_weights.indices.tolist()
            sparse_values = lexical_weights.values.tolist()
        else:
            # Dict format - keys are strings, need to convert to ints!
            sparse_indices = [int(k) for k in lexical_weights]
            sparse_values = list(lexical_weights.values())

        # Build hybrid search with RRF using query API
        # NOTE: Testing without ColBERT first - will add back if dense+sparse works
        search_payload = {
            "prefetch": [
                # Prefetch 1: Dense vector search
                {
                    "query": query_embeddings["dense_vecs"].tolist(),
                    "using": "dense",
                    "limit": 100,  # Get more candidates for fusion
                },
                # Prefetch 2: Sparse BM25 search
                {
                    "query": {
                        "values": sparse_values,  # values BEFORE indices (Qdrant API requirement)
                        "indices": sparse_indices,
                    },
                    "using": "sparse",
                    "limit": 100,
                },
                # Temporarily disabled ColBERT for testing
                # {
                #     "query": query_embeddings["colbert_vecs"].tolist(),
                #     "using": "colbert",
                #     "limit": 100
                # }
            ],
            "query": {
                "fusion": "rrf"  # Reciprocal Rank Fusion
            },
            "limit": top_k,
            "with_payload": True,
            "with_vector": False,
        }

        # Convert all numpy types to Python types for JSON serialization
        search_payload = convert_to_python_types(search_payload)

        response = requests.post(
            f"{self.qdrant_url}/collections/{self.collection_name}/points/query",
            json=search_payload,
            headers=self.headers,
        )

        if response.status_code != 200:
            # Print detailed error for debugging
            print(f"ERROR: {response.status_code} - {response.text}")

        response.raise_for_status()

        resp_data = response.json()

        # Query API returns dict with 'points' key, not a list
        if isinstance(resp_data["result"], dict):
            points_list = resp_data["result"].get("points", [])
        elif isinstance(resp_data["result"], list):
            points_list = resp_data["result"]
        else:
            points_list = []

        results = []
        for point in points_list:
            results.append(
                {
                    "point_id": point["id"],
                    "score": point["score"],
                    "article_number": self._extract_article_number(point["payload"]),
                    "text": point["payload"].get("text", "")[:200] + "...",
                }
            )

        return results


class HybridDBSFColBERTSearchEngine(SearchEngine):
    """
    Advanced hybrid search using DBSF fusion + ColBERT reranking (Qdrant 2025 Best Practices).

    3-Stage Retrieval Pipeline:
    1. Prefetch: Dense + Sparse → 100 candidates each
    2. Fusion: DBSF (Distribution-Based Score Fusion) combines results
    3. Rerank: ColBERT multivector server-side reranking → top-K

    Based on official Qdrant documentation:
    - DBSF: https://qdrant.tech/articles/hybrid-search/
    - ColBERT: https://qdrant.tech/documentation/concepts/hybrid-queries/
    """

    def __init__(self, collection_name: str, embedding_model):
        super().__init__(collection_name)
        self.embedding_model = embedding_model

        # Use config parameters from module level
        self.score_threshold = SCORE_THRESHOLD_HYBRID
        self.hnsw_ef = HNSW_EF_HIGH_PRECISION
        self.stage1_limit = RETRIEVAL_LIMIT_STAGE1
        self.stage2_limit = RETRIEVAL_LIMIT_STAGE2
        self.payload_fields = PAYLOAD_FIELDS_MINIMAL

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """
        3-stage search with DBSF fusion + ColBERT reranking.

        Args:
            query: Search query text
            top_k: Final number of results to return

        Returns:
            List of dicts with keys: point_id, score, article_number, text
        """
        # Generate all embeddings for query
        query_embeddings = self.embedding_model.encode(
            query, return_dense=True, return_sparse=True, return_colbert_vecs=True
        )

        # Convert sparse to Qdrant format
        lexical_weights = query_embeddings["lexical_weights"]
        if hasattr(lexical_weights, "indices"):
            # Scipy sparse format
            sparse_indices = lexical_weights.indices.tolist()
            sparse_values = lexical_weights.values.tolist()
        else:
            # Dict format - keys are strings, need to convert to ints
            sparse_indices = [int(k) for k in lexical_weights]
            sparse_values = list(lexical_weights.values())

        # Build 3-stage query with DBSF fusion + ColBERT reranking
        search_payload = {
            "prefetch": [
                # Stage 1a: Dense vector search (prefetch 100 candidates)
                {
                    "prefetch": [
                        {
                            "query": query_embeddings["dense_vecs"].tolist(),
                            "using": "dense",
                            "limit": self.stage1_limit,
                        },
                        # Stage 1b: Sparse BM25 search (prefetch 100 candidates)
                        {
                            "query": {"values": sparse_values, "indices": sparse_indices},
                            "using": "sparse",
                            "limit": self.stage1_limit,
                        },
                    ],
                    # Stage 2: DBSF fusion combines dense + sparse results
                    "query": {
                        "fusion": "dbsf"  # Distribution-Based Score Fusion
                    },
                }
            ],
            # Stage 3: ColBERT multivector reranking on fused results
            "query": query_embeddings["colbert_vecs"].tolist(),
            "using": "colbert",
            "limit": top_k,
            "score_threshold": self.score_threshold,
            "params": {
                "hnsw_ef": self.hnsw_ef  # Higher precision for ColBERT search
            },
            "with_payload": self.payload_fields,
            "with_vector": False,
        }

        # Convert numpy types to Python types
        search_payload = convert_to_python_types(search_payload)

        # Execute query using Qdrant Query API
        response = requests.post(
            f"{self.qdrant_url}/collections/{self.collection_name}/points/query",
            json=search_payload,
            headers=self.headers,
        )

        if response.status_code != 200:
            print(f"ERROR: {response.status_code} - {response.text}")

        response.raise_for_status()
        resp_data = response.json()

        # Parse response
        if isinstance(resp_data["result"], dict):
            points_list = resp_data["result"].get("points", [])
        elif isinstance(resp_data["result"], list):
            points_list = resp_data["result"]
        else:
            points_list = []

        results = []
        for point in points_list:
            results.append(
                {
                    "point_id": point["id"],
                    "score": point["score"],
                    "article_number": self._extract_article_number(point["payload"]),
                    "text": point["payload"].get("text", "")[:200] + "...",
                }
            )

        return results


class HybridRRFColBERTSearchEngine(SearchEngine):
    """
    Advanced hybrid search using RRF fusion + ColBERT reranking (Official Qdrant Method).

    3-Stage Retrieval Pipeline:
    1. Prefetch: Dense + Sparse → 100 candidates each
    2. Fusion: RRF (Reciprocal Rank Fusion) combines results - OFFICIAL QDRANT METHOD
    3. Rerank: ColBERT multivector server-side reranking → top-K

    Based on official Qdrant documentation:
    - RRF: https://qdrant.tech/articles/hybrid-search/ (officially supported)
    - ColBERT: https://qdrant.tech/documentation/concepts/hybrid-queries/
    """

    def __init__(self, collection_name: str, embedding_model):
        super().__init__(collection_name)
        self.embedding_model = embedding_model

        # Use config parameters from module level
        self.score_threshold = SCORE_THRESHOLD_HYBRID
        self.hnsw_ef = HNSW_EF_HIGH_PRECISION
        self.stage1_limit = RETRIEVAL_LIMIT_STAGE1
        self.stage2_limit = RETRIEVAL_LIMIT_STAGE2
        self.payload_fields = PAYLOAD_FIELDS_MINIMAL

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """
        3-stage search with RRF fusion + ColBERT reranking.

        Args:
            query: Search query text
            top_k: Final number of results to return

        Returns:
            List of dicts with keys: point_id, score, article_number, text
        """
        # Generate all embeddings for query
        query_embeddings = self.embedding_model.encode(
            query, return_dense=True, return_sparse=True, return_colbert_vecs=True
        )

        # Convert sparse to Qdrant format
        lexical_weights = query_embeddings["lexical_weights"]
        if hasattr(lexical_weights, "indices"):
            # Scipy sparse format
            sparse_indices = lexical_weights.indices.tolist()
            sparse_values = lexical_weights.values.tolist()
        else:
            # Dict format - keys are strings, need to convert to ints
            sparse_indices = [int(k) for k in lexical_weights]
            sparse_values = list(lexical_weights.values())

        # Build 3-stage query with RRF fusion + ColBERT reranking
        search_payload = {
            "prefetch": [
                # Stage 1a: Dense vector search (prefetch 100 candidates)
                {
                    "prefetch": [
                        {
                            "query": query_embeddings["dense_vecs"].tolist(),
                            "using": "dense",
                            "limit": self.stage1_limit,
                        },
                        # Stage 1b: Sparse BM25 search (prefetch 100 candidates)
                        {
                            "query": {"values": sparse_values, "indices": sparse_indices},
                            "using": "sparse",
                            "limit": self.stage1_limit,
                        },
                    ],
                    # Stage 2: RRF fusion combines dense + sparse results
                    "query": {
                        "fusion": "rrf"  # Reciprocal Rank Fusion (OFFICIAL METHOD)
                    },
                }
            ],
            # Stage 3: ColBERT multivector reranking on fused results
            "query": query_embeddings["colbert_vecs"].tolist(),
            "using": "colbert",
            "limit": top_k,
            "score_threshold": self.score_threshold,
            "params": {
                "hnsw_ef": self.hnsw_ef  # Higher precision for ColBERT search
            },
            "with_payload": self.payload_fields,
            "with_vector": False,
        }

        # Convert numpy types to Python types
        search_payload = convert_to_python_types(search_payload)

        # Execute query using Qdrant Query API
        response = requests.post(
            f"{self.qdrant_url}/collections/{self.collection_name}/points/query",
            json=search_payload,
            headers=self.headers,
        )

        if response.status_code != 200:
            print(f"ERROR: {response.status_code} - {response.text}")

        response.raise_for_status()
        resp_data = response.json()

        # Parse response
        if isinstance(resp_data["result"], dict):
            points_list = resp_data["result"].get("points", [])
        elif isinstance(resp_data["result"], list):
            points_list = resp_data["result"]
        else:
            points_list = []

        results = []
        for point in points_list:
            results.append(
                {
                    "point_id": point["id"],
                    "score": point["score"],
                    "article_number": self._extract_article_number(point["payload"]),
                    "text": point["payload"].get("text", "")[:200] + "...",
                }
            )

        return results


def create_search_engine(engine_type: str, collection_name: str, embedding_model) -> SearchEngine:
    """
    Factory function to create search engines.

    Args:
        engine_type: "baseline", "hybrid", "dbsf_colbert", or "rrf_colbert"
        collection_name: Qdrant collection name
        embedding_model: BGE-M3 embedding model instance

    Returns:
        SearchEngine instance
    """
    if engine_type == "baseline":
        return BaselineSearchEngine(collection_name, embedding_model)
    if engine_type == "hybrid":
        return HybridSearchEngine(collection_name, embedding_model)
    if engine_type == "dbsf_colbert":
        return HybridDBSFColBERTSearchEngine(collection_name, embedding_model)
    if engine_type == "rrf_colbert":
        return HybridRRFColBERTSearchEngine(collection_name, embedding_model)
    raise ValueError(f"Unknown engine type: {engine_type}")


if __name__ == "__main__":
    # Quick test
    from FlagEmbedding import BGEM3FlagModel

    print("Loading BGE-M3 model...")
    model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)

    collection = "ukraine_criminal_code_zai_full"

    print("\n=== Testing Baseline Search ===")
    baseline = create_search_engine("baseline", collection, model)
    results = baseline.search("кража имущества", top_k=5)
    for i, r in enumerate(results, 1):
        print(f"{i}. Article {r['article_number']}: {r['score']:.4f}")

    print("\n=== Testing Hybrid Search ===")
    hybrid = create_search_engine("hybrid", collection, model)
    results = hybrid.search("кража имущества", top_k=5)
    for i, r in enumerate(results, 1):
        print(f"{i}. Article {r['article_number']}: {r['score']:.4f}")
