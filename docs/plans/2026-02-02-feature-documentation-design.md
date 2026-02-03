# Feature Documentation System Design

**Date:** 2026-02-02
**Status:** Draft
**Author:** Claude + User

## Problem

При работе с проектом Claude Code CLI каждый раз тратит время и токены на анализ кода чтобы понять контекст фичи. Нет централизованной документации фич для быстрого onboarding.

## Solution

Создать систему документации фич в `.claude/rules/features/` с автоматической загрузкой через `paths:` frontmatter. Claude получает контекст автоматически при работе с соответствующими файлами.

## Design Principles (per claude-md-writer)

| Принцип | Применение |
|---------|------------|
| Rules files < 500 lines | Каждый файл 300-450 строк |
| Use `paths:` frontmatter | Автозагрузка по glob patterns |
| Pointers over copies | Ссылки `file:line`, не копии кода |
| No linting rules | Только бизнес-логика и паттерны |
| 3-Tier System | Tier 2 (Component) level |

## File Structure

```
.claude/rules/features/
├── caching.md                 # 6-tier cache system
├── search-retrieval.md        # Hybrid RRF, Qdrant, reranking
├── query-processing.md        # Routing, analysis, preprocessing
├── embeddings.md              ***REMOVED***, USER-base, BGE-M3, BM42
├── llm-integration.md         # LiteLLM, fallbacks, streaming
├── telegram-bot.md            # Handlers, middlewares, error handling
├── user-personalization.md    # CESC, user context, preferences
├── ingestion.md               # Parsing, chunking, indexing
└── evaluation.md              # RAGAS, MLflow, metrics, A/B tests
```

**Total:** 9 new files

**Existing rules (не дублируем):**
- `.claude/rules/docker.md` — infrastructure
- `.claude/rules/observability.md` — Langfuse, baseline
- `.claude/rules/services.md` — service patterns
- `.claude/rules/search.md` — Qdrant SDK
- `.claude/rules/testing.md` — test patterns

## File Specifications

### 1. caching.md

```yaml
paths: "**/cache*.py, src/cache/**"
```

**Содержание:**
- CacheService architecture (6-tier)
- Cache key patterns (`sem:v2:`, `emb:v2:`, `search:v2:`)
- TTL strategies (2h rerank, 7d embeddings, 48h semantic)
- Distance threshold tuning (0.05 exact, 0.10 semantic)
- RedisVL SemanticCache, EmbeddingsCache setup
- CACHE_SCHEMA_VERSION bumping
- Metrics tracking (hits/misses)

**Key files:**
- `telegram_bot/services/cache.py:33` — CacheService class
- `src/cache/redis_semantic_cache.py` — legacy implementation

---

### 2. search-retrieval.md

```yaml
paths: "src/retrieval/**, **/qdrant*.py, **/retriever*.py"
```

**Содержание:**
- Search engine variants (HybridRRFColBERT, DBSF, Baseline)
- Performance benchmarks (Recall@1, latency)
- Qdrant query_points() with nested prefetch
- RRF fusion weights (dense 0.6, sparse 0.4)
- Binary Quantization (40x faster, 75% less RAM)
- Score boosting with exp_decay (freshness)
- MMR diversity reranking
- Filter building (`metadata.price`, `metadata.city`)

**Key files:**
- `src/retrieval/search_engines.py:56` — BaseSearchEngine
- `telegram_bot/services/qdrant.py:19` — QdrantService
- `telegram_bot/services/retriever.py:12` — RetrieverService

---

### 3. query-processing.md

```yaml
paths: "**/query*.py, **/filter*.py"
```

**Содержание:**
- QueryRouter: CHITCHAT/SIMPLE/COMPLEX classification
- Skip RAG for chitchat (canned responses)
- QueryAnalyzer: LLM-based filter extraction
- QueryPreprocessor: translit normalization, RRF weights
- FilterExtractor: regex fallback
- Available filters: price, rooms, city, area, floor, distance_to_sea
- Cache threshold selection (strict vs semantic)

**Key files:**
- `telegram_bot/services/query_router.py:17` — QueryType enum
- `telegram_bot/services/query_analyzer.py:14` — QueryAnalyzer
- `telegram_bot/services/query_preprocessor.py:11` — QueryPreprocessor
- `telegram_bot/services/filter_extractor.py:7` — FilterExtractor

---

### 4. embeddings.md

```yaml
paths: "**/embed*.py, **/vector*.py, **/voyage*.py, services/bge-m3-api/**, services/bm42/**, services/user-base/**"
```

**Содержание:**
- VoyageService: docs (voyage-4-large) + queries (voyage-4-lite)
- Asymmetric retrieval pattern
- Matryoshka dimensions (2048, 1024, 512, 256)
- Retry with exponential backoff (6 attempts)
- UserBaseVectorizer: Russian embeddings (768-dim, ruMTEB #1)
- BGE-M3 API: dense + sparse + ColBERT endpoints
- BM42 service: FastEmbed sparse vectors
- Batch processing (128 texts per request)

**Key files:**
- `telegram_bot/services/voyage.py:26` — VoyageService
- `telegram_bot/services/vectorizers.py:18` — UserBaseVectorizer
- `services/bge-m3-api/app.py:41` — get_model(), endpoints
- `services/bm42/main.py:22` — EmbedRequest/Response
- `services/user-base/main.py:20` — MODEL_NAME, endpoints

**Docker containers:**
- `dev-bge-m3` (8000) — 4GB RAM, dense+sparse+colbert
- `dev-bm42` (8002) — 1GB RAM, sparse only
- `dev-user-base` (8003) — 2GB RAM, Russian semantic

---

### 5. llm-integration.md

```yaml
paths: "**/llm*.py, docker/litellm/**, src/contextualization/**"
```

**Содержание:**
- LiteLLM proxy architecture
- Model routing: gpt-4o-mini → Cerebras GLM-4.7
- Fallback chain: Cerebras → Groq → OpenAI
- Router settings (retry_count: 2)
- Langfuse OTEL callback
- LLMService: async generation, streaming
- System prompts (Bulgarian real estate assistant)
- Contextualization providers (OpenAI, Claude, Groq)

**Key files:**
- `docker/litellm/config.yaml:1` — model_list, router_settings
- `telegram_bot/services/llm.py:15` — LLMService
- `src/contextualization/base.py` — BaseContextualizer
- `src/contextualization/openai.py` — OpenAI implementation

**Docker container:**
- `dev-litellm` (4000) — 512MB RAM

---

### 6. telegram-bot.md

```yaml
paths: "telegram_bot/*.py, telegram_bot/middlewares/**"
```

**Содержание:**
- PropertyBot class initialization
- Service dependencies (Cache, Voyage, Qdrant, LLM)
- Handler registration flow
- ThrottlingMiddleware: rate limiting (1.5s TTL cache)
- ErrorHandlerMiddleware: centralized error handling
- Admin exemption from throttling
- Markdown response formatting
- BM42 sparse embedding HTTP calls

**Key files:**
- `telegram_bot/bot.py:35` — PropertyBot class
- `telegram_bot/main.py` — entry point
- `telegram_bot/middlewares/throttling.py:17` — ThrottlingMiddleware
- `telegram_bot/middlewares/error_handler.py:16` — ErrorHandlerMiddleware
- `telegram_bot/config.py` — BotConfig

**Docker container:**
- `dev-bot` — 512MB RAM, depends on redis, qdrant, litellm

---

### 7. user-personalization.md

```yaml
paths: "**/cesc*.py, **/user_context*.py"
```

**Содержание:**
- CESC (Context-Enabled Semantic Cache)
- Lazy routing: skip personalization for generic queries
- Personal markers detection (regex patterns)
- UserContextService: preference extraction every 3rd query
- Preference merging (cities accumulate, scalars overwrite)
- Profile summary generation
- Redis storage with 30-day TTL
- CESCPersonalizer: LLM-based response adaptation

**Key files:**
- `telegram_bot/services/cesc.py:14` — PERSONAL_MARKERS
- `telegram_bot/services/cesc.py:72` — CESCPersonalizer
- `telegram_bot/services/user_context.py:12` — UserContextService

---

### 8. ingestion.md

```yaml
paths: "src/ingestion/**"
```

**Содержание:**
- UniversalDocumentParser: PyMuPDF (PDF 377x faster) + Docling
- ParserCache: MD5-based caching
- DocumentChunker strategies: FIXED_SIZE, SEMANTIC, SLIDING_WINDOW
- Optimal chunk size: 1024 chars for BGE-M3
- CSV row-per-chunk with structured metadata
- Field mappings (Название→title, Цена→price)
- VoyageIndexer: batch indexing with rate limiting
- Scalar Int8 quantization (4x compression)

**Key files:**
- `src/ingestion/document_parser.py:45` — ParserCache
- `src/ingestion/chunker.py:34` — DocumentChunker
- `src/ingestion/chunker.py:230` — chunk_csv_by_rows()
- `src/ingestion/voyage_indexer.py:47` — VoyageIndexer

**Docker container:**
- `dev-docling` (5001) — 4GB RAM, PDF/DOCX/CSV

---

### 9. evaluation.md

```yaml
paths: "src/evaluation/**, tests/baseline/**"
```

**Содержание:**
- SearchEvaluator: Recall@K, NDCG@10, MRR, Precision@K
- Ground truth format (expected_article)
- RAGAS integration
- MLflow experiment tracking
- A/B test runner
- Baseline comparison (thresholds.yaml)
- Golden set creation
- LightRAG graph-based retrieval (experimental)

**Key files:**
- `src/evaluation/evaluator.py:20` — SearchEvaluator
- `src/evaluation/ragas_evaluation.py` — RAGAS metrics
- `src/evaluation/mlflow_integration.py` — MLflow setup
- `src/evaluation/run_ab_test.py` — A/B testing
- `tests/baseline/collector.py` — LangfuseMetricsCollector
- `tests/baseline/thresholds.yaml` — regression thresholds

**Docker containers:**
- `dev-mlflow` (5000) — experiment tracking
- `dev-lightrag` (9621) — graph RAG (experimental)

---

## Template for Each File

```markdown
---
paths: "glob/pattern/**/*.py"
---

# Feature Name

One-line description.

## Purpose

What problem this feature solves.

## Architecture

```
Component A → Component B → Component C
```

## Key Files

| File | Line | What |
|------|------|------|
| `path/to/file.py` | 123 | Class/function description |

## How It Works

1. Step one
2. Step two
3. Step three

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `PARAM_NAME` | `value` | What it controls |

## Common Patterns

### Pattern Name

```python
# Example code (minimal, pointer to real file)
from module import Service
service = Service()
result = service.method()
```

## Dependencies

- Container: `dev-xxx` (port)
- Requires: Redis, Qdrant, etc.

## Testing

```bash
pytest tests/unit/test_feature.py -v
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| `ErrorName` | Solution |

## Development Guide

### Adding New X

1. Create file in `path/`
2. Inherit from `BaseClass`
3. Register in `__init__.py`
4. Write test in `tests/unit/`

### Common Mistakes

- Mistake 1 → Fix
- Mistake 2 → Fix
```

---

## Implementation Plan

| Step | Task | Files |
|------|------|-------|
| 1 | Create `features/` directory | `.claude/rules/features/` |
| 2 | Write caching.md | ~350 lines |
| 3 | Write search-retrieval.md | ~400 lines |
| 4 | Write query-processing.md | ~300 lines |
| 5 | Write embeddings.md | ~400 lines |
| 6 | Write llm-integration.md | ~300 lines |
| 7 | Write telegram-bot.md | ~350 lines |
| 8 | Write user-personalization.md | ~250 lines |
| 9 | Write ingestion.md | ~300 lines |
| 10 | Write evaluation.md | ~300 lines |
| 11 | Update CLAUDE.md | Add reference to features/ |
| 12 | Test paths: loading | Verify auto-load works |

**Estimated total:** ~2900 lines across 9 files

---

## Success Criteria

1. При работе с `telegram_bot/services/cache.py` → автоматически загружается `caching.md`
2. При работе с `src/retrieval/search_engines.py` → загружается `search-retrieval.md`
3. Claude понимает контекст без дополнительного анализа кода
4. Каждый файл < 500 строк
5. Нет пересечений в `paths:` между файлами

---

## Open Questions

1. Нужно ли добавить `security.md` для PII redaction?
2. LightRAG — достаточно секции в evaluation.md или отдельный файл?
3. Добавить ли примеры промптов для типичных задач?

---

## References

- `.claude/rules/docker.md` — existing infrastructure docs
- `.claude/rules/observability.md` — existing Langfuse docs
- `.claude/rules/services.md` — existing service patterns
- claude-md-writer skill — documentation standards
