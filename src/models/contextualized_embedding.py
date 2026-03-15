"""Voyage AI contextualized embeddings service (voyage-context-3).

Contextualized embeddings capture document structure by processing all chunks
from a document together, allowing each chunk's embedding to incorporate context
from surrounding chunks.

Key API constraints (2026):
- inputs: List of lists, where each inner list is chunks from ONE document
- Max 32K tokens per document
- Max 120K total tokens per request
- Max 16K chunks total
- Max 1000 inputs (documents) per request
- Chunks should NOT overlap (unlike standard chunking)

Reference: Voyage AI Contextualized Chunk Embeddings documentation
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal

import voyageai
from langfuse import get_client, observe
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)


logger = logging.getLogger(__name__)


@dataclass
class ContextualizedEmbeddingResult:
    """Result from contextualized embedding call.

    Attributes:
        embeddings: List of embedding vectors (one per chunk across all documents)
        total_tokens: Total tokens processed
        chunks_per_document: Number of chunks per input document
    """

    embeddings: list[list[float]]
    total_tokens: int
    chunks_per_document: list[int]


class ContextualizedEmbeddingService:
    """Voyage AI contextualized embeddings using voyage-context-3.

    Unlike standard embeddings, contextualized embeddings process chunks together
    to capture document structure. Each chunk's embedding incorporates context
    from surrounding chunks in the same document.

    Example:
        >>> service = ContextualizedEmbeddingService(api_key="...")
        >>> # Document with 3 chunks
        >>> doc_chunks = [["intro", "body", "conclusion"]]
        >>> result = await service.embed_documents(doc_chunks)
        >>> # result.embeddings has 3 vectors, one per chunk

    Best practices:
        - Chunks should NOT overlap (different from standard RAG chunking)
        - Group all chunks from same document together
        - Keep documents under 32K tokens
    """

    # Model name for contextualized embeddings
    MODEL_NAME = "voyage-context-3"

    # API limits
    MAX_DOCUMENTS_PER_REQUEST = 1000
    MAX_CHUNKS_PER_REQUEST = 16000
    MAX_TOKENS_PER_DOCUMENT = 32000
    MAX_TOTAL_TOKENS = 120000

    # Supported output dimensions (Matryoshka)
    SUPPORTED_DIMS = (2048, 1024, 512, 256)
    DEFAULT_DIM = 1024

    def __init__(
        self,
        api_key: str,
        output_dimension: int = 1024,
        output_dtype: Literal["float", "int8", "uint8", "binary", "ubinary"] = "float",
    ):
        """Initialize contextualized embedding service.

        Args:
            api_key: Voyage AI API key
            output_dimension: Embedding dimension (2048, 1024, 512, or 256)
            output_dtype: Output data type (float, int8, uint8, binary, ubinary)

        Raises:
            ValueError: If output_dimension is not supported
        """
        if output_dimension not in self.SUPPORTED_DIMS:
            raise ValueError(
                f"Invalid output_dimension {output_dimension}. Supported: {self.SUPPORTED_DIMS}"
            )

        self._client = voyageai.Client(api_key=api_key)
        self._output_dimension = output_dimension
        self._output_dtype = output_dtype

        logger.info(
            f"ContextualizedEmbeddingService initialized: "
            f"model={self.MODEL_NAME}, dim={output_dimension}, dtype={output_dtype}"
        )

    @property
    def output_dimension(self) -> int:
        """Get configured output dimension."""
        return self._output_dimension

    @observe(name="voyage-contextualized-embed-documents", as_type="generation")
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
        document_chunks: list[list[str]],
    ) -> ContextualizedEmbeddingResult:
        """Generate contextualized embeddings for document chunks.

        Each inner list should contain all chunks from a single document.
        Chunks are embedded together so each chunk's vector captures
        its position and context within the document.

        Args:
            document_chunks: List of documents, each document is a list of chunks.
                Example: [["doc1 chunk1", "doc1 chunk2"], ["doc2 chunk1"]]

        Returns:
            ContextualizedEmbeddingResult with embeddings for all chunks

        Raises:
            ValueError: If input exceeds API limits
        """
        # Validate inputs
        self._validate_inputs(document_chunks)

        # Update Langfuse with input metadata
        total_chunks = sum(len(doc) for doc in document_chunks)
        get_client().update_current_generation(
            model=self.MODEL_NAME,
            input={
                "documents_count": len(document_chunks),
                "total_chunks": total_chunks,
                "output_dimension": self._output_dimension,
            },
        )

        if not document_chunks:
            return ContextualizedEmbeddingResult(
                embeddings=[], total_tokens=0, chunks_per_document=[]
            )

        # Call Voyage API
        response = await asyncio.to_thread(
            self._client.contextualized_embed,
            inputs=document_chunks,
            model=self.MODEL_NAME,
            input_type="document",
            output_dimension=self._output_dimension,
            output_dtype=self._output_dtype,
        )

        # Flatten embeddings from results
        all_embeddings: list[list[float]] = []
        chunks_per_doc: list[int] = []

        for result in response.results:
            all_embeddings.extend(result.embeddings)  # type: ignore[arg-type]
            chunks_per_doc.append(len(result.embeddings))

        # Get token usage
        total_tokens = getattr(response, "total_tokens", 0)

        # Update Langfuse with output metadata
        get_client().update_current_generation(
            usage_details={"input": total_tokens},
            output={
                "embeddings_count": len(all_embeddings),
                "dimensions": self._output_dimension,
            },
        )

        logger.info(
            f"Contextualized {len(document_chunks)} documents ({total_chunks} chunks) "
            f"with {self.MODEL_NAME}"
        )

        return ContextualizedEmbeddingResult(
            embeddings=all_embeddings,
            total_tokens=total_tokens,
            chunks_per_document=chunks_per_doc,
        )

    @observe(name="voyage-contextualized-embed-query", as_type="generation")
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
    async def embed_query(self, query: str) -> list[float]:
        """Generate contextualized embedding for a query.

        For queries, we pass a single-element list to maintain API consistency.

        Args:
            query: Query text to embed

        Returns:
            Single embedding vector
        """
        # Update Langfuse with input metadata
        get_client().update_current_generation(
            model=self.MODEL_NAME,
            input={"query": query[:200], "output_dimension": self._output_dimension},
        )

        # Wrap query in expected format: [[query]]
        response = await asyncio.to_thread(
            self._client.contextualized_embed,
            inputs=[[query]],
            model=self.MODEL_NAME,
            input_type="query",
            output_dimension=self._output_dimension,
            output_dtype=self._output_dtype,
        )

        embedding: list[float] = response.results[0].embeddings[0]  # type: ignore[assignment]
        total_tokens = getattr(response, "total_tokens", 0)

        # Update Langfuse with output metadata
        get_client().update_current_generation(
            usage_details={"input": total_tokens},
            output={"dimensions": len(embedding)},
        )

        return embedding

    @observe(name="voyage-contextualized-embed-queries", as_type="generation")
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
    async def embed_queries(self, queries: list[str]) -> list[list[float]]:
        """Generate contextualized embeddings for multiple queries.

        Each query is treated as a separate "document" with one chunk.

        Args:
            queries: List of query texts to embed

        Returns:
            List of embedding vectors (one per query)
        """
        # Validate inputs
        if not queries:
            return []

        # Update Langfuse with input metadata
        get_client().update_current_generation(
            model=self.MODEL_NAME,
            input={
                "queries_count": len(queries),
                "output_dimension": self._output_dimension,
            },
        )

        # Wrap each query in its own list: [["q1"], ["q2"], ...]
        inputs = [[q] for q in queries]

        response = await asyncio.to_thread(
            self._client.contextualized_embed,
            inputs=inputs,
            model=self.MODEL_NAME,
            input_type="query",
            output_dimension=self._output_dimension,
            output_dtype=self._output_dtype,
        )

        embeddings: list[list[float]] = [
            [float(value) for value in result.embeddings[0]]
            for result in response.results  # type: ignore[misc]
        ]
        total_tokens = getattr(response, "total_tokens", 0)

        # Update Langfuse with output metadata
        get_client().update_current_generation(
            usage_details={"input": total_tokens},
            output={
                "embeddings_count": len(embeddings),
                "dimensions": self._output_dimension,
            },
        )

        logger.info(f"Embedded {len(queries)} queries with {self.MODEL_NAME}")

        return embeddings

    def _validate_inputs(
        self,
        document_chunks: list[list[str]],
    ) -> None:
        """Validate inputs against API limits.

        Args:
            document_chunks: Input documents with chunks

        Raises:
            ValueError: If inputs exceed API limits
        """
        if len(document_chunks) > self.MAX_DOCUMENTS_PER_REQUEST:
            raise ValueError(
                f"Too many documents: {len(document_chunks)} > {self.MAX_DOCUMENTS_PER_REQUEST}"
            )

        total_chunks = sum(len(doc) for doc in document_chunks)
        if total_chunks > self.MAX_CHUNKS_PER_REQUEST:
            raise ValueError(f"Too many chunks: {total_chunks} > {self.MAX_CHUNKS_PER_REQUEST}")

    # Sync wrappers for compatibility

    def embed_documents_sync(
        self,
        document_chunks: list[list[str]],
    ) -> ContextualizedEmbeddingResult:
        """Sync wrapper for embed_documents."""
        return asyncio.run(self.embed_documents(document_chunks))

    def embed_query_sync(self, query: str) -> list[float]:
        """Sync wrapper for embed_query."""
        return asyncio.run(self.embed_query(query))

    def embed_queries_sync(self, queries: list[str]) -> list[list[float]]:
        """Sync wrapper for embed_queries."""
        return asyncio.run(self.embed_queries(queries))
