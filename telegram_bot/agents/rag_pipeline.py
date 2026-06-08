"""Compatibility shim for the runtime-owned RAG pipeline.

Deprecated: import from ``src.runtime.pipeline.rag`` in new code.
"""

from __future__ import annotations

from typing import Any

from src.runtime.pipeline.rag import rag_pipeline


def __getattr__(name: str) -> Any:
    """Forward legacy private helper imports to the runtime implementation."""

    from src.runtime.pipeline import rag as runtime_rag

    return getattr(runtime_rag, name)


__all__ = ["rag_pipeline"]
