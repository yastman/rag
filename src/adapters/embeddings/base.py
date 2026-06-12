"""Base interface for embedding providers."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any


class EmbeddingProvider(ABC):
    """Abstract base class for embedding generation providers.

    This is the canonical application-facing embedding adapter surface.
    Low-level SDK clients (for example ``BGEM3Client``) should be wrapped by
    implementations of this provider rather than used directly by retrieval
    orchestration.
    """

    @abstractmethod
    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Compute dense embeddings for a list of texts.

        Args:
            texts: A sequence of texts to embed.

        Returns:
            A list of float lists, representing the dense embeddings.
        """

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """LangChain-compatible async dense document embedding alias."""
        return await self.embed_texts(texts)

    async def aembed_query(self, text: str) -> list[float]:
        """Compute one dense query embedding."""
        vectors = await self.embed_texts([text])
        return vectors[0]

    async def aembed_hybrid(self, text: str) -> tuple[list[float], dict[str, Any]]:
        """Compute dense+sparse query vectors when supported by the provider."""
        raise NotImplementedError(f"{type(self).__name__} does not provide hybrid embeddings")

    async def aembed_hybrid_with_colbert(
        self, text: str
    ) -> tuple[list[float], dict[str, Any], list[list[float]]]:
        """Compute dense+sparse+ColBERT query vectors when supported."""
        raise NotImplementedError(f"{type(self).__name__} does not provide ColBERT embeddings")

    async def aclose(self) -> None:
        """Close any open resources (no-op by default)."""
        return
