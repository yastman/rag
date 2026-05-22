# Client Pipeline: Dual-Path Architecture

> **Canonical home for the dual-path split.** This doc describes the runtime asymmetry between the text and voice RAG flows.
>
> See also: [`PIPELINE_OVERVIEW.md`](PIPELINE_OVERVIEW.md) for the operational overview of all flows (ingestion / query / voice) and [`PIPELINE_ROUTING.md`](PIPELINE_ROUTING.md) for the StateGraph routing rules used by the voice path and the text-path `rag_search` tool.
>
> Migration plan and SDK context: [`docs/adr/0010-voice-path-create-agent-migration-plan.md`](adr/0010-voice-path-create-agent-migration-plan.md), SDK-native audit issue [#1538](https://github.com/yastman/rag/issues/1538), voice migration tracker [#1535](https://github.com/yastman/rag/issues/1535).

The Telegram bot uses a **dual-path architecture** to route queries efficiently based on role and query complexity. The two paths use **different orchestrators**:

| Path | Orchestrator | Source | Status |
|---|---|---|---|
| Text (text + agent intent) | `langchain.agents.create_agent` (LangChain 1.x) | [`telegram_bot/agents/agent.py`](../telegram_bot/agents/agent.py) | SDK-native |
| Voice | Custom `StateGraph` from `build_graph()` | [`telegram_bot/graph/graph.py`](../telegram_bot/graph/graph.py) | Pending migration ([ADR-0010](adr/0010-voice-path-create-agent-migration-plan.md), #1535) |

The voice path's `StateGraph` is reused (read-only) by the text path's `rag_search` tool, so the routing rules in `PIPELINE_ROUTING.md` apply to both paths' retrieve→grade→rerank inner loop.

## Architecture Overview

```
User Query
    │
    ▼
PropertyBot.handle_query()
    │
    ├─── [Client role + fast query] ──→ Client Direct Pipeline
    │                                          │
    │                                    Deterministic flow
    │                                    (no agent loop)
    │                                          │
    │                                    rag_pipeline() → generate_response()
    │                                          │
    └─── [Manager role OR complex query] ──→ SDK Agent Pipeline (create_agent)
                                               │
                                         langchain.agents.create_agent
                                               │
                                    create_bot_agent() → tools
```

## Path 1: Client Direct Pipeline

**When:** `CLIENT_DIRECT_PIPELINE_ENABLED=true` AND user has `client` role AND query is simple.

**File:** `telegram_bot/pipelines/client.py` — `run_client_pipeline()`

### Flow

```
1. Classify query type
2. Detect agent intent (mortgage/handoff/daily_summary)
   → If intent found, fallback to agent path
3. Check semantic cache
   → Cache hit: return cached response
4. Run RAG pipeline (skip_rewrite=True for FAQ)
5. Generate response
6. Post-process (double-send guard, cache store, history save)
```

### Characteristics

- **0-1 LLM calls** (cache hit = 0, cache miss = 1)
- **No agent loop** — deterministic code path
- **No tools** — direct function calls
- **Faster** — lower latency than agent path
- **Feature flag:** `CLIENT_DIRECT_PIPELINE_ENABLED` env var

### Cache Behavior

Client pipeline uses store guards:
- Only stores for `FAQ`, `GENERAL`, `ENTITY`, `STRUCTURED` types
- Skips contextual follow-ups ("подробнее"/"more details", "первый"/"the first one")
- Requires `grade_confidence >= 0.005` (RRF scale)

## Path 2: SDK Agent Pipeline

**When:** User has `manager` role OR query needs tools (CRM, history, etc.) OR client pipeline signaled `needs_agent=True`.

**File:** `telegram_bot/agents/agent.py` — `create_bot_agent()`

### Flow

```
1. Build tools list (rag_search, history_search, CRM tools)
2. Create agent via LangChain SDK
3. Agent decides which tool to call (LLM routing)
4. Tool executes, result returned to agent
5. Agent generates final response
```

### Characteristics

- **1-N LLM calls** (agent loop + generation)
- **Orchestrator:** `langchain.agents.create_agent` (LangChain 1.x SDK) — not a raw `StateGraph`. Voice path still uses `StateGraph` pending [ADR-0010](adr/0010-voice-path-create-agent-migration-plan.md) / #1535.
- **Tools available:** RAG search, history, CRM operations
- **Higher latency** but more capable

### Available Tools

| Tool | Purpose |
|------|---------|
| `rag_search` | RAG pipeline retrieval |
| `history_search` | Conversation history search |
| `crm_*` (8 tools) | Kommo CRM operations |
| `mortgage_calculator` | Mortgage calculations |
| `daily_summary` | Session summary generation |
| `handoff` | Transfer to human manager |

## Routing Logic

### PropertyBot.handle_query()

```python
async def handle_query(self, query, user, ...):
    if self._is_client_role(user) and self._fast_query(query):
        return await self._handle_client_direct_pipeline(query, user, ...)
    else:
        return await self._handle_query_supervisor(query, user, ...)
```

### Fallback

If client pipeline raises an exception, it falls back to agent path:

```python
try:
    result = await run_client_pipeline(...)
except Exception:
    logger.warning("Client pipeline failed, falling back to agent")
    return await self._handle_query_supervisor(...)
```

## Observability

Each path sets `pipeline_mode` metadata in Langfuse:

| Path | `pipeline_mode` value |
|------|----------------------|
| Client direct | `"client_direct"` |
| SDK agent | `"sdk_agent"` |

Check this in Langfuse UI → Trace → Metadata to understand which path was taken.

## Performance Comparison

| Metric | Client Direct | SDK Agent |
|--------|---------------|-----------|
| Latency (cache hit) | ~100ms | ~500ms+ |
| Latency (cache miss) | ~1-2s | ~2-5s |
| LLM calls | 0-1 | 1-N |
| Tool use | No | Yes |
| CRM access | No | Yes |

## Debugging

### Disable Client Pipeline

Set in `.env`:
```
CLIENT_DIRECT_PIPELINE_ENABLED=false
```

All queries will go through the SDK agent path.

### Trace Which Path

In Langfuse:
1. Open trace
2. Look for `pipeline_mode` in metadata
3. Or check span names: `run_client_pipeline` vs `create_bot_agent`

### Log Comparison

```
# Client direct
logger.info("Client direct pipeline completed", extra={"cache_hit": True, "latency_ms": 150})

# SDK agent
logger.info("SDK agent completed", extra={"tool_calls": ["rag_search", "crm_create_lead"]})
```

## Feature Flags

| Flag | Default | Purpose |
|------|---------|---------|
| `CLIENT_DIRECT_PIPELINE_ENABLED` | `false` | Enable client fast-path |

Fallback to the SDK agent path is built into `PropertyBot._handle_query()`: if
the client direct pipeline raises, the bot logs the failure and calls the
supervisor path. There is no separate runtime flag for this fallback.
