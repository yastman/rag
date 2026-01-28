# LiteLLM Proxy Design

**Date:** 2026-01-28
**Status:** Approved
**Version:** LiteLLM v1.81.3.rc.3

## Overview

Установка LiteLLM Proxy как централизованного LLM Gateway для Telegram бота с failover между провайдерами и интеграцией с Langfuse для трекинга.

## Architecture

```
Текущая схема:
┌─────────┐     httpx      ┌──────────────┐
│   Bot   │ ──────────────→│  Cerebras    │
│ LLMSvc  │                │  (GLM-4)     │
└─────────┘                └──────────────┘

Новая схема:
┌─────────┐    httpx     ┌──────────┐     ┌──────────────┐
│   Bot   │ ───────────→ │ LiteLLM  │ ──→ │  Cerebras    │
│ LLMSvc  │              │  Proxy   │     │  (primary)   │
└─────────┘              │  :4000   │     └──────────────┘
                         │          │     ┌──────────────┐
                         │          │ ──→ │  Groq        │
                         │          │     │  (fallback)  │
                         │          │     └──────────────┘
                         │          │     ┌──────────────┐
                         │          │ ──→ │  OpenAI      │
                         │          │     │  (fallback)  │
                         │          │     └──────────────┘
                         │          │     ┌──────────────┐
                         │          │ ──→ │  Langfuse    │
                         └──────────┘     │  (logging)   │
                                          └──────────────┘
```

## Benefits

| Benefit | Description |
|---------|-------------|
| **Failover** | Автоматическое переключение Cerebras → Groq → OpenAI |
| **Centralized Logging** | Все LLM вызовы в Langfuse |
| **Hot Config** | Смена модели без редеплоя кода |
| **Virtual Keys** | Бот не знает реальных API ключей |
| **UI Dashboard** | Мониторинг на http://localhost:4000/ui |

## Files to Create/Modify

### NEW: docker/litellm/config.yaml

```yaml
# LiteLLM Proxy Configuration
# Docs: https://docs.litellm.ai/docs/proxy/configs

model_list:
  # Primary: Cerebras (текущий провайдер)
  - model_name: gpt-4o-mini
    litellm_params:
      model: openai/zai-glm-4.7
      api_base: https://api.cerebras.ai/v1
      api_key: os.environ/CEREBRAS_API_KEY

  # Fallback 1: Groq (быстрый, бесплатный tier)
  - model_name: gpt-4o-mini-fallback
    litellm_params:
      model: groq/llama-3.1-70b-versatile
      api_key: os.environ/GROQ_API_KEY

  # Fallback 2: OpenAI (надёжный)
  - model_name: gpt-4o-mini-openai
    litellm_params:
      model: openai/gpt-4o-mini
      api_key: os.environ/OPENAI_API_KEY

# Автоматический fallback при ошибках
router_settings:
  fallbacks:
    - gpt-4o-mini: [gpt-4o-mini-fallback, gpt-4o-mini-openai]
  retry_policy:
    retry_count: 2

# Langfuse интеграция
litellm_settings:
  callbacks: ["langfuse"]

# Environment variables для Langfuse
environment_variables:
  LANGFUSE_PUBLIC_KEY: os.environ/LANGFUSE_PUBLIC_KEY
  LANGFUSE_SECRET_KEY: os.environ/LANGFUSE_SECRET_KEY
  LANGFUSE_HOST: os.environ/LANGFUSE_HOST
```

### EDIT: docker-compose.dev.yml

Add litellm service:

```yaml
  litellm:
    image: ghcr.io/berriai/litellm:v1.81.3.rc.3
    container_name: dev-litellm
    ports:
      - "4000:4000"
    volumes:
      - ./docker/litellm/config.yaml:/app/config.yaml:ro
    environment:
      LITELLM_MASTER_KEY: ${LITELLM_MASTER_KEY:-sk-litellm-master-dev}
      CEREBRAS_API_KEY: ${CEREBRAS_API_KEY:-${LLM_API_KEY}}
      GROQ_API_KEY: ${GROQ_API_KEY}
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      LANGFUSE_PUBLIC_KEY: ${LANGFUSE_PUBLIC_KEY:-pk-lf-dev}
      LANGFUSE_SECRET_KEY: ${LANGFUSE_SECRET_KEY:-sk-lf-dev}
      LANGFUSE_HOST: http://langfuse:3000
      DATABASE_URL: postgresql://postgres:postgres@postgres:5432/litellm
    command: ["--config", "/app/config.yaml", "--detailed_debug"]
    depends_on:
      postgres:
        condition: service_healthy
      langfuse:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:4000/health/liveliness"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
```

Update bot service:

```yaml
  bot:
    environment:
      LLM_BASE_URL: http://litellm:4000
      LLM_API_KEY: ${LITELLM_MASTER_KEY:-sk-litellm-master-dev}
      LLM_MODEL: gpt-4o-mini
    depends_on:
      litellm:
        condition: service_healthy
```

### EDIT: .env.example

Add new variables:

```bash
# =============================================================================
# LITELLM PROXY (LLM Gateway)
# =============================================================================
LITELLM_MASTER_KEY=sk-litellm-master-dev
CEREBRAS_API_KEY=your-cerebras-key

# Fallback providers (recommended)
GROQ_API_KEY=your-groq-key
# OPENAI_API_KEY already defined above
```

### EDIT: .env (user's local file)

```bash
# Add:
LITELLM_MASTER_KEY=sk-litellm-master-dev
CEREBRAS_API_KEY=<your-actual-key>
GROQ_API_KEY=<your-actual-key>

# Modify for local dev without Docker:
LLM_BASE_URL=http://localhost:4000
LLM_API_KEY=sk-litellm-master-dev
LLM_MODEL=gpt-4o-mini
```

## Implementation Tasks

### Task 1: Create LiteLLM config directory and file
- Create `docker/litellm/` directory
- Create `docker/litellm/config.yaml` with model list, fallbacks, Langfuse callback

### Task 2: Add LiteLLM service to docker-compose.dev.yml
- Add litellm service with image v1.81.3.rc.3
- Configure environment variables
- Add healthcheck
- Add depends_on for postgres and langfuse

### Task 3: Update bot service in docker-compose.dev.yml
- Change LLM_BASE_URL to http://litellm:4000
- Change LLM_API_KEY to use LITELLM_MASTER_KEY
- Change LLM_MODEL to gpt-4o-mini
- Add depends_on litellm

### Task 4: Update .env.example
- Add LITELLM_MASTER_KEY
- Add CEREBRAS_API_KEY
- Document GROQ_API_KEY as fallback

### Task 5: Create litellm database in postgres init
- Add litellm database creation to docker/postgres/init script

### Task 6: Test deployment
- `docker compose -f docker-compose.dev.yml up -d`
- Verify LiteLLM health: http://localhost:4000/health
- Verify LiteLLM UI: http://localhost:4000/ui
- Test bot with sample query
- Verify logs appear in Langfuse

## Verification Commands

```bash
# Start stack
docker compose -f docker-compose.dev.yml up -d

# Check LiteLLM health
curl http://localhost:4000/health/liveliness

# Test LLM call through proxy
curl -X POST http://localhost:4000/chat/completions \
  -H "Authorization: Bearer sk-litellm-master-dev" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Hello"}]
  }'

# Check logs
docker logs dev-litellm -f

# Open UI
open http://localhost:4000/ui
```

## Rollback Plan

If issues occur:

1. Stop litellm: `docker compose -f docker-compose.dev.yml stop litellm`
2. Revert bot environment variables to direct Cerebras connection
3. Restart bot: `docker compose -f docker-compose.dev.yml restart bot`

## Future Enhancements

- [ ] Add budget limits per user
- [ ] Add rate limiting rules
- [ ] Add more fallback providers (Anthropic, Together)
- [ ] Enable caching for repeated queries
- [ ] Add custom cost tracking
