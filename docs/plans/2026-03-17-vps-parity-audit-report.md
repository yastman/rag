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

Local reference facts were captured from rendered compose using synthetic non-secret env values because this worktree has no `.env` file. Canonical local-release freeze is owned by the local-gate worker and is not merged in this branch yet.

## Parity Facts (Observed)

- VPS runtime services are healthy for core stack (`bot`, `qdrant`, `litellm`, `postgres`, `redis`) and `make test-bot-health-vps` passes with collections `conversation_history`, `gdrive_documents_bge`, `apartments`.
- VPS `.env` includes `COMPOSE_FILE=compose.yml:compose.vps.yml` and `QDRANT_COLLECTION=gdrive_documents_bge`.
- VPS `.env` does not define `COMPOSE_PROFILES`; `docker compose config --services` excludes `mini-app-api` and `mini-app-frontend`.
- Current CI deploy check command (`docker ps ... | grep -E 'vps-.*(Up|healthy)'`) returns healthy output while mini-app host endpoint check fails (`127.0.0.1:8091/health` unreachable).
- Local compose with `--profile bot` includes mini-app services; current VPS default service set does not.

## Findings

### P0

- None verified in this audit slice.

### P1

#### F-001: Post-deploy CI verification is shallow and can pass while a required functional surface is down
- Scope: functional/runtime
- Observed state:
  - Local release intent in plan requires post-deploy functional smoke including mini-app endpoint.
  - VPS: current CI check passes on container status output while `curl http://127.0.0.1:8091/health` fails.
- Impact: release can be marked successful when user-facing functionality is unavailable.
- Root cause hypothesis: CI contract only checks generic container status grep; no functional smoke step.
- Fix area: workflow + reusable smoke script
- Severity: P1

#### F-002: Mini-app parity drift is unresolved in live VPS default compose run
- Scope: config/runtime
- Observed state:
  - Local (profile-enabled) service set includes `mini-app-api` and `mini-app-frontend`.
  - VPS default compose service set excludes mini-app services; strict smoke (`REQUIRE_MINI_APP_ENDPOINT=true`) fails with `mini-app-frontend is not running`.
- Impact: parity is incomplete for mini-app surfaces; strict smoke (`REQUIRE_MINI_APP_ENDPOINT=true`) fails until VPS mini-app parity is fixed.
- Root cause hypothesis: missing/intentional profile activation divergence (`COMPOSE_PROFILES` unset) and pending local-gate reference freeze.
- Fix area: VPS env + compose profile alignment (depends on local-gate release-reference merge)
- Severity: P1

### P2

#### F-003: `scripts/deploy-vps.sh` post-deploy verification is container-presence-only
- Scope: runtime/operational
- Observed state:
  - Script ends with `docker ps ... | grep vps` snapshot and does not assert bot health, in-network reachability, or mini-app endpoint contract.
- Impact: manual deploys can report completion without proving functional readiness.
- Root cause hypothesis: historical script optimized for transport/restart flow, not release contract verification.
- Fix area: deploy script reuse of shared smoke contract
- Severity: P2

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

Not fully verified in this worker slice:
- Final canonical local reference contract from local-gate branch (dependency not merged here)
- Final VPS remediation for mini-app parity (current deploy gates run profile-aware mini-app smoke and strict mode still fails until F-002 is closed)
