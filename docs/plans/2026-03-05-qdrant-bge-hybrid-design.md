# Design: BGE-M3 Hybrid Encoding + Qdrant Improvements

**Date:** 2026-03-05
**Status:** approved
**Branch:** dev

## Problem

1. Ingestion делает 3 отдельных HTTP-вызова к BGE-M3 (dense, sparse, colbert) вместо одного `/encode/hybrid` — 3x overhead по GPU inference
2. `gdrive_documents_bge` коллекция пустая (0 points) — 13 документов не загружены
3. Apartments collection не имеет payload indexes — все фильтры идут full scan
4. Warmup BGE-M3 не прогревает ColBERT — первый запрос медленный
5. Bug: progress log в runner.py показывает `i+100` при batch=20
6. Нет тестов на regression guard для hybrid encoding

## Scope

### In Scope

| # | Приоритет | Задача | Файлы |
|---|-----------|--------|-------|
| 1 | P0 | Добавить `encode_hybrid()` в `BGEM3SyncClient` | `telegram_bot/services/bge_m3_client.py` |
| 2 | P0 | Переключить apartment ingestion на hybrid | `src/ingestion/apartments/runner.py` |
| 3 | P0 | Переключить unified ingestion на hybrid | `src/ingestion/unified/qdrant_writer.py` |
| 4 | P0 | Загрузить документы в `gdrive_documents_bge` | `make ingest-unified` (13 md файлов) |
| 5 | P1 | Создать payload indexes на apartments | `scripts/apartments/setup_collection.py` |
| 6 | P1 | Warmup с ColBERT | `services/bge-m3-api/app.py` |
| 7 | P2 | Fix progress log bug (100 -> 20) | `src/ingestion/apartments/runner.py:184` |
| 8 | P2 | Обновить legacy script | `scripts/apartments/ingest.py` |
| 9 | P0 | Тесты на всё | `tests/unit/`, `tests/integration/` |

### Out of Scope (YAGNI)

- Переименование `bm42` -> `sparse` (breaking change, миграция коллекций)
- Binary quantization (297 points — нет смысла)
- `upload_points` вместо `upsert` (не тот масштаб)
- Batching в async `encode_hybrid` (query-time — single text)

## Architecture

### Current Flow (3 calls)

```
Ingestion → BGEM3SyncClient.encode_dense()   → POST /encode/dense   → model.encode(return_dense=True)
          → BGEM3SyncClient.encode_sparse()  → POST /encode/sparse  → model.encode(return_sparse=True)
          → BGEM3SyncClient.encode_colbert() → POST /encode/colbert → model.encode(return_colbert=True)
```

3 HTTP requests, 3 model forward passes.

### Target Flow (1 call)

```
Ingestion → BGEM3SyncClient.encode_hybrid() → POST /encode/hybrid → model.encode(
                                                                       return_dense=True,
                                                                       return_sparse=True,
                                                                       return_colbert_vecs=True
                                                                     )
```

1 HTTP request, 1 model forward pass. API endpoint `/encode/hybrid` уже существует.

### Payload Indexes

```
apartments collection:
  keyword: city, complex_name, view_primary, section
  integer: rooms, floor
  float:   price_eur, area_m2
  bool:    is_promotion
```

Создаются через `qdrant_client.create_payload_index()` в setup script.

## Implementation Details

### 1. BGEM3SyncClient.encode_hybrid()

```python
# telegram_bot/services/bge_m3_client.py
class BGEM3SyncClient:
    def encode_hybrid(self, texts: list[str]) -> HybridResult:
        """Single call for dense + sparse + colbert vectors."""
        resp = self._session.post(
            f"{self.base_url}/encode/hybrid",
            json={"texts": texts, "max_length": self.max_length},
        )
        resp.raise_for_status()
        data = resp.json()
        return HybridResult(
            dense_vecs=data["dense_vecs"],
            lexical_weights=data["lexical_weights"],
            colbert_vecs=data.get("colbert_vecs"),
            processing_time=data.get("processing_time"),
        )
```

### 2. Runner.py refactor

```python
# До: 3 вызова
dense = self.bge_client.encode_dense(texts)
sparse = self.bge_client.encode_sparse(texts)
colbert = self.bge_client.encode_colbert(texts)

# После: 1 вызов
result = self.bge_client.encode_hybrid(texts)
dense = result.dense_vecs
sparse = result.lexical_weights
colbert = result.colbert_vecs
```

### 3. Warmup fix

```python
# services/bge-m3-api/app.py, lifespan
embeddings = model.encode(
    ["warmup query"],
    return_dense=True,
    return_sparse=True,
    return_colbert_vecs=True,  # was False
)
```

## Testing Strategy

### Unit Tests (новые)

| Тест | Файл | Что проверяет |
|------|------|---------------|
| `test_sync_encode_hybrid_happy_path` | `tests/unit/services/test_bge_m3_client.py` | Один вызов → HybridResult с dense+sparse+colbert |
| `test_sync_encode_hybrid_empty_input` | same | Пустой список → пустой результат |
| `test_sync_encode_hybrid_http_error` | same | HTTP 500 → raise |
| `test_runner_uses_hybrid_call` | `tests/unit/ingestion/test_apartment_runner.py` | Mock: encode_hybrid вызывается 1 раз, encode_dense/sparse/colbert — 0 раз |
| `test_qdrant_writer_uses_hybrid` | `tests/unit/ingestion/test_qdrant_writer_behavior.py` | Same regression guard для unified ingestion |
| `test_payload_indexes_created` | `tests/unit/ingestion/test_apartment_setup.py` | Setup script создаёт все 9 indexes |
| `test_progress_log_batch_size` | `tests/unit/ingestion/test_apartment_runner.py` | Проверка что log message соответствует batch size |

### Integration Tests

| Тест | Файл | Что проверяет |
|------|------|---------------|
| `test_apartments_vectors_all_present` | `tests/integration/test_apartments_ingestion.py` | Каждый point имеет dense + bm42 + colbert |
| `test_apartments_payload_indexes_exist` | same | Collection info показывает 9 payload indexes |
| `test_gdrive_documents_ingested` | `tests/integration/test_unified_ingestion_e2e.py` | После ingestion > 0 points с правильными векторами |

### Regression Guards

- Mock-тест: если ingestion вызывает `encode_dense`/`encode_sparse`/`encode_colbert` по отдельности → FAIL
- Это гарантирует что никто не откатит hybrid на 3 отдельных вызова

## Risks

| Риск | Митигация |
|------|-----------|
| `/encode/hybrid` возвращает другой формат sparse | Уже используется в async клиенте — формат проверен |
| Payload indexes замедляют upsert | 297 points — незначительно, indexes O(log n) |
| `make ingest-unified` падает на md файлах | Pipeline уже поддерживает markdown через Docling |

## Success Criteria

1. `BGEM3SyncClient.encode_hybrid()` работает, возвращает все 3 типа векторов
2. Ingestion (apartments + unified) делает 1 HTTP вызов вместо 3
3. `gdrive_documents_bge` содержит > 0 points после ingestion
4. Apartments collection имеет 9 payload indexes
5. Все новые и существующие тесты проходят
6. `make check` (ruff + mypy) clean
