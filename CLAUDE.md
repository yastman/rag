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
make docker-full-up        # All services (17 containers)
make ingest-unified        # Unified ingestion (CocoIndex)
```

## Project Overview

**Contextual RAG Pipeline** — hybrid search (RRF + ColBERT rerank), BGE-M3 embeddings (local), multi-level caching, Telegram bot.

**Stack:** Python 3.12 | gpt-oss-120b via LiteLLM | BGE-M3 | Qdrant | Redis | CocoIndex

## Architecture

```
Ingestion:  Docling → Chunker → BGE-M3 Dense+Sparse → Qdrant
Text:       Query → [client] rag_pipeline → generate_response service (fast-path)
                  → [manager] create_agent SDK → rag_search | history_search | 8 CRM tools
Voice STT:  .ogg → LangGraph (11 nodes) → transcribe → RAG pipeline
Voice Bot:  /call → LiveKit Agent (ElevenLabs) → RAG API
```

**Services:** Qdrant:6333, Redis:6379, LiteLLM:4000, Langfuse:3001, LiveKit:7880, RAG API:8080

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

## Troubleshooting

| Error | Fix |
|-------|-----|
| Redis connection refused | `docker compose up -d redis` (requires `REDIS_PASSWORD`) |
| Qdrant timeout | `QDRANT_TIMEOUT=30` |
| Docling 0 chunks | Don't set `tokenizer="word"`, use `None` |
| `Model gpt-4o-mini not found` (404) | `LLM_BASE_URL` must point to LiteLLM, not directly to Cerebras |
| Langfuse traces missing locally | `make run-bot` uses `uv run --env-file .env` to load env vars |

## Environment

`cp .env.example .env` → `uv sync && make local-up && make run-bot`

**Required:** `TELEGRAM_BOT_TOKEN`, `CEREBRAS_API_KEY`, `OPENAI_API_KEY`, `LANGFUSE_*`, `REDIS_PASSWORD`

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
