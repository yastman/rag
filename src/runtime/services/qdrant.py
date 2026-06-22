"""Re-export façade — canonical home is src.runtime.qdrant.service (#3012).

All imports of ``QdrantService`` and ``SearchReturn`` from this module continue
to work without change. New code should import from ``src.runtime.qdrant``.
"""

from src.runtime.qdrant.service import QdrantService as QdrantService
from src.runtime.qdrant.service import SearchReturn as SearchReturn


__all__ = ["QdrantService", "SearchReturn"]
