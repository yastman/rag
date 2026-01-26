# 🔌 API REFERENCE - Contextual RAG v2.0.1

> **Complete API reference and usage examples for all modules**

## 📖 Table of Contents

1. [Config API](#config-api)
2. [Contextualization API](#contextualization-api)
3. [Retrieval API](#retrieval-api)
4. [Ingestion API](#ingestion-api)
5. [Evaluation API](#evaluation-api)
6. [Core Pipeline API](#core-pipeline-api)
7. [Data Structures](#data-structures)
8. [Examples](#examples)

---

## CONFIG API

### Module: `src.config`

#### Settings class

```python
from src.config import Settings, APIProvider, SearchEngine

class Settings:
    """Central system configuration."""

    def __init__(
        self,
        env_file: Optional[str] = None,
        # API Configuration
        api_provider: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        groq_api_key: Optional[str] = None,
        # Model Configuration
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        # Vector Database
        qdrant_url: Optional[str] = None,
        qdrant_api_key: Optional[str] = None,
        # Paths
        data_dir: Optional[str] = None,
        docs_dir: Optional[str] = None,
        logs_dir: Optional[str] = None,
        # Search Configuration
        search_engine: Optional[str] = None,
        score_threshold: Optional[float] = None,
        top_k: Optional[int] = None,
        # Processing
        batch_size_embeddings: Optional[int] = None,
        batch_size_documents: Optional[int] = None,
        # Retry
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

#### Usage

```python
# 1. Load from .env
settings = Settings()

# 2. With overrides
settings = Settings(
    api_provider="openai",
    search_engine="baseline",
    qdrant_url="https://qdrant.example.com"
)

# 3. Access properties
print(settings.model_name)           # "claude-3-5-sonnet-20241022"
print(settings.api_provider.value)   # "claude"
print(settings.collection_name)      # "legal_documents"

# 4. Export
config_dict = settings.to_dict()
```

#### Available enumerations

```python
from src.config import APIProvider, SearchEngine, ModelName

# API providers
APIProvider.CLAUDE      # "claude" - recommended
APIProvider.OPENAI      # "openai"
APIProvider.GROQ        # "groq"
APIProvider.Z_AI        # "zai" - deprecated

# Search engines
SearchEngine.BASELINE        # Dense only
SearchEngine.HYBRID_RRF      # Dense + Sparse
SearchEngine.DBSF_COLBERT    # Best (94% Recall@1)

# LLM Models
ModelName.CLAUDE_SONNET      # claude-3-5-sonnet-20241022
ModelName.CLAUDE_HAIKU       # claude-3-5-haiku-20241022
ModelName.GPT_4_TURBO        # gpt-4-turbo-preview
ModelName.GROQ_LLAMA3_70B    # llama3-70b-8192
```

---

## CONTEXTUALIZATION API

### Module: `src.contextualization`

#### Base class: ContextualizeProvider

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

#### Claude Contextualizer ⭐

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

#### Usage

```python
import asyncio
from src.contextualization import ClaudeContextualizer, OpenAIContextualizer, GroqContextualizer

# 1. Claude (recommended)
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

    # Get stats
    stats = contextualizer.get_stats()
    print(f"Total tokens: {stats['total_tokens']}")
    print(f"Total cost: ${stats['total_cost_usd']:.4f}")

# 2. OpenAI alternative
contextualizer = OpenAIContextualizer()
result = await contextualizer.contextualize_single(
    text="Стаття 3...",
    article_number="Ст. 3"
)

# 3. Groq (fast, free)
contextualizer = GroqContextualizer()
results = await contextualizer.contextualize(chunks)

# Run
asyncio.run(contextualize_with_claude())
```

---

## RETRIEVAL API

### Module: `src.retrieval`

#### SearchEngine base class

```python
from src.retrieval import SearchEngine, SearchResult, BaselineSearchEngine
from typing import List, Optional

@dataclass
class SearchResult:
    """Single search result."""
    article_number: str        # "Ст. 1"
    text: str                  # "Право на життя..."
    score: float               # 0.95
    metadata: Dict[str, Any]   # {"chapter": "II", ...}

class BaseSearchEngine(ABC):
    """Abstract base class for search engines."""

    def __init__(self, settings: Optional[Settings] = None):
        """Initialize search engine."""
        pass

    @abstractmethod
    def search(
        self,
        query_embedding: List[float],  # 1024-dim BGE-M3 vector
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

#### 3 implementations

```python
from src.retrieval import (
    BaselineSearchEngine,      # 91.3% Recall@1
    HybridRRFSearchEngine,     # 88.7% Recall@1
    DBSFColBERTSearchEngine,   # 94.0% Recall@1 ⭐
    create_search_engine
)

# 1. Baseline (Dense only)
engine = BaselineSearchEngine()
results = engine.search(query_embedding, top_k=5)

# 2. Hybrid RRF (Dense + Sparse)
engine = HybridRRFSearchEngine()
results = engine.search(query_embedding, top_k=5)

# 3. DBSF+ColBERT (Best result)
engine = DBSFColBERTSearchEngine()
results = engine.search(query_embedding, top_k=5)

# Factory function
engine = create_search_engine(
    engine_type=SearchEngine.DBSF_COLBERT,
    settings=settings
)

# Usage
for result in results:
    print(f"{result.article_number}")
    print(f"Text: {result.text[:100]}...")
    print(f"Score: {result.score:.4f}")
    print(f"Metadata: {result.metadata}")
```

---

## INGESTION API

### Module: `src.ingestion`

#### 1. PDFParser

```python
from src.ingestion import PDFParser, ParsedDocument

parser = PDFParser()

# Parse single file
doc = parser.parse_file("path/to/document.pdf")
# ParsedDocument(
#     filename="document.pdf",
#     title="Document Title",
#     content="Full text...",
#     num_pages=150,
#     metadata={...}
# )

# Parse directory
docs = parser.parse_directory(
    dirpath="docs/documents/",
    pattern="*.pdf"
)

# Parse multiple files
docs = parser.parse_multiple([
    "file1.pdf",
    "file2.pdf",
    "file3.pdf"
])
```

#### 2. DocumentChunker

```python
from src.ingestion import DocumentChunker, ChunkingStrategy, Chunk

chunker = DocumentChunker(
    chunk_size=512,        # Target size in characters
    overlap=128,           # Overlap between chunks
    strategy=ChunkingStrategy.SEMANTIC  # or FIXED_SIZE, SLIDING_WINDOW
)

# Chunk text
chunks = chunker.chunk_text(
    text=doc.content,
    document_name="Конституція_України",
    article_number="Ст. 1"
)

# Result: List[Chunk]
for chunk in chunks:
    print(f"Chunk {chunk.chunk_id}: {chunk.text[:50]}...")
    print(f"Article: {chunk.article_number}")
    print(f"Order: {chunk.order}")
    print()

# Chunking strategies
ChunkingStrategy.FIXED_SIZE      # Fixed size
ChunkingStrategy.SEMANTIC        # By semantic boundaries
ChunkingStrategy.SLIDING_WINDOW  # Sliding window with overlap
```

#### 3. DocumentIndexer

```python
from src.ingestion import DocumentIndexer, IndexStats

indexer = DocumentIndexer(settings)

# Create collection
indexer.create_collection(
    collection_name="legal_documents",
    recreate=False  # True to drop and recreate
)

# Index chunks
stats = await indexer.index_chunks(
    chunks=chunks,
    collection_name="legal_documents",
    batch_size=16
)

# IndexStats
print(f"Total chunks: {stats.total_chunks}")
print(f"Indexed: {stats.indexed_chunks}")
print(f"Failed: {stats.failed_chunks}")
print(f"Duration: {stats.duration_seconds:.1f}s")

# Get collection info
info = indexer.get_collection_stats("legal_documents")
# {
#     "name": "legal_documents",
#     "points_count": 1234,
#     "vectors_count": 1234,
#     "indexed_vectors_count": 1234,
#     "segment_count": 2
# }
```

---

## EVALUATION API

### Module: `src.evaluation`

#### Metrics

```python
from src.evaluation import (
    compute_recall_at_k,
    compute_ndcg_at_k,
    compute_mrr,
    compute_map
)

# Compute metrics
recall = compute_recall_at_k(
    predicted_ranks=[1, 2, 5],  # Ranks of correct results
    k=10
)

ndcg = compute_ndcg_at_k(
    scores=[0.95, 0.87, 0.72],  # Scores of retrieved results
    k=10
)

mrr = compute_mrr(predicted_ranks=[3])  # Mean Reciprocal Rank
```

#### MLflow Integration

```python
from src.evaluation import mlflow_integration
import mlflow

# Start experiment
mlflow.set_experiment("RAG Search Quality")

with mlflow.start_run():
    # Log parameters
    mlflow.log_params({
        "search_engine": "dbsf_colbert",
        "api_provider": "claude",
        "top_k": 10
    })

    # Log metrics
    mlflow.log_metrics({
        "recall_at_1": 0.94,
        "recall_at_10": 0.993,
        "ndcg_at_10": 0.9711,
        "mrr": 0.9636,
        "latency_seconds": 0.69
    })

    # Log model
    mlflow.log_artifact("model.pkl")

# View results
# mlflow ui --host 127.0.0.1 --port 5000
```

#### Langfuse Integration

```python
from src.evaluation import langfuse_integration
from langfuse import Langfuse

langfuse = Langfuse()

# Trace LLM call
with langfuse.trace(name="search") as trace:
    result = await pipeline.search("query")

    trace.log_output(result)
    # View at https://langfuse.com
```

#### Run A/B Test

```bash
python src/evaluation/run_ab_test.py \
  --queries data/test_queries/queries.json \
  --baseline baseline \
  --challenger dbsf_colbert \
  --num_queries 150

# Results:
# Baseline:       Recall@1=91.3%, NDCG@10=0.9619
# DBSF+ColBERT:   Recall@1=94.0%, NDCG@10=0.9711
# Improvement:    +2.9% Recall, +1.0% NDCG ⭐
```

---

## CORE PIPELINE API

### RAGPipeline - Main class

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

#### Usage

```python
import asyncio

async def main():
    # 1. Initialize
    pipeline = RAGPipeline()

    # 2. Index documents
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

    # 3. Search
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

    # 4. Evaluate
    test_queries = [
        "Які права мають громадяни?",
        "Що таке конституція?",
        "Де знаходиться глава про права?",
    ]

    metrics = await pipeline.evaluate(
        queries=test_queries,
        ground_truth=None  # Optional
    )

    print(f"\nAverage latency: {metrics['average_latency']:.3f}s")

    # 5. Get stats
    stats = pipeline.get_stats()
    print(f"\nPipeline stats:")
    print(f"API: {stats['api_provider']}")
    print(f"Model: {stats['model']}")
    print(f"Search: {stats['search_engine']}")

# Run
asyncio.run(main())
```

---

## DATA STRUCTURES

### ContextualizedChunk

```python
@dataclass
class ContextualizedChunk:
    """Chunk with LLM-generated context."""

    original_text: str              # Original text
    contextual_summary: str         # LLM-generated summary
    article_number: str             # "Ст. 1"
    chapter: Optional[str] = None   # "II"
    section: Optional[str] = None   # "Розділ"
    context_method: str = "none"    # "claude", "openai", "groq"
    timestamp: datetime = None

    @property
    def full_text(self) -> str:
        """Combined original + context."""
        return f"{self.contextual_summary}\n\n{self.original_text}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        pass
```

### SearchResult

```python
@dataclass
class SearchResult:
    """Single search result."""

    article_number: str        # "Ст. 1"
    text: str                  # Document text
    score: float               # Relevance score (0-1)
    metadata: Dict[str, Any]   # Additional metadata
```

### RAGResult

```python
@dataclass
class RAGResult:
    """Result from RAG pipeline.search()."""

    query: str                          # Original query
    results: List[Dict[str, Any]]       # Search results
    context_used: bool                  # Was contextualization used
    search_method: str                  # "baseline", "hybrid_rrf", "dbsf_colbert"
    execution_time: float               # Query time in seconds
```

---

## EXAMPLES

### Example 1: Simple search

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

### Example 2: Full workflow

```python
import asyncio
from src.core import RAGPipeline
from src.config import Settings, APIProvider, SearchEngine

async def full_workflow():
    # Custom settings
    settings = Settings(
        api_provider=APIProvider.CLAUDE,
        search_engine=SearchEngine.DBSF_COLBERT,
        qdrant_url="http://localhost:6333",
        top_k=10
    )

    pipeline = RAGPipeline(settings)

    # 1. Index
    print("Indexing documents...")
    stats = await pipeline.index_documents(
        pdf_paths=["docs/documents/Конституція_України.pdf"],
        collection_name="legal_documents"
    )
    print(f"Indexed {stats['indexed_chunks']} chunks")

    # 2. Search multiple queries
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

### Example 3: Different providers

```python
import asyncio
from src.contextualization import (
    ClaudeContextualizer,
    OpenAIContextualizer,
    GroqContextualizer
)

async def compare_providers():
    text = "Стаття 1. Право на життя..."

    # Claude
    contextualizer = ClaudeContextualizer()
    result = await contextualizer.contextualize_single(
        text, "Ст. 1"
    )
    print(f"Claude: {result.contextual_summary[:50]}...")

    # OpenAI
    contextualizer = OpenAIContextualizer()
    result = await contextualizer.contextualize_single(
        text, "Ст. 1"
    )
    print(f"OpenAI: {result.contextual_summary[:50]}...")

    # Groq (fastest, free)
    contextualizer = GroqContextualizer()
    result = await contextualizer.contextualize_single(
        text, "Ст. 1"
    )
    print(f"Groq: {result.contextual_summary[:50]}...")

asyncio.run(compare_providers())
```

---

## 🎯 Best Practices

### 1. Configuration

```python
# ✅ Good: Use Settings
from src.config import Settings
settings = Settings()

# ❌ Bad: Hardcode values
QDRANT_URL = "http://localhost:6333"
```

### 2. Context Managers

```python
# ✅ Good: Use async context
async with create_pipeline() as pipeline:
    result = await pipeline.search("query")

# ❌ Bad: Don't clean up resources
pipeline = create_pipeline()
result = pipeline.search("query")
```

### 3. Error Handling

```python
# ✅ Good: Handle errors
try:
    result = await pipeline.search("query")
except ConnectionError:
    print("Qdrant is not available")
except ValueError as e:
    print(f"Invalid query: {e}")

# ❌ Bad: Ignore errors
result = await pipeline.search("query")
```

### 4. Batch Processing

```python
# ✅ Good: Process in batches
queries = ["q1", "q2", "q3", ...]
for batch in chunks(queries, batch_size=10):
    results = [await pipeline.search(q) for q in batch]

# ❌ Bad: One by one
for query in queries:
    result = await pipeline.search(query)  # Slow!
```

---

**Last Updated**: October 29, 2025
**Version**: 2.0.1
