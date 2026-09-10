# utils/

## Purpose

Utility helpers used by RAG and ingestion code.
Keeps small, shared utility helpers isolated from pipeline logic.

## Files

| File | Purpose |
|------|---------|
| [`__init__.py`](./__init__.py) | Utility exports |
| [`product_events.py`](./product_events.py) | Product / telemetry event payload helpers (used by `src.core.telemetry`) |

## Product Events

`product_events.py` builds structured product / telemetry event payloads emitted by
`src.core.telemetry` (answer served, retrieval outcome, …). Keep it dependency-light.

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
