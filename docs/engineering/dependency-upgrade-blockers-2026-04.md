# Dependency Upgrade Blockers

- `langfuse`: held at `3.14.6` instead of `4.x` because the current codebase still uses v3-only APIs such as `update_current_trace`, `start_as_current_span`, and `LangchainCallbackHandler(update_trace=...)`. Next step: migrate tracing/observation calls in `src/evaluation/langfuse_integration.py`, `telegram_bot/observability.py`, `src/voice/observability.py`, `src/ingestion/unified/observability.py`, `src/api/main.py`, `telegram_bot/bot.py`, and `telegram_bot/middlewares/langfuse_middleware.py`, then re-run the bot/LangGraph wave.
