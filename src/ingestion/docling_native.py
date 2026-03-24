"""Feature-flagged native Docling adapter for unified ingestion."""

from __future__ import annotations

import logging
from importlib import import_module
from pathlib import Path
from typing import Any

from src.ingestion.docling_client import DoclingChunk, DoclingClient, DoclingConfig


logger = logging.getLogger(__name__)

DocumentConverterType = Any


def _load_runtime_document_converter() -> Any | None:
    try:
        module = import_module("docling.document_converter")
    except Exception:  # pragma: no cover - exercised in unit tests via injected converter
        return None
    return getattr(module, "DocumentConverter", None)


RuntimeDocumentConverter: Any | None = _load_runtime_document_converter()


class NativeDoclingAdapter(DoclingClient):
    """Native Docling adapter with the same chunk contract as DoclingClient."""

    def __init__(
        self,
        *,
        max_tokens: int = 512,
        converter: DocumentConverterType | None = None,
    ) -> None:
        super().__init__(DoclingConfig(max_tokens=max_tokens))
        self._converter = converter
        self._max_tokens = max_tokens

    def _get_converter(self) -> DocumentConverterType:
        if self._converter is None:
            if RuntimeDocumentConverter is None:
                raise RuntimeError(
                    "docling is not installed; docling_native backend requires the optional "
                    "docling dependency"
                )
            self._converter = RuntimeDocumentConverter()
        return self._converter

    def chunk_file_sync(
        self,
        file_path: Path,
        contextualize: bool = True,
    ) -> list[DoclingChunk]:
        """Convert document natively and normalize it into DoclingChunk objects."""
        del contextualize  # Native path already emits the final chunk text.

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        suffix = file_path.suffix.lower()
        if suffix not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported format: {suffix}")

        result = self._get_converter().convert(file_path)
        markdown = result.document.export_to_markdown()
        chunks = self._chunk_markdown(markdown)
        logger.info("Chunked (native) %s: %d chunks", file_path.name, len(chunks))
        return chunks

    def _chunk_markdown(self, markdown: str) -> list[DoclingChunk]:
        sections: list[tuple[list[str], str]] = []
        current_heading: list[str] = []
        current_lines: list[str] = []

        def flush() -> None:
            text = "\n".join(current_lines).strip()
            if not text:
                return
            for chunk_text in self._split_text(text):
                sections.append((current_heading.copy(), chunk_text))

        for raw_line in markdown.splitlines():
            line = raw_line.rstrip()
            if line.startswith("#"):
                flush()
                current_lines = []
                heading = line.lstrip("#").strip()
                current_heading = [heading] if heading else []
                continue

            current_lines.append(line)

        flush()

        if not sections and markdown.strip():
            sections.append(([], markdown.strip()))

        normalized: list[DoclingChunk] = []
        for idx, (headings, text) in enumerate(sections):
            normalized.append(
                DoclingChunk(
                    text=text,
                    seq_no=idx,
                    headings=headings,
                    page_range=None,
                    metadata={"parser": "docling_native"},
                )
            )
        return normalized

    def _split_text(self, text: str) -> list[str]:
        if len(text) <= self._max_tokens:
            return [text]

        chunks: list[str] = []
        current = ""
        for paragraph in [part.strip() for part in text.split("\n\n") if part.strip()]:
            candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
            if current and len(candidate) > self._max_tokens:
                chunks.append(current)
                current = paragraph
            else:
                current = candidate

        if current:
            chunks.append(current)

        return chunks or [text]
