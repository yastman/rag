"""Unified Voyage AI service for embeddings and reranking.

Smart Gateway pattern - single entry point for all Voyage AI operations.
Validated by: Voyage AI official documentation (January 2026)
"""

import asyncio
import logging

import voyageai
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)


logger = logging.getLogger(__name__)


class VoyageService:
    """Unified Smart Gateway for Voyage AI.

    Provides:
    - Embeddings for documents (voyage-4-large by default)
    - Embeddings for queries (voyage-4-lite by default, asymmetric retrieval)
    - Reranking (rerank-2.5 by default, 32K context)
    - Matryoshka embeddings (variable dimensions: 2048, 1024, 512, 256)

    Features:
    - Automatic batching (128 texts per request)
    - Retry with exponential backoff (6 attempts, official recommendation)
    - asyncio.to_thread for non-blocking async calls
    """

    # Batch size for embeddings (Voyage AI recommendation)
    BATCH_SIZE = 128

    # Supported Matryoshka dimensions (voyage-4 series)
    MATRYOSHKA_DIMS = (2048, 1024, 512, 256)
    DEFAULT_DIM = 1024

    def __init__(
        self,
        api_key: str,
        model_docs: str = "voyage-4-large",
        model_queries: str = "voyage-4-lite",
        model_rerank: str = "rerank-2.5",
    ):
        """Initialize Voyage service.

        Args:
            api_key: Voyage AI API key
            model_docs: Model for document embeddings (indexed once)
            model_queries: Model for query embeddings (used continuously)
            model_rerank: Model for reranking (32K context with rerank-2.5)

        Asymmetric Retrieval:
            Documents are embedded with voyage-4-large (high quality, one-time cost).
            Queries are embedded with voyage-4-lite (fast, cheap, continuous).
            Shared embedding space makes this possible.
        """
        self._client = voyageai.Client(api_key=api_key)
        self._model_docs = model_docs
        self._model_queries = model_queries
        self._model_rerank = model_rerank
        logger.info(
            f"VoyageService initialized: docs={model_docs}, "
            f"queries={model_queries}, rerank={model_rerank}"
        )

    @retry(
        retry=retry_if_exception_type(
            (
                voyageai.error.RateLimitError,
                voyageai.error.ServiceUnavailableError,
                voyageai.error.Timeout,
            )
        ),
        wait=wait_random_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(6),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    async def embed_documents(
        self,
        texts: list[str],
        input_type: str = "document",
    ) -> list[list[float]]:
        """Generate embeddings for documents with automatic batching.

        Uses voyage-4-large by default for maximum quality.
        Documents are typically indexed once, so quality matters more than speed.

        Args:
            texts: List of document texts to embed
            input_type: Voyage input type ("document" or "query")

        Returns:
            List of embedding vectors (1024-dim for voyage-4-large)
        """
        if not texts:
            return []

        all_embeddings = []

        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i : i + self.BATCH_SIZE]

            # asyncio.to_thread for non-blocking async (best practice)
            response = await asyncio.to_thread(
                self._client.embed,
                texts=batch,
                model=self._model_docs,
                input_type=input_type,
            )
            all_embeddings.extend(response.embeddings)

        logger.info(f"Embedded {len(all_embeddings)} documents with {self._model_docs}")
        return all_embeddings

    @retry(
        retry=retry_if_exception_type(
            (
                voyageai.error.RateLimitError,
                voyageai.error.ServiceUnavailableError,
                voyageai.error.Timeout,
            )
        ),
        wait=wait_random_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(6),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    async def embed_query(self, text: str) -> list[float]:
        """Generate embedding for a single query.

        Uses voyage-4-lite by default for fast, cheap embeddings.
        Queries are processed continuously, so speed matters.

        Asymmetric retrieval: voyage-4-lite queries can search
        voyage-4-large document index (shared embedding space).

        Args:
            text: Query text to embed

        Returns:
            Single embedding vector
        """
        response = await asyncio.to_thread(
            self._client.embed,
            texts=[text],
            model=self._model_queries,
            input_type="query",
        )
        return response.embeddings[0]

    @retry(
        retry=retry_if_exception_type(
            (
                voyageai.error.RateLimitError,
                voyageai.error.ServiceUnavailableError,
            )
        ),
        wait=wait_random_exponential(multiplier=1, max=10),
        stop=stop_after_attempt(3),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int | None = None,
    ) -> list[dict]:
        """Rerank documents by relevance to query.

        Uses rerank-2.5 by default (32K context window).

        Args:
            query: Search query
            documents: List of document texts to rerank
            top_k: Number of top results to return (None = all)

        Returns:
            List of dicts with 'index', 'relevance_score', 'document' keys,
            sorted by relevance (highest first).
        """
        if not documents:
            return []

        response = await asyncio.to_thread(
            self._client.rerank,
            query=query,
            documents=documents,
            model=self._model_rerank,
            top_k=top_k,
        )

        return [
            {
                "index": r.index,
                "relevance_score": r.relevance_score,
                "document": r.document,
            }
            for r in response.results
        ]

    # Matryoshka embeddings (variable dimensions)

    @retry(
        retry=retry_if_exception_type(
            (
                voyageai.error.RateLimitError,
                voyageai.error.ServiceUnavailableError,
                voyageai.error.Timeout,
            )
        ),
        wait=wait_random_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(6),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    async def embed_documents_matryoshka(
        self,
        texts: list[str],
        output_dimension: int = 1024,
        input_type: str = "document",
    ) -> list[list[float]]:
        """Generate Matryoshka embeddings with reduced dimensions.

        Voyage-4 supports Matryoshka embeddings that can be truncated
        to smaller dimensions while preserving semantic quality.

        Trade-offs:
            - 2048 dim: 100% quality, 100% storage
            - 1024 dim: ~98% quality, 50% storage (default)
            - 512 dim: ~95% quality, 25% storage
            - 256 dim: ~90% quality, 12.5% storage

        Args:
            texts: List of document texts to embed
            output_dimension: Target dimension (2048, 1024, 512, or 256)
            input_type: Voyage input type ("document" or "query")

        Returns:
            List of embedding vectors with specified dimension

        Raises:
            ValueError: If output_dimension is not supported
        """
        if output_dimension not in self.MATRYOSHKA_DIMS:
            raise ValueError(
                f"Invalid output_dimension {output_dimension}. Supported: {self.MATRYOSHKA_DIMS}"
            )

        if not texts:
            return []

        all_embeddings = []

        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i : i + self.BATCH_SIZE]

            response = await asyncio.to_thread(
                self._client.embed,
                texts=batch,
                model=self._model_docs,
                input_type=input_type,
                output_dimension=output_dimension,
            )
            all_embeddings.extend(response.embeddings)

        logger.info(
            f"Embedded {len(all_embeddings)} documents with {self._model_docs} "
            f"(dim={output_dimension})"
        )
        return all_embeddings

    @retry(
        retry=retry_if_exception_type(
            (
                voyageai.error.RateLimitError,
                voyageai.error.ServiceUnavailableError,
                voyageai.error.Timeout,
            )
        ),
        wait=wait_random_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(6),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    async def embed_query_matryoshka(
        self,
        text: str,
        output_dimension: int = 1024,
    ) -> list[float]:
        """Generate Matryoshka embedding for a query with reduced dimensions.

        Must use the same output_dimension as the indexed documents!

        Args:
            text: Query text to embed
            output_dimension: Target dimension (must match document index)

        Returns:
            Single embedding vector with specified dimension

        Raises:
            ValueError: If output_dimension is not supported
        """
        if output_dimension not in self.MATRYOSHKA_DIMS:
            raise ValueError(
                f"Invalid output_dimension {output_dimension}. Supported: {self.MATRYOSHKA_DIMS}"
            )

        response = await asyncio.to_thread(
            self._client.embed,
            texts=[text],
            model=self._model_queries,
            input_type="query",
            output_dimension=output_dimension,
        )
        return response.embeddings[0]

    # Sync methods for compatibility with existing code
    def embed_documents_sync(
        self,
        texts: list[str],
        input_type: str = "document",
    ) -> list[list[float]]:
        """Sync wrapper for embed_documents."""
        return asyncio.run(self.embed_documents(texts, input_type))

    def embed_query_sync(self, text: str) -> list[float]:
        """Sync wrapper for embed_query."""
        return asyncio.run(self.embed_query(text))

    def rerank_sync(
        self,
        query: str,
        documents: list[str],
        top_k: int | None = None,
    ) -> list[dict]:
        """Sync wrapper for rerank."""
        return asyncio.run(self.rerank(query, documents, top_k))

    def embed_documents_matryoshka_sync(
        self,
        texts: list[str],
        output_dimension: int = 1024,
        input_type: str = "document",
    ) -> list[list[float]]:
        """Sync wrapper for embed_documents_matryoshka."""
        return asyncio.run(self.embed_documents_matryoshka(texts, output_dimension, input_type))

    def embed_query_matryoshka_sync(
        self,
        text: str,
        output_dimension: int = 1024,
    ) -> list[float]:
        """Sync wrapper for embed_query_matryoshka."""
        return asyncio.run(self.embed_query_matryoshka(text, output_dimension))
