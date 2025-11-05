# Redis Caching - Полная Документация

## Обзор

RAG-система использует 4-уровневую архитектуру кеширования на базе Redis Stack для оптимизации производительности и снижения затрат на API.

## Архитектура

```
┌─────────────────────────────────────────────────────────┐
│                   USER QUERY                            │
└───────────────────┬─────────────────────────────────────┘
                    │
        ┌───────────▼──────────┐
        │   TIER 1: CRITICAL   │
        ├──────────────────────┤
        │ 1. Semantic Cache    │ ◄── Redis Vector Search (KNN)
        │    (LLM answers)     │     COSINE similarity, threshold=0.85
        │                      │     TTL: 48h, Latency: 1-5ms
        │ 2. Embeddings Cache  │ ◄── BGE-M3 vectors cache
        │    (query vectors)   │     TTL: 7d, Speedup: 1000x
        └──────────────────────┘
                    │
        ┌───────────▼──────────┐
        │   TIER 2: MEDIUM     │
        ├──────────────────────┤
        │ 3. Analyzer Cache    │ ◄── Query filters & metadata
        │    (QueryAnalyzer)   │     TTL: 24h, Latency: ~0.5ms
        │                      │
        │ 4. Search Cache      │ ◄── Qdrant search results
        │    (Qdrant results)  │     TTL: 2h, Latency: ~0.7ms
        └──────────────────────┘
```

## Tier 1: Critical Caching

### 1. Semantic Cache (LLM Answers)

**Назначение:** Кеширование финальных ответов LLM с использованием векторного поиска

**Технология:** Redis Vector Search (RediSearch module)

**Ключевые особенности:**
- ✅ **Истинный семантический поиск** - разные формулировки одного вопроса приводят к HIT
- ✅ **KNN алгоритм** - поиск K ближайших соседей (K=1)
- ✅ **COSINE метрика** - измерение семантической близости векторов
- ✅ **Threshold 0.85** - минимальное сходство для HIT (85%)

**Пример работы:**
```
Запрос 1: "Какие квартиры в базе?"
  → Embedding: [0.1, 0.5, 0.3, ..., 0.7] (1024-dim)
  → Store: rag:semantic:abc123 → "Найдено 50 квартир..."
  → TTL: 48h

Запрос 2: "В базе какие у нас квартиры"
  → Embedding: [0.11, 0.51, 0.29, ..., 0.69]
  → KNN Search → cosine_similarity = 0.92
  → similarity (0.92) > threshold (0.85) → HIT ✅
  → Return: "Найдено 50 квартир..." (без вызова LLM!)
```

**Redis команды:**
```redis
# Создание индекса
FT.CREATE idx:rag:semantic_cache
  ON HASH PREFIX 1 rag:semantic:
  SCHEMA
    query_vector VECTOR FLAT 6 TYPE FLOAT32 DIM 1024 DISTANCE_METRIC COSINE
    answer TEXT
    timestamp NUMERIC

# KNN поиск
FT.SEARCH idx:rag:semantic_cache
  "*=>[KNN 1 @query_vector $vec AS score]"
  PARAMS 2 vec <vector_bytes>
  RETURN 2 answer score
```

**Хранение:**
```python
key = f"rag:semantic:{hash(query)}"
mapping = {
    "query_vector": np.array(embedding, dtype=np.float32).tobytes(),
    "answer": llm_answer,
    "timestamp": int(time.time()),
    "query": original_query
}
redis.hset(key, mapping=mapping)
redis.expire(key, 48 * 3600)
```

**Производительность:**
- Latency: 1-5ms
- Hit Rate: зависит от threshold и разнообразия запросов
- Экономия: ~$0.002-0.01 на вызов LLM

### 2. Embeddings Cache (Query Vectors)

**Назначение:** Кеширование векторов запросов от BGE-M3

**Ускорение:** 1000x (5 секунд → 0.005 секунды)

**Хранение:**
```python
key = f"rag:emb:v1:{hash(text)}"
redis.setex(key, 7 * 24 * 3600, json.dumps(embedding))
```

**Производительность:**
- TTL: 7 дней (долгосрочное кеширование)
- Hit Rate: обычно 70-90% для повторяющихся запросов
- Экономия: ~5 секунд на вызов BGE-M3 API

## Tier 2: Medium Caching

### 3. QueryAnalyzer Cache

**Назначение:** Кеширование результатов анализа запросов (фильтры, метаданные)

**Хранение:**
```python
key = f"rag:analysis:v1:{hash(query)}"
analysis = {
    "filters": {"city": "София", "price_max": 150000},
    "semantic_query": "апартамент"
}
redis.setex(key, 24 * 3600, json.dumps(analysis))
```

**Производительность:**
- TTL: 24 часа
- Latency: ~0.5ms
- Hit Rate: 30-50% (зависит от разнообразия запросов)

### 4. Search Cache (Qdrant Results)

**Назначение:** Кеширование результатов векторного поиска в Qdrant

**Ключ:** Комбинация embedding + filters + index_version
```python
embedding_hash = hash(str(embedding[:10]))
filters_hash = hash(json.dumps(filters, sort_keys=True))
key = f"rag:search:v1:{index_version}:{embedding_hash}:{filters_hash}"
```

**Производительность:**
- TTL: 2 часа (короткий, т.к. данные в Qdrant могут обновляться)
- Latency: ~0.7ms
- Hit Rate: 40-60%

## Конфигурация

```python
cache_service = CacheService(
    redis_url="redis://:password@redis:6379",
    semantic_cache_ttl=48 * 3600,        # 48 часов
    embeddings_cache_ttl=7 * 24 * 3600,  # 7 дней
    analyzer_cache_ttl=24 * 3600,        # 24 часа
    search_cache_ttl=2 * 3600,           # 2 часа
    distance_threshold=0.85,              # 85% сходства для semantic cache
)
```

## Метрики

### Автоматический сбор метрик

```python
metrics = cache_service.get_metrics()
# {
#     "by_type": {
#         "semantic": {"hits": 10, "misses": 5, "hit_rate": 66.7},
#         "embeddings": {"hits": 50, "misses": 10, "hit_rate": 83.3},
#         "analyzer": {"hits": 20, "misses": 15, "hit_rate": 57.1},
#         "search": {"hits": 30, "misses": 20, "hit_rate": 60.0}
#     },
#     "total_hits": 110,
#     "total_misses": 50,
#     "total_requests": 160,
#     "overall_hit_rate": 68.8
# }
```

### Логирование

```python
cache_service.log_metrics()
# Cache Metrics: 68.8% hit rate, 160 requests
#   semantic: 66.7% (10/15)
#   embeddings: 83.3% (50/60)
#   analyzer: 57.1% (20/35)
#   search: 60.0% (30/50)
```

## Мониторинг

### Просмотр логов

```bash
# Все события кеширования
docker logs telegram-rag-bot -f | grep -E '(cache|Cache)'

# Только HIT события
docker logs telegram-rag-bot -f | grep "cache HIT"

# Только semantic cache
docker logs telegram-rag-bot -f | grep "Semantic cache"
```

### Проверка Redis

```bash
# Количество ключей по типам
docker exec ai-redis-secure redis-cli -a $REDIS_PASSWORD --no-auth-warning KEYS "rag:semantic:*" | wc -l
docker exec ai-redis-secure redis-cli -a $REDIS_PASSWORD --no-auth-warning KEYS "rag:emb:*" | wc -l
docker exec ai-redis-secure redis-cli -a $REDIS_PASSWORD --no-auth-warning KEYS "rag:analysis:*" | wc -l
docker exec ai-redis-secure redis-cli -a $REDIS_PASSWORD --no-auth-warning KEYS "rag:search:*" | wc -l

# Информация о векторном индексе
docker exec ai-redis-secure redis-cli -a $REDIS_PASSWORD --no-auth-warning FT.INFO idx:rag:semantic_cache

# Пример записи
KEY=$(docker exec ai-redis-secure redis-cli -a $REDIS_PASSWORD --no-auth-warning KEYS "rag:semantic:*" | head -1)
docker exec ai-redis-secure redis-cli -a $REDIS_PASSWORD --no-auth-warning HGETALL "$KEY"
```

## Тестирование

### Автоматические тесты

```bash
cd /srv/contextual_rag
docker exec -e BGE_M3_URL=http://bge-m3-api:8000 telegram-rag-bot python test_cache.py
```

### Ручное тестирование через Telegram

1. **Test Semantic Cache:**
   ```
   Запрос 1: "Какие квартиры в базе?"
   → MISS (новый запрос, LLM генерирует ответ)

   Запрос 2: "Какие квартиры в базе?"
   → HIT similarity=1.000 (точное совпадение)

   Запрос 3: "В базе какие у нас квартиры"
   → HIT similarity=0.92 (семантически похож)
   ```

2. **Test Embeddings Cache:**
   ```
   Запрос 1: любой новый запрос
   → Embedding генерируется (~5 секунд)

   Запрос 2: тот же запрос
   → Embedding из кеша (0.005 секунды) ⚡
   ```

## Настройка Threshold

### Текущий: 0.85 (85% сходства)

**Слишком высокий (0.90-1.0):**
- Много MISS для похожих запросов
- Меньше экономии на LLM

**Оптимальный (0.80-0.90):**
- Баланс между точностью и hit rate
- Рекомендуется 0.85

**Слишком низкий (0.60-0.80):**
- Риск возврата нерелевантного ответа
- Больше ложных HIT

### Изменение threshold

```python
# В telegram_bot/services/cache.py
cache_service = CacheService(
    redis_url=redis_url,
    distance_threshold=0.80  # Изменить здесь
)
```

## Troubleshooting

### Semantic Cache не работает

1. **Проверить Redis Stack:**
   ```bash
   docker exec ai-redis-secure redis-cli -a $REDIS_PASSWORD --no-auth-warning MODULE LIST
   # Должен быть: search (RediSearch)
   ```

2. **Проверить индекс:**
   ```bash
   docker exec ai-redis-secure redis-cli -a $REDIS_PASSWORD --no-auth-warning FT.INFO idx:rag:semantic_cache
   # Должно быть: num_docs > 0
   ```

3. **Проверить логи:**
   ```bash
   docker logs telegram-rag-bot | grep "Semantic cache"
   ```

### Низкий Hit Rate

1. **Проверить метрики:**
   ```python
   cache_service.log_metrics()
   ```

2. **Уменьшить threshold (если semantic cache):**
   ```python
   distance_threshold=0.80  # Было 0.85
   ```

3. **Увеличить TTL:**
   ```python
   semantic_cache_ttl=72 * 3600  # Было 48h
   ```

### Проблемы с памятью Redis

```bash
# Проверить использование памяти
docker exec ai-redis-secure redis-cli -a $REDIS_PASSWORD --no-auth-warning INFO memory

# Очистить старые ключи вручную
docker exec ai-redis-secure redis-cli -a $REDIS_PASSWORD --no-auth-warning FLUSHDB
```

## Best Practices

1. **Мониторить hit rate** - должен быть > 50%
2. **Логировать метрики** - каждые 100 запросов
3. **Настраивать threshold** - на основе production данных
4. **Очищать кеш** - при изменении данных в Qdrant
5. **Резервное копирование** - Redis RDB для важных кешей

## Ссылки

- [SEMANTIC_CACHE_COMPARISON.md](./SEMANTIC_CACHE_COMPARISON.md) - Сравнение подходов
- [RediSearch Documentation](https://redis.io/docs/stack/search/)
- [BGE-M3 Model](https://huggingface.co/BAAI/bge-m3)
