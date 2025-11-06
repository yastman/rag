# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### 🔒 Security
- [ ] Rotate exposed Qdrant API keys (CRITICAL - #1.1)
- [ ] Add `.env` to `.gitignore` and remove secrets from git history

### ⚡ Performance
- [ ] Replace `requests` with `httpx.AsyncClient` in search engines (#1.2)
- [ ] Fix blocking calls in `pipeline.py` async methods (#1.4)
- [ ] Implement singleton pattern for BGE-M3 embedding model (#2.1)
- [ ] Add connection pooling for Qdrant and Redis (#3.1)

### 🐛 Bug Fixes
- [ ] Fix race condition in semantic cache (#2.2)
- [ ] Fix duplicate embedding model loading (4-6GB → 2GB RAM)

### ✨ Features
- [ ] Add rate limiting middleware for Telegram bot (#2.3)
- [ ] Implement distributed lock for semantic cache
- [ ] Add Prometheus metrics endpoint (#4.1)

### 📦 Dependencies
- [ ] Add missing dependencies to `requirements.txt` (#1.3):
  - FlagEmbedding>=1.2.0
  - sentence-transformers>=2.2.0
  - anthropic>=0.18.0
  - openai>=1.10.0
  - groq>=0.4.0

### 🔧 Infrastructure
- [ ] Create `docker-compose.yml` for all services (#3.2)
- [ ] Setup CI/CD pipeline with GitHub Actions (#3.3)
- [ ] Migrate to `AsyncQdrantClient` (#3.4)

### 📝 Documentation
- [ ] Add comprehensive ROADMAP.md
- [ ] Create CHANGELOG.md (this file)
- [ ] Add TODO.md for daily task tracking
- [ ] Update README.md (remove exposed secrets)

---

## [2.5.0] - 2025-11-05

### ✨ Added
- **Semantic Cache Architecture** - 4-tier caching with Redis Vector Search
  - Tier 1: Semantic cache with KNN (COSINE similarity, threshold 0.85)
  - Tier 1: Embeddings cache (30 days TTL, 1000x speedup)
  - Tier 2: Query analyzer cache (24h TTL)
  - Tier 2: Search results cache (2h TTL)
- Different query phrasings now trigger cache HIT
- Cache performance: 1-5ms latency for semantic matching

### 📝 Documentation
- Added `CACHING.md` - Comprehensive caching architecture guide
- Added `SEMANTIC_CACHE_COMPARISON.md` - Comparison of semantic cache approaches

### ⚡ Performance
- Semantic cache hit rate: 70-80%
- Cost savings: 90% (LLM call reduction)
- Cache query latency: 1-5ms

---

## [2.4.0] - 2025-11-05

### ✨ Added
- **Universal Document Indexer** - CLI tool for indexing multiple formats
  - Supports: PDF, DOCX, CSV, XLSX in single command
  - New script: `simple_index_test.py`
- Demo files organized in `data/demo/`
  - `demo_BG.csv` - 4 Bulgarian property listings
  - `info_bg_home.docx` - Company contact information

### 🐛 Fixed
- Fixed Docling parser configuration issues
- Improved CSV to Qdrant indexing reliability

### 📝 Documentation
- Added usage examples for universal indexer
- Documented demo file structure

---

## [2.3.1] - 2025-11-04

### ✨ Added
- **CSV Support** - Direct CSV → Qdrant indexer
  - New script: `src/ingestion/csv_to_qdrant.py`
  - Structured metadata extraction for filtering
- Qdrant Web UI access documentation

### 📝 Documentation
- Added `PIPELINE_OVERVIEW.md` - Complete system architecture
- Documented Qdrant collections:
  - `legal_documents` - 1,294 points (Ukrainian Criminal Code)
  - `bulgarian_properties` - 4 points (demo CSV)
- Added Qdrant Web UI access instructions

### 🔧 Configuration
- Documented Qdrant API key usage
- Added collection statistics

---

## [2.3.0] - 2025-10-30

### ✨ Added
- **Variant B: DBSF + ColBERT** Search Engine
  - Distribution-Based Score Fusion (DBSF) algorithm
  - Statistical score normalization
  - 7% faster than RRF variant (0.937s vs 1.0s)
- **A/B Testing Framework**
  - Compare Variant A (RRF) vs Variant B (DBSF)
  - MLflow experiment tracking
  - Automated metrics calculation

### ⚡ Performance
- Variant B latency: ~0.937s
- Top result agreement with Variant A: 66.7%
- Expected Recall@1: ~94-95%

### 📝 Documentation
- Added Variant A/B comparison guide
- Documented DBSF fusion algorithm
- Added A/B testing instructions

---

## [2.2.0] - 2025-10-30

### ✨ Added
- **Variant A: RRF + ColBERT** (Default Search Engine)
  - 3-Stage Pipeline:
    1. Prefetch: Dense (100) + Sparse BM42 (100)
    2. Fusion: Reciprocal Rank Fusion (RRF)
    3. Rerank: ColBERT MaxSim
  - BM42 sparse vectors (better than BM25 for short chunks)
  - Server-side ColBERT reranking in Qdrant

### ⚡ Performance
- Recall@1: ~95% (improved from 91.3% baseline)
- NDCG@10: ~0.98
- Latency: ~1.0s
- +9% Precision@10 with BM42 vs BM25

### 🔧 Changed
- Made Variant A default search engine
- Upgraded Qdrant to v1.15.4 for BM42 support

---

## [2.1.0] - 2025-10-30

### ✨ Added
- **ML Platform Integration**
  - MLflow experiment tracking (port 5000)
  - Langfuse LLM tracing (port 3001)
  - RAGAS evaluation framework
  - OpenTelemetry distributed tracing
- **2-Level Redis Cache**
  - Level 1: Embeddings cache (7 days TTL)
  - Level 2: Search results cache (1 hour TTL)
- **Model Registry**
  - Staging → Production workflow
  - Version tracking
  - Rollback capability
- **Security Features**
  - PII redaction (Ukrainian patterns)
  - Budget guards ($10/day, $300/month)
  - Rate limiting framework

### 📝 Documentation
- Added `src/evaluation/README.md` - MLflow/Langfuse guide
- Added `src/cache/README.md` - Caching architecture
- Added `src/governance/README.md` - Model registry
- Added `src/security/README.md` - Security features

### 🔧 Infrastructure
- Prometheus metrics (port 9090)
- Grafana dashboards (port 3000)

---

## [2.0.0] - 2025-10-25

### ✨ Added
- **BGE-M3 Multi-Vector Embeddings**
  - Dense vectors (1024-dim) for semantic search
  - Sparse vectors (BM25) for keyword matching
  - ColBERT multivectors for token-level reranking
- **Qdrant Optimizations**
  - Scalar Int8 quantization (4x compression, 0.99 accuracy)
  - ~75% RAM savings (original vectors on disk)
  - HNSW optimization (m=16, ef_construct=200)
  - Batch processing (32 embeddings, 16 documents)

### ⚡ Performance
- Recall@10: 0.96
- NDCG@10: 0.98
- RAM savings: ~75%
- Query latency: < 1.5s

### 🔄 Changed
- Upgraded from single-vector to multi-vector approach
- Migrated from BM25 to BM42 sparse vectors

### 📝 Documentation
- Added `QDRANT_STACK.md` - Detailed configuration guide

---

## [1.0.0] - 2025-10-15

### ✨ Initial Release
- Basic RAG pipeline with dense vectors
- PDF document parsing (PyMuPDF)
- Baseline search engine (Recall@1: 91.3%)
- Qdrant vector database integration
- Basic caching layer

### 📦 Core Features
- Document chunking (512 chars, 128 overlap)
- Semantic search with embeddings
- LLM integration (Claude, OpenAI, Groq)
- REST API endpoints

### 📝 Documentation
- Initial README.md
- Basic setup instructions

---

## Legend

### Types of Changes
- `Added` - New features
- `Changed` - Changes in existing functionality
- `Deprecated` - Soon-to-be removed features
- `Removed` - Removed features
- `Fixed` - Bug fixes
- `Security` - Security fixes

### Priority Icons
- 🔴 **CRITICAL** - Security or data loss issues
- 🟠 **HIGH** - Performance or functionality blockers
- 🟡 **MEDIUM** - Important but not blocking
- 🟢 **LOW** - Nice-to-have improvements

### Category Icons
- ✨ Features
- 🐛 Bug Fixes
- ⚡ Performance
- 🔒 Security
- 📝 Documentation
- 🔧 Configuration
- 📦 Dependencies
- 🔄 Changes
- ❌ Removals

---

## Release Schedule

- **v2.6.0** (Critical Fixes) - Target: 2025-01-08 (2 days)
- **v2.7.0** (High Priority) - Target: 2025-01-15 (1 week)
- **v3.0.0** (Production Ready) - Target: 2025-01-24 (2 weeks)
- **v3.1.0** (Nice-to-have) - Target: 2025-02-10 (4 weeks)

---

## Versioning Strategy

This project follows [Semantic Versioning](https://semver.org/):

- **MAJOR** (X.0.0) - Breaking API changes
- **MINOR** (x.X.0) - New features (backward compatible)
- **PATCH** (x.x.X) - Bug fixes (backward compatible)

### Version Bumping Rules

- Security fixes → PATCH
- Bug fixes → PATCH
- New features → MINOR
- Performance improvements → MINOR (if significant) or PATCH
- Breaking changes → MAJOR
- Critical infrastructure changes → MAJOR

---

## How to Update This File

1. **For developers:**
   ```bash
   # Add your changes under [Unreleased]
   # Use checkbox format: - [ ] Your change description
   ```

2. **For releases:**
   ```bash
   # Move items from [Unreleased] to new version section
   # Update version number and date
   # Mark checkboxes as completed: - [x]
   ```

3. **Commit format:**
   ```bash
   git commit -m "docs(changelog): add v2.6.0 release notes"
   ```

---

**Maintained by:** Project Team
**Last updated:** 2025-01-06
**Format:** [Keep a Changelog v1.1.0](https://keepachangelog.com/en/1.1.0/)
