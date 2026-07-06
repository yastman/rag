# utils/

## Purpose

Utility functions for document processing and serialization.
Owns small, shared utility helpers used by RAG and ingestion code.
Keeps document-structure parsing and JSON serialization helpers isolated from pipeline logic.

## Files

| File | Purpose |
|------|---------|
| [`__init__.py`](./__init__.py) | Utility exports |
| [`product_events.py`](./product_events.py) | Product / telemetry event payload helpers (used by `src.core.telemetry`) |
| [`serialization.py`](./serialization.py) | NumPy-to-Python type conversion helpers |

## Product Events

`product_events.py` builds structured product / telemetry event payloads emitted by
`src.core.telemetry` (answer served, retrieval outcome, …). Keep it dependency-light.

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
