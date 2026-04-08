# Issue #1080 Langfuse Connectivity Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Identify and fix the real root cause behind Langfuse failing to reach PostgreSQL, ClickHouse, and Redis in the local/dev Docker runtime, then lock the fix with regression coverage.

**Architecture:** Treat this as a runtime-debugging task first, not a blind compose edit. Reproduce the broken stack with explicit evidence at the Docker Compose layer, compare the effective service/profile/network shape against the intended Langfuse topology, then apply the smallest config change that restores connectivity and codify that contract in tests.

**Tech Stack:** Docker Compose, YAML, `.env.example`, `pytest`, `uv`, existing compose contract tests

---

### Task 1: Reproduce and capture the real failure boundary

**Files:**
- Modify: `docs/superpowers/plans/2026-04-02-issue-1080-langfuse-connectivity-plan.md`
- Reference: `compose.yml`
- Reference: `compose.dev.yml`
- Reference: `compose.vps.yml`

- [ ] **Step 1: Start from the exact reported runtime path**

Run:
`COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --profile ml --compatibility up -d clickhouse minio redis-langfuse langfuse-worker langfuse postgres`

Expected: the Langfuse stack starts in the same `dev-*` namespace as reported in the issue.

- [ ] **Step 2: Capture container/network evidence instead of guessing**

Run:
- `docker compose -f compose.yml -f compose.dev.yml --profile ml ps`
- `docker inspect dev-langfuse-1 --format '{{json .NetworkSettings.Networks}}'`
- `docker inspect dev-clickhouse-1 --format '{{json .NetworkSettings.Networks}}'`
- `docker inspect dev-redis-langfuse-1 --format '{{json .NetworkSettings.Networks}}'`
- `docker inspect dev-postgres-1 --format '{{json .NetworkSettings.Networks}}'`
- `docker logs dev-langfuse-1 --tail 200`
- `docker logs dev-langfuse-worker-1 --tail 200`

Expected: clear evidence whether the problem is profile gating, service absence, wrong hostnames, or readiness/order.

- [ ] **Step 3: Record the root-cause hypothesis**

Write down one specific hypothesis, for example:
- profile mismatch means dependencies are not on the same network
- service names are correct but startup order/readiness is insufficient
- Langfuse env vars are using the wrong host or protocol

Do not edit code before this step is explicit.

### Task 2: Lock the broken contract with tests

**Files:**
- Modify: `tests/unit/test_compose_langfuse.py`
- Create: `tests/unit/test_compose_langfuse_runtime_contract.py`

- [ ] **Step 1: Add a failing regression test for the discovered root cause**

Depending on the actual evidence, add one focused failing test that codifies the missing contract. Candidates:
- Langfuse services and their stateful dependencies must share compatible profiles
- Langfuse services must depend on all required stateful services with health-based conditions
- Langfuse runtime env must point only at Docker-internal service names

Keep the test as small as possible and target the root cause only.

- [ ] **Step 2: Run RED**

Run:
`uv run pytest tests/unit/test_compose_langfuse.py tests/unit/test_compose_langfuse_runtime_contract.py -q`

Expected: fail on the missing/broken contract.

### Task 3: Apply the minimal compose fix

**Files:**
- Modify: `compose.yml`
- Modify: `compose.dev.yml`
- Modify: `compose.vps.yml` only if the root cause truly lives there
- Modify: `.env.example` only if missing runtime documentation is part of the cause

- [ ] **Step 1: Implement one minimal fix**

Examples, depending on the proven root cause:
- align `profiles:` so Langfuse and its dependencies are activated together
- change `depends_on` conditions or service definitions so startup ordering is valid
- fix a host/URL env var to use the correct Docker-internal target

Do not bundle unrelated cleanup from the issue body unless the evidence shows it is part of the same fault.

- [ ] **Step 2: Re-run RED-path tests to GREEN**

Run:
`uv run pytest tests/unit/test_compose_langfuse.py tests/unit/test_compose_langfuse_runtime_contract.py -q`

Expected: pass.

### Task 4: Verify the actual runtime is repaired

**Files:**
- Modify: `docs/plans/2026-04-01-open-issues-triage-snapshot.md`

- [ ] **Step 1: Recreate the stack and verify health**

Run:
- `COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --profile ml --compatibility up -d clickhouse minio redis-langfuse langfuse-worker langfuse postgres`
- `docker logs dev-langfuse-1 --tail 200 | rg -i 'error|P1001|ETIMEDOUT|no such host|connect: connection refused'`
- `docker logs dev-langfuse-worker-1 --tail 200 | rg -i 'error|ETIMEDOUT|no such host|connect: connection refused'`
- `docker exec dev-langfuse-1 getent hosts postgres clickhouse redis-langfuse`
- `docker exec dev-langfuse-1 wget -qO- http://127.0.0.1:3000/api/public/health`

Expected: no connectivity errors remain, hostnames resolve, and Langfuse health responds.

- [ ] **Step 2: Run repo verification**

Run:
- `make check`
- `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`

Expected: pass.

- [ ] **Step 3: Update shared issue tracking**

If the fix is implemented and verified:
- close `#1080`
- update `docs/plans/2026-04-01-open-issues-triage-snapshot.md`
- move `#1080` out of `Plan needed`
- switch `Next recommended task` to `#1081`
