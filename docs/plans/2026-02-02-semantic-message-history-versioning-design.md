# SemanticMessageHistory Schema Mismatch Fix

**Date:** 2026-02-02
**Status:** Implemented
**Branch:** milestone/h-guardrails

## Problem

При старте dev-bot возникает ошибка:
```
Existing index rag_conversations schema does not match ...
```

Причина: `SemanticMessageHistory` использовал фиксированное имя `"rag_conversations"` без версии. При изменении схемы или vectorizer'а возникает конфликт.

## Solution (Variant A - Versioned Index Name)

Имя индекса включает версию и vectorizer:
```
rag_conversations:{CACHE_SCHEMA_VERSION}:{vectorizer_id}
```

**Примеры:**
- `rag_conversations:v2:userbase768` — для `USE_LOCAL_EMBEDDINGS=true`
- `rag_conversations:v2:voyage1024` — для Voyage API

## Implementation

### File: `telegram_bot/services/cache.py`

**Строка 29-34 (комментарий):**
```python
# Cache versioning - bump when changing cache structure or models
# NOTE: SemanticMessageHistory index is versioned as:
#   rag_conversations:{CACHE_SCHEMA_VERSION}:{vectorizer_id}
#   e.g. rag_conversations:v2:userbase768 or rag_conversations:v2:voyage1024
# Old indices are NOT deleted automatically; clean up manually if needed.
CACHE_SCHEMA_VERSION = "v2"
```

**Строки 215-223 (USE_LOCAL_EMBEDDINGS=true):**
```python
history_index_name = (
    f"rag_conversations:{CACHE_SCHEMA_VERSION}:{self._get_vectorizer_id()}"
)
self.message_history = SemanticMessageHistory(
    name=history_index_name,
    ...
)
```

**Строки 231-242 (Voyage API):**
```python
history_index_name = (
    f"rag_conversations:{CACHE_SCHEMA_VERSION}:{self._get_vectorizer_id()}"
)
self.message_history = SemanticMessageHistory(
    name=history_index_name,
    ...
)
```

## Verification

### 1. Logs (docker logs dev-bot)

**Expected:**
```
✓ SemanticMessageHistory initialized (rag_conversations:v2:voyage1024)
```

**Should NOT contain:**
```
schema does not match
```

### 2. Redis indices

```bash
docker exec dev-redis redis-cli FT._LIST
```

**Expected:** Contains index with pattern `rag_conversations:v2:*`

## Not Done (Explicit)

- `overwrite=True` по умолчанию — НЕТ
- Автоматическое удаление старого `rag_conversations` — НЕТ
- Миграция существующих данных — НЕТ (старые индексы expire естественным путём)

## Cleanup (Manual)

При необходимости удалить старые индексы вместе с документами (DD flag):
```bash
# DD = Delete Documents (удаляет и индекс, и данные)
docker exec dev-redis redis-cli FT.DROPINDEX rag_conversations DD
docker exec dev-redis redis-cli FT.DROPINDEX "rag_conversations:v2" DD
```

**Без DD** — удаляется только индекс, документы остаются в Redis.
