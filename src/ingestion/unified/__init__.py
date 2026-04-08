"""Unified ingestion pipeline package."""

from typing import Any

from src._compat import load_deprecated_package_export


_DEPRECATED_EXPORTS = {
    "FileState": (
        "src.ingestion.unified.state_manager",
        "FileState",
        "from src.ingestion.unified.state_manager import FileState",
    ),
    "QdrantHybridWriter": (
        "src.ingestion.unified.qdrant_writer",
        "QdrantHybridWriter",
        "from src.ingestion.unified.qdrant_writer import QdrantHybridWriter",
    ),
    "UnifiedConfig": (
        "src.ingestion.unified.config",
        "UnifiedConfig",
        "from src.ingestion.unified.config import UnifiedConfig",
    ),
    "UnifiedStateManager": (
        "src.ingestion.unified.state_manager",
        "UnifiedStateManager",
        "from src.ingestion.unified.state_manager import UnifiedStateManager",
    ),
    "WriteStats": (
        "src.ingestion.unified.qdrant_writer",
        "WriteStats",
        "from src.ingestion.unified.qdrant_writer import WriteStats",
    ),
}


def __getattr__(name: str) -> Any:
    """Resolve deprecated package exports lazily."""
    target = _DEPRECATED_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module 'src.ingestion.unified' has no attribute '{name}'")
    value = load_deprecated_package_export(module_name=__name__, attr_name=name, target=target)
    globals()[name] = value
    return value
