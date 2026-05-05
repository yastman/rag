# config/

Central configuration for the RAG pipeline: settings, constants, and Qdrant policy.

## Files

| File | Purpose |
|------|---------|
| [`__init__.py`](./__init__.py) | Exports `Settings`, `APIProvider`, `SearchEngine`, etc. |
| [`settings.py`](./settings.py) | `Settings` class: loads from `.env`, constructor args, defaults |
| [`constants.py`](./constants.py) | Enums (`SearchEngine`, `APIProvider`, `ModelName`) and dataclasses |
| [`qdrant_policy.py`](./qdrant_policy.py) | Collection-level Qdrant configuration rules |

## Usage

```python
from src.config import Settings, APIProvider, SearchEngine

settings = Settings()
print(settings.qdrant_url)  # http://localhost:6333

# Override via constructor
settings = Settings(
    api_provider=APIProvider.OPENAI,
    qdrant_url="https://qdrant.example.com"
)
```

## Focused checks

```bash
uv run pytest tests/unit/config/ -q
```

## Related

- [`.env.example`](../../.env.example) — Environment variables template
- [`src/core/pipeline.py`](../core/pipeline.py) — Uses `Settings` for pipeline config
