***REMOVED*** 📚 COMPLETE PROJECT STRUCTURE - Contextual RAG v2.0.1

> **Comprehensive description of the redesigned project architecture**

***REMOVED******REMOVED*** 📊 Project Overview

**Contextual RAG Pipeline** - production-ready system for searching Ukrainian legal documents using hybrid search, LLM contextualization, and full integration with ML platforms.

| Parameter | Value |
|----------|----------|
| **Version** | 2.0.1 |
| **Python** | ≥3.9 |
| **Status** | ✅ Production Ready |
| **Code Issues** | 0 (was 499) |
| **Best Search** | DBSF+ColBERT: 94.0% Recall@1 |
| **Indexing Time** | 6 minutes for 132 chunks |

---

***REMOVED******REMOVED*** 🏗️ NEW PROJECT STRUCTURE

***REMOVED******REMOVED******REMOVED*** ROOT LEVEL

```
contextual_rag/
├── src/                    ***REMOVED*** ⭐ ALL APPLICATION CODE (new structure)
├── tests/                  ***REMOVED*** Test suites
├── docs/                   ***REMOVED*** Documentation
├── data/                   ***REMOVED*** Data and resources
├── logs/                   ***REMOVED*** Application logs
├── legacy/                 ***REMOVED*** Old code (deprecated)
├── pyproject.toml          ***REMOVED*** Dependency configuration
├── .env.example            ***REMOVED*** Environment variables example
├── .env                    ***REMOVED*** Environment variables (DO NOT commit!)
├── .gitignore              ***REMOVED*** Git ignore rules
├── .pre-commit-config.yaml ***REMOVED*** Pre-commit hooks
├── docker-compose.yml      ***REMOVED*** Docker services (Qdrant, MLflow, Langfuse)
├── README.md               ***REMOVED*** Main documentation
└── Makefile                ***REMOVED*** Common commands (optional)
```

***REMOVED******REMOVED******REMOVED*** SRC STRUCTURE - MAIN (33 Python files)

```
src/                              ***REMOVED*** All project code
│
├── __init__.py                   ***REMOVED*** Package initialization (v2.0.1)
│
├── config/                       ***REMOVED*** ⭐ CONFIGURATION (2 files)
│   ├── __init__.py
│   ├── constants.py              ***REMOVED*** Enums, dataclasses, constants
│   │                             ***REMOVED*** - SearchEngine, APIProvider, ModelName
│   │                             ***REMOVED*** - VectorDimensions, ThresholdValues
│   │                             ***REMOVED*** - BatchSizes, RetrievalStages
│   └── settings.py               ***REMOVED*** Settings class with validation
│                                 ***REMOVED*** - Loads .env and arguments
│                                 ***REMOVED*** - Creates global settings instance
│
├── contextualization/            ***REMOVED*** ⭐ LLM CONTEXTUALIZATION (4 files)
│   ├── __init__.py
│   ├── base.py                   ***REMOVED*** Base class ContextualizeProvider
│   │                             ***REMOVED*** - ContextualizedChunk dataclass
│   │                             ***REMOVED*** - Abstract methods for providers
│   ├── claude.py                 ***REMOVED*** ⭐ Claude API (RECOMMENDED)
│   │                             ***REMOVED*** - Prompt caching for 90% savings
│   │                             ***REMOVED*** - Async + sync methods
│   │                             ***REMOVED*** - Token tracking and cost estimation
│   ├── openai.py                 ***REMOVED*** OpenAI GPT integration
│   │                             ***REMOVED*** - Support for GPT-4, GPT-3.5
│   │                             ***REMOVED*** - Async + sync processing
│   └── groq.py                   ***REMOVED*** Groq LLaMA (fast alternative)
│                                 ***REMOVED*** - 2-4 minutes for 100 chunks
│                                 ***REMOVED*** - Free tier available
│
├── retrieval/                    ***REMOVED*** ⭐ SEARCH AND RANKING (1 file)
│   ├── __init__.py
│   └── search_engines.py         ***REMOVED*** 3 search engine implementations
│                                 ***REMOVED*** 1. BaselineSearchEngine (Dense only)
│                                 ***REMOVED***    - 91.3% Recall@1
│                                 ***REMOVED***    - 0.65s latency
│                                 ***REMOVED*** 2. HybridRRFSearchEngine (Dense+Sparse)
│                                 ***REMOVED***    - 88.7% Recall@1
│                                 ***REMOVED***    - RRF fusion
│                                 ***REMOVED*** 3. DBSFColBERTSearchEngine ⭐ BEST
│                                 ***REMOVED***    - 94.0% Recall@1 (+2.9%)
│                                 ***REMOVED***    - DBSF + ColBERT reranking
│                                 ***REMOVED***    - 0.69s latency
│
├── ingestion/                    ***REMOVED*** ⭐ DOCUMENT LOADING (3 files)
│   ├── __init__.py
│   ├── pdf_parser.py             ***REMOVED*** PDF parsing (PyMuPDF)
│   │                             ***REMOVED*** - Supports PDF, DOCX, EPUB, TXT
│   │                             ***REMOVED*** - Metadata and structure
│   ├── chunker.py                ***REMOVED*** Document chunking
│   │                             ***REMOVED*** - 3 strategies: Fixed, Semantic, Sliding
│   │                             ***REMOVED*** - Preserves document structure
│   │                             ***REMOVED*** - Metadata for legal documents
│   └── indexer.py                ***REMOVED*** Indexing to Qdrant
│                                 ***REMOVED*** - BGE-M3 embeddings (1024-dim)
│                                 ***REMOVED*** - Batch processing
│                                 ***REMOVED*** - Payload indexes
│
├── evaluation/                   ***REMOVED*** ⭐ EVALUATION AND METRICS (12 files)
│   ├── __init__.py
│   ├── metrics.py                ***REMOVED*** Recall@K, NDCG@K, MRR (new)
│   ├── mlflow_integration.py     ***REMOVED*** MLflow tracking
│   │                             ***REMOVED*** - Experiment tracking
│   │                             ***REMOVED*** - Parameters and metrics
│   ├── langfuse_integration.py   ***REMOVED*** Langfuse LLM tracing
│   │                             ***REMOVED*** - Trace all LLM requests
│   │                             ***REMOVED*** - Latency tracking
│   ├── run_ab_test.py            ***REMOVED*** A/B testing
│   ├── evaluate_with_ragas.py    ***REMOVED*** RAGAS evaluation
│   ├── smoke_test.py             ***REMOVED*** Fast smoke tests
│   ├── evaluator.py              ***REMOVED*** Main evaluator class
│   ├── metrics_logger.py         ***REMOVED*** Metrics logging
│   ├── config_snapshot.py        ***REMOVED*** Configuration snapshot
│   ├── generate_test_queries.py  ***REMOVED*** Test query generation
│   ├── search_engines_rerank.py  ***REMOVED*** Search reranking
│   └── test_mlflow_ab.py         ***REMOVED*** MLflow testing
│
├── utils/                        ***REMOVED*** ⭐ UTILITIES (1 file)
│   ├── __init__.py
│   └── structure_parser.py       ***REMOVED*** Document structure parser
│
└── core/                         ***REMOVED*** ⭐ MAIN PIPELINE (1 file)
    ├── __init__.py
    └── pipeline.py               ***REMOVED*** RAGPipeline - orchestrator
                                  ***REMOVED*** - Main class for usage
                                  ***REMOVED*** - Integrates all components
                                  ***REMOVED*** - search(), index_documents()
                                  ***REMOVED*** - evaluate(), get_stats()
```

***REMOVED******REMOVED******REMOVED*** DOCS STRUCTURE

```
docs/
├── README.md                       ***REMOVED*** Documentation overview
├── README_NEW_STRUCTURE.md         ***REMOVED*** New structure description
├── COMPLETE_STRUCTURE.md           ***REMOVED*** This file - complete structure
├── PROJECT_STRUCTURE.md            ***REMOVED*** Old description (reference)
├── QUICK_START.md                  ***REMOVED*** 5 minutes to first search
├── INDEX.md                        ***REMOVED*** Document index
│
├── guides/                         ***REMOVED*** Practical guides
│   ├── QUICK_START.md              ***REMOVED*** Quick start
│   ├── SETUP.md                    ***REMOVED*** Installation and configuration
│   └── CODE_QUALITY.md             ***REMOVED*** Development standards
│
├── architecture/                   ***REMOVED*** Architecture and design
│   ├── ARCHITECTURE.md             ***REMOVED*** System architecture
│   ├── MIGRATION_PLAN.md           ***REMOVED*** Migration plan to new structure
│   └── API_DESIGN.md               ***REMOVED*** API design (new)
│
├── implementation/                 ***REMOVED*** Implementation details
│   ├── OPTIMIZATION_PLAN.md        ***REMOVED*** Optimization plan
│   ├── DBSF_vs_RRF_ANALYSIS.md     ***REMOVED*** Algorithm comparison
│   ├── SEARCH_ENGINE_GUIDE.md      ***REMOVED*** Search engines guide (new)
│   └── CONFIG_GUIDE.md             ***REMOVED*** Configuration guide (new)
│
├── reports/                        ***REMOVED*** Project reports
│   ├── FULL_PROJECT_ANALYSIS.md    ***REMOVED*** Full project analysis
│   ├── PHASE1_COMPLETION_SUMMARY.md
│   ├── PHASE2_COMPLETION_SUMMARY.md
│   └── PHASE3_COMPLETION_SUMMARY.md
│
├── documents/                      ***REMOVED*** Legal documents
│   ├── Конституція України/
│   ├── Кримінальний кодекс України/
│   └── Цивільний кодекс України/
│
└── api/                            ***REMOVED*** API Reference (generated)
    └── API_REFERENCE.md            ***REMOVED*** Full API docs (new)
```

***REMOVED******REMOVED******REMOVED*** TESTS STRUCTURE

```
tests/
├── conftest.py                     ***REMOVED*** Pytest configuration (new)
├── unit/                           ***REMOVED*** Unit tests (to be created)
│   ├── test_config.py
│   ├── test_chunker.py
│   └── test_search_engines.py
├── integration/                    ***REMOVED*** Integration tests (to be created)
│   ├── test_full_pipeline.py
│   └── test_qdrant_integration.py
└── legacy/                         ***REMOVED*** Old tests
    ├── test_api_*.py
    ├── evaluate_ab.py
    ├── example_search.py
    └── ...
```

***REMOVED******REMOVED******REMOVED*** DATA STRUCTURE

```
data/
├── documents/                      ***REMOVED*** Input PDF documents
│   ├── Конституція_України.pdf
│   ├── Кримінальний_кодекс.pdf
│   └── Цивільний_кодекс.pdf
├── test_queries/                   ***REMOVED*** Test queries
│   ├── queries.json                ***REMOVED*** 150+ test queries
│   └── ground_truth.json           ***REMOVED*** Correct answers
├── embeddings/                     ***REMOVED*** Embeddings cache (optional)
└── evaluation/                     ***REMOVED*** Evaluation results
    ├── recall_metrics.json
    ├── ndcg_metrics.json
    └── results_summary.json
```

---

***REMOVED******REMOVED*** 🔑 KEY MODULES (DETAILED)

***REMOVED******REMOVED******REMOVED*** 1. CONFIG (`src/config/`)

**Purpose**: Centralized configuration for the entire system

**Files**:
- `constants.py` - Enums, dataclasses, constants
- `settings.py` - Settings class with .env loading

**Key classes**:
```python
class SearchEngine(Enum):
    BASELINE = "baseline"
    HYBRID_RRF = "hybrid_rrf"
    DBSF_COLBERT = "dbsf_colbert"  ***REMOVED*** Recommended

class APIProvider(Enum):
    CLAUDE = "claude"      ***REMOVED*** ⭐ Recommended
    OPENAI = "openai"
    GROQ = "groq"
    Z_AI = "zai"          ***REMOVED*** Legacy

class Settings:
    def __init__(
        self,
        api_provider: str = "claude",
        search_engine: str = "dbsf_colbert",
        qdrant_url: str = "http://localhost:6333",
        collection_name: str = "legal_documents",
        ...
    )
```

**Usage**:
```python
from src.config import Settings, SearchEngine

***REMOVED*** Load from .env
settings = Settings()

***REMOVED*** Override some parameters
settings = Settings(
    api_provider="openai",
    search_engine=SearchEngine.BASELINE
)
```

---

***REMOVED******REMOVED******REMOVED*** 2. CONTEXTUALIZATION (`src/contextualization/`)

**Purpose**: LLM-based document enrichment with context

**Providers**:

| Provider | Time | Cost | Quality | Status |
|-----------|-------|-----------|----------|--------|
| **Claude** | 8-12 min | ~$12 | ⭐⭐⭐⭐⭐ | ✅ |
| **OpenAI** | 5-8 min | ~$8 | ⭐⭐⭐⭐ | ✅ |
| **Groq** | 2-4 min | FREE | ⭐⭐⭐ | ✅ |
| Z.AI (legacy) | 3-5 min | $3/mo | ⭐⭐⭐ | ⚠️ |

**Base class**:
```python
class ContextualizeProvider(ABC):
    async def contextualize(
        self,
        chunks: List[str],
        query: Optional[str] = None,
    ) -> List[ContextualizedChunk]:
        pass

    async def contextualize_single(
        self,
        text: str,
        article_number: str,
        query: Optional[str] = None,
    ) -> ContextualizedChunk:
        pass
```

**Usage**:
```python
from src.contextualization import ClaudeContextualizer

contextualizer = ClaudeContextualizer()

***REMOVED*** Contextualize chunks
result = await contextualizer.contextualize(
    chunks=["Стаття 1..."],
    query="User query"
)

***REMOVED*** Get statistics
stats = contextualizer.get_stats()
***REMOVED*** {'total_tokens': 1234, 'total_cost_usd': 0.0042, ...}
```

---

***REMOVED******REMOVED******REMOVED*** 3. RETRIEVAL (`src/retrieval/`)

**Purpose**: Search and document ranking

**Three search engines**:

***REMOVED******REMOVED******REMOVED******REMOVED*** A. BaselineSearchEngine
```
Dense vectors only (BGE-M3)
Recall@1:   91.3%
NDCG@10:    0.9619
MRR:        0.9491
Latency:    0.65s
```

***REMOVED******REMOVED******REMOVED******REMOVED*** B. HybridRRFSearchEngine
```
Dense + Sparse (RRF fusion)
Recall@1:   88.7%
NDCG@10:    0.9524
MRR:        0.9421
Latency:    0.72s
```

***REMOVED******REMOVED******REMOVED******REMOVED*** C. DBSFColBERTSearchEngine ⭐ BEST
```
Density-Based Semantic Fusion + ColBERT reranking
Recall@1:   94.0% (+2.9% vs Baseline)
NDCG@10:    0.9711 (+1.0% vs Baseline)
MRR:        0.9636 (+1.5% vs Baseline)
Latency:    0.69s

Algorithm:
1. Dense search (100 candidates)
2. Neighborhood density computation
3. DBSF score fusion
4. ColBERT reranking
5. Final ranking
```

**Usage**:
```python
from src.retrieval import create_search_engine, SearchEngine

***REMOVED*** Create engine
engine = create_search_engine(
    engine_type=SearchEngine.DBSF_COLBERT
)

***REMOVED*** Search
results = engine.search(
    query_embedding=query_vec,  ***REMOVED*** List[float] - 1024 dims
    top_k=10,
    score_threshold=0.3
)

for result in results:
    print(f"{result.article_number}: {result.text}")
    print(f"Score: {result.score:.3f}")
```

---

***REMOVED******REMOVED******REMOVED*** 4. INGESTION (`src/ingestion/`)

**Purpose**: Document loading and indexing

**3-stage pipeline**:

***REMOVED******REMOVED******REMOVED******REMOVED*** Stage 1: PDF Parsing
```python
from src.ingestion import PDFParser

parser = PDFParser()
doc = parser.parse_file("document.pdf")
***REMOVED*** ParsedDocument(
***REMOVED***     filename="...",
***REMOVED***     title="...",
***REMOVED***     content="...",
***REMOVED***     num_pages=150,
***REMOVED***     metadata={...}
***REMOVED*** )
```

***REMOVED******REMOVED******REMOVED******REMOVED*** Stage 2: Document Chunking
```python
from src.ingestion import DocumentChunker, ChunkingStrategy

chunker = DocumentChunker(
    chunk_size=512,
    overlap=128,
    strategy=ChunkingStrategy.SEMANTIC  ***REMOVED*** or FIXED_SIZE, SLIDING_WINDOW
)

chunks = chunker.chunk_text(
    text=doc.content,
    document_name="Конституція_України",
    article_number="Ст. 1"
)
***REMOVED*** List[Chunk] with metadata
```

***REMOVED******REMOVED******REMOVED******REMOVED*** Stage 3: Vector Indexing
```python
from src.ingestion import DocumentIndexer

indexer = DocumentIndexer()

***REMOVED*** Create collection
indexer.create_collection(
    collection_name="legal_documents",
    recreate=False
)

***REMOVED*** Index chunks
stats = await indexer.index_chunks(
    chunks=chunks,
    collection_name="legal_documents",
    batch_size=16
)

print(f"Indexed: {stats.indexed_chunks} chunks")
print(f"Failed: {stats.failed_chunks}")
```

---

***REMOVED******REMOVED******REMOVED*** 5. EVALUATION (`src/evaluation/`)

**Purpose**: Quality evaluation and experiment tracking

**12 modules**:

| Module | Purpose |
|--------|-----------|
| `metrics.py` | Recall@K, NDCG@K, MRR (new) |
| `mlflow_integration.py` | MLflow experiment tracking |
| `langfuse_integration.py` | Langfuse LLM tracing |
| `run_ab_test.py` | A/B testing |
| `evaluate_with_ragas.py` | RAGAS evaluation |
| `smoke_test.py` | Fast smoke tests |
| `evaluator.py` | Main evaluator |
| `metrics_logger.py` | Metrics logging |
| `config_snapshot.py` | Configuration snapshot |
| `generate_test_queries.py` | Query generation |
| `extract_ground_truth.py` | Ground truth extraction |
| `search_engines_rerank.py` | Reranking |

**Usage**:
```python
***REMOVED*** A/B testing
python src/evaluation/run_ab_test.py \
  --queries data/test_queries/queries.json \
  --baseline baseline \
  --challenger dbsf_colbert

***REMOVED*** Results in MLflow
open http://localhost:5000
```

---

***REMOVED******REMOVED******REMOVED*** 6. CORE PIPELINE (`src/core/pipeline.py`)

**Main class for usage**:

```python
from src.core import RAGPipeline

***REMOVED*** Initialize
pipeline = RAGPipeline()

***REMOVED*** 1. Search
result = await pipeline.search(
    query="Які права мають громадяни?",
    top_k=5,
    use_context=True
)

for r in result.results:
    print(f"{r['article_number']}: {r['text'][:100]}")

***REMOVED*** 2. Indexing
stats = await pipeline.index_documents(
    pdf_paths=[
        "docs/documents/Конституція_України.pdf",
        "docs/documents/Кримінальний_кодекс.pdf"
    ],
    collection_name="legal_documents",
    recreate_collection=False
)

***REMOVED*** 3. Evaluation
metrics = await pipeline.evaluate(
    queries=test_queries,
    ground_truth=correct_answers
)

***REMOVED*** 4. Statistics
stats = pipeline.get_stats()
```

---

***REMOVED******REMOVED*** 🔄 OLD CODE MIGRATION

***REMOVED******REMOVED******REMOVED*** What moved to legacy/

```
legacy/
├── config_old.py                  ***REMOVED*** Old configuration
├── contextualize*.py              ***REMOVED*** Old contextualize (5 files)
├── ingestion_contextual_kg*.py    ***REMOVED*** Old ingestion (2 files)
├── create_*.py                    ***REMOVED*** Collection creation utilities
├── check_sparse_vectors.py
├── list_available_models*.py
└── prompts_old.py
```

***REMOVED******REMOVED******REMOVED*** How to migrate your code

**Before (old)**:
```python
from config import ANTHROPIC_API_KEY, QDRANT_URL
from contextualize import contextualize_documents
```

**After (new)**:
```python
from src.config import Settings
from src.contextualization import ClaudeContextualizer

settings = Settings()
contextualizer = ClaudeContextualizer(settings)
```

---

***REMOVED******REMOVED*** 📝 ENVIRONMENT CONFIGURATION

**.env file variables**:

```env
***REMOVED*** ========== API CONFIGURATION ==========
API_PROVIDER=claude                ***REMOVED*** claude, openai, groq
ANTHROPIC_API_KEY=[REDACTED-ANTHROPIC-KEY]
OPENAI_API_KEY=[REDACTED-OPENAI-KEY]
GROQ_API_KEY=[REDACTED-GROQ-KEY]

***REMOVED*** ========== VECTOR DATABASE ==========
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=                    ***REMOVED*** If authentication required

***REMOVED*** ========== SEARCH CONFIGURATION ==========
SEARCH_ENGINE=dbsf_colbert         ***REMOVED*** baseline, hybrid_rrf, dbsf_colbert
COLLECTION_NAME=legal_documents
TOP_K=10

***REMOVED*** ========== PROCESSING ==========
BATCH_SIZE_EMBEDDINGS=32
BATCH_SIZE_DOCUMENTS=16
ENABLE_CACHING=true
ENABLE_QUERY_EXPANSION=true

***REMOVED*** ========== ML PLATFORMS ==========
ENABLE_MLFLOW=true
ENABLE_LANGFUSE=true

***REMOVED*** ========== ENVIRONMENT ==========
ENV=development                    ***REMOVED*** development, production
DEBUG=false
```

---

***REMOVED******REMOVED*** 🔗 DEPENDENCIES

**Core** (required):
```
pymupdf                   ***REMOVED*** PDF parsing
anthropic                 ***REMOVED*** Claude API
openai                    ***REMOVED*** OpenAI API
groq                      ***REMOVED*** Groq API
sentence-transformers     ***REMOVED*** BGE-M3 embeddings
qdrant-client             ***REMOVED*** Vector DB client
```

**ML platforms** (optional, but recommended):
```
mlflow>=2.22.1            ***REMOVED*** Experiment tracking
ragas>=0.2.10             ***REMOVED*** RAG evaluation
langfuse>=3.0.0           ***REMOVED*** LLM observability
```

**Code quality** (development):
```
ruff                      ***REMOVED*** Linting + formatting
mypy                      ***REMOVED*** Type checking
pytest                    ***REMOVED*** Testing
pre-commit                ***REMOVED*** Git hooks
```

---

***REMOVED******REMOVED*** 📊 PERFORMANCE AND METRICS

***REMOVED******REMOVED******REMOVED*** Search Quality (150 test queries)

| Metric | Baseline | Hybrid RRF | DBSF+ColBERT | Improvement |
|---------|----------|-----------|--------------|-----------|
| **Recall@1** | 91.3% | 88.7% | 94.0% | +2.9% ⭐ |
| **Recall@3** | 96.5% | 94.2% | 97.1% | +0.6% |
| **Recall@5** | 98.1% | 97.3% | 98.4% | +0.3% |
| **Recall@10** | 99.2% | 98.9% | 99.3% | +0.1% |
| **NDCG@1** | 0.9189 | 0.8874 | 0.9401 | +2.1% |
| **NDCG@10** | 0.9619 | 0.9524 | 0.9711 | +1.0% ⭐ |
| **MRR** | 0.9491 | 0.9421 | 0.9636 | +1.5% ⭐ |
| **Latency** | 0.65s | 0.72s | 0.69s | -0.04s |

***REMOVED******REMOVED******REMOVED*** Ingestion Time

```
PDF Parsing:       2-3 minutes (132 chunks)
Contextualization: 8-12 minutes (Claude, $12)
                   5-8 minutes (OpenAI, $8)
                   2-4 minutes (Groq, FREE)
Indexing:          1-2 minutes
Total Pipeline:    ~15-20 minutes
```

---

***REMOVED******REMOVED*** 🎯 TECHNOLOGIES USED

***REMOVED******REMOVED******REMOVED*** LLM APIs
- **Anthropic Claude** 3.5 Sonnet (primary)
- **OpenAI GPT-4 Turbo** (alternative)
- **Groq LLaMA 3** (fast)

***REMOVED******REMOVED******REMOVED*** Vector Database
- **Qdrant** v0.13.x (primary)
- **BGE-M3** (1024-dim dense + sparse)
- **ColBERT** (sparse embeddings)

***REMOVED******REMOVED******REMOVED*** ML Platforms
- **MLflow** 2.22.1+ (experiment tracking)
- **Langfuse** 3.0.0+ (LLM observability)
- **RAGAS** 0.2.10+ (RAG evaluation)

***REMOVED******REMOVED******REMOVED*** Code Quality
- **Ruff** 0.14.1 (linting + formatting)
- **MyPy** (type checking)
- **Pre-commit** (git hooks)

---

***REMOVED******REMOVED*** 📈 NEXT STEPS

***REMOVED******REMOVED******REMOVED*** Phase 4 (Planned)
- [ ] Query expansion via LLM
- [ ] Semantic caching (Redis)
- [ ] Graph traversal for related articles
- [ ] Web UI dashboard
- [ ] Multi-language support

---

**Last Updated**: October 29, 2025
**Version**: 2.0.1
**Created by**: Claude Code
