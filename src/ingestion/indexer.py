"""Document indexing to vector database."""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    HnswConfigDiff,
    Modifier,
    MultiVectorComparator,
    MultiVectorConfig,
    OptimizersConfigDiff,
    PayloadSchemaType,
    PointStruct,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from src.config import Settings, VectorDimensions
from src.models import get_bge_m3_model

from .chunker import Chunk


logger = logging.getLogger(__name__)


@dataclass
class IndexStats:
    """Indexing statistics."""

    total_chunks: int = 0
    indexed_chunks: int = 0
    failed_chunks: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    duration_seconds: float = 0.0


class DocumentIndexer:
    """
    Index documents into Qdrant vector database.

    Features:
    - BGE-M3 embeddings (1024-dim dense + sparse + ColBERT)
    - Scalar Int8 quantization (4x compression)
    - HNSW optimization with delta compression
    - Batch indexing for efficiency
    - Automatic collection creation
    - Metadata preservation
    - Async processing
    """

    def __init__(self, settings: Settings | None = None):
        """
        Initialize indexer.

        Args:
            settings: Configuration settings
        """
        self.settings = settings or Settings()
        # Use longer timeout for large batches (embeddings can take 40-60s)
        self.client = QdrantClient(
            self.settings.qdrant_url,
            api_key=self.settings.qdrant_api_key,
            timeout=120,  # 2 minutes timeout for large batch operations
        )
        self.embedding_model = get_bge_m3_model(use_fp16=True)
        self.stats = IndexStats()

    def create_collection(self, collection_name: str, recreate: bool = False) -> bool:
        """
        Create Qdrant collection for embeddings.

        Args:
            collection_name: Name of collection to create
            recreate: Whether to drop and recreate if exists

        Returns:
            True if collection created/exists, False otherwise
        """
        try:
            # Check if collection exists
            self.client.get_collection(collection_name)
            if recreate:
                self.client.delete_collection(collection_name)
                print(f"Deleted existing collection: {collection_name}")
            else:
                print(f"Collection already exists: {collection_name}")
                return True
        except Exception:
            logger.debug("Collection %s not found, will create", collection_name)

        # Create collection with optimized vector configuration
        # Optimizations based on Qdrant best practices (Nov 2025):
        # - Scalar Int8 quantization: 4x compression, 0.99 accuracy, 2x faster
        # - BM42 sparse vectors: +9% Precision@10 vs BM25 for short chunks
        # - Original vectors on disk: RAM savings with fast rescoring
        # - HNSW optimized: m=16 (balance), ef_construct=200 (quality)
        # - Oversampling enabled: 3x limit for rescoring accuracy
        self.client.create_collection(
            collection_name=collection_name,
            vectors_config={
                # Dense vectors for semantic search (BGE-M3)
                "dense": VectorParams(
                    size=VectorDimensions.DENSE,
                    distance=Distance.COSINE,
                    hnsw_config=HnswConfigDiff(
                        m=16,  # Edges per node: balance memory/quality
                        ef_construct=200,  # Build quality (higher = better graph)
                        on_disk=False,  # HNSW graph in RAM for fast traversal
                    ),
                    quantization_config=ScalarQuantization(
                        scalar=ScalarQuantizationConfig(
                            type=ScalarType.INT8,  # 4x compression, 0.99 accuracy
                            quantile=0.99,  # Exclude top 1% outliers
                            always_ram=True,  # Quantized vectors in RAM (fast search)
                        )
                    ),
                    on_disk=True,  # Original vectors on disk (RAM savings + rescoring)
                ),
                # ColBERT multivector for reranking
                "colbert": VectorParams(
                    size=VectorDimensions.DENSE,
                    distance=Distance.COSINE,
                    multivector_config=MultiVectorConfig(comparator=MultiVectorComparator.MAX_SIM),
                    hnsw_config=HnswConfigDiff(
                        m=0,  # Disable HNSW for ColBERT (only for reranking)
                    ),
                    on_disk=True,  # ColBERT vectors on disk (only used for rerank)
                ),
            },
            # BM42 sparse vectors (better than BM25 for short chunks)
            sparse_vectors_config={
                "bm42": SparseVectorParams(
                    modifier=Modifier.IDF,  # Native IDF computation in Qdrant
                )
            },
            # Optimizer config for better bulk indexing
            optimizers_config=OptimizersConfigDiff(
                indexing_threshold=20000,  # Build HNSW every 20k vectors
                memmap_threshold=50000,  # Use mmap for segments >50k
            ),
        )

        # Create indexes on important payload fields for fast filtering
        self._create_payload_indexes(collection_name)

        print(f"✓ Created collection: {collection_name}")
        return True

    def _create_payload_indexes(self, collection_name: str) -> None:
        """Create indexes on payload fields for fast filtering."""
        try:
            # Basic document metadata indexes
            self.client.create_payload_index(
                collection_name=collection_name,
                field_name="metadata.article_number",
                field_schema=PayloadSchemaType.KEYWORD,
            )

            self.client.create_payload_index(
                collection_name=collection_name,
                field_name="metadata.document_name",
                field_schema=PayloadSchemaType.KEYWORD,
            )

            # CSV structured data indexes (for filtering apartments)
            # Text fields
            self.client.create_payload_index(
                collection_name=collection_name,
                field_name="metadata.city",
                field_schema=PayloadSchemaType.KEYWORD,
            )

            self.client.create_payload_index(
                collection_name=collection_name,
                field_name="metadata.source_type",
                field_schema=PayloadSchemaType.KEYWORD,
            )

            for field in [
                "metadata.topic",
                "metadata.doc_type",
                "metadata.jurisdiction",
                "metadata.audience",
                "metadata.language",
            ]:
                self.client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field,
                    field_schema=PayloadSchemaType.KEYWORD,
                )

            # Small-to-big: index order field for neighbor chunk queries
            self.client.create_payload_index(
                collection_name=collection_name,
                field_name="metadata.order",
                field_schema=PayloadSchemaType.INTEGER,
            )

            # Numeric fields - enable range filtering (price < 100000, rooms >= 2, etc.)
            for field in [
                "price",
                "rooms",
                "area",
                "floor",
                "floors",
                "distance_to_sea",
                "bathrooms",
            ]:
                self.client.create_payload_index(
                    collection_name=collection_name,
                    field_name=f"metadata.{field}",
                    field_schema=PayloadSchemaType.INTEGER,
                )

            # Boolean fields
            for field in ["furnished", "year_round"]:
                self.client.create_payload_index(
                    collection_name=collection_name,
                    field_name=f"metadata.{field}",
                    field_schema=PayloadSchemaType.BOOL,
                )

            print(f"✓ Created payload indexes for {collection_name}")
        except Exception as e:
            print(f"Warning: Could not create payload indexes: {e}")

    async def index_chunks(
        self,
        chunks: list[Chunk],
        collection_name: str,
        batch_size: int | None = None,
    ) -> IndexStats:
        """
        Index chunks to vector database.

        Args:
            chunks: List of chunks to index
            collection_name: Target collection name
            batch_size: Batch size for indexing (uses settings default if None)

        Returns:
            Indexing statistics
        """
        batch_size = batch_size or self.settings.batch_size_documents

        self.stats = IndexStats(total_chunks=len(chunks))

        # Create collection if needed
        self.create_collection(collection_name)

        # Process chunks in batches
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            await self._index_batch(batch, collection_name)

        return self.stats

    async def _index_batch(self, chunks: list[Chunk], collection_name: str) -> None:
        """Index a batch of chunks with BGE-M3 (dense + sparse + colbert)."""
        batch_start = time.time()

        try:
            # Log batch info
            doc_names = {c.document_name for c in chunks}
            logger.info(f"Starting batch: {len(chunks)} chunks from {doc_names}")

            # Generate embeddings for batch
            texts = [chunk.text for chunk in chunks]
            avg_len = sum(len(t) for t in texts) / len(texts)
            logger.info(f"  Texts prepared: {len(texts)} chunks, avg {avg_len:.0f} chars")

            embed_start = time.time()
            embeddings = await self._embed_texts(texts)
            embed_time = time.time() - embed_start
            logger.info(
                f"  Embeddings generated: {embed_time:.2f}s ({len(texts) / embed_time:.1f} chunks/s)"
            )

            # Prepare points for Qdrant with named vectors
            prep_start = time.time()
            points = []
            for chunk, emb in zip(chunks, embeddings, strict=True):
                # Convert sparse dict to lists for Qdrant
                sparse_indices = list(emb["lexical_weights"].keys())
                sparse_values = list(emb["lexical_weights"].values())
                dense_vector = [float(v) for v in emb["dense_vecs"].tolist()]
                colbert_vector = [[float(v) for v in row] for row in emb["colbert_vecs"].tolist()]

                # Build metadata dict
                # doc_id and chunk_order are explicit aliases for small-to-big retrieval
                metadata_dict = {
                    "document_name": chunk.document_name,
                    "doc_id": chunk.document_name,  # Explicit alias for small-to-big
                    "article_number": chunk.article_number,
                    "chapter": chunk.chapter,
                    "section": chunk.section,
                    "chunk_id": chunk.chunk_id,
                    "order": chunk.order,
                    "chunk_order": chunk.order,  # Explicit alias for small-to-big
                }

                # Add extra_metadata for structured data (CSV, etc.)
                if chunk.extra_metadata:
                    metadata_dict.update(chunk.extra_metadata)

                point = PointStruct(
                    id=str(uuid.uuid4()),
                    vector={
                        "dense": dense_vector,
                        "colbert": colbert_vector,
                        "bm42": SparseVector(
                            indices=[int(v) for v in sparse_indices],
                            values=[float(v) for v in sparse_values],
                        ),
                    },
                    payload={
                        "page_content": chunk.text,  # n8n expects this field
                        "metadata": metadata_dict,  # All other fields go into metadata
                    },
                )
                points.append(point)

            prep_time = time.time() - prep_start
            logger.info(f"  Points prepared: {len(points)} points in {prep_time:.2f}s")

            # Upsert points to Qdrant
            upsert_start = time.time()
            self.client.upsert(
                collection_name=collection_name,
                points=points,
            )
            upsert_time = time.time() - upsert_start
            logger.info(f"  Qdrant upsert: {upsert_time:.2f}s")

            self.stats.indexed_chunks += len(points)

            batch_time = time.time() - batch_start
            logger.info(f"✓ Batch complete: {len(points)} chunks in {batch_time:.2f}s")
            print(f"  ✓ Indexed {len(points)} chunks")

        except Exception as e:
            batch_time = time.time() - batch_start
            self.stats.failed_chunks += len(chunks)
            logger.error(f"✗ Batch failed after {batch_time:.2f}s: {type(e).__name__}: {e}")
            print(f"  ✗ Failed to index batch: {e}")

    async def _embed_texts(self, texts: list[str]) -> list[dict]:
        """
        Generate embeddings for texts using BGE-M3.

        Returns list of dicts with:
        - dense_vecs: Dense embeddings (1024-dim)
        - lexical_weights: Sparse embeddings (dict of token_id: weight)
        - colbert_vecs: ColBERT multivector embeddings
        """
        logger.debug(
            f"Encoding {len(texts)} texts with BGE-M3 (batch_size={self.settings.batch_size_embeddings})"
        )

        # Run embedding in threadpool to avoid blocking
        encode_start = time.time()
        output = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self.embedding_model.encode(
                texts,
                batch_size=self.settings.batch_size_embeddings,
                return_dense=True,
                return_sparse=True,
                return_colbert_vecs=True,
            ),
        )
        encode_time = time.time() - encode_start
        logger.debug(f"BGE-M3 encode completed in {encode_time:.2f}s")

        # Convert to list of dicts (one per text)
        result = []
        for i in range(len(texts)):
            result.append(
                {
                    "dense_vecs": output["dense_vecs"][i],
                    "lexical_weights": output["lexical_weights"][i],
                    "colbert_vecs": output["colbert_vecs"][i],
                }
            )
        return result

    def get_collection_stats(self, collection_name: str) -> dict[str, Any]:
        """Get statistics for a collection."""
        try:
            info = self.client.get_collection(collection_name)
            return {
                "name": collection_name,
                "points_count": info.points_count,
                "vectors_count": getattr(info, "vectors_count", info.indexed_vectors_count),
                "indexed_vectors_count": info.indexed_vectors_count,
                "segment_count": len(info.segments) if hasattr(info, "segments") else 0,
            }
        except Exception as e:
            print(f"Error getting collection stats: {e}")
            return {}
