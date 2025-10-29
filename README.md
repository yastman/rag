***REMOVED*** 🚀 Contextual RAG Pipeline v2.0.1

> **Production-ready документопошук для українських юридичних документів**

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Code Quality](https://img.shields.io/badge/Code%20Quality-Ruff-purple)](https://github.com/astral-sh/ruff)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-brightgreen)](***REMOVED***)

***REMOVED******REMOVED*** 📋 Что это?

**Contextual RAG Pipeline** - це система пошуку та видобування інформації з українських юридичних документів з використанням:

- 🔍 **Гібридний пошук**: Dense (BGE-M3) + Sparse (ColBERT) векторы
- 🎯 **DBSF Ranking**: 94.0% Recall@1 (найкраща точність)
- 🤖 **Множина LLM**: Claude, OpenAI, Groq
- 💰 **Економія 90%**: Prompt caching для Claude API
- 📊 **ML платформи**: MLflow + Langfuse
- ✅ **Production Ready**: 0 помилок коду, повні тести

---

***REMOVED******REMOVED*** 📁 Структура проекту

```
rag-fresh/
├── src/                          ***REMOVED*** Весь код програми
│   ├── config/                   ***REMOVED*** Конфігурація
│   ├── contextualization/        ***REMOVED*** LLM контекстуалізація
│   ├── retrieval/                ***REMOVED*** Пошукові движки
│   ├── ingestion/                ***REMOVED*** Завантаження документів
│   ├── evaluation/               ***REMOVED*** Оцінка та метрики
│   ├── utils/                    ***REMOVED*** Утиліти
│   └── core/                     ***REMOVED*** Основний pipeline
│
├── docs/                         ***REMOVED*** Документація
│   ├── guides/                   ***REMOVED*** Керівництва користувача
│   ├── architecture/             ***REMOVED*** Архітектура системи
│   ├── implementation/           ***REMOVED*** Деталі реалізації
│   ├── reports/                  ***REMOVED*** Звіти проекту
│   └── documents/                ***REMOVED*** Юридичні документи
│
├── tests/                        ***REMOVED*** Тести
│   ├── unit/                     ***REMOVED*** Юніт-тести
│   ├── integration/              ***REMOVED*** Інтеграційні тести
│   └── legacy/                   ***REMOVED*** Старі тести
│
├── data/                         ***REMOVED*** Дані
│   ├── documents/                ***REMOVED*** Вхідні документи
│   ├── test_queries/             ***REMOVED*** Тестові запити
│   └── evaluation/               ***REMOVED*** Результати оцінки
│
├── legacy/                       ***REMOVED*** Старий код (deprecated)
├── logs/                         ***REMOVED*** Логи
├── pyproject.toml                ***REMOVED*** Конфігурація проекту
├── .env.example                  ***REMOVED*** Приклад змінних середовища
└── docker-compose.yml            ***REMOVED*** Docker сервіси
```

---

***REMOVED******REMOVED*** ⚡ Швидкий старт (5 хвилин)

***REMOVED******REMOVED******REMOVED*** 1. Встановлення

```bash
***REMOVED*** Клонування
git clone https://github.com/yastman/rag.git
cd rag

***REMOVED*** Віртуальне середовище
python3.9 -m venv venv
source venv/bin/activate  ***REMOVED*** Windows: venv\Scripts\activate

***REMOVED*** Залежності
pip install -e .

***REMOVED*** Налаштування
cp .env.example .env
***REMOVED*** Відредагуйте .env з вашими API ключами
```

***REMOVED******REMOVED******REMOVED*** 2. Запуск Qdrant

```bash
docker compose up -d qdrant
```

***REMOVED******REMOVED******REMOVED*** 3. Індексація документів

```python
from src.core import RAGPipeline

pipeline = RAGPipeline()

***REMOVED*** Індексування PDF
await pipeline.index_documents(
    pdf_paths=["docs/documents/Конституція_України.pdf"],
    collection_name="legal_documents"
)
```

***REMOVED******REMOVED******REMOVED*** 4. Пошук

```python
***REMOVED*** Пошук
result = await pipeline.search("Які права мають громадяни?")

for r in result.results:
    print(f"{r['article_number']}: {r['text'][:100]}...")
    print(f"Score: {r['score']:.3f}\n")
```

---

***REMOVED******REMOVED*** 📚 Модулі системи

***REMOVED******REMOVED******REMOVED*** 🔧 Config (`src/config/`)

Централізована конфігурація з валідацією:

```python
from src.config import Settings, APIProvider, SearchEngine

settings = Settings(
    api_provider=APIProvider.CLAUDE,
    search_engine=SearchEngine.DBSF_COLBERT,
)
```

***REMOVED******REMOVED******REMOVED*** 🤖 Contextualization (`src/contextualization/`)

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

***REMOVED******REMOVED******REMOVED*** 🔍 Retrieval (`src/retrieval/`)

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

***REMOVED******REMOVED******REMOVED*** 📥 Ingestion (`src/ingestion/`)

Pipeline завантаження документів:

```python
from src.ingestion import PDFParser, DocumentChunker, DocumentIndexer

***REMOVED*** 1. Парсинг PDF
parser = PDFParser()
doc = parser.parse_file("document.pdf")

***REMOVED*** 2. Розбиття на chunks
chunker = DocumentChunker(chunk_size=512, overlap=128)
chunks = chunker.chunk_text(doc.content, doc.filename, "article_1")

***REMOVED*** 3. Індексація в Qdrant
indexer = DocumentIndexer()
stats = await indexer.index_chunks(chunks, "legal_documents")
```

***REMOVED******REMOVED******REMOVED*** 📊 Evaluation (`src/evaluation/`)

Оцінка якості та експерименти:

- **Метрики**: Recall@K, NDCG@K, MRR
- **MLflow**: http://localhost:5000 (tracking експериментів)
- **Langfuse**: http://localhost:3001 (LLM tracing)
- **RAGAS**: RAG evaluation framework

***REMOVED******REMOVED******REMOVED*** 🎯 Core (`src/core/`)

Головний RAG pipeline:

```python
from src.core import RAGPipeline

pipeline = RAGPipeline()

***REMOVED*** Пошук
result = await pipeline.search("запит", top_k=5)

***REMOVED*** Оцінка
metrics = await pipeline.evaluate(test_queries, ground_truth)

***REMOVED*** Статистика
stats = pipeline.get_stats()
```

---

***REMOVED******REMOVED*** ⚙️ Конфігурація

Налаштування через `.env`:

```env
***REMOVED*** LLM API
API_PROVIDER=claude              ***REMOVED*** claude, openai, groq
ANTHROPIC_API_KEY=[REDACTED-ANTHROPIC-KEY]
OPENAI_API_KEY=[REDACTED-OPENAI-KEY]
GROQ_API_KEY=[REDACTED-GROQ-KEY]

***REMOVED*** Vector Database
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=

***REMOVED*** Пошук
SEARCH_ENGINE=dbsf_colbert       ***REMOVED*** baseline, hybrid_rrf, dbsf_colbert
COLLECTION_NAME=legal_documents
TOP_K=10

***REMOVED*** Функції
ENABLE_CACHING=true
ENABLE_QUERY_EXPANSION=true
ENABLE_MLFLOW=true
ENABLE_LANGFUSE=true

***REMOVED*** Середовище
ENV=development                  ***REMOVED*** development, production
DEBUG=false
```

---

***REMOVED******REMOVED*** 📊 Продуктивність

***REMOVED******REMOVED******REMOVED*** Якість пошуку (150 тестових запитів)

```
BASELINE:       Recall@1=91.3%, NDCG@10=0.9619, Latency=0.65s
HYBRID RRF:     Recall@1=88.7%, NDCG@10=0.9524, Latency=0.72s
DBSF+ColBERT:   Recall@1=94.0%, NDCG@10=0.9711, Latency=0.69s ⭐
```

***REMOVED******REMOVED******REMOVED*** Швидкість індексації

- **Парсинг**: 132 chunks за 2-3 хвилини
- **Контекстуалізація**: $0-3 (залежно від API)
- **Індексація**: 6 хвилин повний pipeline

---

***REMOVED******REMOVED*** 🧪 Тестування

```bash
***REMOVED*** Unit тести
pytest tests/unit/

***REMOVED*** Інтеграційні тести
pytest tests/integration/

***REMOVED*** Smoke тест
python src/evaluation/smoke_test.py

***REMOVED*** A/B тестування
python src/evaluation/run_ab_test.py
```

---

***REMOVED******REMOVED*** 📖 Документація

| Документ | Призначення |
|-----------|-------------|
| [QUICK_START.md](docs/guides/QUICK_START.md) | Швидкий старт за 5 хвилин |
| [ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) | Архітектура системи |
| [CODE_QUALITY.md](docs/guides/CODE_QUALITY.md) | Стандарти розробки |
| [README_NEW_STRUCTURE.md](docs/README_NEW_STRUCTURE.md) | Детальний опис структури |

---

***REMOVED******REMOVED*** 🛠️ Розробка

***REMOVED******REMOVED******REMOVED*** Якість коду

```bash
***REMOVED*** Linting
ruff check src/

***REMOVED*** Форматування
ruff format src/

***REMOVED*** Type checking
mypy src/ --ignore-missing-imports

***REMOVED*** Pre-commit hooks (один раз при setup)
pip install pre-commit
pre-commit install --install-hooks
pre-commit install --hook-type pre-push

***REMOVED*** Запуск вручну
pre-commit run --all-files
```

***REMOVED******REMOVED******REMOVED*** Git Workflow (Автоматизовано)

**Pre-commit хуки запускаються автоматично:**

```bash
***REMOVED*** 1. Створити feature branch
git checkout -b feature/amazing-feature

***REMOVED*** 2. Внести зміни
***REMOVED*** ... редагування коду ...

***REMOVED*** 3. Коммит (автоматично: linting, formatting, checks)
git add .
git commit -m "feat: Add amazing feature"
***REMOVED*** → Ruff перевірить та відформатує код
***REMOVED*** → Якщо є помилки - коммит зупиниться

***REMOVED*** 4. Push (автоматично: branch protection warning)
git push origin feature/amazing-feature
***REMOVED*** → Попередження якщо пушите в main/master
```

**Структура коммітів (Conventional Commits):**

```bash
***REMOVED*** Feature
git commit -m "feat: Add query expansion feature"

***REMOVED*** Bug fix
git commit -m "fix: Fix Qdrant connection timeout"

***REMOVED*** Documentation
git commit -m "docs: Update README with new structure"

***REMOVED*** Refactoring
git commit -m "refactor: Optimize search engine performance"

***REMOVED*** Tests
git commit -m "test: Add unit tests for retrieval module"
```

**Що відбувається автоматично:**
- ✅ **Перед commit**: Ruff перевіряє та форматує код
- ✅ **Перед push**: Попередження про push в main/master
- ✅ **При помилках**: Коммит зупиняється, треба виправити
- ✅ **Auto-fix**: Більшість помилок виправляються автоматично

---

***REMOVED******REMOVED*** 🐛 Вирішення проблем

***REMOVED******REMOVED******REMOVED*** Qdrant не доступний

```bash
docker compose up -d qdrant
curl http://localhost:6333/health
```

***REMOVED******REMOVED******REMOVED*** API ключ не працює

```bash
python -c "from src.config import Settings; Settings()"
***REMOVED*** Перевірте .env файл
```

***REMOVED******REMOVED******REMOVED*** Повільний пошук

- Використовуйте DBSF+ColBERT замість Baseline
- Перевірте, що Qdrant працює
- Збільште HNSW ef параметр у конфігу

---

***REMOVED******REMOVED*** 🤝 Внесок

1. Fork проекту
2. Створіть feature branch: `git checkout -b feature/amazing`
3. Commit змін: `git commit -m 'Add amazing feature'`
4. Push до branch: `git push origin feature/amazing`
5. Створіть Pull Request

---

***REMOVED******REMOVED*** 📞 Підтримка

- **Issues**: [GitHub Issues](https://github.com/yastman/rag/issues)
- **Документація**: Папка `/docs`
- **Статус**: ✅ Production Ready

---

***REMOVED******REMOVED*** 📜 Ліцензія

MIT License - дивись [LICENSE](LICENSE)

---

***REMOVED******REMOVED*** 🎯 Roadmap

***REMOVED******REMOVED******REMOVED*** ✅ Completed (v2.0.1)
- [x] Гібридний DBSF+ColBERT пошук
- [x] MLflow + Langfuse інтеграція
- [x] Prompt caching (90% економія)
- [x] Модульна архітектура
- [x] Повна документація

***REMOVED******REMOVED******REMOVED*** 🚀 Planned (v2.1.0)
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
