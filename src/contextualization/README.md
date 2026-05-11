# contextualization/

LLM-based context enrichment for document chunks (+2-5% Recall improvement).

## Ownership

- Owns contextualization provider interfaces and Claude/OpenAI/Groq implementations.
- Produces `ContextualizedChunk` objects used by RAG and ingestion paths.

## Files

| File | Purpose |
|------|---------|
| [\_\_init\_\_.py](./__init__.py) | Exports ContextualizeProvider, ClaudeContextualizer, etc. |
| [base.py](./base.py) | Abstract base class and ContextualizedChunk dataclass |
| [claude.py](./claude.py) | Claude API contextualizer (recommended) |
| [openai.py](./openai.py) | OpenAI GPT contextualizer |
| [groq.py](./groq.py) | Groq LLaMA contextualizer (fast, free tier) |

## What is Contextualization?

Adds LLM-generated summaries to document chunks before indexing:

```
Original: "Особа звільняється від кримінальної відповідальності..."

Contextualized: "Стаття 45 КК України. Звільнення від кримінальної
відповідальності у зв'язку з дійовим каяттям. Особа звільняється..."
```

## Usage

```python
from src.contextualization import ClaudeContextualizer
from src.config import APIProvider, Settings

settings = Settings(api_provider=APIProvider.CLAUDE)  # Reads provider keys from env.
contextualizer = ClaudeContextualizer(settings=settings)
enriched = await contextualizer.contextualize(["chunk text"], query="optional query")
```

## Boundaries

- Does not own retrieval, ranking, or Qdrant writes.
- Does not own embedding generation; see [`src/models/`](../models/).
- API keys and provider selection come from [`src/config/`](../config/) or caller-provided settings.

## Performance Impact

- +2-5% improvement in Recall@1
- +0.5-1% improvement in NDCG@10
- Cost: ~$0.01/chunk (Claude)

## Focused checks

```bash
uv run pytest tests/unit/contextualization/ -q
```

## Related

- [src/core/pipeline.py](../core/pipeline.py) — Uses contextualizers in RAG pipeline
- [src/ingestion/](../ingestion/) — Document chunking before contextualization
