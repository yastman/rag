# Shim Cleanup Checklist

Статус: blocked until runtime core path is stable
Дата: 2026-06-08

`CORE-010` нельзя завершать до тех пор, пока generation/RAG/runtime pipeline и
Telegram adapter rollout не пройдут ревью. До этого shims являются rollback
механизмом.

## Transitional Shims / Couplings

- `telegram_bot/services/grounding_policy.py` -> `src.runtime.grounding.policy`
- `telegram_bot/agents/rag_pipeline.py` -> `src.runtime.pipeline.rag`
- `src/runtime/pipeline/rag.py` -> legacy helper modules under `telegram_bot.services.*`
- `src/runtime/pipeline/assistant_pipeline.py` -> legacy `telegram_bot.services.generate_response`
- `src/runtime/graph/builder.py` default factory -> `telegram_bot.graph.graph:build_graph`

## Cleanup Conditions

1. `src.runtime.generation` owns the full core generation implementation.
2. `src.runtime.pipeline.rag` no longer depends on helper modules under `telegram_bot.services.*`.
3. `src.runtime.pipeline.assistant_pipeline` has no `telegram_bot.*` executable strings.
4. Telegram text path can render `AssistantResult` with rollback removed.
5. `tests/data/known_runtime_telegram_bot_couplings.json` is empty or removed.
6. README/design docs no longer describe transitional shims as active runtime paths.

## Cleanup Rule

Remove one shim per PR and run the focused contract/static checks for that seam.
