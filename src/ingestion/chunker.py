"""Document chunk dataclass for ingestion pipeline."""

from dataclasses import dataclass
from typing import Any


@dataclass
class Chunk:
    """Document chunk with metadata."""

    text: str
    chunk_id: int
    document_name: str
    article_number: str  # For legal documents
    chapter: str | None = None
    section: str | None = None
    page_range: tuple[int, int] | None = None  # (start, end) pages
    order: int = 0
    extra_metadata: dict[str, Any] | None = None  # For structured data (CSV, etc.)
