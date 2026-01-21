"""Voyage AI embedding service for RAG pipeline."""

import logging

from telegram_bot.services.voyage_client import VoyageClient


logger = logging.getLogger(__name__)


class VoyageEmbeddingService:
    """Generate embeddings using Voyage AI API.

    Replaces local BGE-M3 EmbeddingService with Voyage AI for:
    - Better quality (voyage-3-large: 67.29 MTEB vs BGE-M3: 62.27)
    - Lower RAM usage (~200MB vs ~2.5GB)
    - Unified vendor with cache and reranking
    """

    ***REMOVED*** API batch size limit
    BATCH_SIZE = 128

    def __init__(self, model: str = "voyage-3-large"):
        """Initialize Voyage embedding service.

        Args:
            model: Voyage model name. Default is voyage-3-large for best quality.
                   Use voyage-3-lite for faster/cheaper embeddings.
        """
        self.model = model
        self._client = VoyageClient.get_instance()
        logger.info(f"VoyageEmbeddingService initialized with model={model}")

    def embed_query_sync(self, text: str) -> list[float]:
        """Generate embedding for query text (sync).

        Uses input_type="query" for asymmetric search.

        Args:
            text: Query text to embed.

        Returns:
            Embedding vector (1024-dim for voyage-3-large).
        """
        return self._client.embed_query_sync(text, model=self.model)

    def embed_documents_sync(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for documents (sync).

        Uses input_type="document" for asymmetric search.
        Automatically batches large inputs.

        Args:
            texts: List of document texts to embed.

        Returns:
            List of embedding vectors.
        """
        if not texts:
            return []

        # Batch processing for large inputs
        all_embeddings = []
        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i : i + self.BATCH_SIZE]
            embeddings = self._client.embed_sync(batch, model=self.model, input_type="document")
            all_embeddings.extend(embeddings)

        return all_embeddings

    # Async methods for compatibility with async code
    async def embed_query(self, text: str) -> list[float]:
        """Generate embedding for query text (async).

        Args:
            text: Query text to embed.

        Returns:
            Embedding vector.
        """
        return await self._client.embed_query(text, model=self.model)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for documents (async).

        Args:
            texts: List of document texts.

        Returns:
            List of embedding vectors.
        """
        if not texts:
            return []

        all_embeddings = []
        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i : i + self.BATCH_SIZE]
            embeddings = await self._client.embed(batch, model=self.model, input_type="document")
            all_embeddings.extend(embeddings)

        return all_embeddings

    async def close(self):
        """Close service (no-op for API client)."""
