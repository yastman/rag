"""Qdrant service with Query API, Score Boosting, and MMR (canonical home, #2047).

Moved from ``telegram_bot/services/qdrant.py`` as part of the
reverse-layering fix tracked under #1948 / #2047 / #2049. The legacy
``telegram_bot.services.qdrant`` module is kept as a thin re-export so
existing imports across the test suite, ``telegram_bot/`` internals,
and external consumers continue to work without churn.

Smart Gateway pattern for Qdrant vector database.
Features: RRF fusion, freshness boosting, MMR diversity.
"""

import logging
import time
from typing import Any
from urllib.parse import urlparse

from qdrant_client import AsyncQdrantClient, models

from src.config.qdrant_policy import resolve_collection_name
from src.observability import get_client, observe
from src.runtime.services.metrics import record_pipeline_event


logger = logging.getLogger(__name__)

SearchResults = list[dict[Any, Any]]
SearchReturn = SearchResults | tuple[SearchResults, dict[str, Any]]


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
        prefer_grpc: bool = True,
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
            prefer_grpc: Whether the SDK should prefer gRPC transport
        """
        # Strip api_key for http:// to avoid "insecure connection" warning (#570)
        scheme = urlparse(url).scheme.lower()
        effective_api_key = api_key if scheme == "https" else None
        self._client = AsyncQdrantClient(
            url=url, api_key=effective_api_key, prefer_grpc=prefer_grpc, timeout=timeout
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

    @observe(
        name="qdrant-hybrid-search-rrf",
        as_type="retriever",
        capture_input=False,
        capture_output=False,
    )
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
            },
            metadata={
                "collection": self._collection_name,
                "quantization_mode": self._quantization_mode,
            },
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
            t_start = time.monotonic()
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
                t_elapsed_ms = (time.monotonic() - t_start) * 1000
                lf.update_current_span(
                    output={
                        "results_count": len(results),
                        "top_score": results[0]["score"] if results else None,
                        "grouped": True,
                        "rrf_k": rrf_k,
                        "prefetch_multiplier": prefetch_multiplier,
                        "processing_time_ms": round(t_elapsed_ms, 3),
                    },
                    metadata={
                        "collection": self._collection_name,
                        "quantization_mode": self._quantization_mode,
                    },
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
            t_elapsed_ms = (time.monotonic() - t_start) * 1000
            lf.update_current_span(
                output={
                    "results_count": len(results),
                    "top_score": results[0]["score"] if results else None,
                    "grouped": False,
                    "rrf_k": rrf_k,
                    "prefetch_multiplier": prefetch_multiplier,
                    "processing_time_ms": round(t_elapsed_ms, 3),
                },
                metadata={
                    "collection": self._collection_name,
                    "quantization_mode": self._quantization_mode,
                },
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
                metadata={
                    "collection": self._collection_name,
                    "quantization_mode": self._quantization_mode,
                },
            )
            if return_meta:
                return [], {
                    "backend_error": True,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                }
            return []

    async def _colbert_fallback_to_rrf(
        self,
        *,
        dense_vector: list[float],
        sparse_vector: dict | None,
        filters: dict | None,
        top_k: int,
        dense_weight: float,
        sparse_weight: float,
        rrf_k: int,
        return_meta: bool,
        fallback_reason: str,
    ) -> tuple[SearchReturn, SearchResults]:
        """Run RRF as a fallback for ColBERT search and emit the standard span output.

        Extracted from ``hybrid_search_rrf_colbert`` (#1542) where the same
        ~17-line block was inlined four times — once for each fallback
        cause: ``colbert_unavailable``, ``empty_colbert_query``,
        ``colbert_empty`` (post-query empty result), and
        ``colbert_error:<ExcType>``.

        Args:
            dense_vector / sparse_vector / filters / top_k / dense_weight /
            sparse_weight / rrf_k / return_meta: forwarded verbatim to
                :meth:`hybrid_search_rrf`.
            fallback_reason: human-readable cause used as the
                ``fallback_reason`` field in the Langfuse span output.
                Caller-controlled so the four sites stay observably
                distinct in traces.

        Returns:
            ``(fallback, fallback_results)`` — ``fallback`` preserves the
            shape :meth:`hybrid_search_rrf` returned (list or
            ``(list, meta)`` tuple, mirroring ``return_meta``);
            ``fallback_results`` is the flat list, already unwrapped, so
            the caller can run post-fallback hooks (e.g., disabling
            ColBERT for the collection on a non-empty fallback) without
            re-doing the ``isinstance`` dance.
        """
        fallback: SearchReturn = await self.hybrid_search_rrf(
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
            filters=filters,
            top_k=top_k,
            dense_weight=dense_weight,
            sparse_weight=sparse_weight,
            rrf_k=rrf_k,
            return_meta=return_meta,
        )
        fallback_results = fallback[0] if isinstance(fallback, tuple) else fallback
        get_client().update_current_span(
            output={
                "fallback_reason": fallback_reason,
                "results_count": len(fallback_results),
                "top_score": fallback_results[0]["score"] if fallback_results else None,
            },
            metadata={
                "collection": self._collection_name,
                "quantization_mode": self._quantization_mode,
            },
        )
        return fallback, fallback_results

    @observe(
        name="qdrant-hybrid-search-rrf-colbert",
        as_type="retriever",
        capture_input=False,
        capture_output=False,
    )
    async def hybrid_search_rrf_colbert(
        self,
        dense_vector: list[float],
        colbert_query: list[list[float]],
        sparse_vector: dict | None = None,
        filters: dict | None = None,
        top_k: int = 5,
        dense_limit: int | None = None,
        sparse_limit: int | None = None,
        dense_weight: float = 0.6,
        sparse_weight: float = 0.4,
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
            dense_weight: Dense prefetch weight when dense_limit is not explicitly set
            sparse_weight: Sparse prefetch weight when sparse_limit is not explicitly set
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
            },
            metadata={
                "collection": self._collection_name,
                "quantization_mode": self._quantization_mode,
            },
        )
        if self._colbert_available is False:
            logger.debug(
                "Qdrant ColBERT skipped: vector unavailable in collection %s; using RRF",
                self._collection_name,
            )
            fallback, _ = await self._colbert_fallback_to_rrf(
                dense_vector=dense_vector,
                sparse_vector=sparse_vector,
                filters=filters,
                top_k=top_k,
                dense_weight=dense_weight,
                sparse_weight=sparse_weight,
                rrf_k=rrf_k,
                return_meta=return_meta,
                fallback_reason="colbert_unavailable",
            )
            return fallback

        if not colbert_query:
            logger.warning(
                "Qdrant ColBERT search skipped: empty query vectors, falling back to RRF"
            )
            fallback, _ = await self._colbert_fallback_to_rrf(
                dense_vector=dense_vector,
                sparse_vector=sparse_vector,
                filters=filters,
                top_k=top_k,
                dense_weight=dense_weight,
                sparse_weight=sparse_weight,
                rrf_k=rrf_k,
                return_meta=return_meta,
                fallback_reason="empty_colbert_query",
            )
            return fallback

        effective_dense_limit = (
            dense_limit if dense_limit is not None else max(int(100 * dense_weight / 0.6), top_k)
        )
        effective_sparse_limit = (
            sparse_limit if sparse_limit is not None else max(int(100 * sparse_weight / 0.4), top_k)
        )

        # Inner prefetch: dense + sparse candidates
        inner_prefetch = [
            models.Prefetch(
                query=dense_vector,
                using=self._dense_vector_name,
                limit=effective_dense_limit,
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
                    limit=effective_sparse_limit,
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
            t_start = time.monotonic()
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
                record_pipeline_event("colbert_rerank_empty")
                logger.warning(
                    "Qdrant ColBERT returned 0 docs for collection %s, falling back to RRF",
                    self._collection_name,
                )
                record_pipeline_event("colbert_fallback_to_rrf")
                fallback, fallback_results = await self._colbert_fallback_to_rrf(
                    dense_vector=dense_vector,
                    sparse_vector=sparse_vector,
                    filters=filters,
                    top_k=top_k,
                    dense_weight=dense_weight,
                    sparse_weight=sparse_weight,
                    rrf_k=rrf_k,
                    return_meta=return_meta,
                    fallback_reason="colbert_empty",
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
                    "dense_limit": effective_dense_limit,
                    "sparse_limit": effective_sparse_limit,
                    "rrf_limit": rrf_limit,
                    "rrf_k": rrf_k,
                    "processing_time_ms": round((time.monotonic() - t_start) * 1000, 3),
                },
                metadata={
                    "collection": self._collection_name,
                    "quantization_mode": self._quantization_mode,
                },
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
                metadata={
                    "collection": self._collection_name,
                    "quantization_mode": self._quantization_mode,
                },
            )
            fallback, _ = await self._colbert_fallback_to_rrf(
                dense_vector=dense_vector,
                sparse_vector=sparse_vector,
                filters=filters,
                top_k=top_k,
                dense_weight=dense_weight,
                sparse_weight=sparse_weight,
                rrf_k=rrf_k,
                return_meta=return_meta,
                fallback_reason=f"colbert_error:{type(e).__name__}",
            )
            return fallback

    @observe(
        name="qdrant-batch-search-rrf",
        as_type="retriever",
        capture_input=False,
        capture_output=False,
    )
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
            },
            metadata={
                "collection": self._collection_name,
                "quantization_mode": self._quantization_mode,
            },
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
            t_start = time.monotonic()
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
            t_elapsed_ms = (time.monotonic() - t_start) * 1000
            lf.update_current_span(
                output={
                    "results_count": len(result),
                    "unique_points": len(seen),
                    "top_score": result[0]["score"] if result else None,
                    "processing_time_ms": round(t_elapsed_ms, 3),
                },
                metadata={
                    "collection": self._collection_name,
                    "quantization_mode": self._quantization_mode,
                },
            )
            return result

        except Exception as e:
            logger.error(f"Qdrant batch search failed (graceful degradation): {e}")
            lf.update_current_span(
                level="ERROR",
                status_message=f"Batch search failed: {type(e).__name__}",
                output={"results_count": 0, "error": type(e).__name__},
                metadata={
                    "collection": self._collection_name,
                    "quantization_mode": self._quantization_mode,
                },
            )
            return []

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
