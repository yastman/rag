# ADR 0019: Procedural core text path

- Status: Accepted
- Tracking: CORE-018

## Decision

The assistant core text RAG path is procedural. `src.core.assistant.run_assistant_request` is the public transport-free entrypoint. It delegates to `src.runtime.pipeline.assistant_pipeline.run_assistant_pipeline`, which classifies the request, runs retrieval through the RAG pipeline, then calls the runtime generation service.

`create_agent` is **not** the canonical owner of this path. Agent frameworks may be used by conversational or transport adapters, but `src/core` and `src/runtime` must not import `langchain.agents.create_agent`.

## Consequences

- Core behavior remains callable without Telegram or another transport.
- Retrieval, grounding, and generation policies stay explicit in `src/runtime`.
- Dependency injection uses the contracts in `src/core/contracts.py`; adding an agent-framework lifecycle to the core path requires a new architecture decision.
