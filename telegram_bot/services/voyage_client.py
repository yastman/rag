"""Voyage AI client with retry logic for embeddings and reranking."""

import logging
import os
from typing import Optional

import voyageai
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
)


logger = logging.getLogger(__name__)


class VoyageClient:
    """Unified Voyage AI client for RAG pipeline.

    Provides embeddings and reranking with automatic retry on rate limits.
    Uses singleton pattern to reuse client across requests.
    """

    _instance: Optional["VoyageClient"] = None

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Voyage client.

        Args:
            api_key: Voyage API key. Falls back to VOYAGE_API_KEY env var.

        Raises:
            ValueError: If no API key provided or found in environment.
        """
        self._api_key = api_key or os.getenv("VOYAGE_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "VOYAGE_API_KEY not set. "
                "Provide api_key parameter or set VOYAGE_API_KEY environment variable."
            )

        self._client = voyageai.Client(api_key=self._api_key)
        logger.info("VoyageClient initialized")

    @classmethod
    def get_instance(cls, api_key: Optional[str] = None) -> "VoyageClient":
        """Get singleton instance.

        Args:
            api_key: Optional API key (used only on first call).

        Returns:
            Shared VoyageClient instance.
        """
        if cls._instance is None:
            cls._instance = cls(api_key)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing)."""
        cls._instance = None

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        reraise=True,
    )
    def embed_sync(
        self,
        texts: list[str],
        model: str = "voyage-3-large",
        input_type: str = "document",
    ) -> list[list[float]]:
        """Generate embeddings with retry on rate limits (sync).

        Args:
            texts: List of texts to embed.
            model: Voyage model name.
            input_type: "document" or "query".

        Returns:
            List of embedding vectors.
        """
        result = self._client.embed(
            texts=texts,
            model=model,
            input_type=input_type,
        )
        return result.embeddings

    def embed_query_sync(self, query: str, model: str = "voyage-3-large") -> list[float]:
        """Embed single query (sync).

        Args:
            query: Query text.
            model: Voyage model name.

        Returns:
            Single embedding vector.
        """
        embeddings = self.embed_sync([query], model=model, input_type="query")
        return embeddings[0]

    def embed_for_cache_sync(self, text: str) -> list[float]:
        """Embed for cache using lighter model (sync).

        Args:
            text: Text to embed.

        Returns:
            Embedding vector from voyage-3-lite.
        """
        embeddings = self.embed_sync([text], model="voyage-3-lite", input_type="query")
        return embeddings[0]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
    )
    def rerank_sync(
        self,
        query: str,
        documents: list[str],
        model: str = "rerank-2",
        top_k: int = 5,
    ) -> list[dict]:
        """Rerank documents by relevance (sync).

        Args:
            query: Search query.
            documents: List of document texts.
            model: Reranker model name.
            top_k: Number of top results to return.

        Returns:
            List of dicts with 'index' and 'score' keys, sorted by relevance.
        """
        if not documents:
            return []

        result = self._client.rerank(
            query=query,
            documents=documents,
            model=model,
            top_k=top_k,
        )

        return [{"index": r.index, "score": r.relevance_score} for r in result.results]

    # Async wrappers for compatibility with async code
    async def embed(
        self,
        texts: list[str],
        model: str = "voyage-3-large",
        input_type: str = "document",
    ) -> list[list[float]]:
        """Generate embeddings (async wrapper)."""
        return self.embed_sync(texts, model, input_type)

    async def embed_query(self, query: str, model: str = "voyage-3-large") -> list[float]:
        """Embed single query (async wrapper)."""
        return self.embed_query_sync(query, model)

    async def embed_for_cache(self, text: str) -> list[float]:
        """Embed for cache (async wrapper)."""
        return self.embed_for_cache_sync(text)

    async def rerank(
        self,
        query: str,
        documents: list[str],
        model: str = "rerank-2",
        top_k: int = 5,
    ) -> list[dict]:
        """Rerank documents (async wrapper)."""
        return self.rerank_sync(query, documents, model, top_k)
