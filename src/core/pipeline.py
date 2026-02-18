"""Main RAG pipeline orchestrator."""

import asyncio
from dataclasses import dataclass
from typing import Any

from src.config import APIProvider, Settings
from src.contextualization import (
    ClaudeContextualizer,
    GroqContextualizer,
    OpenAIContextualizer,
)
from src.ingestion import DocumentChunker, DocumentIndexer, UniversalDocumentParser
from src.models import get_sentence_transformer
from src.retrieval import create_search_engine


@dataclass
class RAGResult:
    """Result from RAG pipeline."""

    query: str
    results: list[dict[str, Any]]
    context_used: bool
    search_method: str
    execution_time: float


class RAGPipeline:
    """
    Main Retrieval-Augmented Generation pipeline.

    Orchestrates:
    1. Query embedding
    2. Document retrieval
    3. Context enrichment (optional)
    4. Result ranking

    Example:
        >>> pipeline = RAGPipeline()
        >>> results = await pipeline.search("What are citizen rights?")
        >>> for result in results.results:
        ...     print(result["text"])
    """

    def __init__(self, settings: Settings | None = None):
        """
        Initialize RAG pipeline.

        Args:
            settings: Configuration settings
        """
        self.settings = settings or Settings()

        # Initialize components (singleton model - saves 2-3GB RAM)
        self.embedding_model = get_sentence_transformer("BAAI/bge-m3")
        self.search_engine = create_search_engine(settings=self.settings)

        # Initialize contextualizer based on API provider
        self.contextualizer = self._create_contextualizer()

        # Initialize indexer for document management
        self.indexer = DocumentIndexer(self.settings)
        self.chunker = DocumentChunker()
        self.parser = UniversalDocumentParser(use_cache=True)

    def _create_contextualizer(self):
        """Create contextualizer based on configured API provider."""
        if self.settings.api_provider == APIProvider.CLAUDE:
            return ClaudeContextualizer(self.settings)
        if self.settings.api_provider == APIProvider.OPENAI:
            return OpenAIContextualizer(self.settings)
        if self.settings.api_provider == APIProvider.GROQ:
            return GroqContextualizer(self.settings)
        # Default to Claude
        return ClaudeContextualizer(self.settings)

    async def search(
        self,
        query: str,
        top_k: int | None = None,
        use_context: bool = True,
    ) -> RAGResult:
        """
        Search for relevant documents.

        Args:
            query: User's search query
            top_k: Number of results (uses settings default if None)
            use_context: Whether to use LLM contextualization

        Returns:
            RAGResult with retrieved documents
        """
        import time

        start_time = time.time()
        top_k = top_k or self.settings.top_k

        # Step 1: Determine query format based on search engine
        # Hybrid engines can accept query string directly for sparse/ColBERT vectors
        from src.retrieval import HybridRRFColBERTSearchEngine, HybridRRFSearchEngine

        if isinstance(self.search_engine, (HybridRRFSearchEngine, HybridRRFColBERTSearchEngine)):
            # Pass query string directly for hybrid search (async handled inside)
            loop = asyncio.get_event_loop()
            search_results = await loop.run_in_executor(
                None,
                lambda: self.search_engine.search(
                    query_embedding=query,
                    top_k=top_k,
                    score_threshold=self.settings.score_threshold,
                ),
            )
        else:
            # For other engines, generate dense embedding (async)
            loop = asyncio.get_event_loop()
            query_embedding = await loop.run_in_executor(
                None, lambda: self.embedding_model.encode(query, normalize_embeddings=True).tolist()
            )

            # Step 2: Search using configured search engine (async)
            search_results = await loop.run_in_executor(
                None,
                lambda: self.search_engine.search(
                    query_embedding=query_embedding,
                    top_k=top_k,
                    score_threshold=self.settings.score_threshold,
                ),
            )

        # Step 3: Optional contextualization
        if use_context and self.settings.enable_query_expansion:
            # Enrich results with context (could add query expansion here)
            # For now, just use raw results
            pass

        execution_time = time.time() - start_time

        return RAGResult(
            query=query,
            results=[
                {
                    "article_number": r.article_number,
                    "text": r.text,
                    "score": r.score,
                    "metadata": r.metadata,
                }
                for r in search_results
            ],
            context_used=use_context,
            search_method=self.search_engine.get_name(),
            execution_time=execution_time,
        )

    async def index_documents(
        self,
        pdf_paths: list[str],
        collection_name: str | None = None,
        recreate_collection: bool = False,
    ) -> dict[str, Any]:
        """
        Index documents into the system.

        Args:
            pdf_paths: List of document paths (PDF, DOCX, CSV, Excel)
            collection_name: Target collection (uses settings default if None)
            recreate_collection: Whether to drop and recreate collection

        Returns:
            Indexing statistics
        """
        collection_name = collection_name or self.settings.collection_name

        # Create collection
        self.indexer.create_collection(
            collection_name=collection_name,
            recreate=recreate_collection,
        )

        # Parse and chunk documents
        all_chunks = []
        for pdf_path in pdf_paths:
            try:
                # Parse
                doc = self.parser.parse_file(pdf_path)

                # Chunk
                chunks = self.chunker.chunk_text(
                    text=doc.content,
                    document_name=doc.filename,
                    article_number=doc.filename,
                )

                all_chunks.extend(chunks)
            except Exception as e:
                print(f"Warning: Failed to process {pdf_path}: {e}")

        # Index all chunks
        stats = await self.indexer.index_chunks(
            chunks=all_chunks,
            collection_name=collection_name,
        )

        return {
            "total_chunks": stats.total_chunks,
            "indexed_chunks": stats.indexed_chunks,
            "failed_chunks": stats.failed_chunks,
            "duration_seconds": stats.duration_seconds,
        }

    async def evaluate(
        self,
        queries: list[str],
        ground_truth: list[list[str]] | None = None,
    ) -> dict[str, Any]:
        """
        Evaluate pipeline on test queries.

        Args:
            queries: List of test queries
            ground_truth: List of correct results per query (optional)

        Returns:
            Evaluation metrics
        """
        if not queries:
            return {
                "total_queries": 0,
                "average_latency": 0.0,
                "results": [],
                "metrics": {},
            }

        results = []
        for query in queries:
            result = await self.search(query)
            results.append(result)

        # Compute metrics if ground truth provided
        metrics = {}
        if ground_truth:
            metrics = self._compute_metrics(results, ground_truth)

        return {
            "total_queries": len(queries),
            "average_latency": sum(r.execution_time for r in results) / len(results),
            "results": results,
            "metrics": metrics,
        }

    def _compute_metrics(
        self,
        results: list[RAGResult],
        ground_truth: list[list[str]],
    ) -> dict[str, float]:
        """Compute evaluation metrics (Recall, NDCG, MRR)."""
        # Placeholder for metric computation
        # Would implement Recall@K, NDCG@K, MRR here
        return {
            "recall_at_1": 0.0,
            "recall_at_5": 0.0,
            "recall_at_10": 0.0,
            "ndcg_at_10": 0.0,
            "mrr": 0.0,
        }

    def get_stats(self) -> dict[str, Any]:
        """Get pipeline statistics."""
        return {
            "api_provider": self.settings.api_provider.value,
            "model": self.settings.model_name,
            "search_engine": self.search_engine.get_name(),
            "collection": self.settings.collection_name,
            "contextualization_stats": (
                self.contextualizer.get_stats() if hasattr(self.contextualizer, "get_stats") else {}
            ),
        }


async def main():
    """Example usage of RAG pipeline."""
    # Initialize pipeline
    pipeline = RAGPipeline()

    # Search example
    query = "Які права мають громадяни України?"
    result = await pipeline.search(query)

    print(f"Query: {result.query}")
    print(f"Results: {len(result.results)}")
    print(f"Latency: {result.execution_time:.2f}s")
    print(f"Search method: {result.search_method}")
    print()
    for r in result.results:
        print(f"- {r['article_number']}: {r['text'][:100]}...")
        print(f"  Score: {r['score']:.3f}\n")


if __name__ == "__main__":
    asyncio.run(main())
