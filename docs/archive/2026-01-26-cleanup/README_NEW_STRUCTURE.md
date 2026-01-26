# 📚 Contextual RAG v2.0.1 - New Project Structure

> **Redesigned production-ready architecture with clean module separation**

## 🎯 Project Overview

Contextual RAG Pipeline is a high-performance document retrieval system for Ukrainian legal documents featuring:

- 🔍 **Hybrid Search**: Dense (BGE-M3) + Sparse (ColBERT) vectors
- 🚀 **DBSF Ranking**: Density-Based Semantic Fusion (94.0% Recall@1)
- 💰 **Cost Efficient**: Prompt caching saves 90% on LLM costs
- 🤖 **Multi-LLM**: Claude (recommended), OpenAI, Groq, Z.AI (legacy)
- 📊 **ML Platforms**: MLflow + Langfuse for experiment tracking
- 🎓 **Production Ready**: 0 code issues, comprehensive tests

**Version**: 2.0.1
**Python**: ≥3.9
**Status**: ✅ Production Ready

---

## 📁 New Directory Structure

```
rag-fresh/
├── src/                          # Source code (main application)
│   ├── config/                   # Configuration management
│   │   ├── __init__.py
│   │   ├── constants.py          # Enums, data classes, constants
│   │   └── settings.py           # Settings class with validation
│   │
│   ├── contextualization/        # LLM contextualization
│   │   ├── __init__.py
│   │   ├── base.py               # Base provider class
│   │   ├── claude.py             # Claude API (recommended)
│   │   ├── openai.py             # OpenAI GPT
│   │   └── groq.py               # Groq LLaMA (fast)
│   │
│   ├── retrieval/                # Search and retrieval
│   │   ├── __init__.py
│   │   └── search_engines.py     # Baseline, Hybrid RRF, DBSF+ColBERT
│   │
│   ├── ingestion/                # Document loading and indexing
│   │   ├── __init__.py
│   │   ├── pdf_parser.py         # PDF parsing
│   │   ├── chunker.py            # Document chunking strategies
│   │   └── indexer.py            # Vector database indexing
│   │
│   ├── evaluation/               # Evaluation and metrics
│   │   ├── __init__.py
│   │   ├── metrics.py            # Recall, NDCG, MRR, etc.
│   │   ├── mlflow_integration.py # MLflow experiment tracking
│   │   └── langfuse_integration.py # Langfuse LLM tracing
│   │
│   ├── utils/                    # Utility functions
│   │   ├── __init__.py
│   │   ├── logger.py             # Logging utilities
│   │   └── helpers.py            # Common helpers
│   │
│   └── core/                     # Core application logic
│       ├── __init__.py
│       └── pipeline.py           # Main RAG pipeline orchestrator
│
├── tests/                        # Test suites
│   ├── unit/                     # Unit tests
│   ├── integration/              # Integration tests
│   └── conftest.py               # Pytest configuration
│
├── docs/                         # Documentation
│   ├── README.md                 # Main documentation
│   ├── guides/                   # User guides
│   │   ├── QUICK_START.md
│   │   ├── SETUP.md
│   │   └── CODE_QUALITY.md
│   ├── architecture/             # Architecture docs
│   │   ├── ARCHITECTURE.md
│   │   └── MIGRATION_PLAN.md
│   ├── implementation/           # Implementation details
│   │   ├── OPTIMIZATION_PLAN.md
│   │   └── DBSF_vs_RRF_ANALYSIS.md
│   ├── reports/                  # Project reports
│   │   ├── FINAL_PROJECT_ANALYSIS.md
│   │   └── PHASE*.md
│   ├── documents/                # Legal documents
│   │   ├── Конституція України
│   │   ├── Кримінальний кодекс України
│   │   └── Цивільний кодекс України
│   └── api/                      # API reference (to be generated)
│
├── data/                         # Data and resources
│   ├── documents/                # Input documents
│   ├── test_queries/             # Test queries
│   ├── embeddings/               # Precomputed embeddings (cache)
│   └── evaluation/               # Evaluation results
│
├── logs/                         # Application logs
│   ├── indexing.log
│   └── search.log
│
├── pyproject.toml                # Project configuration and dependencies
├── .env.example                  # Environment variables template
├── .env                          # Environment variables (DO NOT COMMIT)
├── .gitignore                    # Git ignore rules
├── .pre-commit-config.yaml       # Pre-commit hooks (Ruff, MyPy)
├── pytest.ini                    # Pytest configuration
├── Makefile                      # Common commands
└── docker-compose.yml            # Docker services (Qdrant, MLflow, Langfuse)
```

---

## 🔑 Key Features

### 1. Configuration Management (`src/config/`)

**Centralized, type-safe configuration:**

```python
from src.config import Settings, SearchEngine, APIProvider

# Load settings from .env
settings = Settings()

# Override specific settings
settings = Settings(
    api_provider=APIProvider.OPENAI,
    search_engine=SearchEngine.DBSF_COLBERT,
    qdrant_url="https://qdrant.example.com"
)

# Access settings
print(settings.model_name)        # "claude-3-5-sonnet-20241022"
print(settings.collection_name)   # "legal_documents"
```

### 2. Contextualization (`src/contextualization/`)

**LLM-based document enrichment:**

```python
from src.contextualization import ClaudeContextualizer

contextualizer = ClaudeContextualizer()

# Contextualize chunks
chunks = await contextualizer.contextualize(
    texts=["Article text..."],
    query="User's search query",
)

# Get statistics
stats = contextualizer.get_stats()  # tokens, cost, etc.
```

### 3. Retrieval (`src/retrieval/`)

**Three search engine implementations:**

- **Baseline**: Dense vectors only (91.3% Recall@1)
- **Hybrid RRF**: Dense + Sparse with fusion (88.7% Recall@1)
- **DBSF+ColBERT**: Advanced hybrid (94.0% Recall@1) ⭐

```python
from src.retrieval import DBSFColBERTSearchEngine

engine = DBSFColBERTSearchEngine()
results = engine.search(query_embedding, top_k=10)
```

### 4. Ingestion (`src/ingestion/`)

**Document pipeline:**

1. **PDF Parsing**: Extract text from PDFs
2. **Chunking**: Split into semantic units
3. **Embedding**: Generate vector embeddings
4. **Indexing**: Store in Qdrant

```python
from src.ingestion import PDFParser, DocumentChunker, DocumentIndexer

# 1. Parse
parser = PDFParser()
doc = parser.parse_file("my_document.pdf")

# 2. Chunk
chunker = DocumentChunker(chunk_size=512, overlap=128)
chunks = chunker.chunk_text(doc.content, doc.filename, "article_1")

# 3. Index
indexer = DocumentIndexer()
stats = await indexer.index_chunks(chunks, collection_name="legal_documents")
```

### 5. Evaluation (`src/evaluation/`)

**Metrics and tracking:**

- Recall@K, NDCG@K, MRR
- MLflow experiment tracking
- Langfuse LLM tracing
- Cost and performance analytics

---

## 📦 Installation

```bash
# Clone repository
git clone <your-repo>
cd rag-fresh

# Create virtual environment
python3.9 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -e .

# Setup environment
cp .env.example .env
# Edit .env with your API keys

# Start dependencies
docker compose up -d qdrant  # or use `--profile ml` for ML services
```

---

## 🚀 Quick Start

### 1. Index Documents

```bash
python -m src.scripts.index_documents \
  --pdf-dir docs/documents/ \
  --collection legal_documents
```

### 2. Search

```bash
python -m src.scripts.search \
  --query "Які права мають громадяни?" \
  --top-k 5
```

### 3. Evaluate

```bash
python -m src.scripts.evaluate \
  --test-queries evaluation/queries.json \
  --method dbsf_colbert
```

---

## 📚 Documentation

| Document | Purpose |
|----------|---------|
| [QUICK_START.md](guides/QUICK_START.md) | 5-minute setup guide |
| [ARCHITECTURE.md](architecture/ARCHITECTURE.md) | System architecture |
| [CODE_QUALITY.md](guides/CODE_QUALITY.md) | Development standards |
| [API_REFERENCE.md](api/API_REFERENCE.md) | API documentation |

---

## 🔧 Configuration

Configuration is managed through environment variables (`.env`):

```env
# API Provider (claude, openai, groq)
API_PROVIDER=claude
ANTHROPIC_API_KEY=[REDACTED-ANTHROPIC-KEY]
OPENAI_API_KEY=[REDACTED-OPENAI-KEY]
GROQ_API_KEY=[REDACTED-GROQ-KEY]

# Vector Database
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=

# Search
SEARCH_ENGINE=dbsf_colbert  # baseline, hybrid_rrf, dbsf_colbert
COLLECTION_NAME=legal_documents
TOP_K=10

# Features
ENABLE_CACHING=true
ENABLE_QUERY_EXPANSION=true
ENABLE_MLFLOW=true
ENABLE_LANGFUSE=true

# Environment
ENV=development  # development, production
DEBUG=false
```

---

## 🎓 Module Guide

### When to Use Each Module

| Module | Use Case |
|--------|----------|
| `config/` | Loading and validating settings |
| `contextualization/` | Enriching documents with LLM context |
| `retrieval/` | Searching for relevant documents |
| `ingestion/` | Loading and indexing new documents |
| `evaluation/` | Testing quality and running experiments |
| `utils/` | Common utilities and helpers |
| `core/` | Orchestrating the full pipeline |

---

## 📊 Performance

### Search Quality (150 test queries)

| Method | Recall@1 | NDCG@10 | MRR | Latency |
|--------|----------|---------|-----|---------|
| Baseline | 91.3% | 0.9619 | 0.9491 | 0.65s |
| Hybrid RRF | 88.7% | 0.9524 | 0.9421 | 0.72s |
| **DBSF+ColBERT** | **94.0%** | **0.9711** | **0.9636** | **0.69s** |

### Ingestion Speed

- **Parsing**: 132 chunks in 2-3 minutes
- **Contextualization**: $0-3 depending on API
- **Indexing**: 6 minutes for full pipeline

---

## 🐛 Troubleshooting

### Qdrant Connection Error

```bash
# Start Qdrant
docker compose up -d qdrant

# Check health
curl http://localhost:6333/health
```

### API Key Issues

```bash
# Verify .env is properly set
python -c "from src.config import Settings; Settings().validate()"
```

### Slow Search

- Use DBSF+ColBERT instead of Baseline
- Check Qdrant is running and responsive
- Increase HNSW ef parameter in config

---

## 📝 Development

### Code Quality

```bash
# Linting
ruff check src/

# Formatting
ruff format src/

# Type checking
mypy src/ --ignore-missing-imports

# Run tests
pytest tests/
```

### Pre-commit Hooks

```bash
# Install hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

---

## 🤝 Contributing

1. Create feature branch: `git checkout -b feature/my-feature`
2. Make changes and commit: `git add . && git commit -m "Add feature"`
3. Run tests: `pytest tests/`
4. Push and create PR

---

## 📞 Support

- **Issues**: GitHub Issues
- **Documentation**: See `/docs` folder
- **Status**: Production Ready ✅

---

**Last Updated**: October 29, 2025
**Version**: 2.0.1
**Maintainer**: Contextual RAG Team
