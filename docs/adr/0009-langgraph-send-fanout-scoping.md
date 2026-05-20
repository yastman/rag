***REMOVED*** ADR-0009: LangGraph `Send` Fan-Out Adoption — Scoping

**Status:** Scoping (no production adoption yet)

**Date:** 2026-05-20

**Closes:** [***REMOVED***1670](https://github.com/yastman/issues/1670)

***REMOVED******REMOVED*** Context

LangGraph 1.x exposes `Send` (from `langgraph.types`) as the SDK-native primitive for parallel fan-out in conditional edges. A `Send(target_node, partial_state)` instance dispatches one source node to multiple invocations of a downstream node, each with its own partial state. The downstream invocations execute concurrently and their state updates merge back via the graph's state reducer.

```python
from langgraph.types import Send

def fan_out(state):
    return [Send("worker_node", {"query": q}) for q in state["queries"]]

workflow.add_conditional_edges("classify", fan_out, ["worker_node"])
```

Repo grep:

```bash
$ grep -rn "from langgraph\.types import Send\|Send(" telegram_bot/ src/
***REMOVED*** (no matches)
```

The current graph (`telegram_bot/graph/graph.py`) is fully sequential. Wherever a step is structurally a *map* over independent inputs — e.g., generate N hypothetical documents in HyDE, run dense retrieval in M languages — the project either does the work serially (single-doc HyDE) or hides parallelism behind `asyncio.gather` outside the graph. The latter is correct on the asyncio level but loses two LangGraph-native properties:

1. Workers do not become first-class graph nodes; they cannot inherit checkpointer context.
2. Their Langfuse generation observations are not naturally nested under the parent span (parent-child relationship has to be re-established manually).

`Send` solves both.

***REMOVED******REMOVED*** Candidate sites

| Site | Today | Map shape | Quality / latency lever | Pilot priority |
|---|---|---|---|---|
| `services/query_preprocessor.py::HyDEGenerator.generate_hypothetical_document` | Single hypothetical doc per query | N hypothetical docs in parallel (multi-perspective HyDE — different system prompts) | Recall (gold-set NDCG@10 / Recall@10) | **Recommended pilot** |
| Multi-language query expansion (RU / EN / BG) | Implicit single-language path | Run dense retrieval per language and merge with RRF | Recall on multi-language queries | Defer — needs language-detection contract first |
| Pre-agent classify + extract (`classify_node` + filter extractor) | Sequential | Fan-out from `START` to both classifiers, merge into `state` | Latency (-50–80 ms typical) | Defer — measure classifier latency first |

***REMOVED******REMOVED*** Decision

This ADR is a **scoping document, not an implementation**. It adopts `Send` as the canonical SDK pattern for parallel fan-out *when* a site is migrated. No graph code is changed by this ADR.

Recommended pilot when work resumes: **HyDE multi-document fan-out** behind a config flag `HYDE_FANOUT_DOCS` (default `1`, current behavior). The pilot ships independently and is gated by an A/B evaluation on the gold set (`src/evaluation/`).

***REMOVED******REMOVED*** Required shape when a site is migrated

1. Use `from langgraph.types import Send`. Do **not** introduce another fan-out abstraction.
2. The fan-out function returns a `list[Send]`; conditional edge declaration enumerates the target node(s) explicitly: `workflow.add_conditional_edges(src, fan_out, [target])`.
3. Worker state updates merge through an explicit reducer on the relevant `RAGState` field (e.g., `Annotated[list[str], operator.add]` for hypothetical-doc lists).
4. Parent span coverage: the source node that returns `Send` instances must already be wrapped with `@observe` so the workers' Langfuse observations nest under the parent span automatically.
5. `asyncio.gather` is **not** the alternative inside graph code. If the work is a map over LangGraph nodes, use `Send`. `asyncio.gather` remains correct for non-graph code (services, ingestion, bot handlers).

***REMOVED******REMOVED*** Forbidden during a future pilot

- Introducing a new graph framework or custom fan-out helper.
- Migrating sites without a measurable success metric (latency or recall).
- Removing the existing single-doc HyDE path before the gold-set evaluation confirms the multi-doc path's quality. Default `HYDE_FANOUT_DOCS=1` preserves current behavior.

***REMOVED******REMOVED*** Consequences

***REMOVED******REMOVED******REMOVED*** Positive
- Canonical SDK shape is documented; future contributors will not invent ad-hoc fan-out.
- The `instructor` decision in [ADR-0008](0008-instructor-create-partial-deferred.md) and the streaming refactor in [***REMOVED***1671](https://github.com/yastman/rag/issues/1671) compose cleanly with `Send`-based fan-out: each worker can use `instructor.from_openai(...)` and emit `stream_mode="custom"` events independently.

***REMOVED******REMOVED******REMOVED*** Negative
- No latency or recall improvement until a pilot ships.
- The scoping doc has to be re-validated against LangGraph version pin if/when the pilot lands.

***REMOVED******REMOVED*** References

- Issue [***REMOVED***1670](https://github.com/yastman/rag/issues/1670) — research request.
- Issue [***REMOVED***1538](https://github.com/yastman/rag/issues/1538) — broader SDK-vs-custom audit; this is one concrete sub-item.
- Issue [***REMOVED***1671](https://github.com/yastman/rag/issues/1671) — `stream_mode="custom"` (orthogonal but composable with `Send`).
- ADR-0008 — `instructor.create_partial` deferred (related: per-worker structured outputs).
- LangGraph `Send` reference: `langgraph.types.Send`.
- SDK registry entry: `docs/engineering/sdk-registry.md` → `langgraph` section (gotchas).
