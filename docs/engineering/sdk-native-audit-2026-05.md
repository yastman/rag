# SDK-Native vs Custom Implementation Audit — 2026-05 Refresh

Refresh of the audit captured in
[#1538](https://github.com/yastman/rag/issues/1538). The original issue body
was filed on 2026-05-14. This document re-verifies each item against the
current `dev` branch and the relevant Context7 SDK references.

> **Source of truth for SDK choices:** [`sdk-registry.md`](sdk-registry.md).
> This file is a one-time **audit refresh**, not a replacement for the
> registry. Once the open items below are closed (or moved to dedicated
> tracking issues), this file can be archived.

## Methodology

For each item from the original audit:

1. Read the live source on `dev`.
2. If the audit claimed an SDK alternative, query Context7 to confirm the
   alternative still exists and the cited shape (function name, kwargs,
   return type) is current.
3. Mark one of:
   - **closed-on-dev** — already SDK-native; no work to do, candidate for a
     contract pin to prevent regression.
   - **still-open** — custom code still in place; needs follow-up issue or
     PR.
   - **misclassified** — original audit conflated two SDK concepts; no work
     beyond updating the registry / this doc.

Context7 verification was done with library IDs from
[`sdk-registry.md`](sdk-registry.md):
[`/langchain-ai/langgraph`](https://github.com/langchain-ai/langgraph),
[`/qdrant/qdrant-client`](https://github.com/qdrant/qdrant-client),
[`/aiogram/aiogram`](https://github.com/aiogram/aiogram),
[`/aiogram/aiogram-dialog`](https://github.com/aiogram/aiogram-dialog),
[`/langfuse/langfuse-python`](https://github.com/langfuse/langfuse-python).

## Results

### ✅ Already SDK-native — confirmed on dev

These match the issue's "Already using SDK correctly" table and were
re-verified:

| Area | SDK | Live entry point | Notes |
|------|-----|------------------|-------|
| Bot router / dispatcher | `aiogram.Router` + `Dispatcher` | `telegram_bot/bot.py::PropertyBot` | `dp.include_router(...)` chain |
| Dialogs / FSM | `aiogram_dialog.Dialog` + `Window` | `telegram_bot/dialogs/` | states centralised in `states.py` |
| Text agent | `langchain.agents.create_agent` | `telegram_bot/agents/agent.py:334` | `from langchain.agents import create_agent` |
| Vector search | `qdrant_client.AsyncQdrantClient.query_points` + `models.Prefetch` + `models.RrfQuery` | `telegram_bot/services/qdrant.py` | pinned by `tests/contract/test_qdrant_sdk_native_usage_contract.py` |
| Chunking | Docling / CocoIndex chain | `src/ingestion/unified/` | pinned by `tests/contract/test_chunking_strategy_sdk_native_contract.py` |
| Observability | Langfuse SDK + OTEL | `telegram_bot/observability.py` | pinned by `tests/contract/test_langfuse_sdk_native_contract.py` |
| Type / lint | `mypy`, `ruff` | `pyproject.toml`, `Makefile` | repo-wide |
| Pre-commit security | `bandit`, `gitleaks`, `pre-commit-hooks` | `.pre-commit-config.yaml` | enforced in CI |

### 🟡 Audit claim was correct in 2026-05-14 but **closed-on-dev** today

These items were "Custom code that HAS an SDK equivalent" in the original
issue body. Re-reading the source on `dev` shows they have already been
migrated, several without an explicit cross-link in the issue thread.

| Audit claim | Today's status on dev | Evidence |
|-------------|----------------------|----------|
| **P2 — `DraftStreamer` polling** | **gone**: file `telegram_bot/services/draft_streamer.py` no longer exists | `find . -name 'draft_streamer*'` returns nothing |
| **P2 — `_stream_agent_to_draft` should use `agent.astream(stream_mode="messages")`** | **already SDK-native**: function uses `agent.astream(payload, config=config, stream_mode=["messages", "values"])` and unpacks `(msg, metadata)` per `MessagesStreamPart` | `telegram_bot/bot.py:323`; docstring states "the streaming path stays SDK-only" (#1671) |
| **P3 — Custom Conversation memory lifecycle** | **already SDK-native**: `integrations/memory.py` wires `langgraph.checkpoint.redis.aio.AsyncRedisSaver` and falls back to `langgraph.checkpoint.memory.MemorySaver`; module docstring is explicit: "Zero custom logic — SDK wiring only" | `telegram_bot/integrations/memory.py:26,167,184` |
| **P3 — Custom checkpoint namespace management** | **already SDK-native**: `_supervisor_thread_id` derives a `thread_id` and passes it through `config["configurable"]["thread_id"]`, which is the LangGraph-canonical way Context7 documents (`/langchain-ai/langgraph`: "Checkpoints are accessed by thread_id") | `telegram_bot/bot.py` (`_supervisor_thread_id`) |

Context7 evidence for the streaming claim
([`/langchain-ai/langgraph` `MessagesStreamPart`](https://github.com/langchain-ai/langgraph/blob/main/langgraph/libs/langgraph/langgraph/types.py)):
> `MessagesStreamPart` carries `data` as a 2-tuple of `(message, metadata)`
> where `message` is a `BaseMessage` (e.g. `AIMessageChunk`) and
> `metadata` is a dict containing keys like `langgraph_node`,
> `langgraph_step`, `langgraph_triggers`. Content was paraphrased for
> licensing compliance.

### 🔴 Audit claim was misclassified

| Audit claim | Reality on dev | Why misclassified |
|-------------|----------------|-------------------|
| **P3 — "Manual `content_filter` injection detection (regex)" → use `LangChain InjectedState` + guard middleware** | The regex in `telegram_bot/graph/nodes/guard.py` is a **prompt-injection security heuristic** (21+ patterns, EN+RU, three guard modes hard/soft/log). `InjectedState` is a LangChain primitive for injecting **graph state into tool calls**. The two solve different problems and are not substitutable. | Concept conflation. `InjectedState` is not a prompt-injection detector. The right SDK-comparison for guard.py is "LangChain has no canonical prompt-injection guard"; the closest community options (LLM Guard, Rebuff, OpenAI moderation) are not in the registry today. |

### 🟠 Still open — real follow-up items

| ID | Issue body claim | Status | Recommended next step |
|----|------------------|--------|------------------------|
| **P1** | `build_graph()` — voice path uses 11-node custom `StateGraph` while text path uses `create_agent` SDK | **still-open**: `telegram_bot/graph/graph.py:100` builds a raw `StateGraph(RAGState, context_schema=GraphContext)` with conditional edges around guard/classify/rewrite/retrieve/cache/rerank/grade/respond/transcribe nodes | Tracked by **#1535** (currently `status:blocked`). Plan migration to `create_agent` with `before_model` / `tools` middleware. ADR [0010](../adr/0010-voice-path-create-agent-migration-plan.md) already exists. |

The original issue body listed P1 only once; everything else under "Custom
code that HAS an SDK equivalent" reduces to one of the closed-on-dev or
misclassified rows above.

## Bot.py size — informational

The audit body cited `bot.py` at ~5099 lines. As of `dev` `51e52fd9` the file
is **4987 lines** (slight reduction). Decomposition is tracked separately under
**#1265**. Not directly an SDK-native question.

## Recommendations for #1538

1. **Close the issue** as substantially completed; the only live item is P1
   (voice path migration) which is already tracked under #1535.
2. **Pin the streaming claim** with a contract test so a regression to a
   custom polling abstraction is caught at PR time. Implemented in
   `tests/contract/test_streaming_sdk_native_contract.py` in this same PR.
3. **Update the registry** entry for guard.py so future audits don't repeat
   the `InjectedState` confusion. (Not done in this PR — out of scope; raise
   a docs follow-up if desired.)

## Refs

- #1538 — original audit (this doc refreshes it).
- #1535 — voice path migration to `create_agent` (P1 follow-up).
- #1671 — historical PR that already moved DraftStreamer's behaviour into
  `_stream_agent_to_draft` with native `stream_mode`.
- #1265 — `bot.py` decomposition (separate from SDK question).
- [`sdk-registry.md`](sdk-registry.md) — canonical SDK lookup.
- ADR [0010](../adr/0010-voice-path-create-agent-migration-plan.md) — voice
  path migration plan.
- ADR [0012](../adr/0012-langgraph-orchestration.md) — LangGraph
  orchestration choices.
