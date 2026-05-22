"""Document chunking strategies."""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ChunkingStrategy(StrEnum):
    """Document chunking strategies.

    Only the structure-aware ``SEMANTIC`` path is kept — the previous
    ``FIXED_SIZE`` and ``SLIDING_WINDOW`` strategies were deprecated
    in #780 and removed in #1235 because production code never used them
    (they emitted ``DeprecationWarning`` from ``chunk_text``). For new
    chunking work prefer Docling ``HybridChunker`` via
    ``DoclingClient.chunk_file()`` (#1235).
    """

    SEMANTIC = "semantic"  # Structure-aware: paragraphs, sections, articles


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
    """Structure-aware semantic chunker for legal/long-form text.

    Used by the legacy ingestion path; new ingestion goes through Docling
    ``HybridChunker`` (#1235).
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
            strategy: Chunking strategy (only ``SEMANTIC`` is supported)
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
        if self.strategy == ChunkingStrategy.SEMANTIC:
            return self._chunk_semantic(text, document_name, article_number)
        raise ValueError(f"Unknown strategy: {self.strategy}")

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
