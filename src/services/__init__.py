"""Shared service clients for the src/ domain layer.

Uses lazy imports to avoid loading heavy dependencies at import time.
Import specific services directly for best performance:
    from src.services.bge_m3_client import BGEM3SyncClient
    from src.services.voyage import VoyageService
"""

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from .bge_m3_client import BGEM3Client, BGEM3SyncClient
    from .voyage import VoyageService


__all__ = [
    "BGEM3Client",
    "BGEM3SyncClient",
    "VoyageService",
]

_IMPORT_MAP = {
    "BGEM3Client": ".bge_m3_client",
    "BGEM3SyncClient": ".bge_m3_client",
    "VoyageService": ".voyage",
}


def __getattr__(name: str):
    """Lazy import handler."""
    if name in _IMPORT_MAP:
        import importlib

        module = importlib.import_module(_IMPORT_MAP[name], __package__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
