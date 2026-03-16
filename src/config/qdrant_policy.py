"""Shared Qdrant collection policy helpers."""

from __future__ import annotations


def resolve_collection_name(base_name: str, mode: str) -> str:
    """Return collection name with quantization suffix based on mode."""
    base = base_name
    for suffix in ("_binary", "_scalar"):
        base = base.removesuffix(suffix)

    normalized = (mode or "off").lower()
    if normalized == "scalar":
        return f"{base}_scalar"
    if normalized == "binary":
        return f"{base}_binary"
    return base
