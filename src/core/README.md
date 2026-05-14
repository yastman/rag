# core/

## Purpose

Main RAG pipeline orchestrator.
Owns the `RAGPipeline` orchestration API and `RAGResult` return contract.
Coordinates configured embedding, retrieval, contextualization, and indexing helpers.

## Files

| File | Purpose |
|------|---------|
| [`__init__.py`](./__init__.py) | Exports `RAGPipeline`, `RAGResult` |
| [`pipeline.py`](./pipeline.py) | `RAGPipeline`: orchestrates embedding, retrieval, context enrichment |

## Boundaries

- Delegates embedding to [`src/models/`](../models/)
- Delegates search to [`src/retrieval/`](../retrieval/)
- Delegates context enrichment to [`src/contextualization/`](../contextualization/)
- Uses [`src/ingestion/`](../ingestion/) helpers only for the `index_documents()` path.
- Does **not** handle transport-layer concerns (Telegram, HTTP)

## Usage

```python
from src.core import RAGPipeline

pipeline = RAGPipeline()
results = await pipeline.search("What are citizen rights?")

for result in results.results:
    print(result["text"])
```

## Focused checks

```bash
uv run pytest tests/unit/core/ -q
```

## See Also

- [`src/config/`](../config/) — Settings and constants
- [`src/retrieval/`](../retrieval/) — Search engine implementations
- [`src/contextualization/`](../contextualization/) — LLM context enrichment
