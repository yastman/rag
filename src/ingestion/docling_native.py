"""Feature-flagged native Docling adapter for unified ingestion (#1235).

The native path runs ``docling.document_converter.DocumentConverter`` in
process and chunks the result with ``docling_core.transforms.chunker.HybridChunker``
— the SDK's tokenization-aware chunker that respects hierarchical document
structure (headings, tables, page boundaries).

Issue #1235 retired the previous custom chunking pair (``_chunk_markdown``
+ ``_split_text``) which segmented by raw markdown headings and then split
overflowing sections by character count. The character-based splitter was
already self-flagged ``DeprecationWarning`` in ``src/ingestion/chunker.py``
and is what the issue specifically calls out. ``HybridChunker`` is the
canonical Docling answer per the upstream docs (see Context7
``/docling-project/docling-core``):

    chunker = HybridChunker(max_tokens=N, merge_peers=True)
    for chunk in chunker.chunk(doc):
        ...  # chunk.text, chunk.meta.headings

The chunker is dependency-injected via the constructor so unit tests can
substitute a fake without loading a tokenizer model. When not injected, a
default ``HybridChunker`` is lazily instantiated on first use.

Refs #1235.
"""

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


def _load_runtime_hybrid_chunker() -> Any | None:
    try:
        module = import_module("docling_core.transforms.chunker")
    except Exception:  # pragma: no cover - exercised in unit tests via injected chunker
        return None
    return getattr(module, "HybridChunker", None)


RuntimeDocumentConverter: Any | None = _load_runtime_document_converter()


class NativeDoclingAdapter(DoclingClient):
    """Native Docling adapter with the same chunk contract as DoclingClient.

    Uses ``HybridChunker`` over the in-process ``DoclingDocument`` instead of
    the parent class's docling-serve REST round-trip. Behaviour parity with
    ``DoclingClient.chunk_file_sync`` is preserved through ``DoclingChunk``
    objects: ``text``, ``seq_no``, ``headings`` (from ``chunk.meta.headings``),
    plus a ``parser`` metadata marker so downstream consumers can attribute
    chunks to this code path.
    """

    def __init__(
        self,
        *,
        max_tokens: int = 512,
        converter: DocumentConverterType | None = None,
        chunker: Any | None = None,
    ) -> None:
        super().__init__(DoclingConfig(max_tokens=max_tokens))
        self._converter = converter
        self._max_tokens = max_tokens
        self._chunker = chunker

    def _get_converter(self) -> DocumentConverterType:
        if self._converter is None:
            if RuntimeDocumentConverter is None:
                raise RuntimeError(
                    "docling is not installed; docling_native backend requires the optional "
                    "docling dependency"
                )
            self._converter = RuntimeDocumentConverter()
        return self._converter

    def _get_chunker(self) -> Any:
        """Return the injected chunker, lazily falling back to a default ``HybridChunker``.

        Tokenizer download is deferred to first chunk call so module import stays
        cheap (matters for unit-test collection time and for the cocoindex
        target connector that eagerly imports this module).
        """
        if self._chunker is None:
            HybridChunker = _load_runtime_hybrid_chunker()
            if HybridChunker is None:
                raise RuntimeError(
                    "docling_core is not installed; docling_native backend requires "
                    "HybridChunker from docling_core.transforms.chunker"
                )
            self._chunker = HybridChunker(max_tokens=self._max_tokens, merge_peers=True)
        return self._chunker

    def chunk_file_sync(
        self,
        file_path: Path,
        contextualize: bool = True,
    ) -> list[DoclingChunk]:
        """Convert a document natively and chunk it via ``HybridChunker``.

        The ``contextualize`` flag preserves the parent class contract:
        contextualized embedding text uses ``HybridChunker.contextualize`` when
        available, while callers can still request raw chunk text.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        suffix = file_path.suffix.lower()
        if suffix not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported format: {suffix}")

        result = self._get_converter().convert(file_path)
        document = result.document

        chunker = self._get_chunker()
        raw_chunks = list(chunker.chunk(document))
        contextualize_chunk = getattr(chunker, "contextualize", None)
        if contextualize and not callable(contextualize_chunk):
            logger.warning(
                "Docling native chunker %s has no contextualize() method; falling back to raw "
                "chunk text for %s",
                type(chunker).__name__,
                file_path.name,
            )

        chunks: list[DoclingChunk] = []
        for raw_chunk in raw_chunks:
            if contextualize and callable(contextualize_chunk):
                text = contextualize_chunk(raw_chunk)
            else:
                text = getattr(raw_chunk, "text", "")
            text = (text or "").strip()
            if not text:
                continue
            meta = getattr(raw_chunk, "meta", None)
            headings = list(getattr(meta, "headings", None) or []) if meta is not None else []
            chunks.append(
                DoclingChunk(
                    text=text,
                    seq_no=len(chunks),
                    headings=headings,
                    page_range=None,
                    metadata={"parser": "docling_native"},
                )
            )

        logger.info(
            "Chunked (native, HybridChunker) %s: %d chunks",
            file_path.name,
            len(chunks),
        )
        return chunks
