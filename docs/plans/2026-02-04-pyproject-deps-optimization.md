# pyproject.toml Dependencies Optimization + Audit Fixes

**Goal:** Slim down base dependencies to a shared runtime core, move ingestion/bot/eval/heavy deps to optional extras, fix CI blockers from audit.

**Architecture:** Base dependencies contain only what unified ingestion pipeline needs. Bot, evaluation, LLM, local-embeddings, and local-parse become optional extras. This cuts Docker build time significantly and makes dependency structure explicit.

**Tech Stack:** uv, pyproject.toml, Docker multi-stage builds

---

## Parallel Execution (tmux swarm)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DEPENDENCY GRAPH                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ WORKER-A (deps-core) — SEQUENTIAL, main worktree                    │    │
│  │ Tasks 1→2→3→4→5→8: pyproject → lazy imports → lock → Dockerfile     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                              │                                               │
│                              ▼                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ ORCHESTRATOR: Task 12 (bot Dockerfile) — after Worker-A done        │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ═══════════════════════════════════════════════════════════════════════    │
│  PARALLEL (can start immediately, independent files):                        │
│  ═══════════════════════════════════════════════════════════════════════    │
│                                                                              │
│  ┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐          │
│  │ WORKER-B          │ │ WORKER-C          │ │ WORKER-D          │          │
│  │ Task 9: security  │ │ Task 10: lint     │ │ Task 11: tests    │          │
│  │ telegram_bot/     │ │ src/evaluation/   │ │ tests/            │          │
│  │ handlers/         │ │                   │ │                   │          │
│  └───────────────────┘ └───────────────────┘ └───────────────────┘          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Worker Assignment

| Worker | Tasks | Files | Worktree |
|--------|-------|-------|----------|
| **A (deps-core)** | 1, 2, 3, 4, 5, 8 | pyproject.toml, src/__init__.py, src/ingestion/__init__.py, uv.lock, Dockerfile.ingestion, CLAUDE.md | main (no worktree) |
| **B (security)** | 9 | telegram_bot/handlers/, telegram_bot/middlewares/ | .worktrees/fix-security |
| **C (lint)** | 10 | src/evaluation/evaluate_with_ragas.py | .worktrees/fix-lint |
| **D (tests)** | 11 | tests/unit/test_redis_semantic_cache.py, tests/ | .worktrees/fix-tests |
| **Orchestrator** | 12 | telegram_bot/Dockerfile, telegram_bot/requirements.txt | main (after A) |

### Execution Order

```bash
# Phase 1: Create worktrees for parallel workers
git worktree add .worktrees/fix-security -b fix/bot-allowlist main
git worktree add .worktrees/fix-lint -b fix/ruff-e402 main
git worktree add .worktrees/fix-tests -b fix/test-pollution main

# Phase 2: Spawn workers B, C, D in parallel (tmux windows)
# Phase 3: Worker A runs in main worktree (sequential deps tasks)
# Phase 4: Wait for all [COMPLETE]
# Phase 5: Merge branches, run Task 12, final verify
```

---

## Audit Findings (2026-02-04)

| Priority | Issue | Status | Task |
|----------|-------|--------|------|
| **P0** | Leaked OpenAI key in git history | 🔴 Manual rotation needed | N/A (manual) |
| **P0** | Bot allowlist not enforced | 🔴 Code fix | Task 9 |
| **P1** | `make check` fails (Ruff E402) | 🟡 | Task 10 |
| **P1** | 43 failed tests (sys.modules mocking) | 🟡 | Task 11 |
| **P2** | redisvl missing from uv.lock | 🟡 | Task 1 (bot extra) |
| **P2** | httpx implicit dependency | 🟡 | Task 1 (base deps) |
| **P2** | telegram_bot/requirements.txt drift | 🟡 | Task 12 |

---

## Summary of Changes

| Before | After |
|--------|-------|
| 39 base deps (including docling, transformers, mlflow, aiogram) | Small shared base deps + feature extras (`ingest`, `bot`, `eval`, ...) |
| httpx missing (implicit transitive) | httpx explicit |
| redisvl missing from uv.lock | redisvl in `[bot]` extra |
| `uv sync --no-dev` installs everything | `uv sync --no-dev` = minimal, `--extra bot` for bot |
| Dockerfile.ingestion installs ~2GB deps | Installs significantly less (size depends on lock/platform) |
| Bot allowlist not enforced | ALLOWED_USER_IDS checked |
| Ruff E402 in evaluate_with_ragas.py | Fixed with noqa or import reorder |

---

## Key Risk: Eager Imports Will Break Slim Base Deps (Must Fix)

This repo currently has eager imports in package `__init__.py` files that pull in
optional/heavy dependencies at import time.

Examples:
- `src/__init__.py` imports contextualization/core/ingestion unless `RAG_TESTING=true`.
- `src/ingestion/__init__.py` imports local parsing modules that depend on `docling`/`pymupdf`.

If we slim base deps without fixing these, importing the unified ingestion CLI
may fail with `ImportError` even though unified ingestion runtime does not need
those optional dependencies.

---

### Task 1: Update pyproject.toml dependencies section (Shared Base + Extras)

**Files:**
- Modify: `pyproject.toml:1-68`

**Step 1: Replace dependencies and optional-dependencies sections**

Replace the `[project].dependencies`, `[project.optional-dependencies]`, and remove `[dependency-groups]` to avoid having two competing mechanisms for "dev deps".

Proposed replacement:

```toml
[project]
name = "contextual-rag"
version = "2.13.0"
description = "Contextual RAG Pipeline with DBSF + ColBERT hybrid search"
requires-python = ">=3.11"
dependencies = [
    # === SHARED RUNTIME CORE ===
    # Used by bot and ingestion via VoyageService + HTTP clients
    "qdrant-client>=1.15.0",          # Vector database client
    "httpx>=0.27.0",                  # HTTP client for DoclingClient + bot services
    "voyageai>=0.3.0",                ***REMOVED*** AI dense embeddings
    "tenacity>=8.2.0",                # Retry logic with backoff
    "langfuse>=3.0.0",                # LLM observability (@observe in VoyageService)
    "python-dotenv",                  # .env loading
    "numpy",                          # Array operations (fastembed dep)
]

[project.optional-dependencies]
# Unified ingestion pipeline (CocoIndex + Postgres state + BM42)
ingest = [
    "cocoindex>=0.1.60",              # Data transformation framework
    "asyncpg>=0.31.0",                # Postgres async driver
    "fastembed>=0.7.0",               # BM42 sparse embeddings
]

# Telegram bot
bot = [
    "aiogram>=3.22.0",                # Telegram bot framework
    "redis>=7.0.1",                   # Redis client
    "redisvl>=0.13.0",                # Redis vector search (semantic cache) (keep aligned with repo usage)
    "cachetools>=5.0.0",              # In-memory caching
]

# RAG evaluation (RAGAS, MLflow, deepeval)
eval = [
    "mlflow>=2.22.1",                 # Experiment tracking
    "ragas>=0.2.10",                  # RAG evaluation framework
    "deepeval>=2.0.0",                # Hallucination detection
    "datasets>=3.0.0",                # HuggingFace datasets
    "pandas>=2.0.0",                  # Data analysis
    "scipy",                          # Scientific computing
    "aiohttp",                        # Async HTTP
    "requests",                       # Sync HTTP
]

# LLM contextualization (chunk enrichment with LLMs)
llm = [
    "anthropic",                      # Claude API
    "openai",                         # OpenAI API
    "groq",                           ***REMOVED*** API
]

# Local embedding models (high RAM, ~4-6GB)
local-embeddings = [
    "FlagEmbedding",                  # BGE-M3 local model
    "sentence-transformers",          # Sentence embeddings
    "transformers>=4.30.0",           # HuggingFace transformers
]

# Local document parsing (without docling-serve container)
local-parse = [
    "docling>=2.0.0",                 # Document parsing
    "docling-core>=2.0.0",            # Docling core types
    "pymupdf>=1.26.0",                # PDF parsing
]

# Development tools
dev = [
    "ruff>=0.6.0",                    # Linter + formatter
    "mypy>=1.11.0",                   # Type checking
    "pylint>=3.2.0",                  # Comprehensive linting
    "bandit>=1.7.9",                  # Security linting
    "vulture>=2.11",                  # Dead code detection
    "pytest>=8.3.0",                  # Testing framework
    "pytest-cov>=5.0.0",              # Coverage plugin
    "pytest-asyncio>=0.24.0",         # Async testing
    "pytest-httpx>=0.35.0",           # HTTPX mocking
    "opentelemetry-exporter-otlp-proto-grpc>=1.39.0",
    "pre-commit>=3.8.0",              # Git hooks
]

# Documentation
docs = [
    "mkdocs>=1.6.0",
    "mkdocs-material>=9.5.0",
    "mkdocstrings[python]>=0.25.0",
]

# All extras (for local development)
all = [
    "contextual-rag[ingest,bot,eval,llm,local-embeddings,local-parse,dev,docs]",
]
```

**Step 2: Verify TOML syntax**

Run: `python -c "import tomllib; tomllib.load(open('pyproject.toml', 'rb'))"`

Expected: No output (success)

**Step 2.1: Remove dependency-groups**

Delete `[dependency-groups]` section from `pyproject.toml` to avoid confusion between
`--group dev` vs `--extra dev`. Use `dev` extra only.

**Step 3: Commit pyproject.toml changes**

```bash
git add pyproject.toml
git commit -m "refactor(deps): move heavy deps to optional extras

- Base dependencies now contain only shared runtime core
- Add extras: ingest, bot, eval, llm, local-embeddings, local-parse
- Add httpx explicitly (was implicit transitive dependency)
- Dockerfile.ingestion will now install ~500MB instead of ~2GB"
```

---

### Task 2: Make Package Imports Lightweight (Required for Slim Base)

**Files:**
- Modify: `src/__init__.py`
- Modify: `src/ingestion/__init__.py`

**Context:**
After slimming base dependencies, these eager imports can cause `ImportError`
even if unified ingestion does not use optional features.

**Implementation notes:**
- Ensure importing `src.ingestion.unified.cli` does not require `docling`, `pymupdf`,
  `anthropic`, `openai`, `groq`, `transformers`, etc.
- Prefer lazy imports via `__getattr__` + mapping, or move heavy imports behind
  function boundaries.
- Do not change runtime behavior of the app; only make imports non-eager.

**Acceptance (in a clean env with only required extras):**
```bash
uv sync --no-dev --extra ingest
uv run python -c "import src.ingestion.unified.cli"
uv run python -m src.ingestion.unified.cli --help
```
Expected: succeeds without `ImportError`.

**Commit:**
```bash
git add src/__init__.py src/ingestion/__init__.py
git commit -m "refactor(imports): make package imports lazy for slim base deps"
```

---

### Task 3: Regenerate uv.lock

**Files:**
- Modify: `uv.lock`

**Step 1: Run uv lock**

Run: `uv lock`

Expected: Lock file regenerated successfully

**Step 2: Verify lock file**

Run: `uv lock --check`

Expected: "Lockfile is up to date."

**Step 3: Commit lock file**

```bash
git add uv.lock
git commit -m "chore: regenerate uv.lock after deps restructure"
```

---

### Task 4: Update Dockerfile.ingestion (Install ingest extra)

**Files:**
- Modify: `Dockerfile.ingestion`

**Step 1: Verify current Dockerfile uses correct command**

Current Dockerfile already uses:
```dockerfile
uv sync --frozen --no-dev --no-install-project
```

This will now install only shared base deps, but ingestion also needs the `ingest` extra.

**Step 2: Add `--extra ingest` to both uv sync invocations**

In `Dockerfile.ingestion`, update:
- `uv sync --frozen --no-dev --no-install-project`
- `uv sync --frozen --no-dev`

To include:
- `--extra ingest`

**Acceptance:**
- `docker compose -f docker-compose.dev.yml --profile ingest build ingestion` succeeds
- runtime contains `cocoindex`, `asyncpg`, `fastembed` (and still does not require local docling/pymupdf)

---

### Task 5: Verify unified ingestion works with slim base deps

**Files:**
- None (verification only)

**Step 1: Install only base deps**

Run: `uv sync --no-dev --extra ingest`

Expected: Installs shared base + ingest extra only

**Step 2: Import + CLI smoke**

Run:
```bash
uv run python -c "import src.ingestion.unified.cli"
uv run python -m src.ingestion.unified.cli --help
```

Expected: Succeeds

**Step 3: Run ingestion unit tests**

Run: `uv run pytest tests/unit/ingestion -v --tb=short -x`

Expected: All tests pass

---

### Task 6: Verify full local development still works (all extras)

**Files:**
- None (verification only)

**Step 1: Install all extras**

Run: `uv sync --all-extras`

Expected: Installs all optional dependencies successfully

**Step 2: Run a smoke test**

Run: `uv run pytest -q`

Expected: Test suite remains green (or at least no new failures introduced by deps restructure)

---

### Task 7: Verify bot extras work

**Files:**
- None (verification only)

**Step 1: Install bot extras**

Run: `uv sync --extra bot --extra dev`

Expected: Bot dependencies installed

**Step 2: Run bot tests**

Run: `uv run pytest -v --tb=short -x -k "test_bot_ and not integration"`

Expected: Tests pass

---

### Task 8: Document the change

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Update Environment section**

Add after "4. `uv sync && make docker-up`":

```markdown
**Optional extras:**
- `uv sync --extra bot` — Telegram bot dependencies
- `uv sync --extra eval` — RAG evaluation (RAGAS, MLflow)
- `uv sync --extra llm` — LLM providers (OpenAI, Anthropic, Groq)
- `uv sync --extra local-embeddings` — Local BGE-M3 (4-6GB RAM)
- `uv sync --extra local-parse` — Local docling parsing
- `uv sync --all-extras` — Everything (local development)
```

**Step 2: Commit documentation**

```bash
git add CLAUDE.md
git commit -m "docs: add optional extras to CLAUDE.md"
```

---

### Task 9: Enforce bot allowlist (P0 Security)

**Files:**
- Modify: `telegram_bot/handlers/message.py` (or middleware)
- Reference: `telegram_bot/config.py` for ALLOWED_USER_IDS

**Step 1: Find where allowlist is defined**

Run: `grep -r "ALLOWED_USER_IDS" telegram_bot/`

Expected: If empty, add support in config first (Step 2).

**Step 2: Add allowlist config (if missing)**

If `ALLOWED_USER_IDS` (or equivalent) does not exist yet, add it to the bot settings
by parsing env var `ALLOWED_USER_IDS` as a comma-separated list of integers.

Acceptance:
- `ALLOWED_USER_IDS=""` (or unset) means allow all (dev mode).
- `ALLOWED_USER_IDS="123,456"` only allows those user IDs.

**Step 3: Add middleware or handler check**

If not already present, add to message handler:

```python
from telegram_bot.config import settings

async def check_allowed_user(message: Message) -> bool:
    """Check if user is in allowlist. Empty list = allow all."""
    allowed = settings.allowed_user_ids
    if not allowed:
        return True  # No allowlist = public bot (dev mode)
    return message.from_user.id in allowed
```

**Step 4: Apply check in handlers**

```python
@router.message()
async def handle_message(message: Message):
    if not await check_allowed_user(message):
        await message.answer("⛔ Access denied. Contact admin.")
        return
    # ... rest of handler
```

**Step 5: Commit**

```bash
git add telegram_bot/
git commit -m "fix(security): enforce ALLOWED_USER_IDS allowlist

P0: Bot was accepting messages from any user.
Now checks allowlist; empty list = dev mode (allow all)."
```

---

### Task 10: Fix Ruff E402 (P1 CI)

**Files:**
- Modify: `src/evaluation/evaluate_with_ragas.py:52`

**Step 1: Check current error**

Run: `uv run ruff check src/evaluation/evaluate_with_ragas.py --select E402`

Expected: E402 at line 52

**Step 2: Fix with noqa comment (evaluation scripts are special)**

Add `# noqa: E402` to the import line, OR move imports to top.

Since evaluation scripts often need runtime setup before imports:

```python
# At the offending import line:
from ragas import evaluate  # noqa: E402
```

**Step 3: Verify fix**

Run: `uv run ruff check src/evaluation/evaluate_with_ragas.py --select E402`

Expected: No errors

**Step 4: Run full make check**

Run: `make check`

Expected: Pass (or only unrelated errors)

**Step 5: Commit**

```bash
git add src/evaluation/evaluate_with_ragas.py
git commit -m "fix(lint): add noqa E402 for evaluation script imports

Evaluation scripts need runtime setup before some imports."
```

---

### Task 11: Fix flaky tests (P1 - sys.modules pollution)

**Files:**
- Modify: `tests/unit/test_redis_semantic_cache.py`
- Modify: Other tests with `sys.modules[...] = MagicMock()`

**Step 1: Find all sys.modules modifications**

Run: `grep -r "sys.modules\[" tests/`

**Step 2: Convert to pytest monkeypatch (auto-rollback)**

Before (bad - pollutes globally):
```python
sys.modules["redisvl"] = MagicMock()
```

After (good - auto-cleanup):
```python
@pytest.fixture
def mock_redisvl(monkeypatch):
    mock = MagicMock()
    monkeypatch.setitem(sys.modules, "redisvl", mock)
    return mock

def test_something(mock_redisvl):
    # mock_redisvl is available, auto-cleaned after test
    ...
```

**Step 3: Run tests to verify isolation**

Run: `uv run pytest tests/unit/test_redis_semantic_cache.py -v`

Expected: Pass

**Step 4: Run full suite to check no pollution**

Run: `uv run pytest tests/unit/ -q --tb=no | tail -20`

Expected: Fewer failures (ideally 0)

**Step 5: Commit**

```bash
git add tests/
git commit -m "fix(tests): use monkeypatch for sys.modules mocking

Prevents test pollution across modules.
Fixes 43+ test failures from global sys.modules modifications."
```

---

### Task 12: Remove telegram_bot/requirements.txt (P2 - DRY)

**Files:**
- Delete: `telegram_bot/requirements.txt`
- Modify: `telegram_bot/Dockerfile`

**Step 1: Check what's in requirements.txt**

Run: `cat telegram_bot/requirements.txt`

**Step 2: Verify all deps are in pyproject.toml [bot] extra**

Compare with `[project.optional-dependencies.bot]` section.

**Step 3: Update Dockerfile to use uv**

In `telegram_bot/Dockerfile`, change from:
```dockerfile
RUN pip install -r requirements.txt
```

To:
```dockerfile
COPY --from=ghcr.io/astral-sh/uv:0.5.18 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra bot
```

**Step 4: Delete requirements.txt**

Run: `rm telegram_bot/requirements.txt`

**Step 5: Test Docker build**

Run: `docker compose build bot`

Expected: Build succeeds

**Step 6: Commit**

```bash
git add telegram_bot/
git commit -m "refactor(bot): migrate to uv, remove requirements.txt

- Bot Dockerfile now uses uv sync --extra bot
- Single source of truth: pyproject.toml
- Fixes dev/container dependency drift"
```

---

## Verification Checklist

### P2: Dependencies
- [ ] `pyproject.toml` has 7 shared base dependencies
- [ ] `httpx` is explicit in base dependencies
- [ ] `ingest` extra has cocoindex, asyncpg, fastembed
- [ ] `redisvl` is in `[bot]` extra
- [ ] `uv lock` succeeds
- [ ] `uv sync --no-dev --extra ingest` installs shared + ingest deps
- [ ] `uv sync --all-extras` installs everything
- [ ] `Dockerfile.ingestion` uses `--extra ingest`
- [ ] `telegram_bot/requirements.txt` deleted

### P1: CI/Tests
- [ ] `make check` passes (Ruff E402 fixed)
- [ ] Unit tests pass (sys.modules pollution fixed)

### P0: Security
- [ ] Bot allowlist enforced
- [ ] OpenAI key rotated (manual)

### Docker (optional)
- [ ] Dockerfile.ingestion builds successfully
- [ ] telegram_bot/Dockerfile builds with uv

---

## Rollback

If issues arise:
```bash
git revert HEAD~5  # Revert recent commits from this plan (adjust as needed)
uv lock            # Regenerate lock
```

---

## Future: Docling-serve Integration Checklist

> TODO: Add checklist for ingestion → docling-serve on VPS (timeouts, retries, limits, healthchecks)

**Current implementation (`src/ingestion/docling_client.py`):**
- `timeout: 300s` (configurable via DoclingConfig)
- No explicit retries (rely on CocoIndex retry logic)
- Health check: `GET /health`

**Recommended additions:**
- [ ] Retry with backoff for transient failures
- [ ] Request timeout per document size
- [ ] Rate limiting for batch processing
- [ ] Smoke test on deploy (health + chunk endpoint)

---

## tmux Swarm Commands

### Setup

```bash
# Ensure in tmux and logs dir exists
echo $TMUX  # Must be set
mkdir -p logs

# Create worktrees for parallel workers
cd /home/user/projects/rag-fresh
git worktree add .worktrees/fix-security -b fix/bot-allowlist main
git worktree add .worktrees/fix-lint -b fix/ruff-e402 main
git worktree add .worktrees/fix-tests -b fix/test-pollution main
```

### Spawn Workers B, C, D (parallel)

```bash
# Worker B: Security (Task 9)
tmux new-window -n "W-SEC" -c /home/user/projects/rag-fresh/.worktrees/fix-security
tmux send-keys -t "W-SEC" "claude --dangerously-skip-permissions 'W-SEC: Enforce bot allowlist (Task 9).

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-04-pyproject-deps-optimization.md
ЗАДАЧА: Task 9 only

Файлы: telegram_bot/handlers/, telegram_bot/middlewares/
Найди ALLOWED_USER_IDS и добавь проверку в handlers.

ТЕСТЫ: pytest tests/unit/test_bot_*.py -v -k allowlist (если есть)
НЕ запускай все 1000+ тестов.

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-sec.log:
[START] timestamp Task 9
[DONE] timestamp Task 9
[COMPLETE] timestamp Worker finished

НЕ делай git commit — оркестратор сделает в конце.'" Enter

# Worker C: Lint (Task 10)
tmux new-window -n "W-LINT" -c /home/user/projects/rag-fresh/.worktrees/fix-lint
tmux send-keys -t "W-LINT" "claude --dangerously-skip-permissions 'W-LINT: Fix Ruff E402 (Task 10).

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-04-pyproject-deps-optimization.md
ЗАДАЧА: Task 10 only

Файл: src/evaluation/evaluate_with_ragas.py:52
Добавь # noqa: E402 к импорту или перенеси импорты наверх.

ПРОВЕРКА: uv run ruff check src/evaluation/evaluate_with_ragas.py --select E402

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-lint.log:
[START] timestamp Task 10
[DONE] timestamp Task 10
[COMPLETE] timestamp Worker finished

НЕ делай git commit.'" Enter

# Worker D: Tests (Task 11)
tmux new-window -n "W-TEST" -c /home/user/projects/rag-fresh/.worktrees/fix-tests
tmux send-keys -t "W-TEST" "claude --dangerously-skip-permissions 'W-TEST: Fix sys.modules pollution (Task 11).

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-04-pyproject-deps-optimization.md
ЗАДАЧА: Task 11 only

Найди все sys.modules[...] = MagicMock() в tests/ и замени на pytest monkeypatch.

ТЕСТЫ: pytest tests/unit/test_redis_semantic_cache.py -v
НЕ запускай все 1000+ тестов. Используй --lf для упавших.

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-test.log:
[START] timestamp Task 11
[DONE] timestamp Task 11
[COMPLETE] timestamp Worker finished

НЕ делай git commit.'" Enter
```

### Worker A: Deps Core (sequential, main worktree)

```bash
# Worker A runs in main worktree (or orchestrator does it)
tmux new-window -n "W-DEPS" -c /home/user/projects/rag-fresh
tmux send-keys -t "W-DEPS" "claude --dangerously-skip-permissions 'W-DEPS: Dependencies optimization (Tasks 1,2,3,4,5,8).

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-04-pyproject-deps-optimization.md
ЗАДАЧИ: Tasks 1, 2, 3, 4, 5, 8 (sequential)

Порядок:
1. Task 1: Update pyproject.toml (shared base + extras, remove dependency-groups)
2. Task 2: Make imports lazy (src/__init__.py, src/ingestion/__init__.py)
3. Task 3: uv lock
4. Task 4: Update Dockerfile.ingestion (add --extra ingest)
5. Task 5: Verify with uv sync --no-dev --extra ingest && python -c \"import src.ingestion.unified.cli\"
6. Task 8: Update CLAUDE.md

ТЕСТЫ: pytest tests/unit/ingestion -v
НЕ запускай все 1000+ тестов.

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-deps.log:
[START] timestamp Task N
[DONE] timestamp Task N
[COMPLETE] timestamp Worker finished

НЕ делай git commit — оркестратор сделает в конце.'" Enter
```

### Auto-Monitor

```bash
# Start monitor (closes windows on [COMPLETE])
nohup /home/user/projects/rag-fresh/scripts/monitor-workers.sh > logs/monitor.log 2>&1 &

# Check progress
tail -f logs/worker-*.log
```

### After All Workers Complete

```bash
# 1. Check all [COMPLETE]
grep '\[COMPLETE\]' logs/worker-*.log

# 2. Merge branches
cd /home/user/projects/rag-fresh
git checkout main
git merge fix/bot-allowlist --no-edit
git merge fix/ruff-e402 --no-edit
git merge fix/test-pollution --no-edit

# 3. Run Task 12 (depends on Task 1)
# ... orchestrator handles this

# 4. Final verification
uv sync --all-extras
make check
uv run pytest tests/unit/ -q --tb=no | tail -20

# 4.1 Verify slim ingestion works
uv sync --no-dev --extra ingest
uv run python -c "import src.ingestion.unified.cli"
uv run python -m src.ingestion.unified.cli --help

# 5. Single commit
git add -A
git commit -m "refactor(deps): optimize dependencies + fix audit issues

- Base deps: 7 packages (shared runtime core)
- Add extras: ingest, bot, eval, llm, local-embeddings, local-parse
- Add httpx explicitly
- Dockerfile.ingestion uses --extra ingest
- Enforce bot allowlist (P0 security)
- Fix Ruff E402
- Fix sys.modules test pollution
- Remove telegram_bot/requirements.txt"

# 6. Cleanup worktrees
git worktree remove .worktrees/fix-security
git worktree remove .worktrees/fix-lint
git worktree remove .worktrees/fix-tests
git branch -d fix/bot-allowlist fix/ruff-e402 fix/test-pollution
```
