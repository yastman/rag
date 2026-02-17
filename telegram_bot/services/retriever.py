"""Qdrant retrieval service."""

import logging
from typing import TYPE_CHECKING, Any

from qdrant_client import QdrantClient


if TYPE_CHECKING:
    from qdrant_client.http.models.models import Filter as QdrantFilter


logger = logging.getLogger(__name__)


class RetrieverService:
    """Retrieve relevant documents from Qdrant."""

    def __init__(
        self,
        url: str,
        api_key: str,
        collection_name: str,
    ):
        """Initialize retriever.

        Args:
            url: Qdrant URL
            api_key: Qdrant API key (optional)
            collection_name: Collection to search
        """
        self.url = url
        self.api_key = api_key
        self.collection_name = collection_name
        self.client: QdrantClient | None = None
        self._is_healthy = False

        # Initialize client with error handling
        try:
            if api_key:
                self.client = QdrantClient(url=url, api_key=api_key, timeout=5)
            else:
                self.client = QdrantClient(url=url, timeout=5)

            # Test connection
            self.client.get_collections()
            self._is_healthy = True
            logger.info(f"✓ Qdrant connection established: {collection_name}")
        except Exception as e:
            logger.error(f"Qdrant initialization failed: {e}")
            self.client = None
            self._is_healthy = False

    def search(
        self,
        query_vector: list[float],
        filters: dict[str, Any] | None = None,
        top_k: int = 5,
        min_score: float = 0.5,
    ) -> list[dict[str, Any]]:
        """
        Search for relevant documents with graceful degradation.

        Args:
            query_vector: Query embedding vector
            filters: Extracted filters dict (e.g., {"price": {"lt": 100000}, "city": "Несебр"})
            top_k: Number of results to return
            min_score: Minimum similarity score

        Returns:
            List of results with text and metadata. Returns empty list on error.
        """
        # Check if client is available
        if not self.client or not self._is_healthy:
            logger.error("Qdrant client unavailable, returning empty results")
            return []

        try:
            # Build filter: base (CSV rows) + dynamic filters
            query_filter = self._build_filter(filters) if filters else self._build_base_filter()

            # Search using dense vector
            results = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                using="dense",
                query_filter=query_filter,
                limit=top_k,
                score_threshold=min_score,
                with_payload=True,
            )

            # Format results
            formatted_results = []
            for point in results.points:
                formatted_results.append(
                    {
                        "text": (point.payload or {}).get("page_content", ""),
                        "metadata": (point.payload or {}).get("metadata", {}),
                        "score": point.score,
                    }
                )

            logger.info(f"Qdrant search successful: {len(formatted_results)} results")
            return formatted_results

        except Exception as e:
            logger.error(f"Qdrant search failed: {e}", exc_info=True)
            self._is_healthy = False
            return []

    def _build_base_filter(self) -> "QdrantFilter | None":
        """
        Build base Qdrant Filter.

        Returns None to search all documents without restriction.
        Override this method to add collection-specific filters.

        Returns:
            None (no filter) or Qdrant Filter object
        """
        # No base filter - search all documents in collection
        return None

    def _build_filter(self, filters: dict[str, Any]) -> "QdrantFilter | None":
        """
        Build Qdrant Filter from extracted filters dict.

        Args:
            filters: Dict with extracted filters from QueryAnalyzer
                     Example: {"price": {"lt": 100000}, "city": "Несебр", "rooms": 2}

        Returns:
            Qdrant Filter object with dynamic filters, or None if no filters
        """
        if not filters:
            return None

        # Import lazily so returned models stay consistent with current qdrant_client module state.
        from qdrant_client import models

        conditions = []

        for field, value in filters.items():
            # Exact match for strings and integers
            if isinstance(value, (str, int)):
                conditions.append(
                    models.FieldCondition(
                        key=f"metadata.{field}",
                        match=models.MatchValue(value=value),
                    )
                )
            # Range filter for numeric comparisons
            elif isinstance(value, dict):
                range_params = {}
                if "lt" in value:
                    range_params["lt"] = value["lt"]
                if "lte" in value:
                    range_params["lte"] = value["lte"]
                if "gt" in value:
                    range_params["gt"] = value["gt"]
                if "gte" in value:
                    range_params["gte"] = value["gte"]

                if range_params:
                    conditions.append(
                        models.FieldCondition(
                            key=f"metadata.{field}",
                            range=models.Range(**range_params),
                        )
                    )

        # Return None if no conditions were built
        if not conditions:
            return None

        return models.Filter(must=conditions)  # type: ignore[arg-type]
