"""Voyage AI reranking service for RAG pipeline."""

import logging
from typing import Any

from telegram_bot.services.voyage_client import VoyageClient


logger = logging.getLogger(__name__)


class VoyageRerankerService:
    """Rerank search results using Voyage AI reranker.

    Improves search quality by reranking initial retrieval results
    based on query-document relevance.

    Models:
    - rerank-2: Best quality (recommended)
    - rerank-2-lite: Faster, lower cost
    """

    def __init__(self, model: str = "rerank-2"):
        """Initialize Voyage reranker.

        Args:
            model: Voyage reranker model. Default is rerank-2.
        """
        self.model = model
        self._client = VoyageClient.get_instance()
        logger.info(f"VoyageRerankerService initialized with model={model}")

    def _extract_text(self, doc: dict[str, Any]) -> str:
        """Extract text content from document dict.

        Args:
            doc: Document dict with 'text' or 'page_content' key.

        Returns:
            Text content string.
        """
        return doc.get("text") or doc.get("page_content") or ""

    def rerank_sync(
        self,
        query: str,
        documents: list[dict[str, Any]],
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Rerank documents by query relevance (sync).

        Args:
            query: Search query.
            documents: List of document dicts with 'text'/'page_content' and 'metadata'.
            top_k: Number of top results to return.

        Returns:
            Reranked documents with added 'rerank_score' and 'original_score' fields.
        """
        if not documents:
            return []

        # Extract texts for reranking
        texts = [self._extract_text(doc) for doc in documents]

        # Call Voyage reranker
        rerank_results = self._client.rerank_sync(query, texts, model=self.model, top_k=top_k)

        # Build reranked document list
        reranked = []
        for result in rerank_results:
            idx = result["index"]
            original_doc = documents[idx]

            reranked.append(
                {
                    "text": self._extract_text(original_doc),
                    "metadata": original_doc.get("metadata", {}),
                    "rerank_score": result["score"],
                    "original_score": original_doc.get("score", 0.0),
                }
            )

        logger.debug(f"Reranked {len(documents)} -> {len(reranked)} documents")
        return reranked

    async def rerank(
        self,
        query: str,
        documents: list[dict[str, Any]],
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Rerank documents by query relevance (async).

        Args:
            query: Search query.
            documents: List of document dicts.
            top_k: Number of top results to return.

        Returns:
            Reranked documents.
        """
        if not documents:
            return []

        texts = [self._extract_text(doc) for doc in documents]

        rerank_results = await self._client.rerank(query, texts, model=self.model, top_k=top_k)

        reranked = []
        for result in rerank_results:
            idx = result["index"]
            original_doc = documents[idx]

            reranked.append(
                {
                    "text": self._extract_text(original_doc),
                    "metadata": original_doc.get("metadata", {}),
                    "rerank_score": result["score"],
                    "original_score": original_doc.get("score", 0.0),
                }
            )

        return reranked
