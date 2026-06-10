# LiteLLM SDK router

The runtime chat path uses the LiteLLM Python SDK in-process instead of the
former Docker LiteLLM proxy service. `src.runtime.llm.router` owns the migrated
model aliases, retry count, and fallback chain:

- `gpt-4o-mini` → `cerebras/zai-glm-4.7` with reasoning disabled for low TTFT.
- `gpt-4o-mini-cerebras-oss` → `cerebras/gpt-oss-120b`.
- `gpt-4o-mini-fallback` → `groq/llama-3.1-70b-versatile`.
- `gpt-4o-mini-openai` → `openai/gpt-4o-mini`.

Provider credentials are read directly by the application container from
`CEREBRAS_API_KEY`, `GROQ_API_KEY`, and `OPENAI_API_KEY`. `LLM_API_KEY` remains
as a backwards-compatible fallback for Cerebras during rollout, but
`LITELLM_MASTER_KEY` and `LLM_BASE_URL` are no longer required for the bot chat
path.

Whisper STT does not use LiteLLM routing. Telegram demo transcription uses the
OpenAI SDK directly with `OPENAI_API_KEY` because the removed Docker proxy no
longer hosts a `whisper` alias.
