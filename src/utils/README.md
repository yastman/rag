# utils/

## Purpose

Utility functions for document processing and serialization.
Owns small, shared utility helpers used by RAG and ingestion code.
Keeps document-structure parsing and JSON serialization helpers isolated from pipeline logic.

## Files

| File | Purpose |
|------|---------|
| [`__init__.py`](./__init__.py) | Utility exports |
| [`structure_parser.py`](./structure_parser.py) | Regex-based parser for Ukrainian legal documents (articles, chapters) |
| [`serialization.py`](./serialization.py) | NumPy-to-Python type conversion helpers |

## Structure Parser

Extracts structure from Ukrainian Criminal Code:
- Article numbers (Arabic, Roman, Ukrainian words)
- Chapter/section hierarchy
- Cross-references between articles

```python
from src.utils.structure_parser import parse_article_number

article = parse_article_number("Стаття 121")  # Returns: "121"
article = parse_article_number("Стаття сто двадцять перша")  # Returns: "121"
```

## Serialization

Converts NumPy values into JSON-serializable Python types:

```python
from src.utils.serialization import convert_to_python_types

clean = convert_to_python_types({"vector": np.array([1.0, 2.0])})
```

## Boundaries

- Does not own document ingestion orchestration or Qdrant writes.
- Does not own security redaction; see [`src/security/`](../security/).
- Keep utilities dependency-light and reusable across callers.

## Focused checks

```bash
uv run pytest tests/unit/utils/ -q
```

## See Also

- [`src/ingestion/`](../ingestion/) — Document parsing and chunking
