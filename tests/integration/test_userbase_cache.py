# tests/integration/test_userbase_cache.py
"""Integration tests for USER-base semantic cache."""

import os

import pytest


pytestmark = pytest.mark.skipif(
    os.getenv("USER_BASE_URL") is None,
    reason="USER_BASE_URL not set (requires running user-base service)",
)


class TestUserBaseCacheIntegration:
    """Integration tests requiring running services."""
    async def test_russian_paraphrase_matching(self):
        """Should match Russian paraphrases with USER-base."""
        from telegram_bot.services.vectorizers import UserBaseVectorizer

        vectorizer = UserBaseVectorizer(
            base_url=os.getenv("USER_BASE_URL", "http://localhost:8003")
        )

        # Test RU paraphrases
        query1 = "двухкомнатная квартира с видом на море"
        query2 = "двушка с морским видом"

        emb1 = await vectorizer.aembed(query1)
        emb2 = await vectorizer.aembed(query2)

        # Cosine similarity
        import numpy as np

        similarity = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))

        # Should be high for paraphrases (> 0.8)
        assert similarity > 0.8, f"Paraphrase similarity too low: {similarity}"

        await vectorizer.aclose()
