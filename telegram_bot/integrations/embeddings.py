"""Re-export shim — canonical home is src.runtime.integrations.embeddings (#3010)."""

from src.runtime.integrations.embeddings import (
    BGEM3Embeddings as BGEM3Embeddings,
)
from src.runtime.integrations.embeddings import (
    BGEM3HybridEmbeddings as BGEM3HybridEmbeddings,
)
from src.runtime.integrations.embeddings import (
    BGEM3SparseEmbeddings as BGEM3SparseEmbeddings,
)


__all__ = ["BGEM3Embeddings", "BGEM3HybridEmbeddings", "BGEM3SparseEmbeddings"]
