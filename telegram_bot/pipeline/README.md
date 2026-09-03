# telegram_bot/pipeline/

The bot's query pipeline, pre-agent helpers, and streaming helpers — extracted from
`telegram_bot/bot.py` (`card_2a71ec058138`, split #2816).

> **Not to be confused with [`../pipelines/`](../pipelines/)** (plural): `pipelines/` holds the
> client-direct entrypoints. This `pipeline/` (singular) is the supervisor-driven query path
> lifted out of the `bot.py` god-object.

## Files

| File | Purpose |
|------|---------|
| [`supervisor.py`](./supervisor.py) | Query pipeline handlers: `handle_query`, apartment fast-path, client-direct path, pre-agent cache hit, supervisor stream/invoke with recovery, final-trace write |
| [`pre_agent.py`](./pre_agent.py) | Pre-agent helpers (cache/grounding decisions before the agent runs) |
| [`streaming.py`](./streaming.py) | Streaming-response helpers |

## Boundaries

- Delegates retrieval/generation to `src/runtime/` and the agent layer; it wires Telegram
  handling to the engine, it does not query Qdrant or run prompts directly.
- Behaviour is byte-for-byte with the pre-extract `bot.py` functions (regression-guarded).

## See Also

- [`../README.md`](../README.md) — Telegram transport overview
- [`../pipelines/README.md`](../pipelines/README.md) — client-direct paths
- [`../agents/README.md`](../agents/README.md) — agent SDK tools
