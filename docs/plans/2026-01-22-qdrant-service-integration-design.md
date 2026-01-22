***REMOVED***Service Integration Design

**Дата:** 22 января 2026
**Статус:** Ready for implementation
**Исследование:** Exa MCP (Elastic Labs, Qdrant Blog)

---

## Цель

Заменить legacy `RetrieverService` (sync, dense-only) на `QdrantService` с полным набором возможностей:
- Hybrid RRF (dense + sparse BM42)
- Score Boosting (freshness)
- MMR diversity reranking

## Архитектура

### До (legacy)

```
Query → VoyageService.embed_query() → RetrieverService.search() → Rerank → LLM
                                            ↓
                                    (sync, dense-only)
```

### После (native)

```
Query → VoyageService.embed_query() ─┐
      → FastEmbed BM42 ──────────────┼→ QdrantService.hybrid_search_rrf()
                                     │         ↓
                                     │   Score Boosting (exp_decay)
                                     │         ↓
                                     └→ QdrantService.mmr_rerank()
                                              ↓
                                         VoyageService.rerank() → LLM
```

---

## Компоненты

### 1. FastEmbed для BM42 sparse vectors

```python
from fastembed import SparseTextEmbedding

class SparseEmbedder:
    """Generate BM42 sparse vectors for queries."""

    def __init__(self):
        self.model = SparseTextEmbedding(
            model_name="Qdrant/bm42-all-minilm-l6-v2-attentions"
        )

    def embed(self, text: str) -> dict:
        """Return sparse vector as {indices: [...], values: [...]}."""
        result = list(self.model.embed([text]))[0]
        return {
            "indices": result.indices.tolist(),
            "values": result.values.tolist()
        }
```

**Размер модели:** ~50MB (скачивается при первом запуске)

### 2. QdrantService (уже реализован)

Методы:
- `hybrid_search_rrf(dense_vector, sparse_vector, filters, top_k)`
- `search_with_score_boosting(dense_vector, freshness_boost, freshness_field)`
- `mmr_rerank(points, embeddings, lambda_mult, top_k)`

### 3. Конфигурация

```python
# config.py - новые параметры
class BotConfig:
    # Search Configuration
    search_top_k: int = int(os.getenv("SEARCH_TOP_K", "50"))
    rerank_top_k: int = int(os.getenv("RERANK_TOP_K", "5"))

    # Hybrid Search
    hybrid_dense_weight: float = float(os.getenv("HYBRID_DENSE_WEIGHT", "0.6"))
    hybrid_sparse_weight: float = float(os.getenv("HYBRID_SPARSE_WEIGHT", "0.4"))

    # Score Boosting
    freshness_boost_enabled: bool = os.getenv("FRESHNESS_BOOST", "true").lower() == "true"
    freshness_field: str = os.getenv("FRESHNESS_FIELD", "created_at")
    freshness_scale_days: int = int(os.getenv("FRESHNESS_SCALE_DAYS", "30"))

    # MMR Diversity
    mmr_enabled: bool = os.getenv("MMR_ENABLED", "true").lower() == "true"
    mmr_lambda: float = float(os.getenv("MMR_LAMBDA", "0.7"))
```

---

## Изменения в bot.py

### Инициализация

```python
from fastembed import SparseTextEmbedding

class PropertyBot:
    def __init__(self, config: BotConfig):
        # ... existing services ...

        # Replace RetrieverService with QdrantService
        self.qdrant_service = QdrantService(
            url=config.qdrant_url,
            api_key=config.qdrant_api_key,
            collection_name=config.qdrant_collection,
        )

        # BM42 sparse embedder for hybrid search
        self.sparse_embedder = SparseTextEmbedding(
            model_name="Qdrant/bm42-all-minilm-l6-v2-attentions"
        )
```

### Поиск (handle_query)

```python
async def handle_query(self, message: Message):
    # ... query analysis ...

    # 1. Generate embeddings
    query_vector = await self.voyage_service.embed_query(query)
    sparse_vector = self._get_sparse_vector(query)

    # 2. Hybrid search with RRF
    results = await self.qdrant_service.hybrid_search_rrf(
        dense_vector=query_vector,
        sparse_vector=sparse_vector,
        filters=filters,
        top_k=self.config.search_top_k,
        dense_weight=self.config.hybrid_dense_weight,
        sparse_weight=self.config.hybrid_sparse_weight,
    )

    # 3. MMR diversity reranking (if enabled)
    if self.config.mmr_enabled and len(results) > self.config.rerank_top_k:
        # Get embeddings for MMR
        result_texts = [r["text"] for r in results]
        result_embeddings = await self.voyage_service.embed_documents(result_texts)

        results = self.qdrant_service.mmr_rerank(
            points=results,
            embeddings=result_embeddings,
            lambda_mult=self.config.mmr_lambda,
            top_k=self.config.rerank_top_k * 2,  # Keep more for Voyage rerank
        )

    # 4. Voyage rerank (final precision)
    if results and len(results) > 1:
        doc_texts = [r["text"] for r in results]
        rerank_results = await self.voyage_service.rerank(
            query=query,
            documents=doc_texts,
            top_k=self.config.rerank_top_k,
        )
        results = [results[r["index"]] for r in rerank_results]

    # ... continue with LLM ...

def _get_sparse_vector(self, text: str) -> dict:
    """Generate BM42 sparse vector for query."""
    result = list(self.sparse_embedder.embed([text]))[0]
    return {
        "indices": result.indices.tolist(),
        "values": result.values.tolist(),
    }
```

---

## Score Boosting (будущее)

Когда в payload появится `created_at`:

```python
# Вместо hybrid_search_rrf использовать:
results = await self.qdrant_service.search_with_score_boosting(
    dense_vector=query_vector,
    filters=filters,
    top_k=self.config.search_top_k,
    freshness_boost=self.config.freshness_boost_enabled,
    freshness_field=self.config.freshness_field,
    freshness_scale_days=self.config.freshness_scale_days,
)
```

**Graceful fallback:** Если поле не найдено, буст не применяется (уже реализовано в QdrantService).

---

## Удаление legacy кода

### Файлы удалены (✅ сделано)
- `telegram_bot/services/voyage_client.py`
- `telegram_bot/services/voyage_embeddings.py`
- `telegram_bot/services/voyage_reranker.py`
- `telegram_bot/services/hybrid_retriever.py`

### Файлы для удаления после миграции
- `telegram_bot/services/retriever.py` — заменён на QdrantService

---

## Зависимости

```toml
# pyproject.toml - добавить
fastembed = ">=0.3.0"
```

**Размер:** ~50MB (BM42 модель скачивается при первом запуске)

---

## Тестирование

### Unit тесты (уже есть)
- `tests/test_qdrant_service.py` — 11 тестов
- `tests/test_voyage_service.py` — 20 тестов

### Integration тесты (добавить)
```python
@pytest.mark.asyncio
async def test_hybrid_search_e2e():
    """Test full hybrid search pipeline."""
    # 1. Create QdrantService
    # 2. Generate dense + sparse vectors
    # 3. Execute hybrid_search_rrf
    # 4. Apply MMR
    # 5. Verify results diversity
```

---

## Метрики успеха

| Метрика | До | После (ожидание) |
|---------|-----|------------------|
| Recall@5 | ~85% | ~92% (hybrid) |
| Diversity | низкая | +20% (MMR) |
| Latency | ~200ms | ~250ms (+BM42) |

---

## План реализации

1. **Добавить FastEmbed** в зависимости
2. **Обновить bot.py** — заменить RetrieverService на QdrantService
3. **Добавить конфиг** — параметры hybrid/MMR
4. **Тесты** — integration test
5. **Удалить** retriever.py после проверки

---

**Validated by:** Exa MCP Research (January 2026)
- Elastic Labs: MMR best practices
- Qdrant Blog: Diversity-aware reranking
