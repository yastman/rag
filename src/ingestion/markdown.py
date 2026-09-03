# SPDX-License-Identifier: MIT
# Copyright (c) 2025 RAG-Fresh contributors.
"""Deterministic Markdown-only ingestion parser (#3235).

Production ingestion accepts exactly ``.md`` files. This module replaces the
removed Docling ``NativeDoclingAdapter`` with a small stdlib-only parser:

- UTF-8 strict read (no encoding guessing, no converter imports).
- Splitting by ATX headings (``#`` … ``######``) into hierarchical sections;
  headings inside fenced code blocks never split.
- Oversized sections are packed greedily along blank-line paragraph
  boundaries, then hard-split at line boundaries — deterministically, with no
  tokenizer model.
- Output is the existing generic :class:`~src.ingestion.chunker.Chunk`
  contract consumed by ``QdrantHybridWriter``, so manifest deduplication,
  atomic Qdrant replacement, payload shape, and point-id derivation are
  unchanged.

Chunk text keeps the heading context line (``H1 > H2``) that Docling's
``HybridChunker.contextualize`` used to prepend, preserving the
embed-contextualization behavior of the previous pipeline.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.ingestion.chunker import Chunk


# The only suffix production ingestion accepts (#3235). Keep in sync with
# UnifiedConfig.supported_extensions (enforced by the Markdown-only contract).
SUPPORTED_MARKDOWN_SUFFIXES: frozenset[str] = frozenset({".md"})

_ATX_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})")

# ~4 characters per token: deterministic char-budget approximation of the
# previous ``max_tokens_per_chunk`` (BGE-M3 tokenizer) budget.
_CHARS_PER_TOKEN = 4


@dataclass
class MarkdownChunk:
    """Intermediate chunk produced by :class:`MarkdownParser`."""

    text: str
    seq_no: int
    headings: list[str] = field(default_factory=list)


def generate_doc_id(source: str) -> str:
    """Generate document ID from source name (SHA-256 prefix)."""
    return hashlib.sha256(source.encode()).hexdigest()[:16]


class MarkdownParser:
    """Stdlib Markdown reader/splitter producing the generic Chunk contract."""

    SUPPORTED_SUFFIXES = SUPPORTED_MARKDOWN_SUFFIXES

    def __init__(self, *, max_tokens: int = 512) -> None:
        self._max_tokens = max_tokens
        self._max_chars = max(1, max_tokens * _CHARS_PER_TOKEN)

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def chunk_file_sync(self, file_path: Path) -> list[MarkdownChunk]:
        """Read a Markdown file and split it into deterministic chunks."""
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        suffix = file_path.suffix.lower()
        if suffix not in self.SUPPORTED_SUFFIXES:
            raise ValueError(
                f"Unsupported format: {suffix}. Production ingestion is "
                "Markdown-only (#3235); supported suffixes: "
                f"{sorted(self.SUPPORTED_SUFFIXES)}"
            )

        text = file_path.read_text(encoding="utf-8")
        sections = self._split_sections(text)

        chunks: list[MarkdownChunk] = []
        for headings, body in sections:
            body = body.strip()
            if not body:
                continue
            for piece in self._split_oversized(body):
                context = " > ".join(headings)
                chunk_text = f"{context}\n{piece}" if context else piece
                chunks.append(
                    MarkdownChunk(
                        text=chunk_text.strip(),
                        seq_no=len(chunks),
                        headings=list(headings),
                    )
                )

        return chunks

    def _split_sections(self, text: str) -> list[tuple[list[str], str]]:
        """Split Markdown text into (heading-stack, body) sections.

        The heading stack is hierarchical: an ``##`` under an ``#`` yields
        ``["H1", "H2"]``. A deeper heading under a shallower-dimensioned
        stack pads with the last heading so context stays informative.
        Headings inside fenced code blocks are treated as content.
        """
        sections: list[tuple[list[str], str]] = []
        stack: list[tuple[int, str]] = []
        body_lines: list[str] = []
        fence: str | None = None

        def flush() -> None:
            sections.append(([title for _, title in stack], "\n".join(body_lines)))
            body_lines.clear()

        for line in text.splitlines():
            fence_match = _FENCE_RE.match(line)
            if fence_match is not None:
                marker = fence_match.group(2)[:3]
                if fence is None:
                    fence = marker
                elif fence == marker:
                    fence = None
                body_lines.append(line)
                continue
            if fence is None:
                heading_match = _ATX_HEADING_RE.match(line)
                if heading_match is not None:
                    flush()
                    level = len(heading_match.group(1))
                    title = heading_match.group(2).strip()
                    while stack and stack[-1][0] >= level:
                        stack.pop()
                    stack.append((level, title))
                    continue
            body_lines.append(line)

        flush()
        return sections

    def _split_oversized(self, body: str) -> list[str]:
        """Pack a section body into <= max_chars pieces.

        Greedy along blank-line paragraph boundaries; a single paragraph
        longer than the budget is hard-cut at line boundaries until the
        remainder fits.
        """
        if len(body) <= self._max_chars:
            return [body]

        pieces: list[str] = []
        current: list[str] = []
        current_len = 0

        def flush_current() -> None:
            nonlocal current, current_len
            if current:
                pieces.append("\n\n".join(current))
            current = []
            current_len = 0

        for paragraph in re.split(r"\n\s*\n", body):
            if not paragraph.strip():
                continue
            while len(paragraph) > self._max_chars:
                flush_current()
                head, paragraph = self._hard_cut(paragraph)
                pieces.append(head)
            extra = len(paragraph) + (2 if current else 0)
            if current and current_len + extra > self._max_chars:
                flush_current()
                extra = len(paragraph)
            current.append(paragraph)
            current_len += extra

        flush_current()
        return [piece for piece in pieces if piece.strip()]

    def _hard_cut(self, paragraph: str) -> tuple[str, str]:
        """Cut one oversized paragraph at the last line boundary in budget.

        Returns ``(head, tail)``; the tail is re-processed by the caller.
        """
        window = paragraph[: self._max_chars]
        newline_at = window.rfind("\n")
        cut = newline_at if newline_at > 0 else self._max_chars
        return paragraph[:cut].rstrip("\n"), paragraph[cut:].lstrip("\n")

    # ------------------------------------------------------------------
    # Chunk conversion (generic contract)
    # ------------------------------------------------------------------

    def to_ingestion_chunks(
        self,
        markdown_chunks: list[MarkdownChunk],
        source: str,
        source_type: str = "md",
    ) -> list[Chunk]:
        """Convert MarkdownChunks to standard Chunk objects for indexing.

        Mirrors the previous Docling conversion: deterministic ``doc_id``,
        sequential ordering, and the payload-compatible extra metadata.
        """
        doc_id = generate_doc_id(source)
        created_at = datetime.now(UTC).isoformat()

        chunks = []
        for i, mc in enumerate(markdown_chunks):
            extra_metadata: dict[str, Any] = {
                "doc_id": doc_id,
                "source": source,
                "source_type": source_type,
                "created_at": created_at,
                "chunk_order": i,
                "parser": "markdown",
            }

            if mc.headings:
                extra_metadata["section"] = " > ".join(mc.headings)

            chunks.append(
                Chunk(
                    text=mc.text,
                    chunk_id=i,
                    document_name=source,
                    article_number=doc_id,
                    section=" > ".join(mc.headings) if mc.headings else None,
                    page_range=None,
                    order=i,
                    extra_metadata=extra_metadata,
                )
            )

        return chunks
