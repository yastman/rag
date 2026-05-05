***REMOVED*** core/

Main RAG pipeline orchestrator.

***REMOVED******REMOVED*** Files

| File | Purpose |
|------|---------|
| [`__init__.py`](./__init__.py) | Exports `RAGPipeline`, `RAGResult` |
| [`pipeline.py`](./pipeline.py) | `RAGPipeline`: orchestrates embedding, retrieval, context enrichment |

***REMOVED******REMOVED*** Boundaries

- Delegates embedding to [`src/models/`](../models/)
- Delegates search to [`src/retrieval/`](../retrieval/)
- Delegates context enrichment to [`src/contextualization/`](../contextualization/)
- Does **not** handle transport-layer concerns (Telegram, HTTP)

***REMOVED******REMOVED*** Usage

```python
from src.core import RAGPipeline

pipeline = RAGPipeline()
results = await pipeline.search("What are citizen rights?")

for result in results.results:
    print(result["text"])
```

***REMOVED******REMOVED*** Focused checks

```bash
uv run pytest tests/unit/core/ -q
```

***REMOVED******REMOVED*** Related

- [`src/config/`](../config/) — Settings and constants
- [`src/retrieval/`](../retrieval/) — Search engine implementations
- [`src/contextualization/`](../contextualization/) — LLM context enrichment
