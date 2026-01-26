***REMOVED*** 📚 Contextual RAG v2.0.1 - New Project Structure

> **Redesigned production-ready architecture with clean module separation**

***REMOVED******REMOVED*** 🎯 Project Overview

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

***REMOVED******REMOVED*** 📁 New Directory Structure

```
rag-fresh/
├── src/                          ***REMOVED*** Source code (main application)
│   ├── config/                   ***REMOVED*** Configuration management
│   │   ├── __init__.py
│   │   ├── constants.py          ***REMOVED*** Enums, data classes, constants
│   │   └── settings.py           ***REMOVED*** Settings class with validation
│   │
│   ├── contextualization/        ***REMOVED*** LLM contextualization
│   │   ├── __init__.py
│   │   ├── base.py               ***REMOVED*** Base provider class
│   │   ├── claude.py             ***REMOVED*** Claude API (recommended)
│   │   ├── openai.py             ***REMOVED*** OpenAI GPT
│   │   └── groq.py               ***REMOVED*** Groq LLaMA (fast)
│   │
│   ├── retrieval/                ***REMOVED*** Search and retrieval
│   │   ├── __init__.py
│   │   └── search_engines.py     ***REMOVED*** Baseline, Hybrid RRF, DBSF+ColBERT
│   │
│   ├── ingestion/                ***REMOVED*** Document loading and indexing
│   │   ├── __init__.py
│   │   ├── pdf_parser.py         ***REMOVED*** PDF parsing
│   │   ├── chunker.py            ***REMOVED*** Document chunking strategies
│   │   └── indexer.py            ***REMOVED*** Vector database indexing
│   │
│   ├── evaluation/               ***REMOVED*** Evaluation and metrics
│   │   ├── __init__.py
│   │   ├── metrics.py            ***REMOVED*** Recall, NDCG, MRR, etc.
│   │   ├── mlflow_integration.py ***REMOVED*** MLflow experiment tracking
│   │   └── langfuse_integration.py ***REMOVED*** Langfuse LLM tracing
│   │
│   ├── utils/                    ***REMOVED*** Utility functions
│   │   ├── __init__.py
│   │   ├── logger.py             ***REMOVED*** Logging utilities
│   │   └── helpers.py            ***REMOVED*** Common helpers
│   │
│   └── core/                     ***REMOVED*** Core application logic
│       ├── __init__.py
│       └── pipeline.py           ***REMOVED*** Main RAG pipeline orchestrator
│
├── tests/                        ***REMOVED*** Test suites
│   ├── unit/                     ***REMOVED*** Unit tests
│   ├── integration/              ***REMOVED*** Integration tests
│   └── conftest.py               ***REMOVED*** Pytest configuration
│
├── docs/                         ***REMOVED*** Documentation
│   ├── README.md                 ***REMOVED*** Main documentation
│   ├── guides/                   ***REMOVED*** User guides
│   │   ├── QUICK_START.md
│   │   ├── SETUP.md
│   │   └── CODE_QUALITY.md
│   ├── architecture/             ***REMOVED*** Architecture docs
│   │   ├── ARCHITECTURE.md
│   │   └── MIGRATION_PLAN.md
│   ├── implementation/           ***REMOVED*** Implementation details
│   │   ├── OPTIMIZATION_PLAN.md
│   │   └── DBSF_vs_RRF_ANALYSIS.md
│   ├── reports/                  ***REMOVED*** Project reports
│   │   ├── FINAL_PROJECT_ANALYSIS.md
│   │   └── PHASE*.md
│   ├── documents/                ***REMOVED*** Legal documents
│   │   ├── Конституція України
│   │   ├── Кримінальний кодекс України
│   │   └── Цивільний кодекс України
│   └── api/                      ***REMOVED*** API reference (to be generated)
│
├── data/                         ***REMOVED*** Data and resources
│   ├── documents/                ***REMOVED*** Input documents
│   ├── test_queries/             ***REMOVED*** Test queries
│   ├── embeddings/               ***REMOVED*** Precomputed embeddings (cache)
│   └── evaluation/               ***REMOVED*** Evaluation results
│
├── logs/                         ***REMOVED*** Application logs
│   ├── indexing.log
│   └── search.log
│
├── pyproject.toml                ***REMOVED*** Project configuration and dependencies
├── .env.example                  ***REMOVED*** Environment variables template
├── .env                          ***REMOVED*** Environment variables (DO NOT COMMIT)
├── .gitignore                    ***REMOVED*** Git ignore rules
├── .pre-commit-config.yaml       ***REMOVED*** Pre-commit hooks (Ruff, MyPy)
├── pytest.ini                    ***REMOVED*** Pytest configuration
├── Makefile                      ***REMOVED*** Common commands
└── docker-compose.yml            ***REMOVED*** Docker services (Qdrant, MLflow, Langfuse)
```

---

***REMOVED******REMOVED*** 🔑 Key Features

***REMOVED******REMOVED******REMOVED*** 1. Configuration Management (`src/config/`)

**Centralized, type-safe configuration:**

```python
from src.config import Settings, SearchEngine, APIProvider

***REMOVED*** Load settings from .env
settings = Settings()

***REMOVED*** Override specific settings
settings = Settings(
    api_provider=APIProvider.OPENAI,
    search_engine=SearchEngine.DBSF_COLBERT,
    qdrant_url="https://qdrant.example.com"
)

***REMOVED*** Access settings
print(settings.model_name)        ***REMOVED*** "claude-3-5-sonnet-20241022"
print(settings.collection_name)   ***REMOVED*** "legal_documents"
```

***REMOVED******REMOVED******REMOVED*** 2. Contextualization (`src/contextualization/`)

**LLM-based document enrichment:**

```python
from src.contextualization import ClaudeContextualizer

contextualizer = ClaudeContextualizer()

***REMOVED*** Contextualize chunks
chunks = await contextualizer.contextualize(
    texts=["Article text..."],
    query="User's search query",
)

***REMOVED*** Get statistics
stats = contextualizer.get_stats()  ***REMOVED*** tokens, cost, etc.
```

***REMOVED******REMOVED******REMOVED*** 3. Retrieval (`src/retrieval/`)

**Three search engine implementations:**

- **Baseline**: Dense vectors only (91.3% Recall@1)
- **Hybrid RRF**: Dense + Sparse with fusion (88.7% Recall@1)
- **DBSF+ColBERT**: Advanced hybrid (94.0% Recall@1) ⭐

```python
from src.retrieval import DBSFColBERTSearchEngine

engine = DBSFColBERTSearchEngine()
results = engine.search(query_embedding, top_k=10)
```

***REMOVED******REMOVED******REMOVED*** 4. Ingestion (`src/ingestion/`)

**Document pipeline:**

1. **PDF Parsing**: Extract text from PDFs
2. **Chunking**: Split into semantic units
3. **Embedding**: Generate vector embeddings
4. **Indexing**: Store in Qdrant

```python
from src.ingestion import PDFParser, DocumentChunker, DocumentIndexer

***REMOVED*** 1. Parse
parser = PDFParser()
doc = parser.parse_file("my_document.pdf")

***REMOVED*** 2. Chunk
chunker = DocumentChunker(chunk_size=512, overlap=128)
chunks = chunker.chunk_text(doc.content, doc.filename, "article_1")

***REMOVED*** 3. Index
indexer = DocumentIndexer()
stats = await indexer.index_chunks(chunks, collection_name="legal_documents")
```

***REMOVED******REMOVED******REMOVED*** 5. Evaluation (`src/evaluation/`)

**Metrics and tracking:**

- Recall@K, NDCG@K, MRR
- MLflow experiment tracking
- Langfuse LLM tracing
- Cost and performance analytics

---

***REMOVED******REMOVED*** 📦 Installation

```bash
***REMOVED*** Clone repository
git clone <your-repo>
cd rag-fresh

***REMOVED*** Create virtual environment
python3.9 -m venv venv
source venv/bin/activate  ***REMOVED*** Windows: venv\Scripts\activate

***REMOVED*** Install dependencies
pip install -e .

***REMOVED*** Setup environment
cp .env.example .env
***REMOVED*** Edit .env with your API keys

***REMOVED*** Start dependencies
docker compose up -d qdrant  ***REMOVED*** or use `--profile ml` for ML services
```

---

***REMOVED******REMOVED*** 🚀 Quick Start

***REMOVED******REMOVED******REMOVED*** 1. Index Documents

```bash
python -m src.scripts.index_documents \
  --pdf-dir docs/documents/ \
  --collection legal_documents
```

***REMOVED******REMOVED******REMOVED*** 2. Search

```bash
python -m src.scripts.search \
  --query "Які права мають громадяни?" \
  --top-k 5
```

***REMOVED******REMOVED******REMOVED*** 3. Evaluate

```bash
python -m src.scripts.evaluate \
  --test-queries evaluation/queries.json \
  --method dbsf_colbert
```

---

***REMOVED******REMOVED*** 📚 Documentation

| Document | Purpose |
|----------|---------|
| [QUICK_START.md](guides/QUICK_START.md) | 5-minute setup guide |
| [ARCHITECTURE.md](architecture/ARCHITECTURE.md) | System architecture |
| [CODE_QUALITY.md](guides/CODE_QUALITY.md) | Development standards |
| [API_REFERENCE.md](api/API_REFERENCE.md) | API documentation |

---

***REMOVED******REMOVED*** 🔧 Configuration

Configuration is managed through environment variables (`.env`):

```env
***REMOVED*** API Provider (claude, openai, groq)
API_PROVIDER=claude
ANTHROPIC_API_KEY=[REDACTED-ANTHROPIC-KEY]
OPENAI_API_KEY=[REDACTED-OPENAI-KEY]
GROQ_API_KEY=[REDACTED-GROQ-KEY]

***REMOVED*** Vector Database
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=

***REMOVED*** Search
SEARCH_ENGINE=dbsf_colbert  ***REMOVED*** baseline, hybrid_rrf, dbsf_colbert
COLLECTION_NAME=legal_documents
TOP_K=10

***REMOVED*** Features
ENABLE_CACHING=true
ENABLE_QUERY_EXPANSION=true
ENABLE_MLFLOW=true
ENABLE_LANGFUSE=true

***REMOVED*** Environment
ENV=development  ***REMOVED*** development, production
DEBUG=false
```

---

***REMOVED******REMOVED*** 🎓 Module Guide

***REMOVED******REMOVED******REMOVED*** When to Use Each Module

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

***REMOVED******REMOVED*** 📊 Performance

***REMOVED******REMOVED******REMOVED*** Search Quality (150 test queries)

| Method | Recall@1 | NDCG@10 | MRR | Latency |
|--------|----------|---------|-----|---------|
| Baseline | 91.3% | 0.9619 | 0.9491 | 0.65s |
| Hybrid RRF | 88.7% | 0.9524 | 0.9421 | 0.72s |
| **DBSF+ColBERT** | **94.0%** | **0.9711** | **0.9636** | **0.69s** |

***REMOVED******REMOVED******REMOVED*** Ingestion Speed

- **Parsing**: 132 chunks in 2-3 minutes
- **Contextualization**: $0-3 depending on API
- **Indexing**: 6 minutes for full pipeline

---

***REMOVED******REMOVED*** 🐛 Troubleshooting

***REMOVED******REMOVED******REMOVED*** Qdrant Connection Error

```bash
***REMOVED*** Start Qdrant
docker compose up -d qdrant

***REMOVED*** Check health
curl http://localhost:6333/health
```

***REMOVED******REMOVED******REMOVED*** API Key Issues

```bash
***REMOVED*** Verify .env is properly set
python -c "from src.config import Settings; Settings().validate()"
```

***REMOVED******REMOVED******REMOVED*** Slow Search

- Use DBSF+ColBERT instead of Baseline
- Check Qdrant is running and responsive
- Increase HNSW ef parameter in config

---

***REMOVED******REMOVED*** 📝 Development

***REMOVED******REMOVED******REMOVED*** Code Quality

```bash
***REMOVED*** Linting
ruff check src/

***REMOVED*** Formatting
ruff format src/

***REMOVED*** Type checking
mypy src/ --ignore-missing-imports

***REMOVED*** Run tests
pytest tests/
```

***REMOVED******REMOVED******REMOVED*** Pre-commit Hooks

```bash
***REMOVED*** Install hooks
pre-commit install

***REMOVED*** Run manually
pre-commit run --all-files
```

---

***REMOVED******REMOVED*** 🤝 Contributing

1. Create feature branch: `git checkout -b feature/my-feature`
2. Make changes and commit: `git add . && git commit -m "Add feature"`
3. Run tests: `pytest tests/`
4. Push and create PR

---

***REMOVED******REMOVED*** 📞 Support

- **Issues**: GitHub Issues
- **Documentation**: See `/docs` folder
- **Status**: Production Ready ✅

---

**Last Updated**: October 29, 2025
**Version**: 2.0.1
**Maintainer**: Contextual RAG Team
