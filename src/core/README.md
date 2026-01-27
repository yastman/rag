# core/

Main RAG pipeline orchestrator.

## Files

| File | Purpose |
|------|---------|
| [\_\_init\_\_.py](./__init__.py) | Exports RAGPipeline, RAGResult |
| [pipeline.py](./pipeline.py) | RAGPipeline: orchestrates embedding, retrieval, context enrichment |

## Usage

```python
from src.core import RAGPipeline

pipeline = RAGPipeline()
results = await pipeline.search("What are citizen rights?")

for result in results.results:
    print(result["text"])
```

## Related

- [src/config/](../config/) — Settings and constants
- [src/retrieval/](../retrieval/) — Search engine implementations
- [src/contextualization/](../contextualization/) — LLM context enrichment
