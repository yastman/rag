"""Hybrid retrieval service with RRF fusion."""

import logging
from typing import Any, Optional

from qdrant_client import QdrantClient, models


logger = logging.getLogger(__name__)


class HybridRetrieverService:
    """Hybrid search with dense + sparse vectors and RRF fusion.

    Combines:
    - Dense vectors (Voyage AI embeddings)
    - Sparse vectors (FastEmbed BM42)
    - RRF fusion with dynamic weights based on query type
    """

    def __init__(
        self,
        url: str,
        api_key: str,
        collection_name: str,
        dense_vector_name: str = "dense",
        sparse_vector_name: str = "sparse",
    ):
        """Initialize hybrid retriever.

        Args:
            url: Qdrant URL
            api_key: Qdrant API key
            collection_name: Collection to search
            dense_vector_name: Name of dense vector field
            sparse_vector_name: Name of sparse vector field
        """
        self.url = url
        self.api_key = api_key
        self.collection_name = collection_name
        self.dense_vector_name = dense_vector_name
        self.sparse_vector_name = sparse_vector_name
        self.client: Optional[QdrantClient] = None
        self._is_healthy = False

        try:
            if api_key:
                self.client = QdrantClient(url=url, api_key=api_key, timeout=5.0)
            else:
                self.client = QdrantClient(url=url, timeout=5.0)

            self.client.get_collections()
            self._is_healthy = True
            logger.info(f"HybridRetriever connected: {collection_name}")
        except Exception as e:
            logger.error(f"HybridRetriever init failed: {e}")
            self.client = None
            self._is_healthy = False

    def hybrid_search(
        self,
        dense_vector: list[float],
        sparse_indices: list[int],
        sparse_values: list[float],
        rrf_weights: tuple[float, float] = (0.6, 0.4),
        filters: Optional[dict[str, Any]] = None,
        top_k: int = 5,
        prefetch_multiplier: int = 4,
    ) -> list[dict[str, Any]]:
        """Perform hybrid search with RRF fusion.

        Args:
            dense_vector: Dense embedding vector
            sparse_indices: Sparse vector indices
            sparse_values: Sparse vector values
            rrf_weights: (dense_weight, sparse_weight) for prefetch limits
            filters: Optional metadata filters
            top_k: Number of results to return
            prefetch_multiplier: Multiplier for prefetch limits

        Returns:
            List of results with text, metadata, score.
        """
        if not self.client or not self._is_healthy:
            logger.error("Qdrant client unavailable")
            return []

        try:
            dense_weight, sparse_weight = rrf_weights
            base_prefetch = top_k * prefetch_multiplier

            # Calculate weighted prefetch limits
            dense_limit = max(int(base_prefetch * dense_weight), top_k)
            sparse_limit = max(int(base_prefetch * sparse_weight), top_k)

            # Build prefetch queries
            prefetch = [
                models.Prefetch(
                    query=dense_vector,
                    using=self.dense_vector_name,
                    limit=dense_limit,
                ),
            ]

            # Add sparse prefetch if vectors provided
            if sparse_indices and sparse_values:
                prefetch.append(
                    models.Prefetch(
                        query=models.SparseVector(
                            indices=sparse_indices,
                            values=sparse_values,
                        ),
                        using=self.sparse_vector_name,
                        limit=sparse_limit,
                    )
                )

            # Build filter
            query_filter = self._build_filter(filters) if filters else self._build_base_filter()

            # Execute hybrid search with RRF
            results = self.client.query_points(
                collection_name=self.collection_name,
                prefetch=prefetch,
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
            )

            # Format results
            formatted = []
            for point in results.points:
                formatted.append(
                    {
                        "text": point.payload.get("page_content", ""),
                        "metadata": point.payload.get("metadata", {}),
                        "score": point.score,
                    }
                )

            logger.info(f"Hybrid search: {len(formatted)} results (RRF weights: {rrf_weights})")
            return formatted

        except Exception as e:
            logger.error(f"Hybrid search failed: {e}", exc_info=True)
            self._is_healthy = False
            return []

    def _build_base_filter(self) -> models.Filter:
        """Build base filter for CSV rows only."""
        return models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.source_type",
                    match=models.MatchValue(value="csv_row"),
                )
            ]
        )

    def _build_filter(self, filters: dict[str, Any]) -> models.Filter:
        """Build Qdrant filter from dict."""
        conditions = [
            models.FieldCondition(
                key="metadata.source_type",
                match=models.MatchValue(value="csv_row"),
            )
        ]

        for field, value in filters.items():
            if isinstance(value, (str, int)):
                conditions.append(
                    models.FieldCondition(
                        key=f"metadata.{field}",
                        match=models.MatchValue(value=value),
                    )
                )
            elif isinstance(value, dict):
                range_params = {}
                for op in ["lt", "lte", "gt", "gte"]:
                    if op in value:
                        range_params[op] = value[op]
                if range_params:
                    conditions.append(
                        models.FieldCondition(
                            key=f"metadata.{field}",
                            range=models.Range(**range_params),
                        )
                    )

        return models.Filter(must=conditions)
