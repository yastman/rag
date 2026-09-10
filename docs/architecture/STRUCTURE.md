# Canonical project structure

Current module ownership. [PROJECT.md](../../PROJECT.md) owns product scope;
the [RAG VPS v2 proposal](RAG_VPS_V2_PROPOSED.md) is a separate future design.

## Owners

| Path | Owns | Start here |
| --- | --- | --- |
| src/core | Transport-free API, request/result and dependency contracts, app assembly | [assistant.py](../../src/core/assistant.py), [contracts.py](../../src/core/contracts.py), [app.py](../../src/core/app.py) |
| src/runtime/pipeline | Procedural request routing and RAG orchestration | [assistant_pipeline.py](../../src/runtime/pipeline/assistant_pipeline.py), [rag.py](../../src/runtime/pipeline/rag.py) |
| src/runtime/generation | Prompts, answer generation, output policy | [service.py](../../src/runtime/generation/service.py) |
| src/runtime/qdrant | Canonical collection contracts (schema/identity/filter) plus search and readiness | [contracts.py](../../src/runtime/qdrant/contracts.py), [service.py](../../src/runtime/qdrant/service.py), [readiness.py](../../src/runtime/qdrant/readiness.py) |
| src/runtime/retrieval | Retrieval composition | [runtime guide](../../src/runtime/README.md) |
| src/runtime/integrations | Cache/embedding/prompt integrations | [runtime guide](../../src/runtime/README.md) |
| src/runtime/config.py | Runtime GraphConfig; its name does not imply a graph framework | [config.py](../../src/runtime/config.py) |
| src/services | Shared clients and state/content owners | [services](../../src/services/README.md) |
| src/adapters | Provider adapters below orchestration | [adapters](../../src/adapters/README.md) |
| src/ingestion/unified | Markdown load/chunk/manifest/write path | [flow.py](../../src/ingestion/unified/flow.py), [ingestion contract](../INGESTION.md) |
| src/ingestion/apartments | Catalog data ingestion | [apartment ingestion](../../src/ingestion/apartments/README.md) |
| src/retrieval | Retrieval-facing helpers outside orchestration | [retrieval](../../src/retrieval/README.md) |
| telegram_bot | Transport, lifecycle, handlers/dialogs, product UI | [main.py](../../telegram_bot/main.py), [adapter](../../telegram_bot/assistant_core_adapter.py), [bot guide](../../telegram_bot/README.md) |
| services/bge-m3-api | Independently packaged embedding/reranking sidecar and artifact | [service guide](../../services/bge-m3-api/README.md) |
| scripts | Out-of-process bootstrap and operator commands | [scripts](../../scripts/README.md) |

A compatibility re-export is not a second owner. Follow its target before changing behavior.
Check current callers before declaring a module unused.

## Flows

Arrows mean calls/data movement, not strict package layers.

```text
Telegram → assistant_core_adapter → src/core.run_assistant_request
         → src/runtime.pipeline.run_assistant_pipeline
             → RAG retrieval/cache/grounding → generation → AssistantResult
             → deterministic product action → AssistantResult
         → Telegram response

Markdown → unified ingestion → manifest/chunks → Qdrant writes
Apartment corpus → apartment ingestion → catalog collection
Query runtime → Qdrant reads; BGE-M3 and Redis support retrieval/cache
```

Knowledge and apartment collections have different schemas and roles. Startup readiness
does not prove a live known-corpus answer or Telegram journey.

## Dependency constraints

[pyproject.toml](../../pyproject.toml) is the executable import-linter authority.
Core delegates to runtime; runtime also uses shared core contracts/telemetry.
This intentional relationship is not a strictly one-way package hierarchy.

- Neither src/core nor src/runtime imports telegram_bot.
- src/core/contracts.py remains independent of implementation and transport.
- Active src code must not import archive.
- Provider adapters stay below orchestration: do not add imports from src/runtime into
  src/adapters modules.
- src/ingestion must not import src/runtime, with one accepted exception (#3333):
  `src.runtime.qdrant.contracts`, the pure-data Qdrant schema/identity/filter
  authority that ingestion, readiness, setup, and search all consume.
- Ingestion owns writes and identity/manifest handling. Query retrieval is read-oriented;
  setup/readiness scripts have separate operational responsibilities.

Validate boundaries with focused behavior tests and import-linter. Internal wrappers and
filenames are not permanent architecture merely because a migration once introduced them.

## Configuration and updates

Root pyproject.toml/uv.lock own application dependencies; BGE owns its service manifest/lock.
Compose files own wiring, documented by [DOCKER.md](../../DOCKER.md).
The root .env is local configuration, not a versioned source of defaults.

Update this map and affected links with ownership/entry-point changes. Record newly accepted
architectural decisions in ADRs; keep implementation progress on GitHub.
