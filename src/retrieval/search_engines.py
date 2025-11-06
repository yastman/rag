"""Search engine implementations for retrieval."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional, Union

import asyncio

import httpx
import numpy as np
from qdrant_client import QdrantClient

from src.config import SearchEngine, Settings
from src.models import get_bge_m3_model


@dataclass
class SearchResult:
    """Single search result."""

    article_number: str
    text: str
    score: float
    metadata: dict[str, Any]


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


class BaseSearchEngine(ABC):
    """Abstract base class for search engines."""

    def __init__(self, settings: Optional[Settings] = None):
        """Initialize search engine."""
        self.settings = settings or Settings()
        self.client = QdrantClient(self.settings.qdrant_url)

    @abstractmethod
    def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        score_threshold: Optional[float] = None,
    ) -> list[SearchResult]:
        """Search for similar documents."""

    @abstractmethod
    def get_name(self) -> str:
        """Get search engine name."""


class BaselineSearchEngine(BaseSearchEngine):
    """
    Baseline search using only dense vectors.

    Performance:
    - Recall@1: 91.3%
    - NDCG@10: 0.9619
    - Latency: ~0.65s
    """

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        score_threshold: Optional[float] = None,
    ) -> list[SearchResult]:
        """Search using dense vectors only with rescoring for quantization accuracy."""
        if score_threshold is None:
            score_threshold = 0.5

        results = self.client.search(
            collection_name=self.settings.collection_name,
            query_vector=query_embedding,
            limit=top_k,
            score_threshold=score_threshold,
            # Oversampling + rescoring for quantization accuracy
            search_params={
                "quantization": {
                    "rescore": True,  # Rescore with original vectors
                    "oversampling": 3.0,  # Retrieve 3x more for rescoring
                }
            },
        )

        return [
            SearchResult(
                article_number=result.payload.get("metadata", {}).get("article_number", ""),
                text=result.payload.get("page_content", ""),
                score=result.score,
                metadata=result.payload.get("metadata", {}),
            )
            for result in results
        ]

    def get_name(self) -> str:
        """Get search engine name."""
        return "baseline"


class HybridRRFSearchEngine(BaseSearchEngine):
    """
    Hybrid search using RRF (Reciprocal Rank Fusion) + BM42.

    Combines:
    - Dense vectors (BGE-M3 1024D)
    - Sparse vectors (BM42 with IDF weighting - better than BM25 for short chunks)
    - RRF fusion via Qdrant query API

    BM42 advantages over BM25 (for RAG):
    - Better for short chunks (512 chars typical in RAG)
    - Uses transformer attention weights (semantic understanding)
    - Multi-lingual support (Ukrainian, Bulgarian, etc.)
    - +9% Precision@10 improvement on short documents

    Performance (expected with BM42):
    - Recall@1: ~90% (improved from 88.7% with BM25)
    - NDCG@10: ~0.96 (improved from 0.9524)
    - Latency: ~0.72s (same as BM25)
    """

    def __init__(self, settings: Optional[Settings] = None):
        """Initialize hybrid RRF search engine with BGE-M3 model."""
        super().__init__(settings)
        self.embedding_model = get_bge_m3_model(use_fp16=True)

    def search(
        self,
        query_embedding: Union[str, list[float]],
        top_k: int = 10,
        score_threshold: Optional[float] = None,
    ) -> list[SearchResult]:
        """
        Search using RRF fusion of dense and sparse vectors.

        Args:
            query_embedding: Either query string or pre-computed dense embedding.
                If string, will generate all vector types (dense + sparse).
                If list, will use dense-only search (backward compatibility).
            top_k: Number of results to return
            score_threshold: Minimum similarity score threshold

        Returns:
            List of SearchResult objects
        """
        if score_threshold is None:
            score_threshold = 0.3

        # If query is a string, generate all embeddings and use hybrid search
        if isinstance(query_embedding, str):
            return asyncio.run(self._search_hybrid(query_embedding, top_k, score_threshold))

        # Backward compatibility: if embedding provided, use dense-only search
        dense_results = self.client.search(
            collection_name=self.settings.collection_name,
            query_vector=query_embedding,
            limit=top_k,
            score_threshold=score_threshold,
        )

        return [
            SearchResult(
                article_number=result.payload.get("metadata", {}).get("article_number", ""),
                text=result.payload.get("page_content", ""),
                score=result.score,
                metadata=result.payload.get("metadata", {}),
            )
            for result in dense_results
        ]

    async def _search_hybrid(
        self,
        query: str,
        top_k: int,
        score_threshold: float,
    ) -> list[SearchResult]:
        """
        Internal hybrid search using dense + sparse + RRF.

        Uses Qdrant's query API with prefetch for optimal performance:
        1. Prefetch dense vector search (100 candidates)
        2. Prefetch sparse BM25 search (100 candidates)
        3. RRF fusion combines both result sets
        """
        # Generate all embeddings for query
        query_embeddings = self.embedding_model.encode(
            query, return_dense=True, return_sparse=True, return_colbert_vecs=False
        )

        # Convert sparse to Qdrant format
        lexical_weights = query_embeddings["lexical_weights"]
        sparse_indices = [int(k) for k in lexical_weights]
        sparse_values = list(lexical_weights.values())

        # Build hybrid search with RRF using query API
        search_payload = {
            "prefetch": [
                # Prefetch 1: Dense vector search
                {
                    "query": query_embeddings["dense_vecs"].tolist(),
                    "using": "dense",
                    "limit": 100,  # Get more candidates for fusion
                },
                # Prefetch 2: Sparse BM42 search (better than BM25 for chunks)
                {
                    "query": {
                        "values": sparse_values,
                        "indices": sparse_indices,
                    },
                    "using": "bm42",  # Using BM42 instead of "sparse"
                    "limit": 100,
                },
            ],
            "query": {"fusion": "rrf"},  # Reciprocal Rank Fusion
            "limit": top_k,
            "with_payload": True,
            "with_vector": False,
        }

        # Convert all numpy types to Python types for JSON serialization
        search_payload = convert_to_python_types(search_payload)

        # Execute hybrid search via Qdrant query API (async)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.settings.qdrant_url}/collections/{self.settings.collection_name}/points/query",
                    json=search_payload,
                    headers={"api-key": self.settings.qdrant_api_key or ""},
                )
                response.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            # Fallback to dense-only on error
            import logging
            logging.warning(f"Hybrid search failed: {e}, falling back to dense-only")
            dense_embedding = query_embeddings["dense_vecs"].tolist()
            return self.search(dense_embedding, top_k, score_threshold)

        response.raise_for_status()
        resp_data = response.json()

        # Query API returns dict with 'points' key
        if isinstance(resp_data["result"], dict):
            points_list = resp_data["result"].get("points", [])
        elif isinstance(resp_data["result"], list):
            points_list = resp_data["result"]
        else:
            points_list = []

        return [
            SearchResult(
                article_number=point["payload"].get("metadata", {}).get("article_number", ""),
                text=point["payload"].get("page_content", ""),
                score=point["score"],
                metadata=point["payload"].get("metadata", {}),
            )
            for point in points_list
        ]

    def get_name(self) -> str:
        """Get search engine name."""
        return "hybrid_rrf"


class HybridRRFColBERTSearchEngine(BaseSearchEngine):
    """
    Advanced hybrid search using RRF fusion + BM42 + ColBERT multivector reranking.

    This is the COMPLETE "Variant A" implementation with BM42:
    - Dense + BM42 sparse vectors from BGE-M3
    - RRF fusion (Qdrant native)
    - ColBERT multivector MaxSim rerank (server-side in Qdrant)

    3-Stage Pipeline:
    1. Prefetch: Dense search (100 candidates) + BM42 sparse search (100 candidates)
    2. Fusion: RRF combines both result sets
    3. Rerank: ColBERT multivector MaxSim reranking → top-K

    BM42 advantages over BM25:
    - Better for short chunks (512 chars - typical RAG scenario)
    - Transformer attention weights (semantic understanding)
    - +9% Precision@10 on short documents
    - Multi-lingual support (Ukrainian, Bulgarian)

    Performance (Expected with BM42):
    - Recall@1: ~95% (improved from 94% with BM25)
    - NDCG@10: ~0.98 (improved from 0.97)
    - Latency: ~0.7-0.8s (same, all computation in Qdrant)

    References:
    - Qdrant Hybrid Search: https://qdrant.tech/articles/hybrid-search/
    - BM42: https://qdrant.tech/articles/bm42/
    - ColBERT: https://qdrant.tech/documentation/concepts/hybrid-queries/
    """

    def __init__(self, settings: Optional[Settings] = None):
        """Initialize hybrid RRF + ColBERT search engine with BGE-M3 model."""
        super().__init__(settings)
        self.embedding_model = get_bge_m3_model(use_fp16=True)

    def search(
        self,
        query_embedding: Union[str, list[float]],
        top_k: int = 10,
        score_threshold: Optional[float] = None,
    ) -> list[SearchResult]:
        """
        Search using RRF fusion + ColBERT reranking.

        Args:
            query_embedding: Either query string or pre-computed dense embedding.
                If string, will use full hybrid search with ColBERT rerank.
                If list, will use dense-only search (backward compatibility).
            top_k: Number of results to return
            score_threshold: Minimum similarity score threshold

        Returns:
            List of SearchResult objects
        """
        if score_threshold is None:
            score_threshold = 0.3

        # If query is a string, use full hybrid + ColBERT rerank
        if isinstance(query_embedding, str):
            return self._search_hybrid_colbert(query_embedding, top_k, score_threshold)

        # Backward compatibility: if embedding provided, use dense-only search
        dense_results = self.client.search(
            collection_name=self.settings.collection_name,
            query_vector=query_embedding,
            limit=top_k,
            score_threshold=score_threshold,
        )

        return [
            SearchResult(
                article_number=result.payload.get("metadata", {}).get("article_number", ""),
                text=result.payload.get("page_content", ""),
                score=result.score,
                metadata=result.payload.get("metadata", {}),
            )
            for result in dense_results
        ]

    def _search_hybrid_colbert(
        self,
        query: str,
        top_k: int,
        score_threshold: float,
    ) -> list[SearchResult]:
        """
        Internal 3-stage hybrid search with ColBERT rerank.

        Pipeline:
        1. Prefetch dense (100) + sparse (100) candidates
        2. RRF fusion combines both
        3. ColBERT multivector rerank on fused results → top-K
        """
        # Generate all embeddings for query (dense + sparse + colbert)
        query_embeddings = self.embedding_model.encode(
            query, return_dense=True, return_sparse=True, return_colbert_vecs=True
        )

        # Convert sparse to Qdrant format
        lexical_weights = query_embeddings["lexical_weights"]
        sparse_indices = [int(k) for k in lexical_weights]
        sparse_values = list(lexical_weights.values())

        # Build 3-stage query: Prefetch → RRF → ColBERT rerank
        search_payload = {
            "prefetch": [
                {
                    "prefetch": [
                        # Stage 1a: Dense vector search
                        {
                            "query": query_embeddings["dense_vecs"].tolist(),
                            "using": "dense",
                            "limit": 100,
                        },
                        # Stage 1b: BM42 sparse search (better for short chunks)
                        {
                            "query": {
                                "values": sparse_values,
                                "indices": sparse_indices,
                            },
                            "using": "bm42",  # Using BM42 instead of "sparse"
                            "limit": 100,
                        },
                    ],
                    # Stage 2: RRF fusion
                    "query": {"fusion": "rrf"},
                }
            ],
            # Stage 3: ColBERT multivector rerank
            "query": query_embeddings["colbert_vecs"].tolist(),
            "using": "colbert",
            "limit": top_k,
            "with_payload": True,
            "with_vector": False,
        }

        # Convert all numpy types to Python types
        search_payload = convert_to_python_types(search_payload)

        # Execute 3-stage query via Qdrant query API (async)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.settings.qdrant_url}/collections/{self.settings.collection_name}/points/query",
                    json=search_payload,
                    headers={"api-key": self.settings.qdrant_api_key or ""},
                )
                response.raise_for_status()
                resp_data = response.json()
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            # Fallback to RRF without ColBERT on error
            import logging
            logging.warning(f"ColBERT rerank failed: {e}, falling back to RRF only")
            rrf_engine = HybridRRFSearchEngine(self.settings)
            return rrf_engine.search(query, top_k, score_threshold)

        # Parse response
        if isinstance(resp_data["result"], dict):
            points_list = resp_data["result"].get("points", [])
        elif isinstance(resp_data["result"], list):
            points_list = resp_data["result"]
        else:
            points_list = []

        return [
            SearchResult(
                article_number=point["payload"].get("article_number", ""),
                text=point["payload"].get("page_content", ""),
                score=point["score"],
                metadata={
                    **point["payload"],
                    "search_method": "hybrid_rrf_colbert",
                },
            )
            for point in points_list
        ]

    def get_name(self) -> str:
        """Get search engine name."""
        return "hybrid_rrf_colbert"


class DBSFColBERTSearchEngine(BaseSearchEngine):
    """
    Advanced hybrid search using DBSF fusion + ColBERT multivector reranking.

    This is "Variant B" implementation:
    - Dense + Sparse vectors from BGE-M3
    - DBSF fusion (Qdrant native) - statistical score normalization
    - ColBERT multivector MaxSim rerank (server-side in Qdrant)

    3-Stage Pipeline:
    1. Prefetch: Dense search (100 candidates) + Sparse BM25 search (100 candidates)
    2. Fusion: DBSF combines both result sets with statistical normalization
    3. Rerank: ColBERT multivector MaxSim reranking → top-K

    DBSF Formula (server-side in Qdrant):
    normalized_score = (score - (μ - 3σ)) / 6σ, clamped to [0, 1]
    where μ = mean, σ = standard deviation of all scores

    DBSF is theoretically superior to RRF for heterogeneous scores.

    Performance (Expected):
    - Recall@1: ~94-95% (potentially better than RRF)
    - NDCG@10: ~0.97-0.98
    - Latency: ~0.7-0.8s (all computation in Qdrant)

    References:
    - Qdrant DBSF: https://qdrant.tech/documentation/concepts/search/
    - BGE-M3: https://huggingface.co/BAAI/bge-m3
    - ColBERT: https://qdrant.tech/documentation/concepts/hybrid-queries/
    """

    def __init__(self, settings: Optional[Settings] = None):
        """Initialize hybrid DBSF + ColBERT search engine with BGE-M3 model."""
        super().__init__(settings)
        self.embedding_model = get_bge_m3_model(use_fp16=True)

    def search(
        self,
        query_embedding: Union[str, list[float]],
        top_k: int = 10,
        score_threshold: Optional[float] = None,
    ) -> list[SearchResult]:
        """
        Search using DBSF fusion + ColBERT reranking.

        Args:
            query_embedding: Either query string or pre-computed dense embedding.
                If string, will use full hybrid search with ColBERT rerank.
                If list, will use dense-only search (backward compatibility).
            top_k: Number of results to return
            score_threshold: Minimum similarity score threshold

        Returns:
            List of SearchResult objects
        """
        if score_threshold is None:
            score_threshold = 0.3

        # If query is a string, use full hybrid + ColBERT rerank
        if isinstance(query_embedding, str):
            return self._search_hybrid_colbert(query_embedding, top_k, score_threshold)

        # Backward compatibility: if embedding provided, use dense-only search
        dense_results = self.client.search(
            collection_name=self.settings.collection_name,
            query_vector=query_embedding,
            limit=top_k,
            score_threshold=score_threshold,
        )

        return [
            SearchResult(
                article_number=result.payload.get("metadata", {}).get("article_number", ""),
                text=result.payload.get("page_content", ""),
                score=result.score,
                metadata=result.payload.get("metadata", {}),
            )
            for result in dense_results
        ]

    def _search_hybrid_colbert(
        self,
        query: str,
        top_k: int,
        score_threshold: float,
    ) -> list[SearchResult]:
        """
        Internal 3-stage hybrid search with ColBERT rerank.

        Pipeline:
        1. Prefetch dense (100) + sparse (100) candidates
        2. DBSF fusion combines both with statistical normalization
        3. ColBERT multivector rerank on fused results → top-K
        """
        # Generate all embeddings for query (dense + sparse + colbert)
        query_embeddings = self.embedding_model.encode(
            query, return_dense=True, return_sparse=True, return_colbert_vecs=True
        )

        # Convert sparse to Qdrant format
        lexical_weights = query_embeddings["lexical_weights"]
        sparse_indices = [int(k) for k in lexical_weights]
        sparse_values = list(lexical_weights.values())

        # Build 3-stage query: Prefetch → DBSF → ColBERT rerank
        search_payload = {
            "prefetch": [
                {
                    "prefetch": [
                        # Stage 1a: Dense vector search
                        {
                            "query": query_embeddings["dense_vecs"].tolist(),
                            "using": "dense",
                            "limit": 100,
                        },
                        # Stage 1b: Sparse BM25 search
                        {
                            "query": {
                                "values": sparse_values,
                                "indices": sparse_indices,
                            },
                            "using": "sparse",
                            "limit": 100,
                        },
                    ],
                    # Stage 2: DBSF fusion (statistical normalization)
                    "query": {"fusion": "dbsf"},
                }
            ],
            # Stage 3: ColBERT multivector rerank
            "query": query_embeddings["colbert_vecs"].tolist(),
            "using": "colbert",
            "limit": top_k,
            "with_payload": True,
            "with_vector": False,
        }

        # Convert all numpy types to Python types
        search_payload = convert_to_python_types(search_payload)

        # Execute 3-stage query via Qdrant query API (async)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.settings.qdrant_url}/collections/{self.settings.collection_name}/points/query",
                    json=search_payload,
                    headers={"api-key": self.settings.qdrant_api_key or ""},
                )
                response.raise_for_status()
                resp_data = response.json()
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            # Fallback to RRF variant on error
            import logging
            logging.warning(f"DBSF ColBERT rerank failed: {e}, falling back to RRF")
            rrf_engine = HybridRRFColBERTSearchEngine(self.settings)
            return rrf_engine.search(query, top_k, score_threshold)

        # Parse response
        if isinstance(resp_data["result"], dict):
            points_list = resp_data["result"].get("points", [])
        elif isinstance(resp_data["result"], list):
            points_list = resp_data["result"]
        else:
            points_list = []

        return [
            SearchResult(
                article_number=point["payload"].get("article_number", ""),
                text=point["payload"].get("page_content", ""),
                score=point["score"],
                metadata={
                    **point["payload"],
                    "search_method": "dbsf_colbert",
                },
            )
            for point in points_list
        ]

    def get_name(self) -> str:
        """Get search engine name."""
        return "dbsf_colbert"


def create_search_engine(
    engine_type: Optional[SearchEngine] = None,
    settings: Optional[Settings] = None,
) -> Union[
    "BaselineSearchEngine",
    "HybridRRFSearchEngine",
    "HybridRRFColBERTSearchEngine",
    "DBSFColBERTSearchEngine",
]:
    """
    Factory function to create search engine.

    Args:
        engine_type: Type of search engine (uses default from settings if None)
        settings: Configuration settings

    Returns:
        Initialized search engine instance

    Available engines:
        - BASELINE: Dense vectors only (fastest, lowest quality)
        - HYBRID_RRF: Dense + Sparse with RRF fusion (good balance)
        - HYBRID_RRF_COLBERT: Dense + Sparse + ColBERT rerank (BEST - Variant A)
        - DBSF_COLBERT: DBSF fusion + ColBERT (experimental)
    """
    settings = settings or Settings()
    engine_type = engine_type or settings.search_engine

    if engine_type == SearchEngine.BASELINE:
        return BaselineSearchEngine(settings)
    if engine_type == SearchEngine.HYBRID_RRF:
        return HybridRRFSearchEngine(settings)
    if engine_type == SearchEngine.HYBRID_RRF_COLBERT:
        return HybridRRFColBERTSearchEngine(settings)
    if engine_type == SearchEngine.DBSF_COLBERT:
        return DBSFColBERTSearchEngine(settings)

    # Default to Variant A (best performance)
    return HybridRRFColBERTSearchEngine(settings)
