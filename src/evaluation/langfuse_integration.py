#!/usr/bin/env python3
"""Native Langfuse v4 examples for evaluation-time RAG observability.

This module intentionally demonstrates the observation-first SDK model:

- trace attributes are propagated with ``propagate_attributes(...)``;
- root/manual spans are created with ``start_as_current_observation(as_type="span", ...)``;
- active observations are updated via ``update_current_span(...)`` or ``observation.update(...)``;
- scores remain attached through native score APIs.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any

from langfuse import Langfuse, get_client, observe, propagate_attributes


def initialize_langfuse(
    host: str = "http://localhost:3001",
    public_key: str | None = None,
    secret_key: str | None = None,
    enabled: bool = True,
) -> tuple[Langfuse | None, bool]:
    """Initialize Langfuse client with graceful error handling."""
    if not enabled:
        print("⚠️  Langfuse tracing disabled")
        return None, False

    try:
        client = Langfuse(
            host=host,
            public_key=public_key or os.getenv("LANGFUSE_PUBLIC_KEY", ""),
            secret_key=secret_key or os.getenv("LANGFUSE_SECRET_KEY", ""),
        )
        print(f"✅ Langfuse initialized: {host}")
        return client, True
    except Exception as exc:
        print(f"⚠️  Langfuse initialization failed: {exc}")
        print("   Continuing without Langfuse tracing...")
        return None, False


def _search_tags(engine_name: str, *, include_evaluation: bool) -> list[str]:
    tags = ["search", engine_name]
    if include_evaluation:
        tags.append("evaluation")
    return tags


def _search_metadata(engine_name: str, expected_article: int | None) -> dict[str, str]:
    metadata = {"engine": engine_name}
    if expected_article is not None:
        metadata["expected_article"] = str(expected_article)
    return metadata


def _retrieved_articles(results: list[Any]) -> list[int | None]:
    return [r.payload.get("article_number") if hasattr(r, "payload") else None for r in results]


def _build_metrics(
    *,
    results: list[Any],
    latency_ms: float,
    expected_article: int | None,
) -> dict[str, float | int]:
    metrics: dict[str, float | int] = {
        "latency_ms": latency_ms,
        "num_results": len(results),
    }
    if expected_article is None or not results:
        return metrics

    retrieved_articles = _retrieved_articles(results)
    precision_at_1 = 1.0 if retrieved_articles[0] == expected_article else 0.0
    recall_at_10 = 1.0 if expected_article in retrieved_articles[:10] else 0.0
    metrics["precision_at_1"] = precision_at_1
    metrics["recall_at_10"] = recall_at_10
    metrics["correct_at_1"] = precision_at_1
    return metrics


@observe(name="rag-search-query", capture_input=False, capture_output=False)
def trace_search_with_decorator(
    query: str,
    search_fn: Callable[[str], list[Any]],
    engine_name: str = "unknown",
    user_id: str = "anonymous",
    session_id: str | None = None,
    expected_article: int | None = None,
) -> tuple[list[Any], dict[str, float | int]]:
    """Trace a RAG search query through the current v4 observation context."""
    langfuse = get_client()
    metadata = _search_metadata(engine_name, expected_article)

    with propagate_attributes(
        user_id=user_id,
        session_id=session_id,
        tags=_search_tags(engine_name, include_evaluation=True),
        metadata=metadata,
    ):
        langfuse.update_current_span(input={"query": query, "engine": engine_name})

        start_time = time.time()
        results = search_fn(query)
        latency_ms = (time.time() - start_time) * 1000

        metrics = _build_metrics(
            results=results,
            latency_ms=latency_ms,
            expected_article=expected_article,
        )

        if "precision_at_1" in metrics:
            langfuse.score_current_trace(name="precision_at_1", value=metrics["precision_at_1"])
            langfuse.score_current_trace(name="recall_at_10", value=metrics["recall_at_10"])
        langfuse.score_current_trace(name="latency_ms", value=latency_ms)

        langfuse.update_current_span(
            output={
                "num_results": len(results),
                "metrics": metrics,
            }
        )

    return results, metrics


def trace_search_with_spans(
    query: str,
    search_fn: Callable[[str], list[Any]],
    engine_name: str = "unknown",
    user_id: str = "anonymous",
    session_id: str | None = None,
    expected_article: int | None = None,
) -> tuple[list[Any], dict[str, float | int]]:
    """Trace a RAG search query using explicit native v4 observations."""
    langfuse = get_client()
    metadata = _search_metadata(engine_name, expected_article)

    with (
        langfuse.start_as_current_observation(
            as_type="span",
            name="rag-search",
        ) as root_span,
        propagate_attributes(
            user_id=user_id,
            session_id=session_id,
            tags=_search_tags(engine_name, include_evaluation=False),
            metadata=metadata,
        ),
    ):
        root_span.update(
            input={"query": query, "engine": engine_name},
            metadata=metadata,
        )

        with root_span.start_as_current_observation(
            as_type="span",
            name=f"retrieval-{engine_name}",
            input={"query": query},
        ) as retrieval_span:
            start_time = time.time()
            results = search_fn(query)
            latency_ms = (time.time() - start_time) * 1000
            retrieval_span.update(output={"num_results": len(results), "latency_ms": latency_ms})

        metrics = _build_metrics(
            results=results,
            latency_ms=latency_ms,
            expected_article=expected_article,
        )

        if expected_article is not None and results:
            retrieved_articles = _retrieved_articles(results)
            with root_span.start_as_current_observation(
                as_type="span",
                name="evaluation",
                input={"expected_article": expected_article},
            ) as eval_span:
                eval_span.update(
                    output={
                        "precision_at_1": metrics["precision_at_1"],
                        "recall_at_10": metrics["recall_at_10"],
                        "retrieved_articles": retrieved_articles[:10],
                    }
                )
                eval_span.score(name="precision_at_1", value=metrics["precision_at_1"])
                eval_span.score(name="recall_at_10", value=metrics["recall_at_10"])

    return results, metrics


if __name__ == "__main__":
    print("=" * 80)
    print("LANGFUSE V4 INTEGRATION - Examples")
    print("=" * 80)
    print()
    print("1. Decorator path:")
    print("   @observe(name='rag-search-query', capture_input=False, capture_output=False)")
    print("   with propagate_attributes(user_id=..., session_id=..., tags=[...], metadata={...}):")
    print("       langfuse.update_current_span(input={'query': query, 'engine': engine_name})")
    print("       ... search ...")
    print(
        "       langfuse.update_current_span(output={'num_results': len(results), 'metrics': metrics})"
    )
    print()
    print("2. Manual observation path:")
    print(
        "   with langfuse.start_as_current_observation(as_type='span', name='rag-search') as root:"
    )
    print("       with propagate_attributes(...):")
    print(
        "           with root.start_as_current_observation(as_type='span', name='retrieval-...'):"
    )
    print("               ... search ...")
    print("           with root.start_as_current_observation(as_type='span', name='evaluation'):")
    print("               eval_span.score(name='precision_at_1', value=...)")
    print()
    print("Official docs:")
    print("  - https://langfuse.com/docs/observability/sdk/instrumentation")
    print("  - https://langfuse.com/docs/observability/sdk/upgrade-path/python-v3-to-v4")
