# Architecture Decision Records (ADRs)

Documenting significant architectural decisions.

---

## ADR-001: TypedDict for Graph State (not Pydantic)

**Status:** Accepted
**Date:** 2024-01-15

### Context

LangGraph's `StateGraph` supports generic types. We needed a state definition that:
- Works with LangGraph's reducer system
- Is serializable for checkpointing
- Integrates with mypy strict mode

### Decision

Use `TypedDict` for all graph state, not Pydantic models.

```python
class RAGState(TypedDict):
    query: str
    query_type: str | None
    # ... fields
```

### Rationale

- LangGraph's `@operator`装饰器 works natively with TypedDict
- Reducers (`Annotated[list, add_messages]`) require TypedDict
- Checkpointing serializes state; TypedDict is naturally serializable
- Pydantic v2 `BaseModel` adds overhead and doesn't integrate as cleanly

### Consequences

**Positive:**
- Native LangGraph integration
- Simple serialization for Redis checkpointer
- Type checking with mypy

**Negative:**
- No runtime validation at state boundaries
- Must manually validate at node entry points

---

## ADR-002: RRF Fusion over Semantic Search Only

**Status:** Accepted
**Date:** 2024-02-20

### Context

We need high-quality retrieval for real estate queries. Dense embeddings alone miss exact keyword matches (property IDs, prices, neighborhoods).

### Decision

Hybrid search with RRF (Reciprocal Rank Fusion):
1. Dense vector search (BGE-M3)
2. Sparse/bm42 keyword search
3. Fused via RRF with k=60

### Rationale

- RRF is robust to relevance score differences between methods
- Captures semantic meaning AND exact keywords
- No training required
- Works with any vector DB supporting hybrid queries

### Consequences

**Positive:**
- Handles both "2-bedroom apartment" (semantic) and "Apt #123" (keyword)
- Robust to embedding quality variations
- Simple implementation in Qdrant

**Negative:**
- Two embedding calls per query (dense + sparse)
- Slightly more complex than pure semantic

---

## ADR-003: RedisVL for Semantic Cache

**Status:** Accepted
**Date:** 2024-03-10

### Context

We need sub-millisecond cache lookups for repeated/similar queries. Traditional exact-match cache misses on paraphrases.

### Decision

Two-tier semantic cache using RedisVL:
1. **Embeddings cache:** Skip re-encoding repeated queries
2. **Results cache:** Skip retrieval for semantically similar queries

### Rationale

- RedisVL provides vector similarity search within Redis
- Distance thresholds tuned per query type (FAQ vs GENERAL)
- Shared Redis instance with existing cache infrastructure
- No separate cache service needed

### Consequences

**Positive:**
- ~60% cache hit rate in production
- Sub-ms lookup latency
- Embedding reuse across queries

**Negative:**
- Redis memory for vector storage
- Threshold tuning required per query type

---

## ADR-004: Interrupt-based HITL Pattern

**Status:** Accepted
**Date:** 2024-04-05

### Context

CRM operations (create lead, schedule viewing) require human approval before execution. We needed a pattern that:
- Pauses graph execution reliably
- Persists state across bot restarts
- Allows supervisor to approve from Telegram

### Decision

LangGraph `interrupt()` with Redis-persisted `HandoffState`:

```
Tool call → interrupt() → Redis state → Supervisor notification
                                              ↓
                                    User approval/rejection
                                              ↓
                              Command(resume=) → Graph resumes
```

### Rationale

- `interrupt()` is native to LangGraph checkpointing
- Redis persistence survives bot restarts
- Telegram inline keyboards for approval UI
- Simple state machine (waiting → approved/rejected)

### Consequences

**Positive:**
- Reliable pause/resume
- Supervisor can approve from mobile Telegram
- State survives crashes

**Negative:**
- Supervisor must be available (300s timeout)
- Extra Redis keys to manage

---

## ADR-005: BGE-M3 for All Embeddings

**Status:** Accepted
**Date:** 2024-05-12

### Context

We need embeddings that support:
- Dense vectors for semantic search
- Sparse vectors for keyword matching
- ColBERT-style late interaction for reranking

### Decision

Use BGE-M3 exclusively:
- `encode/dense` → 1024-dim dense vectors
- `encode/sparse` → bm42-style sparse vectors
- `encode/colbert` → Late interaction vectors

### Rationale

- Single model for all embedding needs
- Self-hosted (no API costs)
- Dense + sparse in one model
- ColBERT support for reranking

### Consequences

**Positive:**
- No model switching overhead
- Unified embedding pipeline
- Cost-effective (self-hosted)

**Negative:**
- BGE-M3 is ~5GB RAM
- Slower than lightweight embedding models
- Must manage BGE-M3 service

---

## ADR-006: LiteLLM for LLM Abstraction

**Status:** Accepted
**Date:** 2024-06-01

### Context

We use multiple LLM providers (OpenAI, Cerebras, Groq). Direct SDK integration would couple code to provider specifics.

### Decision

Route all LLM calls through LiteLLM proxy:
```
Code → LiteLLM → OpenAI/Cerebras/Groq
```

### Rationale

- Single interface for all providers
- Easy provider switching via env vars
- Built-in retry/timeout handling
- Langfuse integration via `langfuse.openai.AsyncOpenAI`

### Consequences

**Positive:**
- Provider-agnostic code
- Simple fallback configuration
- Centralized LLM observability

**Negative:**
- Additional hop (latency)
- LiteLLM must be running
- Provider-specific quirks may leak through

---

*To add new ADRs: create `docs/adr/ADR-NNN-title.md` with status, context, decision, rationale, and consequences.*
