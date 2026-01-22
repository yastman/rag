"""Voyage AI document indexer for Qdrant.

Replaces BGE-M3 with Voyage AI for dense embeddings.
Keeps FastEmbed BM42 for sparse vectors (hybrid search).
"""

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    HnswConfigDiff,
    Modifier,
    OptimizersConfigDiff,
    PointStruct,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
    SparseVectorParams,
    VectorParams,
)

from telegram_bot.services import VoyageService

from .chunker import Chunk


logger = logging.getLogger(__name__)


@dataclass
class IndexStats:
    """Indexing statistics."""

    total_chunks: int = 0
    indexed_chunks: int = 0
    failed_chunks: int = 0
    duration_seconds: float = 0.0


class VoyageIndexer:
    """Index documents using Voyage AI embeddings + FastEmbed BM42 sparse.

    Features:
    - Voyage AI voyage-4-large (1024-dim dense, MoE architecture)
    - FastEmbed BM42 sparse vectors
    - NO ColBERT (use Voyage rerank-2.5 instead)
    - Scalar Int8 quantization (4x compression)
    - Batch indexing with API rate limit handling
    """

    ***REMOVED*** API batch size limit
    VOYAGE_BATCH_SIZE = 128

    def __init__(
        self,
        qdrant_url: Optional[str] = None,
        qdrant_api_key: Optional[str] = None,
        voyage_api_key: Optional[str] = None,
        voyage_model: str = "voyage-4-large",
    ):
        """Initialize indexer.

        Args:
            qdrant_url: Qdrant URL (default from QDRANT_URL env)
            qdrant_api_key: Qdrant API key (default from QDRANT_API_KEY env)
            voyage_api_key: Voyage API key (default from VOYAGE_API_KEY env)
            voyage_model: Voyage embedding model name (default voyage-4-large)
        """
        self.qdrant_url = qdrant_url or os.getenv("QDRANT_URL", "http://localhost:6333")
        self.qdrant_api_key = qdrant_api_key or os.getenv("QDRANT_API_KEY", "")
        self.voyage_api_key = voyage_api_key or os.getenv("VOYAGE_API_KEY", "")

        ***REMOVED*** client with longer timeout for batch operations
        if self.qdrant_api_key:
            self.client = QdrantClient(
                url=self.qdrant_url, api_key=self.qdrant_api_key, timeout=120
            )
        else:
            self.client = QdrantClient(url=self.qdrant_url, timeout=120)

        ***REMOVED*** AI unified service for dense embeddings
        self.voyage_service = VoyageService(
            api_key=self.voyage_api_key,
            model_docs=voyage_model,
        )

        # FastEmbed BM42 for sparse embeddings
        self.sparse_model = SparseTextEmbedding(
            model_name="Qdrant/bm42-all-minilm-l6-v2-attentions"
        )

        self.stats = IndexStats()
        logger.info(f"VoyageIndexer initialized: {voyage_model} + BM42")

    def create_collection(self, collection_name: str, recreate: bool = False) -> bool:
        """Create Qdrant collection for Voyage embeddings.

        Args:
            collection_name: Name of collection to create
            recreate: Whether to drop and recreate if exists

        Returns:
            True if collection created/exists
        """
        try:
            self.client.get_collection(collection_name)
            if recreate:
                self.client.delete_collection(collection_name)
                logger.info(f"Deleted existing collection: {collection_name}")
            else:
                logger.info(f"Collection already exists: {collection_name}")
                return True
        except Exception:
            pass  # Collection doesn't exist

        # Create collection with Voyage-optimized config
        # No ColBERT - use Voyage rerank-2.5 instead
        self.client.create_collection(
            collection_name=collection_name,
            vectors_config={
                "dense": VectorParams(
                    size=1024,  ***REMOVED*** voyage-4-large dimension
                    distance=Distance.COSINE,
                    hnsw_config=HnswConfigDiff(
                        m=16,
                        ef_construct=200,
                        on_disk=False,
                    ),
                    quantization_config=ScalarQuantization(
                        scalar=ScalarQuantizationConfig(
                            type=ScalarType.INT8,
                            quantile=0.99,
                            always_ram=True,
                        )
                    ),
                    on_disk=True,
                ),
            },
            sparse_vectors_config={
                "bm42": SparseVectorParams(modifier=Modifier.IDF),
            },
            optimizers_config=OptimizersConfigDiff(
                indexing_threshold=20000,
                memmap_threshold=50000,
            ),
        )

        # Create payload indexes
        self._create_payload_indexes(collection_name)

        logger.info(f"Created collection: {collection_name}")
        return True

    def _create_payload_indexes(self, collection_name: str) -> None:
        """Create indexes on payload fields for fast filtering."""
        try:
            # Text fields
            for field in ["source_type", "city", "document_name", "topic"]:
                self.client.create_payload_index(
                    collection_name=collection_name,
                    field_name=f"metadata.{field}",
                    field_schema="keyword",
                )

            # Numeric fields
            for field in ["price", "rooms", "area", "floor", "distance_to_sea", "chunk_id"]:
                self.client.create_payload_index(
                    collection_name=collection_name,
                    field_name=f"metadata.{field}",
                    field_schema="integer",
                )

            logger.info(f"Created payload indexes for {collection_name}")
        except Exception as e:
            logger.warning(f"Could not create payload indexes: {e}")

    async def index_chunks(
        self,
        chunks: list[Chunk],
        collection_name: str,
        batch_size: int = 8,
        rate_limit_delay: float = 25.0,
    ) -> IndexStats:
        """Index chunks to Qdrant with Voyage embeddings.

        Args:
            chunks: List of chunks to index
            collection_name: Target collection name
            batch_size: Batch size for indexing (default 8 for rate limits)
            rate_limit_delay: Delay between batches in seconds (default 25s for 3 RPM)

        Returns:
            Indexing statistics
        """
        start_time = time.time()
        self.stats = IndexStats(total_chunks=len(chunks))

        # Create collection if needed
        self.create_collection(collection_name)

        # Process in batches with rate limiting
        total_batches = (len(chunks) + batch_size - 1) // batch_size
        for i, batch_idx in enumerate(range(0, len(chunks), batch_size)):
            batch = chunks[batch_idx : batch_idx + batch_size]
            await self._index_batch(batch, collection_name)
            logger.info(
                f"Progress: {min(batch_idx + batch_size, len(chunks))}/{len(chunks)} (batch {i + 1}/{total_batches})"
            )

            # Rate limit delay (skip for last batch)
            if batch_idx + batch_size < len(chunks):
                logger.info(f"Rate limit delay: {rate_limit_delay}s...")
                await asyncio.sleep(rate_limit_delay)

        self.stats.duration_seconds = time.time() - start_time
        logger.info(
            f"Indexing complete: {self.stats.indexed_chunks}/{self.stats.total_chunks} "
            f"in {self.stats.duration_seconds:.2f}s"
        )
        return self.stats

    async def _index_batch(self, chunks: list[Chunk], collection_name: str) -> None:
        """Index a batch of chunks with Voyage dense + BM42 sparse."""
        try:
            # Get texts for embedding
            texts = [chunk.text for chunk in chunks]

            # Generate Voyage dense embeddings
            dense_embeddings = await self.voyage_service.embed_documents(texts)

            # Generate BM42 sparse embeddings
            sparse_embeddings = list(self.sparse_model.embed(texts))

            # Prepare points
            points = []
            for chunk, dense_vec, sparse_emb in zip(chunks, dense_embeddings, sparse_embeddings):
                # Convert sparse to Qdrant format
                sparse_indices = sparse_emb.indices.tolist()
                sparse_values = sparse_emb.values.tolist()

                # Build metadata
                metadata = {
                    "document_name": chunk.document_name,
                    "article_number": chunk.article_number,
                    "chapter": chunk.chapter,
                    "section": chunk.section,
                    "chunk_id": chunk.chunk_id,
                    "order": chunk.order,
                }
                if chunk.extra_metadata:
                    metadata.update(chunk.extra_metadata)

                point = PointStruct(
                    id=str(uuid.uuid4()),
                    vector={
                        "dense": dense_vec,
                        "bm42": {
                            "indices": sparse_indices,
                            "values": sparse_values,
                        },
                    },
                    payload={
                        "page_content": chunk.text,
                        "metadata": metadata,
                    },
                )
                points.append(point)

            # Upsert to Qdrant
            self.client.upsert(collection_name=collection_name, points=points)
            self.stats.indexed_chunks += len(points)
            logger.info(f"Indexed batch: {len(points)} chunks")

        except Exception as e:
            self.stats.failed_chunks += len(chunks)
            logger.error(f"Batch indexing failed: {e}", exc_info=True)

    def get_collection_stats(self, collection_name: str) -> dict[str, Any]:
        """Get collection statistics."""
        try:
            info = self.client.get_collection(collection_name)
            return {
                "name": collection_name,
                "points_count": info.points_count,
                "vectors_count": info.vectors_count,
                "indexed_vectors_count": info.indexed_vectors_count,
            }
        except Exception as e:
            logger.error(f"Error getting collection stats: {e}")
            return {}


async def reindex_from_existing(
    source_collection: str = "contextual_bulgaria_voyage",
    target_collection: str = "contextual_bulgaria_voyage4",
    batch_size: int = 8,
    rate_limit_delay: float = 25.0,
) -> IndexStats:
    """Reindex existing Qdrant data with Voyage-4 embeddings.

    Reads from source collection and indexes to target with Voyage-4-large embeddings.

    Args:
        source_collection: Source collection name (voyage-3 indexed)
        target_collection: Target collection name (voyage-4 indexed)
        batch_size: Batch size for processing
        rate_limit_delay: Delay between batches for rate limiting

    Returns:
        Indexing statistics
    """
    logger.info(f"Reindexing: {source_collection} -> {target_collection} (voyage-4-large)")

    # Initialize indexer with voyage-4-large
    indexer = VoyageIndexer(voyage_model="voyage-4-large")

    # Create target collection
    indexer.create_collection(target_collection, recreate=True)

    # Read all points from source
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_api_key = os.getenv("QDRANT_API_KEY", "")

    if qdrant_api_key:
        client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
    else:
        client = QdrantClient(url=qdrant_url)

    # Scroll through all points
    all_chunks = []
    offset = None

    while True:
        results = client.scroll(
            collection_name=source_collection,
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )

        points, next_offset = results

        if not points:
            break

        for point in points:
            payload = point.payload
            metadata = payload.get("metadata", {})

            # Create chunk from existing data
            # Use text_for_embedding if available, otherwise page_content
            text = payload.get("text_for_embedding") or payload.get("page_content", "")

            chunk = Chunk(
                text=text,
                chunk_id=metadata.get("chunk_id", 0),
                document_name=metadata.get("source", metadata.get("document_name", "")),
                article_number=metadata.get("article_number", ""),
                chapter=metadata.get("chapter", ""),
                section=metadata.get("section", ""),
                extra_metadata={
                    k: v
                    for k, v in metadata.items()
                    if k
                    not in ["chunk_id", "document_name", "article_number", "chapter", "section"]
                },
            )
            all_chunks.append(chunk)

        offset = next_offset
        if offset is None:
            break

    logger.info(f"Loaded {len(all_chunks)} chunks from {source_collection}")

    # Reindex with Voyage (with rate limiting)
    return await indexer.index_chunks(all_chunks, target_collection, batch_size, rate_limit_delay)


if __name__ == "__main__":
    # Run reindexing
    logging.basicConfig(level=logging.INFO)
    stats = asyncio.run(reindex_from_existing())
    print("\nReindexing complete!")
    print(f"  Total: {stats.total_chunks}")
    print(f"  Indexed: {stats.indexed_chunks}")
    print(f"  Failed: {stats.failed_chunks}")
    print(f"  Duration: {stats.duration_seconds:.2f}s")
