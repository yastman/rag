"""ColBERT reranker service client.

HTTP client for bge-m3-api /rerank endpoint (ColBERT MaxSim).
Replaces VoyageService.rerank when RERANK_PROVIDER=colbert.
"""

import logging
import os

import httpx

from telegram_bot.observability import observe


logger = logging.getLogger(__name__)


class ColbertRerankerService:
    """HTTP client for bge-m3-api ColBERT reranking.

    Provides drop-in replacement for VoyageService.rerank.
    Uses ColBERT MaxSim scoring for local, fast reranking.
    """

    MAX_LENGTH = 512

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float | None = None,
    ):
        """Initialize service.

        Args:
            base_url: BGE-M3 API base URL
            timeout: Request timeout in seconds (default from COLBERT_TIMEOUT env, fallback 120s)
        """
        if timeout is None:
            timeout = float(os.getenv("COLBERT_TIMEOUT", "120.0"))
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)
        logger.info(f"ColbertRerankerService initialized: {base_url} (timeout={timeout}s)")

    @observe(name="colbert-rerank")
    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int = 5,
    ) -> list[dict]:
        """Rerank documents by relevance to query.

        Args:
            query: Search query
            documents: List of document texts
            top_k: Number of top results to return

        Returns:
            List of dicts with 'index' and 'score' keys,
            sorted by score descending. Compatible with bot's
            existing rerank result handling.
        """
        if not documents:
            return []

        response = await self._client.post(
            f"{self.base_url}/rerank",
            json={
                "query": query,
                "documents": documents,
                "top_k": top_k,
                "max_length": self.MAX_LENGTH,
            },
        )
        response.raise_for_status()
        data = response.json()

        # Return in format expected by bot (index + score)
        return [{"index": r["index"], "score": r["score"]} for r in data["results"]]

    async def close(self):
        """Close HTTP client."""
        await self._client.aclose()
