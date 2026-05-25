"""QdrantService — back-compat module alias.

The canonical implementation moved to :mod:`src.runtime.services.qdrant`
as part of the reverse-layering fix (#2047 / #2049). Keep the legacy module
path as an alias so existing imports and tests that patch module globals such
as ``AsyncQdrantClient`` continue to affect the canonical implementation.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from src.runtime.services import qdrant as _runtime_qdrant


if TYPE_CHECKING:
    from qdrant_client import AsyncQdrantClient  # noqa: F401

    from src.observability import get_client  # noqa: F401
    from src.runtime.services.qdrant import QdrantService

    __all__ = ["QdrantService"]
else:
    _runtime_qdrant.__all__ = ["QdrantService"]  # type: ignore[attr-defined]
    sys.modules[__name__] = _runtime_qdrant
