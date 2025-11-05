# Semantic Cache - Сравнение подходов

## Проблема
```
Запрос 1: "Какие квартиры в базе?"
Запрос 2: "В базе какие у нас квартиры"
→ Смысл одинаковый, но разные хеши → MISS в hash-based кеше
```

## Варианты решения

### 1. Hash-based (текущий) ❌
```python
key = hash(embedding_vector)
```

**Плюсы:**
- Быстрый (O(1) lookup)
- Простая реализация
- Не требует зависимостей

**Минусы:**
- ❌ НЕ semantic - разные формулировки = разные хеши
- ❌ Не находит похожие вопросы
- ❌ Низкий hit rate

**Пример:**
```
"Какие квартиры?" → hash_abc → ответ
"Покажи квартиры" → hash_xyz → MISS (хотя смысл тот же)
```

---

### 2. Redis Vector Search (RediSearch) ✅ РЕКОМЕНДУЕТСЯ
```python
# Создаем векторный индекс
FT.CREATE idx:semantic SCHEMA
  vector VECTOR FLAT 6 TYPE FLOAT32 DIM 1024 DISTANCE_METRIC COSINE

# KNN поиск
FT.SEARCH idx:semantic "*=>[KNN 1 @vector $vec]"
```

**Плюсы:**
- ✅ Настоящий semantic search (cosine similarity)
- ✅ Redis Stack УЖЕ установлен (у вас есть!)
- ✅ Быстрый (оптимизированный C-код)
- ✅ Без дополнительных зависимостей
- ✅ TTL поддержка из коробки

**Минусы:**
- Чуть сложнее реализация (но я уже начал!)

**Пример:**
```
Store: "Какие квартиры?" → vector [0.1, 0.5, ...] → ответ
Search: "Покажи квартиры" → vector [0.11, 0.51, ...]
→ cosine similarity = 0.92 > 0.85 → HIT! ✅
```

**Производительность:**
- Поиск: ~1-5ms для 1000 записей
- Масштабируется до миллионов векторов

---

### 3. RedisVL SemanticCache ⚠️
```python
from redisvl.extensions.cache.llm import SemanticCache

cache = SemanticCache(
    redis_url=redis_url,
    vectorizer=HFTextVectorizer()  # требует sentence-transformers
)
```

**Плюсы:**
- ✅ Высокоуровневый API
- ✅ Semantic search из коробки

**Минусы:**
- ❌ Требует `sentence-transformers` (~1GB)
- ❌ Дублирование: у нас уже есть BGE-M3 API
- ❌ Загружает модель в память (~500MB RAM)
- ⚠️ Медленнее (Python embedding vs внешний API)

**Вердикт:** Избыточно, т.к. у нас уже есть BGE-M3

---

### 4. Python cosine similarity (numpy) 🐌
```python
# Загрузить все векторы из Redis
vectors = [redis.get(f"cache:{i}") for i in range(1000)]
# Вычислить cosine similarity в Python
similarities = [cosine(query_vec, v) for v in vectors]
best = max(similarities)
```

**Плюсы:**
- Простая реализация
- Не требует индексов

**Минусы:**
- ❌ ОЧЕНЬ медленно (O(N) для каждого запроса)
- ❌ Нужно загружать все векторы в память
- ❌ Не масштабируется (>100 записей = проблемы)

**Вердикт:** Непригодно для production

---

## Итоговая таблица

| Критерий | Hash-based | Redis Vector | RedisVL | Python numpy |
|----------|-----------|--------------|---------|--------------|
| **Semantic search** | ❌ Нет | ✅ Да | ✅ Да | ✅ Да |
| **Скорость** | ⚡ 0.1ms | ⚡ 1-5ms | ⚠️ 10-50ms | 🐌 50-500ms |
| **Зависимости** | ✅ Нет | ✅ Нет (уже есть) | ❌ +1GB | ✅ numpy |
| **Память** | ✅ Мало | ✅ Мало | ❌ +500MB | ⚠️ Все векторы |
| **Масштабируемость** | ✅ Отлично | ✅ Отлично | ✅ Хорошо | ❌ Плохо |
| **Hit rate** | ❌ Низкий | ✅ Высокий | ✅ Высокий | ✅ Высокий |
| **TTL** | ✅ Да | ✅ Да | ✅ Да | ⚠️ Вручную |

---

## Рекомендация: Redis Vector Search ✅

**Почему:**
1. Redis Stack УЖЕ установлен у вас (RediSearch 80201 ✅)
2. Нативный semantic search (cosine similarity)
3. Быстро (~1-5ms)
4. Без лишних зависимостей
5. Легко интегрируется с текущим кодом

**Пример работы:**
```python
# 1. Сохранение
query = "Какие квартиры в базе?"
embedding = [0.1, 0.5, ...] # 1024-dim от BGE-M3
answer = "Найдено 50 квартир..."

redis.hset("rag:semantic:abc123", mapping={
    "query_vector": embedding.tobytes(),
    "answer": answer,
    "timestamp": time.time()
})

# 2. Поиск похожего
new_query = "Покажи квартиры в базе"
new_embedding = [0.11, 0.51, ...] # чуть другой вектор

result = FT.SEARCH "idx:semantic" "*=>[KNN 1 @query_vector $vec]"
# → находит предыдущий ответ с similarity=0.92 ✅
```

---

## Реализация

Я уже начал реализацию Redis Vector Search в `cache.py`:
- ✅ Создание индекса `_create_semantic_index()`
- ✅ KNN поиск в `check_semantic_cache()`
- 🔄 Нужно доделать `store_semantic_cache()`

**Следующий шаг:** Завершить реализацию и протестировать с реальными запросами.
