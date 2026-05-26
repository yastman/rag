"""Unit tests for ``QdrantService._colbert_fallback_to_rrf`` (#1542 DRY fix).

Issue #1542 flagged a ColBERT->RRF fallback pattern repeated 4 times inside
``hybrid_search_rrf_colbert`` (qdrant.py). After the layering migration
(#1948 / #2049) the file moved to ``src.runtime.services.qdrant`` but the
duplication came along with it — line 631, 659, 744, 811 each contain the
same ~17-line block:

* call ``hybrid_search_rrf`` with the saved kwargs;
* unwrap the optional ``(results, meta)`` tuple;
* update the current Langfuse span with ``fallback_reason``,
  ``results_count``, ``top_score`` and the standard collection metadata.

This PR extracts the block into ``QdrantService._colbert_fallback_to_rrf``.
The 4 call sites become a single line each. The test below pins:

* the helper forwards every search kwarg to ``hybrid_search_rrf`` unchanged;
* the helper unwraps both ``return_meta`` shapes (list and ``(list, meta)``);
* the span output payload contains the expected ``fallback_reason``,
  ``results_count`` and ``top_score`` fields, plus the standard collection
  metadata;
* the helper returns ``(raw_fallback, flat_results)`` so the caller can
  preserve its return shape AND inspect the flat list (the existing
  ``colbert_empty`` post-hook needs that to disable ColBERT).

We avoid touching the integration tests around ``hybrid_search_rrf_colbert``
itself (those are covered by ``tests/integration/test_colbert_backfill.py``
and ``tests/unit/agents/test_rag_pipeline.py``) — this file targets the
extracted seam only.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.runtime.services.qdrant import QdrantService


def _make_service() -> QdrantService:
    """Build a service shell with just the attributes the helper reads."""
    service = QdrantService.__new__(QdrantService)
    service._collection_name = "unit-collection"
    service._quantization_mode = "binary"
    return service


@pytest.mark.asyncio
async def test_colbert_fallback_forwards_search_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _make_service()
    expected_results = [{"id": "doc-1", "score": 0.91, "text": "hit"}]
    service.hybrid_search_rrf = AsyncMock(return_value=expected_results)
    fake_lf = MagicMock()
    monkeypatch.setattr(
        "src.runtime.services.qdrant.get_client",
        lambda: fake_lf,
    )

    fallback, flat = await service._colbert_fallback_to_rrf(
        dense_vector=[0.1, 0.2],
        sparse_vector={"indices": [1], "values": [0.5]},
        filters={"city": "Tashkent"},
        top_k=7,
        dense_weight=0.5,
        sparse_weight=0.5,
        rrf_k=60,
        return_meta=False,
        fallback_reason="colbert_unavailable",
    )

    service.hybrid_search_rrf.assert_awaited_once_with(
        dense_vector=[0.1, 0.2],
        sparse_vector={"indices": [1], "values": [0.5]},
        filters={"city": "Tashkent"},
        top_k=7,
        dense_weight=0.5,
        sparse_weight=0.5,
        rrf_k=60,
        return_meta=False,
    )
    assert fallback is expected_results
    assert flat is expected_results


@pytest.mark.asyncio
async def test_colbert_fallback_unwraps_return_meta_tuple(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _make_service()
    flat_results = [{"id": "doc-1", "score": 0.5}]
    raw_meta = {"backend_error": False}
    service.hybrid_search_rrf = AsyncMock(return_value=(flat_results, raw_meta))
    monkeypatch.setattr(
        "src.runtime.services.qdrant.get_client",
        lambda: MagicMock(),
    )

    fallback, flat = await service._colbert_fallback_to_rrf(
        dense_vector=[0.0],
        sparse_vector=None,
        filters=None,
        top_k=5,
        dense_weight=0.6,
        sparse_weight=0.4,
        rrf_k=60,
        return_meta=True,
        fallback_reason="empty_colbert_query",
    )

    assert fallback == (flat_results, raw_meta)
    assert flat is flat_results


@pytest.mark.asyncio
async def test_colbert_fallback_emits_canonical_span_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _make_service()
    flat_results = [{"id": "a", "score": 0.7}, {"id": "b", "score": 0.3}]
    service.hybrid_search_rrf = AsyncMock(return_value=flat_results)
    fake_lf = MagicMock()
    monkeypatch.setattr(
        "src.runtime.services.qdrant.get_client",
        lambda: fake_lf,
    )

    await service._colbert_fallback_to_rrf(
        dense_vector=[],
        sparse_vector=None,
        filters=None,
        top_k=5,
        dense_weight=0.6,
        sparse_weight=0.4,
        rrf_k=60,
        return_meta=False,
        fallback_reason="colbert_error:RuntimeError",
    )

    fake_lf.update_current_span.assert_called_once()
    payload = fake_lf.update_current_span.call_args.kwargs
    assert payload["output"] == {
        "fallback_reason": "colbert_error:RuntimeError",
        "results_count": 2,
        "top_score": 0.7,
    }
    assert payload["metadata"] == {
        "collection": "unit-collection",
        "quantization_mode": "binary",
    }


@pytest.mark.asyncio
async def test_colbert_fallback_handles_empty_results(monkeypatch: pytest.MonkeyPatch) -> None:
    """``top_score`` must be ``None`` when fallback returns no docs — the
    existing call sites all rely on this exact shape, so we pin it here.
    """
    service = _make_service()
    service.hybrid_search_rrf = AsyncMock(return_value=[])
    fake_lf = MagicMock()
    monkeypatch.setattr(
        "src.runtime.services.qdrant.get_client",
        lambda: fake_lf,
    )

    await service._colbert_fallback_to_rrf(
        dense_vector=[],
        sparse_vector=None,
        filters=None,
        top_k=5,
        dense_weight=0.6,
        sparse_weight=0.4,
        rrf_k=60,
        return_meta=False,
        fallback_reason="colbert_empty",
    )

    payload = fake_lf.update_current_span.call_args.kwargs
    assert payload["output"]["results_count"] == 0
    assert payload["output"]["top_score"] is None


def test_colbert_fallback_pattern_is_extracted_from_inline_callsites() -> None:
    """Source-level guard: the four inline 'fallback = await self.hybrid_search_rrf(...)
    + unwrap + update_current_span(output={fallback_reason: "<literal>"})' blocks inside
    ``hybrid_search_rrf_colbert`` must collapse after the extraction.

    The check counts span outputs whose ``fallback_reason`` is a non-None
    string literal — those are exactly the four fallback emit sites the
    helper now owns. The success path (which emits
    ``"fallback_reason": None`` after a non-empty ColBERT result) and any
    f-string variant inside the helper itself are intentionally not
    flagged.

    Allows future re-introduction (e.g., a 5th distinct fallback path)
    without forbidding the helper itself, but flags any silent regression.
    """
    import inspect
    import re

    from src.runtime.services import qdrant as qdrant_module

    source = inspect.getsource(qdrant_module)

    # Match an inline span emit pattern with a string literal fallback_reason
    # (single or double quoted), but NOT ``None``. The helper's own emit uses
    # the parameter name (``"fallback_reason": fallback_reason``) which does
    # not match the literal pattern.
    inline_string_literal_emits = re.findall(
        r'"fallback_reason":\s*[\'"][^\'\"]+[\'"]',
        source,
    )
    assert len(inline_string_literal_emits) == 0, (
        f"Found {len(inline_string_literal_emits)} inline ColBERT fallback "
        f"span emit(s) with a string-literal fallback_reason. Route those "
        f"through _colbert_fallback_to_rrf(...,fallback_reason='<reason>') "
        f"instead. Offending matches: {inline_string_literal_emits!r}"
    )
