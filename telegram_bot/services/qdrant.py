"""Qdrant service with Query API, Score Boosting, MMR, and Quantization.

Smart Gateway pattern for Qdrant vector database.
Features: RRF fusion, freshness boosting, MMR diversity, binary quantization.

2026 best practices:
- Binary Quantization: 40x faster, -75% RAM (for dim >= 1024)
- Prefetch: dense + sparse in single RPC
- Rescore with oversampling for accuracy
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np
from qdrant_client import AsyncQdrantClient, models


logger = logging.getLogger(__name__)


class QdrantService:
    """Smart Gateway for Qdrant with advanced search features.

    Provides:
    - Hybrid search with RRF fusion (dense + sparse)
    - Score boosting with exp_decay (freshness)
    - MMR diversity reranking
    - Async operations with AsyncQdrantClient
    """

    def __init__(
        self,
        url: str,
        api_key: Optional[str] = None,
        collection_name: str = "documents",
        dense_vector_name: str = "dense",
        sparse_vector_name: str = "bm42",
        use_quantization: bool = True,
        quantization_rescore: bool = True,
        quantization_oversampling: float = 2.0,
    ):
        """Initialize Qdrant service.

        Args:
            url: Qdrant server URL
            api_key: Optional API key
            collection_name: Default collection name
            dense_vector_name: Name of dense vector field
            sparse_vector_name: Name of sparse vector field
            use_quantization: Enable quantized search (faster, less accurate)
            quantization_rescore: Rescore with original vectors for accuracy
            quantization_oversampling: Fetch N*limit candidates, rescore top limit
        """
        self._client = AsyncQdrantClient(url=url, api_key=api_key)
        self._collection_name = collection_name
        self._dense_vector_name = dense_vector_name
        self._sparse_vector_name = sparse_vector_name
        self._use_quantization = use_quantization
        self._quantization_rescore = quantization_rescore
        self._quantization_oversampling = quantization_oversampling

        logger.info(f"QdrantService initialized: {collection_name} (quantization={use_quantization})")

    async def hybrid_search_rrf(
        self,
        dense_vector: list[float],
        sparse_vector: Optional[dict] = None,
        filters: Optional[dict] = None,
        top_k: int = 10,
        dense_weight: float = 0.6,
        sparse_weight: float = 0.4,
        prefetch_multiplier: int = 3,
        quantization_ignore: Optional[bool] = None,
    ) -> list[dict]:
        """Hybrid search with RRF fusion (dense + sparse).

        Args:
            dense_vector: Dense embedding vector (e.g., voyage-4)
            sparse_vector: Sparse vector dict {"indices": [...], "values": [...]}
            filters: Optional metadata filters
            top_k: Number of results to return
            dense_weight: Weight for dense vector prefetch
            sparse_weight: Weight for sparse vector prefetch
            prefetch_multiplier: Multiplier for prefetch limits
            quantization_ignore: Override quantization per-request (None=use default,
                True=skip quantization, False=force quantization). Useful for A/B testing.

        Returns:
            List of results with id, score, text, metadata
        """
        # Build prefetch queries
        prefetch = []

        # Dense prefetch
        dense_limit = max(int(top_k * prefetch_multiplier * dense_weight), top_k)
        prefetch.append(
            models.Prefetch(
                query=dense_vector,
                using=self._dense_vector_name,
                limit=dense_limit,
            )
        )

        # Sparse prefetch (if available)
        if sparse_vector and sparse_vector.get("indices"):
            sparse_limit = max(int(top_k * prefetch_multiplier * sparse_weight), top_k)
            prefetch.append(
                models.Prefetch(
                    query=models.SparseVector(
                        indices=sparse_vector["indices"],
                        values=sparse_vector["values"],
                    ),
                    using=self._sparse_vector_name,
                    limit=sparse_limit,
                )
            )

        # Build search params with quantization
        # quantization_ignore: None=use default, True=skip quant, False=force quant
        search_params = None
        use_quant = self._use_quantization if quantization_ignore is None else not quantization_ignore
        if use_quant:
            search_params = models.SearchParams(
                quantization=models.QuantizationSearchParams(
                    ignore=False,  # Explicitly use quantization
                    rescore=self._quantization_rescore,
                    oversampling=self._quantization_oversampling,
                )
            )
        elif quantization_ignore is True:
            # Explicitly disable quantization for this request (A/B testing)
            search_params = models.SearchParams(
                quantization=models.QuantizationSearchParams(ignore=True)
            )

        # Execute RRF fusion search
        result = await self._client.query_points(
            collection_name=self._collection_name,
            prefetch=prefetch,
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            query_filter=self._build_filter(filters),
            limit=top_k,
            with_payload=True,
            search_params=search_params,
        )

        return self._format_results(result.points)

    async def search_with_score_boosting(
        self,
        dense_vector: list[float],
        filters: Optional[dict] = None,
        top_k: int = 10,
        freshness_boost: bool = True,
        freshness_field: str = "created_at",
        freshness_scale_days: int = 7,
        quantization_ignore: Optional[bool] = None,
    ) -> list[dict]:
        """Search with score boosting using Qdrant Query API.

        Uses exp_decay formula for freshness boosting.

        Args:
            dense_vector: Query embedding
            filters: Optional metadata filters
            top_k: Number of results
            freshness_boost: Enable freshness boosting
            freshness_field: Payload field for datetime (e.g., "created_at")
            freshness_scale_days: Decay scale in days
            quantization_ignore: Override quantization per-request (None=use default,
                True=skip quantization, False=force quantization). Useful for A/B testing.

        Returns:
            List of results with boosted scores
        """
        # Build search params with quantization
        search_params = None
        use_quant = self._use_quantization if quantization_ignore is None else not quantization_ignore
        if use_quant:
            search_params = models.SearchParams(
                quantization=models.QuantizationSearchParams(
                    ignore=False,
                    rescore=self._quantization_rescore,
                    oversampling=self._quantization_oversampling,
                )
            )
        elif quantization_ignore is True:
            search_params = models.SearchParams(
                quantization=models.QuantizationSearchParams(ignore=True)
            )

        # Base search without boosting
        if not freshness_boost:
            result = await self._client.query_points(
                collection_name=self._collection_name,
                query=dense_vector,
                using=self._dense_vector_name,
                query_filter=self._build_filter(filters),
                limit=top_k,
                with_payload=True,
                search_params=search_params,
            )
            return self._format_results(result.points)

        # Search with score boosting via Query API
        # Note: Qdrant Query API with formulas requires Qdrant 1.10+
        # For older versions, we do post-processing boosting
        try:
            result = await self._client.query_points(
                collection_name=self._collection_name,
                query=dense_vector,
                using=self._dense_vector_name,
                query_filter=self._build_filter(filters),
                limit=top_k * 2,  # Overfetch for boosting
                with_payload=True,
                search_params=search_params,
            )

            # Post-process with freshness boosting
            points = result.points
            now = datetime.now(timezone.utc)
            scale_seconds = freshness_scale_days * 86400

            boosted_results = []
            for point in points:
                base_score = point.score

                # Get datetime from payload
                created_at = point.payload.get("metadata", {}).get(freshness_field)
                if created_at:
                    try:
                        if isinstance(created_at, str):
                            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        else:
                            dt = created_at

                        # Calculate exp_decay boost
                        age_seconds = (now - dt).total_seconds()
                        decay = np.exp(-age_seconds / scale_seconds)
                        boosted_score = base_score + 0.1 * decay  # Small boost
                    except (ValueError, TypeError):
                        boosted_score = base_score
                else:
                    boosted_score = base_score

                boosted_results.append((point, boosted_score))

            # Sort by boosted score and take top_k
            boosted_results.sort(key=lambda x: x[1], reverse=True)
            top_points = [p for p, _ in boosted_results[:top_k]]

            return self._format_results(top_points)

        except Exception as e:
            logger.warning(f"Score boosting failed, falling back: {e}")
            result = await self._client.query_points(
                collection_name=self._collection_name,
                query=dense_vector,
                using=self._dense_vector_name,
                query_filter=self._build_filter(filters),
                limit=top_k,
                with_payload=True,
                search_params=search_params,
            )
            return self._format_results(result.points)

    def mmr_rerank(
        self,
        points: list[dict],
        embeddings: list[list[float]],
        lambda_mult: float = 0.5,
        top_k: int = 10,
    ) -> list[dict]:
        """Maximal Marginal Relevance reranking for diversity.

        Balances relevance and diversity in results.

        Args:
            points: Search results (list of dicts with id, score, text, metadata)
            embeddings: Corresponding embedding vectors
            lambda_mult: Diversity parameter
                - 0.0 = maximum diversity (only diversity matters)
                - 0.5 = balanced (recommended)
                - 1.0 = minimum diversity (only relevance)
            top_k: Number of results to return

        Returns:
            Reranked points with improved diversity
        """
        if not points or len(points) <= top_k:
            return points

        embeddings_array = np.array(embeddings)

        selected_indices = []
        selected_embeddings = []

        # Start with most relevant
        scores = [p["score"] for p in points]
        first_idx = int(np.argmax(scores))
        selected_indices.append(first_idx)
        selected_embeddings.append(embeddings_array[first_idx])

        # Iteratively select by MMR
        while len(selected_indices) < min(top_k, len(points)):
            best_idx = None
            best_mmr = float("-inf")

            for i in range(len(points)):
                if i in selected_indices:
                    continue

                # Relevance term (normalized score)
                relevance = points[i]["score"]

                # Max similarity to already selected
                emb = embeddings_array[i]
                similarities = []
                for sel_emb in selected_embeddings:
                    norm_emb = np.linalg.norm(emb)
                    norm_sel = np.linalg.norm(sel_emb)
                    if norm_emb > 0 and norm_sel > 0:
                        sim = float(np.dot(emb, sel_emb) / (norm_emb * norm_sel))
                    else:
                        sim = 0.0
                    similarities.append(sim)

                max_sim = max(similarities) if similarities else 0.0

                # MMR: lambda * relevance - (1-lambda) * max_similarity
                mmr = lambda_mult * relevance - (1 - lambda_mult) * max_sim

                if mmr > best_mmr:
                    best_mmr = mmr
                    best_idx = i

            if best_idx is not None:
                selected_indices.append(best_idx)
                selected_embeddings.append(embeddings_array[best_idx])

        return [points[i] for i in selected_indices]

    def _build_filter(self, filters: Optional[dict]) -> Optional[models.Filter]:
        """Build Qdrant filter from dict.

        Args:
            filters: Dict with field conditions
                - Exact match: {"city": "Sofia"}
                - Range: {"price": {"gte": 50000, "lte": 100000}}

        Returns:
            Qdrant Filter or None
        """
        if not filters:
            return None

        conditions = []

        for key, value in filters.items():
            if isinstance(value, dict):
                # Range filter
                range_params = {}
                for op in ["lt", "lte", "gt", "gte"]:
                    if op in value:
                        range_params[op] = value[op]

                if range_params:
                    conditions.append(
                        models.FieldCondition(
                            key=f"metadata.{key}",
                            range=models.Range(**range_params),
                        )
                    )
            else:
                # Exact match
                conditions.append(
                    models.FieldCondition(
                        key=f"metadata.{key}",
                        match=models.MatchValue(value=value),
                    )
                )

        return models.Filter(must=conditions) if conditions else None

    def _format_results(self, points: list[Any]) -> list[dict]:
        """Format Qdrant points to standard dict format."""
        return [
            {
                "id": str(p.id),
                "score": p.score,
                "text": p.payload.get("page_content", ""),
                "metadata": p.payload.get("metadata", {}),
            }
            for p in points
        ]

    async def enable_binary_quantization(
        self,
        collection_name: Optional[str] = None,
        always_ram: bool = True,
    ) -> bool:
        """Enable binary quantization on collection for 40x faster search.

        Binary quantization reduces each dimension to 1 bit, achieving:
        - 32x memory compression
        - Up to 40x faster search
        - Works best with dim >= 1024 (voyage-4-large is 1024)

        Args:
            collection_name: Collection to update (default: self._collection_name)
            always_ram: Keep quantized vectors in RAM for speed

        Returns:
            True if successful
        """
        coll = collection_name or self._collection_name
        try:
            await self._client.update_collection(
                collection_name=coll,
                quantization_config=models.BinaryQuantization(
                    binary=models.BinaryQuantizationConfig(always_ram=always_ram),
                ),
            )
            logger.info(f"Binary quantization enabled for {coll}")
            return True
        except Exception as e:
            logger.error(f"Failed to enable binary quantization: {e}")
            return False

    async def get_collection_info(self, collection_name: Optional[str] = None) -> dict:
        """Get collection info including quantization status.

        Args:
            collection_name: Collection to check

        Returns:
            Dict with collection info
        """
        coll = collection_name or self._collection_name
        try:
            info = await self._client.get_collection(collection_name=coll)
            return {
                "name": coll,
                "points_count": info.points_count,
                "vectors_count": info.vectors_count,
                "status": info.status.value,
                "quantization": str(info.config.quantization_config) if info.config.quantization_config else None,
            }
        except Exception as e:
            logger.error(f"Failed to get collection info: {e}")
            return {}

    async def close(self):
        """Close the client connection."""
        await self._client.close()
