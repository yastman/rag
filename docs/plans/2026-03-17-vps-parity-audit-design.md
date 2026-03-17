# VPS Parity Audit And Fix Design

> **For Codex:** This design defines the target operating model for making the local Docker stack the source of truth and bringing VPS runtime to parity before merges to `main`.

**Goal:** Make the local Docker stack the reference environment, remove functional drift on VPS, and enforce a reliable `dev -> main -> autodeploy -> VPS smoke` release path.

**Architecture:** Local Docker runtime is the canonical reference. Audit compares local and VPS across `config`, `data`, `runtime`, and `functional` layers. Fixes land in `dev`, `main` is used only for validated release state, and VPS autodeploy is followed by mandatory post-deploy smoke checks.

**Tech Stack:** Docker Compose, GitHub Actions, Telegram bot, LiteLLM, Qdrant, Redis, PostgreSQL, mini app, ingestion pipeline.

---

## 1. Problem Statement

The current operating model is unstable because local Docker runtime and VPS runtime are not yet guaranteed to be equivalent. A green container list on VPS is not enough to claim the system works. The actual release requirement is stricter: the full required stack must behave the same way on VPS as it does locally.

The current repo state already shows parity risk:

- local `make check` is red
- local `make test-unit` is red
- local `make test-bot-health` is red
- VPS `make test-bot-health-vps` is green
- local and VPS do not agree on the effective Qdrant collection default
- local `mini-app-frontend` is currently `unhealthy`
- current autodeploy verification is too weak to prove functional correctness after deploy

This means the team cannot safely use `main` as a release branch yet. The first priority is not deployment automation itself, but parity and verification discipline.

## 2. Target State

The desired model is:

1. Local Docker stack is the source of truth.
2. `dev` is the integration branch where all fixes are validated.
3. `main` contains only validated release state.
4. Merge to `main` triggers autodeploy to VPS.
5. VPS post-deploy smoke verifies that the deployed system is equivalent to the validated local reference.

Under this model, `main` is never used to discover whether the system works on the server. `main` is only used to release a state already proven locally and audited against VPS expectations.

## 3. Audit Scope

Audit compares `local reference` and `VPS runtime` across four layers.

### 3.1 Config Audit

Compare:

- `compose.yml`
- `compose.dev.yml`
- `compose.vps.yml`
- rendered `docker compose config` locally
- rendered `docker compose config` on VPS
- local `.env` and VPS `/opt/rag-fresh/.env` by key presence and effective values for non-secret operational flags
- `COMPOSE_FILE`
- service list
- build vs image usage
- healthchecks
- volumes
- restart policy
- published ports

Critical variables to audit:

- `QDRANT_COLLECTION`
- `QDRANT_URL`
- `REDIS_URL`
- `REDIS_PASSWORD`
- `POSTGRES_PASSWORD`
- `LITELLM_MASTER_KEY`
- `OPENAI_API_KEY`
- `CEREBRAS_API_KEY`
- `GROQ_API_KEY`
- `LANGFUSE_*`
- `KOMMO_*`
- `RERANK_PROVIDER`
- `RERANK_CANDIDATES_MAX`
- `CLIENT_DIRECT_PIPELINE_ENABLED`

### 3.2 Data Audit

Compare:

- Qdrant collections present locally and on VPS
- any aliases used by runtime
- presence of the actual production collection
- whether required collections contain usable data
- Postgres schema readiness
- Redis availability and expected mode
- ingestion target collection consistency

For this system, missing or wrong Qdrant data is a functional outage even if containers are healthy.

### 3.3 Runtime Audit

Check:

- `docker compose ps`
- unhealthy containers
- restarting containers
- service logs for recent startup errors
- network reachability from `bot` to `qdrant`, `litellm`, `postgres`, `redis`
- file permission issues
- bind mount and volume issues
- startup ordering and dependency problems

### 3.4 Functional Audit

Verify actual product behavior, not just infrastructure:

- Telegram bot can answer a real RAG request
- bot can see the intended Qdrant collection
- LiteLLM responds correctly
- mini app frontend is reachable and usable
- mini app backend responds correctly if required
- ingestion can write to the expected target collection if part of the required stack
- observability path is not silently broken if Langfuse is required

## 4. Findings Model

Audit output must be structured into findings, not raw notes.

Each finding should contain:

- `Scope`: config, data, runtime, or functional
- `Observed state`: verified local state vs verified VPS state
- `Impact`: what is actually broken or risky
- `Root cause hypothesis`: only when supported by evidence
- `Fix area`: repo, VPS env, data, compose, workflow, deploy script
- `Severity`: `P0`, `P1`, or `P2`

Severity model:

- `P0`: blocks merge to `main`
- `P1`: does not block startup but makes release unsafe
- `P2`: creates drift, confusion, or weak signals but is not an immediate blocker

## 5. Known Baseline Findings

Already confirmed:

- local `make check` fails on import ordering in `src/evaluation/mlflow_integration.py`
- local `make test-unit` fails on three tests
- local `make test-bot-health` checks the outdated default collection `contextual_bulgaria_voyage`
- VPS `make test-bot-health-vps` passes against `gdrive_documents_bge`
- local `mini-app-frontend` is `unhealthy`
- current GitHub Actions deploy check is shallow and does not confirm product behavior

These findings are enough to classify the repo as not release-ready.

## 6. Fix Strategy

### Phase 1: Stabilize Local Validation

Fix all local release blockers in `dev`:

- restore green `make check`
- restore green `make test-unit`
- restore green `make test-bot-health`
- fix or explain `mini-app-frontend` unhealthy state if mini app is part of the required stack

This phase is mandatory because local runtime is the source of truth.

### Phase 2: Freeze Local Reference

Document the exact local release reference:

- canonical compose file set
- mandatory services
- mandatory env keys
- canonical Qdrant collection name
- mandatory smoke checks

This prevents future ambiguity about what “working locally” means.

### Phase 3: Audit VPS Against Reference

Collect parity evidence:

- rendered compose config locally and on VPS
- env key diff
- Qdrant collection diff
- runtime status diff
- functional smoke results

Output must be a findings table with severity.

### Phase 4: Remove Drift

Close all `P0` and `P1` findings by aligning:

- env keys and effective values
- collection names and data targets
- compose behavior
- service enablement
- health checks
- runtime assumptions

### Phase 5: Harden Deployment

Autodeploy must verify more than container startup.

Required post-deploy checks:

- `docker compose ps`
- `make test-bot-health-vps`
- mini app endpoint verification if required
- targeted log scan for `bot`, `litellm`, `mini-app-frontend`, `mini-app-api`, `ingestion`

## 7. Release Policy

Target release process:

1. Fixes land in `dev`.
2. `dev` must pass local release-gate.
3. PR `dev -> main`.
4. Merge to `main`.
5. GitHub Actions autodeploys to VPS.
6. VPS post-deploy smoke runs.
7. Release is considered successful only if smoke passes.

Local release-gate should include:

- `make check`
- `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`
- `make test-bot-health`
- required local functional smoke

VPS release-gate should include:

- `docker compose ps`
- `make test-bot-health-vps`
- required VPS functional smoke

## 8. Required Repo Changes

Likely change areas:

- `scripts/test_bot_health.sh`
- `.github/workflows/ci.yml`
- `scripts/deploy-vps.sh`
- `DOCKER.md`
- `README.md`
- `docs/LOCAL-DEVELOPMENT.md`
- failing tests under `tests/unit/...`
- possibly compose files and mini app runtime definitions

## 9. Deliverables

This design should be followed by an executable implementation plan:

- `docs/plans/2026-03-17-vps-parity-fix-plan.md`

That follow-up plan must convert the audit and fix strategy into concrete tasks, files, commands, and verification checkpoints.

## 10. Exit Criteria

This effort is complete only when all of the following are true:

- local release-gate is green
- local health and functional smoke are green
- VPS parity audit has no open `P0` findings
- VPS post-deploy smoke is green after merge to `main`
- release process no longer relies on `main` or VPS as a debugging environment
