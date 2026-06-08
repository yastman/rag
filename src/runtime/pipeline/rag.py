"""Runtime RAG pipeline seam.

This module is the canonical runtime-facing entrypoint for RAG retrieval during
the monolith-core migration. It delegates to the legacy Telegram implementation
until CORE-005 can move the full implementation without changing retrieval
behaviour.
"""

from __future__ import annotations

import importlib
from typing import Any


async def rag_pipeline(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Run the current RAG pipeline through the runtime-owned seam."""

    legacy = importlib.import_module("telegram_bot.agents.rag_pipeline").rag_pipeline
    return await legacy(*args, **kwargs)


__all__ = ["rag_pipeline"]
