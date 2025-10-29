"""PDF document parser using PyMuPDF."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Union

import fitz  # PyMuPDF


@dataclass
class ParsedDocument:
    """Parsed document with metadata."""

    filename: str
    title: str
    content: str  # Full text
    num_pages: int
    metadata: dict[str, Any]


class PDFParser:
    """
    Parse PDF documents using PyMuPDF (fitz).

    Supports:
    - Text extraction with layout preservation
    - Metadata extraction
    - Batch processing
    - Multiple file formats (PDF, DOCX, EPUB, etc.)
    """

    def __init__(self):
        """Initialize PDF parser."""
        self.supported_formats = [".pdf", ".docx", ".epub", ".txt"]

    def parse_file(self, filepath: Union[str, Path]) -> ParsedDocument:
        """
        Parse a single PDF file.

        Args:
            filepath: Path to PDF file (string or Path object)

        Returns:
            ParsedDocument with extracted content and metadata
        """
        filepath = Path(filepath) if isinstance(filepath, str) else filepath

        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        if filepath.suffix.lower() not in self.supported_formats:
            raise ValueError(
                f"Unsupported format: {filepath.suffix}. "
                f"Supported: {self.supported_formats}"
            )

        # Open document
        doc = fitz.open(filepath)

        # Extract metadata
        metadata = doc.metadata if hasattr(doc, 'metadata') else {}
        title = metadata.get('title') or filepath.stem

        # Extract text from all pages
        text_parts = []
        for page_num, page in enumerate(doc, 1):
            page_text = page.get_text()
            text_parts.append(f"--- Page {page_num} ---\n{page_text}")

        content = "\n".join(text_parts)

        doc.close()

        return ParsedDocument(
            filename=filepath.name,
            title=title,
            content=content,
            num_pages=len(doc),
            metadata=metadata,
        )

    def parse_directory(
        self, dirpath: Union[str, Path], pattern: str = "*.pdf"
    ) -> list[ParsedDocument]:
        """
        Parse all PDFs in a directory.

        Args:
            dirpath: Path to directory (string or Path object)
            pattern: File pattern (e.g., "*.pdf", "*.txt")

        Returns:
            List of parsed documents
        """
        dirpath = Path(dirpath) if isinstance(dirpath, str) else dirpath
        documents = []

        for filepath in dirpath.glob(pattern):
            try:
                doc = self.parse_file(str(filepath))
                documents.append(doc)
            except Exception as e:
                print(f"Warning: Failed to parse {filepath}: {e}")

        return documents

    def parse_multiple(self, filepaths: list[str]) -> list[ParsedDocument]:
        """
        Parse multiple files.

        Args:
            filepaths: List of file paths

        Returns:
            List of parsed documents
        """
        documents = []

        for filepath in filepaths:
            try:
                doc = self.parse_file(filepath)
                documents.append(doc)
            except Exception as e:
                print(f"Warning: Failed to parse {filepath}: {e}")

        return documents
