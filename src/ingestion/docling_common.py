"""Shared contract for Docling adapters (HTTP and native).

Contains types and helpers used by both ``DoclingClient`` (HTTP sidecar) and
``NativeDoclingAdapter`` (in-process SDK).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.ingestion.chunker import Chunk


# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------

SUPPORTED_FORMATS: frozenset[str] = frozenset(
    {".pdf", ".docx", ".doc", ".html", ".htm", ".md", ".txt", ".xlsx", ".csv"}
)


@dataclass
class DoclingChunk:
    """Chunk from docling's HybridChunker with rich metadata."""

    text: str
    seq_no: int
    headings: list[str] = field(default_factory=list)
    page_range: tuple[int, int] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def generate_doc_id(source: str) -> str:
    """Generate document ID from source name (SHA-256 prefix)."""
    return hashlib.sha256(source.encode()).hexdigest()[:16]


def to_ingestion_chunks(
    docling_chunks: list[DoclingChunk],
    source: str,
    source_type: str = "docling",
) -> list[Chunk]:
    """Convert DoclingChunks to standard Chunk objects for indexing.

    Args:
        docling_chunks: Chunks from chunk_file() / chunk_file_sync()
        source: Source filename or identifier
        source_type: Type identifier (pdf, docx, gdrive, etc.)

    Returns:
        List of Chunk objects compatible with QdrantHybridWriter
    """
    doc_id = generate_doc_id(source)
    created_at = datetime.now(UTC).isoformat()

    chunks = []
    for i, dc in enumerate(docling_chunks):
        extra_metadata: dict[str, Any] = {
            "doc_id": doc_id,
            "source": source,
            "source_type": source_type,
            "created_at": created_at,
            "chunk_order": i,
        }

        if dc.page_range:
            extra_metadata["page_range"] = list(dc.page_range)

        if dc.headings:
            extra_metadata["section"] = " > ".join(dc.headings)

        if dc.metadata:
            extra_metadata["docling_meta"] = dc.metadata

        chunk = Chunk(
            text=dc.text,
            chunk_id=i,
            document_name=source,
            article_number=doc_id,
            section=" > ".join(dc.headings) if dc.headings else None,
            page_range=dc.page_range,
            order=i,
            extra_metadata=extra_metadata,
        )
        chunks.append(chunk)

    return chunks
