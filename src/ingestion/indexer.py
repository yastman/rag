"""Document indexing to vector database."""

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer

from src.config import Settings, VectorDimensions

from .chunker import Chunk


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
    - BGE-M3 embeddings (1024-dim dense + sparse)
    - Batch indexing for efficiency
    - Automatic collection creation
    - Metadata preservation
    - Async processing
    """

    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize indexer.

        Args:
            settings: Configuration settings
        """
        self.settings = settings or Settings()
        self.client = QdrantClient(self.settings.qdrant_url)
        self.embedding_model = SentenceTransformer("BAAI/bge-m3")
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
            pass  # Collection doesn't exist, will create

        # Create collection with vector configuration
        self.client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=VectorDimensions.DENSE,
                distance=Distance.COSINE,
            ),
            # Optimize for mixed search (dense + metadata filtering)
            optimizers_config=None,
            quantization_config=None,
        )

        # Create indexes on important payload fields for fast filtering
        self._create_payload_indexes(collection_name)

        print(f"✓ Created collection: {collection_name}")
        return True

    def _create_payload_indexes(self, collection_name: str) -> None:
        """Create indexes on payload fields for fast filtering."""
        try:
            # Index article_number for fast filtering
            self.client.create_payload_index(
                collection_name=collection_name,
                field_name="article_number",
                field_schema="keyword",
            )

            # Index document_name
            self.client.create_payload_index(
                collection_name=collection_name,
                field_name="document_name",
                field_schema="keyword",
            )

            print(f"✓ Created payload indexes for {collection_name}")
        except Exception as e:
            print(f"Warning: Could not create payload indexes: {e}")

    async def index_chunks(
        self,
        chunks: list[Chunk],
        collection_name: str,
        batch_size: Optional[int] = None,
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

    async def _index_batch(
        self, chunks: list[Chunk], collection_name: str
    ) -> None:
        """Index a batch of chunks."""
        try:
            # Generate embeddings for batch
            texts = [chunk.text for chunk in chunks]
            embeddings = await self._embed_texts(texts)

            # Prepare points for Qdrant
            points = []
            for chunk, embedding in zip(chunks, embeddings):
                point = PointStruct(
                    id=str(uuid.uuid4()),
                    vector=embedding,
                    payload={
                        "text": chunk.text,
                        "document_name": chunk.document_name,
                        "article_number": chunk.article_number,
                        "chapter": chunk.chapter,
                        "section": chunk.section,
                        "chunk_id": chunk.chunk_id,
                        "order": chunk.order,
                    },
                )
                points.append(point)

            # Upsert points to Qdrant
            self.client.upsert(
                collection_name=collection_name,
                points=points,
            )

            self.stats.indexed_chunks += len(points)
            print(f"  ✓ Indexed {len(points)} chunks")

        except Exception as e:
            self.stats.failed_chunks += len(chunks)
            print(f"  ✗ Failed to index batch: {e}")

    async def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for texts.

        Uses BGE-M3 model for semantic embeddings.
        """
        # Run embedding in threadpool to avoid blocking
        embeddings = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self.embedding_model.encode(
                texts,
                batch_size=self.settings.batch_size_embeddings,
                show_progress_bar=False,
                normalize_embeddings=True,
            ),
        )
        result: list[list[float]] = embeddings.tolist()
        return result

    def get_collection_stats(self, collection_name: str) -> dict[str, Any]:
        """Get statistics for a collection."""
        try:
            info = self.client.get_collection(collection_name)
            return {
                "name": collection_name,
                "points_count": info.points_count,
                "vectors_count": info.vectors_count,
                "indexed_vectors_count": info.indexed_vectors_count,
                "segment_count": len(info.segments) if hasattr(info, 'segments') else 0,
            }
        except Exception as e:
            print(f"Error getting collection stats: {e}")
            return {}
