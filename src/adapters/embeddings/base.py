"""Base interface for embedding providers."""

from abc import ABC, abstractmethod
from collections.abc import Sequence


class EmbeddingProvider(ABC):
    """Abstract base class for embedding generation providers."""

    @abstractmethod
    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Compute dense embeddings for a list of texts.

        Args:
            texts: A sequence of texts to embed.

        Returns:
            A list of float lists, representing the dense embeddings.
        """

    async def aclose(self) -> None:
        """Close any open resources (no-op by default)."""
        return
