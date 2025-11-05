***REMOVED*** 📚 DOCUMENTATION - Contextual RAG v2.4.0

> **Complete project documentation index**

***REMOVED******REMOVED*** 🚀 QUICK START (Start here!)

- **[README.md](../README.md)** - Project home page (5 minutes)
- **[PIPELINE_OVERVIEW.md](PIPELINE_OVERVIEW.md)** ⭐ - Full pipeline overview (10 minutes)
- **[QUICK_START.md](guides/QUICK_START.md)** - Installation and first search (5 minutes)
- **[SETUP.md](guides/SETUP.md)** - Full installation and configuration

---

***REMOVED******REMOVED*** 📖 MAIN DOCUMENTATION

***REMOVED******REMOVED******REMOVED*** 1. STRUCTURE AND ARCHITECTURE

| Document | Description |
|----------|---------|
| **[PIPELINE_OVERVIEW.md](PIPELINE_OVERVIEW.md)** ⭐ | Complete pipeline overview (ingestion → retrieval) |
| **[QDRANT_STACK.md](QDRANT_STACK.md)** ⭐ | Qdrant v1.15.4 configuration (BGE-M3, quantization, optimization) |
| **[COMPLETE_STRUCTURE.md](COMPLETE_STRUCTURE.md)** | Complete project structure (33 files, all modules) |
| **[README_NEW_STRUCTURE.md](README_NEW_STRUCTURE.md)** | New `src/` architecture description |
| **[ARCHITECTURE.md](architecture/ARCHITECTURE.md)** | System architecture and design |
| **[PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)** | Old description (reference) |

***REMOVED******REMOVED******REMOVED*** 2. API REFERENCE

| Document | Description |
|----------|---------|
| **[API_REFERENCE.md](api/API_REFERENCE.md)** ⭐ | Complete API reference for all modules |
| **[SEARCH_ENGINE_GUIDE.md](implementation/SEARCH_ENGINE_GUIDE.md)** | Search engine details (Baseline, Hybrid, DBSF) |
| **[CONFIG_GUIDE.md](implementation/CONFIG_GUIDE.md)** | Configuration and environment variables |

***REMOVED******REMOVED******REMOVED*** 3. IMPLEMENTATION AND OPTIMIZATION

| Document | Description |
|----------|---------|
| **[OPTIMIZATION_PLAN.md](implementation/OPTIMIZATION_PLAN.md)** | Optimization and improvement plan |
| **[DBSF_vs_RRF_ANALYSIS.md](implementation/DBSF_vs_RRF_ANALYSIS.md)** | Ranking method comparison |
| **[MIGRATION_PLAN.md](architecture/MIGRATION_PLAN.md)** | Migration plan to new structure |

***REMOVED******REMOVED******REMOVED*** 4. REPORTS AND RESULTS

| Document | Description |
|----------|---------|
| **[FULL_PROJECT_ANALYSIS.md](reports/FULL_PROJECT_ANALYSIS.md)** | Full project analysis (875 lines) |
| **[PHASE1_COMPLETION_SUMMARY.md](reports/PHASE1_COMPLETION_SUMMARY.md)** | Phase 1 completion |
| **[PHASE2_COMPLETION_SUMMARY.md](reports/PHASE2_COMPLETION_SUMMARY.md)** | Phase 2 completion |
| **[PHASE3_COMPLETION_SUMMARY.md](reports/PHASE3_COMPLETION_SUMMARY.md)** | Phase 3 completion |

---

***REMOVED******REMOVED*** 📚 USER GUIDES

***REMOVED******REMOVED******REMOVED*** Practical instructions

| Document | Purpose |
|----------|-----------|
| **[QUICK_START.md](guides/QUICK_START.md)** | 5-minute start |
| **[SETUP.md](guides/SETUP.md)** | Detailed installation |
| **[CODE_QUALITY.md](guides/CODE_QUALITY.md)** | Development standards |

***REMOVED******REMOVED******REMOVED*** Component usage

| Component | Document |
|-----------|----------|
| **Config** | API_REFERENCE.md → CONFIG API |
| **Contextualization** | API_REFERENCE.md → CONTEXTUALIZATION API |
| **Retrieval/Search** | API_REFERENCE.md → RETRIEVAL API |
| **Ingestion** | API_REFERENCE.md → INGESTION API |
| **Evaluation** | API_REFERENCE.md → EVALUATION API |
| **Core Pipeline** | API_REFERENCE.md → CORE PIPELINE API |

---

***REMOVED******REMOVED*** 🎯 FIND WHAT YOU NEED

***REMOVED******REMOVED******REMOVED*** I want to...

***REMOVED******REMOVED******REMOVED******REMOVED*** ...start from scratch
1. Read [README.md](../README.md)
2. Follow [QUICK_START.md](guides/QUICK_START.md)
3. Run examples from [API_REFERENCE.md](api/API_REFERENCE.md)

***REMOVED******REMOVED******REMOVED******REMOVED*** ...understand the architecture
1. Read [COMPLETE_STRUCTURE.md](COMPLETE_STRUCTURE.md) - complete structure
2. See [ARCHITECTURE.md](architecture/ARCHITECTURE.md) - system design
3. Explore [README_NEW_STRUCTURE.md](README_NEW_STRUCTURE.md) - modules

***REMOVED******REMOVED******REMOVED******REMOVED*** ...use the API
1. Open [API_REFERENCE.md](api/API_REFERENCE.md)
2. Find the needed module (Config, Contextualization, Retrieval, etc.)
3. Copy code example
4. Adapt for your use case

***REMOVED******REMOVED******REMOVED******REMOVED*** ...optimize performance
1. Read [OPTIMIZATION_PLAN.md](implementation/OPTIMIZATION_PLAN.md)
2. See [DBSF_vs_RRF_ANALYSIS.md](implementation/DBSF_vs_RRF_ANALYSIS.md)
3. Use DBSF+ColBERT (94.0% Recall@1)

***REMOVED******REMOVED******REMOVED******REMOVED*** ...develop the project
1. Read [CODE_QUALITY.md](guides/CODE_QUALITY.md)
2. Study [COMPLETE_STRUCTURE.md](COMPLETE_STRUCTURE.md)
3. See examples in [API_REFERENCE.md](api/API_REFERENCE.md)

***REMOVED******REMOVED******REMOVED******REMOVED*** ...monitor experiments
1. Read [API_REFERENCE.md](api/API_REFERENCE.md) → EVALUATION API
2. Run A/B tests (src/evaluation/run_ab_test.py)
3. Use MLflow (http://localhost:5000)

---

***REMOVED******REMOVED*** 🔍 BY MODULE

***REMOVED******REMOVED******REMOVED*** src/config/
- **Files**: constants.py, settings.py
- **Documentation**: [API_REFERENCE.md](api/API_REFERENCE.md***REMOVED***config-api) | [CONFIG_GUIDE.md](implementation/CONFIG_GUIDE.md)
- **Purpose**: Centralized configuration for entire system

***REMOVED******REMOVED******REMOVED*** src/contextualization/
- **Files**: base.py, claude.py, openai.py, groq.py
- **Documentation**: [API_REFERENCE.md](api/API_REFERENCE.md***REMOVED***contextualization-api)
- **Purpose**: LLM-based document enrichment with context

***REMOVED******REMOVED******REMOVED*** src/retrieval/
- **Files**: search_engines.py
- **Documentation**: [API_REFERENCE.md](api/API_REFERENCE.md***REMOVED***retrieval-api) | [SEARCH_ENGINE_GUIDE.md](implementation/SEARCH_ENGINE_GUIDE.md)
- **Purpose**: 3 search engines (Baseline, Hybrid RRF, DBSF+ColBERT)

***REMOVED******REMOVED******REMOVED*** src/ingestion/
- **Files**: pdf_parser.py, chunker.py, indexer.py
- **Documentation**: [API_REFERENCE.md](api/API_REFERENCE.md***REMOVED***ingestion-api)
- **Purpose**: Document loading and indexing

***REMOVED******REMOVED******REMOVED*** src/evaluation/
- **Files**: 12 modules (metrics, mlflow, langfuse, etc.)
- **Documentation**: [API_REFERENCE.md](api/API_REFERENCE.md***REMOVED***evaluation-api)
- **Purpose**: Quality evaluation and experiment tracking

***REMOVED******REMOVED******REMOVED*** src/core/
- **Files**: pipeline.py
- **Documentation**: [API_REFERENCE.md](api/API_REFERENCE.md***REMOVED***core-pipeline-api)
- **Purpose**: Main RAG pipeline (entry point)

***REMOVED******REMOVED******REMOVED*** src/utils/
- **Files**: structure_parser.py
- **Documentation**: src/utils/
- **Purpose**: Utilities and helpers

---

***REMOVED******REMOVED*** 📊 PERFORMANCE

***REMOVED******REMOVED******REMOVED*** Search (150 test queries)

| Metric | Baseline | Hybrid RRF | DBSF+ColBERT |
|---------|----------|-----------|--------------|
| **Recall@1** | 91.3% | 88.7% | **94.0%** ⭐ |
| **NDCG@10** | 0.9619 | 0.9524 | **0.9711** ⭐ |
| **MRR** | 0.9491 | 0.9421 | **0.9636** ⭐ |
| **Latency** | 0.65s | 0.72s | 0.69s |

**Conclusion**: Use DBSF+ColBERT for best results!

***REMOVED******REMOVED******REMOVED*** Indexing

- PDF Parsing: 2-3 minutes (132 chunks)
- Contextualization: 8-12 min (Claude, ~$12)
- Indexing: 1-2 minutes
- **Total**: ~15-20 minutes

---

***REMOVED******REMOVED*** 🛠️ VERSION AND STATUS

| Parameter | Value |
|----------|----------|
| **Version** | 2.0.1 |
| **Python** | ≥3.9 |
| **Status** | ✅ Production Ready |
| **Code Issues** | 0 (was 499) |
| **Types** | ✅ MyPy verified |
| **Linting** | ✅ Ruff (0 issues) |
| **Documentation** | ✅ Complete |

---

***REMOVED******REMOVED*** 📞 HELP AND SUPPORT

***REMOVED******REMOVED******REMOVED*** If something doesn't work

1. **Qdrant unavailable**
   ```bash
   docker compose up -d qdrant
   curl http://localhost:6333/health
   ```

2. **API key doesn't work**
   - Check `.env` file
   - Run: `python -c "from src.config import Settings; Settings()"`

3. **Slow search**
   - Use DBSF+ColBERT instead of Baseline
   - Increase HNSW ef parameter

***REMOVED******REMOVED******REMOVED*** Resources

- **GitHub Issues**: Create issues
- **Code examples**: [API_REFERENCE.md](api/API_REFERENCE.md***REMOVED***examples)
- **Source code**: `src/` folder

---

***REMOVED******REMOVED*** 🎓 RECOMMENDED LEARNING PATH

***REMOVED******REMOVED******REMOVED*** Day 1: Introduction
1. ✅ Read [README.md](../README.md) (15 min)
2. ✅ Complete [QUICK_START.md](guides/QUICK_START.md) (30 min)
3. ✅ Run first search (15 min)

***REMOVED******REMOVED******REMOVED*** Day 2: Architecture
1. ✅ Study [COMPLETE_STRUCTURE.md](COMPLETE_STRUCTURE.md) (45 min)
2. ✅ Read [ARCHITECTURE.md](architecture/ARCHITECTURE.md) (30 min)
3. ✅ Explore modules in `src/` (30 min)

***REMOVED******REMOVED******REMOVED*** Day 3: API and practice
1. ✅ Study [API_REFERENCE.md](api/API_REFERENCE.md) (1 hour)
2. ✅ Run code examples (30 min)
3. ✅ Write your own script (1 hour)

***REMOVED******REMOVED******REMOVED*** Day 4+: In-depth study
1. ✅ [OPTIMIZATION_PLAN.md](implementation/OPTIMIZATION_PLAN.md) - optimization
2. ✅ [CODE_QUALITY.md](guides/CODE_QUALITY.md) - standards
3. ✅ [FULL_PROJECT_ANALYSIS.md](reports/FULL_PROJECT_ANALYSIS.md) - full analysis

---

***REMOVED******REMOVED*** 📋 CHECKLIST

***REMOVED******REMOVED******REMOVED*** Setup
- [ ] Repository cloned
- [ ] Dependencies installed (`pip install -e .`)
- [ ] Copied `.env.example` to `.env`
- [ ] Filled API keys
- [ ] Started Qdrant (`docker compose up -d qdrant`)

***REMOVED******REMOVED******REMOVED*** First run
- [ ] Read QUICK_START.md
- [ ] Completed all steps
- [ ] First search works
- [ ] Results look correct

***REMOVED******REMOVED******REMOVED*** Development
- [ ] Installed pre-commit hooks
- [ ] Run tests (pytest)
- [ ] Linting passes (ruff check)
- [ ] Type checking passes (mypy)

***REMOVED******REMOVED******REMOVED*** Deployment
- [ ] Documentation up to date
- [ ] All tests pass
- [ ] Performance acceptable
- [ ] Code production ready

---

***REMOVED******REMOVED*** 🔄 UPDATES AND VERSIONS

***REMOVED******REMOVED******REMOVED*** v2.4.0 (Current)
- ✅ BGE-M3 multi-vector embeddings (dense + sparse + ColBERT)
- ✅ Qdrant v1.15.4 optimizations (Scalar Int8 quantization, ~75% RAM savings)
- ✅ BM42 sparse vectors (+9% Precision@10 vs BM25)
- ✅ Complete Qdrant stack documentation
- ✅ Updated PIPELINE_OVERVIEW.md

***REMOVED******REMOVED******REMOVED*** v2.0.1
- ✅ New `src/` architecture
- ✅ DBSF+ColBERT search
- ✅ MLflow + Langfuse integration
- ✅ Complete documentation
- ✅ Refactored modules

***REMOVED******REMOVED******REMOVED*** v2.0.0
- ✅ Basic RAG system
- ✅ Multiple search engines
- ✅ Multiple LLM providers

***REMOVED******REMOVED******REMOVED*** v3.0.0 (Planned)
- [ ] Query expansion
- [ ] Semantic caching
- [ ] Graph traversal
- [ ] Web UI dashboard

---

**Last Updated**: November 5, 2025
**Version**: 2.4.0
**Material**: Complete
