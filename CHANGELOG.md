***REMOVED*** Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

***REMOVED******REMOVED*** [Unreleased]

***REMOVED******REMOVED******REMOVED*** 🔧 Infrastructure
- [ ] Add connection pooling for Qdrant and Redis (***REMOVED***3.1)
- [ ] Create `docker-compose.yml` for all services (***REMOVED***3.2)
- [ ] Setup CI/CD pipeline with GitHub Actions (***REMOVED***3.3)
- [ ] Migrate to `AsyncQdrantClient` (***REMOVED***3.4)

***REMOVED******REMOVED******REMOVED*** ✨ Features
- [ ] Implement distributed lock for semantic cache (***REMOVED***2.2)
- [ ] Add Prometheus metrics endpoint (***REMOVED***4.1)
- [ ] User feedback loop (👍/👎 buttons)

---

***REMOVED******REMOVED*** [2.9.0] - 2026-01-21

***REMOVED******REMOVED******REMOVED*** ✨ Features
- ✅ **CESC (Context-Enabled Semantic Cache)** - personalized cached responses
  - `UserContextService` - extracts user preferences from queries via LLM
  - `CESCPersonalizer` - adapts cached responses to user context
  - Preferences: cities, budget, property types, rooms
  - Extraction frequency: every 3rd query
  - Storage: Redis JSON with 30-day TTL

***REMOVED******REMOVED******REMOVED*** ⚡ Performance
- Cache HIT personalization: ~100ms (vs 2-3s full RAG)
- Lightweight LLM call: ~100 tokens for personalization
- User context stored efficiently in Redis

***REMOVED******REMOVED******REMOVED*** 🏗️ Architecture
- New services: `telegram_bot/services/user_context.py`, `telegram_bot/services/cesc.py`
- Configuration: `cesc_enabled`, `cesc_extraction_frequency`, `user_context_ttl`
- Integration: `PropertyBot.handle_query` now personalizes cache hits

***REMOVED******REMOVED******REMOVED*** 🧪 Testing
- 33 tests total for CESC components
  - `test_user_context.py` - 19 unit tests
  - `test_cesc.py` - 11 unit tests
  - `test_cesc_integration.py` - 3 integration tests

---

***REMOVED******REMOVED*** [2.8.0] - 2025-01-06

***REMOVED******REMOVED******REMOVED*** 🛡️ Resilience
- ✅ **Graceful degradation** for all services (zero downtime)
  - Qdrant: Health checks, 5s timeout, empty results on failure
  - LLM: HTTP error handling, fallback answers with search results
  - Redis: Existing error handling improved
- ✅ **Production error handling** - services fail gracefully without crashing

***REMOVED******REMOVED******REMOVED*** 📊 Observability
- ✅ **Structured JSON logging** for production
  - JSONFormatter for log aggregation (ELK, Grafana Loki, CloudWatch)
  - Configurable via `LOG_LEVEL`, `LOG_FORMAT`, `LOG_FILE` env vars
  - StructuredLogger wrapper for contextual logging
  - Third-party logger noise reduction

***REMOVED******REMOVED******REMOVED*** 🏗️ Architecture
- Improved service resilience patterns
- Better error propagation and handling
- Production-ready logging infrastructure

---

***REMOVED******REMOVED*** [2.7.0] - 2025-01-06

***REMOVED******REMOVED******REMOVED*** ✨ Features
- ✅ **Streaming LLM responses** integrated in bot (real-time token display)
- ✅ **Conversation memory** enabled for multi-turn dialogues
- ✅ **Cross-encoder reranking** for +10-15% accuracy improvement
- ✅ Added `/clear` command to clear conversation history
- ✅ Added `/stats` command to view cache performance

***REMOVED******REMOVED******REMOVED*** ⚡ Performance
- Cross-encoder reranking: ms-marco-MiniLM-L-6-v2 (CPU-optimized)
- Rerank latency: ~50-100ms for top-5 results
- Streaming: First tokens in 0.1s (10x UX boost)

***REMOVED******REMOVED******REMOVED*** 🏗️ Architecture
- Created `src/retrieval/reranker.py` module
- Singleton pattern for cross-encoder (save memory)
- Graceful fallback: streaming → non-streaming on error

---

***REMOVED******REMOVED*** [2.6.0] - 2025-01-06

***REMOVED******REMOVED******REMOVED*** 🔒 Security
- ✅ Removed exposed API keys from README.md (***REMOVED***1.1)
- ✅ Replaced hardcoded secrets with placeholders

***REMOVED******REMOVED******REMOVED*** ⚡ Performance
- ✅ Migrated from `requests` to `httpx.AsyncClient` in search engines (***REMOVED***1.2)
- ✅ Fixed blocking async calls in `pipeline.py` (***REMOVED***1.4)
- ✅ Implemented BGE-M3 singleton pattern - **saved 4-6GB RAM** (***REMOVED***2.1)
- ✅ Added LLM streaming responses - **10x UX improvement** (0.1s TTFB) (***REMOVED***2.3)

***REMOVED******REMOVED******REMOVED*** ✨ Features
- ✅ Added `ThrottlingMiddleware` for rate limiting (1.5s window)
- ✅ Added `ErrorHandlerMiddleware` for centralized error handling
- ✅ Implemented conversation memory in Redis (multi-turn dialogues)
- ✅ Created `src/models/` module for shared model instances

***REMOVED******REMOVED******REMOVED*** 📦 Dependencies
- ✅ Completed `requirements.txt` with missing packages (***REMOVED***1.3):
  - FlagEmbedding>=1.2.0
  - sentence-transformers>=2.2.0
  - anthropic>=0.18.0
  - openai>=1.10.0
  - groq>=0.4.0
  - transformers>=4.30.0
  - mlflow>=2.22.1
  - ragas>=0.2.10
  - langfuse>=3.0.0
  - datasets>=3.0.0
  - cachetools>=5.3.0

***REMOVED******REMOVED******REMOVED*** 📝 Documentation
- ✅ Created comprehensive ROADMAP.md (16 tasks, 4 phases)
- ✅ Created CHANGELOG.md (this file)
- ✅ Created TODO.md for daily task tracking
- ✅ Created TASK_MANAGEMENT_2025.md
- ✅ Updated .claude.md with project context

***REMOVED******REMOVED******REMOVED*** 🏗️ Architecture
- ✅ Added singleton pattern for embedding models
- ✅ Integrated production-ready middleware from templates
- ✅ Implemented async streaming for LLM responses

---

***REMOVED******REMOVED*** [2.5.0] - 2025-11-05

***REMOVED******REMOVED******REMOVED*** ✨ Added
- **Semantic Cache Architecture** - 4-tier caching with Redis Vector Search
  - Tier 1: Semantic cache with KNN (COSINE similarity, threshold 0.85)
  - Tier 1: Embeddings cache (30 days TTL, 1000x speedup)
  - Tier 2: Query analyzer cache (24h TTL)
  - Tier 2: Search results cache (2h TTL)
- Different query phrasings now trigger cache HIT
- Cache performance: 1-5ms latency for semantic matching

***REMOVED******REMOVED******REMOVED*** 📝 Documentation
- Added `CACHING.md` - Comprehensive caching architecture guide
- Added `SEMANTIC_CACHE_COMPARISON.md` - Comparison of semantic cache approaches

***REMOVED******REMOVED******REMOVED*** ⚡ Performance
- Semantic cache hit rate: 70-80%
- Cost savings: 90% (LLM call reduction)
- Cache query latency: 1-5ms

---

***REMOVED******REMOVED*** [2.4.0] - 2025-11-05

***REMOVED******REMOVED******REMOVED*** ✨ Added
- **Universal Document Indexer** - CLI tool for indexing multiple formats
  - Supports: PDF, DOCX, CSV, XLSX in single command
  - New script: `simple_index_test.py`
- Demo files organized in `data/demo/`
  - `demo_BG.csv` - 4 Bulgarian property listings
  - `info_bg_home.docx` - Company contact information

***REMOVED******REMOVED******REMOVED*** 🐛 Fixed
- Fixed Docling parser configuration issues
- Improved CSV to Qdrant indexing reliability

***REMOVED******REMOVED******REMOVED*** 📝 Documentation
- Added usage examples for universal indexer
- Documented demo file structure

---

***REMOVED******REMOVED*** [2.3.1] - 2025-11-04

***REMOVED******REMOVED******REMOVED*** ✨ Added
- **CSV Support** - Direct CSV → Qdrant indexer
  - New script: `src/ingestion/csv_to_qdrant.py`
  - Structured metadata extraction for filtering
- Qdrant Web UI access documentation

***REMOVED******REMOVED******REMOVED*** 📝 Documentation
- Added `PIPELINE_OVERVIEW.md` - Complete system architecture
- Documented Qdrant collections:
  - `legal_documents` - 1,294 points (Ukrainian Criminal Code)
  - `bulgarian_properties` - 4 points (demo CSV)
- Added Qdrant Web UI access instructions

***REMOVED******REMOVED******REMOVED*** 🔧 Configuration
- Documented Qdrant API key usage
- Added collection statistics

---

***REMOVED******REMOVED*** [2.3.0] - 2025-10-30

***REMOVED******REMOVED******REMOVED*** ✨ Added
- **Variant B: DBSF + ColBERT** Search Engine
  - Distribution-Based Score Fusion (DBSF) algorithm
  - Statistical score normalization
  - 7% faster than RRF variant (0.937s vs 1.0s)
- **A/B Testing Framework**
  - Compare Variant A (RRF) vs Variant B (DBSF)
  - MLflow experiment tracking
  - Automated metrics calculation

***REMOVED******REMOVED******REMOVED*** ⚡ Performance
- Variant B latency: ~0.937s
- Top result agreement with Variant A: 66.7%
- Expected Recall@1: ~94-95%

***REMOVED******REMOVED******REMOVED*** 📝 Documentation
- Added Variant A/B comparison guide
- Documented DBSF fusion algorithm
- Added A/B testing instructions

---

***REMOVED******REMOVED*** [2.2.0] - 2025-10-30

***REMOVED******REMOVED******REMOVED*** ✨ Added
- **Variant A: RRF + ColBERT** (Default Search Engine)
  - 3-Stage Pipeline:
    1. Prefetch: Dense (100) + Sparse BM42 (100)
    2. Fusion: Reciprocal Rank Fusion (RRF)
    3. Rerank: ColBERT MaxSim
  - BM42 sparse vectors (better than BM25 for short chunks)
  - Server-side ColBERT reranking in Qdrant

***REMOVED******REMOVED******REMOVED*** ⚡ Performance
- Recall@1: ~95% (improved from 91.3% baseline)
- NDCG@10: ~0.98
- Latency: ~1.0s
- +9% Precision@10 with BM42 vs BM25

***REMOVED******REMOVED******REMOVED*** 🔧 Changed
- Made Variant A default search engine
- Upgraded Qdrant to v1.15.4 for BM42 support

---

***REMOVED******REMOVED*** [2.1.0] - 2025-10-30

***REMOVED******REMOVED******REMOVED*** ✨ Added
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

***REMOVED******REMOVED******REMOVED*** 📝 Documentation
- Added `src/evaluation/README.md` - MLflow/Langfuse guide
- Added `src/cache/README.md` - Caching architecture
- Added `src/governance/README.md` - Model registry
- Added `src/security/README.md` - Security features

***REMOVED******REMOVED******REMOVED*** 🔧 Infrastructure
- Prometheus metrics (port 9090)
- Grafana dashboards (port 3000)

---

***REMOVED******REMOVED*** [2.0.0] - 2025-10-25

***REMOVED******REMOVED******REMOVED*** ✨ Added
- **BGE-M3 Multi-Vector Embeddings**
  - Dense vectors (1024-dim) for semantic search
  - Sparse vectors (BM25) for keyword matching
  - ColBERT multivectors for token-level reranking
- **Qdrant Optimizations**
  - Scalar Int8 quantization (4x compression, 0.99 accuracy)
  - ~75% RAM savings (original vectors on disk)
  - HNSW optimization (m=16, ef_construct=200)
  - Batch processing (32 embeddings, 16 documents)

***REMOVED******REMOVED******REMOVED*** ⚡ Performance
- Recall@10: 0.96
- NDCG@10: 0.98
- RAM savings: ~75%
- Query latency: < 1.5s

***REMOVED******REMOVED******REMOVED*** 🔄 Changed
- Upgraded from single-vector to multi-vector approach
- Migrated from BM25 to BM42 sparse vectors

***REMOVED******REMOVED******REMOVED*** 📝 Documentation
- Added `QDRANT_STACK.md` - Detailed configuration guide

---

***REMOVED******REMOVED*** [1.0.0] - 2025-10-15

***REMOVED******REMOVED******REMOVED*** ✨ Initial Release
- Basic RAG pipeline with dense vectors
- PDF document parsing (PyMuPDF)
- Baseline search engine (Recall@1: 91.3%)
- Qdrant vector database integration
- Basic caching layer

***REMOVED******REMOVED******REMOVED*** 📦 Core Features
- Document chunking (512 chars, 128 overlap)
- Semantic search with embeddings
- LLM integration (Claude, OpenAI, Groq)
- REST API endpoints

***REMOVED******REMOVED******REMOVED*** 📝 Documentation
- Initial README.md
- Basic setup instructions

---

***REMOVED******REMOVED*** Legend

***REMOVED******REMOVED******REMOVED*** Types of Changes
- `Added` - New features
- `Changed` - Changes in existing functionality
- `Deprecated` - Soon-to-be removed features
- `Removed` - Removed features
- `Fixed` - Bug fixes
- `Security` - Security fixes

***REMOVED******REMOVED******REMOVED*** Priority Icons
- 🔴 **CRITICAL** - Security or data loss issues
- 🟠 **HIGH** - Performance or functionality blockers
- 🟡 **MEDIUM** - Important but not blocking
- 🟢 **LOW** - Nice-to-have improvements

***REMOVED******REMOVED******REMOVED*** Category Icons
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

***REMOVED******REMOVED*** Release Schedule

- **v2.6.0** (Critical Fixes) - Target: 2025-01-08 (2 days)
- **v2.7.0** (High Priority) - Target: 2025-01-15 (1 week)
- **v3.0.0** (Production Ready) - Target: 2025-01-24 (2 weeks)
- **v3.1.0** (Nice-to-have) - Target: 2025-02-10 (4 weeks)

---

***REMOVED******REMOVED*** Versioning Strategy

This project follows [Semantic Versioning](https://semver.org/):

- **MAJOR** (X.0.0) - Breaking API changes
- **MINOR** (x.X.0) - New features (backward compatible)
- **PATCH** (x.x.X) - Bug fixes (backward compatible)

***REMOVED******REMOVED******REMOVED*** Version Bumping Rules

- Security fixes → PATCH
- Bug fixes → PATCH
- New features → MINOR
- Performance improvements → MINOR (if significant) or PATCH
- Breaking changes → MAJOR
- Critical infrastructure changes → MAJOR

---

***REMOVED******REMOVED*** How to Update This File

1. **For developers:**
   ```bash
   ***REMOVED*** Add your changes under [Unreleased]
   ***REMOVED*** Use checkbox format: - [ ] Your change description
   ```

2. **For releases:**
   ```bash
   ***REMOVED*** Move items from [Unreleased] to new version section
   ***REMOVED*** Update version number and date
   ***REMOVED*** Mark checkboxes as completed: - [x]
   ```

3. **Commit format:**
   ```bash
   git commit -m "docs(changelog): add v2.6.0 release notes"
   ```

---

**Maintained by:** Project Team
**Last updated:** 2025-01-06
**Format:** [Keep a Changelog v1.1.0](https://keepachangelog.com/en/1.1.0/)
