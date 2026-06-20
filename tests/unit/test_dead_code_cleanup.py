"""Tests for dead code cleanup — issue #780.

Verifies:
1. DocumentChunker FIXED_SIZE and SLIDING_WINDOW strategies emit DeprecationWarning
   (replaced by CocoIndex + Docling HybridChunker in production).
2. DocumentChunker SEMANTIC strategy does NOT emit DeprecationWarning
   (still the production path used by the ingestion pipeline).
"""

import warnings


class TestChunkerDeprecatedStrategies:
    """FIXED_SIZE and SLIDING_WINDOW strategies must emit DeprecationWarning."""

    def test_fixed_size_strategy_emits_deprecation(self):
        """FIXED_SIZE strategy is not used in prod — must emit DeprecationWarning."""
        from src.ingestion.chunker import ChunkingStrategy, DocumentChunker

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            chunker = DocumentChunker(strategy=ChunkingStrategy.FIXED_SIZE)
            chunker.chunk_text("some text content here", "doc.pdf", "1")

        deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(deprecation_warnings) >= 1, (
            "ChunkingStrategy.FIXED_SIZE must emit DeprecationWarning "
            "(production path uses CocoIndex + Docling HybridChunker)"
        )

    def test_sliding_window_strategy_emits_deprecation(self):
        """SLIDING_WINDOW strategy is not used in prod — must emit DeprecationWarning."""
        from src.ingestion.chunker import ChunkingStrategy, DocumentChunker

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            chunker = DocumentChunker(strategy=ChunkingStrategy.SLIDING_WINDOW)
            chunker.chunk_text("some text content here", "doc.pdf", "1")

        deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(deprecation_warnings) >= 1, (
            "ChunkingStrategy.SLIDING_WINDOW must emit DeprecationWarning "
            "(production path uses CocoIndex + Docling HybridChunker)"
        )

    def test_semantic_strategy_no_deprecation(self):
        """SEMANTIC is the production chunking path — no warning."""
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

    def test_fixed_size_deprecation_message_mentions_replacement(self):
        """FIXED_SIZE deprecation message should mention the replacement."""
        from src.ingestion.chunker import ChunkingStrategy, DocumentChunker

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            chunker = DocumentChunker(strategy=ChunkingStrategy.FIXED_SIZE)
            chunker.chunk_text("text", "doc.pdf", "1")

        deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert deprecation_warnings, "Expected DeprecationWarning"
        msg = str(deprecation_warnings[0].message).lower()
        assert (
            "deprecated" in msg or "hybridchunker" in msg or "docling" in msg or "cocoindex" in msg
        ), f"Message should mention replacement, got: {msg!r}"

    def test_sliding_window_deprecation_message_mentions_replacement(self):
        """SLIDING_WINDOW deprecation message should mention the replacement."""
        from src.ingestion.chunker import ChunkingStrategy, DocumentChunker

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            chunker = DocumentChunker(strategy=ChunkingStrategy.SLIDING_WINDOW)
            chunker.chunk_text("text", "doc.pdf", "1")

        deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert deprecation_warnings, "Expected DeprecationWarning"
        msg = str(deprecation_warnings[0].message).lower()
        assert (
            "deprecated" in msg or "hybridchunker" in msg or "docling" in msg or "cocoindex" in msg
        ), f"Message should mention replacement, got: {msg!r}"
