---
paths: "**/llm*.py, docker/litellm/**, src/contextualization/**, **/generate.py"
---

# LLM Integration

LiteLLM proxy, model routing, fallbacks, guardrails, and answer generation.

## Purpose

Route LLM requests through LiteLLM proxy with automatic fallback chain and observability.

## Architecture

```
Bot/Graph → LLMService (OpenAI SDK) → LiteLLM Proxy (:4000) → Cerebras/Groq/OpenAI
          → generate_node (ChatLiteLLM) → LiteLLM Proxy      → Langfuse OTEL tracing
```

## Key Files

| File | Description |
|------|-------------|
| `docker/litellm/config.yaml` | Model list, router settings |
| `telegram_bot/services/llm.py` | LLMService class (OpenAI SDK, `langfuse.openai.AsyncOpenAI`) |
| `telegram_bot/services/query_analyzer.py` | QueryAnalyzer (OpenAI SDK) |
| `telegram_bot/services/query_preprocessor.py` | HyDEGenerator (OpenAI SDK) |
| `telegram_bot/graph/nodes/generate.py` | LangGraph generate_node (ChatLiteLLM via langchain) |
| `telegram_bot/graph/nodes/rewrite.py` | LangGraph rewrite_node (ChatLiteLLM) |
| `telegram_bot/graph/config.py` | GraphConfig — `create_llm()` factory |
| `telegram_bot/integrations/langfuse.py` | `create_langfuse_handler()` for LangGraph callbacks |

## Two LLM Patterns

| Pattern | Used By | Client | Tracing |
|---------|---------|--------|---------|
| **OpenAI SDK** | LLMService, QueryAnalyzer, HyDEGenerator | `langfuse.openai.AsyncOpenAI` | Auto (drop-in) |
| **ChatLiteLLM** | generate_node, rewrite_node | `langchain_community.ChatLiteLLM` | Via LangGraph callback |

## Model Routing

| Model Name | Provider | Actual Model |
|------------|----------|--------------|
| `gpt-4o-mini` | Cerebras | zai-glm-4.7 (primary) |
| `gpt-4o-mini-fallback` | Groq | llama-3.1-70b |
| `gpt-4o-mini-openai` | OpenAI | gpt-4o-mini |

## Fallback Chain

```
Cerebras → [error] → Groq → [error] → OpenAI
```

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `LLM_BASE_URL` | http://litellm:4000 | LiteLLM proxy URL |
| `LLM_MODEL` | gpt-4o-mini | Model alias |
| `max_tokens` | 4096 | Response length limit |
| `temperature` | 0.7 | For generate_node and LLMService |

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

## generate_node (LangGraph)

`telegram_bot/graph/nodes/generate.py` — LLM answer generation as a LangGraph node.

- Builds system prompt with domain from `GraphConfig.from_env().domain`
- Formats top-5 documents as context (title, city, price, score)
- Includes conversation history from `state["messages"]`
- Calls LLM via `ChatLiteLLM.ainvoke()` (langchain-community)
- Falls back to document summary if LLM unavailable
- Records `latency_stages["generate"]`

## Langfuse Integration

Two tracing paths:

1. **OpenAI SDK services** — `langfuse.openai.AsyncOpenAI` auto-traces all `chat.completions.create()` calls
2. **LangGraph pipeline** — `create_langfuse_handler()` returns `langfuse.langchain.CallbackHandler`, passed as `config={"callbacks": [handler]}` to `graph.ainvoke()`

Graceful degradation: returns `None` if `LANGFUSE_SECRET_KEY` not set.

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
| `LiteLLM unhealthy` | Wait 30s, check `docker logs dev-litellm` |
| All providers fail | Check API keys in `.env` |
| Slow responses | Cerebras is fastest, check fallback didn't trigger |

## Development Guide

### Adding new LLM provider

1. Add model to `docker/litellm/config.yaml`
2. Add to fallback chain if needed
3. Add API key to `.env`
4. Restart LiteLLM: `docker compose restart litellm`
