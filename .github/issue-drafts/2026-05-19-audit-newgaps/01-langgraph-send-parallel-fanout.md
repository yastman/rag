# refactor: use LangGraph `Send` for parallel fan-out in HyDE / multi-language / multi-query paths

## Source

2026-05-19 cross-domain SDK audit (`.github/issue-drafts/2026-05-19-langfuse-trace-coverage/AUDIT_REPORT.md`, Finding 4).

## Problem

LangGraph 1.x exposes `Send` (from `langgraph.types`) — the SDK-native primitive for parallel fan-out in conditional edges. It dispatches one source node to multiple downstream node invocations with different inputs (the canonical "map" pattern in graph-based pipelines).

Repo grep:

```bash
$ grep -rn "from langgraph\.types import Send\|Send(" telegram_bot/ src/
# (no matches)
```

Several paths today are **sequential** where parallel fan-out would improve latency and recall:

1. **HyDE multi-document expansion** — `telegram_bot/services/query_preprocessor.py:HyDEGenerator.generate_hypothetical_document` produces a single hypothetical document per query. Variants like multi-perspective HyDE (different system prompts per worker) need parallel calls. Today this would require `asyncio.gather` outside the graph; with `Send`, it stays inside the graph and inherits checkpointer / Langfuse parent context naturally.
2. **Multi-language query expansion** — apartment search supports Russian/English/Bulgarian. If the system ever does parallel queries in each language and merges via RRF, `Send` is the SDK-native shape.
3. **Pre-agent classification + retrieval** — currently classify → cache_check → retrieve runs serially. Independent steps (e.g. classify intent + extract apartment filters) could fan-out from `START`.

## Evidence — what's in the repo today

- `telegram_bot/graph/graph.py` builds a sequential `StateGraph` with `add_node` + `add_edge` / `add_conditional_edges`. No fan-out.
- `telegram_bot/services/query_preprocessor.py:HyDEGenerator.generate_hypothetical_document` — single LLM call.
- `telegram_bot/agents/rag_pipeline.py` — sequential retrieval / grade / rerank pipeline.

## Context7 SDK baseline — `/langchain-ai/langgraph`

```python
from langgraph.types import Send
from langgraph.graph import StateGraph

def fan_out(state):
    # Returns list of Send commands; LangGraph runs targets concurrently.
    return [
        Send("worker_node", {"query": q})
        for q in state["queries"]
    ]

workflow.add_conditional_edges("classify", fan_out, ["worker_node"])
```

`Send` carries:
- target node name (must be in graph);
- partial state for that invocation (each worker sees its own `state["query"]`);
- the workers' state updates merge back via the state reducer (e.g. `Annotated[list, add_messages]` or custom reducer).

## Implementation plan

This is a **scoping issue**, not a single PR. Required steps:

1. **Survey** — list every place in `telegram_bot/graph/`, `telegram_bot/agents/`, `telegram_bot/services/` where the bot does sequential work that's structurally a map-then-merge.
2. **Pick one pilot** — recommend HyDE multi-document. Reasons: small surface, clear quality win (multi-perspective recall), doesn't change UX.
3. **Define merge reducer** — for HyDE, the reducer collects N hypothetical docs into a list, then dense+sparse retrieval consumes the list as a single batched embedding call.
4. **Span model** — `Send` workers automatically get nested under the parent span when wrapped in an `@observe`-decorated graph node. Verify against `_validation_comments/04-1661-hyde.md` recommendations.
5. **Pilot PR** — implement HyDE fan-out behind a config flag (`HYDE_FANOUT_DOCS=3`).
6. **Evaluation** — measure NDCG@10 / Recall@10 vs single-doc HyDE on the gold set.

## Forbidden

- No external `asyncio.gather` in graph code where `Send` would express the same pattern (loses checkpointer context and Langfuse parent span).
- No new graph framework beyond LangGraph 1.x.
- No change to current sequential paths until the pilot ships and proves the pattern works.

## SDK / Local Baseline

- LangGraph: `1.0.x` per repo's pin (`telegram_bot/pyproject.toml`).
- `Send` is part of `langgraph.types` since LangGraph 0.2.x; stable in 1.x.

## Verification

```bash
uv run pytest tests/unit/services/test_query_preprocessor.py -q
uv run pytest tests/unit/graph -q
# Add a focused test that asserts the graph topology contains a Send-based fan-out
# under HYDE_FANOUT_DOCS > 1.
```

## Related

- #1538 — broader SDK-vs-custom audit. This is one concrete next item.
- #1535 — voice path migration to `create_agent`. Orthogonal.
- #1652 — research issue for LangChain-native HyDE replacement. Cross-link: if a LangChain HyDE primitive exists in pinned versions, prefer that over `Send`-based fan-out.

## Priority

**P3-backlog** — quality and latency improvement, not a bug.
