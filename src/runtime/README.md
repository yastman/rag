# Shared runtime engine

Procedural routing, retrieval, grounding, generation, runtime configuration, and integrations.
The assistant core and transport assembly use this engine.

| Area | Start point |
| --- | --- |
| Request execution | [pipeline/assistant_pipeline.py](pipeline/assistant_pipeline.py) |
| RAG orchestration | [pipeline/rag.py](pipeline/rag.py) |
| Generation | [generation/service.py](generation/service.py) |
| Qdrant search | [qdrant/service.py](qdrant/service.py) |
| Qdrant readiness | [qdrant/readiness.py](qdrant/readiness.py) |
| Runtime configuration | [config.py](config.py) |
| Provider client | [llm/router.py](llm/router.py) |
| Cache/embedding/prompt integration | [integrations](integrations/) |

## Boundaries

The [canonical structure map](../../docs/architecture/STRUCTURE.md) owns dependency direction.
Core delegates here; runtime consumes shared core contracts/telemetry. Runtime must not import
telegram_bot. Document ingestion owns writes.

GraphConfig is the current runtime configuration type; its name does not imply graph-based
execution. Check composition and consumers before moving/deleting fields.

## Validation

Start with `make test-core` and focused behavior tests.
[AGENTS.md](../../AGENTS.md) owns delivery policy; [Tests](../../tests/README.md) explains lanes.
