# Assistant core

Transport-free public API, dependency contracts, app wiring, and telemetry.
The [structure map](../../docs/architecture/STRUCTURE.md) owns module boundaries.

| File | Responsibility |
| --- | --- |
| [assistant.py](assistant.py) | Low-level run_assistant_request entrypoint |
| [app.py](app.py) | AssistantApp: dependency assembly and run_text facade |
| [contracts.py](contracts.py) | UserContext, AssistantResult, CoreDependencies, provider protocols |
| [telemetry.py](telemetry.py) | Product-event emission |

## Calling the core

Within an async function with an explicitly prepared CoreDependencies bundle:

```python
from src.core.assistant import run_assistant_request
from src.core.contracts import UserContext

result = await run_assistant_request(
    "What documents support this answer?",
    user_context=UserContext(),
    dependencies=dependencies,
)
print(result.response_text)
```

The entrypoint takes a query string and keyword-only dependencies; it does not take an
AssistantRequest object or a deps keyword. Without dependencies it returns the service-unavailable
skeleton result and does not call live services. AssistantApp.run_text supplies the higher-level
assembly path; see its source before constructing runtime dependencies in an adapter.

Core does not own Telegram handling. Shared contracts/telemetry are consumed by runtime;
the implementation delegates execution to runtime.

## Verification

Start with `make test-core`. For a focused edit use
`uv run --no-sync pytest tests/unit/core/ -q`.
See [Tests](../../tests/README.md) and [AGENTS](../../AGENTS.md) for the complete delivery gate.
