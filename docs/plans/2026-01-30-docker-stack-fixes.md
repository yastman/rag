# Docker Stack Fixes Implementation Plan

> Execute task-by-task. No special sub-skill required.

**Goal:** Fix Qdrant insecure connection warning by properly handling empty API key.

**Architecture:** Single fix in config.py to convert empty string to None. Langfuse and LiteLLM issues were startup race conditions — migrations already applied successfully.

**Tech Stack:** Python, Optional types

---

## Pre-verification Summary

After investigation, the actual state is:

| Issue | Status | Action |
|-------|--------|--------|
| Langfuse `partner` column | ✅ Exists | No fix needed |
| LiteLLM views | ✅ All 8 views exist | No fix needed |
| Qdrant warning | ⚠️ Empty string passed as api_key | **Fix needed** |

The Langfuse/LiteLLM errors in logs were from startup race conditions when worker tried to access tables before migrations completed. Current state is healthy.

---

## Task 1: Fix Qdrant API Key Handling

**Problem:** `QDRANT_API_KEY=` in `.env` results in empty string `""` being passed to AsyncQdrantClient, which triggers the "insecure connection" warning. The warning is correct — we're passing credentials over HTTP.

**Root cause fix:** Convert empty string to `None` so no API key is used for local HTTP connections.

**Files:**
- Modify: `telegram_bot/config.py` (BotConfig `qdrant_api_key`)
- Verify: Docker logs (bot)

**Step 1: Read current config**

Verify current implementation:
```python
# Current (problematic)
qdrant_api_key: str = os.getenv("QDRANT_API_KEY", "")
```

**Step 2: Fix api_key to return None for empty values**

```python
# Change from:
qdrant_api_key: str = os.getenv("QDRANT_API_KEY", "")

# Change to:
qdrant_api_key: Optional[str] = os.getenv("QDRANT_API_KEY") or None
```

Also add `Optional` import if not present:
```python
from typing import Optional  # at top of file
```

**Step 2.1: Sanity-check type usage**

If any code assumes `qdrant_api_key` is always `str`, adjust type hints accordingly.

**Step 3: Rebuild and restart bot**

Run: `docker compose -f docker-compose.dev.yml build bot && docker compose -f docker-compose.dev.yml up -d bot`

Expected: Container rebuilds and starts

**Step 4: Verify warning is gone**

Run: `sleep 10 && docker logs dev-bot 2>&1 | grep -i "insecure"`

Expected: No output (warning gone because api_key=None, not "")

**Note:** This removes the warning by removing credentials on HTTP when the env var is empty.
To test production-like behavior, set a real `QDRANT_API_KEY` and use HTTPS.

**Step 5: Verify bot still works**

Run: `docker logs dev-bot --tail 10 2>&1`

Expected: Shows "Start polling" and bot is healthy

**Step 6: Commit**

```bash
git add telegram_bot/config.py
git commit -m "fix(config): convert empty QDRANT_API_KEY to None

Empty string was being passed to AsyncQdrantClient, triggering
'Api key is used with an insecure connection' warning. Now empty
env var correctly results in None (no API key for local HTTP)."
```

---

## Task 2: Document Startup Race Condition (Optional)

**Files:**
- Modify: `docker-compose.dev.yml` (add comment)

**Step 1: Add clarifying comment about startup order**

In `docker-compose.dev.yml`, near langfuse-worker service:

```yaml
  # Langfuse v3 Worker
  # NOTE: On first start, you may see "column does not exist" errors.
  # This is a race condition - worker starts before migrations complete.
  # Errors should resolve after ~30s when migrations finish. If errors persist, investigate migrations.
  langfuse-worker:
```

**Step 2: Commit**

```bash
git add docker-compose.dev.yml
git commit -m "docs(docker): clarify Langfuse startup race condition

Add comment explaining that 'column does not exist' errors on first
start are expected and resolve after migrations complete."
```

---

## Summary

| Task | Description | Time |
|------|-------------|------|
| 1 | Fix Qdrant api_key empty string → None | ~5 min |
| 2 | Document startup race condition (optional) | ~2 min |

**Total: 1 required fix, ~5 minutes**

The original plan over-engineered the solution. Actual issues were:
- Qdrant: Config bug (empty string vs None)
- Langfuse/LiteLLM: Already working, just startup noise
