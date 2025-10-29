# Contextual RAG Pipeline - Production System

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![Ruff](https://img.shields.io/badge/code%20quality-ruff%200.14.1-green)
![License](https://img.shields.io/badge/license-MIT-blue)
![Status](https://img.shields.io/badge/status-production-success)

**Version:** 2.0.1 | **Updated:** 2025-10-23 | **Environment:** VPS Production

---

## ✨ Latest Updates (2025-10-23)

### 🎉 ML Platform Migration Complete
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
# Start ML services
docker compose --profile ml up -d mlflow langfuse

# Run A/B test with MLflow logging (automatic)
python evaluation/run_ab_test.py

# View results
open http://localhost:5000  # MLflow UI
open http://localhost:3001  # Langfuse UI
```

### Code Quality Improvements
- ✅ **499 → 0 issues fixed** with Ruff 0.14.1
- ✅ **Eliminated all `import *`** usages (4 files, 44 instances)
- ✅ **Modernized to PEP 585** (180+ type annotations)
- ✅ **Consistent code style** across 30 Python files
- 📄 See [CODE_QUALITY.md](CODE_QUALITY.md) for details

### New Features
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

## 🎯 TL;DR - Executive Summary

### Latest: DBSF + ColBERT Testing (2025-10-23, 150 queries)

| Metric | Baseline | DBSF+ColBERT | Δ | Winner |
|--------|----------|--------------|---|--------|
| **Recall@1** | 91.3% | **94.0%** | **+2.9%** | DBSF ⭐ |
| **NDCG@10** | 0.9619 | **0.9711** | **+1.0%** | DBSF ⭐ |
| **MRR** | 0.9491 | **0.9636** | **+1.5%** | DBSF ⭐ |
| Recall@10 | 100% | 99.3% | -0.7% | Baseline |
| Latency | 0.673s | 0.690s | +2.5% | Baseline |

**✅ DBSF+ColBERT готов к production:**
- Лучше по критичным метрикам (Recall@1, NDCG, MRR)
- Приемлемый latency (+17ms = +2.5%)
- Для legal domain Recall@1 критичен → DBSF лучше!

### Previous: Contextual Retrieval Testing (10 queries)

| Metric | Baseline (v2) | Contextual+KG | Δ |
|--------|---------------|---------------|---|
| Recall@5 | **65.0%** | 51.7% | -20.5% |
| NDCG@5 | **0.5768** | 0.5139 | -10.9% |
| Failure@5 | **20%** | 30% | +50% |

**❌ Contextual провалился:** Удалили document context для экономии токенов → убили основную ценность метода.

---

## 📁 Структура Проекта

```
contextual_rag/
├── config.py, prompts.py, .env
│
├── Ingestion (2 версии):
│   ├── ingestion_contextual_kg.py         # Sync (Docling API)
│   └── ingestion_contextual_kg_fast.py    # ✅ Async, 15-50x faster
│
├── Contextualization (4 API):
│   ├── contextualize.py                   # Anthropic Claude
│   ├── contextualize_openai_async.py      # OpenAI
│   ├── contextualize_groq_async.py        # Groq
│   └── contextualize_zai_async.py         # ✅ Z.AI (fastest, $3/mo)
│
├── utils/structure_parser.py              # Fallback парсер
├── pymupdf_chunker.py                     # Standalone chunker
│
├── evaluation/                            # A/B testing framework + ML tools
│   ├── evaluator.py                       # Metrics calculator
│   ├── run_ab_test.py                     # A/B runner with MLflow ✅
│   ├── search_engines.py                  # 3 search engines
│   ├── mlflow_integration.py              # MLflow logger (340 lines) ✅
│   ├── langfuse_integration.py            # Langfuse native SDK (430 lines) ✅
│   ├── evaluate_with_ragas.py             # RAGAS evaluation (350 lines) ✅
│   ├── test_mlflow_ab.py                  # MLflow test script ✅
│   └── reports/                           # A/B test results
│
├── venv/                                   # Python virtual environment ✅
│
├── Migration Documentation:
│   ├── MIGRATION_PLAN.md                  # Complete migration plan ✅
│   ├── PHASE1_COMPLETION_SUMMARY.md       # Infrastructure setup ✅
│   ├── PHASE2_COMPLETION_SUMMARY.md       # MLflow integration ✅
│   └── PHASE3_COMPLETION_SUMMARY.md       # Langfuse native SDK ✅
```

**New ML Services (Docker):**
- **MLflow**: http://localhost:5000 (experiment tracking)
- **Langfuse**: http://localhost:3001 (LLM observability)

---

## 📚 Documentation Index

### Core Documentation
- **[README.md](README.md)** ← You are here (project overview & quick start)
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System architecture & technical details
- **[SETUP.md](SETUP.md)** - Step-by-step installation guide
- **[CODE_QUALITY.md](CODE_QUALITY.md)** - Code quality standards & tooling

### Search Engines (3 implementations)
1. **🏆 HybridDBSFColBERTSearchEngine (RECOMMENDED)** - DBSF fusion + ColBERT reranking ⭐
   - 3-stage pipeline: Dense+Sparse → DBSF → ColBERT
   - Based on [Qdrant 2025 best practices](https://qdrant.tech/articles/hybrid-search/)
   - Status: ✅ **Tested and production-ready** (94.0% Recall@1, +2.9% vs baseline)
2. **BaselineSearchEngine** - Dense vectors only (simple, fast, 91.3% Recall@1)
3. **HybridSearchEngine** - Dense + Sparse with RRF fusion (88.7% Recall@1)

### Research & Planning
Located in `docs/` folder (7 files, 116KB):
- `FINAL_REPORT_CONTEXTUAL_RAG.md` - Evaluation results
- `IMPLEMENTATION_COMPLETE_SUMMARY.md` - Implementation summary
- `NEXT_GEN_RAG_IMPLEMENTATION_PLAN.md` - Original plan
- `FINAL_OPTIMIZATION_REPORT.md` - Baseline optimization
- And more...

---

## 🖥️ VPS Services

```yaml
Qdrant v1.15.5:     localhost:6333  (API key in .env)
BGE-M3 API:         localhost:8001  (BAAI/bge-m3)
Docling API:        localhost:5001  (OCR, tables)

# ML Platform (новые)
MLflow v3.5.1:      localhost:5000  (experiment tracking)
Langfuse v2.95.9:   localhost:3001  (LLM observability)
```

**Start ML services:**
```bash
docker compose --profile ml up -d mlflow langfuse
```

### BGE-M3 API Configuration (Important!)

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
# Model loads from volume, no internet download needed
```

**To verify model location:**
```bash
docker run --rm -v ai-bge-m3-models:/models alpine ls -lh /models/huggingface/hub/
```

---

**Коллекции в Qdrant (7):**
1. `uk_civil_code_v2` ← **BEST (baseline)**
2. `uk_civil_code_contextual_kg`
3. `tsivilnij_kodeks_ukraini_yurinkom_inter_contextual_kg`
4-7. Criminal code variants

---

## 🚀 Quick Start

### 1. Setup

```bash
cd /srv/contextual_rag
cp .env.example .env
nano .env  # Добавить API keys
```

**Минимальные переменные:**
```bash
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=your_key
BGE_M3_URL=http://localhost:8001
DOCLING_URL=http://localhost:5001

# Один из API провайдеров:
ANTHROPIC_API_KEY=sk-ant-...  # или
OPENAI_API_KEY=sk-proj-...    # или
GROQ_API_KEY=gsk_...           # или
ZAI_API_KEY=...                # ✅ Рекомендуется ($3/mo)
```

### 2. Install

```bash
pip install pymupdf anthropic openai groq python-dotenv numpy aiohttp requests pandas FlagEmbedding
```

### 3. Test (5 chunks)

```bash
python ingestion_contextual_kg_fast.py --test
# ~15-30 сек, $0.01
```

### 4. Full run (132 chunks)

```bash
python ingestion_contextual_kg_fast.py
# Z.AI: 3-5 мин, $0 (в рамках плана)
# Groq: 2-4 мин, free (с лимитами)
# OpenAI: 5-8 мин, ~$5-10
# Claude: 8-12 мин, ~$10-15
```

---

## 🔬 Evaluation

### A/B Testing with MLflow (automatic logging)

```bash
cd evaluation
python run_ab_test.py
# Automatically logs to MLflow: 5 params + 25 metrics
# Reports → evaluation/reports/
```

**Метрики:** Recall@K, NDCG@K, MRR, Precision@K, Failure Rate@K

### View Results

```bash
# MLflow UI (experiment tracking)
open http://localhost:5000

# Langfuse UI (query tracing)
open http://localhost:3001
```

### RAGAS E2E Evaluation (4 metrics)

```bash
# Evaluate with RAGAS (faithfulness, context relevancy, etc.)
python evaluate_with_ragas.py --engine dbsf_colbert --sample 10 --use-mlflow

# RAGAS metrics:
# - Faithfulness: LLM answers without hallucinations
# - Context Relevancy: Retrieved documents are relevant
# - Answer Relevancy: Answer addresses the question
# - Context Recall: Ground truth in retrieved context
```

### Quick Test (5 queries)

```bash
# Test MLflow integration
python test_mlflow_ab.py
# Runs in ~30 seconds, logs to MLflow
```

---

## 🧪 API Провайдеры

### Сравнение (132 chunks)

| Provider | Time | Cost | Quality | Success |
|----------|------|------|---------|---------|
| Z.AI async | 3-5 min | $3/mo | Good | 100% |
| Groq async | 2-4 min | Free* | Good | 90% |
| OpenAI async | 5-8 min | ~$8 | Very Good | 99% |
| Claude | 8-12 min | ~$12 | Excellent | 99% |

*Rate limits на free tier

### Использование

```python
# Z.AI (рекомендуется)
from contextualize_zai_async import ContextualRetrievalZAIAsync
retriever = ContextualRetrievalZAIAsync()
context = await retriever.generate_context_async(chunk_text)

# OpenAI
from contextualize_openai_async import ContextualRetrievalOpenAIAsync
retriever = ContextualRetrievalOpenAIAsync(model="gpt-4o-mini")

# Groq
from contextualize_groq_async import ContextualRetrievalGroqAsync
retriever = ContextualRetrievalGroqAsync(model="llama-3.3-70b-versatile")

# Claude
from contextualize import ContextualRetrievalClaude
retriever = ContextualRetrievalClaude(use_prompt_caching=True)
```

---

## 🏗️ Архитектура

### Адаптивный chunker

```python
complexity = detect_pdf_complexity(pdf_path)  # <500ms
chunks = docling_chunk(pdf_path) if complexity["use_docling"] else pymupdf_chunk(pdf_path)
```

### Fallback система

```python
try:
    context = await llm_api.generate_context(chunk)
except APIError:
    context = parse_legal_structure(chunk)  # Regex fallback
```

### Qdrant payload

```python
{
    "text": chunk_text,
    "contextual_prefix": "Документ: ..., Стаття 13...",
    "book_number": 1, "section_number": 1, "chapter_number": 2,
    "article_number": 13, "article_title": "...",
    "prev_article": 12, "next_article": 14,
    "related_articles": [12, 14, 25]
}
```

---

## 📊 Performance

### ingestion_contextual_kg_fast.py (async)

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

### ingestion_contextual_kg.py (sync)

```
Same PDF
TOTAL: 18-20 min (sequential)
Используйте fast версию
```

---

## 🔍 Troubleshooting

```bash
# Qdrant
docker compose ps | grep qdrant
curl http://localhost:6333/collections -H "api-key: $QDRANT_API_KEY"

# BGE-M3 API - Basic Health Check
docker compose ps bge-m3-api
curl http://localhost:8001/health
# Expected: {"status":"ok","model_loaded":true}

# BGE-M3 API - Verify Model in Volume
docker run --rm -v ai-bge-m3-models:/models alpine du -sh /models/huggingface
# Expected: ~7.7GB

# BGE-M3 API - Test Embedding
curl -X POST http://localhost:8001/encode/dense \
  -H "Content-Type: application/json" \
  -d '{"texts":["test"],"batch_size":1}'
# Expected: JSON with dense_vecs and processing_time

# BGE-M3 API - Check Container Size
docker ps --size --filter "name=ai-bge-m3-api"
# Expected: SIZE ~2MB (NOT 8GB!)

# BGE-M3 API - Restart if needed
docker compose restart bge-m3-api

# Docling
docker ps | grep docling
curl http://localhost:5001/health

# API Keys
cat .env | grep API_KEY
```

**Common Issues:**

1. **BGE-M3 model not found:** Model should be in volume. Check:
   ```bash
   docker run --rm -v ai-bge-m3-models:/models alpine ls -lh /models/huggingface/hub/
   ```
   If empty, model will re-download on first API call (~7.7GB, 5-10 min).

2. **Container size is 8GB:** Model is in writable layer, not volume. Check `HF_HOME=/models/huggingface` in docker-compose.yml.

3. **Rate limits (Z.AI):** Увеличить `ZAI_RATE_LIMIT_DELAY` в config.py или уменьшить `ASYNC_SEMAPHORE_LIMIT`.

---

## 📚 Документация

### Основная документация (в корне проекта)

- **[README.md](README.md)** - Project overview, quick start
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System architecture, components, data flow
- **[SETUP.md](SETUP.md)** - Installation & configuration guide
- **[CODE_QUALITY.md](CODE_QUALITY.md)** - Code quality standards, Ruff configuration

### Code Quality Achievement
- ✅ **499 → 0 issues** (100% improvement)
- Modern Python tooling: Ruff 0.14.1 (10-100x faster than traditional stack)
- PEP 585 compliant type hints
- Consistent formatting across all files
- Pre-commit hooks configured

### Research документы (папка docs/, организованы по категориям)

**Guides** (`docs/guides/`):
- [QUICK_START_DBSF.md](docs/guides/QUICK_START_DBSF.md) - ⭐ DBSF + ColBERT quick start
- [DEDUPLICATION_GUIDE.md](docs/guides/DEDUPLICATION_GUIDE.md) - Дедупликация
- [DOC_LING_RAG_TASKS_2025.md](docs/guides/DOC_LING_RAG_TASKS_2025.md) - Docling интеграция

**Implementation** (`docs/implementation/`):
- [DBSF_COLBERT_IMPLEMENTATION_SUMMARY.md](docs/implementation/DBSF_COLBERT_IMPLEMENTATION_SUMMARY.md) - Полный гайд
- [IMPLEMENTATION_CHECKLIST.md](docs/implementation/IMPLEMENTATION_CHECKLIST.md) - Чеклист

**Reports** (`docs/reports/`):
- [FINAL_REPORT_CONTEXTUAL_RAG.md](docs/reports/FINAL_REPORT_CONTEXTUAL_RAG.md) - Evaluation результаты
- [TEST_RESULTS_SUMMARY.md](docs/reports/TEST_RESULTS_SUMMARY.md) - API сравнение
- [FINAL_OPTIMIZATION_REPORT.md](docs/reports/FINAL_OPTIMIZATION_REPORT.md) - Оптимизация

**Archive** (`docs/archive/`) - исторические документы:
- [NEXT_GEN_RAG_IMPLEMENTATION_PLAN.md](docs/archive/NEXT_GEN_RAG_IMPLEMENTATION_PLAN.md) - Оригинальный план
- [IMPLEMENTATION_COMPLETE_SUMMARY.md](docs/archive/IMPLEMENTATION_COMPLETE_SUMMARY.md) - Итоги

**Полная навигация:** [docs/INDEX.md](docs/INDEX.md)

### External Research

- Anthropic Contextual Retrieval: https://www.anthropic.com/news/contextual-retrieval
- Microsoft GraphRAG: https://github.com/microsoft/graphrag
- Qdrant KG: https://qdrant.tech/articles/knowledge-graphs-rag/
- Qdrant Hybrid Search: https://qdrant.tech/articles/hybrid-search/

---

## 💰 Cost (1000 docs)

- **Z.AI:** $3/месяц (fixed)
- **OpenAI:** ~$50
- **Claude:** ~$100

---

## 🎓 Lessons Learned

### ✅ Сработало
- Async обработка: 4.7x speedup
- Fallback система: 100% надежность
- Адаптивный chunker
- Множественные API провайдеры

### ❌ Не сработало
- Contextual retrieval: baseline лучше
- Document context удален для экономии → качество упало
- KG метаданные не дали преимущества

### 💡 Вывод
Anthropic contextual retrieval работает **только с полным document context** в каждом запросе. Оптимизация стоимости убила эффективность.

---

## 🚀 Next Steps

### Production (рекомендуется)
1. Reranking (ColBERTv2, bge-reranker)
2. Hybrid Search (BM25 + dense)
3. Query expansion
4. KG metadata для filtering

### Experiments
1. Вернуть full document context (принять высокую стоимость)
2. Aggressive prompt caching (Anthropic)
3. Больше тестовых запросов (>10)

---

## 📊 ML Platform Stack

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
