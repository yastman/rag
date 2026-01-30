# Audit Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all P0 (critical) and P1 (high priority) issues from AUDIT_REPORT.md to improve security, reliability, and maintainability.

**Architecture:** Incremental fixes organized by priority. Each task is independent where possible, enabling parallel execution. Security fixes (P0) first, then dev experience improvements (P1).

**Tech Stack:** Docker Compose, GitHub Actions, Python (pytest, ruff), Redis Stack, Git

---

## Task 1: Remove tracked .env.server from git (P0.1)

**Files:**
- Modify: `.gitignore`
- Delete from git: `.env.server`

**Step 1: Verify .env.server is tracked**

Run: `git ls-files | grep '.env.server'`
Expected: `.env.server`

**Step 2: Remove .env.server from git tracking (keep local file)**

Run: `git rm --cached .env.server`
Expected: `rm '.env.server'`

**Step 3: Add .env.* pattern to .gitignore**

Edit `.gitignore` to add after `.env` line:

```gitignore
.env
.env.*
.env.local
.env.server
.env.production
```

**Step 4: Verify file is now ignored**

Run: `git status`
Expected: `.env.server` not listed (ignored), `.gitignore` modified

**Step 5: Commit**

```bash
git add .gitignore && git commit -m "fix(security): remove .env.server from tracking

Closes P0.1 from AUDIT_REPORT.md.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Strengthen .dockerignore (P0.1)

**Files:**
- Modify: `.dockerignore`

**Step 1: Read current .dockerignore**

```
venv/
__pycache__/
*.pyc
...
.env
```

**Step 2: Add comprehensive env and secret patterns**

Edit `.dockerignore` to add:

```dockerignore
# Secrets and environment files
.env
.env.*
.env.local
.env.server
.env.production
*.pem
*.key
credentials.json
secrets/

# Git
.git/
.gitignore
.github/

# IDE
.vscode/
.idea/

# Tests and coverage
.pytest_cache/
.mypy_cache/
.coverage
htmlcov/
.tox/
```

**Step 3: Verify no secrets in build context**

Run: `docker build --no-cache -f telegram_bot/Dockerfile -t test-context . 2>&1 | head -20`
Expected: Build starts without copying .env files

**Step 4: Commit**

```bash
git add .dockerignore && git commit -m "fix(security): strengthen .dockerignore to exclude secrets

Prevents .env.* files from leaking into Docker build context.
Closes P0.1 from AUDIT_REPORT.md.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Enable CI workflow (P0.2)

**Files:**
- Move: `.github/workflows.disabled/ci.yml` -> `.github/workflows/ci.yml`

**Step 1: Create workflows directory if needed**

Run: `mkdir -p .github/workflows`

**Step 2: Move CI workflow**

Run: `mv .github/workflows.disabled/ci.yml .github/workflows/ci.yml`

**Step 3: Verify workflow syntax**

Run: `cat .github/workflows/ci.yml | head -20`
Expected: Valid YAML with `on: push/pull_request`

**Step 4: Commit**

```bash
git add .github/workflows/ci.yml && git commit -m "ci: enable basic lint and type check workflow

Restores CI quality gate on PRs.
Closes P0.2 from AUDIT_REPORT.md.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Fix MinIO healthcheck (P0.3)

**Files:**
- Modify: `docker-compose.dev.yml:196-214` (minio service)

**Step 1: Identify current healthcheck**

Current (broken - `mc` not in image):
```yaml
healthcheck:
  test: ["CMD", "mc", "ready", "local"]
```

**Step 2: Replace with curl-based healthcheck**

Edit `docker-compose.dev.yml` minio service:

```yaml
  minio:
    image: minio/minio:latest
    container_name: dev-minio
    entrypoint: sh
    command: -c 'mkdir -p /data/langfuse && minio server --address ":9000" --console-address ":9001" /data'
    environment:
      MINIO_ROOT_USER: minio
      MINIO_ROOT_PASSWORD: miniosecret
    ports:
      - "9090:9000"
      - "9091:9001"
    volumes:
      - minio_data:/data
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:9000/minio/health/live || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
```

**Step 3: Verify healthcheck works**

Run: `docker compose -f docker-compose.dev.yml up -d minio && sleep 15 && docker inspect dev-minio --format='{{.State.Health.Status}}'`
Expected: `healthy`

**Step 4: Commit**

```bash
git add docker-compose.dev.yml && git commit -m "fix(docker): use curl-based MinIO healthcheck

The mc CLI is not available in minio/minio image.
Closes P0.3 from AUDIT_REPORT.md.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Add restart policies to core services (P0.3)

**Files:**
- Modify: `docker-compose.dev.yml`

**Step 1: Add restart: unless-stopped to core services**

Add `restart: unless-stopped` to these services:
- postgres (after healthcheck block, ~line 28)
- redis (after healthcheck block, ~line 46)
- qdrant (after healthcheck block, ~line 63)
- clickhouse (after healthcheck block, ~line 193)
- minio (after healthcheck block, ~line 214)
- redis-langfuse (after healthcheck block, ~line 227)
- mlflow (after healthcheck block, ~line 334)
- lightrag (after healthcheck block, ~line 167)

Example for postgres:
```yaml
  postgres:
    image: pgvector/pgvector:pg17
    container_name: dev-postgres
    restart: unless-stopped
    ports:
```

**Step 2: Verify syntax**

Run: `docker compose -f docker-compose.dev.yml config --quiet && echo "Valid"`
Expected: `Valid`

**Step 3: Commit**

```bash
git add docker-compose.dev.yml && git commit -m "fix(docker): add restart policies to core services

Services now restart automatically after Docker/host restart.
Closes P0.3 from AUDIT_REPORT.md.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Upgrade Redis to Redis Stack for vector search (P0.4)

**Files:**
- Modify: `docker-compose.dev.yml:30-47` (redis service)

**Step 1: Replace redis image with Redis Stack**

Edit redis service in `docker-compose.dev.yml`:

```yaml
  redis:
    image: redis/redis-stack-server:7.4.0-v3
    container_name: dev-redis
    restart: unless-stopped
    ports:
      - "6379:6379"
    environment:
      # Redis Stack includes RediSearch, RedisJSON, RedisTimeSeries
      REDIS_ARGS: "--maxmemory 512mb --maxmemory-policy allkeys-lfu --appendonly yes"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3
```

**Step 2: Verify Redis Stack modules are available**

Run: `docker compose -f docker-compose.dev.yml up -d redis && sleep 5 && docker exec dev-redis redis-cli MODULE LIST | grep -E 'search|json'`
Expected: Output shows `search` and `ReJSON` modules

**Step 3: Commit**

```bash
git add docker-compose.dev.yml && git commit -m "feat(docker): upgrade to Redis Stack for vector search

RedisVL SemanticCache requires RediSearch module.
Closes P0.4 from AUDIT_REPORT.md.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Make Settings lazy-loaded (P1.1)

**Files:**
- Modify: `src/config/settings.py`
- Create: `tests/unit/test_settings_lazy.py`

**Step 1: Write the failing test**

Create `tests/unit/test_settings_lazy.py`:

```python
"""Tests for lazy settings initialization."""

import os
from unittest.mock import patch


def test_import_settings_module_without_api_keys():
    """Importing settings module should not require API keys."""
    # Clear any cached settings
    import sys
    for mod in list(sys.modules.keys()):
        if mod.startswith("src.config"):
            del sys.modules[mod]

    # Import without API keys should not raise
    with patch.dict(os.environ, {
        "API_PROVIDER": "claude",
        "ANTHROPIC_API_KEY": "",
        "OPENAI_API_KEY": "",
        "GROQ_API_KEY": "",
    }, clear=False):
        # This should NOT raise ValueError
        from src.config import settings as settings_module

        # get_settings() should be available
        assert hasattr(settings_module, "get_settings")


def test_get_settings_validates_on_call():
    """get_settings() should validate API keys when called."""
    import sys
    for mod in list(sys.modules.keys()):
        if mod.startswith("src.config"):
            del sys.modules[mod]

    with patch.dict(os.environ, {
        "API_PROVIDER": "claude",
        "ANTHROPIC_API_KEY": "",
    }, clear=False):
        from src.config.settings import get_settings
        import pytest

        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            get_settings()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_settings_lazy.py -v`
Expected: FAIL (no `get_settings` function)

**Step 3: Implement lazy settings**

Edit `src/config/settings.py`:

Replace the bottom of the file (lines 209-211):
```python
# Global settings instance (created once at import time)
settings = Settings()
```

With:
```python
# Lazy settings singleton
_settings: Settings | None = None


def get_settings() -> Settings:
    """
    Get the global settings instance (lazy initialization).

    Settings are created on first call, not at import time.
    This allows importing the module without requiring API keys.

    Example:
        >>> from src.config.settings import get_settings
        >>> settings = get_settings()
        >>> settings.qdrant_url
        'http://localhost:6333'
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


# Backward compatibility: settings is now a property-like object
# that creates Settings on first attribute access
class _LazySettings:
    """Lazy proxy for backward compatibility with `from src.config.settings import settings`."""

    _instance: Settings | None = None

    def __getattr__(self, name: str):
        if self._instance is None:
            self._instance = Settings()
        return getattr(self._instance, name)

    def __repr__(self) -> str:
        if self._instance is None:
            return "LazySettings(not initialized)"
        return repr(self._instance)


settings = _LazySettings()
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_settings_lazy.py -v`
Expected: PASS

**Step 5: Run existing settings tests to ensure backward compatibility**

Run: `pytest tests/unit/test_settings.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/config/settings.py tests/unit/test_settings_lazy.py && git commit -m "refactor(config): make Settings lazy-loaded

Import no longer requires API keys to be set.
Validation happens on first access via get_settings().
Backward compatible: `settings.attr` still works.
Closes P1.1 from AUDIT_REPORT.md.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Convert telegram_bot/services to lazy imports (P1.2)

**Files:**
- Modify: `telegram_bot/services/__init__.py`

**Step 1: Measure current import time**

Run: `python -c "import time; t=time.time(); import telegram_bot.services; print(f'{time.time()-t:.2f}s')"`
Expected: Note the time (likely 1-3s)

**Step 2: Convert to lazy imports using __getattr__**

Edit `telegram_bot/services/__init__.py`:

```python
"""Services for Telegram RAG bot.

Uses lazy imports to avoid loading heavy dependencies at import time.
Import specific services directly for best performance:
    from telegram_bot.services.voyage import VoyageService
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .cache import CacheService
    from .cesc import CESCPersonalizer, is_personalized_query
    from .embeddings import EmbeddingService
    from .llm import LLMService
    from .qdrant import QdrantService
    from .query_analyzer import QueryAnalyzer
    from .query_preprocessor import QueryPreprocessor
    from .query_router import QueryType, classify_query, get_chitchat_response, needs_rerank
    from .retriever import RetrieverService
    from .user_context import UserContextService
    from .vectorizers import UserBaseVectorizer
    from .voyage import VoyageService


__all__ = [
    "CESCPersonalizer",
    "CacheService",
    "EmbeddingService",
    "LLMService",
    "QdrantService",
    "QueryAnalyzer",
    "QueryPreprocessor",
    "QueryType",
    "RetrieverService",
    "UserBaseVectorizer",
    "UserContextService",
    "VoyageService",
    "classify_query",
    "get_chitchat_response",
    "is_personalized_query",
    "needs_rerank",
]

# Lazy import mapping
_IMPORT_MAP = {
    "CacheService": ".cache",
    "CESCPersonalizer": ".cesc",
    "is_personalized_query": ".cesc",
    "EmbeddingService": ".embeddings",
    "LLMService": ".llm",
    "QdrantService": ".qdrant",
    "QueryAnalyzer": ".query_analyzer",
    "QueryPreprocessor": ".query_preprocessor",
    "QueryType": ".query_router",
    "classify_query": ".query_router",
    "get_chitchat_response": ".query_router",
    "needs_rerank": ".query_router",
    "RetrieverService": ".retriever",
    "UserContextService": ".user_context",
    "UserBaseVectorizer": ".vectorizers",
    "VoyageService": ".voyage",
}


def __getattr__(name: str):
    """Lazy import handler."""
    if name in _IMPORT_MAP:
        import importlib
        module = importlib.import_module(_IMPORT_MAP[name], __package__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

**Step 3: Measure new import time**

Run: `python -c "import time; t=time.time(); import telegram_bot.services; print(f'{time.time()-t:.2f}s')"`
Expected: Should be <0.1s (no heavy imports)

**Step 4: Verify imports still work**

Run: `python -c "from telegram_bot.services import VoyageService, CacheService, QdrantService; print('OK')"`
Expected: `OK`

**Step 5: Run unit tests**

Run: `pytest tests/unit/services/ -v --tb=short`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add telegram_bot/services/__init__.py && git commit -m "perf(services): convert to lazy imports

Package import no longer loads all services eagerly.
Import time reduced from ~2s to <0.1s.
Closes P1.2 from AUDIT_REPORT.md.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Ensure OTEL is fully disabled in unit tests (P1.3)

**Files:**
- Modify: `tests/conftest.py`

**Step 1: Check current OTEL environment setup**

Current `tests/conftest.py` sets:
```python
os.environ.setdefault("LANGFUSE_TRACING_ENABLED", "false")
```

**Step 2: Add comprehensive OTEL disabling**

Edit `tests/conftest.py`, add after line 17:

```python
# Disable Langfuse tracing by default for tests to avoid timeouts when Langfuse
# is not running locally. Opt-in in Makefile targets that require tracing.
os.environ.setdefault("LANGFUSE_TRACING_ENABLED", "false")

# Disable all OpenTelemetry exporters to prevent network calls in unit tests
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("OTEL_TRACES_EXPORTER", "none")
os.environ.setdefault("OTEL_METRICS_EXPORTER", "none")
os.environ.setdefault("OTEL_LOGS_EXPORTER", "none")

# Disable Langfuse completely (belt and suspenders)
os.environ.setdefault("LANGFUSE_ENABLED", "false")
os.environ.setdefault("LANGFUSE_HOST", "")
```

**Step 3: Run unit tests and check for network warnings**

Run: `pytest tests/unit/ -v --tb=short 2>&1 | grep -i "langfuse\|otel\|timeout" | head -10`
Expected: No timeout warnings related to Langfuse/OTEL

**Step 4: Commit**

```bash
git add tests/conftest.py && git commit -m "test: fully disable OTEL/Langfuse in unit tests

Prevents network calls to localhost:3001 when Langfuse is not running.
Closes P1.3 from AUDIT_REPORT.md.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Bind dev ports to localhost only (P1.5)

**Files:**
- Modify: `docker-compose.dev.yml`

**Step 1: Update port bindings to 127.0.0.1**

Change all port mappings from `"PORT:PORT"` to `"127.0.0.1:PORT:PORT"` for internal services:

```yaml
# postgres
ports:
  - "127.0.0.1:5432:5432"

# redis
ports:
  - "127.0.0.1:6379:6379"

# qdrant (keep 6333 for debugging, bind to localhost)
ports:
  - "127.0.0.1:6333:6333"
  - "127.0.0.1:6334:6334"

# clickhouse
ports:
  - "127.0.0.1:8123:8123"
  - "127.0.0.1:9009:9000"

# minio
ports:
  - "127.0.0.1:9090:9000"
  - "127.0.0.1:9091:9001"

# redis-langfuse
ports:
  - "127.0.0.1:6380:6379"

# bge-m3
ports:
  - "127.0.0.1:8000:8000"

# bm42
ports:
  - "127.0.0.1:8002:8000"

# user-base
ports:
  - "127.0.0.1:8003:8000"

# docling
ports:
  - "127.0.0.1:5001:5001"

# lightrag
ports:
  - "127.0.0.1:9621:9621"

# mlflow
ports:
  - "127.0.0.1:5000:5000"
```

Keep these accessible externally (UI/API for dev):
- `langfuse: 3001:3000` (UI)
- `litellm: 4000:4000` (API gateway)

**Step 2: Verify syntax**

Run: `docker compose -f docker-compose.dev.yml config --quiet && echo "Valid"`
Expected: `Valid`

**Step 3: Verify ports are localhost-only**

Run: `grep -E '^\s+- "[0-9]+:[0-9]+"' docker-compose.dev.yml | wc -l`
Expected: 2 (only langfuse and litellm without 127.0.0.1 prefix)

**Step 4: Commit**

```bash
git add docker-compose.dev.yml && git commit -m "security(docker): bind dev ports to localhost only

Reduces attack surface - internal services not exposed to network.
Only Langfuse UI and LiteLLM API remain externally accessible.
Closes P1.5 from AUDIT_REPORT.md.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

| Task | Priority | Description | Files |
|------|----------|-------------|-------|
| 1 | P0.1 | Remove .env.server from git | .gitignore |
| 2 | P0.1 | Strengthen .dockerignore | .dockerignore |
| 3 | P0.2 | Enable CI workflow | .github/workflows/ci.yml |
| 4 | P0.3 | Fix MinIO healthcheck | docker-compose.dev.yml |
| 5 | P0.3 | Add restart policies | docker-compose.dev.yml |
| 6 | P0.4 | Upgrade to Redis Stack | docker-compose.dev.yml |
| 7 | P1.1 | Lazy settings | src/config/settings.py |
| 8 | P1.2 | Lazy service imports | telegram_bot/services/__init__.py |
| 9 | P1.3 | Disable OTEL in tests | tests/conftest.py |
| 10 | P1.5 | Localhost-only ports | docker-compose.dev.yml |

**Parallel execution groups:**
- **Group A (git/security):** Tasks 1, 2, 3
- **Group B (Docker):** Tasks 4, 5, 6, 10
- **Group C (Python):** Tasks 7, 8, 9
