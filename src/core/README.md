# core/

## Purpose

Core assistant contracts, entrypoint, and app configuration.
Exports typed contracts, the `run_assistant_request` entrypoint, and `AssistantApp`/`DependencyBuilder`.

## Files

| File | Purpose |
|------|---------|
| [`__init__.py`](./__init__.py) | Lazy exports for `AssistantApp`, `DependencyBuilder`, `run_assistant_request`, and contracts |
| [`contracts.py`](./contracts.py) | Typed state contracts: `AssistantRequest`, `AssistantResult`, provider protocols |
| [`assistant.py`](./assistant.py) | `run_assistant_request()` — main assistant entrypoint |
| [`app.py`](./app.py) | `AssistantApp`, `DependencyBuilder` |

## Boundaries

- Does **not** handle transport-layer concerns (Telegram, HTTP)
- Pipeline orchestration lives in [`src/runtime/pipeline/`](../runtime/pipeline/)

## Usage

```python
from src.core import run_assistant_request, AssistantRequest

result = await run_assistant_request(AssistantRequest(...), deps)
```

## Focused checks

```bash
uv run pytest tests/unit/core/ -q
```

## See Also

- [`src/runtime/pipeline/`](../runtime/pipeline/) — imperative assistant pipeline
- [`src/config/`](../config/) — Settings and constants
