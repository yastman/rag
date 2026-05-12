"""BGE-M3 query vector bundle contract.

Provides a typed bundle for dense + sparse + ColBERT query vectors
returned by BGE-M3 /encode/hybrid, plus cache key material generation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


BGE_M3_QUERY_BUNDLE_MODEL = "BAAI/bge-m3"
BGE_M3_QUERY_BUNDLE_MAX_LENGTH = 512
BGE_M3_QUERY_BUNDLE_VERSION = "v1"


def _normalize_query(text: str) -> str:
    """Normalize query text for cache key generation.

    Strip whitespace, lowercase, and remove trailing punctuation so
    semantically identical queries map to the same cache key.
    """
    return re.sub(r"[^\w\s]+$", "", text.strip().lower()).strip()


@dataclass(frozen=True, slots=True)
class BgeM3QueryVectorBundle:
    """Complete BGE-M3 query vector bundle.

    All three representations are required for a *complete* bundle.
    """

    dense: list[float]
    sparse: dict[str, list[int] | list[float]]
    colbert: list[list[float]]
    model: str = BGE_M3_QUERY_BUNDLE_MODEL
    max_length: int = BGE_M3_QUERY_BUNDLE_MAX_LENGTH
    version: str = BGE_M3_QUERY_BUNDLE_VERSION

    def is_complete(self) -> bool:
        """Return True when dense, sparse, and ColBERT are all present and non-empty."""
        return (
            isinstance(self.dense, list)
            and len(self.dense) > 0
            and isinstance(self.sparse, dict)
            and "indices" in self.sparse
            and "values" in self.sparse
            and isinstance(self.sparse["indices"], list)
            and isinstance(self.sparse["values"], list)
            and len(self.sparse["indices"]) > 0
            and len(self.sparse["values"]) > 0
            and isinstance(self.colbert, list)
            and len(self.colbert) > 0
        )

    def to_json_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "dense": self.dense,
            "sparse": self.sparse,
            "colbert": self.colbert,
            "model": self.model,
            "max_length": self.max_length,
            "version": self.version,
        }

    @classmethod
    def from_json_dict(cls, data: Any) -> BgeM3QueryVectorBundle | None:
        """Parse from a JSON-compatible dict.

        Returns ``None`` for non-dicts, wrong shapes, or incomplete bundles.
        """
        if not isinstance(data, dict):
            return None
        try:
            bundle = cls(
                dense=data["dense"],
                sparse=data["sparse"],
                colbert=data["colbert"],
                model=data.get("model", BGE_M3_QUERY_BUNDLE_MODEL),
                max_length=data.get("max_length", BGE_M3_QUERY_BUNDLE_MAX_LENGTH),
                version=data.get("version", BGE_M3_QUERY_BUNDLE_VERSION),
            )
        except (KeyError, TypeError):
            return None

        if not bundle.is_complete():
            return None

        return bundle


def make_bge_m3_query_bundle_key_material(
    query: str,
    *,
    model: str = BGE_M3_QUERY_BUNDLE_MODEL,
    max_length: int = BGE_M3_QUERY_BUNDLE_MAX_LENGTH,
) -> str:
    """Build cache key material for a BGE-M3 query bundle.

    The material includes the version, model, max_length, and normalized
    query text so that semantically identical queries share the same key.
    """
    normalized = _normalize_query(query)
    return f"{BGE_M3_QUERY_BUNDLE_VERSION}:{model}:{max_length}:{normalized}"
