# CLAUDE.md

## Git Workflow

`dev` → `main`. Main = прод, auto-deploy на VPS. Pre-commit hook блокирует прямые коммиты в main.

```bash
git add <files> && git commit -m "feat(scope): msg"
# Деплой:
make check && make test-unit && git checkout main && git merge dev && git push && git checkout dev
```

**NEVER** `git add -A` — specific files only, `git diff --cached --stat` before commit.

## Commands

```bash
uv sync                    # Install deps
make check                 # Lint + types (ruff + mypy)
make test-unit             # Unit tests (fast)
uv run pytest tests/unit/ -n auto  # Parallel (4x faster)
uv run pytest tests/integration/ -v  # Integration (~5s)
make local-up              # Dev services (redis, qdrant, bge-m3, litellm)
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

## Code Style

- **Ruff** (lint+format) | **MyPy** strict | Line length: 100 | Google docstrings
- **Pre-commit:** ruff-check → ruff-format → trailing-whitespace → check-yaml/toml/json
- **Commits:** `feat(scope): msg` | `fix(scope): msg` | `docs(scope): msg`

## Code Search Tools

3 системы дополняют друг друга:

| Инструмент | Когда использовать | Пример |
|------------|-------------------|--------|
| **GrepAI** (MCP) | Semantic search, call graph | "найди код кеширования", "кто вызывает X" |
| **LSP** (Pyright) | Типы, hover, go-to-definition, references | "что возвращает функция", refactoring |
| **Grep/Glob** | Точный текст, regex | `TODO`, конкретный паттерн, imports |

GrepAI tools: `grepai_search`, `grepai_trace_callers`, `grepai_trace_callees`, `grepai_trace_graph`, `grepai_index_status`. Формат: `format: "toon"`, `compact: true` для экономии токенов.

GrepAI daemon: `grepai watch --background` (auto-start не настроен, запускать вручную).

## Context-Mode (MCP plugin)

Экономия контекста ~87%. Сырой output остаётся в sandbox, в контекст — только резюме.

| Вместо | Используй | Когда |
|--------|-----------|-------|
| `Bash` (>20 строк output) | `execute(language, code)` | make check, git log, docker ps, pytest |
| `Read` (анализ) | `execute_file(path, language, code)` | Логи, JSON, CSV, большие файлы |
| N × Bash | `batch_execute(commands, queries)` | Исследование, сбор контекста |
| `WebFetch` | `fetch_and_index(url)` + `search(queries)` | Документация, API reference |

**Read** — только для файлов, которые будешь **Edit**-ить. **Bash** — только git, mkdir, mv, rm, echo.

## Continuous Claude (v3)

Скиллы и агенты автообнаруживаются через description matching. Размер: Small → inline | Medium → /build | Large → /tmux-swarm-orchestration

**Агенты:** sonnet по умолчанию. Opus только для kraken, sleuth, phoenix, architect, profiler, maestro, aegis.

**Memory** (`python -m`, не `python scripts/...`):

```bash
cd /home/user/projects/Continuous-Claude-v3/opc && uv run python -m scripts.core.recall_learnings --query "тема" --k 5 --text-only
cd /home/user/projects/Continuous-Claude-v3/opc && uv run python -m scripts.core.store_learning \
  --session-id "id" --type WORKING_SOLUTION --content "что узнал" \
  --context "контекст" --tags "tag1,tag2" --confidence high
```

**Continuity:** `/create_handoff` перед завершением | `/resume_handoff` при возобновлении | при 90%+ контекста → handoff → `/clear`

## Troubleshooting

| Error | Fix |
|-------|-----|
| Redis connection refused | `docker compose up -d redis` (requires `REDIS_PASSWORD`) |
| Qdrant timeout | `QDRANT_TIMEOUT=30` |
| Docling 0 chunks | Don't set `tokenizer="word"`, use `None` |
| `Model gpt-4o-mini not found` (404) | `LLM_BASE_URL` must point to LiteLLM, not directly to Cerebras |
| Langfuse traces missing locally | `make run-bot` uses `uv run --env-file .env` to load env vars |
| Cache always MISS | Store guard threshold on RRF scale (~0.005), not cosine [0-1] |
| `qdrant-client .search()` AttributeError | Migrated to `.query_points()` in v1.17 — never use `.search()` |
| ColBERT rerank 16s on CPU | Server-side ColBERT via Qdrant nested prefetch, or `RERANK_PROVIDER=none` |
| Kommo `kommo_client = None` | `KOMMO_CLIENT_ID` (not `KOMMO_INTEGRATION_ID`), `KOMMO_CLIENT_SECRET`, `KOMMO_REDIRECT_URI` |
| TTFT drift warnings spam | `TTFT_DRIFT_WARN_MS=500`; raise for reasoning models behind proxy |

## Parallel Sessions

**NEVER** 2+ sessions в одной директории. `claude --worktree <name>` для изоляции.

## Environment

`cp .env.example .env` → `uv sync && make local-up && make run-bot`

**Required:** `TELEGRAM_BOT_TOKEN`, `CEREBRAS_API_KEY`, `OPENAI_API_KEY`, `LANGFUSE_*`, `REDIS_PASSWORD`

**Optional:** `TTFT_DRIFT_WARN_MS`, `KOMMO_ACCESS_TOKEN`, `KOMMO_DEFAULT_PIPELINE_ID`, `KOMMO_*_FIELD_ID`

## Docker Compose

Unified layout: `compose.yml` (base) + override через `COMPOSE_FILE` в `.env`.

| Среда | COMPOSE_FILE | COMPOSE_PROJECT_NAME |
|-------|-------------|---------------------|
| Dev | `compose.yml:compose.dev.yml` | `dev` |
| VPS | `compose.yml:compose.vps.yml` | `vps` |

## CI/CD Pipeline

`.github/workflows/ci.yml`: lint (ruff + mypy) → full-stack deploy (SSH → git pull → docker compose up -d)

Тесты гоняются **локально** перед merge (`make check && make test-unit`). CI только lint + deploy.

**Деплой:** `make deploy-bot` | `gh workflow run ci.yml` | `./scripts/deploy-vps.sh` (`--clean` для пересоздания)

**VPS:** `ssh vps` → `/opt/rag-fresh` → `.claude/rules/k3s.md`

## Modular Docs

`.claude/rules/` — автозагрузка по `paths:` globs при работе с matching файлами.
