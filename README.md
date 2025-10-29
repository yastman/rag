# 🚀 Contextual RAG Pipeline v2.0.1

> **Production-ready документопошук для українських юридичних документів**

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Code Quality](https://img.shields.io/badge/Code%20Quality-Ruff-purple)](https://github.com/astral-sh/ruff)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-brightgreen)](#)

## 📋 Что это?

**Contextual RAG Pipeline** - це система пошуку та видобування інформації з українських юридичних документів з використанням:

- 🔍 **Гібридний пошук**: Dense (BGE-M3) + Sparse (ColBERT) векторы
- 🎯 **DBSF Ranking**: 94.0% Recall@1 (найкраща точність)
- 🤖 **Множина LLM**: Claude, OpenAI, Groq
- 💰 **Економія 90%**: Prompt caching для Claude API
- 📊 **ML платформи**: MLflow + Langfuse
- ✅ **Production Ready**: 0 помилок коду, повні тести

---

## 📁 Структура проекту

```
contextual_rag/
├── src/                          # Весь код програми
│   ├── config/                   # Конфігурація
│   ├── contextualization/        # LLM контекстуалізація
│   ├── retrieval/                # Пошукові движки
│   ├── ingestion/                # Завантаження документів
│   ├── evaluation/               # Оцінка та метрики
│   ├── utils/                    # Утиліти
│   └── core/                     # Основний pipeline
│
├── docs/                         # Документація
│   ├── guides/                   # Керівництва користувача
│   ├── architecture/             # Архітектура системи
│   ├── implementation/           # Деталі реалізації
│   ├── reports/                  # Звіти проекту
│   └── documents/                # Юридичні документи
│
├── tests/                        # Тести
│   ├── unit/                     # Юніт-тести
│   ├── integration/              # Інтеграційні тести
│   └── legacy/                   # Старі тести
│
├── data/                         # Дані
│   ├── documents/                # Вхідні документи
│   ├── test_queries/             # Тестові запити
│   └── evaluation/               # Результати оцінки
│
├── legacy/                       # Старий код (deprecated)
├── logs/                         # Логи
├── pyproject.toml                # Конфігурація проекту
├── .env.example                  # Приклад змінних середовища
└── docker-compose.yml            # Docker сервіси
```

---

## ⚡ Швидкий старт (5 хвилин)

### 1. Встановлення

**Варіант A: Claude Code CLI на сервері (🏆 РЕКОМЕНДОВАНО)**

```bash
# 1. SSH на сервер
ssh user@your-server.com

# 2. Клонувати проект
git clone https://github.com/yastman/rag.git
cd rag

# 3. Налаштувати середовище
python3.9 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# 4. Налаштувати Git
git config user.name "Your Name"
git config user.email "your@email.com"

# 5. Налаштувати pre-commit
pre-commit install --install-hooks
pre-commit install --hook-type pre-push

# 6. Налаштувати .env
cp .env.example .env
nano .env  # API ключі

# 7. Запустити Claude Code
claude

# Готово! Тепер просто говоріть з Claude:
# "покажи структуру проекту"
# "запусти тести"
# "створи нову функцію для..."
```

**Варіант B: Локальна розробка (без Claude Code)**

```bash
# Локально
git clone https://github.com/yastman/rag.git
cd rag

# Віртуальне середовище
python3.9 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Залежності
pip install -e ".[dev]"

# Git hooks
pre-commit install --install-hooks
pre-commit install --hook-type pre-push

# Налаштування
cp .env.example .env
# Відредагуйте .env з вашими API ключами
```

### 2. Запуск Qdrant

```bash
docker compose up -d qdrant
```

### 3. Індексація документів

```python
from src.core import RAGPipeline

pipeline = RAGPipeline()

# Індексування PDF
await pipeline.index_documents(
    pdf_paths=["docs/documents/Конституція_України.pdf"],
    collection_name="legal_documents"
)
```

### 4. Пошук

```python
# Пошук
result = await pipeline.search("Які права мають громадяни?")

for r in result.results:
    print(f"{r['article_number']}: {r['text'][:100]}...")
    print(f"Score: {r['score']:.3f}\n")
```

---

## 📚 Модулі системи

### 🔧 Config (`src/config/`)

Централізована конфігурація з валідацією:

```python
from src.config import Settings, APIProvider, SearchEngine

settings = Settings(
    api_provider=APIProvider.CLAUDE,
    search_engine=SearchEngine.DBSF_COLBERT,
)
```

### 🤖 Contextualization (`src/contextualization/`)

LLM-збагачення документів контекстом:

```python
from src.contextualization import ClaudeContextualizer

contextualizer = ClaudeContextualizer()
chunks = await contextualizer.contextualize(texts, query)
```

**Провайдери:**
- ⭐ **Claude** (рекомендовано): найвища якість, prompt caching
- **OpenAI**: дуже хороша якість
- **Groq**: найшвидший (2-4 хв на 100 chunks)

### 🔍 Retrieval (`src/retrieval/`)

Три рівні пошукових движків:

| Движок | Recall@1 | NDCG@10 | Latency |
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

Pipeline завантаження документів:

```python
from src.ingestion import PDFParser, DocumentChunker, DocumentIndexer

# 1. Парсинг PDF
parser = PDFParser()
doc = parser.parse_file("document.pdf")

# 2. Розбиття на chunks
chunker = DocumentChunker(chunk_size=512, overlap=128)
chunks = chunker.chunk_text(doc.content, doc.filename, "article_1")

# 3. Індексація в Qdrant
indexer = DocumentIndexer()
stats = await indexer.index_chunks(chunks, "legal_documents")
```

### 📊 Evaluation (`src/evaluation/`)

Оцінка якості та експерименти:

- **Метрики**: Recall@K, NDCG@K, MRR
- **MLflow**: http://localhost:5000 (tracking експериментів)
- **Langfuse**: http://localhost:3001 (LLM tracing)
- **RAGAS**: RAG evaluation framework

### 🎯 Core (`src/core/`)

Головний RAG pipeline:

```python
from src.core import RAGPipeline

pipeline = RAGPipeline()

# Пошук
result = await pipeline.search("запит", top_k=5)

# Оцінка
metrics = await pipeline.evaluate(test_queries, ground_truth)

# Статистика
stats = pipeline.get_stats()
```

---

## ⚙️ Конфігурація

Налаштування через `.env`:

```env
# LLM API
API_PROVIDER=claude              # claude, openai, groq
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GROQ_API_KEY=gsk_...

# Vector Database
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=

# Пошук
SEARCH_ENGINE=dbsf_colbert       # baseline, hybrid_rrf, dbsf_colbert
COLLECTION_NAME=legal_documents
TOP_K=10

# Функції
ENABLE_CACHING=true
ENABLE_QUERY_EXPANSION=true
ENABLE_MLFLOW=true
ENABLE_LANGFUSE=true

# Середовище
ENV=development                  # development, production
DEBUG=false
```

---

## 📊 Продуктивність

### Якість пошуку (150 тестових запитів)

```
BASELINE:       Recall@1=91.3%, NDCG@10=0.9619, Latency=0.65s
HYBRID RRF:     Recall@1=88.7%, NDCG@10=0.9524, Latency=0.72s
DBSF+ColBERT:   Recall@1=94.0%, NDCG@10=0.9711, Latency=0.69s ⭐
```

### Швидкість індексації

- **Парсинг**: 132 chunks за 2-3 хвилини
- **Контекстуалізація**: $0-3 (залежно від API)
- **Індексація**: 6 хвилин повний pipeline

---

## 🧪 Тестування

```bash
# Unit тести
pytest tests/unit/

# Інтеграційні тести
pytest tests/integration/

# Smoke тест
python src/evaluation/smoke_test.py

# A/B тестування
python src/evaluation/run_ab_test.py
```

---

## 📖 Документація

| Документ | Призначення |
|-----------|-------------|
| [QUICK_START.md](docs/guides/QUICK_START.md) | Швидкий старт за 5 хвилин |
| [ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) | Архітектура системи |
| [CODE_QUALITY.md](docs/guides/CODE_QUALITY.md) | Стандарти розробки |
| [README_NEW_STRUCTURE.md](docs/README_NEW_STRUCTURE.md) | Детальний опис структури |

---

## 🛠️ Розробка

### Робота з сервером

**🏆 Варіант 1: Claude Code CLI на сервері (НАЙПРОСТІШЕ!)**

```bash
# 1. Підключитись до сервера
ssh user@your-server.com

# 2. Встановити Claude Code (якщо ще не встановлено)
# curl -fsSL https://claude.ai/install.sh | sh

# 3. Перейти в проект
cd /path/to/rag

# 4. Запустити Claude Code
claude

# Готово! 🎉
# Claude Code автоматично:
# - Бачить всі файли проекту
# - Має доступ до Git
# - Може запускати команди
# - Редагує файли
# - Робить коміти з pre-commit hooks
# - Пушить в GitHub
```

**Переваги Claude Code CLI:**
- ⚡ **Найшвидший спосіб** - одна команда `claude`
- 🤖 **AI-асистент** - допомагає з кодом, документацією, дебагінгом
- 🔧 **Все інтегровано** - Git, linting, testing, всі інструменти
- 📝 **Автоматичні коміти** - з правильними повідомленнями
- 🎯 **Розуміє контекст** - бачить весь проект
- 🚀 **Не потрібні налаштування** - працює з коробки

**Варіант 2: VS Code Remote SSH**

```bash
# VS Code з розширенням "Remote - SSH"
# 1. F1 → "Remote-SSH: Connect to Host"
# 2. user@your-server.com
# 3. Відкрити папку /path/to/rag
```

**Варіант 3: Звичайний SSH**

```bash
ssh user@your-server.com
cd /path/to/rag
nano src/file.py  # або vim, emacs
```

**Рекомендований workflow з Claude Code:**
```bash
# На сервері
cd /path/to/rag
claude

# Потім просто кажете Claude що робити:
"Додай функцію для кешування результатів пошуку"
"Виправ помилку в src/retrieval/search_engines.py"
"Створи тести для нового модуля"
"Зроби коміт з цими змінами"
"Запуш в GitHub"

# Claude все зробить автоматично! 🎉
```

### Якість коду

```bash
# Linting
ruff check src/

# Форматування
ruff format src/

# Type checking
mypy src/ --ignore-missing-imports

# Pre-commit hooks (один раз при setup)
pip install pre-commit
pre-commit install --install-hooks
pre-commit install --hook-type pre-push

# Запуск вручну
pre-commit run --all-files
```

### Git Workflow (Автоматизовано)

**Pre-commit хуки запускаються автоматично:**

```bash
# 1. Створити feature branch
git checkout -b feature/amazing-feature

# 2. Внести зміни
# ... редагування коду ...

# 3. Коммит (автоматично: linting, formatting, checks)
git add .
git commit -m "feat: Add amazing feature"
# → Ruff перевірить та відформатує код
# → Якщо є помилки - коммит зупиниться

# 4. Push (автоматично: branch protection warning)
git push origin feature/amazing-feature
# → Попередження якщо пушите в main/master
```

**Структура коммітів (Conventional Commits):**

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

**Що відбувається автоматично:**
- ✅ **Перед commit**: Ruff перевіряє та форматує код
- ✅ **Перед push**: Попередження про push в main/master
- ✅ **При помилках**: Коммит зупиняється, треба виправити
- ✅ **Auto-fix**: Більшість помилок виправляються автоматично

---

## 🐛 Вирішення проблем

### Qdrant не доступний

```bash
docker compose up -d qdrant
curl http://localhost:6333/health
```

### API ключ не працює

```bash
python -c "from src.config import Settings; Settings()"
# Перевірте .env файл
```

### Повільний пошук

- Використовуйте DBSF+ColBERT замість Baseline
- Перевірте, що Qdrant працює
- Збільште HNSW ef параметр у конфігу

---

## 🤝 Внесок

1. Fork проекту
2. Створіть feature branch: `git checkout -b feature/amazing`
3. Commit змін: `git commit -m 'Add amazing feature'`
4. Push до branch: `git push origin feature/amazing`
5. Створіть Pull Request

---

## 📞 Підтримка

- **Issues**: [GitHub Issues](https://github.com/yastman/rag/issues)
- **Документація**: Папка `/docs`
- **Статус**: ✅ Production Ready

---

## 📜 Ліцензія

MIT License - дивись [LICENSE](LICENSE)

---

## 🎯 Roadmap

### ✅ Completed (v2.0.1)
- [x] Гібридний DBSF+ColBERT пошук
- [x] MLflow + Langfuse інтеграція
- [x] Prompt caching (90% економія)
- [x] Модульна архітектура
- [x] Повна документація

### 🚀 Planned (v2.1.0)
- [ ] Query expansion через LLM
- [ ] Semantic caching (Redis)
- [ ] Graph traversal для related articles
- [ ] Multi-language support (BGE-M3 підтримує 111 мов)
- [ ] Web UI dashboard

---

**Last Updated**: October 29, 2024
**Version**: 2.0.1
**Repository**: https://github.com/yastman/rag
**Maintainer**: Contextual RAG Team

**⭐ Якщо проект корисний - поставте зірку!**
