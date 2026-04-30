"""Document chunking strategies."""

import csv
import re
import warnings
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class ChunkingStrategy(StrEnum):
    """Document chunking strategies."""

    FIXED_SIZE = (
        "fixed_size"  # Fixed chunk size with overlap (deprecated — use Docling HybridChunker)
    )
    SEMANTIC = "semantic"  # Based on content structure (paragraphs, sections)
    SLIDING_WINDOW = (
        "sliding_window"  # Sliding window with overlap (deprecated — use Docling HybridChunker)
    )


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


class DocumentChunker:
    """
    Chunk documents into smaller units for processing.

    Strategies:
    1. Fixed size - Simple, consistent chunk sizes
    2. Semantic - Respects document structure
    3. Sliding window - Overlapping chunks for context
    """

    def __init__(
        self,
        chunk_size: int = 1024,
        overlap: int = 256,
        strategy: ChunkingStrategy = ChunkingStrategy.SEMANTIC,
    ):
        """
        Initialize chunker.

        Args:
            chunk_size: Target chunk size in characters (1024 optimal for BGE-M3)
            overlap: Overlap between chunks in characters
            strategy: Chunking strategy (SEMANTIC preserves document structure)
        """
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.strategy = strategy

    def chunk_text(
        self,
        text: str,
        document_name: str,
        article_number: str,
    ) -> list[Chunk]:
        """
        Chunk text content.

        Args:
            text: Text to chunk
            document_name: Name of source document
            article_number: Article/section identifier

        Returns:
            List of chunks
        """
        if self.strategy == ChunkingStrategy.FIXED_SIZE:
            warnings.warn(
                "ChunkingStrategy.FIXED_SIZE is deprecated. Use CocoIndex + Docling "
                "HybridChunker for production chunking.",
                DeprecationWarning,
                stacklevel=2,
            )
            return self._chunk_fixed_size(text, document_name, article_number)
        if self.strategy == ChunkingStrategy.SEMANTIC:
            return self._chunk_semantic(text, document_name, article_number)
        if self.strategy == ChunkingStrategy.SLIDING_WINDOW:
            warnings.warn(
                "ChunkingStrategy.SLIDING_WINDOW is deprecated. Use CocoIndex + Docling "
                "HybridChunker for production chunking.",
                DeprecationWarning,
                stacklevel=2,
            )
            return self._chunk_sliding_window(text, document_name, article_number)
        raise ValueError(f"Unknown strategy: {self.strategy}")

    def _chunk_fixed_size(self, text: str, document_name: str, article_number: str) -> list[Chunk]:
        """Chunk text into fixed-size pieces."""
        chunks = []

        # Calculate number of chunks needed
        num_chunks = max(1, (len(text) - self.overlap) // (self.chunk_size - self.overlap))

        for i in range(num_chunks):
            start = i * (self.chunk_size - self.overlap)
            end = start + self.chunk_size

            chunk_text = text[start:end].strip()

            if chunk_text:
                chunks.append(
                    Chunk(
                        text=chunk_text,
                        chunk_id=i,
                        document_name=document_name,
                        article_number=article_number,
                        order=i,
                    )
                )

        return chunks

    def _chunk_semantic(self, text: str, document_name: str, article_number: str) -> list[Chunk]:
        """
        Chunk text respecting semantic boundaries (paragraphs, sections).

        Handles legal document structure:
        - Sections: "Розділ I", "Розділ II"
        - Chapters: "Глава 1", "Глава II"
        - Articles: "Стаття", "Ст."
        - Paragraphs: Empty lines
        """
        chunks = []

        # Split by major sections first
        section_pattern = r"(Розділ|Глава|Стаття|§|Ст\.)\s*[IVXLCDM\d\w]+"
        sections = re.split(f"({section_pattern})", text)

        current_chunk_text = ""
        chunk_id = 0

        for part in sections:
            if not part.strip():
                continue

            # If this is a section header
            if re.match(section_pattern, part):
                if current_chunk_text.strip():
                    chunks.append(
                        Chunk(
                            text=current_chunk_text.strip(),
                            chunk_id=chunk_id,
                            document_name=document_name,
                            article_number=article_number,
                            order=chunk_id,
                        )
                    )
                    chunk_id += 1
                current_chunk_text = part
            else:
                current_chunk_text += part

            # If chunk is large enough, create it
            if len(current_chunk_text) >= self.chunk_size:
                chunks.append(
                    Chunk(
                        text=current_chunk_text.strip(),
                        chunk_id=chunk_id,
                        document_name=document_name,
                        article_number=article_number,
                        order=chunk_id,
                    )
                )
                current_chunk_text = ""
                chunk_id += 1

        # Add remaining chunk
        if current_chunk_text.strip():
            chunks.append(
                Chunk(
                    text=current_chunk_text.strip(),
                    chunk_id=chunk_id,
                    document_name=document_name,
                    article_number=article_number,
                    order=chunk_id,
                )
            )

        return chunks

    def _chunk_sliding_window(
        self, text: str, document_name: str, article_number: str
    ) -> list[Chunk]:
        """Chunk text with overlapping sliding window."""
        chunks = []
        step = self.chunk_size - self.overlap

        for i, pos in enumerate(range(0, len(text), step)):
            end = min(pos + self.chunk_size, len(text))
            chunk_text = text[pos:end].strip()

            if chunk_text:
                chunks.append(
                    Chunk(
                        text=chunk_text,
                        chunk_id=i,
                        document_name=document_name,
                        article_number=article_number,
                        order=i,
                    )
                )

        return chunks

    @staticmethod
    def extract_metadata(chunk_text: str) -> dict[str, Any]:
        """
        Extract metadata from chunk text.

        Detects:
        - Article numbers
        - Section headers
        - Chapter numbers
        """
        metadata = {}

        # Try to find article number
        article_match = re.search(r"(Стаття|Ст\.)\s*(\d+)", chunk_text)
        if article_match:
            metadata["article_number"] = article_match.group(2)

        # Try to find chapter
        chapter_match = re.search(r"(Розділ|Глава|§)\s*([IVXLCDM\d]+)", chunk_text)
        if chapter_match:
            metadata["chapter"] = chapter_match.group(2)

        return metadata


def chunk_csv_by_rows(csv_path: Path, document_name: str) -> list[Chunk]:
    """
    Chunk CSV file with one row per chunk with structured metadata.

    This preserves row boundaries instead of mixing rows together
    like token-based chunkers do. Perfect for structured data like
    apartment listings where each row is a complete entity.

    Also extracts numeric fields into metadata for filtering:
    - price, rooms, area, floor, floors, distance_to_sea, etc.

    Args:
        csv_path: Path to CSV file
        document_name: Name for the document

    Returns:
        List of chunks, one per CSV row (excluding header)
    """
    chunks = []

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row_idx, row in enumerate(reader):
            # Format row as readable text: "Field1: value1, Field2: value2, ..."
            row_text = ", ".join(f"{k}: {v}" for k, v in row.items() if v)

            # Use first column value or row number as article_number
            article_number = next(iter(row.values())) if row else str(row_idx)

            # Extract structured metadata for filtering
            extra_metadata = _parse_csv_row_metadata(row)

            chunk = Chunk(
                text=row_text,
                chunk_id=row_idx,
                document_name=document_name,
                article_number=article_number,
                order=row_idx,
                extra_metadata=extra_metadata,
            )
            chunks.append(chunk)

    return chunks


def _parse_csv_row_metadata(row: dict[str, str]) -> dict[str, Any]:
    """
    Parse CSV row into structured metadata for Qdrant filtering.

    Extracts numeric fields (price, rooms, area) and converts
    string values to proper types. Handles number formatting
    like "120 000" → 120000.

    Args:
        row: CSV row as dict (field_name: value)

    Returns:
        Structured metadata dict with typed values
    """
    metadata: dict[str, Any] = {}

    # Helper to parse number from string (handles "120 000" format)
    def parse_number(value: str) -> int | float | None:
        if not value or not value.strip():
            return None
        try:
            # Remove spaces and try to parse
            cleaned = value.replace(" ", "").replace(",", "")
            # Try int first, then float
            if "." in cleaned:
                return float(cleaned)
            return int(cleaned)
        except (ValueError, AttributeError):
            return None

    # Map CSV column names to metadata fields
    field_mappings = {
        "Название": "title",
        "Город": "city",
        "Цена (€)": "price",
        "Комнат": "rooms",
        "Площадь (м²)": "area",
        "Этаж": "floor",
        "Этажей": "floors",
        "До моря (м)": "distance_to_sea",
        "Поддержка (€)": "maintenance_fee",
        "Санузлов": "bathrooms",
        "Мебель": "furnished",
        "Круглогодичность": "year_round",
        "Описание": "description",
        "Ссылка": "url",
    }

    for csv_field, meta_field in field_mappings.items():
        value = row.get(csv_field, "").strip()
        if not value:
            continue

        # Numeric fields
        if csv_field in [
            "Цена (€)",
            "Комнат",
            "Площадь (м²)",
            "Этаж",
            "Этажей",
            "До моря (м)",
            "Поддержка (€)",
            "Санузлов",
        ]:
            parsed = parse_number(value)
            if parsed is not None:
                metadata[meta_field] = parsed

        # Boolean fields
        elif csv_field in ["Мебель", "Круглогодичность"]:
            metadata[meta_field] = value.lower() in ["есть", "да", "yes", "true"]

        # Text fields (string as-is)
        else:
            metadata[meta_field] = value

    # Add type marker for filtering
    metadata["source_type"] = "csv_row"

    return metadata
