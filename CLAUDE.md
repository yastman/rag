# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Quick Reference

```bash
uv sync                    # Install all dependencies
make check                 # Lint + types
make test                  # All tests
make test-unit             # Unit tests only (fast)
make docker-up             # Start core services (5 containers, ~17s)
make docker-bot-up         # Core + bot/litellm
make docker-full-up        # All services (20 containers)
make eval-rag              # RAG evaluation (RAGAS faithfulness >= 0.8)
make monitoring-up         # Start alerting stack
make ingest-unified        # Run unified ingestion (CocoIndex v3.2.1)
make ingest-unified-watch  # Continuous mode with FlowLiveUpdater
make ingest-unified-status # Show ingestion stats from Postgres
```

**Location:** `/home/user/projects/rag-fresh` (WSL2) | `/opt/rag-fresh` (VPS)

## Project Overview

**Contextual RAG Pipeline** — Production RAG with hybrid search (RRF + ColBERT), Voyage AI embeddings, multi-level caching, Telegram bot.

**Stack:** Python 3.12 | Cerebras via LiteLLM | Voyage AI | Qdrant | Redis | CocoIndex

**Use cases:** Bulgarian property (192 docs), Ukrainian Criminal Code (1,294 docs)

## Architecture

```
Input → Docling Parser → Chunker → Voyage Embeddings + BM42 → Qdrant
     → QueryPreprocessor → RRF Fusion → Rerank → LLM → Response
```

| Module | Purpose |
|--------|---------|
| `src/core/pipeline.py` | RAG orchestrator |
| `src/retrieval/search_engines.py` | 4 search variants |
| `src/ingestion/unified/` | Unified pipeline v3.2.1 (CocoIndex) |
| `telegram_bot/` | Bot + services |

**Services:** Qdrant:6333, Redis:6379, LiteLLM:4000, Langfuse:3001

**Docker Profiles:** `core` (5 svc, ~17s) | `bot` | `ml` | `obs` | `ai` | `ingest` | `full` (20 svc) → see `.claude/rules/docker.md`

## Code Style

- **Linter/Formatter:** Ruff v0.14.14 | **Types:** MyPy | **Line length:** 100 | **Docstrings:** Google style
- **Pre-commit:** ruff-check (--fix) → ruff-format → trailing-whitespace → check-yaml/toml/json
- **Commits:** `feat(scope): message` | `fix(scope): message` | `docs(scope): message`

## Task Management

**Active:** `TODO.md` | **Backlog:** `gh issue list --label "next"`

**Claude Code Tasks:** Для shared task list между терминалами:
```bash
CLAUDE_CODE_TASK_LIST_ID=my-project claude
```
См. `.claude/rules/shared-tasks.md`

## Environment

1. Install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. Copy `.env.example` → `.env`
3. Required: `TELEGRAM_BOT_TOKEN`, `VOYAGE_API_KEY`, `CEREBRAS_API_KEY`, `LANGFUSE_*`
4. `uv sync && make docker-up`

## Key Docs

| Document | Content |
|----------|---------|
| `docs/PIPELINE_OVERVIEW.md` | Architecture |
| `docs/QDRANT_STACK.md` | Vector DB |
| `docs/INGESTION.md` | Document ingestion pipeline |
| `docs/CONTEXTUALIZED_EMBEDDINGS.md` | voyage-context-3 embeddings |
| `CACHING.md` | 6-tier cache |

#***REMOVED*** Collections

| Collection | Content | Embeddings |
|------------|---------|------------|
| `contextual_bulgaria_voyage` | Bulgarian property (192 docs) | Voyage |
| `legal_documents` | Ukrainian Criminal Code (1,294 docs) | BGE-M3 |
| `gdrive_documents_scalar` | Google Drive docs | Voyage |
| `gdrive_documents_bge` | Google Drive docs (VPS) | BGE-M3 local |

**Settings:** `quantization_mode=off|scalar|binary`, `small_to_big_mode=off|on|auto`, `use_hyde=true|false`

## Deployment

```bash
# Dev (with Voyage API)
make docker-up                      # Core services
make docker-bot-up                  # + bot

# VPS (local embeddings, no Voyage API)
ssh vps "cd /opt/rag-fresh && docker compose --compatibility -f docker-compose.vps.yml up -d"
```

**VPS:** `admin@95.111.252.29:1654` (`ssh vps`) | Path: `/opt/rag-fresh`

**VPS Quick Commands:**
```bash
ssh vps "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep vps"  # Status
ssh vps "docker logs vps-bot --tail 30"                                   # Logs
rsync -avz src/ vps:/opt/rag-fresh/src/ && ssh vps "docker restart vps-ingestion"  # Deploy code
```

**VPS Env:** `RETRIEVAL_DENSE_PROVIDER=bge_m3_api` `RERANK_PROVIDER=colbert` `BGE_M3_URL=http://bge-m3:8000`

## Monitoring & Alerting

`make monitoring-up` | `make monitoring-test-alert` → See `.claude/rules/docker.md` and `docs/ALERTING.md`

## Troubleshooting

| Error | Fix |
|-------|-----|
| Redis connection refused | `docker compose up -d redis` |
| Qdrant timeout | `use_quantization=True` |
| Voyage 429 | Use CacheService |
| Docling 0 chunks | Don't set `tokenizer="word"`, use `None` |
| Alerts not sending | Check `TELEGRAM_ALERTING_*` env vars |

## Skills Workflow

```
/writing-plans → /executing-plans → /finishing-a-development-branch
```

**Details:** `.claude/rules/skills.md`

## Long-Running Commands

For docker build, large tests (> 30 sec) — use tmux + logs:

```bash
mkdir -p logs
tmux new-window -n "W-BUILD" -c /home/user/projects/rag-fresh
tmux send-keys -t "W-BUILD" "docker compose build ingestion 2>&1 | tee logs/build.log; echo '[COMPLETE]'" Enter
```

Check: `tail -f logs/build.log` | Done: `grep '\[COMPLETE\]' logs/build.log`

## Modular Docs

See `.claude/rules/` for domain-specific documentation:

| File | Scope | Loads when |
|------|-------|-----------|
| `features/search-retrieval.md` | RRF, ACORN, quantization, small-to-big | `src/retrieval/**` |
| `features/query-processing.md` | HyDE, preprocessing, routing | `**/query*.py` |
| `features/evaluation.md` | RAGAS, metrics, A/B tests | `src/evaluation/**` |
| `features/caching.md` | 6-tier cache, TTL | `**/cache*.py` |
| `features/embeddings.md` | Voyage, BGE-M3, BM42 | `**/embed*.py` |
| `features/llm-integration.md` | LiteLLM, guardrails, fallbacks | `**/llm*.py` |
| `features/ingestion.md` | CocoIndex, Docling, parsing | `src/ingestion/**` |
| `features/telegram-bot.md` | Handlers, middlewares | `telegram_bot/*.py` |
| `build.md` | uv, Makefile, pre-commit hooks | `Makefile, pyproject.toml` |
| `docker.md` | Containers, monitoring | `docker/**` |
| `testing.md` | Unit tests, chaos tests, E2E | `tests/**` |
| `skills.md` | Superpowers workflow | `docs/plans/**` |
