"""Tests for dead code cleanup — issue #780.

Verifies:
1. ColbertRerankerService emits DeprecationWarning (client-side reranking replaced
   by server-side ColBERT via hybrid_search_rrf_colbert() in #569).
2. DocumentChunker SEMANTIC strategy does NOT emit DeprecationWarning
   (still the production path via src/core/pipeline.py).

Note: ``ChunkingStrategy.FIXED_SIZE`` and ``ChunkingStrategy.SLIDING_WINDOW``
were removed entirely in #1235 (they had no production callers and emitted
``DeprecationWarning`` since #780). The "still emits a warning" assertions
that lived here are now redundant — the strategies don't exist on the enum
any more, so calling them is a hard ``AttributeError``. The structural
guard lives in ``tests/contract/test_chunking_strategy_sdk_native_contract.py``.
"""

import warnings
from unittest.mock import MagicMock


class TestColbertRerankerDeprecation:
    """ColbertRerankerService should emit DeprecationWarning on instantiation."""

    def test_colbert_reranker_emits_deprecation_warning(self):
        """Instantiating ColbertRerankerService must warn that it is deprecated."""
        from telegram_bot.services.colbert_reranker import ColbertRerankerService

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            ColbertRerankerService(client=MagicMock())

        deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(deprecation_warnings) >= 1, (
            "ColbertRerankerService.__init__ must emit DeprecationWarning "
            "(replaced by server-side ColBERT via hybrid_search_rrf_colbert)"
        )

    def test_colbert_reranker_deprecation_message_mentions_replacement(self):
        """Deprecation message should mention the replacement (hybrid_search or #569)."""
        from telegram_bot.services.colbert_reranker import ColbertRerankerService

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            ColbertRerankerService(client=MagicMock())

        deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert deprecation_warnings, "Expected at least one DeprecationWarning"
        msg = str(deprecation_warnings[0].message).lower()
        assert "deprecated" in msg or "569" in msg or "hybrid_search" in msg, (
            f"Deprecation message should mention replacement, got: {msg!r}"
        )


class TestSemanticChunkingNoDeprecation:
    """``ChunkingStrategy.SEMANTIC`` is the kept SDK-native path (#1235)."""

    def test_semantic_strategy_no_deprecation(self):
        """SEMANTIC is the production path — no warning."""
        from src.ingestion.chunker import ChunkingStrategy, DocumentChunker

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            chunker = DocumentChunker(strategy=ChunkingStrategy.SEMANTIC)
            chunker.chunk_text("Стаття 1. Загальні положення законодавства", "doc.pdf", "1")

        deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(deprecation_warnings) == 0, (
            f"ChunkingStrategy.SEMANTIC must NOT emit DeprecationWarning, "
            f"got: {[str(x.message) for x in deprecation_warnings]}"
        )
