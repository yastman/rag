"""QdrantService — back-compat re-export.

The canonical implementation moved to :mod:`src.runtime.services.qdrant`
as part of the reverse-layering fix (#2047 / #2049). This module remains
so that existing ``from telegram_bot.services.qdrant import QdrantService``
imports across ``telegram_bot/``, ``tests/``, and the rest of the repo
continue to work unchanged.
"""

from src.runtime.services.qdrant import QdrantService


__all__ = ["QdrantService"]
