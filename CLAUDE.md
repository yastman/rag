# CLAUDE.md

## Commands

```bash
uv sync                    # Install deps
make check                 # Lint + types (ruff + mypy)
make test-unit             # Unit tests (fast)
uv run pytest tests/unit/ -n auto  # Parallel (4x faster)
uv run pytest tests/integration/ -v  # Integration (~5s)
make local-up              # Dev services (redis, qdrant, bge-m3, litellm)
make run-bot               # Bot natively (no Docker)
make docker-full-up        # All services (23 containers)
make ingest-unified        # Unified ingestion (CocoIndex)
python -m src.ingestion.apartments.runner --incremental  # Apartments (297 rows, change tracking)
```

## Project Overview

**Contextual RAG Pipeline** — hybrid search (RRF + ColBERT rerank), BGE-M3 embeddings (local), multi-level caching, Telegram bot.

**Stack:** Python 3.12 | gpt-oss-120b via LiteLLM | BGE-M3 | Qdrant | Redis | CocoIndex

## Architecture

```
Ingestion:  Docling → Chunker → BGE-M3 Dense+Sparse → Qdrant
Text:       Query → [client] pipelines/client.py → classify → intent → cache → rag → generate
                  → [manager] create_agent SDK → rag_search | history_search | apartment_search | 8 CRM tools
Apartments: Query → regex filters (0 LLM) → hybrid search → response | LOW conf → agent escalation
Menu:       ReplyKeyboard → handle_menu_button → dedicated handlers → svc:/cta:/fav:/results: callbacks
Voice STT:  .ogg → LangGraph (11 nodes) → transcribe → RAG pipeline
Voice Bot:  /call → LiveKit Agent (ElevenLabs) → RAG API
```

**Services:** Postgres:5432, Qdrant:6333, Redis:6379, BGE-M3:8000, LiteLLM:4000, Langfuse:3001, LiveKit:7880, RAG API:8080

## Code Style

- **Ruff** (lint+format) | **MyPy** strict | Line length: 100 | Google docstrings
- **Pre-commit:** ruff-check → ruff-format → trailing-whitespace → check-yaml/toml/json
- **Commits:** `feat(scope): msg` | `fix(scope): msg` | `docs(scope): msg`
- **NEVER** `git add -A` — specific files only, `git diff --cached --stat` before commit

## Task Management

**TODO.md** (active) | **.planning/STATE.md** (pause/resume between sessions)

## Skills Workflow

```
Small:  inline → /test-driven-development → /verification-before-completion → commit
Medium: branch → TDD → /requesting-code-review → merge to main
Large:  plan → /tmux-swarm-orchestration (Sonnet workers) → merge + verify
Bug:    /systematic-debugging → TDD → fix
```

**Details:** `.claude/rules/skills.md`

## Subagent Models

**Default to cheapest model that fits the task.** Opus дорогой — используй только когда реально нужен.

| Model | When | Examples |
|-------|------|----------|
| `haiku` | Поиск, чтение, grep, простые вопросы | Explore codebase, find files, read docs |
| `sonnet` | Код-ревью, планирование, средний код | Plan agent, code-reviewer, write tests |
| `opus` | Только сложная архитектура, критический код | Не указывай model — наследует родителя |

```python
# Explore — всегда haiku
Task(subagent_type="Explore", model="haiku", ...)

# Plan/review — sonnet
Task(subagent_type="Plan", model="sonnet", ...)

# general-purpose код — sonnet по умолчанию
Task(subagent_type="general-purpose", model="sonnet", ...)
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| Redis connection refused | `docker compose up -d redis` (requires `REDIS_PASSWORD`) |
| Qdrant timeout | `QDRANT_TIMEOUT=30` |
| Docling 0 chunks | Don't set `tokenizer="word"`, use `None` |
| `Model gpt-4o-mini not found` (404) | `LLM_BASE_URL` must point to LiteLLM, not directly to Cerebras |
| Langfuse traces missing locally | `make run-bot` uses `uv run --env-file .env` to load env vars |
| Cache never stores / always MISS | Store guard threshold must be on RRF scale (~0.005), not cosine [0-1] |
| `qdrant-client .search()` AttributeError | Migrated to `.query_points()` in v1.17 — never use `.search()` |
| ColBERT rerank 16s on CPU | Use server-side ColBERT via Qdrant nested prefetch (#569), or `RERANK_PROVIDER=none` |
| Kommo `kommo_client = None` at startup | Ensure `KOMMO_CLIENT_ID` (not `KOMMO_INTEGRATION_ID`), `KOMMO_CLIENT_SECRET`, `KOMMO_REDIRECT_URI` in `.env`; fallback seeds Redis from `KOMMO_ACCESS_TOKEN` (#678, #686) |
| TTFT drift warnings spam logs | `TTFT_DRIFT_WARN_MS=500` (default); raise for reasoning models behind proxy (#675) |
| `orch-identity.json` FileNotFoundError from worktree | Fixed in #688: `_main_repo_root()` resolves via `git rev-parse --git-common-dir` |

## Parallel Sessions

**NEVER** run 2+ sessions in one directory — branches collide. Use worktrees:

```bash
claude --worktree feature-auth    # Session 1: .claude/worktrees/feature-auth/
claude --worktree bugfix-123      # Session 2: .claude/worktrees/bugfix-123/
```

Details: `.claude/rules/git-workflow.md`

## Environment

`cp .env.example .env` → `uv sync && make local-up && make run-bot`

**Required:** `TELEGRAM_BOT_TOKEN`, `CEREBRAS_API_KEY`, `OPENAI_API_KEY`, `LANGFUSE_*`, `REDIS_PASSWORD`

**Optional tuning:** `TTFT_DRIFT_WARN_MS` (default 500), `KOMMO_ACCESS_TOKEN` (fallback seed), `KOMMO_DEFAULT_PIPELINE_ID`, `KOMMO_*_FIELD_ID` (deal creation)

## Deployment

**Dev:** `make local-up && make run-bot` | **VPS:** `ssh vps` → `/opt/rag-fresh` → see `.claude/rules/k3s.md`

## Modular Docs

`.claude/rules/` — loaded by `paths:` glob when working on matching files:

| File | Scope |
|------|-------|
| `features/telegram-bot.md` | Bot, RAG pipeline, agent SDK, voice LangGraph |
| `features/search-retrieval.md` | RRF, Qdrant, gRPC, collections, settings |
| `features/caching.md` | 6-tier cache, Redis pipelines |
| `features/evaluation.md` | RAGAS, LLM-as-a-Judge, gold sets |
| `features/embeddings.md` | BGE-M3, Voyage |
| `features/ingestion.md` | CocoIndex, Docling |
| `features/llm-integration.md` | LiteLLM, guardrails |
| `features/query-processing.md` | HyDE, preprocessing |
| `features/voice-bot.md` | LiveKit, SIP, RAG API |
| `features/user-personalization.md` | User context, preferences |
| `observability.md` | Langfuse v3, scores, spans |
| `services.md` | Service patterns, Kommo CRM |
| `docker.md` | Containers, profiles, monitoring |
| `k3s.md` | VPS deployment, k3s manifests |
| `testing.md` | Unit/chaos/E2E tests |
| `build.md` | uv, Makefile, pre-commit |
| `skills.md` | Workflow, dispatch, worker contract |
| `git-workflow.md` | Commits, merge rules, Renovate |
