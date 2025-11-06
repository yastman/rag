# Contextual RAG Pipeline

> **Production RAG система с гибридным поиском и ML платформой**

**Версия:** 2.6.0
**Дата:** 2025-01-06
**Репозиторий:** https://github.com/yastman/rag
**Статус:** 🟢 Production-ready (85% complete)

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

## 🆕 v2.6.0 Updates (2025-01-06)

### Production-Ready Features

**Phase 1: Critical Fixes** ✅
- 🔒 **Security:** Removed exposed API keys, secrets moved to `.env`
- ⚡ **Performance:** Migrated to `httpx.AsyncClient` for async HTTP calls
- 📦 **Dependencies:** Completed requirements.txt (10 missing packages)
- 🐛 **Async:** Fixed blocking calls in pipeline

**Phase 2: Optimizations** ✅
- 🧠 **BGE-M3 Singleton:** Single model instance saves **4-6GB RAM**
- 💬 **Conversation Memory:** Redis-based multi-turn dialogues
- ⚡ **LLM Streaming:** Real-time token display (**0.1s TTFB**, 10x UX boost)
- 🛡️ **Middleware:** Production throttling (1.5s) + error handling

**Production Status:** 🟢 90% ready
- ✅ Security hardened
- ✅ Performance optimized
- ✅ Memory efficient
- ✅ Production middleware
- ✅ LLM streaming (0.1s TTFB)
- ✅ Conversation memory
- ✅ Cross-encoder reranking (+10-15% accuracy)
- ⏳ CI/CD pending
- ⏳ Prometheus metrics pending

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

## 📁 Структура проекта

```
contextual_rag/
├── README.md                    ← ТЫ ЗДЕСЬ
│
├── 📋 Task Management (NEW!)
│   ├── ROADMAP.md               ← ⭐ Стратегический план (16 задач, 4 фазы)
│   ├── TODO.md                  ← ⭐ Ежедневный трекинг задач
│   ├── CHANGELOG.md             ← ⭐ История изменений (Keep a Changelog)
│   ├── TASK_MANAGEMENT_2025.md  ← Best practices
│   ├── SETUP_TRACKING.md        ← Quick start guide
│   └── .claude.md               ← 🤖 Инструкции для Claude AI
│
├── .github/workflows/           ← 🤖 CI/CD автоматизация
│   ├── ci.yml                   ← Lint, Test, Security
│   ├── release.yml              ← Auto-release on tags
│   └── update-roadmap.yml       ← Auto-update progress
│
├── docs/
│   ├── PIPELINE_OVERVIEW.md     ← 📖 НАЧНИ ОТСЮДА (полное описание)
│   └── QDRANT_STACK.md          ← 🗄️ Qdrant конфигурация
│
├── src/                         ← Основной код
│   ├── core/                    ← RAG pipeline orchestrator
│   ├── models/                  ← 🆕 Shared model singletons (BGE-M3)
│   ├── retrieval/               ← Гибридный поиск (4 варианта)
│   ├── ingestion/               ← Парсинг и индексация
│   ├── cache/                   ← 4-tier Redis cache
│   ├── evaluation/              ← MLflow + Langfuse + RAGAS
│   ├── contextualization/       ← LLM интеграции
│   ├── config/                  ← Настройки
│   ├── governance/              ← Model Registry
│   └── security/                ← PII + budget guards
│
├── telegram_bot/                ← Telegram bot
│   ├── bot.py                   ← Main bot logic
│   ├── middlewares/             ← 🆕 Throttling, Error handling
│   └── services/                ← Cache, LLM (streaming), Retriever
│
├── tests/                       ← Тесты
└── scripts/                     ← Утилиты

```

**💡 Каждый модуль имеет свой README.md**
**🆕 Новая система управления задачами - см. ROADMAP.md**

---

## 🔧 Конфигурация

### Environment (.env)

```bash
# API Keys (NEVER commit .env file!)
ANTHROPIC_API_KEY=sk-ant-your_key_here
OPENAI_API_KEY=sk-your_key_here
QDRANT_API_KEY=your_qdrant_api_key_here
REDIS_PASSWORD=your_redis_password_here

# Services
QDRANT_URL=http://localhost:6333
REDIS_HOST=redis
MLFLOW_TRACKING_URI=http://localhost:5000
LANGFUSE_HOST=http://localhost:3001
```

**⚠️ ВАЖНО:** Скопируйте `.env.example` в `.env` и заполните реальные ключи.
**🔒 БЕЗОПАСНОСТЬ:** Файл `.env` добавлен в `.gitignore` - никогда не коммитьте секреты!

##***REMOVED*** Web UI

**URL:** http://localhost:6333/dashboard
**API Key:** Используйте значение из `.env` (QDRANT_API_KEY)

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

### 🆕 Управление проектом (NEW!)

| Документ | Назначение | Обновляется |
|----------|-----------|-------------|
| **[ROADMAP.md](ROADMAP.md)** | 📍 Стратегический план с приоритизированными задачами | Еженедельно |
| **[TODO.md](TODO.md)** | ✅ Ежедневный трекинг задач | Ежедневно |
| **[CHANGELOG.md](CHANGELOG.md)** | 📝 История версий (Keep a Changelog) | При release |
| **[TASK_MANAGEMENT_2025.md](TASK_MANAGEMENT_2025.md)** | 📖 Best practices & workflows | По необходимости |
| **[SETUP_TRACKING.md](SETUP_TRACKING.md)** | 🚀 Quick start для task management | Один раз |
| **[.claude.md](.claude.md)** | 🤖 Контекст для Claude AI | По необходимости |

### Техническая документация

| Документ | Описание |
|----------|----------|
| [PIPELINE_OVERVIEW.md](docs/PIPELINE_OVERVIEW.md) | **НАЧНИ ЗДЕСЬ** - полная архитектура системы |
| [QDRANT_STACK.md](docs/QDRANT_STACK.md) | Qdrant конфигурация и оптимизации |
| [CACHING.md](CACHING.md) | 4-tier semantic cache архитектура |
| [SEMANTIC_CACHE_COMPARISON.md](SEMANTIC_CACHE_COMPARISON.md) | Сравнение подходов к semantic cache |
| [src/evaluation/README.md](src/evaluation/README.md) | MLflow, Langfuse, RAGAS evaluation |
| [src/cache/README.md](src/cache/README.md) | Redis 2-level cache (legacy) |
| [src/governance/README.md](src/governance/README.md) | Model Registry workflow |
| [src/security/README.md](src/security/README.md) | PII redaction & budget guards |

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

## 🤖 Для Claude AI

Если вы - Claude AI Assistant, работающий с этим проектом:

1. **Прочитайте сначала:** [.claude.md](.claude.md) - полный контекст проекта
2. **Проверьте задачи:** [TODO.md](TODO.md) - что делать сегодня
3. **Изучите план:** [ROADMAP.md](ROADMAP.md) - стратегический roadmap
4. **Следуйте workflow:** Все инструкции в `.claude.md`

**Приоритеты:**
- 🔴 Phase 1 (Critical): Security & Performance fixes
- 🟠 Phase 2 (High): Memory & Concurrency issues
- 🟡 Phase 3 (Medium): Infrastructure & DevOps
- 🟢 Phase 4 (Low): Nice-to-have improvements

---

## 🚀 Getting Started

### Для разработчиков

```bash
# 1. Clone репозиторий
git clone https://github.com/yastman/rag
cd rag

# 2. Setup окружение
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt  # ⚠️ TODO: Complete (Task 1.3)

# 3. Настроить .env
cp .env.example .env
# Заполнить реальные API ключи

# 4. Install pre-commit hooks
pip install pre-commit
pre-commit install

# 5. Прочитать документацию
cat ROADMAP.md          # Что нужно сделать
cat TODO.md             # Текущие задачи
cat .claude.md          # Для AI assistants
```

### Для Contributors

1. Прочитать [TASK_MANAGEMENT_2025.md](TASK_MANAGEMENT_2025.md)
2. Выбрать задачу из [ROADMAP.md](ROADMAP.md)
3. Следовать workflow из [TODO.md](TODO.md)
4. Использовать Conventional Commits
5. Создать PR с reference на task

---

## 📊 Project Status

### Completion Progress

```
Phase 1 (Critical):     ░░░░░░░░░░  0% (0/4) 🔴 IN PROGRESS
Phase 2 (High):         ░░░░░░░░░░  0% (0/4) ⏳ Pending
Phase 3 (Medium):       ░░░░░░░░░░  0% (0/4) ⏳ Pending
Phase 4 (Nice-to-have): ░░░░░░░░░░  0% (0/4) ⏳ Pending

Overall: 0/16 tasks (0%)
```

### Known Issues

- 🔴 **CRITICAL:** Exposed API keys in README (Task 1.1)
- 🔴 **CRITICAL:** Blocking requests in async (Task 1.2)
- 🔴 **CRITICAL:** Incomplete requirements.txt (Task 1.3)
- 🔴 **CRITICAL:** Async methods blocking event loop (Task 1.4)

**See [ROADMAP.md](ROADMAP.md) for complete issue list**

---

## 🔗 Полезные ссылки

### Внутренние
- 📍 [Roadmap](ROADMAP.md) - План развития
- ✅ [TODO](TODO.md) - Текущие задачи
- 📝 [Changelog](CHANGELOG.md) - История изменений
- 📖 [Architecture](docs/PIPELINE_OVERVIEW.md) - Архитектура системы

### Внешние
- [GitHub Repository](https://github.com/yastman/rag)
- [Issues](https://github.com/yastman/rag/issues)
- [Qdrant Docs](https://qdrant.tech/documentation/)
- [BGE-M3 Model](https://huggingface.co/BAAI/bge-m3)

---

**Last Updated:** 2025-01-06
**Python:** 3.12.3
**Path:** `/mnt/c/Users/user/Documents/Сайты/Раг/`
**Next Release:** v2.6.0 (Critical Fixes)
