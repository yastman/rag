# Contextual RAG Pipeline

> **RAG система для украинских юридических документов с production ML платформой**

**Версия:** 2.2.0
**Дата:** 2025-10-30
**Репозиторий:** https://github.com/yastman/rag
**Ветка:** main

---

## 📖 Для новой сессии Claude

Привет! Ты начинаешь новую сессию без контекста. Этот README даст тебе всё для работы.

### Что это за проект?

**Contextual RAG Pipeline** - production-ready система поиска по Уголовному кодексу Украины с:
- 🔍 Гибридный поиск: **Variant A** (RRF + ColBERT) - 2025 best practice, ~94% Recall@1
- 📊 ML платформа: MLflow + Langfuse + OpenTelemetry
- 🚀 Redis кэш (2 уровня, версионирование)
- 🏛️ Model Registry (Staging → Production)
- 🔒 PII redaction + budget guards
- 🛠️ Qdrant backups (7-day rotation)

**Пользователь:** yastman
**Язык:** Python 3.12
**Окружение:** `/srv/app/` на сервере

---

## 📁 Структура проекта

```
/srv/app/
│
├── README.md                           ← ТЫ ЗДЕСЬ (главный README)
├── Azbyka_RAG_PLAN_2025_v2.md          ← Новый проект (православный портал)
│
├── src/                                ← Исходный код
│   ├── evaluation/                     ← ✅ MLflow, Langfuse, RAGAS, A/B tests
│   │   └── README.md                   ← Документация evaluation
│   ├── observability/                  ← ✅ OpenTelemetry (Tempo, Prometheus)
│   │   └── README.md                   ← Документация observability
│   ├── cache/                          ← ✅ Redis semantic cache
│   │   └── README.md                   ← Документация cache
│   ├── governance/                     ← ✅ Model Registry (MLflow)
│   │   └── README.md                   ← Документация governance
│   ├── security/                       ← ✅ PII redaction, budget guards
│   │   └── README.md                   ← Документация security
│   ├── retrieval/                      ← Поисковые движки (DBSF, ColBERT)
│   ├── contextualization/              ← LLM контекстуализация
│   ├── ingestion/                      ← Парсинг документов
│   ├── config/                         ← Конфигурация
│   └── core/                           ← Основной RAG pipeline
│
├── scripts/                            ← ✅ Автоматизация
│   ├── README.md                       ← Документация scripts
│   ├── qdrant_backup.sh                ← Nightly бэкапы Qdrant
│   └── qdrant_restore.sh               ← Disaster recovery
│
├── docs/                               ← Документация
│   ├── ML_PLATFORM_INTEGRATION_PLAN.md ← План ML платформы (Week 1-3)
│   ├── guides/                         ← Гайды
│   ├── architecture/                   ← Архитектура
│   └── reports/                        ← Отчёты
│
├── tests/                              ← Тесты
│   ├── data/golden_test_set.json       ← 150 тестовых запросов
│   └── test_redis_cache.py             ← Тесты Redis
│
├── data/                               ← Данные
├── legacy/                             ← Старый код (для справки)
├── logs/                               ← Логи
│
├── .env                                ← Секреты (НЕ в Git!)
├── .env.example                        ← Пример env переменных
├── pyproject.toml                      ← Зависимости
├── .pre-commit-config.yaml             ← Pre-commit hooks
└── venv/                               ← Virtual environment
```

**💡 Важно:** Каждая папка (`src/*/`) имеет свой **README.md** с подробной документацией!

---

## 🚀 Как начать работу

### 1. Окружение

```bash
# Ты уже здесь:
cd /srv/contextual_rag

# Virtual environment
source venv/bin/activate

# Python 3.12
python --version  # Python 3.12.3
```

### 2. Git

```bash
# Текущая ветка
git branch  # * main

# Статус
git status

# История (последние 5 коммитов)
git log --oneline -5
```

### 3. Конфигурация

```bash
# Секреты в .env (НЕ в Git!)
cat .env | grep REDIS_PASSWORD  # Пароль Redis
cat .env | grep ANTHROPIC       # API ключи

# Окружение
echo $REDIS_HOST        # redis (Docker network)
echo $MLFLOW_TRACKING_URI  # http://localhost:5000
```

---

## 📝 Git Workflow (ВАЖНО!)

### Правила коммитов

Используем **Conventional Commits**:

```bash
# Формат
<type>: <description>

- <details line 1>
- <details line 2>

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

### Типы коммитов

| Тип | Когда использовать | Пример |
|-----|-------------------|--------|
| `feat` | Новая функциональность | `feat: Add Redis semantic cache` |
| `fix` | Исправление бага | `fix: Fix Qdrant connection timeout` |
| `docs` | Документация | `docs: Create README for cache module` |
| `refactor` | Рефакторинг | `refactor: Optimize search engine` |
| `test` | Тесты | `test: Add unit tests for cache` |
| `chore` | Инфраструктура | `chore: Update dependencies` |

### Примеры коммитов

```bash
# Хороший коммит ✅
git commit -m "$(cat <<'EOF'
feat: Configure Redis semantic cache for Docker environment

- Updated RedisSemanticCache to use Docker network by default
- Added automatic REDIS_PASSWORD loading from environment
- Created example_usage.py with integration examples
- Added tests for Redis connectivity

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"

# Плохой коммит ❌
git commit -m "fixed stuff"
```

### Pre-commit hooks

**Автоматически запускаются при каждом коммите:**

```bash
# Что проверяется:
✅ Ruff Linter (check + fix)       # Проверка кода + автофикс
✅ Ruff Formatter                  # Форматирование
✅ Trailing whitespace             # Пробелы в конце строк
✅ End of files                    # Пустая строка в конце файлов
✅ Large files                     # Файлы > 500KB
✅ Merge conflicts                 # Конфликты слияния
✅ Debugger imports                # print(), debugger
```

**Если коммит падает:**
1. Ruff автоматически исправит код
2. Нужно заново `git add` исправленные файлы
3. Повторить `git commit`

### Workflow

```bash
# 1. Проверить статус
git status

# 2. Добавить файлы
git add <files>
# или всё сразу
git add -A

# 3. Коммит (pre-commit hooks запустятся автоматически)
git commit -m "feat: Add new feature

- Detail 1
- Detail 2

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"

# 4. Push (если нужно)
git push origin main
```

---

## 📊 Changelog (История изменений)

### v2.2.0 (2025-10-30) - Variant A Implementation ✅

**Hybrid RRF + ColBERT Reranking (2025 Best Practice):**
- ✅ **Variant A search engine** (HybridRRFColBERTSearchEngine)
- ✅ **BGE-M3 integration** (dense + sparse + ColBERT vectors)
- ✅ **3-stage pipeline** (Prefetch 100 + RRF fusion + ColBERT MaxSim rerank)
- ✅ **Server-side reranking** (Qdrant Query API multivector support)
- ✅ **Comprehensive tests** (3 test queries, all passed with method verification)
- ✅ **Set as default** (SearchEngine.HYBRID_RRF_COLBERT in config)
- ✅ **Expected performance** (~94% Recall@1, ~0.97 NDCG@10)

**Commits:**
- `a16f5d6` - feat: implement Variant A - complete BGE-M3 + ColBERT rerank

### v2.1.0 (2025-10-30) - Production ML Platform ✅

**Week 1-3 Implementation:**
- ✅ **RAGAS quality metrics** (faithfulness ≥ 0.85, precision ≥ 0.80, recall ≥ 0.90)
- ✅ **Golden test set** (150 queries: lookup/crimes/concepts/procedures/definitions)
- ✅ **MLflow integration** (experiments, Model Registry, A/B testing)
- ✅ **Langfuse integration** (LLM tracing, cost tracking)
- ✅ **OpenTelemetry** (traces → Tempo, metrics → Prometheus)
- ✅ **Redis semantic cache** (2-layer: embeddings 30d + responses 5-60min)
- ✅ **Model Registry** (Staging → Production workflow, rollback)
- ✅ **Qdrant backups** (nightly, 7-day rotation, RTO < 1 hour)
- ✅ **PII redaction** (Ukrainian phones, emails, tax IDs, passports)
- ✅ **Budget guards** ($10/day, $300/month limits)
- ✅ **Comprehensive documentation** (README in each module)

**Commits:**
- `39051e9` - feat: Configure Redis semantic cache for Docker environment
- `4de8a79` - docs: Create comprehensive README documentation for all modules
- `d64d3ea` - feat: implement production ML platform - Week 1, 2, 3 complete
- `e1413c7` - fix: clean up ML platform plan - remove broken code and old sections
- `868dc73` - feat: complete production-ready ML platform integration plan

### v2.0.1 (2025-10-29) - Stable Production

**Features:**
- Hybrid DBSF+ColBERT search (94% Recall@1)
- Prompt caching (90% cost savings)
- Modular architecture
- Complete documentation

### v2.0.0 (2025-10-15) - Major Refactor

**Breaking changes:**
- New modular structure (`src/evaluation/`, `src/retrieval/`)
- Unified configuration via Pydantic
- API changes in core pipeline

---

## 📚 Важные документы

### 📖 Планы

| Документ | Описание | Статус |
|----------|----------|--------|
| [ML_PLATFORM_INTEGRATION_PLAN.md](docs/ML_PLATFORM_INTEGRATION_PLAN.md) | План ML платформы (Week 1-3) | ✅ Завершён |
| [Azbyka_RAG_PLAN_2025_v2.md](Azbyka_RAG_PLAN_2025_v2.md) | Новый проект: православный портал | 📋 В планах |

### 📂 README по модулям

| Модуль | README | Что внутри |
|--------|--------|-----------|
| Evaluation | [src/evaluation/README.md](src/evaluation/README.md) | MLflow, Langfuse, RAGAS, A/B tests, Golden test set |
| Observability | [src/observability/README.md](src/observability/README.md) | OpenTelemetry, Tempo, Prometheus, Grafana |
| Cache | [src/cache/README.md](src/cache/README.md) | Redis semantic cache, versioning, cost tracking |
| Governance | [src/governance/README.md](src/governance/README.md) | Model Registry, Staging→Production, rollback |
| Security | [src/security/README.md](src/security/README.md) | PII redaction, budget guards, Ukrainian patterns |
| Scripts | [scripts/README.md](scripts/README.md) | Qdrant backup/restore, disaster recovery |

---

## 🛠️ Технический стек

### Основное

| Компонент | Версия | Назначение |
|-----------|--------|-----------|
| **Python** | 3.12.3 | Основной язык |
| **Qdrant** | 1.15.4 | Vector database |
| **Redis** | 8.2 | Кэш (2 уровня) |
| **MLflow** | latest | Эксперименты, Model Registry |
| **Langfuse** | latest | LLM tracing, cost tracking |

### ML Платформа

| Компонент | Порт | Назначение |
|-----------|------|-----------|
| **MLflow UI** | :5000 | http://localhost:5000 |
| **Langfuse UI** | :3001 | http://localhost:3001 |
| **Prometheus** | :9090 | http://localhost:9090 |
| **Grafana** | :3000 | http://localhost:3000 |
| **Qdrant** | :6333 | http://localhost:6333 |
| **Redis** | :6379 | redis:6379 (Docker network) |

### Библиотеки

```toml
# Ключевые зависимости
qdrant-client = "^1.12.1"
redis = "^7.0.1"
mlflow = "^2.19.0"
langfuse = "^2.57.0"
opentelemetry-api = "*"
opentelemetry-sdk = "*"
ragas = "*"
pydantic = "^2.9.2"
fastapi = "^0.115.4"
```

---

## 🔍 Быстрая диагностика

### Проверить окружение

```bash
# Python
python --version  # 3.12.3

# Virtual environment
which python  # /srv/app/venv/bin/python

# Git
git remote -v  # origin https://github.com/yastman/rag.git
git branch     # * main
```

### Проверить сервисы

```bash
# Qdrant
curl http://localhost:6333/health

# Redis
docker exec ai-redis-secure redis-cli -a $REDIS_PASSWORD PING

# MLflow
curl http://localhost:5000/health

# Langfuse
curl http://localhost:3001/api/health
```

### Запустить тесты

```bash
# Redis cache
python tests/test_redis_url.py

# Smoke test
python src/evaluation/smoke_test.py

# Unit tests
pytest tests/unit/

# All tests
pytest
```

---

## 🎯 Частые задачи

### Создать новый модуль

```bash
# 1. Создать папку
mkdir -p src/new_module

# 2. Создать __init__.py
touch src/new_module/__init__.py

# 3. Создать README.md
nano src/new_module/README.md

# 4. Создать основной файл
nano src/new_module/main.py

# 5. Добавить в Git
git add src/new_module/
git commit -m "feat: Add new_module

- Created module structure
- Added README with documentation

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Добавить зависимость

```bash
# 1. Добавить в pyproject.toml
nano pyproject.toml

# 2. Установить
pip install -e ".[dev]"

# 3. Закоммитить
git add pyproject.toml
git commit -m "chore: Add new dependency

- Added <package_name> for <purpose>

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Обновить документацию

```bash
# 1. Редактировать README
nano src/<module>/README.md

# 2. Коммит
git add src/<module>/README.md
git commit -m "docs: Update <module> documentation

- Added section about <topic>
- Updated usage examples

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Сделать backup Qdrant

```bash
# Manual backup
./scripts/qdrant_backup.sh

# Setup cron (nightly at 3 AM)
crontab -e
# Add: 0 3 * * * /srv/app/scripts/qdrant_backup.sh >> /srv/logs/qdrant_backup.log 2>&1
```

---

## 🚨 Troubleshooting

### Pre-commit hook failed

```bash
# Проблема: Ruff нашёл ошибки

# Решение:
git add -A  # Добавить автофиксы от Ruff
git commit -m "..."  # Повторить коммит
```

### Redis connection error

```bash
# Проблема: Can't connect to redis:6379

# Решение:
docker ps | grep redis  # Проверить контейнер
echo $REDIS_PASSWORD    # Проверить пароль
```

### Git divergent branches

```bash
# Проблема: fatal: Need to specify how to reconcile divergent branches

# Решение:
git pull --rebase origin main
git push origin main
```

---

## 📞 Контакты и ресурсы

- **GitHub**: https://github.com/yastman/rag
- **Issues**: https://github.com/yastman/rag/issues
- **Maintainer**: yastman
- **Server**: `/srv/app/`

---

## ✅ Checklist для новой сессии

Прочитал этот README? Отлично! Теперь ты знаешь:

- [x] Что это за проект
- [x] Структуру файлов (где что лежит)
- [x] Как делать коммиты (conventional commits + pre-commit)
- [x] Где документация (README в каждой папке)
- [x] Changelog (что недавно менялось)
- [x] Технический стек (Python, Qdrant, Redis, MLflow, Langfuse)
- [x] Частые задачи (создать модуль, добавить зависимость)

**Готов работать!** 🚀

---

**Last Updated:** 2025-10-30
**Version:** 2.2.0
**Branch:** main
**Python:** 3.12.3
**Path:** `/srv/app/`
