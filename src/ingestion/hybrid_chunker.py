"""Public adapter for ``docling_core.transforms.chunker.HybridChunker`` (#1235).

The legacy :class:`~src.ingestion.chunker.DocumentChunker` exposes
``FIXED_SIZE`` / ``SLIDING_WINDOW`` strategies that the project itself
marked deprecated in favour of Docling's HybridChunker (issue #1235).
This module gives downstream code a stable, tested entry point so the
follow-up call-site migrations (``cocoindex_flow.py``,
``core/pipeline.py``) become mechanical edits.

The adapter intentionally does **not** delete the legacy chunker — that
removal is gated by the contract test
``tests/contract/test_chunker_migration_1235_contract.py`` which
allowlists existing call sites and ratchets toward zero.

Verified shape via Context7 (``/docling-project/docling-core``):

* ``HybridChunker(tokenizer=, max_tokens=, merge_peers=)``
* ``chunker.chunk(doc)`` returns chunks each exposing a ``text`` attribute.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterable
from typing import Any

from src.ingestion.chunker import Chunk


__all__ = ["chunks_to_chunk_objects", "make_hybrid_chunker"]


def _load_hybrid_chunker_cls() -> type[Any] | None:
    """Lazy-import ``HybridChunker``; returns ``None`` when ingest extra missing."""
    try:
        module = importlib.import_module("docling_core.transforms.chunker")
    except ImportError:
        return None
    return getattr(module, "HybridChunker", None)


def make_hybrid_chunker(
    *,
    max_tokens: int = 1024,
    merge_peers: bool = True,
    tokenizer: Any | None = None,
) -> Any:
    """Return a configured ``HybridChunker`` instance.

    Args:
        max_tokens: Token budget per chunk. Default 1024 matches the BGE-M3
            embedding window the project ships with.
        merge_peers: Merge undersized peer chunks that share metadata.
        tokenizer: Optional tokenizer (transformers ``PreTrainedTokenizer``
            or HF model name). When ``None`` the SDK's own default factory
            is used — we deliberately omit the kwarg in that case so the
            SDK default applies.

    Raises:
        ImportError: When ``docling_core`` is not installed. Message points
            operators at ``uv sync --extra ingest``.
    """
    HybridChunker = _load_hybrid_chunker_cls()
    if HybridChunker is None:
        raise ImportError(
            "docling_core.transforms.chunker.HybridChunker is unavailable. "
            "Install the optional ingest extra: `uv sync --extra ingest`."
        )

    kwargs: dict[str, Any] = {"max_tokens": max_tokens, "merge_peers": merge_peers}
    if tokenizer is not None:
        kwargs["tokenizer"] = tokenizer
    return HybridChunker(**kwargs)


def _extract_text(item: Any) -> str:
    """Best-effort extraction of chunk text from object or dict shapes."""
    text = getattr(item, "text", None)
    if text is None and isinstance(item, dict):
        text = item.get("text", "")
    return text or ""


def chunks_to_chunk_objects(
    raw_chunks: Iterable[Any],
    *,
    document_name: str,
    article_number: str = "",
) -> list[Chunk]:
    """Adapt ``HybridChunker.chunk(doc)`` output to legacy :class:`Chunk` dataclasses.

    Empty-text chunks are dropped. ``chunk_id`` and ``order`` are assigned
    from the surviving sequence so downstream consumers (indexer,
    contextual loader) keep their stable identifiers.

    Args:
        raw_chunks: Iterable produced by ``HybridChunker.chunk(doc)``.
            Each item may be a Pydantic-style object exposing ``.text`` or
            a plain dict with a ``"text"`` key.
        document_name: Stable name attached to every emitted ``Chunk``.
        article_number: Optional article identifier carried into each
            ``Chunk`` (used by legal-document ingestion). Defaults to ``""``
            for generic documents that have no article structure.
    """
    out: list[Chunk] = []
    next_id = 0
    for item in raw_chunks:
        text = _extract_text(item).strip()
        if not text:
            continue
        out.append(
            Chunk(
                text=text,
                chunk_id=next_id,
                document_name=document_name,
                article_number=article_number,
                order=next_id,
            )
        )
        next_id += 1
    return out
