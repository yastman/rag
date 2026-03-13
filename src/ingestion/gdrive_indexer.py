"""Google Drive document indexer with hybrid search and replace semantics.

DEPRECATED: Use unified ingestion pipeline instead (src.ingestion.unified).

Indexes documents from synced Google Drive folder into Qdrant with:
- Voyage AI dense embeddings (1024-dim)
- FastEmbed BM42 sparse vectors
- Quantization configured at collection level (`*_scalar` / `*_binary`)
- Replace semantics: DELETE by file_id -> UPSERT new chunks
"""

import logging
import os
import time
import uuid
import warnings
from dataclasses import dataclass, field
from typing import Any

from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    SparseVector,
)

from src.ingestion.chunker import Chunk
from telegram_bot.services import VoyageService


warnings.warn(
    "This module is deprecated. Use src.ingestion.unified instead.",
    DeprecationWarning,
    stacklevel=2,
)

logger = logging.getLogger(__name__)

# Namespace for deterministic UUID generation
NAMESPACE_GDRIVE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


@dataclass
class IndexStats:
    """Indexing statistics."""

    total_chunks: int = 0
    indexed_chunks: int = 0
    deleted_points: int = 0
    failed_chunks: int = 0
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)


class GDriveIndexer:
    """Index Google Drive documents with hybrid search and replace semantics.

    Features:
    - Voyage AI voyage-4-large (1024-dim dense)
    - FastEmbed BM42 sparse vectors
    - Replace semantics: DELETE by file_id before UPSERT
    - Deterministic point IDs: uuid5(file_id + chunk_location)
    """

    VOYAGE_BATCH_SIZE = 128
    DEFAULT_COLLECTION = "gdrive_documents_bge"

    def __init__(
        self,
        qdrant_url: str | None = None,
        qdrant_api_key: str | None = None,
        voyage_api_key: str | None = None,
        voyage_model: str = "voyage-4-large",
    ):
        """Initialize indexer.

        Args:
            qdrant_url: Qdrant URL (default from QDRANT_URL env)
            qdrant_api_key: Qdrant API key (optional)
            voyage_api_key: Voyage API key (default from VOYAGE_API_KEY env)
            voyage_model: Voyage model name
        """
        self.qdrant_url = qdrant_url or os.getenv("QDRANT_URL", "http://localhost:6333")
        self.qdrant_api_key = qdrant_api_key or os.getenv("QDRANT_API_KEY")
        api_key = voyage_api_key or os.getenv("VOYAGE_API_KEY")
        if not api_key:
            raise ValueError("VOYAGE_API_KEY is required")
        self.voyage_api_key = api_key

        # Qdrant client
        if self.qdrant_api_key:
            self.client = QdrantClient(
                url=self.qdrant_url, api_key=self.qdrant_api_key, timeout=120
            )
        else:
            self.client = QdrantClient(url=self.qdrant_url, timeout=120)

        # Voyage AI for dense embeddings
        self.voyage_service = VoyageService(
            api_key=self.voyage_api_key,
            model_docs=voyage_model,
        )

        # FastEmbed BM42 for sparse embeddings
        self.sparse_model = SparseTextEmbedding(
            model_name="Qdrant/bm42-all-minilm-l6-v2-attentions"
        )

        logger.info(f"GDriveIndexer initialized: {voyage_model} + BM42")

    def _generate_point_id(self, file_id: str, chunk_location: str) -> str:
        """Generate deterministic point ID from file_id and chunk_location.

        Args:
            file_id: Google Drive file ID or local file path hash
            chunk_location: Chunk location identifier (e.g., "chunk_0", "page_1_para_2")

        Returns:
            UUID string (deterministic)
        """
        combined = f"{file_id}::{chunk_location}"
        return str(uuid.uuid5(NAMESPACE_GDRIVE, combined))

    async def delete_file_points(
        self,
        file_id: str,
        collection_name: str | None = None,
    ) -> int:
        """Delete all points for a given file_id.

        Args:
            file_id: File identifier to delete
            collection_name: Target collection

        Returns:
            Number of points deleted (estimated)
        """
        collection = collection_name or self.DEFAULT_COLLECTION

        # Count existing points first
        count_result = self.client.count(
            collection_name=collection,
            count_filter=Filter(
                must=[
                    FieldCondition(
                        key="file_id",
                        match=MatchValue(value=file_id),
                    )
                ]
            ),
        )
        existing_count = count_result.count

        if existing_count > 0:
            self.client.delete(
                collection_name=collection,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="file_id",
                            match=MatchValue(value=file_id),
                        )
                    ]
                ),
            )
            logger.info(f"Deleted {existing_count} points for file_id={file_id}")

        return existing_count

    async def index_file_chunks(
        self,
        chunks: list[Chunk],
        file_id: str,
        collection_name: str | None = None,
        file_metadata: dict[str, Any] | None = None,
    ) -> IndexStats:
        """Index chunks for a single file with replace semantics.

        Deletes existing points for file_id, then upserts new chunks.

        Args:
            chunks: List of chunks to index
            file_id: File identifier (used for replace semantics)
            collection_name: Target collection
            file_metadata: Additional metadata to add to all points

        Returns:
            Indexing statistics
        """
        start_time = time.time()
        collection = collection_name or self.DEFAULT_COLLECTION
        stats = IndexStats(total_chunks=len(chunks))

        if not chunks:
            logger.warning(f"No chunks to index for file_id={file_id}")
            return stats

        try:
            # Step 1: Delete existing points for this file
            stats.deleted_points = await self.delete_file_points(file_id, collection)

            # Step 2: Generate embeddings
            texts = [chunk.text for chunk in chunks]

            # Dense embeddings (Voyage)
            dense_embeddings = await self.voyage_service.embed_documents(texts)

            # Sparse embeddings (BM42)
            sparse_embeddings = list(self.sparse_model.embed(texts))

            # Step 3: Build points
            points = []
            for i, (chunk, dense_vec, sparse_emb) in enumerate(
                zip(chunks, dense_embeddings, sparse_embeddings, strict=True)
            ):
                chunk_location = f"chunk_{i}"
                if chunk.extra_metadata and "chunk_location" in chunk.extra_metadata:
                    chunk_location = chunk.extra_metadata["chunk_location"]

                point_id = self._generate_point_id(file_id, chunk_location)

                # Build payload
                payload: dict[str, Any] = {
                    "file_id": file_id,
                    "file_name": chunk.document_name,
                    "chunk_id": chunk.chunk_id,
                    "chunk_location": chunk_location,
                    "page_content": chunk.text,
                    "headings": (
                        chunk.extra_metadata.get("headings", []) if chunk.extra_metadata else []
                    ),
                }

                # Add optional metadata
                if chunk.section:
                    payload["section"] = chunk.section
                if chunk.page_range:
                    payload["page_range"] = list(chunk.page_range)
                if chunk.extra_metadata:
                    for key in ["source_path", "mime_type", "modified_time"]:
                        if key in chunk.extra_metadata:
                            payload[key] = chunk.extra_metadata[key]
                if file_metadata:
                    payload.update(file_metadata)

                point = PointStruct(
                    id=point_id,
                    vector={
                        "dense": dense_vec,
                        "bm42": SparseVector(
                            indices=sparse_emb.indices.tolist(),
                            values=sparse_emb.values.tolist(),
                        ),
                    },
                    payload=payload,
                )
                points.append(point)

            # Step 4: Upsert to Qdrant
            self.client.upsert(collection_name=collection, points=points)
            stats.indexed_chunks = len(points)

            logger.info(
                f"Indexed {stats.indexed_chunks} chunks for file_id={file_id} "
                f"(replaced {stats.deleted_points} existing)"
            )

        except Exception as e:
            stats.failed_chunks = len(chunks)
            stats.errors.append(str(e))
            logger.error(f"Indexing failed for file_id={file_id}: {e}", exc_info=True)

        stats.duration_seconds = time.time() - start_time
        return stats
