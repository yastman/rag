# src/services/vectorizers.py
"""Semantic-cache vectorizer — official RedisVL CustomVectorizer factory (#3389).

The historical ``BgeM3CacheVectorizer`` (a custom ``BaseVectorizer`` subclass)
was replaced after characterization by the documented ``CustomVectorizer``:
the characterized contract is preserved (1024-dim / float32 index schema
inputs, async one/batch embedding via ``BGEM3Client`` with a lazily created,
reused client, and no BGE calls at construction).

The sync ``embed``/``embed_many`` surface is intentionally different from the
archived subclass: ``CustomVectorizer`` construction validates dims through
the sync callable, so it is satisfied by a local zero-vector probe that never
contacts BGE. Production never calls the sync surface — ``check_semantic`` /
``store_semantic`` always pass ``vector=`` explicitly.

UserBaseVectorizer (deepvk/USER2-base) has been archived to
archive/user-base/ (#2627). BGE-M3 is the canonical embedding provider.
"""

from typing import Any, cast

from redisvl.utils.vectorize import CustomVectorizer


BGE_M3_CACHE_DIMS = 1024
DEFAULT_BGE_M3_URL = "http://bge-m3:8000"
DEFAULT_BGE_M3_TIMEOUT = 30.0


def create_bge_m3_cache_vectorizer(
    base_url: str = DEFAULT_BGE_M3_URL,
    timeout: float = DEFAULT_BGE_M3_TIMEOUT,
) -> CustomVectorizer:
    """Build the official RedisVL ``CustomVectorizer`` for the semantic cache.

    The BGEM3Client is created lazily on the first real embed call and reused
    afterwards, so cache initialization performs no BGE I/O.
    """
    holder: list[Any] = []

    def _get_bge_client() -> Any:
        if not holder:
            from src.services.bge_m3_client import BGEM3Client

            holder.append(BGEM3Client(base_url=base_url, timeout=timeout))
        return holder[0]

    def _dims_probe(_content: Any) -> list[float]:
        """Local, BGE-free probe satisfying CustomVectorizer dims validation."""
        return [0.0] * BGE_M3_CACHE_DIMS

    async def _aembed(content: Any) -> list[float]:
        result = await _get_bge_client().encode_dense([content])
        return cast(list[float], result.vectors[0])

    async def _aembed_many(contents: list[Any]) -> list[list[float]]:
        result = await _get_bge_client().encode_dense(contents)
        return cast(list[list[float]], result.vectors)

    return CustomVectorizer(embed=_dims_probe, aembed=_aembed, aembed_many=_aembed_many)
