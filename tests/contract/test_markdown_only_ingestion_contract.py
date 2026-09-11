"""Contract: production ingestion is Markdown-only (#3235).

Retained static contract (#3407) — the user-facing gate only:

- UnifiedConfig.supported_extensions is exactly ``{'.md'}``.
- A real ``.md`` file parses successfully with the stdlib parser.
- One representative converter-era suffix is rejected by the parser gate.

The searchable-ingestion result is proven by the strict E2E suite
(#3416/#3364); converter, lock, and Docker absence checks ended with the
Docling behavior they guarded.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.ingestion.markdown import MarkdownParser
from src.ingestion.unified.config import UnifiedConfig


def test_unified_config_supports_only_markdown() -> None:
    """UnifiedConfig.supported_extensions must be exactly {'.md'}."""
    assert UnifiedConfig().supported_extensions == frozenset({".md"}), (
        "UnifiedConfig.supported_extensions must be exactly {'.md'} — "
        "production ingestion is Markdown-only (#3235)."
    )


def test_markdown_parser_parses_real_md_file(tmp_path: Path) -> None:
    """A successful `.md` parse returns at least one chunk."""
    doc = tmp_path / "doc.md"
    doc.write_text("# Heading\n\nBody paragraph.", encoding="utf-8")

    chunks = MarkdownParser().chunk_file_sync(doc)

    assert len(chunks) >= 1


def test_markdown_parser_rejects_representative_non_markdown_suffix(
    tmp_path: Path,
) -> None:
    """A representative converter-era suffix (.pdf) must stay rejected."""
    doc = tmp_path / "doc.pdf"
    doc.write_bytes(b"%PDF-1.7 not really a pdf")

    with pytest.raises(ValueError, match="Markdown-only"):
        MarkdownParser().chunk_file_sync(doc)
