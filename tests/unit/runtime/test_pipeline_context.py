"""Behavior tests for PipelineContext, the typed rag_pipeline state (#2946).

``PipelineContext`` is a ``TypedDict(total=False)``: at runtime its behavior
is the mapping protocol rag_pipeline() callers rely on. Key/type checking is
owned by MyPy, not by source inspection (#3406 replaced the structural
TypedDict/signature ratchets with these direct construction tests).
"""

from __future__ import annotations

from src.runtime.pipeline.context import PipelineContext


def test_pipeline_context_round_trips_all_documented_fields() -> None:
    """A caller can build a full context from the documented keys and read it back."""
    ctx = PipelineContext(
        cache_checked=True,
        cache_hit=False,
        cache_scope="session",
        embedding_bundle_ready=True,
        embedding_bundle_version="bge-m3-v1",
        dense_vector=[0.1, 0.2, 0.3, 0.4],
        sparse_vector={"indices": [1], "values": [0.5]},
        colbert_query=[[0.1, 0.2]],
        query_type="real_estate",
        topic_hint="apartments",
        filters={"city": "Nesebar"},
        retrieval_policy="hybrid",
        grounding_mode="strict",
    )

    assert ctx["cache_checked"] is True
    assert ctx["cache_hit"] is False
    assert ctx["cache_scope"] == "session"
    assert ctx["embedding_bundle_ready"] is True
    assert ctx["embedding_bundle_version"] == "bge-m3-v1"
    assert ctx["dense_vector"] == [0.1, 0.2, 0.3, 0.4]
    assert ctx["sparse_vector"] == {"indices": [1], "values": [0.5]}
    assert ctx["colbert_query"] == [[0.1, 0.2]]
    assert ctx["query_type"] == "real_estate"
    assert ctx["topic_hint"] == "apartments"
    assert ctx["filters"] == {"city": "Nesebar"}
    assert ctx["retrieval_policy"] == "hybrid"
    assert ctx["grounding_mode"] == "strict"


def test_pipeline_context_supports_partial_construction() -> None:
    """total=False: callers may construct a partial context with only known keys."""
    ctx = PipelineContext(filters={"city": "Nesebar"})

    assert ctx["filters"] == {"city": "Nesebar"}
    assert "dense_vector" not in ctx
