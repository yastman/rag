# Fast Doc Search

Quick search patterns and task-oriented lookups. Use these commands from the repo root to find the right canonical doc without browsing the tree manually.

## By Request Type

### "Study recent Langfuse traces"

Start with the runbook, then search related code:

```bash
# Runbook
cat docs/runbooks/LANGFUSE_TRACING_GAPS.md

# Trace spans and scoring in source
rg -n "Langfuse|trace|observation|score" telegram_bot/graph/ telegram_bot/services/ src/api/ src/evaluation/
```

See also: [`observability-and-storage.md`](observability-and-storage.md#langfuse-traces)

### "Inspect Qdrant issues"

```bash
# Runbook
cat docs/runbooks/QDRANT_TROUBLESHOOTING.md

# Stack reference
cat docs/QDRANT_STACK.md

# Collection policy and runtime integration
rg -n "Qdrant|collection|vector" telegram_bot/services/ src/ingestion/unified/ src/config/
```

See also: [`observability-and-storage.md`](observability-and-storage.md#qdrant)

### "Inspect Redis/cache issues"

```bash
# Runbook
cat docs/runbooks/REDIS_CACHE_DEGRADATION.md

# Cache architecture and thresholds
cat docs/TROUBLESHOOTING_CACHE.md

# Redis integration and cache tiers
rg -n "Redis|cache|redis-cli" telegram_bot/integrations/ telegram_bot/services/ src/
```

See also: [`observability-and-storage.md`](observability-and-storage.md#redis-and-cache)

### "Understand Docker services"

```bash
# Canonical source of truth
cat DOCKER.md

# Service containers index
cat services/README.md

# Compose validation
make verify-compose-images
```

See also: [`runtime-services.md`](runtime-services.md#docker-services)

### "Understand ingestion"

```bash
# Runbook and guide
cat docs/INGESTION.md
cat docs/GDRIVE_INGESTION.md

# Pipeline code
rg -n "ingestion|cocoindex|docling" src/ingestion/unified/

# CLI help
uv run python -m src.ingestion.unified.cli --help
```

See also: [`runtime-services.md`](runtime-services.md#ingestion)

### "Understand mini app"

```bash
# Mini app index
cat mini_app/README.md

# Backend entrypoint and tests
rg -n "mini_app" mini_app/ tests/unit/mini_app/
```

See also: [`runtime-services.md`](runtime-services.md#mini-app)

### "Understand Telegram bot flow"

```bash
# Bot index
cat telegram_bot/README.md

# LangGraph pipeline
rg -n "build_graph|State|node" telegram_bot/graph/

# Bot handlers and services
rg -n "handler|middleware|pipeline" telegram_bot/handlers/ telegram_bot/services/
```

See also: [`runtime-services.md`](runtime-services.md#telegram-bot)

## General Search Commands

Search the doc tree from the repo root:

```bash
# Find all docs mentioning a keyword
rg -n "Langfuse|LiteLLM|Redis|Qdrant|Compose|ingestion|voice|mini app|Telegram|RAG" docs/ README.md DOCKER.md AGENTS.md

# List all README indexes
find . -maxdepth 3 -name README.md | sort

# List runbooks
find docs/runbooks -maxdepth 1 -name '*.md' | sort
```
