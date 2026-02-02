---
paths: "**/llm*.py, docker/litellm/**, src/contextualization/**"
---

***REMOVED*** LLM Integration

LiteLLM proxy, model routing, fallbacks, guardrails, and answer generation.

***REMOVED******REMOVED*** Purpose

Route LLM requests through LiteLLM proxy with automatic fallback chain and observability.

***REMOVED******REMOVED*** Architecture

```
Bot → LLMService → LiteLLM Proxy (:4000) → Cerebras/Groq/OpenAI
                                        → Langfuse OTEL tracing
```

***REMOVED******REMOVED*** Key Files

| File | Line | Description |
|------|------|-------------|
| `docker/litellm/config.yaml` | 1 | Model list, router settings |
| `telegram_bot/services/llm.py` | 15 | LLMService class |
| `src/contextualization/base.py` | - | BaseContextualizer |
| `src/contextualization/openai.py` | - | OpenAI implementation |

***REMOVED******REMOVED*** Model Routing

| Model Name | Provider | Actual Model |
|------------|----------|--------------|
| `gpt-4o-mini` | Cerebras | zai-glm-4.7 (primary) |
| `gpt-4o-mini-fallback` | Groq | llama-3.1-70b |
| `gpt-4o-mini-openai` | OpenAI | gpt-4o-mini |

***REMOVED******REMOVED*** Fallback Chain

```
Cerebras → [error] → Groq → [error] → OpenAI
```

Configured in `docker/litellm/config.yaml`:

```yaml
router_settings:
  fallbacks:
    - gpt-4o-mini: [gpt-4o-mini-fallback, gpt-4o-mini-openai]
  retry_policy:
    retry_count: 2
```

***REMOVED******REMOVED*** Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `LLM_BASE_URL` | http://litellm:4000 | LiteLLM proxy URL |
| `LLM_MODEL` | gpt-4o-mini | Model alias |
| `max_tokens` | 1024 | Response length limit |
| `temperature` | 0.0 | For deterministic responses |

***REMOVED******REMOVED*** Common Patterns

***REMOVED******REMOVED******REMOVED*** LLMService usage

```python
from telegram_bot.services.llm import LLMService

llm = LLMService(
    api_key=litellm_key,
    base_url="http://localhost:4000",
    model="gpt-4o-mini",
)

***REMOVED*** Generate answer from context
answer = await llm.generate_answer(
    question="Какие квартиры в Несебре?",
    context_chunks=search_results,
    system_prompt=None,  ***REMOVED*** Uses default Bulgarian RE prompt
)
```

***REMOVED******REMOVED******REMOVED*** Streaming response

```python
async for chunk in llm.generate_stream(question, context):
    await message.edit_text(accumulated + chunk)
```

***REMOVED******REMOVED******REMOVED*** Custom system prompt

```python
answer = await llm.generate_answer(
    question=query,
    context_chunks=results,
    system_prompt="Ты эксперт по недвижимости. Отвечай кратко.",
)
```

***REMOVED******REMOVED*** Default System Prompt

```
Ты - ассистент по недвижимости в Болгарии.
Отвечай на вопросы пользователя на основе предоставленного контекста.
Если информации недостаточно, честно скажи об этом.
Всегда указывай цены в евро и расстояния в метрах.
Будь вежливым и полезным.
Форматируй ответ с Markdown: используй **жирный** для важного, • для списков.
```

***REMOVED******REMOVED*** Guardrails

***REMOVED******REMOVED******REMOVED*** Confidence Scoring

LLMService returns confidence scores with responses:

```python
from telegram_bot.services.llm import LLMService, LOW_CONFIDENCE_THRESHOLD

result = await llm.generate_with_confidence(question, context)
***REMOVED*** result.answer, result.confidence, result.sources

if result.confidence < LOW_CONFIDENCE_THRESHOLD:  ***REMOVED*** 0.3
    return create_low_confidence_response(result)
```

***REMOVED******REMOVED******REMOVED*** Off-Topic Detection

QueryRouter detects off-topic queries (non-real-estate):

```python
from telegram_bot.services.query_router import classify_query, QueryType, get_off_topic_response

if classify_query(query) == QueryType.OFF_TOPIC:
    return get_off_topic_response()  ***REMOVED*** "Я специализируюсь на недвижимости..."
```

**Off-topic examples:** recipes, crypto, movies, sports

***REMOVED******REMOVED******REMOVED*** Chaos Testing

Tests for graceful degradation when services fail:

```bash
pytest tests/chaos/ -v
***REMOVED*** test_qdrant_failures.py - Timeout, connection refused
***REMOVED*** test_redis_failures.py - Disconnect, pool exhaustion
***REMOVED*** test_llm_fallback.py - Rate limits, parsing errors
```

***REMOVED******REMOVED*** Langfuse Integration

LiteLLM sends traces to Langfuse via OTEL:

```yaml
litellm_settings:
  callbacks: ["langfuse_otel"]
```

All LLM calls appear in Langfuse UI at http://localhost:3001

***REMOVED******REMOVED*** Dependencies

- Container: `dev-litellm` (4000), 512MB RAM
- Requires: `dev-langfuse` for tracing
- Environment: `CEREBRAS_API_KEY`, `GROQ_API_KEY`, `OPENAI_API_KEY`

***REMOVED******REMOVED*** Testing

```bash
pytest tests/unit/test_llm_service.py -v
```

***REMOVED******REMOVED*** Troubleshooting

| Error | Fix |
|-------|-----|
| `LiteLLM unhealthy` | Wait 30s, check `docker logs dev-litellm` |
| All providers fail | Check API keys in `.env` |
| Slow responses | Cerebras is fastest, check fallback didn't trigger |

***REMOVED******REMOVED*** Development Guide

***REMOVED******REMOVED******REMOVED*** Adding new LLM provider

1. Add model to `docker/litellm/config.yaml`:
```yaml
- model_name: gpt-4o-mini-new
  litellm_params:
    model: provider/model-name
    api_key: os.environ/NEW_API_KEY
```

2. Add to fallback chain if needed
3. Add API key to `.env`
4. Restart LiteLLM: `docker compose restart litellm`
