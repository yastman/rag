#!/usr/bin/env python3
"""
Search engine with reranker for 2-stage retrieval:
1. BaselineSearchEngine retrieves top-100 candidates
2. Reranker reranks to top-K final results
"""

import sys


sys.path.append("/home/admin/contextual_rag")

# Import from same directory
import importlib.util
import os


spec = importlib.util.spec_from_file_location(
    "search_engines", os.path.join(os.path.dirname(__file__), "search_engines.py")
)
search_engines = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(search_engines)  # type: ignore[union-attr]
BaselineSearchEngine = search_engines.BaselineSearchEngine


class RerankSearchEngine:
    """
    2-stage retrieval with reranker:
    - Stage 1: Baseline dense search retrieves top-100 candidates
    - Stage 2: Cross-encoder reranker reranks to top-K
    """

    def __init__(
        self,
        collection_name: str,
        embedding_model,
        reranker_model_name: str = "BAAI/bge-reranker-v2-m3",
    ):
        """
        Initialize rerank search engine.

        Args:
            collection_name: Qdrant collection name
            embedding_model: BGE-M3 model for dense embeddings
            reranker_model_name: Cross-encoder reranker model name
        """
        # Stage 1: Baseline retriever
        self.baseline_engine = BaselineSearchEngine(collection_name, embedding_model)

        # Stage 2: Reranker (multilingual BGE-reranker-v2-m3)
        try:
            from FlagEmbedding import FlagReranker
        except ImportError as e:
            raise ImportError(
                "FlagEmbedding is not installed. Install ml-local extra: uv sync --extra ml-local"
            ) from e

        print(f"Loading reranker: {reranker_model_name}...")
        self.reranker = FlagReranker(
            reranker_model_name,
            use_fp16=True,  # Faster computation
            devices=["cuda:0"],
        )
        print("✓ Reranker loaded successfully")

    def search(self, query: str, top_k: int = 10, retrieval_top_k: int = 100) -> list[dict]:
        """
        2-stage search with reranking.

        Args:
            query: Search query text
            top_k: Final number of results to return (after reranking)
            retrieval_top_k: Number of candidates to retrieve in stage 1 (before reranking)

        Returns:
            List of dicts with keys: point_id, score, article_number, text
        """
        # Stage 1: Retrieve top-100 candidates using dense search
        candidates = self.baseline_engine.search(query, top_k=retrieval_top_k)

        if not candidates:
            return []

        # Stage 2: Rerank using cross-encoder
        # Prepare pairs: [(query, passage1), (query, passage2), ...]
        pairs = [[query, candidate["text"]] for candidate in candidates]

        # Compute reranker scores
        rerank_scores = self.reranker.compute_score(pairs, normalize=True)

        # Combine reranker scores with candidates
        for i, candidate in enumerate(candidates):
            candidate["score"] = float(rerank_scores[i])  # Replace dense score with rerank score

        # Sort by rerank score and return top-K
        candidates.sort(key=lambda x: x["score"], reverse=True)

        return candidates[:top_k]  # type: ignore[no-any-return]


def create_rerank_search_engine(
    collection_name: str, embedding_model, reranker_model: str = "BAAI/bge-reranker-v2-m3"
):
    """
    Factory function to create rerank search engine.

    Args:
        collection_name: Qdrant collection name
        embedding_model: BGE-M3 embedding model instance
        reranker_model: Reranker model name

    Returns:
        RerankSearchEngine instance
    """
    return RerankSearchEngine(collection_name, embedding_model, reranker_model)


if __name__ == "__main__":
    # Quick test
    try:
        from FlagEmbedding import BGEM3FlagModel
    except ImportError:
        raise SystemExit("FlagEmbedding is not installed. Run: uv sync --extra ml-local")

    print("Loading BGE-M3 model...")
    model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)

    collection = "ukraine_criminal_code_zai_full"

    print("\n=== Testing Rerank Search ===")
    rerank = create_rerank_search_engine(collection, model)
    results = rerank.search("кража имущества", top_k=5, retrieval_top_k=100)

    print("\nTop 5 results after reranking:")
    for i, r in enumerate(results, 1):
        print(f"{i}. Article {r['article_number']}: {r['score']:.4f}")
