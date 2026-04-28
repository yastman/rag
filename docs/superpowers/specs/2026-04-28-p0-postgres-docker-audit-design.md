# P0 Postgres Shutdown And Docker Runtime Audit Design

## Context

Issue `#1081` tracks repeated PostgreSQL unclean shutdowns, WAL recovery messages, and autovacuum startup warnings. It is the only open `P0-critical` issue in the current backlog, so the execution order starts there even though `#1194` previously excluded production durability incidents from the local stabilization cycle.

Initial evidence collected on 2026-04-28 shows that the original suspected compose defect is already remediated on `dev`:

- `compose.yml` declares `services.postgres.stop_grace_period: 30s`.
- The live local Postgres container exposed `StopTimeout=30` and `StopSignal="SIGINT"`.
- A controlled `docker stop -t 30` produced a clean PostgreSQL shutdown.
- A direct `docker start dev-postgres-1` failed because Docker Desktop had a stale WSL bind mount for `./docker/postgres/init`.
- `COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility up -d postgres` recreated the container and restored a healthy Postgres service.

This means the remaining work must distinguish between a fixed compose shutdown contract, operator/runtime lifecycle problems, and any unrelated Docker service failures.

## Goal

Close `#1081` only after producing evidence that the current Postgres compose contract shuts down cleanly and documenting the correct recovery path. In the same pass, audit the local Docker Compose runtime and create separate GitHub issues for broken services that are not part of `#1081`.

## Non-Goals

- Do not fix every Docker service failure inside `#1081`.
- Do not perform VPS or production host remediation in this cycle.
- Do not delete volumes, reset databases, or run destructive cleanup as part of the audit.
- Do not close issues based only on static config; runtime evidence is required.

## Scope

The audit targets the local Docker Compose runtime first:

- Effective config from `COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility config`.
- Service inventory from `docker compose --compatibility config --services`.
- Core/default services and profile-gated groups that can be started locally without production secrets.
- Postgres lifecycle checks: rendered `stop_grace_period`, live `StopTimeout`, `StopSignal`, controlled stop/start behavior, recent recovery log lines, and Docker events when available.
- Service health checks: `docker compose ps`, container health status, relevant startup logs, and lightweight reachability checks where the repo already has helper scripts.

If the local audit exposes a production-specific gap that cannot be verified locally, create a separate issue with the evidence and mark it as requiring VPS investigation.

## Approach

Use a two-part workflow.

First, resolve `#1081` as a root-cause close-out:

1. Verify the current compose shutdown contract for Postgres.
2. Reproduce a controlled local stop/start through the supported Compose path.
3. Capture evidence that controlled shutdown is clean.
4. Document the stale WSL bind-mount failure mode and the correct recovery command.
5. Close `#1081` only if the evidence supports that the tracked compose-level failure is fixed.

Second, run a local Docker service audit:

1. Render effective Compose config with native Docker Compose env handling.
2. List service sets and identify profile-gated services.
3. Start the safe local service groups in a bounded order.
4. Check health, logs, and reachability.
5. For each distinct failure, create a GitHub issue with command output, affected service, suspected lane, suggested priority, and reproduction steps.

## Issue Creation Rules

Create a new issue only when the failure is distinct, reproducible, and not already tracked by an open issue. Each new issue should include:

- Observed failure and timestamp.
- Commands used to reproduce.
- Relevant logs or inspect output.
- Affected Compose files or service names.
- Proposed labels such as `infra`, `bug`, `lane:quick-execution`, `lane:plan-needed`, or priority labels.
- A note linking it to the Docker runtime audit.

Do not create issues for expected missing production secrets in local dev unless the local dev contract claims the service should run without them.

## Error Handling

If a service fails because of stale Docker Desktop WSL bind mounts, prefer `docker compose up -d <service>` or `--force-recreate` over direct `docker start`. Record the exact error and create a GitHub issue only if the repo lacks documentation or a recovery guardrail for the failure mode.

If the audit would require destructive recovery, stop and record the blocker instead of modifying volumes or deleting state.

If a service requires unavailable secrets, classify it as out of local audit scope unless the repo documentation says local defaults should cover it.

## Validation

Minimum validation before closing `#1081`:

- Rendered compose config includes Postgres `stop_grace_period`.
- Live Postgres container has `StopTimeout >= 30`.
- Controlled Compose-managed restart produces clean shutdown evidence.
- Existing compose tests covering the Postgres shutdown contract pass.

Minimum validation for the Docker audit:

- Effective local service list captured.
- Health status captured for started services.
- Failures are either explained, linked to existing issues, or converted into new GitHub issues.

## Handoff

After this design is approved, write an implementation plan for:

1. `#1081` evidence collection, documentation, validation, and close-out.
2. Local Docker Compose service audit.
3. GitHub issue creation for newly discovered broken services.

Implementation must follow the repo issue-triage lanes and use separate issues for follow-up fixes outside the `#1081` root-cause close-out.
