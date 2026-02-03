#!/usr/bin/env python3
"""
Langfuse Integration for Production RAG Observability - Native SDK Usage

Uses official Langfuse Python SDK patterns with @observe() decorator.
No custom wrappers - just native SDK features.

Features:
    - Automatic function tracing with @observe() decorator
    - Query-level observability with nested spans
    - Session and user tracking
    - Metrics logging (latency, precision, recall)
    - Production-ready error handling

Usage Example 1: Decorator-based (Recommended):
    from langfuse import observe, get_client

    @observe(name="rag-query")
    def search_query(query: str, engine_name: str):
        langfuse = get_client()

        # Update trace metadata
        langfuse.update_current_trace(
            input={"query": query, "engine": engine_name},
            session_id="session_123",
            user_id="user_456",
            tags=["search", engine_name]
        )

        # Your search logic
        results = engine.search(query)

        # Log metrics
        langfuse.score_current_trace(
            name="precision_at_1",
            value=calculate_precision(results)
        )

        return results

Usage Example 2: Manual spans for RAG (Retrieval + Generation):
    from langfuse import get_client

    langfuse = get_client()

    with langfuse.start_as_current_span(name="rag-pipeline") as trace:
        # Retrieval span
        with trace.start_as_current_span(
            name="retrieval",
            input={"query": query}
        ) as retrieval_span:
            contexts = vector_db.search(query)
            retrieval_span.update(output={"contexts": contexts})

        # Generation span (if using LLM)
        with trace.start_as_current_span(
            name="generation",
            input={"query": query, "contexts": contexts}
        ) as gen_span:
            answer = llm.generate(query, contexts)
            gen_span.update(output={"answer": answer})

Environment Variables:
    LANGFUSE_PUBLIC_KEY: Public API key (optional for self-hosted)
    LANGFUSE_SECRET_KEY: Secret API key (optional for self-hosted)
    LANGFUSE_HOST: Langfuse server URL (default: http://localhost:3001)

Integration:
    - Langfuse UI: http://localhost:3001
    - Real-time query monitoring
    - Session analytics
    - Automatic nesting of decorated functions

Reference:
    Official docs: https://langfuse.com/docs/sdk/python/decorators
    RAG example: https://langfuse.com/docs/guides/cookbook/evaluation_with_ragas
"""

import os
import time
from collections.abc import Callable
from typing import Any

from langfuse import Langfuse, get_client, observe


# ============================================================================
# Helper Functions for RAG Search Tracing
# ============================================================================


def initialize_langfuse(
    host: str = "http://localhost:3001",
    public_key: str | None = None,
    secret_key: str | None = None,
    enabled: bool = True,
) -> tuple[Langfuse | None, bool]:
    """
    Initialize Langfuse client with graceful error handling.

    Args:
        host: Langfuse server URL
        public_key: Public API key (optional for self-hosted)
        secret_key: Secret API key (optional for self-hosted)
        enabled: Enable/disable tracing

    Returns:
        (client, is_enabled) tuple

    Example:
        client, enabled = initialize_langfuse()
        if enabled:
            # Use Langfuse
            pass
    """
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

    except Exception as e:
        print(f"⚠️  Langfuse initialization failed: {e}")
        print("   Continuing without Langfuse tracing...")
        return None, False


@observe(name="rag-search-query")
def trace_search_with_decorator(
    query: str,
    search_fn: Callable,
    engine_name: str = "unknown",
    user_id: str = "anonymous",
    session_id: str | None = None,
    expected_article: int | None = None,
) -> tuple[list[Any], dict[str, float]]:
    """
    Trace a RAG search query using native @observe() decorator.

    This function is automatically traced by Langfuse. All nested
    function calls within this function will be captured as spans.

    Args:
        query: Search query text
        search_fn: Function that performs the search (takes query as input)
        engine_name: Search engine name (baseline, hybrid, dbsf_colbert)
        user_id: User identifier
        session_id: Session identifier (optional)
        expected_article: Expected article number for evaluation (optional)

    Returns:
        (results, metrics) tuple

    Example:
        results, metrics = trace_search_with_decorator(
            query="статья 121 УК",
            search_fn=lambda q: engine.search(q, limit=10),
            engine_name="dbsf_colbert",
            user_id="user_123",
            expected_article=121
        )
    """
    langfuse = get_client()

    # Update trace with metadata
    langfuse.update_current_trace(
        input={"query": query, "engine": engine_name},
        user_id=user_id,
        session_id=session_id,
        tags=["search", engine_name, "evaluation"],
        metadata={"expected_article": expected_article} if expected_article else {},
    )

    # Execute search (automatically captured as nested span if search_fn is also decorated)
    start_time = time.time()
    results = search_fn(query)
    latency_ms = (time.time() - start_time) * 1000

    # Calculate evaluation metrics
    metrics = {
        "latency_ms": latency_ms,
        "num_results": len(results),
    }

    if expected_article is not None and results:
        # Extract article numbers from results
        retrieved_articles = [
            r.payload.get("article_number") if hasattr(r, "payload") else None for r in results
        ]

        # Calculate precision@1 and recall@10
        precision_at_1 = 1.0 if retrieved_articles[0] == expected_article else 0.0
        recall_at_10 = 1.0 if expected_article in retrieved_articles[:10] else 0.0

        metrics["precision_at_1"] = precision_at_1
        metrics["recall_at_10"] = recall_at_10
        metrics["correct_at_1"] = precision_at_1

        # Log scores to Langfuse
        langfuse.score_current_trace(name="precision_at_1", value=precision_at_1)
        langfuse.score_current_trace(name="recall_at_10", value=recall_at_10)
        langfuse.score_current_trace(name="latency_ms", value=latency_ms)

    # Update trace with output
    langfuse.update_current_trace(output={"num_results": len(results), "metrics": metrics})

    return results, metrics


def trace_search_with_spans(
    query: str,
    search_fn: Callable,
    engine_name: str = "unknown",
    user_id: str = "anonymous",
    session_id: str | None = None,
    expected_article: int | None = None,
) -> tuple[list[Any], dict[str, float]]:
    """
    Trace a RAG search query using manual span creation.

    This approach gives more control over span structure, useful for
    complex RAG pipelines with multiple stages (retrieval → reranking → generation).

    Args:
        query: Search query text
        search_fn: Function that performs the search
        engine_name: Search engine name
        user_id: User identifier
        session_id: Session identifier
        expected_article: Expected article number for evaluation

    Returns:
        (results, metrics) tuple

    Example:
        results, metrics = trace_search_with_spans(
            query="статья 121 УК",
            search_fn=lambda q: engine.search(q, limit=10),
            engine_name="dbsf_colbert",
            expected_article=121
        )
    """
    langfuse = get_client()

    # Create main trace
    with langfuse.start_as_current_span(name="rag-search") as trace:
        # Store trace metadata
        trace.update(
            user_id=user_id,
            session_id=session_id,
            tags=["search", engine_name],
            metadata={"engine": engine_name, "expected_article": expected_article},
        )

        # Retrieval span
        with trace.start_as_current_span(
            name=f"retrieval-{engine_name}", input={"query": query}
        ) as retrieval_span:
            start_time = time.time()
            results = search_fn(query)
            latency_ms = (time.time() - start_time) * 1000

            retrieval_span.update(output={"num_results": len(results), "latency_ms": latency_ms})

        # Evaluation span (if expected article provided)
        if expected_article is not None and results:
            with trace.start_as_current_span(
                name="evaluation", input={"expected_article": expected_article}
            ) as eval_span:
                # Extract article numbers
                retrieved_articles = [
                    r.payload.get("article_number") if hasattr(r, "payload") else None
                    for r in results
                ]

                # Calculate metrics
                precision_at_1 = 1.0 if retrieved_articles[0] == expected_article else 0.0
                recall_at_10 = 1.0 if expected_article in retrieved_articles[:10] else 0.0

                eval_span.update(
                    output={
                        "precision_at_1": precision_at_1,
                        "recall_at_10": recall_at_10,
                        "retrieved_articles": retrieved_articles[:10],
                    }
                )

                # Log scores
                eval_span.score(name="precision_at_1", value=precision_at_1)
                eval_span.score(name="recall_at_10", value=recall_at_10)

                metrics = {
                    "latency_ms": latency_ms,
                    "num_results": len(results),
                    "precision_at_1": precision_at_1,
                    "recall_at_10": recall_at_10,
                }
        else:
            metrics = {
                "latency_ms": latency_ms,
                "num_results": len(results),
            }

        return results, metrics


# ============================================================================
# Integration Examples
# ============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("LANGFUSE NATIVE SDK INTEGRATION - Examples")
    print("=" * 80)

    # Check Langfuse server
    import requests  # type: ignore[import-untyped]

    try:
        response = requests.get("http://localhost:3001/api/public/health", timeout=2)
        print(f"\n✅ Langfuse server: {response.json()}")
    except Exception as e:
        print(f"\n⚠️  Langfuse server not accessible: {e}")
        print("   Start with: docker compose --profile ml up -d langfuse")

    print("\n📊 Langfuse UI: http://localhost:3001")

    # Example 1: Decorator-based tracing (recommended)
    print("\n" + "=" * 80)
    print("Example 1: @observe() Decorator (Automatic Tracing)")
    print("=" * 80)

    @observe(name="search-example")
    def example_search(query: str):
        """Example search function with automatic tracing."""
        langfuse = get_client()

        # Update trace
        langfuse.update_current_trace(
            input={"query": query}, tags=["example", "demo"], user_id="demo_user"
        )

        # Simulate search
        time.sleep(0.1)  # Simulate latency
        mock_results = [{"article_number": 121, "score": 0.95}]

        # Log score
        langfuse.score_current_trace(name="num_results", value=len(mock_results))

        return mock_results

    print("   Code:")
    print("   @observe(name='search-example')")
    print("   def example_search(query):")
    print("       langfuse.update_current_trace(input={'query': query})")
    print("       return results")
    print()
    print("   ✓ Automatic trace creation")
    print("   ✓ Auto-nesting of function calls")
    print("   ✓ Captures input/output/latency")

    # Example 2: Manual spans for RAG
    print("\n" + "=" * 80)
    print("Example 2: Manual Spans (Fine-grained Control)")
    print("=" * 80)

    print("   Code:")
    print("   with langfuse.start_as_current_span(name='rag-pipeline'):")
    print("       with trace.start_as_current_span(name='retrieval'):")
    print("           contexts = search(query)")
    print("       with trace.start_as_current_span(name='generation'):")
    print("           answer = llm.generate(query, contexts)")
    print()
    print("   ✓ Explicit span structure")
    print("   ✓ Separate retrieval/generation stages")
    print("   ✓ Custom metadata per span")

    # Usage recommendations
    print("\n" + "=" * 80)
    print("💡 Integration Recommendations:")
    print("=" * 80)
    print()
    print("1. For simple functions → Use @observe() decorator")
    print("   - Automatic, zero-friction tracing")
    print("   - Perfect for search engines")
    print()
    print("2. For complex RAG pipelines → Use manual spans")
    print("   - Fine-grained control over structure")
    print("   - Separate retrieval, reranking, generation stages")
    print()
    print("3. Integration points:")
    print("   - search_engines.py → Add @observe() to search methods")
    print("   - run_ab_test.py → Already has MLflow, add Langfuse spans")
    print("   - evaluate_with_ragas.py → Add @observe() to eval functions")
    print()
    print("4. View traces:")
    print("   - Langfuse UI: http://localhost:3001")
    print("   - Filter by tags, user_id, session_id")
    print("   - Analyze latency, scores, errors")

    print("\n" + "=" * 80)
    print("📚 Official Documentation:")
    print("=" * 80)
    print("   - Decorators: https://langfuse.com/docs/sdk/python/decorators")
    print("   - RAG cookbook: https://langfuse.com/docs/guides/cookbook/evaluation_with_ragas")
    print("   - Tracing: https://langfuse.com/docs/tracing")
    print("=" * 80)
