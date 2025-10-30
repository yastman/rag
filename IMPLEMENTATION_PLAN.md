# 📋 RAG System Implementation Plan

**Based on**: Azbyka RAG Plan concept
**Date**: 2025-10-30
**Version**: 1.0.0

---

## 📊 Current State Analysis

### ✅ РЕАЛИЗОВАНО (v2.1.0)

#### 1. Инфраструктура
- ✅ **Qdrant 1.15.4** - vector database (порт 6333)
- ✅ **Redis 8.2** - кэширование (порт 6379, настроен!)
- ✅ **MLflow** - experiment tracking (порт 5000)
- ✅ **Langfuse** - LLM observability (порт 3001)
- ✅ **Prometheus + Grafana** - monitoring

#### 2. Retrieval & Search
- ✅ **3 Search Engines**:
  - `BaselineSearchEngine` - dense vectors only
  - `HybridRRFSearchEngine` - RRF fusion (только dense)
  - `DBSFColBERTSearchEngine` - DBSF fusion + ColBERT
- ✅ **Cross-encoder reranking** - `search_engines_rerank.py` (BAAI/bge-reranker-v2-m3)
- ✅ **BGE-M3 embeddings** - 1024-dim dense vectors
- ✅ **Payload indexes** - article_number, document_name

#### 3. Ingestion & Chunking
- ✅ **PDF Parser** - document parsing
- ✅ **3 Chunking Strategies**:
  - Fixed size (512 chars, 128 overlap)
  - Semantic (respects document structure)
  - Sliding window (overlapping chunks)
- ✅ **Batch indexing** - async processing

#### 4. Caching
- ✅ **Redis L2 Cache**:
  - Embedding cache (TTL: 30 days)
  - Response cache (TTL: 5-60 min)
  - Version-aware keys
  - Auto-detection Docker environment

#### 5. Evaluation & Quality
- ✅ **Golden Test Set** - 93 queries (только что сгенерирован!)
  - 53 easy, 30 medium, 10 hard
  - 5 категорий: lookup, crimes, legal_concept, procedure, definitions
- ✅ **RAGAS Integration** - `ragas_evaluation.py`
  - Faithfulness (target ≥0.85)
  - Context Precision (target ≥0.80)
  - Context Recall (target ≥0.90)
  - Answer Relevancy (target ≥0.80)
- ✅ **A/B Testing** - `run_ab_test.py` (3 search engines)
- ✅ **MLflow logging** - experiments, metrics, artifacts
- ✅ **Langfuse tracing** - LLM calls, costs, latency

#### 6. Configuration
- ✅ **Settings Class** - environment-based config
- ✅ **Constants** - SearchEngine, APIProvider, ModelName enums
- ✅ **Rate Limits** - constants defined (Claude, OpenAI, Groq)
- ✅ **API Limits** - tokens, context windows, requests/min

#### 7. Security & Governance
- ✅ **PII Redaction** - Ukrainian patterns (phone, email, tax ID, passport)
- ✅ **Budget Guards** - daily ($10), monthly ($300) limits
- ✅ **Model Registry** - staging→production workflow
- ✅ **Qdrant Backups** - scripts for backup/restore

#### 8. Observability
- ✅ **OpenTelemetry** - traces, metrics
- ✅ **Langfuse** - LLM observability
- ✅ **MLflow** - experiment tracking

#### 9. LLM Contextualization
- ✅ **3 Providers**: Claude, OpenAI, Groq
- ✅ **Prompt Caching** - Claude (90% cost reduction)
- ✅ **Token Tracking** - cost estimation

#### 10. Documentation
- ✅ **Comprehensive READMEs** - all modules documented
- ✅ **Architecture docs** - detailed explanations
- ✅ **Workflow guide** - Git, commits, testing

---

## ❌ НЕ РЕАЛИЗОВАНО

### 1. Sparse Vectors / BM25 в Qdrant
**Текущее состояние**: Коллекция создаётся только с dense vectors
**Файл**: `src/ingestion/indexer.py:79`

```python
# Сейчас
self.client.create_collection(
    collection_name=collection_name,
    vectors_config=VectorParams(
        size=VectorDimensions.DENSE,  # Только dense!
        distance=Distance.COSINE,
    ),
)
```

**Нужно**: Добавить sparse vectors для BM25

```python
# Должно быть
self.client.create_collection(
    collection_name=collection_name,
    vectors_config={
        "dense": VectorParams(
            size=1024,
            distance=Distance.Cosine,
        ),
        "sparse": SparseVectorParams(
            modifier=Modifier.IDF,  # BM25-like scoring
        ),
    },
)
```

### 2. Hybrid Search (Dense + Sparse RRF)
**Текущее состояние**: `HybridRRFSearchEngine` использует только dense vectors
**Файл**: `src/retrieval/search_engines.py:119-121`

```python
# Комментарий в коде:
# RRF fusion: score = sum(1/(rank_dense + rank_sparse + 1))
# For now, using dense only (sparse search requires separate index)
```

**Нужно**: Реализовать настоящий hybrid search с RRF

### 3. L1 Cache (In-Memory LRU)
**Текущее состояние**: Только L2 (Redis)
**Нужно**: In-process LRU cache для hot queries

### 4. Query Expansion
**Текущее состояние**: Флаг есть (`enable_query_expansion`), логика не реализована
**Файл**: `src/core/pipeline.py:115-118`

```python
if use_context and self.settings.enable_query_expansion:
    # Enrich results with context (could add query expansion here)
    # For now, just use raw results
    pass
```

**Нужно**: Реализовать query expansion (multi-query, HyDE, или LLM-based)

### 5. Specialized Retrieval Tools
**Текущее состояние**: Отсутствуют
**Нужно**: BibleTool-like инструменты для специализированного поиска

### 6. Hydra Configuration Management
**Текущее состояние**: Только Settings класс + environment variables
**Нужно**: Hydra для модульных YAML configs с profiles (dev/staging/prod)

### 7. Rate Limiting Enforcement
**Текущее состояние**: Константы определены, но не используются
**Файл**: `src/config/constants.py:108-114`

```python
RATE_LIMITS = {
    APIProvider.CLAUDE: 1.2,
    APIProvider.OPENAI: 1.2,
    APIProvider.GROQ: 0.5,
}
```

**Нужно**: Middleware для rate limiting LLM calls

### 8. Regression Gates
**Текущее состояние**: Отсутствуют
**Нужно**: Automated gates блокирующие релиз при падении метрик

### 9. Red-Team Testing
**Текущее состояние**: Отсутствуют
**Нужно**: Security/jailbreak tests для LLM

### 10. Canary Index Deployment
**Текущее состояние**: Отсутствует
**Нужно**: Blue-green deployment для Qdrant collections

### 11. Disaster Recovery Playbook
**Текущее состояние**: Есть backup scripts, нет playbook
**Нужно**: Documented RTO/RPO procedures

---

## 🎯 Implementation Plan

### Phase 1: Hybrid Search (Dense + Sparse) - ПРИОРИТЕТ 1
**Цель**: Включить BM25 через sparse vectors в Qdrant
**Время**: 2-3 дня

#### Task 1.1: Добавить Sparse Vectors в Qdrant Collection
- [ ] **1.1.1** Обновить `indexer.py` - создание коллекции с dense + sparse
- [ ] **1.1.2** Добавить генерацию sparse vectors (BM25 weights)
- [ ] **1.1.3** Обновить `_index_batch()` для upsert dense + sparse
- [ ] **1.1.4** Создать utility функции для BM25 tokenization
- [ ] **1.1.5** Тестирование sparse indexing

#### Task 1.2: Реализовать Hybrid RRF Search
- [ ] **1.2.1** Обновить `HybridRRFSearchEngine.search()`
- [ ] **1.2.2** Реализовать Reciprocal Rank Fusion (RRF)
- [ ] **1.2.3** Добавить Qdrant `query_points()` с prefetch
- [ ] **1.2.4** Настроить RRF weights (alpha для dense/sparse)
- [ ] **1.2.5** A/B test: Baseline vs Hybrid RRF

#### Task 1.3: Integration Tests
- [ ] **1.3.1** Unit tests для sparse vector generation
- [ ] **1.3.2** Integration test для hybrid search
- [ ] **1.3.3** Evaluate на golden test set (93 queries)
- [ ] **1.3.4** Сравнить метрики: Recall@1, NDCG@10, MRR

**Acceptance Criteria**:
- Sparse vectors индексируются в Qdrant
- Hybrid RRF search работает
- Recall@1 ≥ baseline (91.3%)

---

### Phase 2: Caching & Performance - ПРИОРИТЕТ 2
**Цель**: L1 cache + optimizations
**Время**: 1-2 дня

#### Task 2.1: L1 In-Memory LRU Cache
- [ ] **2.1.1** Создать `src/cache/lru_cache.py`
- [ ] **2.1.2** Implement LRU cache для hot queries
- [ ] **2.1.3** Интегрировать в `RAGPipeline.search()`
- [ ] **2.1.4** Two-level caching: L1 (in-memory) → L2 (Redis)
- [ ] **2.1.5** Cache metrics (L1 hit rate, L2 hit rate)

#### Task 2.2: Query Expansion
- [ ] **2.2.1** Выбрать strategy (multi-query / HyDE / LLM-based)
- [ ] **2.2.2** Реализовать в `src/retrieval/query_expansion.py`
- [ ] **2.2.3** Интегрировать в pipeline
- [ ] **2.2.4** A/B test с/без expansion
- [ ] **2.2.5** Evaluate impact на Recall

**Acceptance Criteria**:
- L1 cache hit rate ≥ 30%
- Combined L1+L2 hit rate ≥ 70%
- Latency: p50 < 100ms, p95 < 500ms

---

### Phase 3: Configuration Management - ПРИОРИТЕТ 3
**Цель**: Hydra для модульных configs
**Время**: 2-3 дня

#### Task 3.1: Hydra Setup
- [ ] **3.1.1** Создать `configs/` directory structure
- [ ] **3.1.2** Migrate Settings → Hydra YAML
- [ ] **3.1.3** Создать profiles: dev.yaml, staging.yaml, prod.yaml
- [ ] **3.1.4** Compose configs: search, model, retrieval, cache
- [ ] **3.1.5** Update всех entry points для Hydra

#### Task 3.2: Environment-Specific Configs
- [ ] **3.2.1** dev.yaml - debug mode, small limits
- [ ] **3.2.2** staging.yaml - moderate limits
- [ ] **3.2.3** prod.yaml - production settings
- [ ] **3.2.4** Secrets management (не в Git!)

**Acceptance Criteria**:
- Hydra configs работают
- `python pipeline.py --config-name=prod` запускается
- Secrets не в Git

---

### Phase 4: Rate Limiting & Resilience - ПРИОРИТЕТ 4
**Цель**: Rate limiting + error handling
**Время**: 1-2 дня

#### Task 4.1: Rate Limiting Middleware
- [ ] **4.1.1** Создать `src/utils/rate_limiter.py`
- [ ] **4.1.2** Token bucket / leaky bucket algorithm
- [ ] **4.1.3** Per-provider limits (Claude, OpenAI, Groq)
- [ ] **4.1.4** Интегрировать в contextualizer classes
- [ ] **4.1.5** Metrics: rate_limit_hits, throttle_delays

#### Task 4.2: Resilience Patterns
- [ ] **4.2.1** Circuit breaker для LLM calls
- [ ] **4.2.2** Fallback chain: local → OpenRouter → Gemini
- [ ] **4.2.3** Retry с exponential backoff
- [ ] **4.2.4** Timeout handling (max 30s)

**Acceptance Criteria**:
- Rate limits не превышаются
- Circuit breaker срабатывает при ошибках
- Fallback chain работает

---

### Phase 5: Quality Gates & Regression - ПРИОРИТЕТ 5
**Цель**: Automated regression gates
**Время**: 1-2 дня

#### Task 5.1: Regression Gates
- [ ] **5.1.1** Создать `tests/regression_gate.py`
- [ ] **5.1.2** Thresholds: Recall@1 ≥ 0.90, NDCG@10 ≥ 0.95
- [ ] **5.1.3** Run on every commit (pre-commit hook)
- [ ] **5.1.4** Block merge if metrics drop
- [ ] **5.1.5** Slack alerts on failures

#### Task 5.2: Continuous Evaluation
- [ ] **5.2.1** Nightly RAGAS evaluation
- [ ] **5.2.2** Weekly A/B tests (new features vs baseline)
- [ ] **5.2.3** Golden set expansion (93 → 150 queries)
- [ ] **5.2.4** Drift detection (query distribution changes)

**Acceptance Criteria**:
- Regression gate блокирует bad commits
- Nightly evaluation runs автоматически
- Alerts работают

---

### Phase 6: Specialized Tools (Optional) - ПРИОРИТЕТ 6
**Цель**: Domain-specific retrieval tools
**Время**: 3-5 дней

#### Task 6.1: ArticleTool
- [ ] **6.1.1** Direct lookup: "Стаття 121" → article 121
- [ ] **6.1.2** Regex parsing: "Стаття сто двадцять перша"
- [ ] **6.1.3** Fallback to semantic search
- [ ] **6.1.4** Cache exact matches

#### Task 6.2: ConceptTool
- [ ] **6.2.1** "Які злочини проти власності?" → category filter
- [ ] **6.2.2** Metadata-based filtering (chapter, section)
- [ ] **6.2.3** Semantic expansion для concepts

#### Task 6.3: Tool Orchestration
- [ ] **6.3.1** Tool router - выбор tool по query type
- [ ] **6.3.2** Multi-tool queries (article + concept)
- [ ] **6.3.3** Langfuse tracing для tool calls

**Acceptance Criteria**:
- ArticleTool: 100% accuracy на direct lookups
- ConceptTool: Recall@5 ≥ 0.95
- Tools интегрированы в pipeline

---

### Phase 7: Security & Red-Team - ПРИОРИТЕТ 7
**Цель**: Security hardening
**Время**: 2-3 дня

#### Task 7.1: Red-Team Tests
- [ ] **7.1.1** Jailbreak attempts (system prompts)
- [ ] **7.1.2** PII injection tests
- [ ] **7.1.3** Prompt injection attacks
- [ ] **7.1.4** Adversarial queries
- [ ] **7.1.5** Generate test suite (20+ attacks)

#### Task 7.2: Security Hardening
- [ ] **7.2.1** Input validation (max length, allowed chars)
- [ ] **7.2.2** Output sanitization
- [ ] **7.2.3** Rate limiting per user (not just global)
- [ ] **7.2.4** API key rotation policy

**Acceptance Criteria**:
- Red-team tests pass (0 jailbreaks)
- Security checklist complete
- Audit log для security events

---

### Phase 8: Disaster Recovery - ПРИОРИТЕТ 8
**Цель**: DR playbook + automation
**Время**: 1 день

#### Task 8.1: DR Playbook
- [ ] **8.1.1** Document RTO (Recovery Time Objective): 1 hour
- [ ] **8.1.2** Document RPO (Recovery Point Objective): 24 hours
- [ ] **8.1.3** Restore procedures (step-by-step)
- [ ] **8.1.4** Rollback procedures
- [ ] **8.1.5** Contact list (on-call engineer)

#### Task 8.2: Automated Backups
- [ ] **8.2.1** Daily Qdrant snapshots (cron)
- [ ] **8.2.2** Backup to S3 / remote storage
- [ ] **8.2.3** Test restore procedure monthly
- [ ] **8.2.4** Backup monitoring (alert if failed)

#### Task 8.3: Canary Deployment
- [ ] **8.3.1** Blue-green collections (v1, v2)
- [ ] **8.3.2** Gradual traffic shift (10% → 50% → 100%)
- [ ] **8.3.3** Rollback procedure (switch back to v1)
- [ ] **8.3.4** Metrics comparison (v1 vs v2)

**Acceptance Criteria**:
- DR playbook documented
- Backup/restore tested successfully
- Canary deployment works

---

## 📅 Timeline

| Phase | Tasks | Priority | Duration | Dependencies |
|-------|-------|----------|----------|--------------|
| **Phase 1** | Hybrid Search (Sparse Vectors + RRF) | 🔴 P1 | 2-3 days | None |
| **Phase 2** | Caching & Performance (L1 + Query Expansion) | 🔴 P2 | 1-2 days | Phase 1 |
| **Phase 3** | Hydra Configuration | 🟡 P3 | 2-3 days | None |
| **Phase 4** | Rate Limiting & Resilience | 🟡 P4 | 1-2 days | Phase 3 |
| **Phase 5** | Regression Gates | 🟡 P5 | 1-2 days | Phase 1, 2 |
| **Phase 6** | Specialized Tools (Optional) | 🟢 P6 | 3-5 days | Phase 1 |
| **Phase 7** | Security & Red-Team | 🟡 P7 | 2-3 days | Phase 4 |
| **Phase 8** | Disaster Recovery | 🟢 P8 | 1 day | None |

**Total**: 13-21 days (2-3 недели intensive work)

---

## 🎯 Success Metrics

### Retrieval Quality
- **Recall@1** ≥ 0.94 (current baseline: 0.913)
- **NDCG@10** ≥ 0.97 (current baseline: 0.9619)
- **MRR** ≥ 0.96

### Performance
- **Latency p50** < 100ms (cache hit)
- **Latency p95** < 500ms (cache miss + dense+sparse search)
- **Cache hit rate** ≥ 70% (L1 + L2 combined)

### RAGAS Quality (на golden set)
- **Faithfulness** ≥ 0.85
- **Context Precision** ≥ 0.80
- **Context Recall** ≥ 0.90
- **Answer Relevancy** ≥ 0.80

### Availability & Reliability
- **Uptime** ≥ 99.5%
- **Error rate** < 0.1%
- **Rate limit compliance** 100%

### Security
- **PII detection rate** tracked
- **Budget compliance** 100% (не превышаем $10/day, $300/month)
- **Red-team tests** 100% passed

---

## 📚 References

### Azbyka Plan Concepts Applied
1. ✅ **Two-layer caching** - L1 (in-memory) + L2 (Redis)
2. ✅ **Hydra configs** - modular YAML configuration
3. ✅ **RAGAS evaluation** - quality metrics
4. ✅ **MLflow + Langfuse** - observability stack
5. ✅ **Hybrid search** - dense + sparse + RRF
6. ✅ **Golden test set** - 93 queries (expanding to 150)
7. ✅ **Regression gates** - automated quality checks
8. ✅ **Security** - PII redaction, budget guards, red-team
9. ✅ **DR/Backups** - Qdrant snapshots, restore procedures

### Documentation Links
- `/srv/app/README.md` - main workflow guide
- `src/*/README.md` - module-specific docs
- `Azbyka_RAG_PLAN_2025_v2.md` - original concept plan

---

## ✅ Next Steps

1. **Review this plan** with team
2. **Prioritize phases** based on business needs
3. **Start with Phase 1** (Hybrid Search) - highest impact
4. **Track progress** - update this document
5. **Celebrate wins** 🎉

---

**Last Updated**: 2025-10-30
**Owner**: Contextual RAG Team
**Status**: Ready for Implementation
