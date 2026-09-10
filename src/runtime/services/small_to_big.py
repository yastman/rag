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

# Identity namespaces keep Qdrant point ids distinct from canonical
# (doc_id, order) pairs inside the deduplication set.
_PointIdentity = tuple[str, str]
_DocIdentity = tuple[str, str, Any]


def _chunk_doc_id(chunk: dict[str, Any]) -> Any:
    """Return the document identifier from chunk metadata, if any."""
    metadata = chunk.get("metadata") or {}
    return metadata.get("doc_id") or metadata.get("document_name")


def _chunk_order(chunk: dict[str, Any]) -> Any:
    """Return the chunk order from metadata, tolerating either key and order 0."""
    metadata = chunk.get("metadata") or {}
    order = metadata.get("order")
    if order is None:
        order = metadata.get("chunk_order")
    return order


def _chunk_sort_key(chunk: dict[str, Any]) -> Any:
    """Sort key ordering chunks by document position, defaults last."""
    order = _chunk_order(chunk)
    if order is None:
        order = 0
    return order


def _chunk_identities(chunk: dict[str, Any]) -> set[_PointIdentity | _DocIdentity]:
    """Return identity keys for a retrieved hit or a fetched neighbor point.

    Uses the Qdrant point id when present plus the canonical ``(doc_id, order)``
    pair from metadata, so an original hit and a fetched neighbor pointing at
    the same stored chunk compare equal (#3441).
    """
    identities: set[_PointIdentity | _DocIdentity] = set()
    point_id = chunk.get("id") or chunk.get("point_id")
    if point_id:
        identities.add(("point", str(point_id)))
    doc_id = _chunk_doc_id(chunk)
    order = _chunk_order(chunk)
    if doc_id and order is not None:
        identities.add(("doc", str(doc_id), order))
    return identities


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
            max_expanded_chunks: Expansion budget: maximum added neighbor
                chunks across one expand_context call
            max_context_tokens: Expansion budget: maximum estimated tokens of
                added neighbor text across one expand_context call
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

        Returns exactly one ``ExpandedChunk`` per input chunk, in input order:
        original hits are never dropped (#3441). The constructor limits form
        the expansion budget and apply only to added neighbor chunks —
        ``max_expanded_chunks`` caps the number of added neighbors and
        ``max_context_tokens`` caps the estimated tokens of added neighbor
        text across the whole call. An expansion budget cap at the generation
        boundary, if required, is a separate concern.

        When ``deduplicate`` is enabled, the seen-identity set is seeded with
        every original hit (point id or canonical ``(doc_id, order)``) so a
        retrieved hit is never re-added as another hit's neighbor.

        Args:
            chunks: Search results (list of dicts with text, metadata)
            window_before: Number of chunks to fetch before each result
            window_after: Number of chunks to fetch after each result
            deduplicate: Remove duplicate chunks across expansions

        Returns:
            One ExpandedChunk per input chunk; neighbors admitted within the
            expansion budget.
        """
        if not chunks:
            return []

        expanded_results: list[ExpandedChunk] = []
        # Expansion budget counters track added neighbor chunks only.
        added_neighbor_count = 0
        added_neighbor_tokens = 0
        seen_identities: set[_PointIdentity | _DocIdentity] = set()
        if deduplicate:
            for chunk in chunks:
                seen_identities.update(_chunk_identities(chunk))

        for chunk in chunks:
            doc_id = _chunk_doc_id(chunk)
            chunk_order = _chunk_order(chunk)

            neighbors: list[dict[str, Any]] = []
            if doc_id is None or chunk_order is None:
                # Can't expand without document/order info
                logger.warning(f"Chunk missing doc_id or order: {chunk.get('metadata', {})}")
            else:
                fetched = await self._fetch_neighbors(
                    doc_id=doc_id,
                    center_order=chunk_order,
                    window_before=window_before,
                    window_after=window_after,
                )
                fetched.sort(key=_chunk_sort_key)
                for neighbor in fetched:
                    if deduplicate and _chunk_identities(neighbor) & seen_identities:
                        continue
                    if added_neighbor_count >= self._max_expanded_chunks:
                        break  # count budget exhausted
                    neighbor_tokens = len(neighbor.get("text", "")) // 4
                    if added_neighbor_tokens + neighbor_tokens > self._max_context_tokens:
                        continue  # does not fit; a smaller later neighbor may
                    if deduplicate:
                        seen_identities.update(_chunk_identities(neighbor))
                    added_neighbor_count += 1
                    added_neighbor_tokens += neighbor_tokens
                    neighbors.append(neighbor)

            # Build expanded text (sorted by order)
            all_chunks = sorted([chunk, *neighbors], key=_chunk_sort_key)
            expanded_text = "\n\n".join(c.get("text", "") for c in all_chunks)
            tokens_estimate = len(expanded_text) // 4

            expanded_results.append(
                ExpandedChunk(
                    original_chunk=chunk,
                    expanded_text=expanded_text,
                    neighbor_chunks=neighbors,
                    total_tokens_estimate=tokens_estimate,
                )
            )

        logger.info(
            "Expanded %d chunks with %d added neighbors (~%d/%d expansion budget tokens)",
            len(chunks),
            added_neighbor_count,
            added_neighbor_tokens,
            self._max_context_tokens,
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
            logger.error(
                "Failed to fetch neighbors for %s:%s (%s): %s",
                doc_id,
                center_order,
                type(e).__name__,
                e,
            )
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
