#!/usr/bin/env python3
"""
Search engines for evaluation:
1. BaselineSearchEngine - Dense-only (BGE-M3 dense vectors)
2. HybridSearchEngine - Dense + Sparse + ColBERT with RRF
"""

import os
from abc import ABC, abstractmethod

import numpy as np
from qdrant_client import QdrantClient, models

from src.config import HSNWParameters, RetrievalStages, Settings, ThresholdValues


# Load Qdrant config without failing module import in test environments.
try:
    _settings = Settings()
    QDRANT_URL = _settings.qdrant_url
    QDRANT_API_KEY = _settings.qdrant_api_key or ""
except ValueError:
    QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")


def _qdrant_url() -> str:
    """Return Qdrant base URL from resolved settings/environment."""
    return QDRANT_URL or "http://localhost:6333"


def _qdrant_api_key() -> str:
    """Return Qdrant API key from resolved settings/environment."""
    return QDRANT_API_KEY or ""


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


def _lexical_weights_to_sparse(lexical_weights) -> models.SparseVector:
    """Convert BGE-M3 lexical weights to Qdrant SparseVector."""
    if hasattr(lexical_weights, "indices"):
        # Scipy sparse format
        sparse_indices = lexical_weights.indices.tolist()
        sparse_values = lexical_weights.values.tolist()
    else:
        # Dict format - keys are strings, need to convert to ints
        sparse_indices = [int(k) for k in lexical_weights]
        sparse_values = list(lexical_weights.values())
    return models.SparseVector(indices=sparse_indices, values=sparse_values)


class SearchEngine(ABC):
    """Abstract base class for search engines."""

    def __init__(self, collection_name: str):
        self.collection_name = collection_name
        url = _qdrant_url()
        api_key = _qdrant_api_key()
        if api_key:
            self.client = QdrantClient(url=url, api_key=api_key)
        else:
            self.client = QdrantClient(url=url)

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

        dense_vector = convert_to_python_types(query_embedding["dense_vecs"])

        response = self.client.query_points(
            collection_name=self.collection_name,
            query=dense_vector,
            using="dense",
            limit=top_k,
            with_payload=True,
        )

        return [
            {
                "point_id": point.id,
                "score": point.score,
                "article_number": self._extract_article_number(point.payload or {}),
                "text": (point.payload or {}).get("text", "")[:200] + "...",
            }
            for point in response.points
        ]


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
        3. RRF combines both result sets
        """
        # Generate all embeddings for query
        query_embeddings = self.embedding_model.encode(
            query, return_dense=True, return_sparse=True, return_colbert_vecs=True
        )

        dense_vector = convert_to_python_types(query_embeddings["dense_vecs"])
        sparse_vector = _lexical_weights_to_sparse(query_embeddings["lexical_weights"])

        # Build hybrid search with RRF using query API
        prefetch = [
            models.Prefetch(query=dense_vector, using="dense", limit=100),
            models.Prefetch(query=sparse_vector, using="sparse", limit=100),
        ]

        response = self.client.query_points(
            collection_name=self.collection_name,
            prefetch=prefetch,
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=top_k,
            with_payload=True,
        )

        return [
            {
                "point_id": point.id,
                "score": point.score,
                "article_number": self._extract_article_number(point.payload or {}),
                "text": (point.payload or {}).get("text", "")[:200] + "...",
            }
            for point in response.points
        ]


class HybridDBSFColBERTSearchEngine(SearchEngine):
    """
    Advanced hybrid search using DBSF fusion + ColBERT reranking (Qdrant 2025 Best Practices).

    3-Stage Retrieval Pipeline:
    1. Prefetch: Dense + Sparse -> 100 candidates each
    2. Fusion: DBSF (Distribution-Based Score Fusion) combines results
    3. Rerank: ColBERT multivector server-side reranking -> top-K

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

        dense_vector = convert_to_python_types(query_embeddings["dense_vecs"])
        sparse_vector = _lexical_weights_to_sparse(query_embeddings["lexical_weights"])
        colbert_vectors = convert_to_python_types(query_embeddings["colbert_vecs"])

        # Build 3-stage query with DBSF fusion + ColBERT reranking
        dbsf_prefetch = models.Prefetch(
            prefetch=[
                models.Prefetch(query=dense_vector, using="dense", limit=self.stage1_limit),
                models.Prefetch(query=sparse_vector, using="sparse", limit=self.stage1_limit),
            ],
            query=models.FusionQuery(fusion=models.Fusion.DBSF),
        )

        response = self.client.query_points(
            collection_name=self.collection_name,
            prefetch=[dbsf_prefetch],
            query=colbert_vectors,
            using="colbert",
            limit=top_k,
            score_threshold=self.score_threshold,
            search_params=models.SearchParams(hnsw_ef=self.hnsw_ef),
            with_payload=self.payload_fields,
        )

        return [
            {
                "point_id": point.id,
                "score": point.score,
                "article_number": self._extract_article_number(point.payload or {}),
                "text": (point.payload or {}).get("text", "")[:200] + "...",
            }
            for point in response.points
        ]


class HybridRRFColBERTSearchEngine(SearchEngine):
    """
    Advanced hybrid search using RRF fusion + ColBERT reranking (Official Qdrant Method).

    3-Stage Retrieval Pipeline:
    1. Prefetch: Dense + Sparse -> 100 candidates each
    2. Fusion: RRF (Reciprocal Rank Fusion) combines results - OFFICIAL QDRANT METHOD
    3. Rerank: ColBERT multivector server-side reranking -> top-K

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

        dense_vector = convert_to_python_types(query_embeddings["dense_vecs"])
        sparse_vector = _lexical_weights_to_sparse(query_embeddings["lexical_weights"])
        colbert_vectors = convert_to_python_types(query_embeddings["colbert_vecs"])

        # Build 3-stage query with RRF fusion + ColBERT reranking
        rrf_prefetch = models.Prefetch(
            prefetch=[
                models.Prefetch(query=dense_vector, using="dense", limit=self.stage1_limit),
                models.Prefetch(query=sparse_vector, using="sparse", limit=self.stage1_limit),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
        )

        response = self.client.query_points(
            collection_name=self.collection_name,
            prefetch=[rrf_prefetch],
            query=colbert_vectors,
            using="colbert",
            limit=top_k,
            score_threshold=self.score_threshold,
            search_params=models.SearchParams(hnsw_ef=self.hnsw_ef),
            with_payload=self.payload_fields,
        )

        return [
            {
                "point_id": point.id,
                "score": point.score,
                "article_number": self._extract_article_number(point.payload or {}),
                "text": (point.payload or {}).get("text", "")[:200] + "...",
            }
            for point in response.points
        ]


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
