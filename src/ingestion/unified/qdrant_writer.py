# src/ingestion/unified/qdrant_writer.py
"""Qdrant writer with payload contract and replace semantics."""

import logging
import uuid
from dataclasses import dataclass
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

from telegram_bot.services import VoyageService


logger = logging.getLogger(__name__)

# Namespace for deterministic UUID generation
NAMESPACE_GDRIVE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


@dataclass
class WriteStats:
    """Statistics from write operation."""

    points_deleted: int = 0
    points_upserted: int = 0
    errors: list[str] | None = None


class QdrantHybridWriter:
    """Writes chunks to Qdrant with hybrid vectors and payload contract.

    Payload Contract:
    - page_content: str (chunk text)
    - metadata: dict (doc_id, order, source, file_id, ...)
    - file_id: str (flat, for fast delete)

    Vector Names:
    - dense: Voyage 1024-dim
    - bm42: FastEmbed sparse
    """

    VOYAGE_BATCH_SIZE = 128
    BGE_M3_BATCH_SIZE = 32

    def __init__(
        self,
        qdrant_url: str,
        qdrant_api_key: str | None = None,
        voyage_api_key: str | None = None,
        voyage_model: str = "voyage-4-large",
        bm42_model: str = "Qdrant/bm42-all-minilm-l6-v2-attentions",
        bge_m3_url: str | None = None,
        use_local_embeddings: bool = False,
    ):
        ***REMOVED*** client
        self.client = QdrantClient(
            url=qdrant_url,
            api_key=qdrant_api_key,
            timeout=120,
        )

        # Dense embeddings: local BGE-M3 or Voyage API
        self.use_local_embeddings = use_local_embeddings
        self._http_client = None
        self.voyage = None

        if use_local_embeddings:
            import httpx

            self.bge_m3_url = bge_m3_url or "http://localhost:8000"
            self._http_client = httpx.Client(timeout=60.0)
            logger.info(f"QdrantHybridWriter using local BGE-M3: {self.bge_m3_url}")
        else:
            self.voyage = VoyageService(
                api_key=voyage_api_key,
                model_docs=voyage_model,
            )
            logger.info(f"QdrantHybridWriter using Voyage: {voyage_model}")

        # FastEmbed BM42 for sparse
        self.sparse_model = SparseTextEmbedding(model_name=bm42_model)

        logger.info(f"QdrantHybridWriter initialized with BM42: {bm42_model}")

    @staticmethod
    def generate_point_id(file_id: str, chunk_location: str) -> str:
        """Generate deterministic point ID."""
        combined = f"{file_id}::{chunk_location}"
        return str(uuid.uuid5(NAMESPACE_GDRIVE, combined))

    @staticmethod
    def get_chunk_location(chunk: Any, index: int) -> str:
        """Get stable chunk location from docling metadata or fallback.

        Priority:
        1. Docling meta with page/offset
        2. seq_no from docling
        3. Fallback: chunk_{index}
        """
        # Check for docling metadata
        extra = getattr(chunk, "extra_metadata", {}) or {}
        docling_meta = extra.get("docling_meta", {})

        # Priority 1: Page + offset from docling
        if "page" in docling_meta or "page_start" in docling_meta:
            page = docling_meta.get("page") or docling_meta.get("page_start", 0)
            offset = docling_meta.get("offset", index)
            return f"page_{page}_offset_{offset}"

        # Priority 2: seq_no from docling
        if hasattr(chunk, "extra_metadata") and extra.get("chunk_order") is not None:
            return f"seq_{extra['chunk_order']}"

        # Priority 3: Use order if available
        if hasattr(chunk, "order") and chunk.order is not None:
            return f"order_{chunk.order}"

        # Fallback
        return f"chunk_{index}"

    def _embed_documents_local(self, texts: list[str]) -> list[list[float]]:
        """Embed documents using local BGE-M3 API.

        Args:
            texts: List of document texts

        Returns:
            List of 1024-dim dense embedding vectors
        """
        if not texts:
            return []

        if self._http_client is None:
            raise RuntimeError("HTTP client not initialized for local embeddings")

        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), self.BGE_M3_BATCH_SIZE):
            batch = texts[i : i + self.BGE_M3_BATCH_SIZE]
            response = self._http_client.post(
                f"{self.bge_m3_url}/encode/dense",
                json={"texts": batch, "batch_size": len(batch), "max_length": 512},
            )
            response.raise_for_status()
            all_embeddings.extend(response.json()["dense_vecs"])

        return all_embeddings

    def build_payload(
        self,
        chunk: Any,
        file_id: str,
        source_path: str,
        chunk_location: str,
        file_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Build payload with enforced contract.

        Required fields:
        - page_content: chunk text
        - metadata.file_id, metadata.doc_id, metadata.order, metadata.source
        - file_id (flat for delete)
        """
        order = getattr(chunk, "order", 0) or getattr(chunk, "chunk_id", 0)
        extra = getattr(chunk, "extra_metadata", {}) or {}

        metadata = {
            # Identity (required for small-to-big)
            "file_id": file_id,
            "doc_id": file_id,  # Same as file_id for small-to-big compatibility
            # Order (required for small-to-big sorting)
            "order": order,
            "chunk_order": order,  # Alias
            # Source (required for citations)
            "source": source_path,
            "file_name": getattr(chunk, "document_name", file_metadata.get("file_name")),
            # Chunk position
            "chunk_id": getattr(chunk, "chunk_id", order),
            "chunk_location": chunk_location,
            # Document structure
            "section": getattr(chunk, "section", None),
            "headings": extra.get("headings", []),
            # Page info
            "page_range": list(chunk.page_range) if getattr(chunk, "page_range", None) else None,
            # File info
            "mime_type": file_metadata.get("mime_type"),
            "modified_time": file_metadata.get("modified_time"),
            "content_hash": file_metadata.get("content_hash"),
        }

        # Clean None values
        metadata = {k: v for k, v in metadata.items() if v is not None}

        return {
            "page_content": chunk.text,
            "metadata": metadata,
            "file_id": file_id,  # Flat for fast delete
        }

    async def delete_file(self, file_id: str, collection_name: str) -> int:
        """Delete all points for a file.

        Uses metadata.file_id filter (more reliable than flat file_id).
        """
        # Count before delete
        count_result = self.client.count(
            collection_name=collection_name,
            count_filter=Filter(
                must=[FieldCondition(key="metadata.file_id", match=MatchValue(value=file_id))]
            ),
        )
        count = count_result.count

        if count > 0:
            # Delete by metadata.file_id
            self.client.delete(
                collection_name=collection_name,
                points_selector=Filter(
                    must=[FieldCondition(key="metadata.file_id", match=MatchValue(value=file_id))]
                ),
            )
            logger.info(f"Deleted {count} points for file_id={file_id}")

        return count

    async def upsert_chunks(
        self,
        chunks: list[Any],
        file_id: str,
        source_path: str,
        file_metadata: dict[str, Any],
        collection_name: str,
    ) -> WriteStats:
        """Upsert chunks with replace semantics.

        1. Delete existing points for file_id
        2. Generate embeddings
        3. Build points with payload contract
        4. Upsert to Qdrant
        """
        stats = WriteStats()

        if not chunks:
            return stats

        try:
            # Step 1: Delete existing (replace semantics)
            stats.points_deleted = await self.delete_file(file_id, collection_name)

            # Step 2: Extract texts
            texts = [chunk.text for chunk in chunks]

            # Step 3: Generate embeddings (local BGE-M3 or Voyage API)
            if self.use_local_embeddings:
                dense_embeddings = self._embed_documents_local(texts)
            else:
                if self.voyage is None:
                    raise RuntimeError("VoyageService not initialized")
                dense_embeddings = await self.voyage.embed_documents(texts)
            sparse_embeddings = list(self.sparse_model.embed(texts))

            # Step 4: Build points
            points = []
            for i, (chunk, dense_vec, sparse_emb) in enumerate(
                zip(chunks, dense_embeddings, sparse_embeddings, strict=True)
            ):
                chunk_location = self.get_chunk_location(chunk, i)
                point_id = self.generate_point_id(file_id, chunk_location)
                payload = self.build_payload(
                    chunk, file_id, source_path, chunk_location, file_metadata
                )

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

            # Step 5: Upsert
            self.client.upsert(collection_name=collection_name, points=points)
            stats.points_upserted = len(points)

            logger.info(
                f"Upserted {stats.points_upserted} points for {source_path} "
                f"(replaced {stats.points_deleted})"
            )

        except Exception as e:
            stats.errors = [str(e)]
            logger.error(f"Error upserting chunks: {e}", exc_info=True)

        return stats
