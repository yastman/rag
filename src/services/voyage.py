"""Unified Voyage AI service for embeddings and reranking.

Smart Gateway pattern - single entry point for all Voyage AI operations.
Validated by: Voyage AI official documentation (January 2026)

Instrumented with Langfuse @observe for LLM observability (2026-01-28).
"""

import asyncio
import logging
from typing import cast

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

from src.observability import get_client, observe


logger = logging.getLogger(__name__)


def _create_voyage_client(api_key: str):
    """Create a Voyage client only when the optional voyage extra is installed."""
    try:
        import voyageai
    except ImportError as exc:
        raise RuntimeError(
            "voyageai is required for VoyageService. "
            "Install it with `uv sync --extra voyage` or package extra "
            "`rag-telegram-bot[voyage]`."
        ) from exc
    return voyageai.Client(api_key=api_key)


def _get_voyage_errors():
    """Lazily import and return voyageai error types for retry predicates."""
    import voyageai

    return (
        voyageai.error.RateLimitError,
        voyageai.error.ServiceUnavailableError,
        voyageai.error.Timeout,
    )


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
        self._client = _create_voyage_client(api_key)
        self._model_docs = model_docs
        self._model_queries = model_queries
        self._model_rerank = model_rerank
        logger.info(
            f"VoyageService initialized: docs={model_docs}, "
            f"queries={model_queries}, rerank={model_rerank}"
        )

    @observe(name="voyage-embed-documents", as_type="generation")
    @retry(
        retry=retry_if_exception(lambda exc: isinstance(exc, _get_voyage_errors())),
        wait=wait_random_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(6),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    async def embed_documents(
        self,
        texts: list[str],
        input_type: str = "document",
    ) -> list[list[float]]:
        """Generate embeddings for documents with automatic batching."""
        get_client().update_current_generation(
            model=self._model_docs,
            input={"count": len(texts), "input_type": input_type},
        )

        if not texts:
            return []

        all_embeddings: list[list[float]] = []
        total_tokens = 0

        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i : i + self.BATCH_SIZE]
            response = await asyncio.to_thread(
                self._client.embed,
                texts=batch,
                model=self._model_docs,
                input_type=input_type,
            )
            all_embeddings.extend(cast(list[list[float]], response.embeddings))
            if hasattr(response, "usage") and response.usage:
                total_tokens += getattr(response.usage, "total_tokens", 0)

        get_client().update_current_generation(
            usage_details={"input": total_tokens},
            output={
                "count": len(all_embeddings),
                "dimensions": len(all_embeddings[0]) if all_embeddings else 0,
            },
        )

        logger.info(f"Embedded {len(all_embeddings)} documents with {self._model_docs}")
        return all_embeddings

    @observe(name="voyage-embed-query", as_type="generation")
    @retry(
        retry=retry_if_exception(lambda exc: isinstance(exc, _get_voyage_errors())),
        wait=wait_random_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(6),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    async def embed_query(self, text: str) -> list[float]:
        """Generate embedding for a single query."""
        get_client().update_current_generation(
            model=self._model_queries,
            input={"text": text[:200]},
        )

        response = await asyncio.to_thread(
            self._client.embed,
            texts=[text],
            model=self._model_queries,
            input_type="query",
        )

        total_tokens = 0
        if hasattr(response, "usage") and response.usage:
            total_tokens = getattr(response.usage, "total_tokens", 0)

        get_client().update_current_generation(
            usage_details={"input": total_tokens},
            output={"dimensions": len(response.embeddings[0])},
        )

        return cast(list[float], response.embeddings[0])

    @observe(name="voyage-rerank", as_type="generation")
    @retry(
        retry=retry_if_exception(lambda exc: isinstance(exc, _get_voyage_errors())),
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
        """Rerank documents by relevance to query."""
        get_client().update_current_generation(
            model=self._model_rerank,
            input={"query": query[:200], "documents_count": len(documents), "top_k": top_k},
        )

        if not documents:
            return []

        response = await asyncio.to_thread(
            self._client.rerank,
            query=query,
            documents=documents,
            model=self._model_rerank,
            top_k=top_k,
        )

        results = [
            {
                "index": r.index,
                "relevance_score": r.relevance_score,
                "document": r.document,
            }
            for r in response.results
        ]

        get_client().update_current_generation(
            output={
                "results_count": len(results),
                "top_score": results[0]["relevance_score"] if results else 0,
            },
        )

        return results

    @observe(name="voyage-embed-documents-matryoshka", as_type="generation")
    @retry(
        retry=retry_if_exception(lambda exc: isinstance(exc, _get_voyage_errors())),
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
        """Generate Matryoshka embeddings with reduced dimensions."""
        get_client().update_current_generation(
            model=self._model_docs,
            input={
                "count": len(texts),
                "output_dimension": output_dimension,
                "input_type": input_type,
            },
        )

        if output_dimension not in self.MATRYOSHKA_DIMS:
            raise ValueError(
                f"Invalid output_dimension {output_dimension}. Supported: {self.MATRYOSHKA_DIMS}"
            )

        if not texts:
            return []

        all_embeddings: list[list[float]] = []
        total_tokens = 0

        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i : i + self.BATCH_SIZE]
            response = await asyncio.to_thread(
                self._client.embed,
                texts=batch,
                model=self._model_docs,
                input_type=input_type,
                output_dimension=output_dimension,
            )
            all_embeddings.extend(cast(list[list[float]], response.embeddings))
            if hasattr(response, "usage") and response.usage:
                total_tokens += getattr(response.usage, "total_tokens", 0)

        get_client().update_current_generation(
            usage_details={"input": total_tokens},
            output={"count": len(all_embeddings), "dimensions": output_dimension},
        )

        logger.info(
            f"Embedded {len(all_embeddings)} documents with {self._model_docs} "
            f"(dim={output_dimension})"
        )
        return all_embeddings

    @observe(name="voyage-embed-query-matryoshka", as_type="generation")
    @retry(
        retry=retry_if_exception(lambda exc: isinstance(exc, _get_voyage_errors())),
        wait=wait_random_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(6),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    async def embed_query_matryoshka(
        self,
        text: str,
        output_dimension: int = 1024,
    ) -> list[float]:
        """Generate Matryoshka embedding for a query with reduced dimensions."""
        get_client().update_current_generation(
            model=self._model_queries,
            input={"text": text[:200], "output_dimension": output_dimension},
        )

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

        total_tokens = 0
        if hasattr(response, "usage") and response.usage:
            total_tokens = getattr(response.usage, "total_tokens", 0)

        get_client().update_current_generation(
            usage_details={"input": total_tokens},
            output={"dimensions": output_dimension},
        )

        return cast(list[float], response.embeddings[0])

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
