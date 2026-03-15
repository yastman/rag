"""Optional native Docling adapter (feature-flagged)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.ingestion.docling_client import DoclingChunk


def _chunk_text(text: str, *, max_tokens: int) -> list[str]:
    """Split markdown text into bounded chunks by word count."""
    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    cursor = 0
    while cursor < len(words):
        window = words[cursor : cursor + max_tokens]
        chunks.append(" ".join(window))
        cursor += max_tokens
    return chunks


@dataclass
class DoclingNativeConfig:
    """Runtime config for native Docling adapter."""

    max_tokens: int = 512


class DoclingNativeConverter:
    """Narrow wrapper around Docling `DocumentConverter` for spike usage."""

    def __init__(self, config: DoclingNativeConfig | None = None) -> None:
        self.config = config or DoclingNativeConfig()

    @staticmethod
    def is_available() -> bool:
        """Return True when native docling package is installed."""
        try:
            from docling.document_converter import DocumentConverter  # noqa: F401
        except Exception:
            return False
        return True

    @staticmethod
    def _create_document_converter():
        from docling.document_converter import DocumentConverter

        return DocumentConverter()

    def chunk_file_sync(self, file_path: Path) -> list[DoclingChunk]:
        """Convert file with native Docling and return normalized chunks."""
        try:
            converter = self._create_document_converter()
        except Exception as exc:  # pragma: no cover - environment dependent
            raise RuntimeError("Native docling is not installed") from exc

        result = converter.convert(str(file_path))
        document = result.document
        markdown = document.export_to_markdown()
        raw_chunks = _chunk_text(markdown, max_tokens=self.config.max_tokens)

        chunks: list[DoclingChunk] = []
        for idx, text in enumerate(raw_chunks):
            chunks.append(
                DoclingChunk(
                    text=text,
                    seq_no=idx,
                    headings=[],
                    page_range=None,
                    metadata={"backend": "docling-native", "offset": idx},
                )
            )
        return chunks
