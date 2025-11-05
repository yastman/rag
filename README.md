# Contextual RAG Pipeline

> **Production RAG система с гибридным поиском и ML платформой**

**Версия:** 2.5.0
**Дата:** 2025-11-05
**Репозиторий:** https://github.com/yastman/rag

---

## 🎯 Что это?

Production-ready RAG система для поиска по документам с:

- 🔍 **Гибридный поиск:** RRF + ColBERT (Variant A) / DBSF + ColBERT (Variant B)
- 🧠 **BGE-M3 Embeddings:** Dense (1024-dim) + Sparse (BM42) + ColBERT за один проход
- 🗄️ **Qdrant v1.15.4:** Scalar Int8 quantization (~75% RAM savings), оптимизированный HNSW
- 📊 **ML платформа:** MLflow + Langfuse + OpenTelemetry
- 🚀 **Redis кэш:** 4-уровневая архитектура с semantic search (Redis Vector Search)
- 📄 **Форматы:** PDF, CSV, DOCX через Docling
- 🏛️ **Model Registry:** Staging → Production workflow
- 🔒 **Security:** PII redaction + budget guards

**Use cases:**
- Уголовный кодекс Украины (1,294 документов)
- CSV данные (недвижимость, каталоги, etc.)

**Performance:**
- Recall@10: 0.96 (hybrid search)
- NDCG@10: 0.98
- Latency: ~1.0s (including ColBERT rerank)
- RAM: ~75% savings with quantization

---

## 🚀 Быстрый старт

```bash
cd /home/admin/contextual_rag
source venv/bin/activate

# Проверить статус
git status
python --version  # 3.12.3

# Добавить CSV в Qdrant
python src/ingestion/csv_to_qdrant.py \
    --input demo_BG.csv \
    --collection bulgarian_properties
```

---

## 📁 Структура

```
contextual_rag/
├── README.md                    ← ТЫ ЗДЕСЬ
├── docs/
│   ├── PIPELINE_OVERVIEW.md     ← 📖 НАЧНИ ОТСЮДА (полное описание)
│   └── QDRANT_STACK.md          ← 🗄️ Qdrant конфигурация и оптимизации
├── src/
│   ├── ingestion/               ← PDF/CSV парсеры + индексация
│   ├── retrieval/               ← Гибридный поиск (Variant A/B)
│   ├── cache/                   ← Redis 2-level cache
│   ├── evaluation/              ← MLflow + Langfuse + RAGAS
│   ├── governance/              ← Model Registry
│   ├── security/                ← PII + budget guards
│   └── core/                    ← RAG pipeline
├── scripts/
│   ├── qdrant_backup.sh         ← Backup Qdrant
│   └── qdrant_restore.sh        ← Restore Qdrant
└── tests/                       ← Unit + integration tests
```

**💡 Каждый модуль имеет свой README.md**

---

## 🔧 Конфигурация

### Environment (.env)

```bash
# API Keys
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
QDRANT_API_KEY=REDACTED_QDRANT_KEY
REDIS_PASSWORD=...

# Services
QDRANT_URL=http://localhost:6333
REDIS_HOST=redis
MLFLOW_TRACKING_URI=http://localhost:5000
LANGFUSE_HOST=http://localhost:3001
```

##***REMOVED*** Web UI

**URL:** http://localhost:6333/dashboard
**API Key:** `REDACTED_QDRANT_KEY`

**Коллекции:**
- `legal_documents` - 1294 точек
- `bulgarian_properties` - 4 точек (demo CSV)

---

## 📝 Git Workflow

```bash
# Pre-commit hooks (автоматически)
✅ Ruff Linter + Formatter
✅ Trailing whitespace
✅ Large files check

# Commit формат
<type>: <description>

- <details>

🤖 Generated with [Claude Code](https://claude.com/claude-code)
Co-Authored-By: Claude <noreply@anthropic.com>

# Типы: feat, fix, docs, refactor, test, chore
```

---

## 📊 Changelog

### v2.5.0 (2025-11-05) - Semantic Cache ✅

- ✅ **Redis Vector Search** - истинный semantic cache с KNN
- ✅ 4-tier caching: Semantic (Tier 1), Embeddings (Tier 1), Analyzer (Tier 2), Search (Tier 2)
- ✅ COSINE similarity с threshold 0.85 для semantic matching
- ✅ Разные формулировки одного вопроса → HIT
- ✅ Производительность: 1-5ms latency, 1000x speedup для embeddings
- ✅ Документация: CACHING.md + SEMANTIC_CACHE_COMPARISON.md

### v2.4.0 (2025-11-05) - Universal Indexer ✅

- ✅ Universal document indexer CLI (`simple_index_test.py`)
- ✅ Supports PDF, DOCX, CSV, XLSX in single command
- ✅ Demo files organized in `data/demo/`
- ✅ Fixed Docling parser configuration

### v2.3.1 (2025-11-04) - CSV Support ✅

- ✅ CSV → Qdrant indexer (`csv_to_qdrant.py`)
- ✅ PIPELINE_OVERVIEW.md (full system documentation)
- ✅ Qdrant Web UI access documented

### v2.3.0 (2025-10-30) - Variant B ✅

- ✅ DBSF + ColBERT (7% faster than RRF)
- ✅ A/B testing framework

### v2.2.0 (2025-10-30) - Variant A ✅

- ✅ RRF + ColBERT (default, 94% Recall@1)

### v2.1.0 (2025-10-30) - ML Platform ✅

- ✅ MLflow + Langfuse + RAGAS
- ✅ Redis 2-level cache
- ✅ Model Registry
- ✅ PII redaction + budget guards

---

## 📚 Документация

| Документ | Описание |
|----------|----------|
| [PIPELINE_OVERVIEW.md](docs/PIPELINE_OVERVIEW.md) | **НАЧНИ ЗДЕСЬ** - полное описание системы |
| [CACHING.md](CACHING.md) | **Redis кэширование** - 4-tier semantic cache |
| [SEMANTIC_CACHE_COMPARISON.md](SEMANTIC_CACHE_COMPARISON.md) | Сравнение подходов к semantic cache |
| [src/evaluation/README.md](src/evaluation/README.md) | MLflow, Langfuse, RAGAS |
| [src/cache/README.md](src/cache/README.md) | Redis 2-level cache (legacy) |
| [src/governance/README.md](src/governance/README.md) | Model Registry |
| [src/security/README.md](src/security/README.md) | PII + budget guards |

---

## 🎯 Быстрые команды

### Индексировать документы (универсальный скрипт)
```bash
# Индексировать любые файлы (PDF, DOCX, CSV, XLSX)
python simple_index_test.py file1.pdf file2.docx --collection my_docs

# Пример с демо файлами
python simple_index_test.py \
    data/demo/demo_BG.csv \
    data/demo/info_bg_home.docx \
    --collection bulgarian_properties \
    --recreate
```

**Демо файлы** (в `data/demo/`):
- `demo_BG.csv` - 4 объекта недвижимости в Болгарии
- `info_bg_home.docx` - контакты компании

### Добавить CSV (legacy)
```bash
python src/ingestion/csv_to_qdrant.py --input file.csv --collection name
```

### Backup Qdrant
```bash
./scripts/qdrant_backup.sh
```

### Проверить сервисы
```bash
curl http://localhost:6333/health  ***REMOVED***
curl http://localhost:5000/health  # MLflow
docker exec ai-redis-secure redis-cli -a $REDIS_PASSWORD PING  # Redis
```

### Запустить тесты
```bash
python test_cache.py                      # 4-tier cache tests (Semantic + Embeddings + Analyzer + Search)
python tests/test_redis_url.py           # Redis cache (legacy)
python src/evaluation/smoke_test.py      # Smoke test
pytest                                    # All tests
```

---

## 🛠️ Технологии

| Компонент | Технология | Порт |
|-----------|-----------|------|
| Vector DB | Qdrant 1.15.4 | 6333 |
| Cache | Redis Stack 8.2 (RediSearch) | 6379 |
| Embeddings | BGE-M3 (1024-dim) | - |
| ML Platform | MLflow | 5000 |
| Tracing | Langfuse | 3001 |
| Monitoring | Prometheus + Grafana | 9090, 3000 |

---

## 📞 Контакты

- **Maintainer:** yastman
- **GitHub:** https://github.com/yastman/rag
- **Issues:** https://github.com/yastman/rag/issues

---

**Last Updated:** 2025-11-04
**Python:** 3.12.3
**Path:** `/home/admin/contextual_rag/`
