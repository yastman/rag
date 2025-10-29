# 🔑 Content-Based Deduplication Guide

**Дата**: 2025-10-22
**Версия**: v1.1 (with deduplication)

---

## 📋 Что изменилось?

### ❌ СТАРЫЙ подход (sequential IDs):
```python
# Каждый запуск создавал новые points с новыми IDs
point_id = 1, 2, 3, 4...  # При втором запуске: 133, 134, 135...
```

**Проблема**: Дубликаты накапливаются при повторной обработке

### ✅ НОВЫЙ подход (content-based hash IDs):
```python
# ID генерируется из SHA256 hash контента
point_id = "a3f5e8c9..."  # Всегда одинаковый для одного chunk
```

**Решение**: Qdrant `upsert` автоматически обновляет существующий point

---

## 🎯 Как работает deduplication?

### 1. Генерация stable ID
```python
def generate_chunk_id(chunk_text: str, source: str, chunk_index: int) -> str:
    """Generate stable UUID from content hash."""
    content = f"{source}::{chunk_text}"
    hash_obj = hashlib.sha256(content.encode('utf-8'))
    return hash_obj.hexdigest()[:32]  # First 32 hex chars
```

**Что включается в hash:**
- `source`: Полный путь к PDF файлу
- `chunk_text`: Текст chunk
- Результат: Уникальный 32-символьный hex ID

### 2. Qdrant upsert behavior
```python
# Если ID существует → UPDATE existing point
# Если ID не существует → CREATE new point
qdrant_upsert(collection, chunk_id, vectors, payload)
```

---

## 📊 Примеры работы

### Сценарий 1: Первый запуск
```bash
./process-pdf.sh document.pdf
```

**Результат**:
- Chunk 1: hash `abc123...` → CREATE new point
- Chunk 2: hash `def456...` → CREATE new point
- Chunk 3: hash `789ghi...` → CREATE new point
- **Total points: 3**

### Сценарий 2: Повторный запуск (тот же PDF)
```bash
./process-pdf.sh document.pdf  # Снова!
```

**Результат**:
- Chunk 1: hash `abc123...` → UPDATE existing (content unchanged)
- Chunk 2: hash `def456...` → UPDATE existing (content unchanged)
- Chunk 3: hash `789ghi...` → UPDATE existing (content unchanged)
- **Total points: 3** ✅ (нет дубликатов!)

### Сценарий 3: Обновлённый PDF
```bash
# document.pdf изменён (Chunk 2 updated, Chunk 4 added)
./process-pdf.sh document.pdf
```

**Результат**:
- Chunk 1: hash `abc123...` → UPDATE (unchanged)
- Chunk 2: hash `NEW_HASH` → CREATE (text changed!)
- Chunk 3: hash `789ghi...` → UPDATE (unchanged)
- Chunk 4: hash `jkl012...` → CREATE (new chunk)
- **Total points: 5** (old Chunk 2 + new Chunk 2 + others)

**Примечание**: Старый Chunk 2 остаётся в базе (можно удалить вручную если нужно)

### Сценарий 4: Cross-document deduplication
```bash
./process-pdf.sh doc1.pdf
./process-pdf.sh doc2.pdf  # Содержит те же chunks
```

**Результат**:
- Если chunks идентичны → используют разные IDs (из-за `source` в hash)
- Если хочешь **глобальную дедупликацию** → убери `source` из hash

---

## 🔧 Настройка поведения

### Опция 1: Per-document deduplication (текущее)
```python
# В generate_chunk_id():
content = f"{source}::{chunk_text}"
```

**Эффект**: Одинаковые chunks из разных PDF имеют **разные ID**

**Use case**: Каждый документ независимый (Civil Code, Criminal Code)

### Опция 2: Global deduplication
```python
# Изменить в generate_chunk_id():
content = chunk_text  # Убрать source!
```

**Эффект**: Одинаковые chunks из любых PDF имеют **одинаковый ID**

**Use case**: Хочешь хранить unique chunks across all documents

### Опция 3: Versioned deduplication
```python
# Добавить timestamp в hash:
import datetime
content = f"{source}::{chunk_text}::{datetime.date.today()}"
```

**Эффект**: Каждый день создаются новые IDs

**Use case**: Tracking historical changes

---

## 🎯 Что происходит при UPDATE?

Когда Qdrant видит существующий ID:

```python
# OLD point (before update):
{
  "id": "abc123...",
  "vector": [0.1, 0.2, ...],
  "payload": {
    "text": "Article 13...",
    "contextual_prefix": "Old context",
    ...
  }
}

# NEW point (after upsert):
{
  "id": "abc123...",  # Same ID
  "vector": [0.1, 0.2, ...],  # Overwritten!
  "payload": {
    "text": "Article 13...",
    "contextual_prefix": "New context from Z.AI",  # Updated!
    ...
  }
}
```

**Всё заменяется**: vector, payload, всё!

---

## 📝 Payload теперь включает hash ID

```json
{
  "text": "Chunk text...",
  "chunk_id": "a3f5e8c9...",  // NEW! For reference/debugging
  "contextual_prefix": "Context...",
  "document": "Civil Code",
  "source": "/path/to/file.pdf",
  "chunk_index": 42
}
```

**Зачем?** Можешь найти point по hash в payload:
```python
# Search by hash
from qdrant_client.models import Filter, FieldCondition, MatchValue

client.scroll(
    collection_name="my_collection",
    scroll_filter=Filter(
        must=[
            FieldCondition(
                key="chunk_id",
                match=MatchValue(value="a3f5e8c9...")
            )
        ]
    )
)
```

---

## 🚨 Важные примечания

### ✅ Что защищено:
- **Точные дубликаты** - автоматически обновляются
- **Повторная обработка** - безопасна, создаёт 0 новых points
- **Concurrency** - SHA256 hash deterministic, нет race conditions

### ⚠️ Что НЕ защищено:
- **Minor text changes** - даже пробел изменит hash → новый point
- **Encoding differences** - UTF-8 vs CP1251 → разные hashes
- **Normalized vs raw text** - "Article  13" vs "Article 13" → разные hashes

### 💡 Best Practices:
1. **Normalize text** перед hash (lowercase, trim spaces, etc.)
2. **Use same PDF source** - разные пути → разные hashes
3. **Clean before re-process** - если хочешь fresh start:
   ```bash
   # Delete collection before re-processing
   curl -X DELETE "http://localhost:6333/collections/my_collection"
   ```

---

## 🔍 Debugging

### Проверить hash для chunk:
```python
import hashlib

chunk_text = "Your chunk text..."
source = "/path/to/file.pdf"
content = f"{source}::{chunk_text}"
hash_id = hashlib.sha256(content.encode('utf-8')).hexdigest()[:32]
print(f"Chunk ID: {hash_id}")
```

### Найти duplicate chunks:
```python
from qdrant_client import QdrantClient

client = QdrantClient(url="http://localhost:6333")

# Get all points
points = client.scroll(
    collection_name="my_collection",
    limit=10000,
    with_payload=True
)[0]

# Group by chunk_id
from collections import defaultdict
duplicates = defaultdict(list)
for point in points:
    chunk_id = point.payload.get('chunk_id')
    duplicates[chunk_id].append(point.id)

# Find duplicates
for chunk_id, point_ids in duplicates.items():
    if len(point_ids) > 1:
        print(f"Duplicate: {chunk_id} appears {len(point_ids)} times")
```

---

## 🎓 Связь с Qdrant best practices

Из [Qdrant docs](https://qdrant.tech/documentation/):

> **Point IDs can be any unique identifier**: integers, UUIDs, or strings. Using content-based IDs (like SHA256 hash) enables automatic deduplication via upsert operation.

**Преимущества content-based IDs**:
1. ✅ Idempotent writes - можно запускать pipeline много раз
2. ✅ No external ID tracking - не нужна отдельная база ID mapping
3. ✅ Automatic dedup - Qdrant делает всё сам
4. ✅ Fast lookups - hash ID = direct point access (O(1))

---

## 📚 Дополнительное чтение

- [Qdrant Upsert Documentation](https://qdrant.tech/documentation/concepts/points/#upload-points)
- [SHA256 Hash Collisions](https://en.wikipedia.org/wiki/SHA-2) - вероятность ~0 для наших данных
- [Content Addressing](https://en.wikipedia.org/wiki/Content-addressable_storage) - концепция hash-based IDs

---

**Версия**: 1.1
**Файл**: `/home/admin/contextual_rag/ingestion_contextual_kg_fast.py`
**Функция**: `generate_chunk_id()` (lines 110-134)

**Вопросы?** Проверь examples выше или запусти `./process-pdf.sh --help`
