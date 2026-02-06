# src/ingestion/unified/__init__.py
"""Unified ingestion pipeline package."""

from importlib import import_module
from typing import TYPE_CHECKING, Any


__all__ = [
    "FileState",
    "QdrantHybridWriter",
    "UnifiedConfig",
    "UnifiedStateManager",
    "WriteStats",
]


if TYPE_CHECKING:
    from src.ingestion.unified.config import UnifiedConfig
    from src.ingestion.unified.qdrant_writer import QdrantHybridWriter, WriteStats
    from src.ingestion.unified.state_manager import FileState, UnifiedStateManager


_LAZY_ATTRS = {
    "UnifiedConfig": ("src.ingestion.unified.config", "UnifiedConfig"),
    "QdrantHybridWriter": ("src.ingestion.unified.qdrant_writer", "QdrantHybridWriter"),
    "WriteStats": ("src.ingestion.unified.qdrant_writer", "WriteStats"),
    "FileState": ("src.ingestion.unified.state_manager", "FileState"),
    "UnifiedStateManager": ("src.ingestion.unified.state_manager", "UnifiedStateManager"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY_ATTRS.get(name)
    if target is None:
        raise AttributeError(f"module 'src.ingestion.unified' has no attribute '{name}'")
    module_name, attr_name = target
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
