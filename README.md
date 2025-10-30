***REMOVED*** 🚀 Contextual RAG Pipeline v2.0.1

> **Production-ready document search for Ukrainian legal documents**

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Code Quality](https://img.shields.io/badge/Code%20Quality-Ruff-purple)](https://github.com/astral-sh/ruff)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-brightgreen)](***REMOVED***)

***REMOVED******REMOVED*** 📋 What is this?

**Contextual RAG Pipeline** is an information retrieval system for Ukrainian legal documents featuring:

- 🔍 **Hybrid Search**: Dense (BGE-M3) + Sparse (ColBERT) vectors
- 🎯 **DBSF Ranking**: 94.0% Recall@1 (best accuracy)
- 🤖 **Multiple LLMs**: Claude, OpenAI, Groq
- 💰 **90% Cost Savings**: Prompt caching for Claude API
- 📊 **ML Platforms**: MLflow + Langfuse
- ✅ **Production Ready**: 0 code errors, full tests

---

***REMOVED******REMOVED*** 📁 Project Structure

```
contextual_rag/
├── src/                          ***REMOVED*** Application code
│   ├── config/                   ***REMOVED*** Configuration
│   ├── contextualization/        ***REMOVED*** LLM contextualization
│   ├── retrieval/                ***REMOVED*** Search engines
│   ├── ingestion/                ***REMOVED*** Document loading
│   ├── evaluation/               ***REMOVED*** 📊 Evaluation + ML platforms
│   │   ├── mlflow_integration.py     ***REMOVED*** MLflow wrapper
│   │   ├── mlflow_experiments.py     ***REMOVED*** A/B testing
│   │   ├── create_golden_set.py      ***REMOVED*** Test set generator (150 queries)
│   │   └── ragas_evaluation.py       ***REMOVED*** RAGAS quality metrics
│   ├── observability/            ***REMOVED*** 📈 OpenTelemetry (NEW)
│   │   └── otel_setup.py             ***REMOVED*** OTEL traces → Tempo/Prometheus
│   ├── cache/                    ***REMOVED*** 🚀 Redis semantic cache (NEW)
│   │   └── redis_semantic_cache.py   ***REMOVED*** Versioned cache (embeddings + responses)
│   ├── governance/               ***REMOVED*** 🏛️ Model Registry (NEW)
│   │   └── model_registry.py         ***REMOVED*** MLflow Registry (Staging→Production)
│   ├── security/                 ***REMOVED*** 🔒 PII redaction + budget (NEW)
│   │   └── pii_redaction.py          ***REMOVED*** Ukrainian PII + cost limits
│   ├── utils/                    ***REMOVED*** Utilities
│   └── core/                     ***REMOVED*** Main pipeline
│
├── scripts/                      ***REMOVED*** 🛠️ Automation scripts (NEW)
│   ├── qdrant_backup.sh              ***REMOVED*** Nightly Qdrant backups (7-day rotation)
│   └── qdrant_restore.sh             ***REMOVED*** Disaster recovery (RTO < 1 hour)
│
├── docs/                         ***REMOVED*** Documentation
│   ├── guides/                   ***REMOVED*** User guides
│   ├── architecture/             ***REMOVED*** System architecture
│   ├── implementation/           ***REMOVED*** Implementation details
│   ├── reports/                  ***REMOVED*** Project reports
│   ├── ML_PLATFORM_INTEGRATION_PLAN.md  ***REMOVED*** Full ML platform plan
│   └── documents/                ***REMOVED*** Legal documents
│
├── tests/                        ***REMOVED*** Tests
│   ├── unit/                     ***REMOVED*** Unit tests
│   ├── integration/              ***REMOVED*** Integration tests
│   ├── data/                     ***REMOVED*** Test data
│   │   └── golden_test_set.json      ***REMOVED*** 150 queries for RAGAS
│   └── legacy/                   ***REMOVED*** Legacy tests
│
├── data/                         ***REMOVED*** Data
│   ├── documents/                ***REMOVED*** Input documents
│   ├── test_queries/             ***REMOVED*** Test queries
│   └── evaluation/               ***REMOVED*** Evaluation results
│
├── legacy/                       ***REMOVED*** Old code (for reference)
├── logs/                         ***REMOVED*** Logs
├── pyproject.toml                ***REMOVED*** Project configuration
├── .env.example                  ***REMOVED*** Environment variables example
└── docker-compose.yml            ***REMOVED*** Docker services (Qdrant, Redis, etc.)
```

**📖 Each folder has its own README.md with detailed documentation!**

---

***REMOVED******REMOVED*** ⚡ Quick Start (5 minutes)

***REMOVED******REMOVED******REMOVED*** 1. Installation

**Option A: Claude Code CLI on Server (🏆 RECOMMENDED)**

```bash
***REMOVED*** 1. SSH to server
ssh user@your-server.com

***REMOVED*** 2. Clone project
git clone https://github.com/yastman/rag.git
cd rag

***REMOVED*** 3. Setup environment
python3.9 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

***REMOVED*** 4. Configure Git
git config user.name "Your Name"
git config user.email "your@email.com"

***REMOVED*** 5. Setup pre-commit
pre-commit install --install-hooks
pre-commit install --hook-type pre-push

***REMOVED*** 6. Configure .env
cp .env.example .env
nano .env  ***REMOVED*** Add your API keys

***REMOVED*** 7. Launch Claude Code
claude

***REMOVED*** Done! Now just talk to Claude:
***REMOVED*** "show project structure"
***REMOVED*** "run tests"
***REMOVED*** "create a new function for..."
```

**Option B: Local Development (without Claude Code)**

```bash
***REMOVED*** Locally
git clone https://github.com/yastman/rag.git
cd rag

***REMOVED*** Virtual environment
python3.9 -m venv venv
source venv/bin/activate  ***REMOVED*** Windows: venv\Scripts\activate

***REMOVED*** Dependencies
pip install -e ".[dev]"

***REMOVED*** Git hooks
pre-commit install --install-hooks
pre-commit install --hook-type pre-push

***REMOVED*** Configuration
cp .env.example .env
***REMOVED*** Edit .env with your API keys
```

***REMOVED******REMOVED******REMOVED*** 2. Start Qdrant

```bash
docker compose up -d qdrant
```

***REMOVED******REMOVED******REMOVED*** 3. Index Documents

```python
from src.core import RAGPipeline

pipeline = RAGPipeline()

***REMOVED*** Index PDF
await pipeline.index_documents(
    pdf_paths=["docs/documents/Constitution_Ukraine.pdf"],
    collection_name="legal_documents"
)
```

***REMOVED******REMOVED******REMOVED*** 4. Search

```python
***REMOVED*** Search
result = await pipeline.search("What rights do citizens have?")

for r in result.results:
    print(f"{r['article_number']}: {r['text'][:100]}...")
    print(f"Score: {r['score']:.3f}\n")
```

---

***REMOVED******REMOVED*** 📚 System Modules

***REMOVED******REMOVED******REMOVED*** 🔧 Config (`src/config/`)

Centralized configuration with validation:

```python
from src.config import Settings, APIProvider, SearchEngine

settings = Settings(
    api_provider=APIProvider.CLAUDE,
    search_engine=SearchEngine.DBSF_COLBERT,
)
```

***REMOVED******REMOVED******REMOVED*** 🤖 Contextualization (`src/contextualization/`)

LLM-powered document enrichment:

```python
from src.contextualization import ClaudeContextualizer

contextualizer = ClaudeContextualizer()
chunks = await contextualizer.contextualize(texts, query)
```

**Providers:**
- ⭐ **Claude** (recommended): highest quality, prompt caching
- **OpenAI**: very good quality
- **Groq**: fastest (2-4 min for 100 chunks)

***REMOVED******REMOVED******REMOVED*** 🔍 Retrieval (`src/retrieval/`)

Three tiers of search engines:

| Engine | Recall@1 | NDCG@10 | Latency |
|--------|----------|---------|---------|
| Baseline | 91.3% | 0.9619 | 0.65s |
| Hybrid RRF | 88.7% | 0.9524 | 0.72s |
| **DBSF+ColBERT** | **94.0%** ⭐ | **0.9711** | **0.69s** |

```python
from src.retrieval import DBSFColBERTSearchEngine

engine = DBSFColBERTSearchEngine()
results = engine.search(query_embedding, top_k=10)
```

***REMOVED******REMOVED******REMOVED*** 📥 Ingestion (`src/ingestion/`)

Document loading pipeline:

```python
from src.ingestion import PDFParser, DocumentChunker, DocumentIndexer

***REMOVED*** 1. Parse PDF
parser = PDFParser()
doc = parser.parse_file("document.pdf")

***REMOVED*** 2. Split into chunks
chunker = DocumentChunker(chunk_size=512, overlap=128)
chunks = chunker.chunk_text(doc.content, doc.filename, "article_1")

***REMOVED*** 3. Index in Qdrant
indexer = DocumentIndexer()
stats = await indexer.index_chunks(chunks, "legal_documents")
```

***REMOVED******REMOVED******REMOVED*** 📊 Evaluation (`src/evaluation/`)

Production ML platform with quality metrics:

```python
***REMOVED*** 1. Create golden test set (150 queries)
python src/evaluation/create_golden_set.py

***REMOVED*** 2. Run RAGAS evaluation
python src/evaluation/ragas_evaluation.py

***REMOVED*** 3. A/B testing
from src.evaluation.mlflow_experiments import RAGExperimentRunner
runner = RAGExperimentRunner("contextual_rag_ab_tests")
await runner.run_ab_test(...)
```

**Components:**
- **Golden Test Set**: 150 queries across 5 categories (lookup, crimes, concepts, procedures, definitions)
- **RAGAS**: Automated quality metrics (faithfulness ≥ 0.85, precision ≥ 0.80, recall ≥ 0.90)
- **MLflow**: http://localhost:5000 (experiments, A/B tests, Model Registry)
- **Langfuse**: http://localhost:3001 (LLM tracing, cost tracking)

***REMOVED******REMOVED******REMOVED*** 📈 Observability (`src/observability/`)

OpenTelemetry integration for system metrics:

```python
from src.observability.otel_setup import setup_opentelemetry
setup_opentelemetry("contextual-rag")

***REMOVED*** Automatic tracking:
***REMOVED*** - Traces → Tempo (http://localhost:4317)
***REMOVED*** - Metrics → Prometheus
***REMOVED*** - Latency by steps: embed/search/rerank
***REMOVED*** - System metrics: CPU, RAM, I/O
```

***REMOVED******REMOVED******REMOVED*** 🚀 Cache (`src/cache/`)

Redis semantic cache with versioning:

```python
from src.cache.redis_semantic_cache import RedisSemanticCache

cache = RedisSemanticCache(index_version="1.0.0")

***REMOVED*** Embedding cache (TTL: 30 days)
embedding = await cache.get_embedding(query)

***REMOVED*** Response cache (TTL: 5-60 min)
response = await cache.get_response(query, top_k=10)

***REMOVED*** Statistics
stats = cache.get_stats()  ***REMOVED*** hit_rate, saved_cost_usd
```

**Key features:**
- **Version-aware keys**: `embedding_v1.0.0_{hash}` (invalidates on reindex)
- **Two-layer caching**: Embeddings (30d) + Full responses (5-60min)
- **Cost tracking**: `saved_cost_usd` metric
- **OTEL integration**: Traces cache hits/misses

***REMOVED******REMOVED******REMOVED*** 🏛️ Governance (`src/governance/`)

MLflow Model Registry for production workflow:

```python
from src.governance.model_registry import RAGModelRegistry

registry = RAGModelRegistry()

***REMOVED*** Register new config after evaluation
version = registry.register_config(
    run_id="abc123",
    config_version="1.2.0",
    metrics={"faithfulness": 0.87, ...}
)

***REMOVED*** Promote to staging
registry.promote_to_staging(version)

***REMOVED*** Promote to production
registry.promote_to_production(version)

***REMOVED*** Rollback if needed
registry.rollback_production(to_version="5")
```

***REMOVED******REMOVED******REMOVED*** 🔒 Security (`src/security/`)

PII redaction and budget guards:

```python
from src.security.pii_redaction import PIIRedactor, BudgetGuard

***REMOVED*** Redact Ukrainian PII
redactor = PIIRedactor()
redacted_query, metadata = redactor.redact_query(query)
***REMOVED*** Replaces: phones, emails, tax IDs, passports

***REMOVED*** Budget limits
guard = BudgetGuard()  ***REMOVED*** Daily: $10, Monthly: $300
allowed, warning = guard.check_budget(estimated_cost)
```

***REMOVED******REMOVED******REMOVED*** 🛠️ Scripts (`scripts/`)

Automation for disaster recovery:

```bash
***REMOVED*** Nightly Qdrant backup (run via cron)
./scripts/qdrant_backup.sh

***REMOVED*** Restore from backup
./scripts/qdrant_restore.sh /path/to/backup.snapshot

***REMOVED*** Setup cron job for nightly backups
crontab -e
***REMOVED*** Add: 0 3 * * * /srv/app/scripts/qdrant_backup.sh
```

**Features:**
- **7-day rotation**: Keeps last 7 backups
- **RTO < 1 hour**: Fast recovery from disasters
- **Automatic cleanup**: Removes old backups

***REMOVED******REMOVED******REMOVED*** 🎯 Core (`src/core/`)

Main RAG pipeline:

```python
from src.core import RAGPipeline

pipeline = RAGPipeline()

***REMOVED*** Search
result = await pipeline.search("query", top_k=5)

***REMOVED*** Evaluate
metrics = await pipeline.evaluate(test_queries, ground_truth)

***REMOVED*** Statistics
stats = pipeline.get_stats()
```

---

***REMOVED******REMOVED*** ⚙️ Configuration

Settings via `.env`:

```env
***REMOVED*** LLM API
API_PROVIDER=claude              ***REMOVED*** claude, openai, groq
ANTHROPIC_API_KEY=[REDACTED-ANTHROPIC-KEY]
OPENAI_API_KEY=[REDACTED-OPENAI-KEY]
GROQ_API_KEY=[REDACTED-GROQ-KEY]

***REMOVED*** Vector Database
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=

***REMOVED*** Search
SEARCH_ENGINE=dbsf_colbert       ***REMOVED*** baseline, hybrid_rrf, dbsf_colbert
COLLECTION_NAME=legal_documents
TOP_K=10

***REMOVED*** Features
ENABLE_CACHING=true
ENABLE_QUERY_EXPANSION=true
ENABLE_MLFLOW=true
ENABLE_LANGFUSE=true

***REMOVED*** Environment
ENV=development                  ***REMOVED*** development, production
DEBUG=false
```

---

***REMOVED******REMOVED*** 📊 Performance

***REMOVED******REMOVED******REMOVED*** Search Quality (150 test queries)

```
BASELINE:       Recall@1=91.3%, NDCG@10=0.9619, Latency=0.65s
HYBRID RRF:     Recall@1=88.7%, NDCG@10=0.9524, Latency=0.72s
DBSF+ColBERT:   Recall@1=94.0%, NDCG@10=0.9711, Latency=0.69s ⭐
```

***REMOVED******REMOVED******REMOVED*** Indexing Speed

- **Parsing**: 132 chunks in 2-3 minutes
- **Contextualization**: $0-3 (depending on API)
- **Indexing**: 6 minutes full pipeline

---

***REMOVED******REMOVED*** 🧪 Testing

```bash
***REMOVED*** Unit tests
pytest tests/unit/

***REMOVED*** Integration tests
pytest tests/integration/

***REMOVED*** Smoke test
python src/evaluation/smoke_test.py

***REMOVED*** A/B testing
python src/evaluation/run_ab_test.py
```

---

***REMOVED******REMOVED*** 📖 Documentation

| Document | Purpose |
|-----------|-------------|
| [QUICK_START.md](docs/guides/QUICK_START.md) | 5-minute quick start |
| [ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) | System architecture |
| [CODE_QUALITY.md](docs/guides/CODE_QUALITY.md) | Development standards |
| [README_NEW_STRUCTURE.md](docs/README_NEW_STRUCTURE.md) | Detailed structure description |

---

***REMOVED******REMOVED*** 🛠️ Development

***REMOVED******REMOVED******REMOVED*** Working on Server

**🏆 Option 1: Claude Code CLI on Server (EASIEST!)**

```bash
***REMOVED*** 1. Connect to server
ssh user@your-server.com

***REMOVED*** 2. Install Claude Code (if not installed)
***REMOVED*** curl -fsSL https://claude.ai/install.sh | sh

***REMOVED*** 3. Go to project
cd /path/to/rag

***REMOVED*** 4. Launch Claude Code
claude

***REMOVED*** Done! 🎉
***REMOVED*** Claude Code automatically:
***REMOVED*** - Sees all project files
***REMOVED*** - Has Git access
***REMOVED*** - Can run commands
***REMOVED*** - Edits files
***REMOVED*** - Makes commits with pre-commit hooks
***REMOVED*** - Pushes to GitHub
```

**Claude Code CLI Benefits:**
- ⚡ **Fastest way** - one command `claude`
- 🤖 **AI assistant** - helps with code, docs, debugging
- 🔧 **Everything integrated** - Git, linting, testing, all tools
- 📝 **Automatic commits** - with proper messages
- 🎯 **Understands context** - sees entire project
- 🚀 **No setup needed** - works out of the box

**Option 2: VS Code Remote SSH**

```bash
***REMOVED*** VS Code with "Remote - SSH" extension
***REMOVED*** 1. F1 → "Remote-SSH: Connect to Host"
***REMOVED*** 2. user@your-server.com
***REMOVED*** 3. Open folder /path/to/rag
```

**Option 3: Plain SSH**

```bash
ssh user@your-server.com
cd /path/to/rag
nano src/file.py  ***REMOVED*** or vim, emacs
```

**Recommended workflow with Claude Code:**
```bash
***REMOVED*** On server
cd /path/to/rag
claude

***REMOVED*** Then just tell Claude what to do:
"Add caching function for search results"
"Fix error in src/retrieval/search_engines.py"
"Create tests for new module"
"Make a commit with these changes"
"Push to GitHub"

***REMOVED*** Claude will do everything automatically! 🎉
```

***REMOVED******REMOVED******REMOVED*** Code Quality

```bash
***REMOVED*** Linting
ruff check src/

***REMOVED*** Formatting
ruff format src/

***REMOVED*** Type checking
mypy src/ --ignore-missing-imports

***REMOVED*** Pre-commit hooks (one-time setup)
pip install pre-commit
pre-commit install --install-hooks
pre-commit install --hook-type pre-push

***REMOVED*** Run manually
pre-commit run --all-files
```

***REMOVED******REMOVED******REMOVED*** Git Workflow (Automated)

**Pre-commit hooks run automatically:**

```bash
***REMOVED*** 1. Create feature branch
git checkout -b feature/amazing-feature

***REMOVED*** 2. Make changes
***REMOVED*** ... edit code ...

***REMOVED*** 3. Commit (automatic: linting, formatting, checks)
git add .
git commit -m "feat: Add amazing feature"
***REMOVED*** → Ruff checks and formats code
***REMOVED*** → If errors - commit stops

***REMOVED*** 4. Push (automatic: branch protection warning)
git push origin feature/amazing-feature
***REMOVED*** → Warning if pushing to main/master
```

**Commit Structure (Conventional Commits):**

```bash
***REMOVED*** Feature
git commit -m "feat: Add query expansion feature"

***REMOVED*** Bug fix
git commit -m "fix: Fix Qdrant connection timeout"

***REMOVED*** Documentation
git commit -m "docs: Update README with new structure"

***REMOVED*** Refactoring
git commit -m "refactor: Optimize search engine performance"

***REMOVED*** Tests
git commit -m "test: Add unit tests for retrieval module"
```

**What happens automatically:**
- ✅ **Before commit**: Ruff checks and formats code
- ✅ **Before push**: Warning about push to main/master
- ✅ **On errors**: Commit stops, need to fix
- ✅ **Auto-fix**: Most errors are fixed automatically

---

***REMOVED******REMOVED*** 🐛 Troubleshooting

***REMOVED******REMOVED******REMOVED*** Qdrant not available

```bash
docker compose up -d qdrant
curl http://localhost:6333/health
```

***REMOVED******REMOVED******REMOVED*** API key not working

```bash
python -c "from src.config import Settings; Settings()"
***REMOVED*** Check .env file
```

***REMOVED******REMOVED******REMOVED*** Slow search

- Use DBSF+ColBERT instead of Baseline
- Check that Qdrant is running
- Increase HNSW ef parameter in config

---

***REMOVED******REMOVED*** 🤝 Contributing

1. Fork the project
2. Create feature branch: `git checkout -b feature/amazing`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing`
5. Create Pull Request

---

***REMOVED******REMOVED*** 📞 Support

- **Issues**: [GitHub Issues](https://github.com/yastman/rag/issues)
- **Documentation**: `/docs` folder
- **Status**: ✅ Production Ready

---

***REMOVED******REMOVED*** 📜 License

MIT License - see [LICENSE](LICENSE)

---

***REMOVED******REMOVED*** 🎯 Roadmap

***REMOVED******REMOVED******REMOVED*** ✅ Completed (v2.0.1)
- [x] Hybrid DBSF+ColBERT search (94% Recall@1)
- [x] MLflow + Langfuse integration
- [x] Prompt caching (90% cost savings)
- [x] Modular architecture
- [x] Complete documentation

***REMOVED******REMOVED******REMOVED*** ✅ Completed (v2.1.0) - Production ML Platform
- [x] **RAGAS quality metrics** (faithfulness, precision, recall)
- [x] **Golden test set** (150 queries with ground truth)
- [x] **OpenTelemetry** (traces → Tempo, metrics → Prometheus)
- [x] **Redis semantic cache** (2-layer with versioning)
- [x] **MLflow Model Registry** (Staging → Production workflow)
- [x] **Qdrant backups** (7-day rotation, RTO < 1 hour)
- [x] **PII redaction** (Ukrainian patterns)
- [x] **Budget guards** ($10/day, $300/month limits)
- [x] **A/B testing framework**
- [x] **Nightly RAGAS evaluation** (cron jobs)

***REMOVED******REMOVED******REMOVED*** 🚀 Planned (v2.2.0)
- [ ] Query expansion via LLM
- [ ] Graph traversal for related articles
- [ ] Multi-language support (BGE-M3 → 111 languages)
- [ ] Web UI dashboard (Streamlit/Gradio)
- [ ] Real-time streaming responses

---

**Last Updated**: October 30, 2025
**Version**: 2.1.0
**Repository**: https://github.com/yastman/rag
**Maintainer**: Contextual RAG Team

**⭐ If this project is useful - give it a star!**
