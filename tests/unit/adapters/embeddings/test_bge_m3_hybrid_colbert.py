"""Q2: BGE-M3 hybrid/colbert provider — mock-tier tests.

Tests that BgeM3EmbeddingProvider.aembed_hybrid_with_colbert either uses the
colbert_vecs already returned by encode_hybrid (no extra encode_colbert call)
or falls back to encode_colbert when colbert_vecs is absent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from src.adapters.embeddings.bge_m3 import BgeM3EmbeddingProvider


_DENSE = [[0.1] * 1024]
_SPARSE = [{"indices": [1, 2, 3], "values": [0.5, 0.3, 0.2]}]
_COLBERT = [[[0.1] * 128, [0.2] * 128]]  # 2 token vectors


@dataclass
class _FakeHybridResult:
    dense_vecs: list[list[float]]
    lexical_weights: list[dict[str, Any]]
    colbert_vecs: list[list[list[float]]] | None = None
    processing_time: float | None = None


@dataclass
class _FakeColbertResult:
    colbert_vecs: list[list[list[float]]] = field(default_factory=list)
    processing_time: float | None = None


def _make_provider() -> tuple[BgeM3EmbeddingProvider, MagicMock]:
    """Build a provider with a fake BGEM3Client injected."""
    fake_client = MagicMock()
    provider = BgeM3EmbeddingProvider(client=fake_client)
    return provider, fake_client


class TestBgeM3HybridColbert:
    """Tests for aembed_hybrid_with_colbert branch selection."""

    async def test_colbert_vecs_present_skips_encode_colbert(self):
        """When encode_hybrid returns colbert_vecs, encode_colbert is NOT called."""
        provider, client = _make_provider()
        client.encode_hybrid = AsyncMock(
            return_value=_FakeHybridResult(
                dense_vecs=_DENSE,
                lexical_weights=_SPARSE,
                colbert_vecs=_COLBERT,
            )
        )
        client.encode_colbert = AsyncMock()

        dense, sparse, colbert = await provider.aembed_hybrid_with_colbert("test query")

        client.encode_hybrid.assert_awaited_once_with(["test query"])
        client.encode_colbert.assert_not_awaited()

        assert dense == _DENSE[0]
        assert sparse == _SPARSE[0]
        assert colbert == _COLBERT[0]

    async def test_colbert_vecs_none_calls_encode_colbert_once(self):
        """When encode_hybrid returns colbert_vecs=None, encode_colbert IS called exactly once."""
        provider, client = _make_provider()
        fallback_colbert = [[[0.3] * 128]]
        client.encode_hybrid = AsyncMock(
            return_value=_FakeHybridResult(
                dense_vecs=_DENSE,
                lexical_weights=_SPARSE,
                colbert_vecs=None,  # absent → must call encode_colbert
            )
        )
        client.encode_colbert = AsyncMock(
            return_value=_FakeColbertResult(colbert_vecs=fallback_colbert)
        )

        dense, sparse, colbert = await provider.aembed_hybrid_with_colbert("another query")

        client.encode_hybrid.assert_awaited_once_with(["another query"])
        client.encode_colbert.assert_awaited_once_with(["another query"])

        assert dense == _DENSE[0]
        assert sparse == _SPARSE[0]
        assert colbert == fallback_colbert[0]

    async def test_colbert_vecs_empty_list_calls_encode_colbert_once(self):
        """When encode_hybrid returns colbert_vecs=[], encode_colbert IS called exactly once.

        An empty list is falsy in Python, so the condition ``if result.colbert_vecs``
        is False and the fallback branch is taken.
        """
        provider, client = _make_provider()
        fallback_colbert = [[[0.4] * 128]]
        client.encode_hybrid = AsyncMock(
            return_value=_FakeHybridResult(
                dense_vecs=_DENSE,
                lexical_weights=_SPARSE,
                colbert_vecs=[],  # empty list → falsy → fallback
            )
        )
        client.encode_colbert = AsyncMock(
            return_value=_FakeColbertResult(colbert_vecs=fallback_colbert)
        )

        _dense, _sparse, colbert = await provider.aembed_hybrid_with_colbert("q")

        client.encode_colbert.assert_awaited_once()
        assert colbert == fallback_colbert[0]

    async def test_colbert_vecs_present_returns_correct_slice(self):
        """Returns colbert_vecs[0] (the first text's vectors) when present."""
        two_docs_colbert = [[[0.1] * 128], [[0.9] * 128]]
        provider, client = _make_provider()
        client.encode_hybrid = AsyncMock(
            return_value=_FakeHybridResult(
                dense_vecs=[_DENSE[0], [0.2] * 1024],
                lexical_weights=[_SPARSE[0], {"indices": [5], "values": [0.7]}],
                colbert_vecs=two_docs_colbert,
            )
        )
        client.encode_colbert = AsyncMock()

        _dense, _sparse, colbert = await provider.aembed_hybrid_with_colbert("q")

        # Must return colbert_vecs[0], not the full list
        assert colbert == two_docs_colbert[0]
        client.encode_colbert.assert_not_awaited()
