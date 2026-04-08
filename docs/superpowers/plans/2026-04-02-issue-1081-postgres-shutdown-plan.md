# Issue #1081 Postgres Shutdown Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent unclean PostgreSQL shutdowns in local/VPS compose flows by guaranteeing Docker gives the database enough time to flush WAL and exit cleanly before sending SIGKILL.

**Architecture:** Keep the fix at the compose contract layer instead of changing application code. Add a regression test that asserts `postgres` declares an explicit shutdown grace period, then add the minimal `compose.yml` change and verify both rendered config and a recreated container expose the expected timeout.

**Tech Stack:** Docker Compose, pytest, YAML-based compose tests

---

### Task 1: Lock the shutdown contract with a regression test

**Files:**
- Modify: `tests/unit/test_compose_config.py`
- Test: `tests/unit/test_compose_config.py`

- [ ] **Step 1: Write the failing test**

Add a test that asserts `compose.yml` declares `services.postgres.stop_grace_period` and that the duration is comfortably above the current 1-second runtime timeout.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_compose_config.py -q`
Expected: FAIL because `postgres` currently has no `stop_grace_period`.

### Task 2: Implement the compose fix

**Files:**
- Modify: `compose.yml`

- [ ] **Step 3: Write minimal implementation**

Add an explicit `stop_grace_period` to `services.postgres` in `compose.yml`. Keep the blast radius narrow: no unrelated runtime changes, no new abstractions.

- [ ] **Step 4: Run targeted tests to verify they pass**

Run: `uv run pytest tests/unit/test_compose_config.py tests/unit/test_compose.py tests/unit/test_docker_compose_profiles.py tests/unit/test_compose_langfuse.py -q`
Expected: PASS

### Task 3: Verify effective runtime behavior

**Files:**
- Modify: `compose.yml` (already above)

- [ ] **Step 5: Verify rendered compose config**

Run: `COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility config | sed -n '/^  postgres:/,/^  [a-zA-Z0-9_-]\\+:/p'`
Expected: rendered `postgres` block includes `stop_grace_period`.

- [ ] **Step 6: Recreate postgres and inspect live timeout**

Run: `COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility up -d --force-recreate postgres`

Then run: `docker inspect dev_postgres_1 --format 'StopTimeout={{json .Config.StopTimeout}} StopSignal={{json .Config.StopSignal}}'`

Expected: `StopTimeout` is no longer `1`, and the container keeps the Postgres image stop signal.
