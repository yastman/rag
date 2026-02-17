"""Cross-encoder reranking for improved search accuracy.

Reranking improves retrieval accuracy by 10-15% NDCG.
Uses lightweight cross-encoder for CPU inference (~50-100ms latency).

NOTE: sentence_transformers is imported lazily to avoid pulling torch
for bot runtime. Install with: uv sync --extra ml-local
"""

import logging
from typing import TYPE_CHECKING, Any, cast


if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder


logger = logging.getLogger(__name__)

# Global singleton (type: CrossEncoder when loaded)
_cross_encoder: Any | None = None


def get_cross_encoder(model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> "CrossEncoder":
    """
    Get singleton cross-encoder model.

    Model: ms-marco-MiniLM-L-6-v2
    - Size: 80MB (lightweight for CPU)
    - Latency: ~50-100ms for 5 pairs on CPU
    - Trained on MS MARCO passage ranking

    Args:
        model_name: HuggingFace model ID

    Returns:
        Shared CrossEncoder instance

    Raises:
        ImportError: If sentence_transformers not installed
    """
    global _cross_encoder

    if _cross_encoder is None:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as e:
            raise ImportError(
                "sentence_transformers is not installed. "
                "Install ml-local extra: uv sync --extra ml-local"
            ) from e

        logger.info(f"Loading cross-encoder: {model_name}")
        _cross_encoder = CrossEncoder(model_name, max_length=512)
        logger.info("Cross-encoder loaded successfully")
    else:
        logger.debug("Using existing cross-encoder instance")

    # cast is safe: _cross_encoder is always set to CrossEncoder when not None
    return cast("CrossEncoder", _cross_encoder)


def rerank_results(
    query: str,
    results: list[dict[str, Any]],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """
    Rerank search results using cross-encoder.

    Reranks top_k results for balance between accuracy and latency.
    Cross-encoder scores query-document relevance more accurately than
    vector similarity alone.

    Args:
        query: User query
        results: Search results with 'text' and 'score' fields
        top_k: Number of results to rerank (default: 5)

    Returns:
        Reranked results with updated scores
    """
    if not results or len(results) == 0:
        return results

    # Get cross-encoder model
    model = get_cross_encoder()

    # Prepare query-document pairs for top_k results
    pairs = [(query, result["text"]) for result in results[:top_k]]

    # Score with cross-encoder (returns relevance scores)
    try:
        scores = model.predict(pairs)

        # Update scores and sort by cross-encoder score
        for i, score in enumerate(scores):
            results[i]["original_score"] = results[i]["score"]
            results[i]["rerank_score"] = float(score)
            results[i]["score"] = float(score)  # Replace with rerank score

        # Sort by rerank score (descending)
        reranked = sorted(results[:top_k], key=lambda x: x["rerank_score"], reverse=True)

        # Append remaining results unchanged
        reranked.extend(results[top_k:])

        logger.info(f"Reranked top {top_k} results with cross-encoder")
        return reranked

    except Exception as e:
        logger.error(f"Reranking error: {e}", exc_info=True)
        # Return original results on error
        return results


def clear_cross_encoder():
    """Clear cross-encoder from memory."""
    global _cross_encoder

    if _cross_encoder is not None:
        logger.info("Clearing cross-encoder from memory")
        del _cross_encoder
        _cross_encoder = None

        import gc

        gc.collect()
