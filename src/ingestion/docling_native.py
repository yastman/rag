"""Feature-flagged native Docling adapter for unified ingestion."""

from __future__ import annotations

import logging
from importlib import import_module
from pathlib import Path
from typing import Any

from src.ingestion.docling_client import DoclingChunk, DoclingClient, DoclingConfig


logger = logging.getLogger(__name__)

DocumentConverterType = Any
HybridChunkerType = Any


def _load_runtime_document_converter() -> Any | None:
    try:
        module = import_module("docling.document_converter")
    except Exception:  # pragma: no cover - exercised in unit tests via injected converter
        return None
    return getattr(module, "DocumentConverter", None)


def _load_hybrid_chunker() -> Any | None:
    """Load HybridChunker from docling_core (optional ingest dependency)."""
    try:
        module = import_module("docling_core.transforms.chunker")
        return getattr(module, "HybridChunker", None)
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("Failed to load HybridChunker from docling_core.transforms.chunker: %s", exc)
        return None
    try:
        module = import_module("docling.chunking")
        return getattr(module, "HybridChunker", None)
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("Failed to load HybridChunker from docling.chunking: %s", exc)
        return None
    return None


RuntimeDocumentConverter: Any | None = _load_runtime_document_converter()
RuntimeHybridChunker: Any | None = _load_hybrid_chunker()


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

    def _get_chunker(self) -> HybridChunkerType:
        """Return a HybridChunker instance configured with max_tokens."""
        if RuntimeHybridChunker is None:
            raise RuntimeError(
                "docling_core is not installed; docling_native backend requires the optional "
                "docling-core dependency for HybridChunker"
            )
        return RuntimeHybridChunker(max_tokens=self._max_tokens)

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
        chunker = self._get_chunker()
        raw_chunks = list(chunker.chunk(result.document))

        chunks: list[DoclingChunk] = []
        for idx, chunk in enumerate(raw_chunks):
            headings: list[str] = []
            page_range: tuple[int, int] | None = None

            meta = getattr(chunk, "meta", None)
            if meta is not None:
                headings = getattr(meta, "headings", None) or []
                doc_items = getattr(meta, "doc_items", None) or []
                page_numbers: list[int] = []
                for item in doc_items:
                    for prov in getattr(item, "prov", []):
                        page_no = getattr(prov, "page_no", None)
                        if page_no is not None:
                            page_numbers.append(int(page_no))
                if page_numbers:
                    page_range = (min(page_numbers), max(page_numbers))

            chunks.append(
                DoclingChunk(
                    text=chunk.text,
                    seq_no=idx,
                    headings=headings,
                    page_range=page_range,
                    metadata={"parser": "docling_native"},
                )
            )

        logger.info("Chunked (native) %s: %d chunks", file_path.name, len(chunks))
        return chunks
