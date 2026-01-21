# Добавление документов

> Как загрузить свои документы в систему

---

## Поддерживаемые форматы

- PDF
- DOCX
- CSV
- XLSX

---

## Шаг 1: Подготовка документов

Положи файлы в папку `data/`:

```bash
data/
├── my_document.pdf
├── data.csv
└── report.docx
```

---

## Шаг 2: Индексация

### PDF документы

```bash
python src/ingestion/indexer.py \
    --input data/my_document.pdf \
    --collection my_documents
```

### CSV данные

```bash
python src/ingestion/csv_to_qdrant.py \
    --input data/data.csv \
    --collection my_data \
    --recreate
```

---

## Шаг 3: Проверка

```python
from qdrant_client import QdrantClient

client = QdrantClient("localhost", port=6333)
info = client.get_collection("my_documents")
print(f"Documents: {info.points_count}")
```

---

## Параметры чанкинга

```python
# В src/ingestion/chunker.py
CHUNK_SIZE = 512      # Размер чанка
CHUNK_OVERLAP = 128   # Перекрытие
```

---

## Что дальше?

- [Поиск по документам](first-search.md)
- [Настройка collection](../reference/configuration.md)

---

**Время:** ~10 минут
