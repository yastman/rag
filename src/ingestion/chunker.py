"""Document chunking strategies."""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class ChunkingStrategy(str, Enum):
    """Document chunking strategies."""

    FIXED_SIZE = "fixed_size"  # Fixed chunk size with overlap
    SEMANTIC = "semantic"  # Based on content structure (paragraphs, sections)
    SLIDING_WINDOW = "sliding_window"  # Sliding window with overlap


@dataclass
class Chunk:
    """Document chunk with metadata."""

    text: str
    chunk_id: int
    document_name: str
    article_number: str  # For legal documents
    chapter: Optional[str] = None
    section: Optional[str] = None
    page_range: Optional[tuple[int, int]] = None  # (start, end) pages
    order: int = 0


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
        chunk_size: int = 512,
        overlap: int = 128,
        strategy: ChunkingStrategy = ChunkingStrategy.FIXED_SIZE,
    ):
        """
        Initialize chunker.

        Args:
            chunk_size: Target chunk size in characters
            overlap: Overlap between chunks in characters
            strategy: Chunking strategy
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
            return self._chunk_fixed_size(text, document_name, article_number)
        if self.strategy == ChunkingStrategy.SEMANTIC:
            return self._chunk_semantic(text, document_name, article_number)
        if self.strategy == ChunkingStrategy.SLIDING_WINDOW:
            return self._chunk_sliding_window(text, document_name, article_number)
        raise ValueError(f"Unknown strategy: {self.strategy}")

    def _chunk_fixed_size(
        self, text: str, document_name: str, article_number: str
    ) -> list[Chunk]:
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

    def _chunk_semantic(
        self, text: str, document_name: str, article_number: str
    ) -> list[Chunk]:
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
