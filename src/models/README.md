# models/

Embedding model singletons to prevent duplicate loading (saves 4-6GB RAM).

## Files

| File | Purpose |
|------|---------|
| [\_\_init\_\_.py](./__init__.py) | Exports get_bge_m3_model, get_sentence_transformer |
| [embedding_model.py](./embedding_model.py) | Singleton BGE-M3 (FlagEmbedding) and SentenceTransformer |

## Usage

```python
from src.models import get_bge_m3_model, get_sentence_transformer

# BGE-M3 with ColBERT vectors (for hybrid search)
model = get_bge_m3_model()  # Reuses single instance

# SentenceTransformer (for simple dense search)
st = get_sentence_transformer("BAAI/bge-m3")
```

## Why Singletons?

- BGE-M3 consumes 4-6GB RAM per instance
- Loading multiple times wastes memory
- `get_bge_m3_model()` ensures only ONE instance exists

## Related

- [src/retrieval/](../retrieval/) — Uses models for search
- [telegram_bot/services/voyage.py](../../telegram_bot/services/voyage.py) — Voyage AI alternative
