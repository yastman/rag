# refactor: replace custom DraftStreamer with LangGraph `StreamWriter` + `stream_mode="custom"`

## Source

2026-05-19 cross-domain SDK audit (`.github/issue-drafts/2026-05-19-langfuse-trace-coverage/AUDIT_REPORT.md`, Finding 5).

## Problem

LangGraph 1.x exposes `stream_mode="custom"` plus `StreamWriter` (injected as a node parameter) as the SDK-native way to emit progress events from inside graph nodes — typing indicators, partial drafts, retrieval-progress dots, etc. — without polluting the main `values`/`updates` stream and without coupling streaming logic to Telegram-specific surfaces.

Repo grep:

```bash
$ grep -rn "StreamWriter\|stream_writer\|stream_mode=\"custom\"" telegram_bot/ src/
# (no matches)
```

Today the bot uses **two custom abstractions** for the same job:

1. `telegram_bot/services/draft_streamer.py:DraftStreamer` — Telegram `sendMessageDraft` polling wrapper.
2. `telegram_bot/bot.py:3689-3749 _stream_agent_to_draft` — custom adapter from `agent.astream` to `DraftStreamer`.

Both are flagged in the SDK audit (#1538) as "custom code that has an SDK equivalent". This issue is the concrete proposal.

## Evidence — what's in the repo today

- `telegram_bot/services/draft_streamer.py` — 51 lines, custom polling.
- `telegram_bot/bot.py:3689-3749` — adapter glue tied to aiogram message edits.
- `tests/unit/test_draft_streamer*.py` — tests pinned to the custom abstraction.
- Issue #1538 lists this exact migration as P2.
- Issue #1541 lists `DraftStreamer` as never-instantiated dead code (this audit recommends re-verifying that claim per `audit-clarify-1541-formula-query-not-dead.md`).

## Context7 SDK baseline — `/langchain-ai/langgraph`

```python
# 1) Producer side — emit custom events from inside any graph node
from langgraph.config import get_stream_writer

async def respond_node(state, runtime):
    writer = get_stream_writer()
    writer({"type": "thinking", "stage": "retrieve"})
    docs = await retrieve(state["query"])
    writer({"type": "draft", "text": "Searching apartments..."})
    answer = await generate(docs, state["query"])
    writer({"type": "draft", "text": answer})
    return {"messages": [AIMessage(content=answer)]}

# 2) Consumer side — Telegram bot subscribes to the custom mode
async for event in graph.astream(input, config, stream_mode="custom"):
    # event is the dict the producer wrote
    await dispatch_to_telegram_draft(event)
```

`StreamMode = Literal["values", "updates", "checkpoints", "tasks", "debug", "messages", "custom"]`.

The `"custom"` mode is independent of the main state stream, so producer events don't fight with the canonical state-update stream that the rest of the app already consumes.

## Implementation plan

1. **Producer** — replace direct calls to `DraftStreamer.write(...)` inside graph nodes with `get_stream_writer()(...)`. Producer emits structured events (`{"type": "thinking" | "draft" | "filter_extracted" | ...}`).
2. **Consumer** — refactor `bot.py:_stream_agent_to_draft` into a thin adapter that:
   - calls `graph.astream(input, config, stream_mode=["custom", "messages"])` (multi-mode);
   - dispatches `"custom"` events to `aiogram` message edits;
   - dispatches `"messages"` events for token-level streaming where needed.
3. **Delete** `services/draft_streamer.py` once all producers/consumers are migrated.
4. **Migrate tests** — assertions move from `DraftStreamer.write_called_with(...)` to `graph.astream(stream_mode="custom") yields {...}`.
5. **Pin removed** — `_BACKGROUND_TASKS` set in `funnel.py:263` (#1541) and any other ad-hoc streaming glue.

## Forbidden

- No new custom streaming abstraction.
- No coupling of `aiogram` editing logic into graph node code (graph nodes write to `StreamWriter`, the bot consumes; aiogram concerns stay in `bot.py`).
- Land BEFORE or AFTER #1535 (voice path migration). Order does not matter; both paths can adopt `stream_mode="custom"` independently.

## SDK / Local Baseline

- LangGraph: `1.0.x` per repo's pin.
- `StreamWriter` and `stream_mode="custom"` are stable in LangGraph 1.x.
- `langgraph.config.get_stream_writer()` is the canonical accessor inside async nodes.

## Verification

```bash
uv run pytest tests/unit/test_draft_streamer*.py -q   # adapt or remove
uv run pytest tests/unit/graph -q
uv run pytest tests/unit/test_bot_handlers.py -k "stream" -q
```

Manual: send a long query in dev. Confirm Telegram message edits show retrieval progress + final answer streamed exactly as before, but with no `DraftStreamer` import in the call chain.

## Related

- #1538 — broader SDK-vs-custom audit; this is one of the concrete migrations listed there as P2.
- #1541 — dead-code cleanup includes `DraftStreamer`. After this PR lands, the cleanup is straightforward.
- #1535 — voice path migration to `create_agent`. Orthogonal but synergistic.

## Priority

**P2-backlog** — moderate maintenance win, modest UX consistency win.
