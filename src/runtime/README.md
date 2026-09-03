# `src/runtime` — shared runtime engine

The engine layer of the monolith. `src/core/` (public boundary) and `telegram_bot/`
(adapter) both call into here.

Layering: `src/core` → `src/runtime` → `telegram_bot` (enforced by `import-linter`; see
[`../../pyproject.toml`](../../pyproject.toml) `[tool.importlinter]`). The reverse-layering
migration that created this package is complete — the runtime kernel does not import from
`telegram_bot`.

## Subpackages

| Path | Role |
|------|------|
| `pipeline/` | RAG orchestration — `assistant_pipeline.py`, `rag.py` (`rag_pipeline`), retrieve / grade+rerank / cache stages |
| `generation/` | Answer generation — `service.py` (`generate_answer`), prompts, streaming, policy |
| `graph/` | Graph factory resolver + config — `builder.resolve_pipeline_factory`, `GraphConfig`, `state.py`, `nodes/`, `edges.py` |
| `qdrant/` | `QdrantService` — hybrid dense + sparse + ColBERT search gateway |
| `retrieval/` | `RetrievalService` — composes embeddings with the Qdrant gateway |
| `grounding/` | Grounding / citation policy |
| `llm/` | `router.py` — LLM provider routing |
| `services/` | Runtime helpers — query preprocessing, cache policy, small-to-big, ColBERT rerank, coverage mode |
| `integrations/` | `CacheLayerManager` (Redis caches), embeddings, prompt manager |
| `domain_defaults.py` | Domain-tunable retrieval / generation defaults |

## The spine

```
run_assistant_pipeline   pipeline/assistant_pipeline.py
  → classify_query
  → rag_pipeline         pipeline/rag.py     (cache → hybrid search → grade → rerank → optional rewrite loop)
  → generate_answer      generation/service.py
```

## Boundaries

- Engine code must not import from `telegram_bot/`. The contract test
  [`tests/contract/test_runtime_no_telegram_bot_coupling_contract.py`](../../tests/contract/test_runtime_no_telegram_bot_coupling_contract.py)
  enforces this.
- Retrieval is query-only; ingestion writes are owned by `src/ingestion/`.

## Verification

```bash
make test-core
```
