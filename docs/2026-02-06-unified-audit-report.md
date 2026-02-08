# Unified Audit Report (Server + Docker + Code)

Date: 2026-02-06
Project: `/opt/rag-fresh`
Host: `vmi2696211` (Ubuntu 24.04.3 LTS)

## Scope

- Host audit: security, services, updates, disk/memory, timers/cron, logs.
- Docker audit: runtime, resources, hardening, image size/cache, container logs.
- Code/config audit: ingestion pipeline, Makefile commands, guardrails/config drift, preflight checks.
- Plan verification: `docs/plans/2026-02-01-rag-2026-tz.md`.
- SDK verification via Context7 (`qdrant-client`, `redisvl`, `langfuse-python`).

## Executive Summary

- This file is the **single consolidated report** of all findings.
- Main risk areas:
  1. Ingestion reliability and correctness.
  2. Operations resilience (backup/restore, patching, disk pressure).
  3. Docker hardening and resource governance.
  4. Config/plan drift versus actual runtime state.

## Consolidated Findings

| ID | Severity | Domain | Evidence | Impact | Recommendation |
|---|---|---|---|---|---|
| U-01 | Critical | Ingestion CLI | `Makefile:661`, `Makefile:666`, `src/ingestion/service.py:211` | `make ingest-gdrive` points to not-implemented path. | Repoint to working `src.ingestion.gdrive_flow` or implement CocoIndex GDrive path. |
| U-02 | Critical | Ingestion state | `src/ingestion/gdrive_flow.py:118`, `src/ingestion/gdrive_flow.py:120`, `src/ingestion/gdrive_flow.py:252` | Claimed persistent state is in-memory only; restart breaks reconciliation behavior. | Implement sqlite/postgres persistent state and startup state load. |
| U-03 | Critical | DR/Backups | Backup scripts exist, but no active scheduler and no fresh validated backups detected. | High data-loss risk on host/volume failure. | Add automated backups (Qdrant/Postgres/Redis) + retention + restore drills. |
| U-04 | High | Host security control | `fail2ban.service` failed; stale caddy log jail path. | SSH brute-force automation degraded. | Fix/remove stale `caddy-auth` jail and restore fail2ban health. |
| U-05 | High | Secrets management | Runtime env exposes API keys; static DB creds in `docker-compose.vps.yml:22`. | Credential exposure risk via runtime inspection/host compromise. | Move to secrets workflow and rotate active keys. |
| U-06 | High | Patch debt | `apt-get -s upgrade` shows 76 upgradable packages. | Elevated vulnerability/instability exposure. | Run planned patch window + reboot + post-checks. |
| U-07 | High | Logging reliability | Historical `No space left on device` caused rsyslog message loss. | Monitoring/audit blind spots under disk pressure. | Add disk SLO alerts and cache/log budget enforcement. |
| U-08 | High | Disk pressure | `/var/lib/containerd` ~55G, build cache ~25.8G, large images. | Higher chance of ENOSPC and cascading failures. | Add scheduled pruning and image/cache lifecycle policy. |
| U-09 | High | Redis parity drift | Runtime `maxmemory-samples=5` (plan expects 10). | Weaker LFU eviction quality under pressure. | Set `--maxmemory-samples 10` and verify in preflight. |
| U-10 | High | Privilege model | `admin` has `NOPASSWD: ALL`, also in `docker` group. | Root-equivalent escalation path if user/session compromised. | Restrict sudoers and review docker-group usage. |
| U-11 | High | Plan/runtime drift | Plan marks milestones complete, runtime differs (collection/state). | False confidence in completion status. | Track completion per environment (`dev` vs `vps`) with runtime proofs. |
| U-12 | High | Resource policy | Sum container memory limits exceeds host RAM; CPU limits absent. | Load spikes can destabilize host despite per-container limits. | Rebalance memory budget and define CPU quotas. |
| U-13 | High | Docker hardening | No `cap_drop`, no `no-new-privileges`, no `pids_limit`, `ReadonlyRootfs=false`. | Larger attack surface/containment weakness. | Add hardening baseline in compose. |
| U-14 | High | Root containers | `vps-litellm` runs as root; `vps-qdrant` as `0:0`. | Increased blast radius on compromise. | Run non-root where possible; tighten service controls otherwise. |
| U-15 | High | Ingestion reliability | `vps-ingestion` logs: frequent timeouts/upsert/mutation errors. | Indexing failures and retries reduce throughput/correctness. | Add retry/backoff, tune batch/timeout, track DLQ/error-rate SLO. |
| U-16 | Medium | DNS service | `unbound` fails to bind `::1` while IPv6 disabled. | Resolver service remains failed and noisy. | Align unbound config with IPv6 policy or disable if unused. |
| U-17 | Medium | Stale timer/service | `update-caddy-logpath.timer` failed; script targets non-existing `ai-caddy`. | Operational drift, unnecessary failure noise. | Remove/update stale unit and associated script. |
| U-18 | Medium | LiteLLM telemetry | OTEL export tries host `none`; repeated name-resolution errors. | Error-noise, telemetry path broken. | Fix `LANGFUSE_OTEL_HOST` or disable callback until valid. |
| U-19 | Medium | DB app drift | Postgres logs: missing relation and role errors. | Inconsistent app bootstrap/migrations. | Align migration/init process and DB role expectations. |
| U-20 | Medium | Preflight portability | `make test-redis` expects `dev-redis`; `test-bot-health` defaults localhost. | Checks fail/misreport in VPS profile. | Parameterize container names and endpoints for env profiles. |
| U-21 | Medium | Guardrails drift | `telegram_bot/config.py:114` (0.3) vs `telegram_bot/services/llm.py:17` (0.5). | Runtime behavior differs from configured threshold. | Inject threshold into `LLMService`, remove hardcoded constant. |
| U-22 | Medium | ACORN docs drift | Plan says SDK blocked, runtime has `qdrant-client 1.16.2` + `AcornSearchParams`. | Optimization may be postponed unnecessarily. | Update plan status and rerun benchmark decision. |
| U-23 | Medium | Ingestion log volume | `src/ingestion/unified/targets/qdrant_hybrid_target.py` has per-item INFO spam. | High log noise and I/O overhead. | Move per-item logs to DEBUG; keep summaries at INFO. |
| U-24 | Medium | Prod immutability | `docker-compose.vps.yml:285-286` bind-mounts code into ingestion container. | Runtime depends on host source tree. | Remove code bind mounts in VPS production profile. |
| U-25 | Medium | Image footprint | Heavy images (`litellm`, `ingestion`, `docling`, embeddings services). | Slower deploys and storage growth. | Continue dependency trimming and unified image strategy. |
| U-26 | Medium | Init process | All containers `HostConfig.Init=false`. | Possible zombie process handling issues. | Enable `init: true` for long-running Python services. |
| U-27 | Medium | Local compose drift | `docker-compose.local.yml` keeps `allkeys-lfu` policy. | Behavior mismatch between environments. | Align local and VPS Redis policy/parameters. |
| U-28 | Medium | Config contract drift | `src/config/settings.py` lacks expected `retrieval_profile` contract from plan docs. | Documentation and actual config diverge. | Implement or update docs to current reality. |
| U-29 | Low | File hygiene | Some env files have executable bit set. | Hygiene issue and audit noise. | Normalize permissions to `600/640`. |
| U-30 | Low | Legacy artifacts | Stale scripts/services and old paths remain. | Raises MTTR during incidents. | Archive/remove obsolete automation and document current topology. |

## Plan Verification Snapshot

- Checked file: `docs/plans/2026-02-01-rag-2026-tz.md`
- Checklist counters (current):
  - Done: `77`
  - Todo: `124`
- Key mismatch examples:
  - ACORN milestone status text is stale versus installed SDK capability.
  - "Completed" collection/data assumptions do not fully match current VPS runtime state.

## Context7 Verification Notes

1. Qdrant client (`/qdrant/qdrant-client`)
- Official docs confirm filtered/vector search patterns and search params usage.
- Runtime confirms `AcornSearchParams` availability in installed SDK.

2. RedisVL (`/redis/redis-vl-python`)
- Official examples use `redis_url` initialization for SemanticCache/EmbeddingsCache and TTL settings.

3. Langfuse Python (`/langfuse/langfuse-python`)
- Official initialization requires public/secret key (or env vars), matching observed disabled/no-op behavior when missing.

## Prioritized Remediation

### 0-24h

1. Fix `ingest-gdrive` command path and ingestion state persistence gap (U-01/U-02).
2. Restore fail2ban health and remove stale caddy dependency (U-04/U-17).
3. Address storage pressure (cache pruning policy + alerting) (U-07/U-08).
4. Correct LiteLLM telemetry misconfiguration (U-18).

### 1-7 days

1. Implement automated backups and restore drill (U-03).
2. Apply patching cycle for host updates (U-06).
3. Parameterize preflight checks by environment profile (U-20).
4. Apply Docker hardening baseline and resource rebalancing (U-12/U-13/U-14).

### 1-4 weeks

1. Reduce image footprints and stabilize build cache budget (U-25).
2. Remove production code bind mounts and enforce immutable deployment flow (U-24).
3. Resolve remaining config/plan drift (`retrieval_profile`, ACORN status, Redis parity) (U-22/U-27/U-28).

## Related Detailed Reports

- `docs/2026-02-06-full-audit-report.md`
- `docs/2026-02-06-deep-server-audit-report.md`
- `docs/2026-02-06-docker-deep-audit.md`
