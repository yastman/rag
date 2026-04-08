"""Configuration module for Contextual RAG Pipeline."""

from typing import Any

from src._compat import load_deprecated_package_export

from .constants import (
    AcornMode,
    APIProvider,
    HSNWParameters,
    QuantizationMode,
    RetrievalStages,
    SearchEngine,
    ThresholdValues,
    VectorDimensions,
)
from .settings import Settings


__all__ = [
    "APIProvider",
    "AcornMode",
    "HSNWParameters",
    "QuantizationMode",
    "RetrievalStages",
    "SearchEngine",
    "Settings",
    "ThresholdValues",
    "VectorDimensions",
]


_DEPRECATED_EXPORTS = {
    "SmallToBigMode": (
        "src.config.constants",
        "SmallToBigMode",
        "from src.config.constants import SmallToBigMode",
    ),
}


def __getattr__(name: str) -> Any:
    """Resolve deprecated package exports lazily."""
    target = _DEPRECATED_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module 'src.config' has no attribute '{name}'")
    value = load_deprecated_package_export(module_name=__name__, attr_name=name, target=target)
    globals()[name] = value
    return value
