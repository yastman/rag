***REMOVED*** Fast Doc Search

Quick search patterns and task-oriented lookups. Use these commands from the repo root to find the right canonical doc without browsing the tree manually.

***REMOVED******REMOVED*** By Request Type

***REMOVED******REMOVED******REMOVED*** "Study recent Langfuse traces"

Start with the runbook, then search related code:

```bash
***REMOVED*** Runbook
cat docs/runbooks/LANGFUSE_TRACING_GAPS.md

***REMOVED*** Trace spans and scoring in source
rg -n "Langfuse|trace|observation|score" telegram_bot/graph/ telegram_bot/services/ src/api/ src/evaluation/
```

See also: [`observability-and-storage.md`](observability-and-storage.md***REMOVED***langfuse-traces)

***REMOVED******REMOVED******REMOVED*** "Inspect Qdrant issues"

```bash
***REMOVED*** Runbook
cat docs/runbooks/QDRANT_TROUBLESHOOTING.md

***REMOVED*** Stack reference
cat docs/QDRANT_STACK.md

***REMOVED*** Collection policy and runtime integration
rg -n "Qdrant|collection|vector" telegram_bot/services/ src/ingestion/unified/ src/config/
```

See also: [`observability-and-storage.md`](observability-and-storage.md***REMOVED***qdrant)

***REMOVED******REMOVED******REMOVED*** "Inspect Redis/cache issues"

```bash
***REMOVED*** Runbook
cat docs/runbooks/REDIS_CACHE_DEGRADATION.md

***REMOVED*** Cache architecture and thresholds
cat docs/TROUBLESHOOTING_CACHE.md

***REMOVED*** Redis integration and cache tiers
rg -n "Redis|cache|redis-cli" telegram_bot/integrations/ telegram_bot/services/ src/
```

See also: [`observability-and-storage.md`](observability-and-storage.md***REMOVED***redis-and-cache)

***REMOVED******REMOVED******REMOVED*** "Understand Docker services"

```bash
***REMOVED*** Canonical source of truth
cat DOCKER.md

***REMOVED*** Service containers index
cat services/README.md

***REMOVED*** Compose validation
make verify-compose-images
```

See also: [`runtime-services.md`](runtime-services.md***REMOVED***docker-services)

***REMOVED******REMOVED******REMOVED*** "Understand ingestion"

```bash
***REMOVED*** Runbook and guide
cat docs/INGESTION.md
cat docs/GDRIVE_INGESTION.md

***REMOVED*** Pipeline code
rg -n "ingestion|cocoindex|docling" src/ingestion/unified/

***REMOVED*** CLI help
uv run python -m src.ingestion.unified.cli --help
```

See also: [`runtime-services.md`](runtime-services.md***REMOVED***ingestion)

***REMOVED******REMOVED******REMOVED*** "Understand mini app"

```bash
***REMOVED*** Mini app index
cat mini_app/README.md

***REMOVED*** Backend entrypoint and tests
rg -n "mini_app" mini_app/ tests/unit/mini_app/
```

See also: [`runtime-services.md`](runtime-services.md***REMOVED***mini-app)

***REMOVED******REMOVED******REMOVED*** "Understand Telegram bot flow"

```bash
***REMOVED*** Bot index
cat telegram_bot/README.md

***REMOVED*** LangGraph pipeline
rg -n "build_graph|State|node" telegram_bot/graph/

***REMOVED*** Bot handlers and services
rg -n "handler|middleware|pipeline" telegram_bot/handlers/ telegram_bot/services/
```

See also: [`runtime-services.md`](runtime-services.md***REMOVED***telegram-bot)

***REMOVED******REMOVED*** General Search Commands

Search the doc tree from the repo root:

```bash
***REMOVED*** Find all docs mentioning a keyword
rg -n "Langfuse|LiteLLM|Redis|Qdrant|Compose|ingestion|voice|mini app|Telegram|RAG" docs/ README.md DOCKER.md AGENTS.md

***REMOVED*** List all README indexes
find . -maxdepth 3 -name README.md | sort

***REMOVED*** List runbooks
find docs/runbooks -maxdepth 1 -name '*.md' | sort
```
