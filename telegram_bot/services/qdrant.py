"""Qdrant service with Query API, Score Boosting, and MMR.

Smart Gateway pattern for Qdrant vector database.
Features: RRF fusion, freshness boosting, MMR diversity.
"""

import logging
from typing import Any
from urllib.parse import urlparse

import numpy as np
from qdrant_client import AsyncQdrantClient, models

from src.config.qdrant_policy import resolve_collection_name
from telegram_bot.observability import get_client, observe


logger = logging.getLogger(__name__)


class QdrantService:
    """Smart Gateway for Qdrant with advanced search features.

    Provides:
    - Hybrid search with RRF fusion (dense + sparse)
    - Score boosting with exp_decay (freshness)
    - MMR diversity reranking
    - Async operations with AsyncQdrantClient
    - Quantization mode-based collection selection
    """

    # ACORN filtered search (Feb 2026): Code ready in src/retrieval/search_engines.py
    # but AcornSearchParams not yet exported by qdrant-client SDK.
    # Track: waiting for qdrant-client 1.18+ release. See #590.

    def __init__(
        self,
        url: str,
        api_key: str | None = None,
        collection_name: str = "documents",
        dense_vector_name: str = "dense",
        sparse_vector_name: str = "bm42",
        quantization_mode: str = "off",
        timeout: int = 30,
    ):
        """Initialize Qdrant service.

        Args:
            url: Qdrant server URL
            api_key: Optional API key
            collection_name: Default collection name (base, without suffix)
            dense_vector_name: Name of dense vector field
            sparse_vector_name: Name of sparse vector field
            quantization_mode: One of 'off', 'scalar', 'binary' - controls collection suffix
            timeout: Connection timeout in seconds (default 30)
        """
        # Strip api_key for http:// to avoid "insecure connection" warning (#570)
        scheme = urlparse(url).scheme.lower()
        effective_api_key = api_key if scheme == "https" else None
        self._client = AsyncQdrantClient(
            url=url, api_key=effective_api_key, prefer_grpc=True, timeout=timeout
        )
        self._base_collection_name = collection_name
        self._quantization_mode = quantization_mode.lower()
        self._collection_name = self._get_collection_name(collection_name, quantization_mode)
        self._dense_vector_name = dense_vector_name
        self._sparse_vector_name = sparse_vector_name
        self._collection_validated = False
        self._colbert_available: bool | None = None

        logger.info(
            f"QdrantService initialized: {self._collection_name} (mode={quantization_mode})"
        )

    @staticmethod
    def _get_collection_name(base_name: str, mode: str) -> str:
        """Get collection name with appropriate suffix based on quantization mode.

        Args:
            base_name: Base collection name
            mode: Quantization mode ('off', 'scalar', 'binary')

        Returns:
            Collection name with suffix
        """
        return resolve_collection_name(base_name, mode)

    @property
    def collection_name(self) -> str:
        """Get the current collection name (with quantization suffix)."""
        return self._collection_name

    @property
    def client(self) -> AsyncQdrantClient:
        """Expose underlying client for helper services (e.g., small-to-big)."""
        return self._client

    def set_quantization_mode(self, mode: str) -> None:
        """Change quantization mode and update collection name.

        Args:
            mode: New quantization mode ('off', 'scalar', 'binary')
        """
        self._quantization_mode = mode.lower()
        self._collection_name = self._get_collection_name(self._base_collection_name, mode)
        self._collection_validated = False
        logger.info(f"QdrantService: switched to {self._collection_name} (mode={mode})")

    @observe(name="qdrant-apply-strict-mode", capture_input=False, capture_output=False)
    async def _apply_strict_mode(self) -> None:
        """Apply conservative strict mode limits to the current collection.

        Sets server-side guardrails to prevent runaway queries:
          - max_query_limit=100  — caps result set size per query
          - max_timeout=30       — prevents queries from blocking too long
          - search_max_hnsw_ef=512 — caps HNSW graph traversal depth

        Called after ensure_collection() during initialization. Non-blocking:
        if the server does not support StrictModeConfig (older version or error),
        a warning is logged and startup continues.
        """
        lf = get_client()
        lf.update_current_span(input={"collection": self._collection_name})
        try:
            strict_config = models.StrictModeConfig(
                enabled=True,
                max_query_limit=100,
                max_timeout=30,
                search_max_hnsw_ef=512,
            )
            await self._client.update_collection(
                collection_name=self._collection_name,
                strict_mode_config=strict_config,
            )
            logger.info(
                "QdrantService: strict mode applied to '%s' "
                "(max_query_limit=100, max_timeout=30, search_max_hnsw_ef=512)",
                self._collection_name,
            )
            lf.update_current_span(
                output={
                    "collection": self._collection_name,
                    "strict_mode_applied": True,
                }
            )
        except Exception as exc:
            logger.warning(
                "QdrantService: strict mode not applied to '%s': %s",
                self._collection_name,
                exc,
            )
            lf.update_current_span(
                level="WARNING",
                status_message=f"Strict mode not applied: {type(exc).__name__}",
                output={
                    "collection": self._collection_name,
                    "strict_mode_applied": False,
                    "error": type(exc).__name__,
                },
            )

    @observe(name="qdrant-ensure-alias", capture_input=False, capture_output=False)
    async def _ensure_alias(self) -> None:
        """Ensure the collection alias '{name}_active' points to the current collection.

        Creates or updates alias '{collection_name}_active' → current collection name.

        Blue/green cutover pattern: to cut over to a new collection without downtime,
        call update_collection_aliases() to atomically switch the alias from the old
        collection to the new one. Bot reads via alias after the switch.

        Called after ensure_collection() during initialization. Non-blocking:
        alias creation failure is logged as a warning and does not block startup.
        """
        alias_name = f"{self._collection_name}_active"
        lf = get_client()
        lf.update_current_span(
            input={"collection": self._collection_name, "alias_name": alias_name}
        )
        try:
            aliases = await self._client.get_aliases()
            current_target = next(
                (
                    alias.collection_name
                    for alias in aliases.aliases
                    if alias.alias_name == alias_name
                ),
                None,
            )

            if current_target == self._collection_name:
                logger.info(
                    "QdrantService: alias '%s' already points to '%s'",
                    alias_name,
                    self._collection_name,
                )
                lf.update_current_span(
                    output={
                        "alias_name": alias_name,
                        "alias_updated": False,
                        "already_pointing": True,
                    }
                )
                return

            operations: list[
                models.CreateAliasOperation
                | models.DeleteAliasOperation
                | models.RenameAliasOperation
            ] = []
            if current_target is not None:
                operations.append(
                    models.DeleteAliasOperation(
                        delete_alias=models.DeleteAlias(alias_name=alias_name)
                    )
                )
            operations.append(
                models.CreateAliasOperation(
                    create_alias=models.CreateAlias(
                        collection_name=self._collection_name,
                        alias_name=alias_name,
                    )
                )
            )
            await self._client.update_collection_aliases(change_aliases_operations=operations)
            logger.info(
                "QdrantService: alias '%s' → '%s' ensured",
                alias_name,
                self._collection_name,
            )
            lf.update_current_span(
                output={
                    "alias_name": alias_name,
                    "alias_updated": True,
                    "previous_target": current_target,
                }
            )
        except Exception as exc:
            logger.warning(
                "QdrantService: alias '%s' creation failed: %s",
                alias_name,
                exc,
            )
            lf.update_current_span(
                level="WARNING",
                status_message=f"Alias ensure failed: {type(exc).__name__}",
                output={
                    "alias_name": alias_name,
                    "alias_updated": False,
                    "error": type(exc).__name__,
                },
            )

    @observe(name="qdrant-ensure-collection", capture_input=False, capture_output=False)
    async def ensure_collection(self) -> None:
        """Ensure the configured collection exists; fallback to base collection if needed.

        This prevents hard failures when quantization_mode points to a suffix collection
        that hasn't been created/reindexed yet.
        """
        lf = get_client()
        lf.update_current_span(
            input={
                "requested_collection": self._collection_name,
                "base_collection": self._base_collection_name,
                "quantization_mode": self._quantization_mode,
            }
        )

        if self._collection_validated:
            if self._colbert_available is None:
                await self._refresh_collection_capabilities()
            lf.update_current_span(
                output={
                    "validated": True,
                    "active_collection": self._collection_name,
                    "fallback_used": False,
                    "cached_validation": True,
                }
            )
            return

        try:
            resp = await self._client.get_collections()
            names = {c.name for c in resp.collections}
        except Exception as e:
            # If we can't list collections, let the actual query raise a meaningful error.
            logger.warning(f"QdrantService: unable to list collections: {e}")
            lf.update_current_span(
                level="WARNING",
                status_message=f"Unable to list collections: {type(e).__name__}",
                output={"validated": False, "list_collections_failed": True},
            )
            return

        if self._collection_name in names:
            self._collection_validated = True
            await self._refresh_collection_capabilities()
            await self._apply_strict_mode()
            await self._ensure_alias()
            lf.update_current_span(
                output={
                    "validated": True,
                    "active_collection": self._collection_name,
                    "fallback_used": False,
                }
            )
            return

        # Fallback: use base collection if it exists.
        if self._base_collection_name in names:
            logger.warning(
                "QdrantService: collection '%s' not found, falling back to base '%s'",
                self._collection_name,
                self._base_collection_name,
            )
            self._collection_name = self._base_collection_name
            self._quantization_mode = "off"
            self._collection_validated = True
            await self._refresh_collection_capabilities()
            await self._apply_strict_mode()
            await self._ensure_alias()
            lf.update_current_span(
                output={
                    "validated": True,
                    "active_collection": self._collection_name,
                    "fallback_used": True,
                }
            )
            return

        lf.update_current_span(
            level="ERROR",
            status_message="Qdrant collection validation failed",
            output={
                "validated": False,
                "requested_collection": self._collection_name,
                "base_collection": self._base_collection_name,
            },
        )
        raise RuntimeError(
            f"Qdrant collection '{self._collection_name}' not found "
            f"(base '{self._base_collection_name}' also missing)"
        )

    async def _refresh_collection_capabilities(self) -> None:
        """Refresh runtime capability flags from collection config."""
        try:
            info = await self._client.get_collection(self._collection_name)
            dense_vectors = info.config.params.vectors
            dense_names = set(dense_vectors.keys()) if isinstance(dense_vectors, dict) else set()
            colbert_present = "colbert" in dense_names
            if self._colbert_available is None and not colbert_present:
                logger.info(
                    "QdrantService: collection '%s' missing 'colbert' vector; "
                    "server-side ColBERT disabled (RRF fallback active)",
                    self._collection_name,
                )
            self._colbert_available = colbert_present
        except Exception as exc:
            logger.debug(
                "QdrantService: failed to inspect vector config for %s: %s",
                self._collection_name,
                exc,
            )

    @staticmethod
    def _is_missing_vector_error(exc: Exception) -> bool:
        """Detect errors that indicate absent vector names in collection config."""
        msg = str(exc).lower()
        return "not existing vector name" in msg or "requires specified vector name" in msg

    @observe(name="qdrant-hybrid-search-rrf", capture_input=False, capture_output=False)
    async def hybrid_search_rrf(
        self,
        dense_vector: list[float],
        sparse_vector: dict | None = None,
        filters: dict | None = None,
        top_k: int = 10,
        dense_weight: float = 0.6,
        sparse_weight: float = 0.4,
        prefetch_multiplier: int = 3,
        # Quantization A/B testing params
        quantization_ignore: bool | None = None,
        quantization_rescore: bool = True,
        quantization_oversampling: float = 2.0,
        # RRF tuning
        rrf_k: int = 60,
        # Grouping for diverse results
        group_by: str | None = None,
        group_size: int = 2,
        # Per-call error meta (#117)
        return_meta: bool = False,
    ) -> list[dict] | tuple[list[dict], dict[str, Any]]:
        """Hybrid search with RRF fusion (dense + sparse).

        Args:
            dense_vector: Dense embedding vector (e.g., voyage-4)
            sparse_vector: Sparse vector dict {"indices": [...], "values": [...]}
            filters: Optional metadata filters
            top_k: Number of results to return
            dense_weight: Weight for dense vector prefetch
            sparse_weight: Weight for sparse vector prefetch
            prefetch_multiplier: Multiplier for prefetch limits
            quantization_ignore: If True, skip quantization (use full vectors)
            quantization_rescore: If True, rescore with original vectors
            quantization_oversampling: Oversampling factor for quantized search
            rrf_k: RRF constant k (higher = more weight to lower-ranked results).
            group_by: Optional payload field to group results by (e.g. "metadata.doc_id").
            group_size: Max points per group when group_by is set.
            return_meta: If True, return (results, meta) tuple with backend_error info.

        Returns:
            If return_meta=False: list of results (backward compatible).
            If return_meta=True: (results, meta) where meta has
                backend_error, error_type, error_message.
        """
        await self.ensure_collection()
        lf = get_client()
        lf.update_current_span(
            input={
                "collection": self._collection_name,
                "top_k": top_k,
                "has_sparse": bool(sparse_vector and sparse_vector.get("indices")),
                "has_filters": bool(filters),
                "group_by": group_by,
                "rrf_k": rrf_k,
            }
        )
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

        # Build search params for quantization A/B testing
        search_params = None
        if quantization_ignore is not None:
            search_params = models.SearchParams(
                quantization=models.QuantizationSearchParams(
                    ignore=quantization_ignore,
                    rescore=quantization_rescore,
                    oversampling=quantization_oversampling,
                )
            )

        rrf_query = models.RrfQuery(rrf=models.Rrf(k=rrf_k))
        ok_meta: dict[str, Any] = {
            "backend_error": False,
            "error_type": None,
            "error_message": None,
        }

        # Execute RRF fusion search with graceful degradation
        try:
            if group_by:
                group_result = await self._client.query_points_groups(
                    collection_name=self._collection_name,
                    prefetch=prefetch,
                    query=rrf_query,
                    query_filter=self._build_filter(filters),
                    group_by=group_by,
                    group_size=group_size,
                    limit=top_k,
                    with_payload=True,
                    search_params=search_params,
                )
                results = self._format_group_results(group_result)
                lf.update_current_span(
                    output={
                        "results_count": len(results),
                        "top_score": results[0]["score"] if results else None,
                        "grouped": True,
                    }
                )
                if return_meta:
                    return results, ok_meta
                return results

            result = await self._client.query_points(
                collection_name=self._collection_name,
                prefetch=prefetch,
                query=rrf_query,
                query_filter=self._build_filter(filters),
                limit=top_k,
                with_payload=True,
                search_params=search_params,
            )
            results = self._format_results(result.points)
            lf.update_current_span(
                output={
                    "results_count": len(results),
                    "top_score": results[0]["score"] if results else None,
                    "grouped": False,
                }
            )
            if return_meta:
                return results, ok_meta
            return results
        except Exception as e:
            # Graceful degradation: return empty list on any Qdrant error
            logger.error(f"Qdrant search failed (graceful degradation): {e}")
            lf.update_current_span(
                level="ERROR",
                status_message=f"Qdrant search failed: {type(e).__name__}: {str(e)[:200]}",
                output={
                    "results_count": 0,
                    "error": type(e).__name__,
                    "collection": self._collection_name,
                },
            )
            if return_meta:
                return [], {
                    "backend_error": True,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                }
            return []

    @observe(name="qdrant-hybrid-search-rrf-colbert", capture_input=False, capture_output=False)
    async def hybrid_search_rrf_colbert(
        self,
        dense_vector: list[float],
        colbert_query: list[list[float]],
        sparse_vector: dict | None = None,
        filters: dict | None = None,
        top_k: int = 5,
        dense_limit: int = 100,
        sparse_limit: int = 100,
        rrf_k: int = 60,
        return_meta: bool = False,
    ) -> list[dict] | tuple[list[dict], dict[str, Any]]:
        """3-stage hybrid search: dense+sparse -> RRF fusion -> ColBERT MaxSim rerank.

        Uses Qdrant nested prefetch to perform all three stages server-side
        in a single query_points call. ColBERT reranking uses pre-stored
        multivectors (no CPU-side encoding needed for documents).

        Args:
            dense_vector: Dense embedding for semantic search
            colbert_query: ColBERT query token vectors (num_tokens x 1024)
            sparse_vector: Optional sparse vector {"indices": [...], "values": [...]}
            filters: Optional metadata filters
            top_k: Final number of results after ColBERT reranking
            dense_limit: Number of dense candidates for RRF
            sparse_limit: Number of sparse candidates for RRF
            rrf_k: RRF constant k
            return_meta: If True, return (results, meta) tuple

        Returns:
            Reranked results (ColBERT MaxSim scores).
        """
        await self.ensure_collection()
        lf = get_client()
        lf.update_current_span(
            input={
                "collection": self._collection_name,
                "top_k": top_k,
                "has_sparse": bool(sparse_vector and sparse_vector.get("indices")),
                "has_filters": bool(filters),
                "colbert_tokens": len(colbert_query) if colbert_query else 0,
                "rrf_k": rrf_k,
            }
        )
        if self._colbert_available is False:
            logger.debug(
                "Qdrant ColBERT skipped: vector unavailable in collection %s; using RRF",
                self._collection_name,
            )
            fallback = await self.hybrid_search_rrf(
                dense_vector=dense_vector,
                sparse_vector=sparse_vector,
                filters=filters,
                top_k=top_k,
                rrf_k=rrf_k,
                return_meta=return_meta,
            )
            fallback_results = fallback[0] if isinstance(fallback, tuple) else fallback
            lf.update_current_span(
                output={
                    "fallback_reason": "colbert_unavailable",
                    "results_count": len(fallback_results),
                    "top_score": fallback_results[0]["score"] if fallback_results else None,
                }
            )
            return fallback

        if not colbert_query:
            logger.warning(
                "Qdrant ColBERT search skipped: empty query vectors, falling back to RRF"
            )
            fallback = await self.hybrid_search_rrf(
                dense_vector=dense_vector,
                sparse_vector=sparse_vector,
                filters=filters,
                top_k=top_k,
                rrf_k=rrf_k,
                return_meta=return_meta,
            )
            fallback_results = fallback[0] if isinstance(fallback, tuple) else fallback
            lf.update_current_span(
                output={
                    "fallback_reason": "empty_colbert_query",
                    "results_count": len(fallback_results),
                    "top_score": fallback_results[0]["score"] if fallback_results else None,
                }
            )
            return fallback

        # Inner prefetch: dense + sparse candidates
        inner_prefetch = [
            models.Prefetch(
                query=dense_vector,
                using=self._dense_vector_name,
                limit=dense_limit,
            )
        ]

        if sparse_vector and sparse_vector.get("indices"):
            inner_prefetch.append(
                models.Prefetch(
                    query=models.SparseVector(
                        indices=sparse_vector["indices"],
                        values=sparse_vector["values"],
                    ),
                    using=self._sparse_vector_name,
                    limit=sparse_limit,
                )
            )

        # Middle stage: RRF fusion of dense + sparse
        # Overfetch so ColBERT has enough candidates to meaningfully rerank
        rrf_limit = max(top_k * 4, 20)
        rrf_prefetch = models.Prefetch(
            prefetch=inner_prefetch,
            query=models.RrfQuery(rrf=models.Rrf(k=rrf_k)),
            limit=rrf_limit,
        )

        ok_meta: dict[str, Any] = {
            "backend_error": False,
            "error_type": None,
            "error_message": None,
        }

        try:
            # Outer stage: ColBERT MaxSim reranking on pre-stored multivectors
            result = await self._client.query_points(
                collection_name=self._collection_name,
                prefetch=[rrf_prefetch],
                query=colbert_query,
                using="colbert",
                query_filter=self._build_filter(filters),
                limit=top_k,
                with_payload=True,
            )
            results = self._format_results(result.points)
            if not results:
                logger.info(
                    "metric",
                    extra={"metric_name": "colbert_rerank_empty", "value": 1},
                )
                logger.warning(
                    "Qdrant ColBERT returned 0 docs for collection %s, falling back to RRF",
                    self._collection_name,
                )
                logger.info(
                    "metric",
                    extra={"metric_name": "colbert_fallback_to_rrf", "value": 1},
                )
                fallback = await self.hybrid_search_rrf(
                    dense_vector=dense_vector,
                    sparse_vector=sparse_vector,
                    filters=filters,
                    top_k=top_k,
                    rrf_k=rrf_k,
                    return_meta=return_meta,
                )
                fallback_results = fallback[0] if isinstance(fallback, tuple) else fallback
                lf.update_current_span(
                    output={
                        "fallback_reason": "colbert_empty",
                        "results_count": len(fallback_results),
                        "top_score": fallback_results[0]["score"] if fallback_results else None,
                    }
                )
                if fallback_results:
                    self._colbert_available = False
                    logger.info(
                        "Qdrant ColBERT disabled for collection %s: no point-level "
                        "ColBERT vectors detected (RRF returned %d docs)",
                        self._collection_name,
                        len(fallback_results),
                    )
                return fallback
            lf.update_current_span(
                output={
                    "fallback_reason": None,
                    "results_count": len(results),
                    "top_score": results[0]["score"] if results else None,
                }
            )
            if return_meta:
                return results, ok_meta
            return results
        except Exception as e:
            if self._is_missing_vector_error(e):
                self._colbert_available = False
                logger.info(
                    "Qdrant ColBERT disabled for collection %s: %s",
                    self._collection_name,
                    e,
                )
            logger.warning(
                "Qdrant ColBERT search failed (%s: %s), falling back to RRF",
                type(e).__name__,
                e,
            )
            lf.update_current_span(
                level="WARNING",
                status_message=f"ColBERT search failed: {type(e).__name__}",
            )
            fallback = await self.hybrid_search_rrf(
                dense_vector=dense_vector,
                sparse_vector=sparse_vector,
                filters=filters,
                top_k=top_k,
                rrf_k=rrf_k,
                return_meta=return_meta,
            )
            fallback_results = fallback[0] if isinstance(fallback, tuple) else fallback
            lf.update_current_span(
                output={
                    "fallback_reason": f"colbert_error:{type(e).__name__}",
                    "results_count": len(fallback_results),
                    "top_score": fallback_results[0]["score"] if fallback_results else None,
                }
            )
            return fallback

    @observe(name="qdrant-batch-search-rrf", capture_input=False, capture_output=False)
    async def batch_search_rrf(
        self,
        queries: list[dict],
        filters: dict | None = None,
        top_k: int = 10,
        prefetch_multiplier: int = 3,
        rrf_k: int = 60,
    ) -> list[dict]:
        """Batch hybrid search for multiple queries in a single round-trip.

        Sends all queries to Qdrant via query_batch_points, reducing N round-trips
        to 1. Useful for HyDE (2-3 query variations) and multi-query scenarios.
        Results are merged and deduplicated by point ID, keeping the best score.

        Args:
            queries: List of query dicts, each with:
                - "dense_vector": list[float] (required)
                - "sparse_vector": dict with "indices"/"values" (optional)
            filters: Optional metadata filters (shared across all queries)
            top_k: Number of results per query
            prefetch_multiplier: Overfetch ratio for prefetch
            rrf_k: RRF constant k

        Returns:
            Deduplicated list of results sorted by best score, capped at top_k.
        """
        if not queries:
            return []

        await self.ensure_collection()
        lf = get_client()
        lf.update_current_span(
            input={
                "collection": self._collection_name,
                "queries_count": len(queries),
                "top_k": top_k,
                "has_filters": bool(filters),
                "rrf_k": rrf_k,
            }
        )

        query_filter = self._build_filter(filters)
        requests = []

        for q in queries:
            dense_vector = q["dense_vector"]
            sparse_vector = q.get("sparse_vector")

            prefetch = [
                models.Prefetch(
                    query=dense_vector,
                    using=self._dense_vector_name,
                    limit=max(int(top_k * prefetch_multiplier * 0.6), top_k),
                ),
            ]

            if sparse_vector and sparse_vector.get("indices"):
                prefetch.append(
                    models.Prefetch(
                        query=models.SparseVector(
                            indices=sparse_vector["indices"],
                            values=sparse_vector["values"],
                        ),
                        using=self._sparse_vector_name,
                        limit=max(int(top_k * prefetch_multiplier * 0.4), top_k),
                    )
                )

            requests.append(
                models.QueryRequest(
                    prefetch=prefetch,
                    query=models.RrfQuery(rrf=models.Rrf(k=rrf_k)),
                    filter=query_filter,
                    limit=top_k,
                    with_payload=True,
                )
            )

        try:
            responses = await self._client.query_batch_points(
                collection_name=self._collection_name,
                requests=requests,
            )

            # Merge and deduplicate across all query responses
            seen: dict[str, dict] = {}
            for response in responses:
                for point in response.points:
                    pid = str(point.id)
                    payload = point.payload or {}
                    formatted = {
                        "id": pid,
                        "score": point.score,
                        "text": payload.get("page_content", ""),
                        "metadata": payload.get("metadata", {}),
                    }
                    if pid not in seen or point.score > seen[pid]["score"]:
                        seen[pid] = formatted

            merged = sorted(seen.values(), key=lambda x: x["score"], reverse=True)
            result = merged[:top_k]
            lf.update_current_span(
                output={
                    "results_count": len(result),
                    "unique_points": len(seen),
                    "top_score": result[0]["score"] if result else None,
                }
            )
            return result

        except Exception as e:
            logger.error(f"Qdrant batch search failed (graceful degradation): {e}")
            lf.update_current_span(
                level="ERROR",
                status_message=f"Batch search failed: {type(e).__name__}",
                output={"results_count": 0, "error": type(e).__name__},
            )
            return []

    @observe(name="qdrant-search-score-boosting", capture_input=False, capture_output=False)
    async def search_with_score_boosting(
        self,
        dense_vector: list[float],
        filters: dict | None = None,
        top_k: int = 10,
        freshness_boost: bool = True,
        freshness_field: str = "created_at",
        freshness_scale_days: int = 7,
    ) -> list[dict]:
        """Search with server-side score boosting using FormulaQuery.

        Uses FormulaQuery with exp_decay for freshness boosting (Qdrant 1.14+).
        Formula: $score + 0.1 * exp_decay(metadata.{field}, scale=N days)
        Note: payload field used in formula benefits from a payload index.

        FormulaQuery freshness boosting: implemented and tested but not wired into
        rag_pipeline. Decision (2026-02-24, #590): Keep as opt-in capability.
        NOT connected to production pipeline -- requires product decision on freshness
        ranking. ACORN also blocked pending qdrant-client export of AcornSearchParams.
        See #590 for full audit. Strict mode + aliases are active (see ensure_collection).

        Args:
            dense_vector: Query embedding
            filters: Optional metadata filters
            top_k: Number of results
            freshness_boost: Enable freshness boosting
            freshness_field: Payload field for datetime
            freshness_scale_days: Decay scale in days

        Returns:
            List of results with boosted scores
        """
        await self.ensure_collection()
        lf = get_client()
        lf.update_current_span(
            input={
                "collection": self._collection_name,
                "top_k": top_k,
                "has_filters": bool(filters),
                "freshness_boost": freshness_boost,
                "freshness_field": freshness_field,
                "freshness_scale_days": freshness_scale_days,
            }
        )

        if not freshness_boost:
            result = await self._client.query_points(
                collection_name=self._collection_name,
                query=dense_vector,
                using=self._dense_vector_name,
                query_filter=self._build_filter(filters),
                limit=top_k,
                with_payload=True,
            )
            plain_results = self._format_results(result.points)
            lf.update_current_span(
                output={
                    "mode": "plain",
                    "results_count": len(plain_results),
                    "top_score": plain_results[0]["score"] if plain_results else None,
                }
            )
            return plain_results

        formula_query = models.FormulaQuery(
            formula=models.SumExpression(
                sum=[
                    "$score",
                    models.MultExpression(
                        mult=[
                            0.1,
                            models.ExpDecayExpression(
                                exp_decay=models.DecayParamsExpression(
                                    x=models.DatetimeKeyExpression(
                                        datetime_key=f"metadata.{freshness_field}"
                                    ),
                                    scale=float(freshness_scale_days),
                                )
                            ),
                        ]
                    ),
                ]
            ),
        )

        try:
            result = await self._client.query_points(
                collection_name=self._collection_name,
                prefetch=models.Prefetch(
                    query=dense_vector,
                    using=self._dense_vector_name,
                    limit=top_k,
                ),
                query=formula_query,
                query_filter=self._build_filter(filters),
                limit=top_k,
                with_payload=True,
            )
            boosted_results = self._format_results(result.points)
            lf.update_current_span(
                output={
                    "mode": "boosted",
                    "results_count": len(boosted_results),
                    "top_score": boosted_results[0]["score"] if boosted_results else None,
                }
            )
            return boosted_results

        except Exception as e:
            logger.warning(f"FormulaQuery score boosting failed, falling back: {e}")
            lf.update_current_span(
                level="WARNING",
                status_message=f"Score boosting fallback: {type(e).__name__}",
            )
            result = await self._client.query_points(
                collection_name=self._collection_name,
                query=dense_vector,
                using=self._dense_vector_name,
                query_filter=self._build_filter(filters),
                limit=top_k,
                with_payload=True,
            )
            fallback_results = self._format_results(result.points)
            lf.update_current_span(
                output={
                    "mode": "fallback_plain",
                    "results_count": len(fallback_results),
                    "top_score": fallback_results[0]["score"] if fallback_results else None,
                    "fallback_error": type(e).__name__,
                }
            )
            return fallback_results

    @observe(name="qdrant-mmr-rerank", capture_input=False, capture_output=False)
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
        lf = get_client()
        lf.update_current_span(
            input={
                "points_count": len(points),
                "embeddings_count": len(embeddings),
                "top_k": top_k,
                "lambda_mult": lambda_mult,
            }
        )

        if not points or len(points) <= top_k:
            lf.update_current_span(output={"results_count": len(points), "rerank_applied": False})
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

        reranked = [points[i] for i in selected_indices]
        lf.update_current_span(output={"results_count": len(reranked), "rerank_applied": True})
        return reranked

    def _build_filter(self, filters: dict | None) -> models.Filter | None:
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

        return models.Filter(must=conditions) if conditions else None  # type: ignore[arg-type]  # list invariance

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

    def _format_group_results(self, result: Any) -> list[dict]:
        """Format grouped Qdrant results to flat list of dicts."""
        results: list[dict] = []
        for group in result.groups:
            for p in group.hits:
                results.append(
                    {
                        "id": str(p.id),
                        "score": p.score,
                        "text": p.payload.get("page_content", ""),
                        "metadata": p.payload.get("metadata", {}),
                    }
                )
        return results

    async def close(self):
        """Close the client connection."""
        await self._client.close()
