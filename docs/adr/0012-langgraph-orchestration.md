***REMOVED*** ADR-0012: LangGraph State Machine for Workflow Orchestration

**Status:** Accepted

**Date:** 2025-05-21

***REMOVED******REMOVED*** Context

The AI assistant requires multi-step stateful workflows: classification, content guarding, cache checking, retrieval, grading, reranking, generation, response formatting, optional summarization, and tool/CRM calls with human-in-the-loop approval. We evaluated several approaches:

1. **LangGraph** - State machine with typed state, conditional routing edges, and checkpointing
2. **Raw LangChain sequential chains** - Linear chain composition without branching or shared state
3. **Custom async pipeline** - Hand-rolled async Python with explicit state passing
4. **Temporal / Prefect** - Durable execution engines for workflow orchestration
5. **CrewAI** - Agent-centric multi-agent framework

***REMOVED******REMOVED*** Decision

We chose **LangGraph state machine** with typed state (`RAGState` TypedDict) and conditional routing edges as the workflow orchestration framework.

***REMOVED******REMOVED******REMOVED*** Why LangGraph

1. **Explicit state flow** - The entire pipeline is visible as a directed graph with named nodes and edges
2. **Conditional routing** - Conditional edges enable dynamic routing (e.g., skip retrieval on cache hit, route to HITL on tool calls)
3. **Checkpointing** - Built-in support for conversation memory and state persistence across turns
4. **Per-node tracing** - `@observe` decorator and LangSmith/Langfuse integration for node-level observability
5. **Testable node functions** - Each node is a standalone function that takes and returns state, enabling unit testing
6. **Shared runtime** - Same graph definition serves both the Telegram bot and the RAG API

***REMOVED******REMOVED******REMOVED*** Why Not Others

| Approach | Reason Rejected |
|----------|----------------|
| Raw LangChain chains | No branching or shared state; sequential-only composition |
| Custom async pipeline | High maintenance burden; no ecosystem tooling for tracing or checkpointing |
| Temporal / Prefect | Overkill for single-request flows; adds significant operational overhead |
| CrewAI | Agent-centric model; less control over node-level routing and state transitions |

***REMOVED******REMOVED*** Consequences

***REMOVED******REMOVED******REMOVED*** Positive
- Explicit state flow visible in code as a graph definition
- Conditional edges for dynamic routing based on state
- Checkpointing for conversation memory across turns
- `@observe` decorator enables per-node tracing via Langfuse
- Testable node functions with clear input/output contracts
- Same graph runtime shared by Telegram bot and RAG API

***REMOVED******REMOVED******REMOVED*** Negative
- LangGraph version coupling: API changes between versions require migration
- Learning curve for conditional edges and `Send` patterns
- Graph compilation overhead (negligible at runtime, but adds complexity to initialization)

***REMOVED******REMOVED*** Implementation

- `telegram_bot/graph/graph.py` - `build_graph()` function that assembles the full state machine
- `telegram_bot/graph/state.py` - `RAGState` TypedDict defining the shared state schema
- `telegram_bot/graph/nodes/` - One file per node (classify, guard, cache, retrieve, grade, rerank, generate, format, summarize, tools)
- `telegram_bot/graph/context.py` - `GraphContext` dependency injection container for services
- Same graph runtime shared by Telegram bot handler and RAG API endpoint

***REMOVED******REMOVED*** References

- [docs/PIPELINE_OVERVIEW.md](../PIPELINE_OVERVIEW.md) - Full pipeline flow documentation
- [docs/BOT_ARCHITECTURE.md](../BOT_ARCHITECTURE.md) - Bot architecture and graph integration
- [telegram_bot/graph/](../../telegram_bot/graph/) - Graph implementation directory
