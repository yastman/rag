"""Search engine implementations for retrieval."""

from abc import abstractmethod
from dataclasses import dataclass
from typing import Any, Union

from qdrant_client import QdrantClient, models

from src.config import AcornMode, QuantizationMode, SearchEngine, Settings
from src.models import get_bge_m3_model
from src.retrieval.search_engine_shared import (
    AbstractSearchEngine,
    create_engine_from_registry,
    lexical_weights_to_sparse,
)
from src.utils.serialization import convert_to_python_types


# ACORN: available in qdrant-client SDK (≥1.16.2) but intentionally not connected
# to bot runtime. Evaluation-only — used in search benchmark engines below.
# Connect to production when filtered queries need higher recall. See #590.
try:
    from qdrant_client.models import AcornSearchParams

    ACORN_AVAILABLE = True
except ImportError:
    ACORN_AVAILABLE = False
    AcornSearchParams = None  # type: ignore[misc, assignment]


@dataclass
class SearchResult:
    """Single search result."""

    article_number: str
    text: str
    score: float
    metadata: dict[str, Any]


class BaseSearchEngine(AbstractSearchEngine):
    """Abstract base class for search engines."""

    def __init__(self, settings: Settings | None = None):
        """Initialize search engine."""
        self.settings = settings or Settings()
        self.client = QdrantClient(self.settings.qdrant_url)
        # Use quantization-aware collection name
        self._collection_name = self.settings.get_collection_name()

    @property
    def collection_name(self) -> str:
        """Get collection name (respects quantization_mode setting)."""
        return self._collection_name

    def _should_use_acorn(self, has_filters: bool, estimated_selectivity: float | None) -> bool:
        """Determine if ACORN should be enabled based on settings and query context.

        Args:
            has_filters: Whether the query has any filters applied.
            estimated_selectivity: Estimated fraction of vectors matching filters (0.0-1.0).
                None if unknown.

        Returns:
            True if ACORN should be enabled for this query.
        """
        if self.settings.acorn_mode == AcornMode.OFF:
            return False

        if self.settings.acorn_mode == AcornMode.ON:
            # Always use ACORN when filters are present
            return has_filters

        # AUTO mode: use ACORN only with filters AND low selectivity
        if not has_filters:
            return False

        # If selectivity is unknown, default to enabled (conservative)
        if estimated_selectivity is None:
            return True

        # Enable ACORN only if selectivity is below threshold
        return estimated_selectivity < self.settings.acorn_enabled_selectivity_threshold

    def _build_search_params(
        self,
        has_filters: bool = False,
        estimated_selectivity: float | None = None,
    ) -> models.SearchParams:
        """Build SearchParams with quantization and optional ACORN settings.

        Args:
            has_filters: Whether the query has filters applied.
            estimated_selectivity: Estimated fraction of vectors matching filters.

        Returns:
            SearchParams configured for quantization and ACORN.
        """
        # Build quantization params
        quantization_params = models.QuantizationSearchParams(
            ignore=(self.settings.quantization_mode == QuantizationMode.OFF),
            rescore=self.settings.quantization_rescore,
            oversampling=self.settings.quantization_oversampling,
        )

        # Determine if ACORN should be enabled
        # Only use ACORN if the feature is available in qdrant-client
        use_acorn = ACORN_AVAILABLE and self._should_use_acorn(has_filters, estimated_selectivity)

        if use_acorn and AcornSearchParams is not None:
            acorn_params = AcornSearchParams(
                enable=True,
                max_selectivity=self.settings.acorn_max_selectivity,
            )
            return models.SearchParams(
                quantization=quantization_params,
                acorn=acorn_params,
            )

        return models.SearchParams(quantization=quantization_params)

    @staticmethod
    def _parse_group_results(response: Any) -> list[SearchResult]:
        """Parse grouped query results into flat SearchResult list.

        Extracts the top hit from each group, preserving group ordering.
        """
        results: list[SearchResult] = []
        for group in response.groups:
            for point in group.hits:
                results.append(
                    SearchResult(
                        article_number=(point.payload or {})
                        .get("metadata", {})
                        .get("article_number", ""),
                        text=(point.payload or {}).get("page_content", ""),
                        score=point.score,
                        metadata=(point.payload or {}).get("metadata", {}),
                    )
                )
        return results

    @abstractmethod
    def search(
        self,
        query_embedding: str | list[float],
        top_k: int = 10,
        score_threshold: float | None = None,
    ) -> list[SearchResult]:
        """Search for similar documents.

        Args:
            query_embedding: Either query string (for hybrid engines) or
                pre-computed dense embedding (for baseline engine).
            top_k: Number of results to return.
            score_threshold: Minimum similarity score threshold.

        Returns:
            List of SearchResult objects.
        """

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

    Supports ACORN for filtered queries (see acorn_mode setting).
    """

    def search(
        self,
        query_embedding: str | list[float],
        top_k: int = 10,
        score_threshold: float | None = None,
        *,
        query_filter: models.Filter | None = None,
        estimated_selectivity: float | None = None,
    ) -> list[SearchResult]:
        """Search using dense vectors only with rescoring for quantization accuracy.

        Args:
            query_embedding: Dense vector embedding of the query (str not supported,
                for API compatibility only - will raise TypeError).
            top_k: Number of results to return.
            score_threshold: Minimum similarity score threshold.
            query_filter: Optional Qdrant filter for filtered search.
            estimated_selectivity: Estimated fraction of vectors matching filter (0.0-1.0).
                Used to determine if ACORN should be enabled in 'auto' mode.

        Returns:
            List of SearchResult objects.

        Raises:
            TypeError: If query_embedding is a string (not supported for baseline).
        """
        if isinstance(query_embedding, str):
            raise TypeError(
                "BaselineSearchEngine requires pre-computed embeddings, not query strings"
            )
        if score_threshold is None:
            score_threshold = 0.5

        # Build search params with quantization and conditional ACORN
        has_filters = query_filter is not None
        search_params = self._build_search_params(
            has_filters=has_filters,
            estimated_selectivity=estimated_selectivity,
        )

        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            using="dense",
            query_filter=query_filter,
            limit=top_k,
            score_threshold=score_threshold,
            search_params=search_params,
        )

        return [
            SearchResult(
                article_number=(result.payload or {}).get("metadata", {}).get("article_number", ""),
                text=(result.payload or {}).get("page_content", ""),
                score=result.score,
                metadata=(result.payload or {}).get("metadata", {}),
            )
            for result in response.points
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

    def __init__(self, settings: Settings | None = None):
        """Initialize hybrid RRF search engine with BGE-M3 model."""
        super().__init__(settings)
        self.embedding_model = get_bge_m3_model(use_fp16=True)

    def search(
        self,
        query_embedding: str | list[float],
        top_k: int = 10,
        score_threshold: float | None = None,
        *,
        rrf_k: int = 60,
        group_by: str | None = None,
        group_size: int = 2,
    ) -> list[SearchResult]:
        """
        Search using RRF fusion of dense and sparse vectors.

        Args:
            query_embedding: Either query string or pre-computed dense embedding.
                If string, will generate all vector types (dense + sparse).
                If list, will use dense-only search (backward compatibility).
            top_k: Number of results to return
            score_threshold: Minimum similarity score threshold
            rrf_k: RRF constant k (higher = more weight to lower-ranked results).
            group_by: Optional payload field to group results by (e.g. "metadata.doc_id").
            group_size: Max points per group when group_by is set.

        Returns:
            List of SearchResult objects
        """
        if score_threshold is None:
            score_threshold = 0.3

        # If query is a string, generate all embeddings and use hybrid search
        if isinstance(query_embedding, str):
            return self._search_hybrid(
                query_embedding,
                top_k,
                score_threshold,
                rrf_k=rrf_k,
                group_by=group_by,
                group_size=group_size,
            )

        # Backward compatibility: if embedding provided, use dense-only search
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            using="dense",
            limit=top_k,
            score_threshold=score_threshold,
        )

        return [
            SearchResult(
                article_number=(result.payload or {}).get("metadata", {}).get("article_number", ""),
                text=(result.payload or {}).get("page_content", ""),
                score=result.score,
                metadata=(result.payload or {}).get("metadata", {}),
            )
            for result in response.points
        ]

    def _search_hybrid(
        self,
        query: str,
        top_k: int,
        score_threshold: float,
        *,
        rrf_k: int = 60,
        group_by: str | None = None,
        group_size: int = 2,
    ) -> list[SearchResult]:
        """
        Hybrid search using dense + sparse + RRF via SDK query_points.

        Uses Qdrant's native query API with prefetch:
        1. Prefetch dense vector search (100 candidates)
        2. Prefetch sparse BM42 search (100 candidates)
        3. RRF fusion combines both result sets

        Args:
            query: Search query string.
            top_k: Number of results to return.
            score_threshold: Minimum score threshold.
            rrf_k: RRF constant k (higher = more weight to lower-ranked results).
            group_by: Optional payload field to group results by (e.g. "metadata.doc_id").
            group_size: Max points per group when group_by is set.
        """
        import logging

        # Generate all embeddings for query
        query_embeddings = self.embedding_model.encode(
            query, return_dense=True, return_sparse=True, return_colbert_vecs=False
        )

        # Convert to Python/Qdrant types
        dense_vector = convert_to_python_types(query_embeddings["dense_vecs"])
        sparse_vector = lexical_weights_to_sparse(query_embeddings["lexical_weights"])

        prefetch = [
            models.Prefetch(query=dense_vector, using="dense", limit=100),
            models.Prefetch(query=sparse_vector, using="bm42", limit=100),
        ]
        rrf_query = models.RrfQuery(rrf=models.Rrf(k=rrf_k))

        try:
            if group_by:
                grouped_response = self.client.query_points_groups(
                    collection_name=self.collection_name,
                    prefetch=prefetch,
                    query=rrf_query,
                    group_by=group_by,
                    group_size=group_size,
                    limit=top_k,
                    with_payload=True,
                )
                return self._parse_group_results(grouped_response)

            query_response = self.client.query_points(
                collection_name=self.collection_name,
                prefetch=prefetch,
                query=rrf_query,
                limit=top_k,
                with_payload=True,
            )

            return [
                SearchResult(
                    article_number=(point.payload or {})
                    .get("metadata", {})
                    .get("article_number", ""),
                    text=(point.payload or {}).get("page_content", ""),
                    score=point.score,
                    metadata=(point.payload or {}).get("metadata", {}),
                )
                for point in query_response.points
            ]

        except Exception as e:
            logging.warning(f"Hybrid search failed: {e}, falling back to dense-only")
            dense_embedding = convert_to_python_types(query_embeddings["dense_vecs"])
            return self.search(dense_embedding, top_k, score_threshold)

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

    def __init__(self, settings: Settings | None = None):
        """Initialize hybrid RRF + ColBERT search engine with BGE-M3 model."""
        super().__init__(settings)
        self.embedding_model = get_bge_m3_model(use_fp16=True)

    def search(
        self,
        query_embedding: str | list[float],
        top_k: int = 10,
        score_threshold: float | None = None,
        *,
        rrf_k: int = 60,
        group_by: str | None = None,
        group_size: int = 2,
    ) -> list[SearchResult]:
        """
        Search using RRF fusion + ColBERT reranking.

        Args:
            query_embedding: Either query string or pre-computed dense embedding.
                If string, will use full hybrid search with ColBERT rerank.
                If list, will use dense-only search (backward compatibility).
            top_k: Number of results to return
            score_threshold: Minimum similarity score threshold
            rrf_k: RRF constant k (higher = more weight to lower-ranked results).
            group_by: Optional payload field to group results by (e.g. "metadata.doc_id").
            group_size: Max points per group when group_by is set.

        Returns:
            List of SearchResult objects
        """
        if score_threshold is None:
            score_threshold = 0.3

        # If query is a string, use full hybrid + ColBERT rerank
        if isinstance(query_embedding, str):
            return self._search_hybrid_colbert(
                query_embedding,
                top_k,
                score_threshold,
                rrf_k=rrf_k,
                group_by=group_by,
                group_size=group_size,
            )

        # Backward compatibility: if embedding provided, use dense-only search
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            using="dense",
            limit=top_k,
            score_threshold=score_threshold,
        )

        return [
            SearchResult(
                article_number=(result.payload or {}).get("metadata", {}).get("article_number", ""),
                text=(result.payload or {}).get("page_content", ""),
                score=result.score,
                metadata=(result.payload or {}).get("metadata", {}),
            )
            for result in response.points
        ]

    def _search_hybrid_colbert(
        self,
        query: str,
        top_k: int,
        score_threshold: float,
        *,
        rrf_k: int = 60,
        group_by: str | None = None,
        group_size: int = 2,
    ) -> list[SearchResult]:
        """
        3-stage hybrid search with ColBERT rerank via SDK query_points.

        Pipeline:
        1. Prefetch dense (100) + sparse (100) candidates
        2. RRF fusion combines both
        3. ColBERT multivector rerank on fused results -> top-K
        """
        import logging

        # Generate all embeddings for query (dense + sparse + colbert)
        query_embeddings = self.embedding_model.encode(
            query, return_dense=True, return_sparse=True, return_colbert_vecs=True
        )

        # Convert to Python/Qdrant types
        dense_vector = convert_to_python_types(query_embeddings["dense_vecs"])
        sparse_vector = lexical_weights_to_sparse(query_embeddings["lexical_weights"])
        colbert_vectors = convert_to_python_types(query_embeddings["colbert_vecs"])

        rrf_prefetch = models.Prefetch(
            prefetch=[
                models.Prefetch(query=dense_vector, using="dense", limit=100),
                models.Prefetch(query=sparse_vector, using="bm42", limit=100),
            ],
            query=models.RrfQuery(rrf=models.Rrf(k=rrf_k)),
        )

        try:
            if group_by:
                grouped_response = self.client.query_points_groups(
                    collection_name=self.collection_name,
                    prefetch=[rrf_prefetch],
                    query=colbert_vectors,
                    using="colbert",
                    group_by=group_by,
                    group_size=group_size,
                    limit=top_k,
                    with_payload=True,
                )
                return self._parse_group_results(grouped_response)

            query_response = self.client.query_points(
                collection_name=self.collection_name,
                prefetch=[rrf_prefetch],
                query=colbert_vectors,
                using="colbert",
                limit=top_k,
                with_payload=True,
            )

            return [
                SearchResult(
                    article_number=(point.payload or {}).get("article_number", ""),
                    text=(point.payload or {}).get("page_content", ""),
                    score=point.score,
                    metadata={
                        **(point.payload or {}),
                        "search_method": "hybrid_rrf_colbert",
                    },
                )
                for point in query_response.points
            ]

        except Exception as e:
            logging.warning(f"ColBERT rerank failed: {e}, falling back to RRF only")
            rrf_engine = HybridRRFSearchEngine(self.settings)
            return rrf_engine.search(query, top_k, score_threshold)

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

    def __init__(self, settings: Settings | None = None):
        """Initialize hybrid DBSF + ColBERT search engine with BGE-M3 model."""
        super().__init__(settings)
        self.embedding_model = get_bge_m3_model(use_fp16=True)

    def search(
        self,
        query_embedding: str | list[float],
        top_k: int = 10,
        score_threshold: float | None = None,
        *,
        group_by: str | None = None,
        group_size: int = 2,
    ) -> list[SearchResult]:
        """
        Search using DBSF fusion + ColBERT reranking.

        Args:
            query_embedding: Either query string or pre-computed dense embedding.
                If string, will use full hybrid search with ColBERT rerank.
                If list, will use dense-only search (backward compatibility).
            top_k: Number of results to return
            score_threshold: Minimum similarity score threshold
            group_by: Optional payload field to group results by (e.g. "metadata.doc_id").
            group_size: Max points per group when group_by is set.

        Returns:
            List of SearchResult objects
        """
        if score_threshold is None:
            score_threshold = 0.3

        # If query is a string, use full hybrid + ColBERT rerank
        if isinstance(query_embedding, str):
            return self._search_hybrid_colbert(
                query_embedding,
                top_k,
                score_threshold,
                group_by=group_by,
                group_size=group_size,
            )

        # Backward compatibility: if embedding provided, use dense-only search
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            using="dense",
            limit=top_k,
            score_threshold=score_threshold,
        )

        return [
            SearchResult(
                article_number=(result.payload or {}).get("metadata", {}).get("article_number", ""),
                text=(result.payload or {}).get("page_content", ""),
                score=result.score,
                metadata=(result.payload or {}).get("metadata", {}),
            )
            for result in response.points
        ]

    def _search_hybrid_colbert(
        self,
        query: str,
        top_k: int,
        score_threshold: float,
        *,
        group_by: str | None = None,
        group_size: int = 2,
    ) -> list[SearchResult]:
        """
        3-stage hybrid search with DBSF fusion + ColBERT rerank via SDK.

        Pipeline:
        1. Prefetch dense (100) + sparse (100) candidates
        2. DBSF fusion combines both with statistical normalization
        3. ColBERT multivector rerank on fused results -> top-K
        """
        import logging

        # Generate all embeddings
        query_embeddings = self.embedding_model.encode(
            query, return_dense=True, return_sparse=True, return_colbert_vecs=True
        )

        dense_vector = convert_to_python_types(query_embeddings["dense_vecs"])
        sparse_vector = lexical_weights_to_sparse(query_embeddings["lexical_weights"])
        colbert_vectors = convert_to_python_types(query_embeddings["colbert_vecs"])

        dbsf_prefetch = models.Prefetch(
            prefetch=[
                models.Prefetch(query=dense_vector, using="dense", limit=100),
                models.Prefetch(query=sparse_vector, using="sparse", limit=100),
            ],
            query=models.FusionQuery(fusion=models.Fusion.DBSF),
        )

        try:
            if group_by:
                grouped_response = self.client.query_points_groups(
                    collection_name=self.collection_name,
                    prefetch=[dbsf_prefetch],
                    query=colbert_vectors,
                    using="colbert",
                    group_by=group_by,
                    group_size=group_size,
                    limit=top_k,
                    with_payload=True,
                )
                return self._parse_group_results(grouped_response)

            query_response = self.client.query_points(
                collection_name=self.collection_name,
                prefetch=[dbsf_prefetch],
                query=colbert_vectors,
                using="colbert",
                limit=top_k,
                with_payload=True,
            )

            return [
                SearchResult(
                    article_number=(point.payload or {}).get("article_number", ""),
                    text=(point.payload or {}).get("page_content", ""),
                    score=point.score,
                    metadata={
                        **(point.payload or {}),
                        "search_method": "dbsf_colbert",
                    },
                )
                for point in query_response.points
            ]

        except Exception as e:
            logging.warning(f"DBSF ColBERT rerank failed: {e}, falling back to RRF")
            rrf_engine = HybridRRFColBERTSearchEngine(self.settings)
            return rrf_engine.search(query, top_k, score_threshold)

    def get_name(self) -> str:
        """Get search engine name."""
        return "dbsf_colbert"


def create_search_engine(
    engine_type: SearchEngine | None = None,
    settings: Settings | None = None,
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
    requested_engine = engine_type or settings.search_engine
    requested_key = (
        requested_engine.value
        if isinstance(requested_engine, SearchEngine)
        else str(requested_engine)
    )

    registry = {
        SearchEngine.BASELINE.value: lambda: BaselineSearchEngine(settings),
        SearchEngine.HYBRID_RRF.value: lambda: HybridRRFSearchEngine(settings),
        SearchEngine.HYBRID_RRF_COLBERT.value: lambda: HybridRRFColBERTSearchEngine(settings),
        SearchEngine.DBSF_COLBERT.value: lambda: DBSFColBERTSearchEngine(settings),
    }

    return create_engine_from_registry(
        requested_key,
        registry=registry,
        default_key=SearchEngine.HYBRID_RRF_COLBERT.value,
        fallback_on_unknown=True,
    )
