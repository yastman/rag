"""Re-export shim — canonical home is src.runtime.services.qdrant (#3010)."""

from src.runtime.services.qdrant import QdrantService as QdrantService
from src.runtime.services.qdrant import SearchReturn as SearchReturn


__all__ = ["QdrantService", "SearchReturn"]
