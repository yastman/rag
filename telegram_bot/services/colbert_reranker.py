"""ColBERT reranker service client.

HTTP client for bge-m3-api /rerank endpoint (ColBERT MaxSim).
Replaces VoyageService.rerank when RERANK_PROVIDER=colbert.
Delegates to BGEM3Client (unified SDK layer).
"""

import logging
import os

from telegram_bot.observability import observe
from telegram_bot.services.bge_m3_client import BGEM3Client


logger = logging.getLogger(__name__)


class ColbertRerankerService:
    """HTTP client for bge-m3-api ColBERT reranking.

    Provides drop-in replacement for VoyageService.rerank.
    Uses ColBERT MaxSim scoring for local, fast reranking.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float | None = None,
        *,
        client: BGEM3Client | None = None,
    ):
        if timeout is None:
            timeout = float(os.getenv("COLBERT_TIMEOUT", "120.0"))
        self._client = client or BGEM3Client(base_url=base_url, timeout=timeout)
        logger.info("ColbertRerankerService initialized: %s (timeout=%ss)", base_url, timeout)

    @observe(name="colbert-rerank")
    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int = 5,
    ) -> list[dict]:
        """Rerank documents by relevance to query.

        Returns list of dicts with 'index' and 'score' keys,
        sorted by score descending.
        """
        if not documents:
            return []
        result = await self._client.rerank(query, documents, top_k)
        return result.results

    async def close(self):
        """Close HTTP client."""
        await self._client.aclose()
