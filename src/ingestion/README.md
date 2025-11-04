# Ingestion Module

> **Парсинг, чанкинг и индексация документов в Qdrant**

---

## 📂 Скрипты

### 1. **pdf_parser.py** - PDF парсер (PyMuPDF)

**Что делает:** Парсит PDF документы через PyMuPDF (fitz)

**Класс:** `PDFParser`

**Поддерживаемые форматы:** `.pdf`, `.docx`, `.epub`, `.txt`

**Output:** `ParsedDocument` (filename, title, content, num_pages, metadata)

**Использование:**
```python
from src.ingestion import PDFParser

parser = PDFParser()
doc = parser.parse_file("document.pdf")
print(doc.content)
```

**Статус:** ⚠️ Устаревает - планируется замена на Docling

---

### 2. **csv_to_qdrant.py** - CSV → Qdrant индексатор

**Что делает:** Прямая индексация CSV файлов в Qdrant (standalone)

**Класс:** `CSVToQdrantIndexer`

**Workflow:**
1. Читает CSV файл
2. Конвертирует строки в natural language text
3. Генерирует BGE-M3 embeddings (1024-dim)
4. Индексирует в Qdrant с metadata

**CLI:**
```bash
python src/ingestion/csv_to_qdrant.py \
    --input demo_BG.csv \
    --collection bulgarian_properties \
    --recreate
```

**Статус:** ⚠️ Дубликат - планируется удаление после рефакторинга

---

### 3. **chunker.py** - Стратегии чанкинга

**Что делает:** Разбивает документы на chunks для индексации

**Класс:** `DocumentChunker`

**Стратегии:**
- `FIXED_SIZE` - Фиксированный размер (512 chars, 128 overlap)
- `SEMANTIC` - По семантическим границам (параграфы, секции)
- `SLIDING_WINDOW` - Скользящее окно с overlap

**Output:** `List[Chunk]` с metadata (text, document_name, article_number, order)

**Использование:**
```python
from src.ingestion import DocumentChunker
from src.ingestion.chunker import ChunkingStrategy

chunker = DocumentChunker(
    chunk_size=512,
    overlap=128,
    strategy=ChunkingStrategy.SEMANTIC
)

chunks = chunker.chunk_text(
    text=document.content,
    document_name="document.pdf",
    article_number="1"
)
```

**Статус:** ✅ Активен

---

### 4. **indexer.py** - Индексация в Qdrant

**Что делает:** Индексирует chunks в Qdrant vector database

**Класс:** `DocumentIndexer`

**Возможности:**
- BGE-M3 embeddings (1024-dim)
- Batch processing
- Automatic collection creation
- Payload indexes (article_number, document_name)
- Async processing

**Workflow:**
```python
from src.ingestion import DocumentIndexer

indexer = DocumentIndexer()

# Создать коллекцию
indexer.create_collection("my_collection", recreate=False)

# Индексировать chunks
stats = await indexer.index_chunks(
    chunks=chunks,
    collection_name="my_collection",
    batch_size=32
)

print(f"Indexed: {stats.indexed_chunks} chunks")
```

**Статус:** ✅ Активен

---

## 🔄 Типичный Pipeline

```python
from src.ingestion import PDFParser, DocumentChunker, DocumentIndexer

# 1. Парсинг
parser = PDFParser()
doc = parser.parse_file("document.pdf")

# 2. Чанкинг
chunker = DocumentChunker(chunk_size=512, overlap=128)
chunks = chunker.chunk_text(
    text=doc.content,
    document_name=doc.filename,
    article_number="1"
)

# 3. Индексация
indexer = DocumentIndexer()
await indexer.index_chunks(
    chunks=chunks,
    collection_name="legal_documents"
)
```

---

## 🎯 Планируемые изменения

### Рефакторинг на Docling

**Цель:** Универсальный парсер для всех форматов

**План:**
1. ✅ Изучена документация Docling через MCP Context7
2. ⏳ Обновить `pdf_parser.py` → `document_parser.py` (Docling-based)
3. ⏳ Удалить `csv_to_qdrant.py` (дубликат)
4. ⏳ Обновить импорты в `__init__.py` и `pipeline.py`

**Преимущества Docling:**
- Автоматическое определение формата (PDF, CSV, DOCX, HTML, etc.)
- Лучший парсинг таблиц и структуры
- Единый интерфейс для всех форматов
- Chunking из коробки

---

## 📊 Статистика

| Скрипт | Размер | Строк кода | Статус |
|--------|--------|-----------|--------|
| pdf_parser.py | 3.4K | ~127 | ⚠️ Устаревает |
| csv_to_qdrant.py | 9.6K | ~280 | ⚠️ Дубликат |
| chunker.py | 7.0K | ~229 | ✅ Активен |
| indexer.py | 7.1K | ~219 | ✅ Активен |

---

## 🔗 Связанные модули

- **src/retrieval/** - Поиск по проиндексированным документам
- **src/config/** - Конфигурация (Settings, VectorDimensions)
- **src/core/pipeline.py** - Использует PDFParser, DocumentChunker, DocumentIndexer

---

## 🚀 Быстрые команды

### Проверить текущую коллекцию
```python
indexer = DocumentIndexer()
stats = indexer.get_collection_stats("legal_documents")
print(stats)
```

### Batch индексация
```bash
# Использовать существующий workflow из pipeline.py
python -c "
from src.core import RAGPipeline
pipeline = RAGPipeline()
# pipeline имеет indexer, chunker, parser
"
```

---

**Last Updated:** 2025-11-04
**Maintainer:** yastman
