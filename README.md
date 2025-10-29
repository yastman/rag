# 🚀 Contextual RAG Pipeline v2.0.1

> **Production-ready document search for Ukrainian legal documents**

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Code Quality](https://img.shields.io/badge/Code%20Quality-Ruff-purple)](https://github.com/astral-sh/ruff)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-brightgreen)](#)

## 📋 What is this?

**Contextual RAG Pipeline** is an information retrieval system for Ukrainian legal documents featuring:

- 🔍 **Hybrid Search**: Dense (BGE-M3) + Sparse (ColBERT) vectors
- 🎯 **DBSF Ranking**: 94.0% Recall@1 (best accuracy)
- 🤖 **Multiple LLMs**: Claude, OpenAI, Groq
- 💰 **90% Cost Savings**: Prompt caching for Claude API
- 📊 **ML Platforms**: MLflow + Langfuse
- ✅ **Production Ready**: 0 code errors, full tests

---

## 📁 Project Structure

```
contextual_rag/
├── src/                          # All application code
│   ├── config/                   # Configuration
│   ├── contextualization/        # LLM contextualization
│   ├── retrieval/                # Search engines
│   ├── ingestion/                # Document loading
│   ├── evaluation/               # Evaluation and metrics
│   ├── utils/                    # Utilities
│   └── core/                     # Main pipeline
│
├── docs/                         # Documentation
│   ├── guides/                   # User guides
│   ├── architecture/             # System architecture
│   ├── implementation/           # Implementation details
│   ├── reports/                  # Project reports
│   └── documents/                # Legal documents
│
├── tests/                        # Tests
│   ├── unit/                     # Unit tests
│   ├── integration/              # Integration tests
│   └── legacy/                   # Legacy tests
│
├── data/                         # Data
│   ├── documents/                # Input documents
│   ├── test_queries/             # Test queries
│   └── evaluation/               # Evaluation results
│
├── legacy/                       # Old code (deprecated)
├── logs/                         # Logs
├── pyproject.toml                # Project configuration
├── .env.example                  # Environment variables example
└── docker-compose.yml            # Docker services
```

---

## ⚡ Quick Start (5 minutes)

### 1. Installation

**Option A: Claude Code CLI on Server (🏆 RECOMMENDED)**

```bash
# 1. SSH to server
ssh user@your-server.com

# 2. Clone project
git clone https://github.com/yastman/rag.git
cd rag

# 3. Setup environment
python3.9 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# 4. Configure Git
git config user.name "Your Name"
git config user.email "your@email.com"

# 5. Setup pre-commit
pre-commit install --install-hooks
pre-commit install --hook-type pre-push

# 6. Configure .env
cp .env.example .env
nano .env  # Add your API keys

# 7. Launch Claude Code
claude

# Done! Now just talk to Claude:
# "show project structure"
# "run tests"
# "create a new function for..."
```

**Option B: Local Development (without Claude Code)**

```bash
# Locally
git clone https://github.com/yastman/rag.git
cd rag

# Virtual environment
python3.9 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Dependencies
pip install -e ".[dev]"

# Git hooks
pre-commit install --install-hooks
pre-commit install --hook-type pre-push

# Configuration
cp .env.example .env
# Edit .env with your API keys
```

### 2. Start Qdrant

```bash
docker compose up -d qdrant
```

### 3. Index Documents

```python
from src.core import RAGPipeline

pipeline = RAGPipeline()

# Index PDF
await pipeline.index_documents(
    pdf_paths=["docs/documents/Constitution_Ukraine.pdf"],
    collection_name="legal_documents"
)
```

### 4. Search

```python
# Search
result = await pipeline.search("What rights do citizens have?")

for r in result.results:
    print(f"{r['article_number']}: {r['text'][:100]}...")
    print(f"Score: {r['score']:.3f}\n")
```

---

## 📚 System Modules

### 🔧 Config (`src/config/`)

Centralized configuration with validation:

```python
from src.config import Settings, APIProvider, SearchEngine

settings = Settings(
    api_provider=APIProvider.CLAUDE,
    search_engine=SearchEngine.DBSF_COLBERT,
)
```

### 🤖 Contextualization (`src/contextualization/`)

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

### 🔍 Retrieval (`src/retrieval/`)

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

### 📥 Ingestion (`src/ingestion/`)

Document loading pipeline:

```python
from src.ingestion import PDFParser, DocumentChunker, DocumentIndexer

# 1. Parse PDF
parser = PDFParser()
doc = parser.parse_file("document.pdf")

# 2. Split into chunks
chunker = DocumentChunker(chunk_size=512, overlap=128)
chunks = chunker.chunk_text(doc.content, doc.filename, "article_1")

# 3. Index in Qdrant
indexer = DocumentIndexer()
stats = await indexer.index_chunks(chunks, "legal_documents")
```

### 📊 Evaluation (`src/evaluation/`)

Quality assessment and experiments:

- **Metrics**: Recall@K, NDCG@K, MRR
- **MLflow**: http://localhost:5000 (experiment tracking)
- **Langfuse**: http://localhost:3001 (LLM tracing)
- **RAGAS**: RAG evaluation framework

### 🎯 Core (`src/core/`)

Main RAG pipeline:

```python
from src.core import RAGPipeline

pipeline = RAGPipeline()

# Search
result = await pipeline.search("query", top_k=5)

# Evaluate
metrics = await pipeline.evaluate(test_queries, ground_truth)

# Statistics
stats = pipeline.get_stats()
```

---

## ⚙️ Configuration

Settings via `.env`:

```env
# LLM API
API_PROVIDER=claude              # claude, openai, groq
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GROQ_API_KEY=gsk_...

# Vector Database
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=

# Search
SEARCH_ENGINE=dbsf_colbert       # baseline, hybrid_rrf, dbsf_colbert
COLLECTION_NAME=legal_documents
TOP_K=10

# Features
ENABLE_CACHING=true
ENABLE_QUERY_EXPANSION=true
ENABLE_MLFLOW=true
ENABLE_LANGFUSE=true

# Environment
ENV=development                  # development, production
DEBUG=false
```

---

## 📊 Performance

### Search Quality (150 test queries)

```
BASELINE:       Recall@1=91.3%, NDCG@10=0.9619, Latency=0.65s
HYBRID RRF:     Recall@1=88.7%, NDCG@10=0.9524, Latency=0.72s
DBSF+ColBERT:   Recall@1=94.0%, NDCG@10=0.9711, Latency=0.69s ⭐
```

### Indexing Speed

- **Parsing**: 132 chunks in 2-3 minutes
- **Contextualization**: $0-3 (depending on API)
- **Indexing**: 6 minutes full pipeline

---

## 🧪 Testing

```bash
# Unit tests
pytest tests/unit/

# Integration tests
pytest tests/integration/

# Smoke test
python src/evaluation/smoke_test.py

# A/B testing
python src/evaluation/run_ab_test.py
```

---

## 📖 Documentation

| Document | Purpose |
|-----------|-------------|
| [QUICK_START.md](docs/guides/QUICK_START.md) | 5-minute quick start |
| [ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) | System architecture |
| [CODE_QUALITY.md](docs/guides/CODE_QUALITY.md) | Development standards |
| [README_NEW_STRUCTURE.md](docs/README_NEW_STRUCTURE.md) | Detailed structure description |

---

## 🛠️ Development

### Working on Server

**🏆 Option 1: Claude Code CLI on Server (EASIEST!)**

```bash
# 1. Connect to server
ssh user@your-server.com

# 2. Install Claude Code (if not installed)
# curl -fsSL https://claude.ai/install.sh | sh

# 3. Go to project
cd /path/to/rag

# 4. Launch Claude Code
claude

# Done! 🎉
# Claude Code automatically:
# - Sees all project files
# - Has Git access
# - Can run commands
# - Edits files
# - Makes commits with pre-commit hooks
# - Pushes to GitHub
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
# VS Code with "Remote - SSH" extension
# 1. F1 → "Remote-SSH: Connect to Host"
# 2. user@your-server.com
# 3. Open folder /path/to/rag
```

**Option 3: Plain SSH**

```bash
ssh user@your-server.com
cd /path/to/rag
nano src/file.py  # or vim, emacs
```

**Recommended workflow with Claude Code:**
```bash
# On server
cd /path/to/rag
claude

# Then just tell Claude what to do:
"Add caching function for search results"
"Fix error in src/retrieval/search_engines.py"
"Create tests for new module"
"Make a commit with these changes"
"Push to GitHub"

# Claude will do everything automatically! 🎉
```

### Code Quality

```bash
# Linting
ruff check src/

# Formatting
ruff format src/

# Type checking
mypy src/ --ignore-missing-imports

# Pre-commit hooks (one-time setup)
pip install pre-commit
pre-commit install --install-hooks
pre-commit install --hook-type pre-push

# Run manually
pre-commit run --all-files
```

### Git Workflow (Automated)

**Pre-commit hooks run automatically:**

```bash
# 1. Create feature branch
git checkout -b feature/amazing-feature

# 2. Make changes
# ... edit code ...

# 3. Commit (automatic: linting, formatting, checks)
git add .
git commit -m "feat: Add amazing feature"
# → Ruff checks and formats code
# → If errors - commit stops

# 4. Push (automatic: branch protection warning)
git push origin feature/amazing-feature
# → Warning if pushing to main/master
```

**Commit Structure (Conventional Commits):**

```bash
# Feature
git commit -m "feat: Add query expansion feature"

# Bug fix
git commit -m "fix: Fix Qdrant connection timeout"

# Documentation
git commit -m "docs: Update README with new structure"

# Refactoring
git commit -m "refactor: Optimize search engine performance"

# Tests
git commit -m "test: Add unit tests for retrieval module"
```

**What happens automatically:**
- ✅ **Before commit**: Ruff checks and formats code
- ✅ **Before push**: Warning about push to main/master
- ✅ **On errors**: Commit stops, need to fix
- ✅ **Auto-fix**: Most errors are fixed automatically

---

## 🐛 Troubleshooting

##***REMOVED*** not available

```bash
docker compose up -d qdrant
curl http://localhost:6333/health
```

### API key not working

```bash
python -c "from src.config import Settings; Settings()"
# Check .env file
```

### Slow search

- Use DBSF+ColBERT instead of Baseline
- Check that Qdrant is running
- Increase HNSW ef parameter in config

---

## 🤝 Contributing

1. Fork the project
2. Create feature branch: `git checkout -b feature/amazing`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing`
5. Create Pull Request

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/yastman/rag/issues)
- **Documentation**: `/docs` folder
- **Status**: ✅ Production Ready

---

## 📜 License

MIT License - see [LICENSE](LICENSE)

---

## 🎯 Roadmap

### ✅ Completed (v2.0.1)
- [x] Hybrid DBSF+ColBERT search
- [x] MLflow + Langfuse integration
- [x] Prompt caching (90% savings)
- [x] Modular architecture
- [x] Complete documentation

### 🚀 Planned (v2.1.0)
- [ ] Query expansion via LLM
- [ ] Semantic caching (Redis)
- [ ] Graph traversal for related articles
- [ ] Multi-language support (BGE-M3 supports 111 languages)
- [ ] Web UI dashboard

---

**Last Updated**: October 29, 2024
**Version**: 2.0.1
**Repository**: https://github.com/yastman/rag
**Maintainer**: Contextual RAG Team

**⭐ If this project is useful - give it a star!**
