"""src.runtime.qdrant — focused Qdrant gateway modules (#3012)."""

from .service import QdrantService as QdrantService
from .service import SearchReturn as SearchReturn


__all__ = ["QdrantService", "SearchReturn"]
