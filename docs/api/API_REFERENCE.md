***REMOVED*** 🔌 API REFERENCE - Contextual RAG v2.0.1

> **Complete API reference and usage examples for all modules**

***REMOVED******REMOVED*** 📖 Table of Contents

1. [Config API](***REMOVED***config-api)
2. [Contextualization API](***REMOVED***contextualization-api)
3. [Retrieval API](***REMOVED***retrieval-api)
4. [Ingestion API](***REMOVED***ingestion-api)
5. [Evaluation API](***REMOVED***evaluation-api)
6. [Core Pipeline API](***REMOVED***core-pipeline-api)
7. [Data Structures](***REMOVED***data-structures)
8. [Examples](***REMOVED***examples)

---

***REMOVED******REMOVED*** CONFIG API

***REMOVED******REMOVED******REMOVED*** Module: `src.config`

***REMOVED******REMOVED******REMOVED******REMOVED*** Settings class

```python
from src.config import Settings, APIProvider, SearchEngine

class Settings:
    """Central system configuration."""

    def __init__(
        self,
        env_file: Optional[str] = None,
        ***REMOVED*** API Configuration
        api_provider: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        groq_api_key: Optional[str] = None,
        ***REMOVED*** Model Configuration
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        ***REMOVED*** Vector Database
        qdrant_url: Optional[str] = None,
        qdrant_api_key: Optional[str] = None,
        ***REMOVED*** Paths
        data_dir: Optional[str] = None,
        docs_dir: Optional[str] = None,
        logs_dir: Optional[str] = None,
        ***REMOVED*** Search Configuration
        search_engine: Optional[str] = None,
        score_threshold: Optional[float] = None,
        top_k: Optional[int] = None,
        ***REMOVED*** Processing
        batch_size_embeddings: Optional[int] = None,
        batch_size_documents: Optional[int] = None,
        ***REMOVED*** Retry
        max_retries: Optional[int] = None,
        retry_backoff: Optional[float] = None,
    ) -> None:
        """
        Initialize settings from environment variables and arguments.

        Environment variables take precedence over defaults but not over
        explicit arguments.
        """
        pass

    def to_dict(self) -> Dict[str, Any]:
        """Export settings as dictionary (excluding sensitive data)."""
        pass
```

***REMOVED******REMOVED******REMOVED******REMOVED*** Usage

```python
***REMOVED*** 1. Load from .env
settings = Settings()

***REMOVED*** 2. With overrides
settings = Settings(
    api_provider="openai",
    search_engine="baseline",
    qdrant_url="https://qdrant.example.com"
)

***REMOVED*** 3. Access properties
print(settings.model_name)           ***REMOVED*** "claude-3-5-sonnet-20241022"
print(settings.api_provider.value)   ***REMOVED*** "claude"
print(settings.collection_name)      ***REMOVED*** "legal_documents"

***REMOVED*** 4. Export
config_dict = settings.to_dict()
```

***REMOVED******REMOVED******REMOVED******REMOVED*** Available enumerations

```python
from src.config import APIProvider, SearchEngine, ModelName

***REMOVED*** API providers
APIProvider.CLAUDE      ***REMOVED*** "claude" - recommended
APIProvider.OPENAI      ***REMOVED*** "openai"
APIProvider.GROQ        ***REMOVED*** "groq"
APIProvider.Z_AI        ***REMOVED*** "zai" - deprecated

***REMOVED*** Search engines
SearchEngine.BASELINE        ***REMOVED*** Dense only
SearchEngine.HYBRID_RRF      ***REMOVED*** Dense + Sparse
SearchEngine.DBSF_COLBERT    ***REMOVED*** Best (94% Recall@1)

***REMOVED*** LLM Models
ModelName.CLAUDE_SONNET      ***REMOVED*** claude-3-5-sonnet-20241022
ModelName.CLAUDE_HAIKU       ***REMOVED*** claude-3-5-haiku-20241022
ModelName.GPT_4_TURBO        ***REMOVED*** gpt-4-turbo-preview
ModelName.GROQ_LLAMA3_70B    ***REMOVED*** llama3-70b-8192
```

---

***REMOVED******REMOVED*** CONTEXTUALIZATION API

***REMOVED******REMOVED******REMOVED*** Module: `src.contextualization`

***REMOVED******REMOVED******REMOVED******REMOVED*** Base class: ContextualizeProvider

```python
from src.contextualization import ContextualizeProvider
from typing import List, Optional

class ContextualizeProvider(ABC):
    """Abstract base class for contextualization providers."""

    @abstractmethod
    async def contextualize(
        self,
        chunks: List[str],
        query: Optional[str] = None,
        context_window: int = 3,
    ) -> List['ContextualizedChunk']:
        """
        Contextualize a list of chunks.

        Args:
            chunks: List of text chunks to contextualize
            query: Optional user query
            context_window: Number of neighboring chunks to consider

        Returns:
            List[ContextualizedChunk] - chunks with context
        """
        pass

    @abstractmethod
    async def contextualize_single(
        self,
        text: str,
        article_number: str,
        query: Optional[str] = None,
    ) -> 'ContextualizedChunk':
        """Contextualize a single chunk."""
        pass
```

***REMOVED******REMOVED******REMOVED******REMOVED*** Claude Contextualizer ⭐

```python
from src.contextualization import ClaudeContextualizer

class ClaudeContextualizer(ContextualizeProvider):
    """
    Contextualization via Anthropic Claude API.

    Features:
    - Prompt caching for 90% cost savings
    - Async/sync support
    - Token tracking
    - Highest quality output

    Performance:
    - ~8-12 minutes for 100 chunks
    - ~$0.003-0.01 per chunk (with caching)
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        use_cache: bool = True
    ):
        """
        Initialize Claude contextualizer.

        Args:
            settings: Configuration settings
            use_cache: Enable prompt caching
        """
        pass

    async def contextualize(
        self,
        chunks: List[str],
        query: Optional[str] = None,
        context_window: int = 3,
    ) -> List['ContextualizedChunk']:
        """Contextualize multiple chunks."""
        pass

    async def contextualize_single(
        self,
        text: str,
        article_number: str,
        query: Optional[str] = None,
    ) -> 'ContextualizedChunk':
        """Contextualize a single chunk."""
        pass

    def contextualize_sync(
        self,
        text: str,
        article_number: str,
        query: Optional[str] = None,
    ) -> 'ContextualizedChunk':
        """Synchronous contextualization (blocking)."""
        pass

    def get_stats(self) -> Dict[str, Any]:
        """Get contextualization statistics."""
        pass
```

***REMOVED******REMOVED******REMOVED******REMOVED*** Usage

```python
import asyncio
from src.contextualization import ClaudeContextualizer, OpenAIContextualizer, GroqContextualizer

***REMOVED*** 1. Claude (recommended)
async def contextualize_with_claude():
    contextualizer = ClaudeContextualizer(use_cache=True)

    chunks = [
        "Стаття 1. Право на життя...",
        "Стаття 2. Право на честь...",
    ]

    results = await contextualizer.contextualize(
        chunks=chunks,
        query="What are basic human rights?"
    )

    for result in results:
        print(f"Original: {result.original_text[:50]}...")
        print(f"Context: {result.contextual_summary}")
        print(f"Cost: ${result.timestamp}")

    ***REMOVED*** Get stats
    stats = contextualizer.get_stats()
    print(f"Total tokens: {stats['total_tokens']}")
    print(f"Total cost: ${stats['total_cost_usd']:.4f}")

***REMOVED*** 2. OpenAI alternative
contextualizer = OpenAIContextualizer()
result = await contextualizer.contextualize_single(
    text="Стаття 3...",
    article_number="Ст. 3"
)

***REMOVED*** 3. Groq (fast, free)
contextualizer = GroqContextualizer()
results = await contextualizer.contextualize(chunks)

***REMOVED*** Run
asyncio.run(contextualize_with_claude())
```

---

***REMOVED******REMOVED*** RETRIEVAL API

***REMOVED******REMOVED******REMOVED*** Module: `src.retrieval`

***REMOVED******REMOVED******REMOVED******REMOVED*** SearchEngine base class

```python
from src.retrieval import SearchEngine, SearchResult, BaselineSearchEngine
from typing import List, Optional

@dataclass
class SearchResult:
    """Single search result."""
    article_number: str        ***REMOVED*** "Ст. 1"
    text: str                  ***REMOVED*** "Право на життя..."
    score: float               ***REMOVED*** 0.95
    metadata: Dict[str, Any]   ***REMOVED*** {"chapter": "II", ...}

class BaseSearchEngine(ABC):
    """Abstract base class for search engines."""

    def __init__(self, settings: Optional[Settings] = None):
        """Initialize search engine."""
        pass

    @abstractmethod
    def search(
        self,
        query_embedding: List[float],  ***REMOVED*** 1024-dim BGE-M3 vector
        top_k: int = 10,
        score_threshold: Optional[float] = None,
    ) -> List[SearchResult]:
        """
        Search for similar documents.

        Args:
            query_embedding: Query embedding vector (1024 dims)
            top_k: Number of results to return
            score_threshold: Minimum score to include

        Returns:
            List[SearchResult] sorted by relevance
        """
        pass
```

***REMOVED******REMOVED******REMOVED******REMOVED*** 3 implementations

```python
from src.retrieval import (
    BaselineSearchEngine,      ***REMOVED*** 91.3% Recall@1
    HybridRRFSearchEngine,     ***REMOVED*** 88.7% Recall@1
    DBSFColBERTSearchEngine,   ***REMOVED*** 94.0% Recall@1 ⭐
    create_search_engine
)

***REMOVED*** 1. Baseline (Dense only)
engine = BaselineSearchEngine()
results = engine.search(query_embedding, top_k=5)

***REMOVED*** 2. Hybrid RRF (Dense + Sparse)
engine = HybridRRFSearchEngine()
results = engine.search(query_embedding, top_k=5)

***REMOVED*** 3. DBSF+ColBERT (Best result)
engine = DBSFColBERTSearchEngine()
results = engine.search(query_embedding, top_k=5)

***REMOVED*** Factory function
engine = create_search_engine(
    engine_type=SearchEngine.DBSF_COLBERT,
    settings=settings
)

***REMOVED*** Usage
for result in results:
    print(f"{result.article_number}")
    print(f"Text: {result.text[:100]}...")
    print(f"Score: {result.score:.4f}")
    print(f"Metadata: {result.metadata}")
```

---

***REMOVED******REMOVED*** INGESTION API

***REMOVED******REMOVED******REMOVED*** Module: `src.ingestion`

***REMOVED******REMOVED******REMOVED******REMOVED*** 1. PDFParser

```python
from src.ingestion import PDFParser, ParsedDocument

parser = PDFParser()

***REMOVED*** Parse single file
doc = parser.parse_file("path/to/document.pdf")
***REMOVED*** ParsedDocument(
***REMOVED***     filename="document.pdf",
***REMOVED***     title="Document Title",
***REMOVED***     content="Full text...",
***REMOVED***     num_pages=150,
***REMOVED***     metadata={...}
***REMOVED*** )

***REMOVED*** Parse directory
docs = parser.parse_directory(
    dirpath="docs/documents/",
    pattern="*.pdf"
)

***REMOVED*** Parse multiple files
docs = parser.parse_multiple([
    "file1.pdf",
    "file2.pdf",
    "file3.pdf"
])
```

***REMOVED******REMOVED******REMOVED******REMOVED*** 2. DocumentChunker

```python
from src.ingestion import DocumentChunker, ChunkingStrategy, Chunk

chunker = DocumentChunker(
    chunk_size=512,        ***REMOVED*** Target size in characters
    overlap=128,           ***REMOVED*** Overlap between chunks
    strategy=ChunkingStrategy.SEMANTIC  ***REMOVED*** or FIXED_SIZE, SLIDING_WINDOW
)

***REMOVED*** Chunk text
chunks = chunker.chunk_text(
    text=doc.content,
    document_name="Конституція_України",
    article_number="Ст. 1"
)

***REMOVED*** Result: List[Chunk]
for chunk in chunks:
    print(f"Chunk {chunk.chunk_id}: {chunk.text[:50]}...")
    print(f"Article: {chunk.article_number}")
    print(f"Order: {chunk.order}")
    print()

***REMOVED*** Chunking strategies
ChunkingStrategy.FIXED_SIZE      ***REMOVED*** Fixed size
ChunkingStrategy.SEMANTIC        ***REMOVED*** By semantic boundaries
ChunkingStrategy.SLIDING_WINDOW  ***REMOVED*** Sliding window with overlap
```

***REMOVED******REMOVED******REMOVED******REMOVED*** 3. DocumentIndexer

```python
from src.ingestion import DocumentIndexer, IndexStats

indexer = DocumentIndexer(settings)

***REMOVED*** Create collection
indexer.create_collection(
    collection_name="legal_documents",
    recreate=False  ***REMOVED*** True to drop and recreate
)

***REMOVED*** Index chunks
stats = await indexer.index_chunks(
    chunks=chunks,
    collection_name="legal_documents",
    batch_size=16
)

***REMOVED*** IndexStats
print(f"Total chunks: {stats.total_chunks}")
print(f"Indexed: {stats.indexed_chunks}")
print(f"Failed: {stats.failed_chunks}")
print(f"Duration: {stats.duration_seconds:.1f}s")

***REMOVED*** Get collection info
info = indexer.get_collection_stats("legal_documents")
***REMOVED*** {
***REMOVED***     "name": "legal_documents",
***REMOVED***     "points_count": 1234,
***REMOVED***     "vectors_count": 1234,
***REMOVED***     "indexed_vectors_count": 1234,
***REMOVED***     "segment_count": 2
***REMOVED*** }
```

---

***REMOVED******REMOVED*** EVALUATION API

***REMOVED******REMOVED******REMOVED*** Module: `src.evaluation`

***REMOVED******REMOVED******REMOVED******REMOVED*** Metrics

```python
from src.evaluation import (
    compute_recall_at_k,
    compute_ndcg_at_k,
    compute_mrr,
    compute_map
)

***REMOVED*** Compute metrics
recall = compute_recall_at_k(
    predicted_ranks=[1, 2, 5],  ***REMOVED*** Ranks of correct results
    k=10
)

ndcg = compute_ndcg_at_k(
    scores=[0.95, 0.87, 0.72],  ***REMOVED*** Scores of retrieved results
    k=10
)

mrr = compute_mrr(predicted_ranks=[3])  ***REMOVED*** Mean Reciprocal Rank
```

***REMOVED******REMOVED******REMOVED******REMOVED*** MLflow Integration

```python
from src.evaluation import mlflow_integration
import mlflow

***REMOVED*** Start experiment
mlflow.set_experiment("RAG Search Quality")

with mlflow.start_run():
    ***REMOVED*** Log parameters
    mlflow.log_params({
        "search_engine": "dbsf_colbert",
        "api_provider": "claude",
        "top_k": 10
    })

    ***REMOVED*** Log metrics
    mlflow.log_metrics({
        "recall_at_1": 0.94,
        "recall_at_10": 0.993,
        "ndcg_at_10": 0.9711,
        "mrr": 0.9636,
        "latency_seconds": 0.69
    })

    ***REMOVED*** Log model
    mlflow.log_artifact("model.pkl")

***REMOVED*** View results
***REMOVED*** mlflow ui --host 127.0.0.1 --port 5000
```

***REMOVED******REMOVED******REMOVED******REMOVED*** Langfuse Integration

```python
from src.evaluation import langfuse_integration
from langfuse import Langfuse

langfuse = Langfuse()

***REMOVED*** Trace LLM call
with langfuse.trace(name="search") as trace:
    result = await pipeline.search("query")

    trace.log_output(result)
    ***REMOVED*** View at https://langfuse.com
```

***REMOVED******REMOVED******REMOVED******REMOVED*** Run A/B Test

```bash
python src/evaluation/run_ab_test.py \
  --queries data/test_queries/queries.json \
  --baseline baseline \
  --challenger dbsf_colbert \
  --num_queries 150

***REMOVED*** Results:
***REMOVED*** Baseline:       Recall@1=91.3%, NDCG@10=0.9619
***REMOVED*** DBSF+ColBERT:   Recall@1=94.0%, NDCG@10=0.9711
***REMOVED*** Improvement:    +2.9% Recall, +1.0% NDCG ⭐
```

---

***REMOVED******REMOVED*** CORE PIPELINE API

***REMOVED******REMOVED******REMOVED*** RAGPipeline - Main class

```python
from src.core import RAGPipeline
from src.config import Settings
import asyncio

class RAGPipeline:
    """
    Main RAG pipeline - orchestrates all components.

    Uses:
    - ClaudeContextualizer (by default)
    - DBSFColBERTSearchEngine (by default)
    - DocumentIndexer for loading

    This is the main class to use!
    """

    def __init__(self, settings: Optional[Settings] = None):
        """Initialize RAG pipeline with all components."""
        pass

    async def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        use_context: bool = True,
    ) -> 'RAGResult':
        """
        Search documents by query.

        Args:
            query: User query string
            top_k: Number of results (uses settings default if None)
            use_context: Use LLM contextualization

        Returns:
            RAGResult with retrieved documents
        """
        pass

    async def index_documents(
        self,
        pdf_paths: List[str],
        collection_name: Optional[str] = None,
        recreate_collection: bool = False,
    ) -> Dict[str, Any]:
        """
        Index documents into the system.

        Args:
            pdf_paths: List of PDF file paths
            collection_name: Target collection
            recreate_collection: Drop and recreate

        Returns:
            Indexing statistics
        """
        pass

    async def evaluate(
        self,
        queries: List[str],
        ground_truth: Optional[List[List[str]]] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate pipeline quality.

        Args:
            queries: Test queries
            ground_truth: Correct results per query

        Returns:
            Evaluation metrics
        """
        pass

    def get_stats(self) -> Dict[str, Any]:
        """Get pipeline statistics."""
        pass
```

***REMOVED******REMOVED******REMOVED******REMOVED*** Usage

```python
import asyncio

async def main():
    ***REMOVED*** 1. Initialize
    pipeline = RAGPipeline()

    ***REMOVED*** 2. Index documents
    stats = await pipeline.index_documents(
        pdf_paths=[
            "docs/documents/Конституція_України.pdf",
            "docs/documents/Кримінальний_кодекс.pdf",
            "docs/documents/Цивільний_кодекс.pdf"
        ],
        collection_name="legal_documents",
        recreate_collection=False
    )

    print(f"Indexed {stats['indexed_chunks']} chunks")

    ***REMOVED*** 3. Search
    result = await pipeline.search(
        query="Які права мають громадяни України?",
        top_k=5,
        use_context=True
    )

    print(f"Found {len(result.results)} results")
    print(f"Latency: {result.execution_time:.2f}s")
    print(f"Search method: {result.search_method}")

    for i, r in enumerate(result.results, 1):
        print(f"\n{i}. {r['article_number']}")
        print(f"   Text: {r['text'][:100]}...")
        print(f"   Score: {r['score']:.4f}")

    ***REMOVED*** 4. Evaluate
    test_queries = [
        "Які права мають громадяни?",
        "Що таке конституція?",
        "Де знаходиться глава про права?",
    ]

    metrics = await pipeline.evaluate(
        queries=test_queries,
        ground_truth=None  ***REMOVED*** Optional
    )

    print(f"\nAverage latency: {metrics['average_latency']:.3f}s")

    ***REMOVED*** 5. Get stats
    stats = pipeline.get_stats()
    print(f"\nPipeline stats:")
    print(f"API: {stats['api_provider']}")
    print(f"Model: {stats['model']}")
    print(f"Search: {stats['search_engine']}")

***REMOVED*** Run
asyncio.run(main())
```

---

***REMOVED******REMOVED*** DATA STRUCTURES

***REMOVED******REMOVED******REMOVED*** ContextualizedChunk

```python
@dataclass
class ContextualizedChunk:
    """Chunk with LLM-generated context."""

    original_text: str              ***REMOVED*** Original text
    contextual_summary: str         ***REMOVED*** LLM-generated summary
    article_number: str             ***REMOVED*** "Ст. 1"
    chapter: Optional[str] = None   ***REMOVED*** "II"
    section: Optional[str] = None   ***REMOVED*** "Розділ"
    context_method: str = "none"    ***REMOVED*** "claude", "openai", "groq"
    timestamp: datetime = None

    @property
    def full_text(self) -> str:
        """Combined original + context."""
        return f"{self.contextual_summary}\n\n{self.original_text}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        pass
```

***REMOVED******REMOVED******REMOVED*** SearchResult

```python
@dataclass
class SearchResult:
    """Single search result."""

    article_number: str        ***REMOVED*** "Ст. 1"
    text: str                  ***REMOVED*** Document text
    score: float               ***REMOVED*** Relevance score (0-1)
    metadata: Dict[str, Any]   ***REMOVED*** Additional metadata
```

***REMOVED******REMOVED******REMOVED*** RAGResult

```python
@dataclass
class RAGResult:
    """Result from RAG pipeline.search()."""

    query: str                          ***REMOVED*** Original query
    results: List[Dict[str, Any]]       ***REMOVED*** Search results
    context_used: bool                  ***REMOVED*** Was contextualization used
    search_method: str                  ***REMOVED*** "baseline", "hybrid_rrf", "dbsf_colbert"
    execution_time: float               ***REMOVED*** Query time in seconds
```

---

***REMOVED******REMOVED*** EXAMPLES

***REMOVED******REMOVED******REMOVED*** Example 1: Simple search

```python
import asyncio
from src.core import RAGPipeline

async def simple_search():
    pipeline = RAGPipeline()

    result = await pipeline.search(
        "Які права на приватність?",
        top_k=3
    )

    for r in result.results:
        print(f"{r['article_number']}: {r['score']:.3f}")

asyncio.run(simple_search())
```

***REMOVED******REMOVED******REMOVED*** Example 2: Full workflow

```python
import asyncio
from src.core import RAGPipeline
from src.config import Settings, APIProvider, SearchEngine

async def full_workflow():
    ***REMOVED*** Custom settings
    settings = Settings(
        api_provider=APIProvider.CLAUDE,
        search_engine=SearchEngine.DBSF_COLBERT,
        qdrant_url="http://localhost:6333",
        top_k=10
    )

    pipeline = RAGPipeline(settings)

    ***REMOVED*** 1. Index
    print("Indexing documents...")
    stats = await pipeline.index_documents(
        pdf_paths=["docs/documents/Конституція_України.pdf"],
        collection_name="legal_documents"
    )
    print(f"Indexed {stats['indexed_chunks']} chunks")

    ***REMOVED*** 2. Search multiple queries
    queries = [
        "Права громадян",
        "Обов'язки державі",
        "Конституційні гарантії"
    ]

    for query in queries:
        result = await pipeline.search(query)
        print(f"\nQuery: {query}")
        print(f"Top result: {result.results[0]['article_number']}")
        print(f"Score: {result.results[0]['score']:.4f}")

asyncio.run(full_workflow())
```

***REMOVED******REMOVED******REMOVED*** Example 3: Different providers

```python
import asyncio
from src.contextualization import (
    ClaudeContextualizer,
    OpenAIContextualizer,
    GroqContextualizer
)

async def compare_providers():
    text = "Стаття 1. Право на життя..."

    ***REMOVED*** Claude
    contextualizer = ClaudeContextualizer()
    result = await contextualizer.contextualize_single(
        text, "Ст. 1"
    )
    print(f"Claude: {result.contextual_summary[:50]}...")

    ***REMOVED*** OpenAI
    contextualizer = OpenAIContextualizer()
    result = await contextualizer.contextualize_single(
        text, "Ст. 1"
    )
    print(f"OpenAI: {result.contextual_summary[:50]}...")

    ***REMOVED*** Groq (fastest, free)
    contextualizer = GroqContextualizer()
    result = await contextualizer.contextualize_single(
        text, "Ст. 1"
    )
    print(f"Groq: {result.contextual_summary[:50]}...")

asyncio.run(compare_providers())
```

---

***REMOVED******REMOVED*** 🎯 Best Practices

***REMOVED******REMOVED******REMOVED*** 1. Configuration

```python
***REMOVED*** ✅ Good: Use Settings
from src.config import Settings
settings = Settings()

***REMOVED*** ❌ Bad: Hardcode values
QDRANT_URL = "http://localhost:6333"
```

***REMOVED******REMOVED******REMOVED*** 2. Context Managers

```python
***REMOVED*** ✅ Good: Use async context
async with create_pipeline() as pipeline:
    result = await pipeline.search("query")

***REMOVED*** ❌ Bad: Don't clean up resources
pipeline = create_pipeline()
result = pipeline.search("query")
```

***REMOVED******REMOVED******REMOVED*** 3. Error Handling

```python
***REMOVED*** ✅ Good: Handle errors
try:
    result = await pipeline.search("query")
except ConnectionError:
    print("Qdrant is not available")
except ValueError as e:
    print(f"Invalid query: {e}")

***REMOVED*** ❌ Bad: Ignore errors
result = await pipeline.search("query")
```

***REMOVED******REMOVED******REMOVED*** 4. Batch Processing

```python
***REMOVED*** ✅ Good: Process in batches
queries = ["q1", "q2", "q3", ...]
for batch in chunks(queries, batch_size=10):
    results = [await pipeline.search(q) for q in batch]

***REMOVED*** ❌ Bad: One by one
for query in queries:
    result = await pipeline.search(query)  ***REMOVED*** Slow!
```

---

**Last Updated**: October 29, 2025
**Version**: 2.0.1
