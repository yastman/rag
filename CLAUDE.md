# CLAUDE.md

## TLDR-First Workflow (ОБЯЗАТЕЛЬНО)

**Приоритет инструментов для исследования кода:**

```
1. tldr semantic search "что ищем" --k 10   # Первый шаг — семантический поиск (~200ms)
2. tldr search "pattern" src/                # Точный текстовый поиск
3. tldr extract file.py                      # Структура файла (вместо Read)
4. tldr context func --project . --depth 2   # LLM-ready контекст функции
5. Read file.py offset=N limit=M             # ТОЛЬКО конкретные строки, когда точно знаешь что читать
```

**ЗАПРЕЩЕНО:**
- НЕ запускать scout/Explore агентов для поиска файлов — `tldr semantic search` делает это за 200ms
- НЕ делать Read целых файлов — `tldr extract` даёт структуру за 95% экономии токенов
- НЕ использовать Grep когда есть `tldr search` — структурированные результаты лучше
- НЕ спавнить суб-агентов для "исследования кодбейза" — tldr + Read конкретных строк

**Правило:** `tldr semantic search` для обнаружения. `tldr extract` для навигации. `Read offset limit` для чтения кода. `tldr impact` перед рефакторингом. `tldr warm .` для переиндексации.

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
tldr structure . --lang python   # Code overview (95% token savings)
tldr search "pattern" src/       # Structured code search
tldr context entry_point --project .  # LLM-ready context for function
tldr daemon start                # Background daemon (155x faster)
tldr semantic search "query" --k 5   # Semantic search via daemon (~200ms, 6930 units)
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

## Continuous Claude (v3)

114 skills, 48 agents, 64 hooks. Хуки автоактивируют скиллы по естественному языку.

### Workflow Dispatch

```
Что делать?
├── Не знаю → /workflow (роутер спросит цель)
├── Понять код → /explore quick|deep|architecture
├── Спланировать → /premortem → plan-agent
├── Построить → /build greenfield|brownfield
├── Починить → /fix bug|hook|deps|pr-comments
├── Тесты → /tdd
├── Рефакторинг → /refactor
├── Ревью → /review
└── Релиз → /release
```

Размер: Small → inline/tdd | Medium → branch + /build + /review | Large → /tmux-swarm-orchestration

### Skill Options

**`/build <mode> [options]`** — greenfield | brownfield | tdd | refactor

| Option | Effect |
|--------|--------|
| `--skip-discovery` | Пропустить интервью (есть чёткий spec) |
| `--skip-validate` | Пропустить валидацию плана |
| `--skip-commit` | Не коммитить автоматически |
| `--parallel` | Параллельные research агенты |

**`/fix <scope> [options]`** — bug | hook | deps | pr-comments

| Option | Effect |
|--------|--------|
| `--dry-run` | Только диагностика, не фиксить |
| `--no-test` | Пропустить регрессионные тесты |
| `--no-commit` | Не коммитить автоматически |

**`/explore <depth> [options]`** — quick (~1 мин) | deep (~5 мин) | architecture (~3 мин)

| Option | Effect |
|--------|--------|
| `--focus "area"` | Фокус на области (e.g. `--focus "auth"`) |
| `--output handoff` | Создать handoff для реализации |
| `--entry "func"` | Начать от entry point |

### Key Skills

| Skill | Когда |
|-------|-------|
| `/premortem` | Перед реализацией — TIGERS (угрозы) + ELEPHANTS (скрытые риски) |
| `/discovery-interview` | Размытые требования → детальный spec |
| `qlty-check` | 70+ linters, auto-fix |
| `braintrust-analyze` | Анализ сессий, replay |
| `ast-grep-find` | Структурный поиск по AST (не текстовый) |

### Agents

| Agent | Когда | Model |
|-------|-------|-------|
| **kraken** | Имплементация кода | opus |
| **spark** | Мелкие фиксы, твики | sonnet |
| **sleuth** | Диагностика багов | opus |
| **scout** | Исследование кодбейза | sonnet |
| **arbiter** | Тесты и верификация | sonnet |
| **phoenix** | Анализ рефакторинга | opus |
| **oracle** | Внешнее исследование | sonnet |
| **plan-agent** | Планирование фич | sonnet |

**Правило:** sonnet по умолчанию. Opus только для kraken, sleuth, phoenix, architect, profiler, maestro, aegis. Haiku не используем.

### Memory

**Формат:** `python -m` (не `python scripts/...`).

```bash
# Recall — перед реализацией, проверь прошлый опыт
cd /home/user/projects/Continuous-Claude-v3/opc && uv run python -m scripts.core.recall_learnings --query "тема" --k 5 --text-only

# Store — после решения проблемы, сохрани опыт
cd /home/user/projects/Continuous-Claude-v3/opc && uv run python -m scripts.core.store_learning \
  --session-id "id" --type WORKING_SOLUTION --content "что узнал" \
  --context "контекст" --tags "tag1,tag2" --confidence high
```

Типы: `WORKING_SOLUTION` | `ARCHITECTURAL_DECISION` | `CODEBASE_PATTERN` | `FAILED_APPROACH` | `ERROR_FIX`

### Continuity

**Внутри сессии:** `thoughts/ledgers/CONTINUITY_<topic>.md` — автотрекинг через хуки
**Между сессиями:** `thoughts/shared/handoffs/*.yaml` — YAML handoffs

- **Перед завершением:** `/create_handoff`
- **При возобновлении:** `/resume_handoff`
- **При 90%+ контекста:** `create_handoff` → `/clear`

### TLDR Code Analysis

```bash
# Индексация (первый раз или после больших изменений)
tldr warm .                             # Все слои + semantic embeddings
tldr daemon start                       # Фоновый демон (100ms запросы)

# Структура — вместо чтения файлов
tldr structure . --lang python          # Обзор проекта (95% экономия токенов)
tldr tree src/ --ext .py                # Дерево файлов
tldr extract src/file.py                # Полный анализ одного файла

# Поиск — вместо grep
tldr search "pattern" src/              # Структурированный поиск
tldr semantic search "что делает" --k 5 # Семантический через daemon (~200ms)

# Контекст для LLM
tldr context func_name --project . --depth 2  # LLM-ready summary (95% savings)

# Анализ функций
tldr cfg src/file.py func_name          # Control flow graph
tldr dfg src/file.py func_name          # Data flow graph
tldr slice src/file.py func 42          # Что влияет на строку 42

# Рефакторинг
tldr impact func_name src/ --depth 3    # Кто вызывает эту функцию
tldr calls src/                         # Полный call graph
tldr dead src/                          # Мёртвый код
tldr arch src/                          # Слои архитектуры

# Импорты
tldr imports src/file.py                # Что импортирует файл
tldr importers module_name src/         # Кто импортирует модуль

# CI
tldr diagnostics .                      # Type check + lint (pyright/ruff)
tldr change-impact --git                # Какие тесты затронуты изменениями
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
