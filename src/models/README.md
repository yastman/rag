# models/

## Purpose

Embedding model singletons to prevent duplicate loading (saves 4–6 GB RAM).
Owns process-local embedding model singletons and the Voyage contextualized embedding client.
Keeps heavy ML imports lazy so normal imports do not require local model extras.

## Files

| File | Purpose |
|------|---------|
| [`__init__.py`](./__init__.py) | Exports `get_bge_m3_model`, `get_sentence_transformer` |
| [`embedding_model.py`](./embedding_model.py) | Singleton BGE-M3 (`FlagEmbedding`) and `SentenceTransformer` |
| [`contextualized_embedding.py`](./contextualized_embedding.py) | Voyage AI `voyage-context-3` contextualized embeddings client |

## Usage

```python
from src.models import get_bge_m3_model, get_sentence_transformer

# BGE-M3 with ColBERT vectors (for hybrid search)
model = get_bge_m3_model()  # Reuses single instance

# SentenceTransformer (for simple dense search)
st = get_sentence_transformer("BAAI/bge-m3")
```

## Why singletons?

- BGE-M3 consumes 4–6 GB RAM per instance
- Loading multiple times wastes memory
- `get_bge_m3_model()` ensures only one instance exists

## Boundaries

- Does not own retrieval algorithms or Qdrant search behavior.
- Does not own provider/model selection policy outside model-loading helpers.
- Local ML dependencies are optional; install the `ml-local` extra when running real local models.

## Focused checks

```bash
uv run pytest tests/unit/utils/test_embedding_model.py tests/unit/test_contextualized_embeddings.py -q
```

## See Also

- [`src/retrieval/`](../retrieval/) — Uses models for search
- [`telegram_bot/services/voyage.py`](../../telegram_bot/services/voyage.py) — Voyage AI alternative
