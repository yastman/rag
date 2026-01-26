***REMOVED*** 📋 PROJECT STRUCTURE - Contextual RAG v2.0.1

> **Complete project structure guide with description of each module**

***REMOVED******REMOVED*** Table of Contents
1. [Project Overview](***REMOVED***project-overview)
2. [Directory Structure](***REMOVED***directory-structure)
3. [Core Modules](***REMOVED***core-modules)
4. [Technology Stack](***REMOVED***technology-stack)
5. [Workflow](***REMOVED***workflow)
6. [Quick Reference](***REMOVED***quick-reference)

---

***REMOVED******REMOVED*** Project Overview

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

***REMOVED******REMOVED*** Directory Structure

```
contextual_rag/
│
├── 📋 ROOT CONFIGURATION
│   ├── pyproject.toml               ***REMOVED*** Project configuration, dependencies
│   ├── config.py                    ***REMOVED*** Application parameters
│   ├── prompts.py                   ***REMOVED*** Prompt system for LLM
│   ├── .env                         ***REMOVED*** API keys and URLs (DO NOT commit!)
│   ├── .env.example                 ***REMOVED*** Environment variables example
│   ├── .pre-commit-config.yaml      ***REMOVED*** Pre-commit hooks (Ruff, MyPy)
│   └── __init__.py                  ***REMOVED*** Package initialization
│
├── 🔄 CONTEXTUALIZATION & RETRIEVAL
│   ├── contextualize.py             ***REMOVED*** ⭐ Claude API (main)
│   ├── contextualize_groq_async.py  ***REMOVED*** Groq async version
│   ├── contextualize_openai_async.py ***REMOVED*** OpenAI async version
│   ├── contextualize_zai.py         ***REMOVED*** Z.AI sync version
│   └── contextualize_zai_async.py   ***REMOVED*** Z.AI async version
│
├── 📥 INGESTION & INDEXING
│   ├── ingestion_contextual_kg_fast.py ***REMOVED*** ⭐ Fast version (optimized)
│   ├── ingestion_contextual_kg.py      ***REMOVED*** Base version
│   ├── pymupdf_chunker.py              ***REMOVED*** PDF parsing + chunking
│   ├── create_collection_enhanced.py   ***REMOVED*** Qdrant collection creation
│   └── create_payload_indexes.py       ***REMOVED*** Payload index creation
│
├── 🧪 TESTING & VALIDATION
│   ├── test_api_quick.py            ***REMOVED*** Quick smoke test
│   ├── test_api_safe.py             ***REMOVED*** Safe testing
│   ├── test_api_comparison.py       ***REMOVED*** API comparison
│   ├── test_api_extended.py         ***REMOVED*** Extended test with metrics
│   ├── test_api_comparison_multi.py ***REMOVED*** Multi-API comparison
│   ├── test_dbsf_fusion.py          ***REMOVED*** DBSF+ColBERT testing
│   ├── evaluate_ab.py               ***REMOVED*** A/B testing
│   ├── evaluation.py                ***REMOVED*** Main evaluator
│   └── example_search.py            ***REMOVED*** Usage example
│
├── 📊 EVALUATION/
│   ├── search_engines.py            ***REMOVED*** Implementation of 3 search engines
│   │                                ***REMOVED*** (Baseline, Hybrid, DBSF)
│   ├── run_ab_test.py               ***REMOVED*** ⭐ A/B test with MLflow logging
│   ├── evaluate_with_ragas.py       ***REMOVED*** RAGAS framework integration
│   ├── smoke_test.py                ***REMOVED*** Smoke tests
│   ├── langfuse_integration.py      ***REMOVED*** Langfuse (LLM tracing)
│   ├── mlflow_integration.py        ***REMOVED*** MLflow (experiment tracking)
│   ├── evaluator.py                 ***REMOVED*** Main evaluator class
│   ├── metrics_logger.py            ***REMOVED*** Metrics logging
│   ├── config_snapshot.py           ***REMOVED*** Configuration snapshot at runtime
│   ├── generate_test_queries.py     ***REMOVED*** Test query generation
│   ├── extract_ground_truth.py      ***REMOVED*** Ground truth extraction
│   ├── search_engines_rerank.py     ***REMOVED*** Search reranking
│   ├── test_mlflow_ab.py            ***REMOVED*** MLflow testing
│   ├── data/                        ***REMOVED*** Test data
│   ├── evaluation/                  ***REMOVED*** Evaluation results
│   ├── reports/                     ***REMOVED*** Evaluation reports
│   └── results/                     ***REMOVED*** Test results
│
├── 📚 DOCS/
│   ├── INDEX.md                     ***REMOVED*** Index of all documentation
│   ├── README.md                    ***REMOVED*** Documentation overview
│   ├── documents/                   ***REMOVED*** Ukrainian legal documents
│   │   ├── Конституція України
│   │   ├── Кримінальний кодекс України
│   │   └── Цивільний кодекс України
│   ├── guides/                      ***REMOVED*** Practical guides
│   │   ├── QUICK_START_DBSF.md
│   │   ├── DEDUPLICATION_GUIDE.md
│   │   └── DOC_LING_RAG_TASKS_2025.md
│   ├── implementation/              ***REMOVED*** Checklists and plans
│   │   ├── IMPLEMENTATION_CHECKLIST.md
│   │   └── DBSF_COLBERT_IMPLEMENTATION_SUMMARY.md
│   ├── reports/                     ***REMOVED*** Final reports
│   │   ├── FINAL_REPORT_CONTEXTUAL_RAG.md
│   │   ├── FINAL_OPTIMIZATION_REPORT.md
│   │   └── TEST_RESULTS_SUMMARY.md
│   └── archive/                     ***REMOVED*** Old document versions
│
├── 🛠️ UTILS/
│   ├── __init__.py                  ***REMOVED*** Package initialization
│   └── structure_parser.py          ***REMOVED*** Document structure parser
│
├── 📦 contextual_rag.egg-info/      ***REMOVED*** Package metadata (auto-generated)
│   ├── PKG-INFO
│   ├── SOURCES.txt
│   ├── dependency_links.txt
│   ├── entry_points.txt
│   ├── requires.txt
│   └── top_level.txt
│
├── 🗂️ ROOT DOCUMENTATION
│   ├── README.md                    ***REMOVED*** ⭐ Main documentation
│   ├── ARCHITECTURE.md              ***REMOVED*** System architecture
│   ├── SETUP.md                     ***REMOVED*** Installation and setup
│   ├── CODE_QUALITY.md              ***REMOVED*** Code quality recommendations
│   ├── MIGRATION_PLAN.md            ***REMOVED*** ML platform migration plan
│   ├── OPTIMIZATION_PLAN.md         ***REMOVED*** Optimization plan
│   ├── DBSF_vs_RRF_ANALYSIS.md      ***REMOVED*** Ranking methods analysis
│   ├── PHASE1_COMPLETION_SUMMARY.md ***REMOVED*** Phase 1 completion
│   ├── PHASE2_COMPLETION_SUMMARY.md ***REMOVED*** Phase 2 completion
│   └── PHASE3_COMPLETION_SUMMARY.md ***REMOVED*** Phase 3 completion
│
├── 🔐 BACKUP & CACHE
│   ├── contextual_rag_backup_*.tar.gz ***REMOVED*** Project backups
│   ├── **/__pycache__/              ***REMOVED*** Python cache (ignore)
│   └── *.egg-info/                  ***REMOVED*** Package metadata (ignore)
│
└── 📝 GIT & CI/CD
    ├── .git/                        ***REMOVED*** Git repository
    ├── .gitignore                   ***REMOVED*** Ignored files
    ├── docker-compose.yml           ***REMOVED*** Docker services (Qdrant, MLflow, Langfuse)
    └── .github/workflows/           ***REMOVED*** GitHub Actions (if present)
```

---

***REMOVED******REMOVED*** Core Modules

***REMOVED******REMOVED******REMOVED*** 1. Contextualization Layer

| Module | Purpose | Status |
|--------|---------|--------|
| `contextualize.py` | Claude API with prompt caching | ⭐ Main |
| `contextualize_groq_async.py` | Groq (fast) | Alternative |
| `contextualize_openai_async.py` | OpenAI GPT | Alternative |
| `contextualize_zai*.py` | Z.AI (legacy) | Legacy |

**Function**: Document context enrichment through LLM before search.

```python
***REMOVED*** Usage example
from contextualize import contextualize_documents
enriched_docs = contextualize_documents(documents, query)
```

---

***REMOVED******REMOVED******REMOVED*** 2. Ingestion Layer

| Module | Purpose | Status |
|--------|---------|--------|
| `ingestion_contextual_kg_fast.py` | Fast optimized ingestion | ⭐ Main |
| `ingestion_contextual_kg.py` | Standard ingestion | Fallback |
| `pymupdf_chunker.py` | PDF parser with chunking | Utility |
| `create_collection_enhanced.py` | Collection creation | Setup |
| `create_payload_indexes.py` | Payload indexes | Setup |

**Function**: Loading PDF documents into Qdrant with contextualization.

```python
***REMOVED*** Usage example
from ingestion_contextual_kg_fast import ingest_documents
ingest_documents(pdf_path, collection_name='legal_documents')
```

---

***REMOVED******REMOVED******REMOVED*** 3. Search & Retrieval

**Three search levels**:
1. **Baseline**: BM25 + Dense vectors (standard)
2. **Hybrid**: Dense + Sparse (BGE-M3 + ColBERT)
3. **DBSF**: Density-Based Semantic Fusion (optimal)

**Improvement metrics (DBSF vs Baseline)**:
- Recall@1: 91.3% → 94.0% (+2.9%) ✅
- NDCG@10: 0.9619 → 0.9711 (+1.0%) ✅
- MRR: 0.9491 → 0.9636 (+1.5%) ✅

```python
***REMOVED*** Implementation in evaluation/search_engines.py
from evaluation.search_engines import DBSFSearchEngine
engine = DBSFSearchEngine()
results = engine.search(query, top_k=10)
```

---

***REMOVED******REMOVED******REMOVED*** 4. Evaluation Layer

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

***REMOVED******REMOVED******REMOVED*** 5. Configuration

**config.py** - central project configuration:
```python
API_PROVIDER = 'claude'           ***REMOVED*** 'claude', 'openai', 'groq', 'zai'
VECTOR_DB_URL = 'http://localhost:6333'  ***REMOVED*** Qdrant
COLLECTION_NAME = 'legal_documents'
MODEL_NAME = 'claude-3-5-sonnet-20241022'  ***REMOVED*** Main model
EMBEDDING_MODEL = 'BAAI/bge-m3'   ***REMOVED*** 1024-dim vectors
```

---

***REMOVED******REMOVED******REMOVED*** 6. Utility Functions

| Module | Purpose |
|--------|---------|
| `utils/structure_parser.py` | Document structure parser |
| `check_sparse_vectors.py` | Sparse vectors check |
| `list_available_models.py` | List available models |
| `example_search.py` | API usage example |

---

***REMOVED******REMOVED*** Technology Stack

***REMOVED******REMOVED******REMOVED*** Vector Database
- **Qdrant** v0.13.x
- **Dense Embeddings**: BGE-M3 (1024-dim)
- **Sparse Embeddings**: ColBERT
- **Hybrid Search**: DBSF + RRF

***REMOVED******REMOVED******REMOVED*** LLM APIs
- **Anthropic Claude** 3.5 Sonnet (main)
- **OpenAI GPT-4** (alternative)
- **Groq LLaMA3** (fast)
- **Z.AI GLM-4.6** (legacy)

***REMOVED******REMOVED******REMOVED*** ML Platforms
- **MLflow** 2.22.1+ (experiment tracking)
- **Langfuse** 3.0.0+ (LLM observability)
- **RAGAS** 0.2.10+ (RAG evaluation)

***REMOVED******REMOVED******REMOVED*** Code Quality
- **Ruff** 0.14.1 (linting + formatting)
- **MyPy** (type checking)
- **Bandit** (security scanning)
- **Pre-commit** (git hooks)

***REMOVED******REMOVED******REMOVED*** Document Processing
- **PyMuPDF** (PDF parsing)
- **FlagEmbedding** (BGE embeddings)
- **LangChain** (ecosystem utilities)

---

***REMOVED******REMOVED*** Workflow

***REMOVED******REMOVED******REMOVED*** 1️⃣ Setup & Installation
```bash
***REMOVED*** Clone repository
git clone <repo>
cd contextual_rag

***REMOVED*** Install dependencies
pip install -e .

***REMOVED*** Configuration
cp .env.example .env
***REMOVED*** Edit .env with your API keys

***REMOVED*** Start Qdrant via Docker
docker compose up -d qdrant

***REMOVED*** (Optional) Start ML platforms
docker compose --profile ml up -d mlflow langfuse
```

***REMOVED******REMOVED******REMOVED*** 2️⃣ Data Ingestion
```bash
***REMOVED*** Create collection
python create_collection_enhanced.py

***REMOVED*** Load documents
python ingestion_contextual_kg_fast.py \
  --pdf-path docs/documents/ \
  --collection legal_documents
```

***REMOVED******REMOVED******REMOVED*** 3️⃣ Testing
```bash
***REMOVED*** Smoke test
python evaluation/smoke_test.py

***REMOVED*** A/B testing (with MLflow logging)
python evaluation/run_ab_test.py

***REMOVED*** Quick API test
python test_api_quick.py
```

***REMOVED******REMOVED******REMOVED*** 4️⃣ Production Query
```bash
***REMOVED*** Search example
python example_search.py \
  --query "Які право мають громадяни?" \
  --top-k 10
```

***REMOVED******REMOVED******REMOVED*** 5️⃣ Monitoring & Analysis
```bash
***REMOVED*** MLflow Dashboard
open http://localhost:5000

***REMOVED*** Langfuse Dashboard
open http://localhost:3001
```

---

***REMOVED******REMOVED*** Quick Reference

***REMOVED******REMOVED******REMOVED*** Main Commands

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

***REMOVED******REMOVED******REMOVED*** Important Files to Edit

| File | When to Edit |
|------|-------------|
| `.env` | Adding API keys |
| `config.py` | Changing system parameters |
| `prompts.py` | Updating LLM prompts |
| `pyproject.toml` | Adding new dependencies |
| `.pre-commit-config.yaml` | Changing code quality settings |

***REMOVED******REMOVED******REMOVED*** Common Issues

| Issue | Solution |
|-------|----------|
| `ConnectionError` to Qdrant | Run `docker compose up -d qdrant` |
| `APIError` from Claude | Check `.env` key `ANTHROPIC_API_KEY` |
| `ModuleNotFoundError` | Reinstall `pip install -e .` |
| Slow search | Use `ingestion_contextual_kg_fast.py` |
| Low metrics | Check DBSF configuration in `config.py` |

---

***REMOVED******REMOVED*** Module Documentation

Detailed description of each module see in:
- 📖 **MODULE_GUIDE.md** - Description of all modules
- 🚀 **QUICK_START.md** - Step-by-step start
- 📦 **DEPENDENCIES.md** - All dependencies
- 🔧 **DEBUGGING_GUIDE.md** - Troubleshooting

---

***REMOVED******REMOVED*** Contact and Support

- **Issues**: Create GitHub issues
- **Documentation**: See `/docs` folder
- **Status**: Production ready ✅

---

**Last Updated**: 2025-10-29
**Version**: 2.0.1
**Maintainer**: Contextual RAG Team
