# LiteLLM Proxy Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Install and configure LiteLLM Proxy as centralized LLM Gateway with failover and Langfuse integration.

**Architecture:** LiteLLM Proxy runs as Docker container, receives all LLM requests from bot, routes to Cerebras (primary) with automatic failover to Groq/OpenAI, logs everything to Langfuse.

**Tech Stack:** LiteLLM v1.81.3.rc.3, Docker, PostgreSQL, Langfuse

---

## Task 1: Create LiteLLM config directory and config.yaml

**Files:**
- Create: `docker/litellm/config.yaml`

**Step 1: Create directory**

Run: `mkdir -p docker/litellm`
Expected: Directory created (no output)

**Step 2: Create config.yaml with model list, fallbacks, Langfuse**

Create file `docker/litellm/config.yaml`:

```yaml
# LiteLLM Proxy Configuration
# Docs: https://docs.litellm.ai/docs/proxy/configs
# Version: v1.81.3.rc.3

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

**Step 3: Verify file created**

Run: `cat docker/litellm/config.yaml | head -20`
Expected: First 20 lines of config displayed

**Step 4: Commit**

```bash
git add docker/litellm/config.yaml
git commit -m "feat(litellm): add proxy config with models and fallbacks"
```

---

## Task 2: Add litellm database to postgres init script

**Files:**
- Modify: `docker/postgres/init/00-init-databases.sql`

**Step 1: Add litellm database creation**

Add to end of `docker/postgres/init/00-init-databases.sql`:

```sql
-- Database for LiteLLM (LLM Gateway)
CREATE DATABASE litellm;
GRANT ALL PRIVILEGES ON DATABASE litellm TO postgres;
```

**Step 2: Verify changes**

Run: `cat docker/postgres/init/00-init-databases.sql`
Expected: File contains langfuse, mlflow, and litellm databases

**Step 3: Commit**

```bash
git add docker/postgres/init/00-init-databases.sql
git commit -m "feat(postgres): add litellm database"
```

---

## Task 3: Add LiteLLM service to docker-compose.dev.yml

**Files:**
- Modify: `docker-compose.dev.yml`

**Step 1: Add litellm service after mlflow section**

Insert after line 221 (after mlflow healthcheck closing brace), before TELEGRAM BOT section:

```yaml

  litellm:
    image: ghcr.io/berriai/litellm:v1.81.3.rc.3
    container_name: dev-litellm
    ports:
      - "4000:4000"
    volumes:
      - ./docker/litellm/config.yaml:/app/config.yaml:ro
    environment:
      # Auth
      LITELLM_MASTER_KEY: ${LITELLM_MASTER_KEY:-sk-litellm-master-dev}
      # LLM Providers
      CEREBRAS_API_KEY: ${CEREBRAS_API_KEY:-${LLM_API_KEY}}
      GROQ_API_KEY: ${GROQ_API_KEY}
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      # Langfuse (Docker internal network)
      LANGFUSE_PUBLIC_KEY: ${LANGFUSE_PUBLIC_KEY:-pk-lf-dev}
      LANGFUSE_SECRET_KEY: ${LANGFUSE_SECRET_KEY:-sk-lf-dev}
      LANGFUSE_HOST: http://langfuse:3000
      # Database for virtual keys
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
    deploy:
      resources:
        limits:
          memory: 512M
```

**Step 2: Verify YAML syntax**

Run: `python -c "import yaml; yaml.safe_load(open('docker-compose.dev.yml'))"`
Expected: No output (valid YAML)

**Step 3: Commit**

```bash
git add docker-compose.dev.yml
git commit -m "feat(docker): add litellm proxy service"
```

---

## Task 4: Update bot service to use LiteLLM

**Files:**
- Modify: `docker-compose.dev.yml`

**Step 1: Update bot environment variables**

In bot service (line ~227-265), change LLM environment variables:

Replace:
```yaml
      # LLM (Cerebras)
      LLM_API_KEY: ${LLM_API_KEY:-${CEREBRAS_API_KEY}}
      LLM_BASE_URL: ${LLM_BASE_URL:-https://api.cerebras.ai/v1}
      LLM_MODEL: ${LLM_MODEL:-qwen-3-32b}
```

With:
```yaml
      # LLM (via LiteLLM Proxy)
      LLM_API_KEY: ${LITELLM_MASTER_KEY:-sk-litellm-master-dev}
      LLM_BASE_URL: http://litellm:4000
      LLM_MODEL: gpt-4o-mini
```

**Step 2: Add litellm to bot depends_on**

In bot service depends_on section, add after user-base:

```yaml
      litellm:
        condition: service_healthy
```

**Step 3: Verify YAML syntax**

Run: `python -c "import yaml; yaml.safe_load(open('docker-compose.dev.yml'))"`
Expected: No output (valid YAML)

**Step 4: Commit**

```bash
git add docker-compose.dev.yml
git commit -m "feat(bot): route LLM requests through litellm proxy"
```

---

## Task 5: Update .env.example with LiteLLM variables

**Files:**
- Modify: `.env.example`

**Step 1: Add LiteLLM section after Voyage AI section**

Insert after line 61 (after VOYAGE_RERANK_MODEL), before E2E TESTING section:

```bash

# =============================================================================
# LITELLM PROXY (LLM Gateway)
# =============================================================================
# Master key for LiteLLM authentication
LITELLM_MASTER_KEY=sk-litellm-master-dev

# Primary LLM provider (Cerebras)
CEREBRAS_API_KEY=your-cerebras-key-here

# Fallback providers are OPENAI_API_KEY and GROQ_API_KEY (already defined above)
```

**Step 2: Verify file is valid**

Run: `head -80 .env.example`
Expected: Shows new LiteLLM section

**Step 3: Commit**

```bash
git add .env.example
git commit -m "docs(env): add litellm proxy configuration variables"
```

---

## Task 6: Test LiteLLM deployment

**Files:**
- None (verification only)

**Step 1: Reset postgres volume (for new database)**

Run: `docker compose -f docker-compose.dev.yml down -v postgres`
Expected: Postgres volume removed

**Step 2: Start core services**

Run: `docker compose -f docker-compose.dev.yml up -d postgres redis qdrant`
Expected: Services starting

**Step 3: Wait for postgres healthy**

Run: `docker compose -f docker-compose.dev.yml ps postgres`
Expected: Status shows "healthy"

**Step 4: Start langfuse and litellm**

Run: `docker compose -f docker-compose.dev.yml up -d langfuse litellm`
Expected: Services starting

**Step 5: Check LiteLLM logs**

Run: `docker logs dev-litellm --tail 50`
Expected: Shows "LiteLLM Proxy running on http://0.0.0.0:4000"

**Step 6: Verify LiteLLM health endpoint**

Run: `curl -s http://localhost:4000/health/liveliness`
Expected: `{"status":"healthy"}` or similar JSON

**Step 7: Test LLM call through proxy**

Run:
```bash
curl -s -X POST http://localhost:4000/chat/completions \
  -H "Authorization: Bearer sk-litellm-master-dev" \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Say hello"}], "max_tokens": 10}'
```
Expected: JSON response with LLM completion

**Step 8: Verify Langfuse receives logs**

Open: http://localhost:3001
Expected: LiteLLM trace appears in Langfuse dashboard

**Step 9: Start bot and test full flow**

Run: `docker compose -f docker-compose.dev.yml up -d bot`
Expected: Bot starts and connects

---

## Verification Checklist

After all tasks complete, verify:

- [ ] `docker/litellm/config.yaml` exists with correct content
- [ ] `docker-compose.dev.yml` has litellm service
- [ ] Bot uses `http://litellm:4000` as LLM_BASE_URL
- [ ] `.env.example` documents LITELLM_MASTER_KEY and CEREBRAS_API_KEY
- [ ] LiteLLM health endpoint returns healthy
- [ ] LLM calls work through proxy
- [ ] Traces appear in Langfuse

---

## Rollback

If issues occur:

```bash
# Stop litellm
docker compose -f docker-compose.dev.yml stop litellm

# Revert bot to direct Cerebras (edit docker-compose.dev.yml)
# LLM_BASE_URL: https://api.cerebras.ai/v1
# LLM_API_KEY: ${CEREBRAS_API_KEY}

# Restart bot
docker compose -f docker-compose.dev.yml restart bot
```
