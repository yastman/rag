# CLAUDE.md

## Git Workflow

`dev` → `main`. Main = прод, auto-deploy на VPS. Pre-commit hook блокирует прямые коммиты в main.

```bash
git add <files> && git commit -m "feat(scope): msg"
```

Деплой: см. `.claude/rules/git-workflow.md` → CI/CD Pipeline.

**NEVER** `git add -A` — specific files only, `git diff --cached --stat` before commit.

## Commands

```bash
uv sync                    # Install deps
make check                 # Lint + types (ruff + mypy)
make test-unit             # Unit tests (fast)
uv run pytest tests/unit/ -n auto  # Parallel (4x faster)
uv run pytest tests/integration/ -v  # Integration (~5s)
make local-up              # Dev services (redis, qdrant, bge-m3, docling, litellm)
make run-bot               # Bot natively (no Docker)
make docker-full-up        # All services (23 containers, COMPOSE_FILE from .env)
make ingest-unified        # Unified ingestion (CocoIndex)
python -m src.ingestion.apartments.runner --incremental  # Apartments
```

## Project Overview

**Contextual RAG Pipeline** — hybrid search (RRF + ColBERT rerank), BGE-M3 embeddings (local), multi-level caching, Telegram bot.

**Stack:** Python 3.12 | gpt-oss-120b via LiteLLM | BGE-M3 | Qdrant | Redis | CocoIndex

## Architecture

```
Ingestion:  Docling → Chunker → BGE-M3 Dense+Sparse → Qdrant
Text:       Query → pipelines/client.py → classify → intent → cache → rag → generate
            → create_agent SDK → rag_search | history_search | apartment_search | 8 CRM tools
Apartments: regex filters (0 LLM) → hybrid search → response | LOW conf → agent escalation
Menu:       ReplyKeyboard → handle_menu_button → svc:/cta:/fav:/results: callbacks
Voice STT:  .ogg → LangGraph (11 nodes) → transcribe → RAG pipeline
Voice Bot:  /call → LiveKit Agent (ElevenLabs) → RAG API
```

**Services:** Postgres:5432, Qdrant:6333, Redis:6379, BGE-M3:8000, LiteLLM:4000, Langfuse:3001, LiveKit:7880, RAG API:8080

## SDK-First

**Правило:** перед написанием кода проверь `.claude/rules/sdk-registry.md` — если задача покрывается SDK, используй SDK.

**Обновление реестра:** при добавлении/удалении зависимости из `pyproject.toml` — обнови `.claude/rules/sdk-registry.md`.

## Code Style

- **Ruff** (lint+format) | **MyPy** strict | Line length: 100 | Google docstrings
- **Pre-commit:** ruff-check → ruff-format → trailing-whitespace → check-yaml/toml/json
- **Commits:** `feat(scope): msg` | `fix(scope): msg` | `docs(scope): msg`

## Environment

`cp .env.example .env` → `uv sync && make local-up && make run-bot`

**Required:** `TELEGRAM_BOT_TOKEN`, `CEREBRAS_API_KEY`, `OPENAI_API_KEY`, `LANGFUSE_*`, `REDIS_PASSWORD`

**Optional:** `TTFT_DRIFT_WARN_MS`, `KOMMO_ACCESS_TOKEN`, `KOMMO_DEFAULT_PIPELINE_ID`, `KOMMO_*_FIELD_ID`

## Post-Work

После PR/коммита с новыми файлами, сервисами или зависимостями → rules-sync (inline mode). Проверь diff → обнови затронутые `.claude/rules/`.

## Modular Docs

`.claude/rules/` — автозагрузка по `paths:` globs при работе с matching файлами.

| Rule | Когда грузится |
|------|---------------|
| `sdk-registry.md` | SDK-First проверка |
| `testing.md` | `tests/**` |
| `mini-app.md` | `mini_app/**` |
| `docker.md` | Docker, compose |
| `git-workflow.md` | PR, CI/CD, deploy |
| `services.md` | `telegram_bot/services/` |
| `features/*.md` | telegram-bot, voice, search, caching, ingestion и др. |
