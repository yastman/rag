"""Tests for dead code cleanup — issue #780.

Verifies:
1. ColbertRerankerService emits DeprecationWarning (client-side reranking replaced
   by server-side ColBERT via hybrid_search_rrf_colbert() in #569).
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
