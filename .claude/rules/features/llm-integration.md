---
paths: "**/llm*.py, docker/litellm/**, src/contextualization/**, **/generate.py"
---

# LLM Integration

LiteLLM proxy, model routing, fallbacks, guardrails, and answer generation.

## Purpose

Route LLM requests through LiteLLM proxy with automatic fallback chain and observability.

## Architecture

```
Bot/Graph → All LLM calls (OpenAI SDK) → LiteLLM Proxy (:4000) → Cerebras/Groq/OpenAI
          → langfuse.openai.AsyncOpenAI  → auto-tracing via Langfuse
```

## Key Files

| File | Description |
|------|-------------|
| `docker/litellm/config.yaml` | Model list, router settings |
| `telegram_bot/services/llm.py` | LLMService class (OpenAI SDK, `langfuse.openai.AsyncOpenAI`) |
| `telegram_bot/services/query_analyzer.py` | QueryAnalyzer (OpenAI SDK) |
| `telegram_bot/services/query_preprocessor.py` | HyDEGenerator (OpenAI SDK) |
| `telegram_bot/graph/nodes/generate.py` | LangGraph generate_node (OpenAI SDK via GraphConfig) |
| `telegram_bot/graph/nodes/rewrite.py` | LangGraph rewrite_node (OpenAI SDK via GraphConfig) |
| `telegram_bot/graph/config.py` | GraphConfig — `create_llm()` factory |
| `telegram_bot/observability.py` | `get_client()`, `@observe`, `propagate_attributes` |

## LLM Pattern (unified)

All LLM-calling code uses `langfuse.openai.AsyncOpenAI` (OpenAI SDK drop-in with auto-tracing):

| Used By | Client | Tracing |
|---------|--------|---------|
| LLMService, QueryAnalyzer, HyDEGenerator | `langfuse.openai.AsyncOpenAI` | Auto (drop-in) |
| generate_node, rewrite_node | `GraphConfig.create_llm()` → `AsyncOpenAI` | Auto (drop-in) |

## Model Routing

| Model Name | Provider | Actual Model | Notes |
|------------|----------|--------------|-------|
| `gpt-4o-mini` | Cerebras | gpt-oss-120b (primary) | Reasoning model, 3000 tok/s, `merge_reasoning_content_in_choices: true` |
| `gpt-4o-mini-cerebras-glm` | Cerebras | zai-glm-4.7 | Fallback 1 (former primary) |
| `gpt-4o-mini-fallback` | Groq | llama-3.1-70b-versatile | Fallback 2 |
| `gpt-4o-mini-openai` | OpenAI | gpt-4o-mini | Fallback 3 (reliable) |
| `gpt-oss-120b` | Cerebras | gpt-oss-120b | Standalone alias for benchmarking |
| `whisper` | OpenAI | whisper-1 | STT (audio_transcription mode) |

**Note:** `gpt-oss-120b` sends reasoning tokens as `delta.reasoning` — `merge_reasoning_content_in_choices: true` merges them into `delta.content`.

## Fallback Chain

```
gpt-4o-mini (Cerebras/gpt-oss-120b) → cerebras-glm → Groq → OpenAI
```

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `LLM_BASE_URL` | http://litellm:4000 | LiteLLM proxy URL (local: `http://localhost:4000/v1`) |
| `LLM_MODEL` | gpt-4o-mini | Model alias |
| `SUPERVISOR_MODEL` | gpt-4o-mini | Model for agent routing (BotConfig) |
| `max_tokens` | 4096 | Response length limit |
| `temperature` | 0.7 | For generate_node and LLMService |
| `REWRITE_MODEL` | gpt-4o-mini | Separate model for rewrite_node (defaults to LLM_MODEL) |
| `REWRITE_MAX_TOKENS` | 200 | Max tokens for query rewrite (short output) |
| `STREAMING_ENABLED` | true | Stream generate_node output to Telegram (feature flag) |

## Local Dev (`make run-bot`)

**IMPORTANT:** Bot MUST go through LiteLLM even locally — many components use `gpt-4o-mini` alias which LiteLLM routes to Cerebras. Direct Cerebras URL (`api.cerebras.ai`) → 404 on `gpt-4o-mini`.

`.env` for local dev:
```
LLM_BASE_URL=http://localhost:4000/v1
LLM_API_KEY=sk-litellm-master-dev
```

`make run-bot` uses `uv run --env-file .env` to load env vars into the process (required for Langfuse SDK init via `os.getenv()` in `observability.py`).

## OpenAI SDK Pattern (services)

All LLM-calling services use `langfuse.openai.AsyncOpenAI` drop-in for auto-tracing:

| Service | File | SDK Client |
|---------|------|-----------|
| `LLMService` | `telegram_bot/services/llm.py` | `AsyncOpenAI` |
| `QueryAnalyzer` | `telegram_bot/services/query_analyzer.py` | `AsyncOpenAI` |
| `HyDEGenerator` | `telegram_bot/services/query_preprocessor.py` | `AsyncOpenAI` |

```python
from langfuse.openai import AsyncOpenAI

class MyService:
    def __init__(self, api_key: str, base_url: str, model: str = "gpt-4o-mini"):
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=2, timeout=30.0)

    async def call_llm(self, query: str) -> str:
        response = await self.client.chat.completions.create(
            model=self.model, messages=[...],
            name="my-operation",  # type: ignore[call-overload]  # langfuse kwarg
        )
        return response.choices[0].message.content
```

### Error handling

```python
except (openai.APIConnectionError, openai.RateLimitError, openai.APITimeoutError) as e:
    logger.error("API error: %s", e)
    return fallback_value
```

## Contextualization Module (`src/contextualization/`)

Enriches document chunks with LLM-generated summaries before indexing to improve retrieval quality.

| File | Provider | Notes |
|------|----------|-------|
| `src/contextualization/base.py` | — | `ContextualizeProvider` ABC, `ContextualizedChunk` dataclass |
| `src/contextualization/openai.py` | OpenAI | `OpenAIContextualizer`, ~$0.008-0.012/chunk |
| `src/contextualization/claude.py` | Anthropic | `ClaudeContextualizer` |
| `src/contextualization/groq.py` | Groq | `GroqContextualizer` |

**Impact:** +2-5% Recall@1, +0.5-1% NDCG@10. Used during ingestion (optional, not in default CocoIndex flow).

## generate_node (LangGraph)

`telegram_bot/graph/nodes/generate.py` — LLM answer generation as a LangGraph node.

- Builds system prompt with domain from `GraphConfig.from_env().domain`
- Formats top-5 documents as context (title, city, price, score)
- Includes conversation history from `state["messages"]`
- **Streaming path** (when `message` injected + `streaming_enabled`): sends placeholder → streams via `stream=True` → edits Telegram message every 300ms → finalizes with Markdown → sets `response_sent=True`
- **Non-streaming path**: calls `create_llm().chat.completions.create()` (OpenAI SDK)
- Falls back to non-streaming if streaming fails, then to document summary if LLM unavailable
- Records `latency_stages["generate"]` (seconds)

## rewrite_node (LangGraph)

`telegram_bot/graph/nodes/rewrite.py` — LLM query reformulation for better retrieval.

- Uses `config.rewrite_model` and `config.rewrite_max_tokens` (separate from generate)
- Sets `rewrite_effective=False` if LLM returns empty/unchanged content
- `route_grade` checks `rewrite_effective` before allowing another retry
- Resets `query_embedding=None` to force re-embedding after rewrite
- Records `latency_stages["rewrite"]` (seconds)

## Langfuse Integration

All LLM calls auto-traced via `langfuse.openai.AsyncOpenAI` drop-in. Graph-level tracing uses `@observe` decorator + `propagate_attributes()` context manager (Langfuse SDK v3). Scores written via `_write_langfuse_scores()` in `bot.py`.

Graceful degradation: `_NullLangfuseClient` stub when `LANGFUSE_SECRET_KEY` not set. Langfuse SDK v3 also self-disables without credentials (`@observe` works as passthrough).

**Note:** `LANGFUSE_SECRET_KEY` must be in process env (not just `.env` file) — `observability.py` checks `os.getenv()` at import time. `uv run --env-file .env` handles this.

## Guardrails

### Confidence Scoring (LLMService)

```python
result = await llm.generate_answer(question, context, with_confidence=True)
# result.answer, result.confidence, result.is_low_confidence
```

### Off-Topic Detection

Handled by `classify_node` (6-type taxonomy) in the LangGraph pipeline.

## Dependencies

- Container: `dev-litellm` (4000), 512MB RAM
- Requires: `dev-langfuse` for tracing
- Environment: `CEREBRAS_API_KEY`, `GROQ_API_KEY`, `OPENAI_API_KEY`

## Testing

```bash
pytest tests/unit/test_llm_service.py -v
pytest tests/unit/services/test_query_analyzer.py -v
pytest tests/unit/test_hyde.py -v
pytest tests/unit/graph/test_generate_node.py -v
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| `Model gpt-4o-mini does not exist` (404) | `LLM_BASE_URL` points directly to Cerebras — must go through LiteLLM |
| `LiteLLM unhealthy` / preflight 404 | Preflight strips `/v1` from URL for health check. Verify: `curl localhost:4000/health/liveliness` |
| Langfuse traces missing | `LANGFUSE_SECRET_KEY` not in process env — use `uv run --env-file .env` |
| All providers fail | Check API keys in `.env` |
| Slow responses | Cerebras is fastest, check fallback didn't trigger |

## Development Guide

### Adding new LLM provider

1. Add model to `docker/litellm/config.yaml`
2. Add to fallback chain if needed
3. Add API key to `.env`
4. Restart LiteLLM: `docker compose restart litellm`
