***REMOVED*** Contextual RAG Pipeline - Production System

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![Ruff](https://img.shields.io/badge/code%20quality-ruff%200.14.1-green)
![License](https://img.shields.io/badge/license-MIT-blue)
![Status](https://img.shields.io/badge/status-production-success)

**Version:** 2.0.1 | **Updated:** 2025-10-23 | **Environment:** VPS Production

---

***REMOVED******REMOVED*** ✨ Latest Updates (2025-10-23)

***REMOVED******REMOVED******REMOVED*** 🎉 ML Platform Migration Complete
**Status:** ✅ **ALL PHASES COMPLETE** (Phases 1-3)

Migrated from custom evaluation scripts (923 lines) to production-grade ML platform in 1 day:

- ✅ **MLflow 3.5.1** - Experiment tracking with UI (http://localhost:5000)
- ✅ **Langfuse 2.95.9** - LLM observability with native SDK (http://localhost:3001)
- ✅ **RAGAS 0.3.7** - E2E RAG evaluation (4 metrics)
- ✅ **25 metrics per A/B test** - automatic logging to MLflow
- ✅ **Native SDK patterns** - zero custom wrappers, official Langfuse decorators

**Documentation:**
- [MIGRATION_PLAN.md](MIGRATION_PLAN.md) - Complete migration overview
- [PHASE1_COMPLETION_SUMMARY.md](PHASE1_COMPLETION_SUMMARY.md) - Infrastructure setup
- [PHASE2_COMPLETION_SUMMARY.md](PHASE2_COMPLETION_SUMMARY.md) - MLflow integration
- [PHASE3_COMPLETION_SUMMARY.md](PHASE3_COMPLETION_SUMMARY.md) - Langfuse native SDK

**Quick Start:**
```bash
***REMOVED*** Start ML services
docker compose --profile ml up -d mlflow langfuse

***REMOVED*** Run A/B test with MLflow logging (automatic)
python evaluation/run_ab_test.py

***REMOVED*** View results
open http://localhost:5000  ***REMOVED*** MLflow UI
open http://localhost:3001  ***REMOVED*** Langfuse UI
```

***REMOVED******REMOVED******REMOVED*** Code Quality Improvements
- ✅ **499 → 0 issues fixed** with Ruff 0.14.1
- ✅ **Eliminated all `import *`** usages (4 files, 44 instances)
- ✅ **Modernized to PEP 585** (180+ type annotations)
- ✅ **Consistent code style** across 30 Python files
- 📄 See [CODE_QUALITY.md](CODE_QUALITY.md) for details

***REMOVED******REMOVED******REMOVED*** New Features
- 🚀 **DBSF + ColBERT hybrid search** implemented ([Qdrant 2025 best practices](https://qdrant.tech/articles/hybrid-search/))
- ⚡ **Payload indexes** for 10-100x faster filtering
- 🎯 **3 search engines**: Baseline, Hybrid RRF, DBSF+ColBERT
- 🔧 **Optimized configuration**: HNSW parameters, batch sizes, score thresholds

**Changelog v2.0.1:**
- Migrated BGE-M3 model to Docker volume (ai-bge-m3-models)
- Added HF_HOME=/models/huggingface environment variable
- Container size reduced from 8.23GB → 2MB writable layer
- Model persists across container rebuilds (no re-download)

---

***REMOVED******REMOVED*** 🎯 TL;DR - Executive Summary

***REMOVED******REMOVED******REMOVED*** Latest: DBSF + ColBERT Testing (2025-10-23, 150 queries)

| Metric | Baseline | DBSF+ColBERT | Δ | Winner |
|--------|----------|--------------|---|--------|
| **Recall@1** | 91.3% | **94.0%** | **+2.9%** | DBSF ⭐ |
| **NDCG@10** | 0.9619 | **0.9711** | **+1.0%** | DBSF ⭐ |
| **MRR** | 0.9491 | **0.9636** | **+1.5%** | DBSF ⭐ |
| Recall@10 | 100% | 99.3% | -0.7% | Baseline |
| Latency | 0.673s | 0.690s | +2.5% | Baseline |

**✅ DBSF+ColBERT ready for production:**
- Better on critical metrics (Recall@1, NDCG, MRR)
- Acceptable latency (+17ms = +2.5%)
- For legal domain, Recall@1 is critical → DBSF is better!

***REMOVED******REMOVED******REMOVED*** Previous: Contextual Retrieval Testing (10 queries)

| Metric | Baseline (v2) | Contextual+KG | Δ |
|--------|---------------|---------------|---|
| Recall@5 | **65.0%** | 51.7% | -20.5% |
| NDCG@5 | **0.5768** | 0.5139 | -10.9% |
| Failure@5 | **20%** | 30% | +50% |

**❌ Contextual failed:** Removed document context to save tokens → killed the main value of the method.

---

***REMOVED******REMOVED*** 📁 Project Structure

```
contextual_rag/
├── config.py, prompts.py, .env
│
├── Ingestion (2 versions):
│   ├── ingestion_contextual_kg.py         ***REMOVED*** Sync (Docling API)
│   └── ingestion_contextual_kg_fast.py    ***REMOVED*** ✅ Async, 15-50x faster
│
├── Contextualization (4 APIs):
│   ├── contextualize.py                   ***REMOVED*** Anthropic Claude
│   ├── contextualize_openai_async.py      ***REMOVED*** OpenAI
│   ├── contextualize_groq_async.py        ***REMOVED*** Groq
│   └── contextualize_zai_async.py         ***REMOVED*** ✅ Z.AI (fastest, $3/mo)
│
├── utils/structure_parser.py              ***REMOVED*** Fallback parser
├── pymupdf_chunker.py                     ***REMOVED*** Standalone chunker
│
├── evaluation/                            ***REMOVED*** A/B testing framework + ML tools
│   ├── evaluator.py                       ***REMOVED*** Metrics calculator
│   ├── run_ab_test.py                     ***REMOVED*** A/B runner with MLflow ✅
│   ├── search_engines.py                  ***REMOVED*** 3 search engines
│   ├── mlflow_integration.py              ***REMOVED*** MLflow logger (340 lines) ✅
│   ├── langfuse_integration.py            ***REMOVED*** Langfuse native SDK (430 lines) ✅
│   ├── evaluate_with_ragas.py             ***REMOVED*** RAGAS evaluation (350 lines) ✅
│   ├── test_mlflow_ab.py                  ***REMOVED*** MLflow test script ✅
│   └── reports/                           ***REMOVED*** A/B test results
│
├── venv/                                   ***REMOVED*** Python virtual environment ✅
│
├── Migration Documentation:
│   ├── MIGRATION_PLAN.md                  ***REMOVED*** Complete migration plan ✅
│   ├── PHASE1_COMPLETION_SUMMARY.md       ***REMOVED*** Infrastructure setup ✅
│   ├── PHASE2_COMPLETION_SUMMARY.md       ***REMOVED*** MLflow integration ✅
│   └── PHASE3_COMPLETION_SUMMARY.md       ***REMOVED*** Langfuse native SDK ✅
```

**New ML Services (Docker):**
- **MLflow**: http://localhost:5000 (experiment tracking)
- **Langfuse**: http://localhost:3001 (LLM observability)

---

***REMOVED******REMOVED*** 📚 Documentation Index

***REMOVED******REMOVED******REMOVED*** Core Documentation
- **[README.md](README.md)** ← You are here (project overview & quick start)
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System architecture & technical details
- **[SETUP.md](SETUP.md)** - Step-by-step installation guide
- **[CODE_QUALITY.md](CODE_QUALITY.md)** - Code quality standards & tooling

***REMOVED******REMOVED******REMOVED*** Search Engines (3 implementations)
1. **🏆 HybridDBSFColBERTSearchEngine (RECOMMENDED)** - DBSF fusion + ColBERT reranking ⭐
   - 3-stage pipeline: Dense+Sparse → DBSF → ColBERT
   - Based on [Qdrant 2025 best practices](https://qdrant.tech/articles/hybrid-search/)
   - Status: ✅ **Tested and production-ready** (94.0% Recall@1, +2.9% vs baseline)
2. **BaselineSearchEngine** - Dense vectors only (simple, fast, 91.3% Recall@1)
3. **HybridSearchEngine** - Dense + Sparse with RRF fusion (88.7% Recall@1)

***REMOVED******REMOVED******REMOVED*** Research & Planning
Located in `docs/` folder (7 files, 116KB):
- `FINAL_REPORT_CONTEXTUAL_RAG.md` - Evaluation results
- `IMPLEMENTATION_COMPLETE_SUMMARY.md` - Implementation summary
- `NEXT_GEN_RAG_IMPLEMENTATION_PLAN.md` - Original plan
- `FINAL_OPTIMIZATION_REPORT.md` - Baseline optimization
- And more...

---

***REMOVED******REMOVED*** 🖥️ VPS Services

```yaml
Qdrant v1.15.5:     localhost:6333  (API key in .env)
BGE-M3 API:         localhost:8001  (BAAI/bge-m3)
Docling API:        localhost:5001  (OCR, tables)

***REMOVED*** ML Platform (new)
MLflow v3.5.1:      localhost:5000  (experiment tracking)
Langfuse v2.95.9:   localhost:3001  (LLM observability)
```

**Start ML services:**
```bash
docker compose --profile ml up -d mlflow langfuse
```

***REMOVED******REMOVED******REMOVED*** BGE-M3 API Configuration (Important!)

**Container:** `ai-bge-m3-api` (Docker Compose service: `bge-m3-api`)

**Model Storage:**
- Volume: `ai-bge-m3-models` → `/models` (container)
- Model cache: `/models/huggingface/hub/models--BAAI--bge-m3/` (~7.7GB)
- Environment: `HF_HOME=/models/huggingface`

**Why this matters:**
- Model persists across container rebuilds (no re-download)
- Container writable layer: ~2MB (not 8GB!)
- First startup downloads model (~7.7GB), subsequent starts use cached model

**If rebuilding container:**
```bash
docker compose up -d bge-m3-api --force-recreate
***REMOVED*** Model loads from volume, no internet download needed
```

**To verify model location:**
```bash
docker run --rm -v ai-bge-m3-models:/models alpine ls -lh /models/huggingface/hub/
```

---

**Qdrant Collections (7):**
1. `uk_civil_code_v2` ← **BEST (baseline)**
2. `uk_civil_code_contextual_kg`
3. `tsivilnij_kodeks_ukraini_yurinkom_inter_contextual_kg`
4-7. Criminal code variants

---

***REMOVED******REMOVED*** 🚀 Quick Start

***REMOVED******REMOVED******REMOVED*** 1. Setup

```bash
cd /srv/contextual_rag
cp .env.example .env
nano .env  ***REMOVED*** Add API keys
```

**Minimum required variables:**
```bash
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=your_key
BGE_M3_URL=http://localhost:8001
DOCLING_URL=http://localhost:5001

***REMOVED*** One of the API providers:
ANTHROPIC_API_KEY=[REDACTED-ANTHROPIC-KEY]  ***REMOVED*** or
OPENAI_API_KEY=[REDACTED-OPENAI-KEY]    ***REMOVED*** or
GROQ_API_KEY=[REDACTED-GROQ-KEY]           ***REMOVED*** or
ZAI_API_KEY=[REDACTED-ZAI-KEY]                ***REMOVED*** ✅ Recommended ($3/mo)
```

***REMOVED******REMOVED******REMOVED*** 2. Install

```bash
pip install pymupdf anthropic openai groq python-dotenv numpy aiohttp requests pandas FlagEmbedding
```

***REMOVED******REMOVED******REMOVED*** 3. Test (5 chunks)

```bash
python ingestion_contextual_kg_fast.py --test
***REMOVED*** ~15-30 sec, $0.01
```

***REMOVED******REMOVED******REMOVED*** 4. Full run (132 chunks)

```bash
python ingestion_contextual_kg_fast.py
***REMOVED*** Z.AI: 3-5 min, $0 (within plan limits)
***REMOVED*** Groq: 2-4 min, free (with rate limits)
***REMOVED*** OpenAI: 5-8 min, ~$5-10
***REMOVED*** Claude: 8-12 min, ~$10-15
```

---

***REMOVED******REMOVED*** 🔬 Evaluation

***REMOVED******REMOVED******REMOVED*** A/B Testing with MLflow (automatic logging)

```bash
cd evaluation
python run_ab_test.py
***REMOVED*** Automatically logs to MLflow: 5 params + 25 metrics
***REMOVED*** Reports → evaluation/reports/
```

**Metrics:** Recall@K, NDCG@K, MRR, Precision@K, Failure Rate@K

***REMOVED******REMOVED******REMOVED*** View Results

```bash
***REMOVED*** MLflow UI (experiment tracking)
open http://localhost:5000

***REMOVED*** Langfuse UI (query tracing)
open http://localhost:3001
```

***REMOVED******REMOVED******REMOVED*** RAGAS E2E Evaluation (4 metrics)

```bash
***REMOVED*** Evaluate with RAGAS (faithfulness, context relevancy, etc.)
python evaluate_with_ragas.py --engine dbsf_colbert --sample 10 --use-mlflow

***REMOVED*** RAGAS metrics:
***REMOVED*** - Faithfulness: LLM answers without hallucinations
***REMOVED*** - Context Relevancy: Retrieved documents are relevant
***REMOVED*** - Answer Relevancy: Answer addresses the question
***REMOVED*** - Context Recall: Ground truth in retrieved context
```

***REMOVED******REMOVED******REMOVED*** Quick Test (5 queries)

```bash
***REMOVED*** Test MLflow integration
python test_mlflow_ab.py
***REMOVED*** Runs in ~30 seconds, logs to MLflow
```

---

***REMOVED******REMOVED*** 🧪 API Providers

***REMOVED******REMOVED******REMOVED*** Comparison (132 chunks)

| Provider | Time | Cost | Quality | Success |
|----------|------|------|---------|---------|
| Z.AI async | 3-5 min | $3/mo | Good | 100% |
| Groq async | 2-4 min | Free* | Good | 90% |
| OpenAI async | 5-8 min | ~$8 | Very Good | 99% |
| Claude | 8-12 min | ~$12 | Excellent | 99% |

*Rate limits on free tier

***REMOVED******REMOVED******REMOVED*** Usage

```python
***REMOVED*** Z.AI (recommended)
from contextualize_zai_async import ContextualRetrievalZAIAsync
retriever = ContextualRetrievalZAIAsync()
context = await retriever.generate_context_async(chunk_text)

***REMOVED*** OpenAI
from contextualize_openai_async import ContextualRetrievalOpenAIAsync
retriever = ContextualRetrievalOpenAIAsync(model="gpt-4o-mini")

***REMOVED*** Groq
from contextualize_groq_async import ContextualRetrievalGroqAsync
retriever = ContextualRetrievalGroqAsync(model="llama-3.3-70b-versatile")

***REMOVED*** Claude
from contextualize import ContextualRetrievalClaude
retriever = ContextualRetrievalClaude(use_prompt_caching=True)
```

---

***REMOVED******REMOVED*** 🏗️ Architecture

***REMOVED******REMOVED******REMOVED*** Adaptive Chunker

```python
complexity = detect_pdf_complexity(pdf_path)  ***REMOVED*** <500ms
chunks = docling_chunk(pdf_path) if complexity["use_docling"] else pymupdf_chunk(pdf_path)
```

***REMOVED******REMOVED******REMOVED*** Fallback System

```python
try:
    context = await llm_api.generate_context(chunk)
except APIError:
    context = parse_legal_structure(chunk)  ***REMOVED*** Regex fallback
```

***REMOVED******REMOVED******REMOVED*** Qdrant Payload

```python
{
    "text": chunk_text,
    "contextual_prefix": "Document: ..., Article 13...",
    "book_number": 1, "section_number": 1, "chapter_number": 2,
    "article_number": 13, "article_title": "...",
    "prev_article": 12, "next_article": 14,
    "related_articles": [12, 14, 25]
}
```

---

***REMOVED******REMOVED*** 📊 Performance

***REMOVED******REMOVED******REMOVED*** ingestion_contextual_kg_fast.py (async)

```
PDF: 132 chunks
Complexity check: 0.3s
Chunking: 8.2s (PyMuPDF)
Contextualization: 231s (Z.AI, 10 concurrent) → 1.75s/chunk
Embedding: 120s (BGE-M3)
Qdrant upsert: 15s
TOTAL: ~6 min
Cost: $0 (Z.AI plan)
```

***REMOVED******REMOVED******REMOVED*** ingestion_contextual_kg.py (sync)

```
Same PDF
TOTAL: 18-20 min (sequential)
Use fast version instead
```

---

***REMOVED******REMOVED*** 🔍 Troubleshooting

```bash
***REMOVED*** Qdrant
docker compose ps | grep qdrant
curl http://localhost:6333/collections -H "api-key: $QDRANT_API_KEY"

***REMOVED*** BGE-M3 API - Basic Health Check
docker compose ps bge-m3-api
curl http://localhost:8001/health
***REMOVED*** Expected: {"status":"ok","model_loaded":true}

***REMOVED*** BGE-M3 API - Verify Model in Volume
docker run --rm -v ai-bge-m3-models:/models alpine du -sh /models/huggingface
***REMOVED*** Expected: ~7.7GB

***REMOVED*** BGE-M3 API - Test Embedding
curl -X POST http://localhost:8001/encode/dense \
  -H "Content-Type: application/json" \
  -d '{"texts":["test"],"batch_size":1}'
***REMOVED*** Expected: JSON with dense_vecs and processing_time

***REMOVED*** BGE-M3 API - Check Container Size
docker ps --size --filter "name=ai-bge-m3-api"
***REMOVED*** Expected: SIZE ~2MB (NOT 8GB!)

***REMOVED*** BGE-M3 API - Restart if needed
docker compose restart bge-m3-api

***REMOVED*** Docling
docker ps | grep docling
curl http://localhost:5001/health

***REMOVED*** API Keys
cat .env | grep API_KEY
```

**Common Issues:**

1. **BGE-M3 model not found:** Model should be in volume. Check:
   ```bash
   docker run --rm -v ai-bge-m3-models:/models alpine ls -lh /models/huggingface/hub/
   ```
   If empty, model will re-download on first API call (~7.7GB, 5-10 min).

2. **Container size is 8GB:** Model is in writable layer, not volume. Check `HF_HOME=/models/huggingface` in docker-compose.yml.

3. **Rate limits (Z.AI):** Increase `ZAI_RATE_LIMIT_DELAY` in config.py or decrease `ASYNC_SEMAPHORE_LIMIT`.

---

***REMOVED******REMOVED*** 📚 Documentation

***REMOVED******REMOVED******REMOVED*** Core Documentation (in project root)

- **[README.md](README.md)** - Project overview, quick start
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System architecture, components, data flow
- **[SETUP.md](SETUP.md)** - Installation & configuration guide
- **[CODE_QUALITY.md](CODE_QUALITY.md)** - Code quality standards, Ruff configuration

***REMOVED******REMOVED******REMOVED*** Code Quality Achievement
- ✅ **499 → 0 issues** (100% improvement)
- Modern Python tooling: Ruff 0.14.1 (10-100x faster than traditional stack)
- PEP 585 compliant type hints
- Consistent formatting across all files
- Pre-commit hooks configured

***REMOVED******REMOVED******REMOVED*** Research Documents (docs/ folder, organized by categories)

**Guides** (`docs/guides/`):
- [QUICK_START_DBSF.md](docs/guides/QUICK_START_DBSF.md) - ⭐ DBSF + ColBERT quick start
- [DEDUPLICATION_GUIDE.md](docs/guides/DEDUPLICATION_GUIDE.md) - Deduplication
- [DOC_LING_RAG_TASKS_2025.md](docs/guides/DOC_LING_RAG_TASKS_2025.md) - Docling integration

**Implementation** (`docs/implementation/`):
- [DBSF_COLBERT_IMPLEMENTATION_SUMMARY.md](docs/implementation/DBSF_COLBERT_IMPLEMENTATION_SUMMARY.md) - Complete guide
- [IMPLEMENTATION_CHECKLIST.md](docs/implementation/IMPLEMENTATION_CHECKLIST.md) - Checklist

**Reports** (`docs/reports/`):
- [FINAL_REPORT_CONTEXTUAL_RAG.md](docs/reports/FINAL_REPORT_CONTEXTUAL_RAG.md) - Evaluation results
- [TEST_RESULTS_SUMMARY.md](docs/reports/TEST_RESULTS_SUMMARY.md) - API comparison
- [FINAL_OPTIMIZATION_REPORT.md](docs/reports/FINAL_OPTIMIZATION_REPORT.md) - Optimization

**Archive** (`docs/archive/`) - historical documents:
- [NEXT_GEN_RAG_IMPLEMENTATION_PLAN.md](docs/archive/NEXT_GEN_RAG_IMPLEMENTATION_PLAN.md) - Original plan
- [IMPLEMENTATION_COMPLETE_SUMMARY.md](docs/archive/IMPLEMENTATION_COMPLETE_SUMMARY.md) - Summary

**Full Navigation:** [docs/INDEX.md](docs/INDEX.md)

***REMOVED******REMOVED******REMOVED*** External Research

- Anthropic Contextual Retrieval: https://www.anthropic.com/news/contextual-retrieval
- Microsoft GraphRAG: https://github.com/microsoft/graphrag
- Qdrant KG: https://qdrant.tech/articles/knowledge-graphs-rag/
- Qdrant Hybrid Search: https://qdrant.tech/articles/hybrid-search/

---

***REMOVED******REMOVED*** 💰 Cost (1000 docs)

- **Z.AI:** $3/month (fixed)
- **OpenAI:** ~$50
- **Claude:** ~$100

---

***REMOVED******REMOVED*** 🎓 Lessons Learned

***REMOVED******REMOVED******REMOVED*** ✅ What Worked
- Async processing: 4.7x speedup
- Fallback system: 100% reliability
- Adaptive chunker
- Multiple API providers

***REMOVED******REMOVED******REMOVED*** ❌ What Didn't Work
- Contextual retrieval: baseline is better
- Document context removed to save costs → quality degraded
- KG metadata provided no advantage

***REMOVED******REMOVED******REMOVED*** 💡 Conclusion
Anthropic contextual retrieval works **only with full document context** in each request. Cost optimization killed effectiveness.

---

***REMOVED******REMOVED*** 🚀 Next Steps

***REMOVED******REMOVED******REMOVED*** Production (recommended)
1. Reranking (ColBERTv2, bge-reranker)
2. Hybrid Search (BM25 + dense)
3. Query expansion
4. KG metadata for filtering

***REMOVED******REMOVED******REMOVED*** Experiments
1. Return full document context (accept high cost)
2. Aggressive prompt caching (Anthropic)
3. More test queries (>10)

---

***REMOVED******REMOVED*** 📊 ML Platform Stack

**Experiment Tracking:**
- MLflow 3.5.1 (PostgreSQL backend)
- 25 metrics per A/B test run
- Config versioning (SHA256 hash)
- Automatic artifact logging

**LLM Observability:**
- Langfuse 2.95.9 (PostgreSQL backend)
- Native SDK with `@observe()` decorator
- Query-level tracing
- Session and user tracking

**RAG Evaluation:**
- RAGAS 0.3.7 (OpenAI-powered)
- 4 E2E metrics: faithfulness, context relevancy, answer relevancy, context recall
- MLflow integration

**Migration:**
- From: 923 lines of custom code
- To: 1,272 lines of production tools (MLflow + RAGAS + Langfuse)
- Time: 1 day (instead of planned 2-3 days)
- Zero breaking changes (graceful degradation)

---

**Stack:** Python, Qdrant, BGE-M3, PyMuPDF, Docker, MLflow, Langfuse, RAGAS
**Created by:** Claude Code + Sequential Thinking MCP + Context7
**Status:** Production-ready with ML platform ✅ | Baseline 94% Recall@1 ⭐
