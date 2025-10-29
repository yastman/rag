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

```bash
# Клонування
git clone <your-repo>
cd contextual_rag

# Віртуальне середовище
python3.9 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Залежності
pip install -e .

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

### Якість коду

```bash
# Linting
ruff check src/

# Форматування
ruff format src/

# Type checking
mypy src/ --ignore-missing-imports

# Pre-commit hooks
pre-commit install
pre-commit run --all-files
```

### Структура коммітів

```bash
# Feature
git commit -m "feat: Add query expansion feature"

# Bug fix
git commit -m "fix: Fix Qdrant connection timeout"

# Documentation
git commit -m "docs: Update README with new structure"
```

---

## 🐛 Вирішення проблем

##***REMOVED*** не доступний

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

- **Issues**: [GitHub Issues](https://github.com/your-repo/issues)
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

**Last Updated**: October 29, 2025
**Version**: 2.0.1
**Maintainer**: Contextual RAG Team

**⭐ Якщо проект корисний - поставте зірку!**
