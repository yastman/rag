# src/ingestion/unified/qdrant_writer.py
"""Qdrant writer with payload contract and replace semantics."""

import json as _json
import logging
import threading
import uuid
from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    SparseVector,
)

from src.ingestion.unified.observability import observe, try_update_ingestion_trace
from src.retrieval.topic_classifier import classify_chunk_topic, classify_doc_type
from telegram_bot.services import VoyageService


logger = logging.getLogger(__name__)

# Namespace for deterministic UUID generation
NAMESPACE_GDRIVE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

# Qdrant default max payload size (32 MB).  Points exceeding this are skipped.
QDRANT_MAX_PAYLOAD_BYTES = 32 * 1024 * 1024


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
    - dense: BGE-M3 1024-dim (or Voyage)
    - bm42: BGE-M3 sparse (named 'bm42' for backward compat with existing collection)
    """

    VOYAGE_BATCH_SIZE = 128
    BGE_M3_BATCH_SIZE = 32

    def __init__(
        self,
        qdrant_url: str,
        qdrant_api_key: str | None = None,
        voyage_api_key: str | None = None,
        voyage_model: str = "voyage-4-large",
        bge_m3_url: str | None = None,
        bge_m3_timeout: float = 300.0,
        bge_m3_concurrency: int = 1,
        use_local_embeddings: bool = False,
    ):
        # Qdrant client
        self.client = QdrantClient(
            url=qdrant_url,
            api_key=qdrant_api_key,
            timeout=120,
        )

        # BGE-M3 HTTP client (unified SDK layer)
        from telegram_bot.services.bge_m3_client import BGEM3SyncClient

        self.bge_m3_url = bge_m3_url or "http://localhost:8000"
        self._bge_client = BGEM3SyncClient(
            base_url=self.bge_m3_url,
            timeout=bge_m3_timeout,
            batch_size=self.BGE_M3_BATCH_SIZE,
        )
        logger.info("QdrantHybridWriter BGE-M3 URL: %s", self.bge_m3_url)
        logger.info("QdrantHybridWriter BGE-M3 timeout: %ss", bge_m3_timeout)

        # Dense embeddings: local BGE-M3 or Voyage API
        self.use_local_embeddings = use_local_embeddings
        self.voyage = None

        if use_local_embeddings:
            self._dense_semaphore = threading.Semaphore(max(1, bge_m3_concurrency))
            logger.info(
                f"QdrantHybridWriter dense: local BGE-M3 (concurrency={bge_m3_concurrency})"
            )
        else:
            if not voyage_api_key:
                raise ValueError("voyage_api_key is required when use_local_embeddings=False")
            self.voyage = VoyageService(
                api_key=voyage_api_key,
                model_docs=voyage_model,
            )
            logger.info(f"QdrantHybridWriter dense: Voyage ({voyage_model})")

        logger.info("QdrantHybridWriter sparse: BGE-M3 /encode/sparse")

    def _embed_sparse(self, texts: list[str]) -> list[dict[str, list]]:
        """Generate sparse embeddings via BGEM3SyncClient.

        Returns list of dicts with 'indices' and 'values' keys.
        """
        if not texts:
            return []
        result = self._bge_client.encode_sparse(texts)
        return result.weights

    def _embed_colbert(self, texts: list[str]) -> list[list[list[float]]]:
        """Generate ColBERT multivectors via BGEM3SyncClient.

        Returns list of token vector lists (one per document).
        Each document's colbert is list[list[float]] (num_tokens x 1024).
        """
        if not texts:
            return []
        result = self._bge_client.encode_colbert(texts)
        return result.colbert_vecs

    @staticmethod
    def _to_sparse_vector(sparse_emb: Any) -> SparseVector:
        if isinstance(sparse_emb, dict):
            indices = sparse_emb.get("indices", [])
            values = sparse_emb.get("values", [])
        else:
            indices = sparse_emb.indices.tolist()
            values = sparse_emb.values.tolist()
        return SparseVector(indices=indices, values=values)

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
        """Embed documents using BGEM3SyncClient.

        Args:
            texts: List of document texts

        Returns:
            List of 1024-dim dense embedding vectors
        """
        if not texts:
            return []
        # Semaphore covers entire call including internal batching.
        # bge_m3_concurrency defaults to 1; CocoIndex runs sequentially.
        with self._dense_semaphore:
            result = self._bge_client.encode_dense(texts)
        return result.vectors

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
        metadata["topic"] = classify_chunk_topic(getattr(chunk, "text", ""))
        metadata["doc_type"] = classify_doc_type(
            source_path, str(file_metadata.get("mime_type", ""))
        )

        # Clean None values
        metadata = {k: v for k, v in metadata.items() if v is not None}

        return {
            "page_content": chunk.text,
            "metadata": metadata,
            "file_id": file_id,  # Flat for fast delete
        }

    @observe(name="ingestion-qdrant-delete-file", capture_input=False, capture_output=False)
    async def delete_file(self, file_id: str, collection_name: str) -> int:
        """Delete all points for a file.

        Uses metadata.file_id filter (more reliable than flat file_id).
        """
        try_update_ingestion_trace(
            command="qdrant-delete-file",
            status="started",
            metadata={"collection": collection_name},
        )
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

        try_update_ingestion_trace(
            command="qdrant-delete-file",
            status="completed",
            metadata={"collection": collection_name, "points_deleted": count},
        )
        return count

    @observe(name="ingestion-qdrant-upsert-chunks", capture_input=False, capture_output=False)
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
        try_update_ingestion_trace(
            command="qdrant-upsert-chunks",
            status="started",
            metadata={"collection": collection_name, "chunks": len(chunks)},
        )

        if not chunks:
            try_update_ingestion_trace(
                command="qdrant-upsert-chunks",
                status="completed",
                metadata={"collection": collection_name, "chunks": 0},
            )
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
            sparse_embeddings = self._embed_sparse(texts)
            colbert_embeddings = self._embed_colbert(texts) if self.use_local_embeddings else []

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

                vector_dict: dict = {
                    "dense": dense_vec,
                    "bm42": self._to_sparse_vector(sparse_emb),
                }
                if colbert_embeddings:
                    vector_dict["colbert"] = colbert_embeddings[i]

                point = PointStruct(
                    id=point_id,
                    vector=vector_dict,
                    payload=payload,
                )
                points.append(point)

            # Step 5: Payload size guard
            payload_size = len(_json.dumps([p.payload for p in points]).encode())
            if payload_size > QDRANT_MAX_PAYLOAD_BYTES:
                msg = (
                    f"Payload {payload_size / 1024 / 1024:.1f}MB exceeds "
                    f"Qdrant limit {QDRANT_MAX_PAYLOAD_BYTES / 1024 / 1024:.0f}MB "
                    f"for {source_path} ({len(points)} chunks) — skipping"
                )
                logger.warning(msg)
                stats.errors = [msg]
                try_update_ingestion_trace(
                    command="qdrant-upsert-chunks",
                    status="error",
                    metadata={"collection": collection_name, "error_type": "PayloadTooLarge"},
                )
                return stats

            # Step 6: Upsert
            self.client.upsert(collection_name=collection_name, points=points)
            stats.points_upserted = len(points)

            logger.info(
                f"Upserted {stats.points_upserted} points for {source_path} "
                f"(replaced {stats.points_deleted})"
            )

        except Exception as e:
            stats.errors = [str(e)]
            logger.error(f"Error upserting chunks: {e}", exc_info=True)
            try_update_ingestion_trace(
                command="qdrant-upsert-chunks",
                status="error",
                metadata={"collection": collection_name, "error_type": type(e).__name__},
            )
            return stats

        try_update_ingestion_trace(
            command="qdrant-upsert-chunks",
            status="completed",
            metadata={
                "collection": collection_name,
                "points_deleted": stats.points_deleted,
                "points_upserted": stats.points_upserted,
            },
        )
        return stats

    def delete_file_sync(self, file_id: str, collection_name: str) -> int:
        """Sync version of delete_file.

        Uses sync Qdrant client directly.
        """
        # Qdrant client is already sync
        count_result = self.client.count(
            collection_name=collection_name,
            count_filter=Filter(
                must=[FieldCondition(key="metadata.file_id", match=MatchValue(value=file_id))]
            ),
        )
        count = count_result.count

        if count > 0:
            self.client.delete(
                collection_name=collection_name,
                points_selector=Filter(
                    must=[FieldCondition(key="metadata.file_id", match=MatchValue(value=file_id))]
                ),
            )
            logger.info(f"Deleted {count} points for file_id={file_id}")

        return count

    def upsert_chunks_sync(
        self,
        chunks: list[Any],
        file_id: str,
        source_path: str,
        file_metadata: dict[str, Any],
        collection_name: str,
    ) -> WriteStats:
        """Sync version of upsert_chunks.

        Uses sync Voyage client and sync Qdrant operations.
        """
        stats = WriteStats()

        if not chunks:
            return stats

        try:
            # Step 1: Delete existing (replace semantics)
            stats.points_deleted = self.delete_file_sync(file_id, collection_name)

            # Step 2: Extract texts
            texts = [chunk.text for chunk in chunks]

            # Step 3: Generate embeddings — single hybrid call when local BGE-M3
            all_dense_embeddings: list[list[float]]
            if self.use_local_embeddings:
                hybrid_result = self._bge_client.encode_hybrid(texts)
                all_dense_embeddings = [
                    [float(value) for value in embedding] for embedding in hybrid_result.dense_vecs
                ]
                sparse_embeddings = hybrid_result.lexical_weights
                colbert_embeddings = hybrid_result.colbert_vecs or []
            else:
                if self.voyage is None:
                    raise RuntimeError("VoyageService not initialized")
                all_dense_embeddings = []
                for i in range(0, len(texts), self.VOYAGE_BATCH_SIZE):
                    batch = texts[i : i + self.VOYAGE_BATCH_SIZE]
                    response = self.voyage._client.embed(
                        texts=batch,
                        model=self.voyage._model_docs,
                        input_type="document",
                    )
                    all_dense_embeddings.extend(
                        [[float(value) for value in embedding] for embedding in response.embeddings]
                    )
                sparse_embeddings = self._embed_sparse(texts)
                colbert_embeddings = []

            # Step 4: Build points
            points = []
            for i, (chunk, dense_vec, sparse_emb) in enumerate(
                zip(chunks, all_dense_embeddings, sparse_embeddings, strict=True)
            ):
                chunk_location = self.get_chunk_location(chunk, i)
                point_id = self.generate_point_id(file_id, chunk_location)
                payload = self.build_payload(
                    chunk, file_id, source_path, chunk_location, file_metadata
                )

                vector_dict: dict = {
                    "dense": dense_vec,
                    "bm42": self._to_sparse_vector(sparse_emb),
                }
                if colbert_embeddings:
                    vector_dict["colbert"] = colbert_embeddings[i]

                point = PointStruct(
                    id=point_id,
                    vector=vector_dict,
                    payload=payload,
                )
                points.append(point)

            # Step 5: Payload size guard — skip oversized batches
            payload_size = len(_json.dumps([p.payload for p in points]).encode())
            if payload_size > QDRANT_MAX_PAYLOAD_BYTES:
                msg = (
                    f"Payload {payload_size / 1024 / 1024:.1f}MB exceeds "
                    f"Qdrant limit {QDRANT_MAX_PAYLOAD_BYTES / 1024 / 1024:.0f}MB "
                    f"for {source_path} ({len(points)} chunks) — skipping"
                )
                logger.warning(msg)
                stats.errors = [msg]
                return stats

            # Step 6: Upsert (sync)
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
