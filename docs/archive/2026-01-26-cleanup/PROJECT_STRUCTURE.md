# 📋 PROJECT STRUCTURE - Contextual RAG v2.0.1

> **Complete project structure guide with description of each module**

## Table of Contents
1. [Project Overview](#project-overview)
2. [Directory Structure](#directory-structure)
3. [Core Modules](#core-modules)
4. [Technology Stack](#technology-stack)
5. [Workflow](#workflow)
6. [Quick Reference](#quick-reference)

---

## Project Overview

**Contextual RAG Pipeline** - a production-ready system for searching and retrieving information from Ukrainian legal documents, using:
- 🤖 **Hybrid Search**: Dense (BGE-M3) + Sparse (ColBERT) vectors
- 🔍 **DBSF Ranking**: Density-Based Semantic Fusion for optimal results
- 📊 **ML Platforms**: MLflow + Langfuse for experiment tracking
- 🚀 **Multiple LLMs**: Claude, OpenAI, Groq, Z.AI
- 📚 **Contextualization**: Automatic context enrichment through Claude API

**Version**: 2.0.1
**Python**: ≥ 3.9
**License**: MIT
**Status**: Production Ready ✅

---

## Directory Structure

```
contextual_rag/
│
├── 📋 ROOT CONFIGURATION
│   ├── pyproject.toml               # Project configuration, dependencies
│   ├── config.py                    # Application parameters
│   ├── prompts.py                   # Prompt system for LLM
│   ├── .env                         # API keys and URLs (DO NOT commit!)
│   ├── .env.example                 # Environment variables example
│   ├── .pre-commit-config.yaml      # Pre-commit hooks (Ruff, MyPy)
│   └── __init__.py                  # Package initialization
│
├── 🔄 CONTEXTUALIZATION & RETRIEVAL
│   ├── contextualize.py             # ⭐ Claude API (main)
│   ├── contextualize_groq_async.py  ***REMOVED*** async version
│   ├── contextualize_openai_async.py # OpenAI async version
│   ├── contextualize_zai.py         # Z.AI sync version
│   └── contextualize_zai_async.py   # Z.AI async version
│
├── 📥 INGESTION & INDEXING
│   ├── ingestion_contextual_kg_fast.py # ⭐ Fast version (optimized)
│   ├── ingestion_contextual_kg.py      # Base version
│   ├── pymupdf_chunker.py              # PDF parsing + chunking
│   ├── create_collection_enhanced.py   ***REMOVED*** collection creation
│   └── create_payload_indexes.py       # Payload index creation
│
├── 🧪 TESTING & VALIDATION
│   ├── test_api_quick.py            # Quick smoke test
│   ├── test_api_safe.py             # Safe testing
│   ├── test_api_comparison.py       # API comparison
│   ├── test_api_extended.py         # Extended test with metrics
│   ├── test_api_comparison_multi.py # Multi-API comparison
│   ├── test_dbsf_fusion.py          # DBSF+ColBERT testing
│   ├── evaluate_ab.py               # A/B testing
│   ├── evaluation.py                # Main evaluator
│   └── example_search.py            # Usage example
│
├── 📊 EVALUATION/
│   ├── search_engines.py            # Implementation of 3 search engines
│   │                                # (Baseline, Hybrid, DBSF)
│   ├── run_ab_test.py               # ⭐ A/B test with MLflow logging
│   ├── evaluate_with_ragas.py       # RAGAS framework integration
│   ├── smoke_test.py                # Smoke tests
│   ├── langfuse_integration.py      # Langfuse (LLM tracing)
│   ├── mlflow_integration.py        # MLflow (experiment tracking)
│   ├── evaluator.py                 # Main evaluator class
│   ├── metrics_logger.py            # Metrics logging
│   ├── config_snapshot.py           # Configuration snapshot at runtime
│   ├── generate_test_queries.py     # Test query generation
│   ├── extract_ground_truth.py      # Ground truth extraction
│   ├── search_engines_rerank.py     # Search reranking
│   ├── test_mlflow_ab.py            # MLflow testing
│   ├── data/                        # Test data
│   ├── evaluation/                  # Evaluation results
│   ├── reports/                     # Evaluation reports
│   └── results/                     # Test results
│
├── 📚 DOCS/
│   ├── INDEX.md                     # Index of all documentation
│   ├── README.md                    # Documentation overview
│   ├── documents/                   # Ukrainian legal documents
│   │   ├── Конституція України
│   │   ├── Кримінальний кодекс України
│   │   └── Цивільний кодекс України
│   ├── guides/                      # Practical guides
│   │   ├── QUICK_START_DBSF.md
│   │   ├── DEDUPLICATION_GUIDE.md
│   │   └── DOC_LING_RAG_TASKS_2025.md
│   ├── implementation/              # Checklists and plans
│   │   ├── IMPLEMENTATION_CHECKLIST.md
│   │   └── DBSF_COLBERT_IMPLEMENTATION_SUMMARY.md
│   ├── reports/                     # Final reports
│   │   ├── FINAL_REPORT_CONTEXTUAL_RAG.md
│   │   ├── FINAL_OPTIMIZATION_REPORT.md
│   │   └── TEST_RESULTS_SUMMARY.md
│   └── archive/                     # Old document versions
│
├── 🛠️ UTILS/
│   ├── __init__.py                  # Package initialization
│   └── structure_parser.py          # Document structure parser
│
├── 📦 contextual_rag.egg-info/      # Package metadata (auto-generated)
│   ├── PKG-INFO
│   ├── SOURCES.txt
│   ├── dependency_links.txt
│   ├── entry_points.txt
│   ├── requires.txt
│   └── top_level.txt
│
├── 🗂️ ROOT DOCUMENTATION
│   ├── README.md                    # ⭐ Main documentation
│   ├── ARCHITECTURE.md              # System architecture
│   ├── SETUP.md                     # Installation and setup
│   ├── CODE_QUALITY.md              # Code quality recommendations
│   ├── MIGRATION_PLAN.md            # ML platform migration plan
│   ├── OPTIMIZATION_PLAN.md         # Optimization plan
│   ├── DBSF_vs_RRF_ANALYSIS.md      # Ranking methods analysis
│   ├── PHASE1_COMPLETION_SUMMARY.md # Phase 1 completion
│   ├── PHASE2_COMPLETION_SUMMARY.md # Phase 2 completion
│   └── PHASE3_COMPLETION_SUMMARY.md # Phase 3 completion
│
├── 🔐 BACKUP & CACHE
│   ├── contextual_rag_backup_*.tar.gz # Project backups
│   ├── **/__pycache__/              # Python cache (ignore)
│   └── *.egg-info/                  # Package metadata (ignore)
│
└── 📝 GIT & CI/CD
    ├── .git/                        # Git repository
    ├── .gitignore                   # Ignored files
    ├── docker-compose.yml           # Docker services (Qdrant, MLflow, Langfuse)
    └── .github/workflows/           # GitHub Actions (if present)
```

---

## Core Modules

### 1. Contextualization Layer

| Module | Purpose | Status |
|--------|---------|--------|
| `contextualize.py` | Claude API with prompt caching | ⭐ Main |
| `contextualize_groq_async.py` | Groq (fast) | Alternative |
| `contextualize_openai_async.py` | OpenAI GPT | Alternative |
| `contextualize_zai*.py` | Z.AI (legacy) | Legacy |

**Function**: Document context enrichment through LLM before search.

```python
# Usage example
from contextualize import contextualize_documents
enriched_docs = contextualize_documents(documents, query)
```

---

### 2. Ingestion Layer

| Module | Purpose | Status |
|--------|---------|--------|
| `ingestion_contextual_kg_fast.py` | Fast optimized ingestion | ⭐ Main |
| `ingestion_contextual_kg.py` | Standard ingestion | Fallback |
| `pymupdf_chunker.py` | PDF parser with chunking | Utility |
| `create_collection_enhanced.py` | Collection creation | Setup |
| `create_payload_indexes.py` | Payload indexes | Setup |

**Function**: Loading PDF documents into Qdrant with contextualization.

```python
# Usage example
from ingestion_contextual_kg_fast import ingest_documents
ingest_documents(pdf_path, collection_name='legal_documents')
```

---

### 3. Search & Retrieval

**Three search levels**:
1. **Baseline**: BM25 + Dense vectors (standard)
2. **Hybrid**: Dense + Sparse (BGE-M3 + ColBERT)
3. **DBSF**: Density-Based Semantic Fusion (optimal)

**Improvement metrics (DBSF vs Baseline)**:
- Recall@1: 91.3% → 94.0% (+2.9%) ✅
- NDCG@10: 0.9619 → 0.9711 (+1.0%) ✅
- MRR: 0.9491 → 0.9636 (+1.5%) ✅

```python
# Implementation in evaluation/search_engines.py
from evaluation.search_engines import DBSFSearchEngine
engine = DBSFSearchEngine()
results = engine.search(query, top_k=10)
```

---

### 4. Evaluation Layer

| Module | Purpose |
|--------|---------|
| `run_ab_test.py` | A/B test with MLflow logging |
| `evaluate_with_ragas.py` | RAGAS evaluation framework |
| `smoke_test.py` | Quick smoke tests |
| `langfuse_integration.py` | LLM tracing via Langfuse |
| `mlflow_integration.py` | Experiment tracking via MLflow |

**Integrations**:
- **MLflow**: http://localhost:5000
- **Langfuse**: http://localhost:3001
- **RAGAS**: RAG evaluation metrics

---

### 5. Configuration

**config.py** - central project configuration:
```python
API_PROVIDER = 'claude'           # 'claude', 'openai', 'groq', 'zai'
VECTOR_DB_URL = 'http://localhost:6333'  ***REMOVED***
COLLECTION_NAME = 'legal_documents'
MODEL_NAME = 'claude-3-5-sonnet-20241022'  # Main model
EMBEDDING_MODEL = 'BAAI/bge-m3'   # 1024-dim vectors
```

---

### 6. Utility Functions

| Module | Purpose |
|--------|---------|
| `utils/structure_parser.py` | Document structure parser |
| `check_sparse_vectors.py` | Sparse vectors check |
| `list_available_models.py` | List available models |
| `example_search.py` | API usage example |

---

## Technology Stack

### Vector Database
- **Qdrant** v0.13.x
- **Dense Embeddings**: BGE-M3 (1024-dim)
- **Sparse Embeddings**: ColBERT
- **Hybrid Search**: DBSF + RRF

### LLM APIs
- **Anthropic Claude** 3.5 Sonnet (main)
- **OpenAI GPT-4** (alternative)
- **Groq LLaMA3** (fast)
- **Z.AI GLM-4.6** (legacy)

### ML Platforms
- **MLflow** 2.22.1+ (experiment tracking)
- **Langfuse** 3.0.0+ (LLM observability)
- **RAGAS** 0.2.10+ (RAG evaluation)

### Code Quality
- **Ruff** 0.14.1 (linting + formatting)
- **MyPy** (type checking)
- **Bandit** (security scanning)
- **Pre-commit** (git hooks)

### Document Processing
- **PyMuPDF** (PDF parsing)
- **FlagEmbedding** (BGE embeddings)
- **LangChain** (ecosystem utilities)

---

## Workflow

### 1️⃣ Setup & Installation
```bash
# Clone repository
git clone <repo>
cd contextual_rag

# Install dependencies
pip install -e .

# Configuration
cp .env.example .env
# Edit .env with your API keys

# Start Qdrant via Docker
docker compose up -d qdrant

# (Optional) Start ML platforms
docker compose --profile ml up -d mlflow langfuse
```

### 2️⃣ Data Ingestion
```bash
# Create collection
python create_collection_enhanced.py

# Load documents
python ingestion_contextual_kg_fast.py \
  --pdf-path docs/documents/ \
  --collection legal_documents
```

### 3️⃣ Testing
```bash
# Smoke test
python evaluation/smoke_test.py

# A/B testing (with MLflow logging)
python evaluation/run_ab_test.py

# Quick API test
python test_api_quick.py
```

### 4️⃣ Production Query
```bash
# Search example
python example_search.py \
  --query "Які право мають громадяни?" \
  --top-k 10
```

### 5️⃣ Monitoring & Analysis
```bash
# MLflow Dashboard
open http://localhost:5000

# Langfuse Dashboard
open http://localhost:3001
```

---

## Quick Reference

### Main Commands

| Command | Description |
|---------|-------------|
| `python test_api_quick.py` | Quick smoke test |
| `python evaluation/run_ab_test.py` | A/B test with logging |
| `python example_search.py --query "..."` | Search |
| `ruff check .` | Lint check |
| `ruff format .` | Code formatting |
| `mypy . --ignore-missing-imports` | Type checking |
| `docker compose up -d` | Start Qdrant |
| `docker compose --profile ml up -d` | Start ML platforms |

### Important Files to Edit

| File | When to Edit |
|------|-------------|
| `.env` | Adding API keys |
| `config.py` | Changing system parameters |
| `prompts.py` | Updating LLM prompts |
| `pyproject.toml` | Adding new dependencies |
| `.pre-commit-config.yaml` | Changing code quality settings |

### Common Issues

| Issue | Solution |
|-------|----------|
| `ConnectionError` to Qdrant | Run `docker compose up -d qdrant` |
| `APIError` from Claude | Check `.env` key `ANTHROPIC_API_KEY` |
| `ModuleNotFoundError` | Reinstall `pip install -e .` |
| Slow search | Use `ingestion_contextual_kg_fast.py` |
| Low metrics | Check DBSF configuration in `config.py` |

---

## Module Documentation

Detailed description of each module see in:
- 📖 **MODULE_GUIDE.md** - Description of all modules
- 🚀 **QUICK_START.md** - Step-by-step start
- 📦 **DEPENDENCIES.md** - All dependencies
- 🔧 **DEBUGGING_GUIDE.md** - Troubleshooting

---

## Contact and Support

- **Issues**: Create GitHub issues
- **Documentation**: See `/docs` folder
- **Status**: Production ready ✅

---

**Last Updated**: 2025-10-29
**Version**: 2.0.1
**Maintainer**: Contextual RAG Team
