# Dev Runtime Contract Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-align clean `dev` so the documented local bot workflow actually starts the expected host-published services, validates the right dependencies, and degrades cleanly when optional runtime services are absent.

**Architecture:** Keep the fix narrow and SDK-first. `asyncpg`, `redis.asyncio`, and `langfuse` already cover the needed behavior; the work belongs in repo-local contract glue: explicit Compose target wiring in `Makefile`, host-native defaults for native bot runs, safer Langfuse Redis Compose wiring, and better startup handling around Postgres and Redis lease refresh failures.

**Tech Stack:** Docker Compose v2, Makefile, Pydantic Settings, asyncpg, redis-py asyncio, Langfuse Python SDK, aiogram, pytest

---

## Scope Check

This is `Plan needed`, not `Quick execution`:

- It spans `Makefile`, `compose.yml`, `compose.dev.yml`, startup code, shell preflight, docs, and multiple test suites.
- The affected surfaces are runtime-impacting under `AGENTS.md`.
- The current issue is not a single failure. It is a contract split between:
  - local commands that do not explicitly load `compose.dev.yml`
  - native bot defaults that do not match password-protected local Redis
  - a broken base `redis-langfuse` command when `LANGFUSE_REDIS_PASSWORD` is unset
  - bot startup that re-probes optional Postgres after preflight already failed
  - polling lock heartbeat that stops polling on the first Redis refresh error

Do not bundle unrelated SDK cleanup or broad architecture refactors.

## SDK Coverage

| SDK | Covers | Pattern to keep | Custom glue to change |
|---|---|---|---|
| `asyncpg` | connectivity probe and pool creation | `connect(..., timeout=5)` and `create_pool(...)` | avoid duplicate startup probes after authoritative preflight already marked Postgres unavailable |
| `redis.asyncio` / `redis-py` lock | Redis client reuse, lock acquire/reacquire/release | `redis.lock(..., blocking=False, thread_local=False)` | add bounded heartbeat retry policy in bot lifecycle, not a new lock abstraction |
| `langfuse` | optional tracing init and graceful disable | `initialize_langfuse()` + `_disable_otel_exporter()` | fix local Compose dependency contract; do not add a custom tracing stack |

No new SDK is required.

## Current Audit Snapshot

These findings should drive the implementation order:

- `Makefile` local and docker dev targets currently use plain `docker compose --compatibility`, not an explicit `COMPOSE_FILE=compose.yml:compose.dev.yml` wrapper.
- Real runtime evidence on this machine shows `dev-postgres-1` running with `PortBindings={}` and its `config_files` label pointing at a base-only compose path, which explains `localhost:5432` refusal for native bot runs.
- Real runtime evidence also shows `dev-redis-langfuse-1` restart-looping with `Cmd=["redis-server","--requirepass"]`, which matches the broken base `compose.yml` command when `LANGFUSE_REDIS_PASSWORD` is empty.
- `BotConfig.redis_url` still defaults to `redis://localhost:6379`, while local dev Redis runs password-protected under `compose.dev.yml`.
- `scripts/test_bot_health.sh` currently checks only Qdrant and LiteLLM; it does not validate Redis auth or local Postgres reachability.
- `telegram_bot.preflight._check_single_dep("postgres", ...)` returns a generic warning for refused local connections.
- `PropertyBot.start()` runs preflight early, but still immediately retries `asyncpg.connect()` and `asyncpg.create_pool()` even when preflight already reported `postgres=False`.
- `_polling_lock_heartbeat()` stops polling on the first refresh exception; current tests only lock in that brittle behavior.

## File Structure Map

- Create: `tests/unit/test_local_compose_contract.py`
  - Owner tests for local Makefile/docs contract around `compose.yml:compose.dev.yml`.
- Create: `tests/unit/scripts/test_test_bot_health.py`
  - Owner tests for the local shell preflight script.
- Modify: `Makefile`
  - Introduce explicit local Compose wrapper and use it consistently for dev/local Docker targets.
- Modify: `telegram_bot/config.py`
  - Derive host-native Redis URL from `REDIS_PASSWORD` when `REDIS_URL` is unset.
- Modify: `scripts/test_bot_health.sh`
  - Validate Redis auth and local Postgres reachability in the same host-native mode as `make run-bot`.
- Modify: `compose.yml`
  - Make `redis-langfuse` safe when `LANGFUSE_REDIS_PASSWORD` is empty.
- Modify: `compose.dev.yml`
  - Preserve explicit local-only defaults and published ports.
- Modify: `telegram_bot/preflight.py`
  - Improve local Postgres remediation messaging.
- Modify: `telegram_bot/bot.py`
  - Reuse preflight output for optional Postgres and add bounded polling-lock heartbeat retries.
- Modify: `docs/LOCAL-DEVELOPMENT.md`
  - Make the canonical local workflow explicit and consistent with the updated Makefile.
- Modify: `tests/unit/config/test_bot_config_settings.py`
  - Own host-native Redis defaulting behavior.
- Modify: `tests/unit/test_compose_langfuse.py`
  - Own base/dev Langfuse Redis command and healthcheck posture.
- Modify: `tests/unit/test_preflight.py`
  - Own local Postgres remediation behavior.
- Modify: `tests/unit/test_bot_handlers.py`
  - Own startup degradation and heartbeat retry behavior.

### Task 1: Lock the local Compose target contract

**Files:**
- Create: `tests/unit/test_local_compose_contract.py`
- Modify: `Makefile`
- Modify: `docs/LOCAL-DEVELOPMENT.md`

- [ ] **Step 1: Write the failing Makefile contract test**

Create `tests/unit/test_local_compose_contract.py` with a focused assertion that local/dev Docker targets must use an explicit local Compose wrapper instead of raw `$(COMPOSE_CMD)`.

```python
def test_local_dev_targets_use_local_compose_wrapper() -> None:
    text = Path("Makefile").read_text(encoding="utf-8")
    for target in ("docker-core-up", "docker-bot-up", "docker-ml-up", "local-up", "local-down"):
        block = _target_block(text, target)
        assert "$(LOCAL_COMPOSE_CMD)" in block
```

- [ ] **Step 2: Write the failing docs contract test**

In the same test file, assert `docs/LOCAL-DEVELOPMENT.md` names `make local-up` or `make docker-up` as a path that explicitly uses `compose.yml:compose.dev.yml`.

```python
def test_local_docs_name_compose_dev_contract() -> None:
    text = Path("docs/LOCAL-DEVELOPMENT.md").read_text(encoding="utf-8")
    assert "compose.yml:compose.dev.yml" in text
```

- [ ] **Step 3: Run RED**

Run: `uv run pytest tests/unit/test_local_compose_contract.py -q`

Expected: FAIL because this test file does not exist yet and the current Makefile uses `$(COMPOSE_CMD)` directly.

- [ ] **Step 4: Implement explicit local Compose wiring**

Add:

```make
LOCAL_COMPOSE_FILE := compose.yml:compose.dev.yml
LOCAL_COMPOSE_CMD := COMPOSE_FILE=$(LOCAL_COMPOSE_FILE) $(COMPOSE_CMD)
```

Then switch the local/dev Docker targets to `$(LOCAL_COMPOSE_CMD)`:

- `docker-core-up`
- `docker-bot-up`
- `docker-obs-up`
- `docker-ml-up`
- `docker-ai-up`
- `docker-ingest-up`
- `docker-voice-up`
- `docker-full-up`
- `docker-down`
- `docker-ps`
- `local-up`
- `local-down`
- `local-logs`
- `local-ps`
- `local-build`

- [ ] **Step 5: Update docs to match the fixed target behavior**

State clearly that local Docker commands load `compose.yml:compose.dev.yml` explicitly and are not expected to rely on `COMPOSE_FILE` leaking in from the shell or `.env`.

- [ ] **Step 6: Run GREEN**

Run: `uv run pytest tests/unit/test_local_compose_contract.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add Makefile docs/LOCAL-DEVELOPMENT.md tests/unit/test_local_compose_contract.py
git commit -m "fix: make local docker targets use dev compose override"
```

### Task 2: Lock the native Redis contract for `make run-bot`

**Files:**
- Modify: `tests/unit/config/test_bot_config_settings.py`
- Create: `tests/unit/scripts/test_test_bot_health.py`
- Modify: `telegram_bot/config.py`
- Modify: `scripts/test_bot_health.sh`
- Modify: `docs/LOCAL-DEVELOPMENT.md`

- [ ] **Step 1: Write the failing config test**

Add a unit test proving that host-native bot runs derive an auth-aware Redis URL from `REDIS_PASSWORD` when `REDIS_URL` is not set.

```python
def test_config_derives_local_redis_url_from_password(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("REDIS_PASSWORD", "dev_redis_pass")
    config = BotConfig(_env_file=None)
    assert config.redis_url == "redis://:dev_redis_pass@localhost:6379"
```

- [ ] **Step 2: Run RED on config behavior**

Run: `uv run pytest tests/unit/config/test_bot_config_settings.py -q`

Expected: FAIL because `redis_url` still defaults to `redis://localhost:6379`.

- [ ] **Step 3: Write the failing script contract test**

Create `tests/unit/scripts/test_test_bot_health.py` and assert the shell health check reuses `BotConfig` or equivalent host-native resolution for Redis instead of probing only Qdrant and LiteLLM.

```python
def test_bot_health_checks_redis_auth_contract() -> None:
    text = Path("scripts/test_bot_health.sh").read_text(encoding="utf-8")
    assert "REDIS" in text
    assert "localhost:6379" in text or "BotConfig" in text
```

- [ ] **Step 4: Run RED on the shell contract**

Run: `uv run pytest tests/unit/scripts/test_test_bot_health.py -q`

Expected: FAIL because the script does not validate Redis today.

- [ ] **Step 5: Implement host-native Redis defaulting**

In `telegram_bot/config.py`, add a small helper that derives `redis://:REDIS_PASSWORD@localhost:6379` only when:

- `REDIS_URL` is absent
- `REDIS_PASSWORD` is non-empty

Do not override an explicit `REDIS_URL`.

- [ ] **Step 6: Extend `scripts/test_bot_health.sh`**

Add a Redis check that:

- resolves the same host-native URL contract as the bot
- verifies auth success when `REDIS_PASSWORD` is set
- fails clearly if Redis is unreachable or password-protected with a mismatched URL

Keep this script bounded to local bot prerequisites; do not turn it into a full-stack end-to-end test.

- [ ] **Step 7: Document the native Redis behavior**

Update `docs/LOCAL-DEVELOPMENT.md` to state that native bot runs either:

- use explicit `REDIS_URL`, or
- derive `REDIS_URL` from `REDIS_PASSWORD` for local Docker Redis

- [ ] **Step 8: Run GREEN**

Run:

- `uv run pytest tests/unit/config/test_bot_config_settings.py -q`
- `uv run pytest tests/unit/scripts/test_test_bot_health.py -q`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add telegram_bot/config.py scripts/test_bot_health.sh docs/LOCAL-DEVELOPMENT.md tests/unit/config/test_bot_config_settings.py tests/unit/scripts/test_test_bot_health.py
git commit -m "fix: align native bot redis contract with local dev"
```

### Task 3: Fix the Langfuse Redis Compose contract

**Files:**
- Modify: `tests/unit/test_compose_langfuse.py`
- Modify: `compose.yml`
- Modify: `compose.dev.yml`

- [ ] **Step 1: Write the failing base Compose command test**

Extend `tests/unit/test_compose_langfuse.py` with a regression test asserting that base `redis-langfuse` does not render an invalid bare `--requirepass` command when `LANGFUSE_REDIS_PASSWORD` is empty.

```python
def test_base_redis_langfuse_command_is_safe_without_password(compose_base: dict):
    command = compose_base["services"]["redis-langfuse"]["command"]
    assert 'redis-server --requirepass ${LANGFUSE_REDIS_PASSWORD:-}' not in str(command)
```

- [ ] **Step 2: Write the failing healthcheck test**

Assert the base healthcheck also works with and without a password.

```python
def test_base_redis_langfuse_healthcheck_handles_optional_password(compose_base: dict):
    test_cmd = compose_base["services"]["redis-langfuse"]["healthcheck"]["test"]
    assert "${LANGFUSE_REDIS_PASSWORD:-}" not in str(test_cmd)
```

- [ ] **Step 3: Run RED**

Run: `uv run pytest tests/unit/test_compose_langfuse.py -q`

Expected: FAIL because base Compose still uses the broken string form.

- [ ] **Step 4: Implement minimal safe Compose logic**

In `compose.yml`, replace the broken string command with a shell-based conditional that:

- starts `redis-server --requirepass "$LANGFUSE_REDIS_PASSWORD"` when the password is non-empty
- otherwise starts plain `redis-server`

Use the same conditional shape for the healthcheck.

Do not move dev-only defaults into the base file.

- [ ] **Step 5: Keep `compose.dev.yml` explicit**

Retain the current dev-only `langfuseredis` fallback in `compose.dev.yml` so local ML profile remains convenient.

- [ ] **Step 6: Run GREEN**

Run: `uv run pytest tests/unit/test_compose_langfuse.py tests/unit/test_compose_langfuse_runtime_contract.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add compose.yml compose.dev.yml tests/unit/test_compose_langfuse.py
git commit -m "fix: harden langfuse redis compose contract"
```

### Task 4: Reduce noisy Postgres degradation in startup

**Files:**
- Modify: `tests/unit/test_preflight.py`
- Modify: `tests/unit/test_bot_handlers.py`
- Modify: `telegram_bot/preflight.py`
- Modify: `telegram_bot/bot.py`

- [ ] **Step 1: Write the failing local remediation test**

Extend `tests/unit/test_preflight.py` so a refused `localhost:5432` Postgres connection produces a remediation hint that points at the local Compose contract instead of only logging a generic unreachable warning.

```python
async def test_postgres_preflight_logs_local_remediation_on_connection_refused(caplog):
    config = _make_config(realestate_database_url="postgresql://u:p@localhost:5432/realestate")
    with patch("telegram_bot.preflight.asyncpg") as mock_asyncpg:
        mock_asyncpg.connect = AsyncMock(side_effect=ConnectionRefusedError(111, "Connection refused"))
        client = AsyncMock()
        result = await _check_single_dep("postgres", config, client)
    assert result is False
    assert "make local-up" in caplog.text or "compose.dev.yml" in caplog.text
```

- [ ] **Step 2: Run RED for preflight**

Run: `uv run pytest tests/unit/test_preflight.py -q -k postgres`

Expected: FAIL because the local remediation text does not exist yet.

- [ ] **Step 3: Write the failing startup reuse test**

Extend `tests/unit/test_bot_handlers.py` so startup does not immediately run another optional Postgres connect/pool attempt when `check_dependencies()` already returned `{"postgres": False}`.

```python
async def test_start_skips_postgres_pool_when_preflight_already_failed(mock_config):
    bot, _ = _create_bot(mock_config)
    result = DependencyCheckResult({"redis": True, "postgres": False}, report=StartupReport())
    with (
        patch("telegram_bot.preflight.check_dependencies", new_callable=AsyncMock, return_value=result),
        patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect,
        patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_pool,
    ):
        await bot.start()
    mock_connect.assert_not_awaited()
    mock_pool.assert_not_awaited()
```

- [ ] **Step 4: Run RED for startup behavior**

Run: `uv run pytest tests/unit/test_bot_handlers.py -q -k postgres`

Expected: FAIL because startup currently re-probes Postgres after preflight.

- [ ] **Step 5: Implement the minimal remediation helper**

In `telegram_bot/preflight.py`, add a small DSN-aware helper that appends local remediation when the host is `localhost` or `127.0.0.1`.

- [ ] **Step 6: Reuse authoritative preflight output in startup**

In `telegram_bot/bot.py`, gate the optional Postgres pool branch on the existing preflight result:

- if preflight says Postgres is available, run the current pool init path
- if preflight says Postgres is unavailable, skip pool init and rely on the existing degraded startup report

Do not change Postgres from optional to critical.

- [ ] **Step 7: Run GREEN**

Run:

- `uv run pytest tests/unit/test_preflight.py -q -k postgres`
- `uv run pytest tests/unit/test_bot_handlers.py -q -k postgres`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add telegram_bot/preflight.py telegram_bot/bot.py tests/unit/test_preflight.py tests/unit/test_bot_handlers.py
git commit -m "fix: reduce noisy postgres startup degradation"
```

### Task 5: Make polling lock heartbeat tolerate transient Redis failures

**Files:**
- Modify: `tests/unit/test_bot_handlers.py`
- Modify: `telegram_bot/bot.py`

- [ ] **Step 1: Write the failing transient failure test**

Extend `tests/unit/test_bot_handlers.py` so one failed `refresh()` call does not stop polling immediately.

```python
async def test_polling_lock_heartbeat_retries_before_stopping(mock_config):
    bot, _ = _create_bot(mock_config)
    bot._polling_lock = AsyncMock()
    bot._polling_lock.ttl_sec = 3
    bot._polling_lock.refresh = AsyncMock(side_effect=[RuntimeError("redis lost"), None, asyncio.CancelledError()])
    bot.dp = MagicMock()
    bot.dp.stop_polling = AsyncMock()
```

Assert `stop_polling` is not awaited after the first failure.

- [ ] **Step 2: Write the failing exhaustion test**

Add a second test proving that repeated failures still stop polling after a bounded threshold.

```python
assert bot.dp.stop_polling.await_count == 1
```

- [ ] **Step 3: Run RED**

Run: `uv run pytest tests/unit/test_bot_handlers.py -q -k polling_lock_heartbeat`

Expected: FAIL because the current implementation stops on the first exception.

- [ ] **Step 4: Implement bounded heartbeat retries**

Keep `RedisPollingLock` thin. Put the policy in `_polling_lock_heartbeat()`:

- track consecutive refresh failures
- warn and continue below threshold
- reset the counter after a successful refresh
- stop polling only after the retry budget is exhausted

- [ ] **Step 5: Run GREEN**

Run: `uv run pytest tests/unit/test_bot_handlers.py -q -k polling_lock_heartbeat`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add telegram_bot/bot.py tests/unit/test_bot_handlers.py
git commit -m "fix: retry polling lock refresh before stopping bot"
```

### Task 6: Verification

**Files:**
- Modify: none

- [ ] **Step 1: Run focused unit suites**

Run:

- `uv run pytest tests/unit/test_local_compose_contract.py tests/unit/scripts/test_test_bot_health.py tests/unit/config/test_bot_config_settings.py tests/unit/test_compose_langfuse.py tests/unit/test_compose_langfuse_runtime_contract.py tests/unit/test_preflight.py tests/unit/test_bot_handlers.py -q`

- [ ] **Step 2: Validate rendered local Compose config with explicit dummy env**

Run:

```bash
POSTGRES_PASSWORD=x REDIS_PASSWORD=x TELEGRAM_BOT_TOKEN=x LITELLM_MASTER_KEY=x OPENAI_API_KEY=x LLM_API_KEY=x NEXTAUTH_SECRET=x SALT=x ENCRYPTION_KEY=x LIVEKIT_API_KEY=x LIVEKIT_API_SECRET=x GDRIVE_SYNC_DIR=/tmp COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility config --services
POSTGRES_PASSWORD=x REDIS_PASSWORD=x TELEGRAM_BOT_TOKEN=x LITELLM_MASTER_KEY=x OPENAI_API_KEY=x LLM_API_KEY=x NEXTAUTH_SECRET=x SALT=x ENCRYPTION_KEY=x LIVEKIT_API_KEY=x LIVEKIT_API_SECRET=x GDRIVE_SYNC_DIR=/tmp COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility config | rg 'published: "5432"|published: "6379"|published: "3001"|published: "6380"'
```

Expected: rendered config includes the host-published local ports and no malformed `redis-langfuse` command.

- [ ] **Step 3: Validate the actual local health script**

Run:

- `make test-bot-health`

Expected: it passes on a correctly started local stack, or fails with clear Redis/Postgres/Qdrant/LiteLLM diagnostics.

- [ ] **Step 4: Run repo-required gates if feasible**

Run:

- `make check`
- `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`

- [ ] **Step 5: Record any skipped verification explicitly**

If Docker verification or full gates are skipped, record exactly what was skipped and why.

---

Manual review note: this refreshed plan supersedes the earlier dirty-worktree draft because clean `dev` exposed a more fundamental root cause in `Makefile` and local runtime defaults.
