# 2026-03-17 VPS Parity Audit Report

Audit date: 2026-03-17 (UTC)
Worker: `W-issue-988-vps-audit`
Branch: `wt/issue-988-vps-audit`

## Scope And Evidence

Commands/evidence gathered against live VPS (`admin@95.111.252.29:1654`):
- `docker ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'`
- `make test-bot-health-vps`
- `docker compose exec -T bot` socket checks to `qdrant:6333`, `litellm:4000`, `postgres:5432`, `redis:6379`
- `curl http://127.0.0.1:8091/health` and `curl http://127.0.0.1:8090/health`
- `/opt/rag-fresh/.env` key audit (keys only, no secret values)
- `docker compose config --services` on VPS

Local reference facts were captured from rendered compose using synthetic non-secret env values because this worktree has no `.env` file. The canonical local-release contract was later frozen and merged by PR #989: `make check`, `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`, and `make test-bot-health`.

## Parity Facts (Observed)

- VPS runtime services are healthy for core stack (`bot`, `qdrant`, `litellm`, `postgres`, `redis`) and `make test-bot-health-vps` passes with collections `conversation_history`, `gdrive_documents_bge`, `apartments`.
- VPS `.env` includes `COMPOSE_FILE=compose.yml:compose.vps.yml` and `QDRANT_COLLECTION=gdrive_documents_bge`.
- VPS `.env` does not define `COMPOSE_PROFILES`; `docker compose config --services` excludes `mini-app-api` and `mini-app-frontend`.
- Current CI deploy check command (`docker ps ... | grep -E 'vps-.*(Up|healthy)'`) returns healthy output while mini-app host endpoint check fails (`127.0.0.1:8091/health` unreachable).
- Canonical local release contract merged in PR #989 does not require mini-app startup or a mini-app endpoint check.
- Current VPS default service set excludes mini-app services because they are not part of the effective compose config without an explicit profile.

## Findings

### P0

- None verified in this audit slice.

### P1

#### F-001: Post-deploy CI verification is shallow and can pass while a required functional surface is down
- Scope: functional/runtime
- Observed state:
  - Old CI check passed on container status output even when it did not prove bot/Qdrant/LiteLLM readiness.
  - This PR replaces that shallow check with reusable release smoke covering compose status, `make test-bot-health-vps`, and bot reachability to `qdrant`, `litellm`, `postgres`, and `redis`.
- Impact: resolved by this PR; deploy no longer relies on container-status grep alone.
- Root cause hypothesis: CI contract only checked generic container status grep; no functional smoke step.
- Fix area: workflow + reusable smoke script
- Severity: Resolved by this PR

#### F-002: Mini-app remains outside the current canonical release contract and must be enabled explicitly before it can become a parity gate
- Scope: config/runtime
- Observed state:
  - `compose.yml` declares `mini-app-api` and `mini-app-frontend` behind the `bot`/`full` profiles.
  - The canonical local release contract merged in PR #989 does not require mini-app startup or a mini-app endpoint check.
  - VPS default compose service set excludes mini-app services; strict smoke (`REQUIRE_MINI_APP_ENDPOINT=true`) fails with `mini-app-frontend is not running`, while profile-aware smoke passes because the effective VPS config does not declare mini-app services.
- Impact: mini-app parity is still an open product/runtime question, but it is not a blocker for the currently documented release path.
- Root cause hypothesis: the repository does not yet define mini-app as a mandatory release surface in the frozen local reference.
- Fix area: future scope decision. If mini-app becomes mandatory, enable it in the effective compose config and switch smoke to strict mode.
- Severity: P2

### P2

#### F-003: `scripts/deploy-vps.sh` post-deploy verification was container-presence-only before this fix
- Scope: runtime/operational
- Observed state:
  - Script ends with `docker ps ... | grep vps` snapshot and does not assert bot health, in-network reachability, or mini-app endpoint contract.
- Impact: resolved by this PR; manual deploy now reuses the same functional smoke contract as CI.
- Root cause hypothesis: historical script optimized for transport/restart flow, not release contract verification.
- Fix area: deploy script reuse of shared smoke contract
- Severity: Resolved by this PR

#### F-004: One-shot `Exited (0)` compose containers exist and must not be treated as hard failure
- Scope: runtime/operational
- Observed state:
  - VPS includes `vps-hf-cache-perms-1` in `Exited (0)` state.
- Impact: naive "no exited containers" checks cause false failures and noisy deploy signals.
- Root cause hypothesis: expected one-shot init helper behavior.
- Fix area: smoke script status classification
- Severity: P2

## Verified vs Not Verified

Verified live on VPS:
- Core container health snapshot
- Qdrant collection visibility used by bot-health preflight
- Bot reachability to Qdrant/LiteLLM/Postgres/Redis
- CI-contract gap demonstration (old check passes while mini-app endpoint fails)
- Canonical local release contract from merged PR #989 excludes mini-app checks

Not fully verified in this worker slice:
- Future decision to make mini-app part of the mandatory release contract
