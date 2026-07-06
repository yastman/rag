# src/retrieval/

Reranking and topic-classification helpers for retrieval. Production hybrid search itself
lives in `src.runtime` (`QdrantService` + `RetrievalService`); this package holds the
cross-encoder reranker and a lightweight topic classifier used to tune retrieval. It does
**not** export search engine classes — the old `create_search_engine` benchmark variants
were removed; `__init__.py` only marks the package.

## Files

| File | Purpose |
|------|---------|
| [`__init__.py`](./__init__.py) | Package exports |
| [`reranker.py`](./reranker.py) | Cross-encoder reranking (+NDCG on the top-k) |
| [`topic_classifier.py`](./topic_classifier.py) | Lightweight topic / doc-type classification for retrieval tuning |

## Boundaries

- Retrieval code is **query-only** — it must not write to Qdrant or modify collections.
- Production runtime retrieval uses `src.runtime.retrieval.RetrievalService` over `src.runtime.qdrant.QdrantService`.
- `topic_classifier.py` is advisory only; retrieval must still work when it returns `None`.
- Score shapes / payload fields are coupled to [`../ingestion/unified/qdrant_writer.py`](../ingestion/unified/qdrant_writer.py); if the ingestion payload contract changes, reranking/parsing may need updates.

## Focused Checks

```bash
make check
pytest src/retrieval/
```

## See Also

- [`../runtime/qdrant/service.py`](../runtime/qdrant/service.py) — production Qdrant search gateway
- [`../ingestion/`](../ingestion/) — chunk production and payload contract
- [`../../docs/LOCAL-DEVELOPMENT.md`](../../docs/LOCAL-DEVELOPMENT.md) — local setup and validation ladder
