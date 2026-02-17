"""Small-to-big context expansion service.

Expands retrieved chunks by fetching neighboring chunks from the same document.
This improves answer quality by providing more context around relevant passages.

Usage:
    service = SmallToBigService(qdrant_client, collection_name)
    expanded = await service.expand_context(
        chunks=search_results,
        window_before=1,
        window_after=1,
    )
"""

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from qdrant_client import AsyncQdrantClient, models


logger = logging.getLogger(__name__)


class SmallToBigMode(StrEnum):
    """Small-to-big expansion mode."""

    OFF = "off"  # No expansion
    ON = "on"  # Always expand
    AUTO = "auto"  # Expand only for complex queries


@dataclass
class ExpandedChunk:
    """A chunk with its expanded context."""

    original_chunk: dict[str, Any]
    expanded_text: str
    neighbor_chunks: list[dict[str, Any]]
    total_tokens_estimate: int  # Rough estimate: chars / 4


class SmallToBigService:
    """Service for expanding search results with neighboring chunks.

    Small-to-big retrieval pattern:
    1. Search returns small, focused chunks (high precision)
    2. Expand each chunk with neighbors from same document (more context)
    3. Use expanded context for LLM generation (better answers)

    Benefits:
    - Small chunks = better embedding precision
    - Expanded context = LLM has more info for generation
    - Maintains document coherence
    """

    def __init__(
        self,
        client: AsyncQdrantClient,
        collection_name: str,
        max_expanded_chunks: int = 10,
        max_context_tokens: int = 8000,
    ):
        """Initialize small-to-big service.

        Args:
            client: Async Qdrant client
            collection_name: Target collection name
            max_expanded_chunks: Maximum chunks after expansion
            max_context_tokens: Maximum estimated tokens in expanded context
        """
        self._client = client
        self._collection_name = collection_name
        self._max_expanded_chunks = max_expanded_chunks
        self._max_context_tokens = max_context_tokens

    async def expand_context(
        self,
        chunks: list[dict[str, Any]],
        window_before: int = 1,
        window_after: int = 1,
        deduplicate: bool = True,
    ) -> list[ExpandedChunk]:
        """Expand chunks by fetching neighbors from same document.

        Args:
            chunks: Search results (list of dicts with text, metadata)
            window_before: Number of chunks to fetch before each result
            window_after: Number of chunks to fetch after each result
            deduplicate: Remove duplicate chunks across expansions

        Returns:
            List of ExpandedChunk with original and neighbor chunks
        """
        if not chunks:
            return []

        expanded_results: list[ExpandedChunk] = []
        seen_chunk_ids = set()
        total_tokens = 0

        for chunk in chunks:
            if total_tokens >= self._max_context_tokens:
                logger.info(f"Stopping expansion: reached {total_tokens} tokens limit")
                break

            if len(expanded_results) >= self._max_expanded_chunks:
                logger.info(f"Stopping expansion: reached {len(expanded_results)} chunks limit")
                break

            # Get document info
            metadata = chunk.get("metadata", {})
            doc_id = metadata.get("doc_id") or metadata.get("document_name")
            chunk_order = metadata.get("chunk_order") or metadata.get("order")

            if doc_id is None or chunk_order is None:
                # Can't expand without document/order info
                logger.warning(f"Chunk missing doc_id or order: {metadata}")
                expanded_results.append(
                    ExpandedChunk(
                        original_chunk=chunk,
                        expanded_text=chunk.get("text", ""),
                        neighbor_chunks=[],
                        total_tokens_estimate=len(chunk.get("text", "")) // 4,
                    )
                )
                continue

            # Fetch neighbor chunks
            neighbors = await self._fetch_neighbors(
                doc_id=doc_id,
                center_order=chunk_order,
                window_before=window_before,
                window_after=window_after,
            )

            # Deduplicate if enabled
            if deduplicate:
                unique_neighbors = []
                for n in neighbors:
                    n_id = n.get("id", "")
                    if n_id not in seen_chunk_ids:
                        seen_chunk_ids.add(n_id)
                        unique_neighbors.append(n)
                neighbors = unique_neighbors

            # Build expanded text (sorted by order)
            all_chunks = [chunk, *neighbors]
            all_chunks.sort(
                key=lambda c: (
                    c.get("metadata", {}).get("order", 0)
                    or c.get("metadata", {}).get("chunk_order", 0)
                )
            )

            expanded_text = "\n\n".join(c.get("text", "") for c in all_chunks)
            tokens_estimate = len(expanded_text) // 4

            # Check token limit
            if total_tokens + tokens_estimate > self._max_context_tokens:
                # Try without neighbors
                expanded_text = chunk.get("text", "")
                tokens_estimate = len(expanded_text) // 4
                neighbors = []

            total_tokens += tokens_estimate

            expanded_results.append(
                ExpandedChunk(
                    original_chunk=chunk,
                    expanded_text=expanded_text,
                    neighbor_chunks=neighbors,
                    total_tokens_estimate=tokens_estimate,
                )
            )

        logger.info(
            f"Expanded {len(chunks)} chunks to {len(expanded_results)} with ~{total_tokens} tokens"
        )
        return expanded_results

    async def _fetch_neighbors(
        self,
        doc_id: str,
        center_order: int,
        window_before: int,
        window_after: int,
    ) -> list[dict[str, Any]]:
        """Fetch neighboring chunks from the same document.

        Args:
            doc_id: Document identifier (document_name)
            center_order: Order of the center chunk
            window_before: Number of chunks before
            window_after: Number of chunks after

        Returns:
            List of neighbor chunks (excluding center)
        """
        # Calculate order range
        order_min = max(0, center_order - window_before)
        order_max = center_order + window_after

        try:
            # Build filter for same document and order range
            filter_conditions = models.Filter(
                must=[
                    # Same document
                    models.FieldCondition(
                        key="metadata.doc_id",
                        match=models.MatchValue(value=doc_id),
                    ),
                    # Order in range (excluding center)
                    models.FieldCondition(
                        key="metadata.order",
                        range=models.Range(gte=order_min, lte=order_max),
                    ),
                ],
                must_not=[
                    # Exclude center chunk
                    models.FieldCondition(
                        key="metadata.order",
                        match=models.MatchValue(value=center_order),
                    ),
                ],
            )

            # Scroll to get all matching chunks
            # We use scroll instead of search since we're filtering, not searching
            result = await self._client.scroll(
                collection_name=self._collection_name,
                scroll_filter=filter_conditions,
                limit=window_before + window_after + 1,  # Extra buffer
                with_payload=True,
            )

            points = result[0]  # (points, next_page_offset)

            # Format results
            return [
                {
                    "id": str(p.id),
                    "text": (p.payload or {}).get("page_content", ""),
                    "metadata": (p.payload or {}).get("metadata", {}),
                    "score": 0.0,  # Neighbors don't have search scores
                }
                for p in points
            ]

        except Exception as e:
            logger.error(f"Failed to fetch neighbors for {doc_id}:{center_order}: {e}")
            return []

    def format_expanded_context(
        self,
        expanded_chunks: list[ExpandedChunk],
        include_metadata: bool = True,
    ) -> str:
        """Format expanded chunks for LLM context.

        Args:
            expanded_chunks: List of expanded chunks
            include_metadata: Include metadata in output

        Returns:
            Formatted context string
        """
        context_parts = []

        for i, ec in enumerate(expanded_chunks, 1):
            original = ec.original_chunk
            metadata = original.get("metadata", {})

            header = f"[Document {i}]"
            if include_metadata:
                if title := metadata.get("title"):
                    header += f" {title}"
                if score := original.get("score"):
                    header += f" (score: {score:.2f})"

            context_parts.append(f"{header}\n{ec.expanded_text}")

        return "\n\n---\n\n".join(context_parts)
