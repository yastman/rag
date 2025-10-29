# Documentation Index - Contextual RAG Pipeline

**Last Updated:** 2025-10-23

Complete navigation guide for all project documentation.

---

## 🚀 Quick Start

**New to the project?** Start here:

1. **[README.md](../README.md)** - Project overview & quick start guide
2. **[SETUP.md](../SETUP.md)** - Complete installation instructions
3. **[ARCHITECTURE.md](../ARCHITECTURE.md)** - How the system works

---

## 📚 Core Documentation

### Main Guides (Project Root)

| Document | Description | Audience |
|----------|-------------|----------|
| **[README.md](../README.md)** | Project overview, quick start, services setup | Everyone |
| **[ARCHITECTURE.md](../ARCHITECTURE.md)** | System architecture, components, data flow, technical specs | Developers |
| **[SETUP.md](../SETUP.md)** | Step-by-step installation & configuration | New users |
| **[CODE_QUALITY.md](../CODE_QUALITY.md)** | Code standards, Ruff configuration, best practices | Contributors |

### Configuration Files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Python project config, Ruff linter/formatter settings |
| `.pre-commit-config.yaml` | Git hooks for automatic code quality checks |
| `.env` | Environment variables (API keys, service URLs) |
| `config.py` | Application configuration (thresholds, limits, paths) |
| `prompts.py` | LLM prompts for contextualization |

---

## 📖 Documentation Structure

All documentation is organized in `docs/` folder with the following structure:

```
docs/
├── INDEX.md                    ← You are here (navigation hub)
├── README.md                   ← Quick overview & links
│
├── guides/                     ← How-to guides & tutorials
│   ├── QUICK_START_DBSF.md              ⭐ DBSF + ColBERT quick start
│   ├── DEDUPLICATION_GUIDE.md           Content-based deduplication
│   └── DOC_LING_RAG_TASKS_2025.md       Docling API integration
│
├── implementation/             ← Implementation details
│   ├── DBSF_COLBERT_IMPLEMENTATION_SUMMARY.md    Complete DBSF guide
│   └── IMPLEMENTATION_CHECKLIST.md               Implementation checklist
│
├── reports/                    ← Evaluation results & benchmarks
│   ├── FINAL_REPORT_CONTEXTUAL_RAG.md   A/B test results
│   ├── TEST_RESULTS_SUMMARY.md          API comparison
│   └── FINAL_OPTIMIZATION_REPORT.md     Baseline optimization
│
└── archive/                    ← Historical documents
    ├── NEXT_GEN_RAG_IMPLEMENTATION_PLAN.md      Original plan
    └── IMPLEMENTATION_COMPLETE_SUMMARY.md       Completion summary
```

### 📁 Guides (`docs/guides/`)

| Document | Description |
|----------|-------------|
| **[QUICK_START_DBSF.md](guides/QUICK_START_DBSF.md)** | ⭐ Quick start for DBSF + ColBERT hybrid search |
| **[DEDUPLICATION_GUIDE.md](guides/DEDUPLICATION_GUIDE.md)** | Content-based deduplication using SHA256 |
| **[DOC_LING_RAG_TASKS_2025.md](guides/DOC_LING_RAG_TASKS_2025.md)** | Docling API integration guide |

### 🔧 Implementation (`docs/implementation/`)

| Document | Description |
|----------|-------------|
| **[DBSF_COLBERT_IMPLEMENTATION_SUMMARY.md](implementation/DBSF_COLBERT_IMPLEMENTATION_SUMMARY.md)** | Complete DBSF + ColBERT implementation guide |
| **[IMPLEMENTATION_CHECKLIST.md](implementation/IMPLEMENTATION_CHECKLIST.md)** | Step-by-step implementation checklist |

### 📊 Reports (`docs/reports/`)

| Document | Date | Description |
|----------|------|-------------|
| **[FINAL_REPORT_CONTEXTUAL_RAG.md](reports/FINAL_REPORT_CONTEXTUAL_RAG.md)** | 2025-10 | A/B test: Baseline vs Contextual+KG |
| **[TEST_RESULTS_SUMMARY.md](reports/TEST_RESULTS_SUMMARY.md)** | 2025-10 | API provider comparison (Z.AI, Groq, OpenAI, Claude) |
| **[FINAL_OPTIMIZATION_REPORT.md](reports/FINAL_OPTIMIZATION_REPORT.md)** | 2025-10 | Baseline optimization report |

### 📦 Archive (`docs/archive/`)

Historical documents for reference:

| Document | Date | Description |
|----------|------|-------------|
| **[NEXT_GEN_RAG_IMPLEMENTATION_PLAN.md](archive/NEXT_GEN_RAG_IMPLEMENTATION_PLAN.md)** | 2025-10 | Original implementation plan (completed) |
| **[IMPLEMENTATION_COMPLETE_SUMMARY.md](archive/IMPLEMENTATION_COMPLETE_SUMMARY.md)** | 2025-10 | Implementation completion summary |

---

## 🔍 Component Documentation

### Ingestion Pipeline

**Files:**
- `ingestion_contextual_kg.py` - Sync implementation
- `ingestion_contextual_kg_fast.py` - ⭐ Async implementation (15-50x faster)

**Key features:**
- Adaptive chunking (Docling vs PyMuPDF)
- Async contextualization (10 concurrent)
- Fallback system for reliability
- Content-based deduplication

### Contextualization APIs

**Supported providers:**
- `contextualize.py` - Anthropic Claude (sync)
- `contextualize_openai_async.py` - OpenAI GPT-4o-mini (async)
- `contextualize_groq_async.py` - Groq Llama-3.3-70b (async)
- `contextualize_zai_async.py` - ⭐ Z.AI (async, recommended)

**See:** [TEST_RESULTS_SUMMARY.md](TEST_RESULTS_SUMMARY.md) for comparison

### Search Engines

**Location:** `evaluation/search_engines.py`

**Implementations:**
1. **BaselineSearchEngine** - Dense vectors only (simple, fast)
2. **HybridSearchEngine** - Dense + Sparse with RRF fusion
3. **HybridDBSFColBERTSearchEngine** - ⭐ DBSF fusion + ColBERT reranking

**Status:** DBSF+ColBERT implemented but not tested yet

**See:** [ARCHITECTURE.md](../ARCHITECTURE.md) for technical details

### Evaluation Framework

**Files:**
- `evaluation/evaluator.py` - Metrics implementation
- `evaluation/run_ab_test.py` - A/B testing framework
- `evaluation/extract_ground_truth.py` - Ground truth extraction
- `evaluation/generate_test_queries.py` - Test query generation

**Metrics:**
- Recall@K
- NDCG@K
- Precision@K
- MRR (Mean Reciprocal Rank)
- Failure Rate@K

---

## 🎯 By Task

### I want to...

#### ...install the system
→ Start with **[SETUP.md](../SETUP.md)**

#### ...understand how it works
→ Read **[ARCHITECTURE.md](../ARCHITECTURE.md)**

#### ...run a test
→ Follow **Quick Test** in [SETUP.md](../SETUP.md#first-test-run)

#### ...add a new feature
→ Check **[CODE_QUALITY.md](../CODE_QUALITY.md)** for standards

#### ...optimize search
→ Review **[DBSF + ColBERT Implementation](implementation/DBSF_COLBERT_IMPLEMENTATION_SUMMARY.md)**
→ Quick start: **[QUICK_START_DBSF.md](guides/QUICK_START_DBSF.md)**

#### ...compare APIs
→ See **[API Comparison Report](reports/TEST_RESULTS_SUMMARY.md)**

#### ...evaluate performance
→ Run **`evaluation/run_ab_test.py`** (see [README.md](../README.md#evaluation))
→ Review **[Evaluation Results](reports/FINAL_REPORT_CONTEXTUAL_RAG.md)**

#### ...fix code quality issues
→ Follow **[CODE_QUALITY.md](../CODE_QUALITY.md)**

#### ...integrate Docling
→ Read **[Docling Integration Guide](guides/DOC_LING_RAG_TASKS_2025.md)**

#### ...prevent duplicates
→ See **[Deduplication Guide](guides/DEDUPLICATION_GUIDE.md)**

---

## 🔧 Configuration Reference

### Environment Variables (.env)

**Required:**
- `QDRANT_URL` - Qdrant API endpoint
- `QDRANT_API_KEY` - Qdrant API key
- `BGE_M3_URL` - BGE-M3 embedding API
- `DOCLING_URL` - Docling document processing API
- At least one LLM API key (ZAI/Groq/OpenAI/Anthropic)

**Optional:**
- `ZAI_RATE_LIMIT_DELAY` - Rate limiting (default: 0.1s)
- `ASYNC_SEMAPHORE_LIMIT` - Max concurrent requests (default: 10)
- `COLLECTION_BASELINE` - Baseline collection name
- `COLLECTION_CONTEXTUAL_KG` - Contextual collection name
- `PDF_PATH` - Default PDF path

### Application Config (config.py)

**Key parameters:**
- `SCORE_THRESHOLD_*` - Search score thresholds
- `HNSW_EF_*` - HNSW search precision
- `RETRIEVAL_LIMIT_STAGE*` - Multi-stage retrieval limits
- `BATCH_SIZE_*` - Batch processing sizes

**See:** [config.py](../config.py) for full list

---

## 📊 Performance Data

### Ingestion Benchmarks (132 chunks)

| Implementation | Time | Speed | API |
|----------------|------|-------|-----|
| Sync | 18-20 min | 1x | Any |
| Async | 3-6 min | 15-50x | Z.AI/Groq |

### API Costs (132 chunks)

| Provider | Cost | Time | Quality |
|----------|------|------|---------|
| Z.AI | $3/mo fixed | 3-5 min | Good |
| Groq | Free* | 2-4 min | Good |
| OpenAI | ~$8 | 5-8 min | Very Good |
| Claude | ~$12 | 8-12 min | Excellent |

*Free tier has rate limits

### Search Latency (estimated)

| Engine | Latency | Quality |
|--------|---------|---------|
| Baseline (dense only) | 30-50ms | Good |
| Hybrid RRF | 80-120ms | Better |
| DBSF + ColBERT | 200-300ms | Best |

---

## 🐛 Troubleshooting

Common issues and solutions:

1. **Service connection errors** → Check Docker containers ([SETUP.md](../SETUP.md#troubleshooting))
2. **API key errors** → Verify .env configuration ([SETUP.md](../SETUP.md#issue-api-key-not-found-or-401-unauthorized))
3. **Code quality errors** → Run `ruff check --fix .` ([CODE_QUALITY.md](../CODE_QUALITY.md))
4. **BGE-M3 model not found** → Check volume ([SETUP.md](../SETUP.md#issue-bge-m3-model-not-found))
5. **Rate limits** → Adjust config ([SETUP.md](../SETUP.md#issue-rate-limits-groqopenai-free-tier))

---

## 🔗 External Resources

##***REMOVED*** Documentation
- [Hybrid Search](https://qdrant.tech/articles/hybrid-search/) - DBSF + ColBERT methodology
- [Knowledge Graphs](https://qdrant.tech/articles/knowledge-graphs-rag/) - KG integration
- [Quantization](https://qdrant.tech/documentation/guides/quantization/) - INT8 quantization

### Research Papers
- [Anthropic Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval) - Original methodology
- [BGE-M3](https://arxiv.org/abs/2402.03216) - Multi-lingual multi-functionality embeddings
- [ColBERT](https://arxiv.org/abs/2004.12832) - Late interaction for efficient retrieval

### Tools & Libraries
- [Ruff](https://docs.astral.sh/ruff/) - Python linter & formatter
- [Qdrant](https://qdrant.tech/documentation/) - Vector database
- [FlagEmbedding](https://github.com/FlagOpen/FlagEmbedding) - BGE models

---

## 📋 Document Status

| Document | Status | Last Updated |
|----------|--------|--------------|
| README.md | ✅ Current | 2025-10-23 |
| ARCHITECTURE.md | ✅ Current | 2025-10-23 |
| SETUP.md | ✅ Current | 2025-10-23 |
| CODE_QUALITY.md | ✅ Current | 2025-10-23 |
| Research docs | ⚠️ Archive | 2025-10 |

**Legend:**
- ✅ Current - Up to date
- ⚠️ Archive - Historical reference, may be outdated
- 🔄 In Progress - Being updated

---

## 🎯 Quick Links

**Getting Started:**
- [Installation](../SETUP.md#installation-steps)
- [Configuration](../SETUP.md#configuration)
- [First Test](../SETUP.md#first-test-run)

**Development:**
- [Architecture Overview](../ARCHITECTURE.md#system-overview)
- [Code Quality](../CODE_QUALITY.md)
- [Search Engines](../ARCHITECTURE.md#search-engines)

**Evaluation:**
- [Run A/B Test](../README.md#evaluation)
- [Metrics](../ARCHITECTURE.md#technical-specifications)
- [Results](reports/FINAL_REPORT_CONTEXTUAL_RAG.md)

**Optimization:**
- [DBSF + ColBERT](implementation/DBSF_COLBERT_IMPLEMENTATION_SUMMARY.md)
- [Quick Start Guide](guides/QUICK_START_DBSF.md)
- [Payload Indexes](../ARCHITECTURE.md#payload-indexes)
- [Performance Tuning](../ARCHITECTURE.md#performance-optimization)

---

**Maintained by:** Claude Code + Sequential Thinking MCP
**Last Review:** 2025-10-23
**Next Review:** When major features are added
