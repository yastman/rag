# core/

## Purpose

Public boundary for the RAG assistant.
Owns the `run_assistant_request` entrypoint, Protocol-based DI contracts, app wiring, and telemetry helpers.
All adapters (Telegram, tests) call through this layer.

## Files

| File | Purpose |
|------|---------|
| [`__init__.py`](./__init__.py) | Package exports |
| [`assistant.py`](./assistant.py) | `run_assistant_request`: single public entrypoint for all adapters |
| [`app.py`](./app.py) | `AssistantApp`: wires dependencies for the assistant pipeline |
| [`contracts.py`](./contracts.py) | Protocol-based DI types: `AssistantRequest`, `AssistantResult`, `CoreDependencies`, provider Protocols |
| [`telemetry.py`](./telemetry.py) | `emit_product_event`: structured telemetry helper |

## Boundaries

- `run_assistant_request` is the only public entrypoint — all callers use it.
- Does **not** handle transport-layer concerns (Telegram, HTTP).
- Delegates retrieval and generation to [`src/runtime/`](../runtime/).

## Usage

```python
from src.core.assistant import run_assistant_request
from src.core.contracts import AssistantRequest

result = await run_assistant_request(AssistantRequest(query="What are citizen rights?"), deps=deps)
print(result.answer)
```

## Focused checks

```bash
uv run pytest tests/unit/core/ -q
```

## See Also

- [`src/config/`](../config/) — Settings and constants
- [`src/runtime/`](../runtime/) — Pipeline, RAG, retrieval, generation engine
- [`src/contextualization/`](../contextualization/) — LLM context enrichment
