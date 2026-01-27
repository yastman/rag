# utils/

Utility functions for document processing.

## Files

| File | Purpose |
|------|---------|
| [\_\_init\_\_.py](./__init__.py) | Utility exports |
| [structure_parser.py](./structure_parser.py) | Regex-based parser for Ukrainian legal documents (articles, chapters) |

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

## Related

- [src/ingestion/](../ingestion/) — Document parsing and chunking
