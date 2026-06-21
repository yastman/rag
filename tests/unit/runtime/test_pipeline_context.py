"""Tests for PipelineContext typed state container (#2946)."""

from __future__ import annotations


def test_pipeline_context_importable() -> None:
    from src.runtime.pipeline.context import PipelineContext  # noqa: F401


def test_pipeline_context_is_typeddict() -> None:
    from typing import get_type_hints

    from src.runtime.pipeline.context import PipelineContext

    hints = get_type_hints(PipelineContext)
    assert "cache_checked" in hints
    assert "dense_vector" in hints
    assert "filters" in hints
    assert "topic_hint" in hints


def test_pipeline_context_can_be_constructed() -> None:
    from src.runtime.pipeline.context import PipelineContext

    ctx: PipelineContext = {
        "cache_checked": True,
        "cache_hit": False,
        "dense_vector": [0.1] * 4,
        "filters": {"city": "Nesebar"},
    }
    assert ctx["cache_checked"] is True
    assert ctx["filters"] == {"city": "Nesebar"}


def test_rag_pipeline_accepts_pipeline_context() -> None:
    """rag_pipeline type annotation must accept PipelineContext, not dict[str, Any]."""
    import inspect

    from src.runtime.pipeline.rag import rag_pipeline

    sig = inspect.signature(rag_pipeline)
    annotation = sig.parameters["state_contract"].annotation
    # The annotation should reference PipelineContext, not dict
    assert "PipelineContext" in str(annotation)
