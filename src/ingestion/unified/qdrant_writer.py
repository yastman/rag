# SPDX-License-Identifier: MIT
# Copyright (c) 2025 RAG-Fresh contributors.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

"""Qdrant writer with payload contract and replace semantics."""

import json as _json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    HasIdCondition,
    MatchValue,
    PointStruct,
    SparseVector,
)

from src.retrieval.topic_classifier import classify_chunk_topic, classify_doc_type


logger = logging.getLogger(__name__)

# Namespace for deterministic UUID generation
NAMESPACE_GDRIVE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

# Keep request bodies below Qdrant's 32MB JSON limit with safety headroom.
QDRANT_UPSERT_MAX_REQUEST_BYTES = 28 * 1024 * 1024


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
    - dense: BGE-M3 1024-dim
    - bm42: BGE-M3 sparse (named 'bm42' for backward compat with existing collection)
    """

    BGE_M3_BATCH_SIZE = 32

    def __init__(
        self,
        qdrant_url: str,
        qdrant_api_key: str | None = None,
        bge_m3_url: str | None = None,
        bge_m3_timeout: float = 300.0,
        bge_m3_concurrency: int = 1,
    ):
        # Qdrant client
        self.client = QdrantClient(
            url=qdrant_url,
            api_key=qdrant_api_key,
            timeout=120,
        )

        # BGE-M3 HTTP client (unified SDK layer)
        from src.services.bge_m3_client import BGEM3SyncClient

        self.bge_m3_url = bge_m3_url or "http://localhost:8000"
        self._bge_client = BGEM3SyncClient(
            base_url=self.bge_m3_url,
            timeout=bge_m3_timeout,
            batch_size=self.BGE_M3_BATCH_SIZE,
            max_length=1024,  # chunks are contextualized (headings prepended) → can exceed 512
        )
        logger.info("QdrantHybridWriter BGE-M3 URL: %s", self.bge_m3_url)
        logger.info("QdrantHybridWriter BGE-M3 timeout: %ss", bge_m3_timeout)
        logger.info("QdrantHybridWriter dense: local BGE-M3 (concurrency=%d)", bge_m3_concurrency)
        logger.info("QdrantHybridWriter sparse: BGE-M3 /encode/sparse")

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
        """Get stable chunk location from chunk metadata or fallback.

        Priority:
        1. Legacy docling meta with page/offset (pre-#3235 points)
        2. chunk_order written by the Markdown parser
        3. Fallback: chunk_{index}
        """
        # Check for legacy docling metadata (pre-#3235 points)
        extra = getattr(chunk, "extra_metadata", {}) or {}
        docling_meta = extra.get("docling_meta", {})

        # Priority 1: Page + offset from legacy docling meta
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

    @staticmethod
    def _infer_language(source_path: str, file_metadata: dict[str, Any]) -> str:
        value = file_metadata.get("language")
        if isinstance(value, str) and value.strip():
            return value.strip().lower()

        normalized = source_path.lower()
        if "/en/" in normalized or normalized.endswith(("-en.pdf", "-en.docx")):
            return "en"
        if "/uk/" in normalized or normalized.endswith(("-uk.pdf", "-uk.docx")):
            return "uk"
        return "ru"

    @staticmethod
    def _infer_source_type(source_path: str, file_metadata: dict[str, Any]) -> str:
        value = file_metadata.get("source_type")
        if isinstance(value, str) and value.strip():
            return value.strip().lower()

        normalized = source_path.lower()
        if "gdrive" in normalized:
            return "gdrive"
        if normalized.endswith(".docx"):
            return "docx"
        if normalized.endswith(".pdf"):
            return "pdf"
        return "file"

    @staticmethod
    def _infer_audience(source_path: str, text: str) -> str:
        normalized = f"{source_path} {text}".lower()
        if any(token in normalized for token in ("client", "клиент", "внж", "покуп", "сделк")):
            return "client"
        return "client"

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
        metadata["topic"] = classify_chunk_topic(getattr(chunk, "text", "")).value
        metadata["doc_type"] = classify_doc_type(
            source_path, str(file_metadata.get("mime_type", ""))
        ).value
        metadata["jurisdiction"] = str(file_metadata.get("jurisdiction", "bg")).lower()
        metadata["language"] = self._infer_language(source_path, file_metadata)
        metadata["source_type"] = self._infer_source_type(source_path, file_metadata)
        metadata["audience"] = self._infer_audience(source_path, getattr(chunk, "text", ""))

        # Clean None values
        metadata = {k: v for k, v in metadata.items() if v is not None}

        return {
            "page_content": chunk.text,
            "metadata": metadata,
            "file_id": file_id,  # Flat for fast delete
        }

    @staticmethod
    def _point_to_jsonable(point: PointStruct) -> dict[str, Any]:
        """Convert a PointStruct into a JSON-serializable dict for size estimation."""
        if hasattr(point, "model_dump"):
            return point.model_dump(mode="json", exclude_none=True)
        if hasattr(point, "dict"):
            return point.dict(exclude_none=True)
        return {
            "id": point.id,
            "vector": point.vector,
            "payload": point.payload,
        }

    @classmethod
    def _estimate_point_request_bytes(cls, point: PointStruct) -> int:
        """Estimate serialized request bytes for a single point."""
        return len(
            _json.dumps(
                cls._point_to_jsonable(point),
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        )

    @staticmethod
    def _text_exceeds_single_point_limit(text: str, source_path: str) -> str | None:
        """Return a request-limit error for text that cannot fit in one Qdrant point."""
        text_bytes = len(text.encode("utf-8"))
        if text_bytes <= QDRANT_UPSERT_MAX_REQUEST_BYTES:
            return None
        return (
            f"Single point text payload {text_bytes / 1024 / 1024:.1f}MB exceeds "
            f"safe Qdrant limit {QDRANT_UPSERT_MAX_REQUEST_BYTES / 1024 / 1024:.0f}MB "
            f"for {source_path}"
        )

    def _upsert_points_in_batches(
        self,
        *,
        collection_name: str,
        points: list[PointStruct],
        source_path: str,
    ) -> int:
        """Upsert points in request-size-safe batches."""
        if not points:
            return 0

        total_upserted = 0
        batch: list[PointStruct] = []
        batch_bytes = 2  # JSON array brackets
        batch_index = 1

        for point in points:
            point_bytes = self._estimate_point_request_bytes(point)
            if point_bytes > QDRANT_UPSERT_MAX_REQUEST_BYTES:
                raise ValueError(
                    f"Single point request {point_bytes / 1024 / 1024:.1f}MB exceeds "
                    f"safe Qdrant limit {QDRANT_UPSERT_MAX_REQUEST_BYTES / 1024 / 1024:.0f}MB "
                    f"for {source_path}"
                )

            separator_bytes = 1 if batch else 0
            if (
                batch
                and batch_bytes + separator_bytes + point_bytes > QDRANT_UPSERT_MAX_REQUEST_BYTES
            ):
                self.client.upsert(collection_name=collection_name, points=batch)
                logger.info(
                    "Upserted batch %d for %s: %d points (~%.1fMB)",
                    batch_index,
                    source_path,
                    len(batch),
                    batch_bytes / 1024 / 1024,
                )
                total_upserted += len(batch)
                batch = [point]
                batch_bytes = 2 + point_bytes
                batch_index += 1
                continue

            batch.append(point)
            batch_bytes += separator_bytes + point_bytes

        if batch:
            self.client.upsert(collection_name=collection_name, points=batch)
            logger.info(
                "Upserted batch %d for %s: %d points (~%.1fMB)",
                batch_index,
                source_path,
                len(batch),
                batch_bytes / 1024 / 1024,
            )
            total_upserted += len(batch)

        return total_upserted

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
                points_selector=FilterSelector(
                    filter=Filter(
                        must=[
                            FieldCondition(
                                key="metadata.file_id",
                                match=MatchValue(value=file_id),
                            )
                        ]
                    )
                ),
            )
            logger.info(f"Deleted {count} points for file_id={file_id}")

        return count

    def delete_by_source_path_sync(self, source_path: str, collection_name: str) -> int:
        """Delete every point whose ``metadata.source`` equals ``source_path``.

        Stable across content changes: ``source_path`` never changes for the
        same file, whereas ``file_id`` is re-minted when content changes (the
        manifest hashes content). The post-upsert stale sweep keys on the new
        ``file_id`` only, so the previous version's points — written under the
        old ``file_id`` — would otherwise be orphaned. The flow calls this
        before re-upserting a changed file so no stale chunks survive.

        Returns the number of points deleted.
        """
        source_filter = Filter(
            must=[FieldCondition(key="metadata.source", match=MatchValue(value=source_path))]
        )
        count = self.client.count(
            collection_name=collection_name,
            count_filter=source_filter,
        ).count

        if count > 0:
            self.client.delete(
                collection_name=collection_name,
                points_selector=FilterSelector(filter=source_filter),
            )
            logger.info("Deleted %d points for source_path=%s", count, source_path)

        return count

    def upsert_chunks_sync(
        self,
        chunks: list[Any],
        file_id: str,
        source_path: str,
        file_metadata: dict[str, Any],
        collection_name: str,
    ) -> WriteStats:
        """Sync atomic-replace counterpart of ``upsert_chunks`` (#1602).

        Build replacement points first, upsert them with deterministic IDs,
        and only delete stale orphan IDs after the upsert succeeds. If any
        step before the stale-id sweep fails, no destructive delete runs.
        """
        stats = WriteStats()

        if not chunks:
            return stats

        try:
            # Step 1: Extract texts
            texts = [chunk.text for chunk in chunks]
            for text in texts:
                if error := self._text_exceeds_single_point_limit(text, source_path):
                    raise ValueError(error)

            # Step 2: Generate embeddings — single hybrid call via BGE-M3.
            # Any failure here exits via `except` BEFORE any destructive call.
            hybrid_result = self._bge_client.encode_hybrid(texts)
            all_dense_embeddings: list[list[float]] = [
                [float(value) for value in embedding] for embedding in hybrid_result.dense_vecs
            ]
            sparse_embeddings = hybrid_result.lexical_weights
            colbert_embeddings = hybrid_result.colbert_vecs or []

            # Indices the encoder flagged as invalid (empty/whitespace texts). The
            # server still returns full-cardinality output with sentinel vectors at
            # these positions — writing those poison vectors would silently corrupt
            # the index, so skip them here. (card_06c91625a24c)
            poison_indices = {pf["index"] for pf in hybrid_result.partial_failures if "index" in pf}
            if poison_indices:
                logger.warning(
                    "Skipping %d chunk(s) with poison vectors for %s (indices=%s)",
                    len(poison_indices),
                    source_path,
                    sorted(poison_indices),
                )

            # Step 3: Build points
            points: list[PointStruct] = []
            new_ids: list[str] = []
            for i, (chunk, dense_vec, sparse_emb) in enumerate(
                zip(chunks, all_dense_embeddings, sparse_embeddings, strict=True)
            ):
                if i in poison_indices:
                    continue
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
                new_ids.append(point_id)

            # Step 4: Upsert replacement points first.
            stats.points_upserted = self._upsert_points_in_batches(
                collection_name=collection_name,
                points=points,
                source_path=source_path,
            )

            # Step 5: Now safe to sweep stale orphan IDs.
            stats.points_deleted = self._delete_stale_points_sync(
                file_id=file_id,
                collection_name=collection_name,
                new_ids=set(new_ids),
            )

            logger.info(
                f"Upserted {stats.points_upserted} points for {source_path} "
                f"(swept {stats.points_deleted} stale points)"
            )

        except Exception as e:
            stats.errors = [str(e)]
            logger.error(f"Error upserting chunks: {e}", exc_info=True)

        return stats

    def _delete_stale_points_sync(
        self,
        *,
        file_id: str,
        collection_name: str,
        new_ids: set[str],
    ) -> int:
        """Delete points that belong to ``file_id`` but are not in ``new_ids``.

        This is the post-upsert sweep half of the atomic-replace pattern from
        #1602: by the time we run, replacement points are already live in the
        collection (Step 4 of ``upsert_chunks_sync``), so we only need to drop
        whichever historical chunk IDs no longer participate in the file.

        Returns the number of stale point IDs that were deleted.
        """
        stale_ids: list[int | str | uuid.UUID] = []
        next_offset: Any = None
        while True:
            records, next_offset = self.client.scroll(
                collection_name=collection_name,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="metadata.file_id",
                            match=MatchValue(value=file_id),
                        )
                    ]
                ),
                limit=512,
                offset=next_offset,
                with_payload=False,
                with_vectors=False,
            )
            for record in records or []:
                rid = record.id
                if rid not in new_ids:
                    stale_ids.append(rid)
            if not next_offset:
                break

        if not stale_ids:
            return 0

        self.client.delete(
            collection_name=collection_name,
            points_selector=Filter(must=[HasIdCondition(has_id=stale_ids)]),
        )
        logger.info("Swept %d stale points for file_id=%s (post-upsert)", len(stale_ids), file_id)
        return len(stale_ids)
