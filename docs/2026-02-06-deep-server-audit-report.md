# Deep Server Audit Report (Host + Docker + Code + Plan)

Date: 2026-02-06
Project: `/opt/rag-fresh`
Host: `vmi2696211` (Ubuntu 24.04.3 LTS)
Auditor: Codex (GPT-5)

## Scope

- Host OS and operations: services, logs, firewall, SSH, updates, disk/memory, cron/timers.
- Docker runtime and compose security: running `vps-*` containers, isolation/hardening, storage pressure.
- Code and config review: ingestion, preflight, guardrails, Redis/Qdrant runtime parity.
- Plan verification: `docs/plans/2026-02-01-rag-2026-tz.md`.
- Official SDK cross-check via Context7:
  - `/qdrant/qdrant-client`
  - `/redis/redis-vl-python`
  - `/langfuse/langfuse-python`

## Executive Summary

- Total findings: 21
- Critical: 3
- High: 8
- Medium: 8
- Low: 2

Top risks are:

1. Ingestion reliability gap (`make ingest-gdrive` points to not-implemented path + non-persistent GDrive state).
2. Disaster recovery gap (no active automated backups for Qdrant/Postgres/Redis data).
3. Ops/security drift (fail2ban down, stale caddy log jail, pending security updates, previous log-loss event due disk pressure).

## Runtime Snapshot (2026-02-06)

- Host load and resources:
  - `uptime`: load around `7.80, 5.61, 4.25`
  - RAM: `11 GiB` total, swap in use (`~2.2 GiB`)
  - Disk `/`: `74G/96G` (78% used)
- Open host ports: `80`, `443`, `1654` (SSH), `3306` local-only.
- UFW: active, default deny incoming, only `80/443/1654` allowed.
- Docker: 10 containers running, all currently healthy.
- Qdrant runtime collections (from container network): only `gdrive_documents_bge`.

## Findings

| ID | Severity | Area | Evidence | Impact | Recommendation |
|---|---|---|---|---|---|
| C-01 | Critical | Ingestion CLI | `Makefile:661`, `Makefile:666`, `src/ingestion/service.py:211`, `telegram_bot/services/ingestion_cocoindex.py:93` | `make ingest-gdrive` points to path explicitly marked "not yet implemented". Operator runbook command is effectively broken. | Repoint target to working `src.ingestion.gdrive_flow` path, or implement CocoIndex GDrive ingestion before exposing command. |
| C-02 | Critical | GDrive watcher state | `src/ingestion/gdrive_flow.py:4`, `src/ingestion/gdrive_flow.py:118`, `src/ingestion/gdrive_flow.py:120`, `src/ingestion/gdrive_flow.py:252` | Code documents sqlite persistence but stores state only in memory (`self._processed`). On restart, deletion/change reconciliation is unreliable. | Implement persistent state (sqlite/postgres) and startup rehydration before calling deletion reconciliation. |
| C-03 | Critical | Backup / DR | `scripts/qdrant_backup.sh` exists, but no scheduler found in `/etc/cron*` or systemd; `/home/admin/backups` latest file is old test SQL dump | No verified automated data backups for live Qdrant/Postgres/Redis volumes; high data-loss risk on host/disk failure. | Add scheduled backups (Qdrant snapshots + pg_dump + Redis RDB/AOF policy), retention, and restore test. |
| H-01 | High | Host security control | `systemctl --failed` shows `fail2ban.service` failed; restart logs show `Failed during configuration: ... caddy-auth jail` and dangling `/var/log/caddy-access.log` | Brute-force ban automation is down. SSH still hardened, but defense-in-depth reduced. | Disable/remove stale `caddy-auth` jail or restore valid log path; ensure fail2ban service is green and persistent. |
| H-02 | High | Secrets handling | Runtime env of app containers includes API keys/tokens and static DB creds in compose (`docker-compose.vps.yml:22`) | Secrets are readable by privileged runtime inspection paths; higher blast radius if host/container access is obtained. | Move secrets to Docker secrets or external secret store; rotate keys; avoid static defaults (`postgres/postgres`). |
| H-03 | High | Patch debt | `apt-get -s upgrade`: 76 packages upgradable (incl. `systemd`, `apparmor`, `linux-firmware`, `mariadb`) | Increased exposure to known vulnerabilities and operational bugs. | Run staged patch window and reboot planning; track with change log and post-check health tests. |
| H-04 | High | Logging reliability | `journalctl` shows repeated `No space left on device` from `rsyslog`, including lost messages | Monitoring/audit trail was partially blind during incident period. | Enforce disk budget for containerd/docker cache, log retention caps, and alert on free-space threshold. |
| H-05 | High | Disk pressure source | `du`: `/var/lib/containerd ~55G`, `/var/lib/docker ~5.6G`; `docker system df -v` build cache `~17.69G` | Storage pressure can re-trigger service instability and log loss. | Add periodic cache cleanup policy and build-cache governance; pin maximum retained artifacts. |
| H-06 | High | Redis runtime drift | `docker exec vps-redis redis-cli CONFIG GET maxmemory-samples` => `5`; expected plan value is `10` | LFU/LRU eviction quality lower than planned under pressure. | Add `--maxmemory-samples 10` in `docker-compose.vps.yml` and validate in preflight. |
| H-07 | High | Privilege model | `sudo -l` => `NOPASSWD: ALL`; user in `docker` group | Full root-equivalent escalation path if user/session compromised. | Restrict sudoers to required commands; reduce docker-group exposure and use least privilege. |
| H-08 | High | Plan/runtime data drift | Plan marks collection milestones complete (`docs/plans/2026-02-01-rag-2026-tz.md:581`), runtime has only `gdrive_documents_bge` | "Complete" status in docs does not reflect current VPS runtime, increasing operational confusion. | Split dev/prod status explicitly and add runtime verification section per environment. |
| M-01 | Medium | DNS service | `unbound.service` failed: `can't bind socket ... ::1 port 53`; host has IPv6 disabled (`net.ipv6.conf.*.disable_ipv6=1`) | Local recursive DNS not running; possible resolution path confusion. | Align unbound bind config with IPv6-disabled host or disable unbound if not required. |
| M-02 | Medium | System timer drift | `update-caddy-logpath.timer` failed; script expects non-existent `ai-caddy` container | Stale automation, noisy failures, and indirect impact on fail2ban config integrity. | Remove stale timer/service or update to active ingress service topology. |
| M-03 | Medium | LLM gateway telemetry | `vps-litellm` logs include repeated name resolution failures to host `none` for OTEL traces | Error noise and broken telemetry pipeline; can mask real incidents. | Fix telemetry endpoint env or disable exporter explicitly. |
| M-04 | Medium | DB app errors | `vps-postgres` logs show missing relation and missing role `rag` | App migrations/config likely inconsistent across components. | Reconcile DB bootstrap and app role expectations; add startup migration check. |
| M-05 | Medium | Container hardening | Runtime inspect: `ReadonlyRootfs=false`, no explicit `no-new-privileges`, no `cap_drop`, no `pids_limit` for most services | Wider post-compromise attack surface inside containers. | Add hardening defaults in compose (`read_only`, `cap_drop: [ALL]`, `security_opt`, pids limits). |
| M-06 | Medium | Preflight portability | `make test-redis` expects `dev-redis`; `make test-bot-health` defaults to localhost endpoints and fails on VPS | Health checks produce false negatives/positives across environments. | Parameterize names/URLs (`REDIS_CONTAINER`, `QDRANT_URL`, `LLM_BASE_URL`) and include vps profile. |
| M-07 | Medium | Guardrails config drift | `telegram_bot/config.py:114` (`LOW_CONFIDENCE_THRESHOLD=0.3`) vs `telegram_bot/services/llm.py:17` (`LOW_CONFIDENCE_THRESHOLD=0.5`) and `telegram_bot/bot.py:130` constructor without threshold injection | Runtime behavior differs from configured operational policy. | Inject threshold from config into `LLMService`; remove hardcoded constant. |
| M-08 | Medium | ACORN status drift | Plan says SDK blocked (`docs/plans/2026-02-01-rag-2026-tz.md:599`, `:604`), runtime has `qdrant-client 1.16.2` + `AcornSearchParams=True` | Team may postpone already-available optimization due stale status. | Update plan wording and rerun benchmark decision using current SDK. |
| L-01 | Low | File hygiene | `.env` files in deployment tree have executable bit (`-rwxrwx---`) | Not a direct exploit by itself, but weak config hygiene and audit noise. | Normalize permissions to `640`/`600` for env files. |
| L-02 | Low | Legacy artifacts | Old/stale automation references (caddy symlink helper, historical paths) | Drift accumulates and increases incident MTTR. | Remove or archive obsolete infra scripts and document current runtime topology. |

## Plan Verification (`2026-02-01-rag-2026-tz.md`)

- Checkbox state in file:
  - Done: `77`
  - Todo: `124`
- Key mismatches:
  - Plan marks some milestones complete but VPS runtime differs (collection state, ACORN SDK status).
  - Initial critical bot checklist entries near top (`docs/plans/2026-02-01-rag-2026-tz.md:68`) remain unchecked.
  - Some completed marks are environment-specific and should be split by `dev`/`vps`.

## Context7 Cross-Check (Official SDK)

1. Qdrant client (`/qdrant/qdrant-client`)
- Official docs show filtered vector search and `SearchParams` usage.
- Runtime confirms current SDK supports ACORN model object.
- Sources:
  - https://github.com/qdrant/qdrant-client/blob/master/README.md
  - https://github.com/qdrant/qdrant-client/blob/master/docs/source/index.rst

2. RedisVL (`/redis/redis-vl-python`)
- Official examples initialize `SemanticCache`/`EmbeddingsCache` with `redis_url`, optional TTL.
- Confirms cache behavior and constructor patterns used for validation.
- Sources:
  - https://github.com/redis/redis-vl-python/blob/main/docs/user_guide/03_llmcache.ipynb
  - https://github.com/redis/redis-vl-python/blob/main/docs/user_guide/10_embeddings_cache.ipynb
  - https://github.com/redis/redis-vl-python/blob/main/README.md

3. Langfuse Python (`/langfuse/langfuse-python`)
- Official initialization requires public/secret keys (or env vars).
- Missing/invalid keys can degrade to disabled/no-op behavior, consistent with observed bot warning.
- Sources:
  - https://context7.com/langfuse/langfuse-python/llms.txt
  - https://github.com/langfuse/langfuse-python/blob/main/langfuse/api/README.md

## Priority Remediation Plan

### 0-24h

1. Fix fail2ban startup by removing stale `caddy-auth` dependency and validating active jails.
2. Fix `ingest-gdrive` command path and publish one canonical ingestion entrypoint.
3. Add immediate disk pressure relief (`builder cache prune`) and free-space alerting.
4. Rotate exposed API keys and move secrets out of plain runtime env where feasible.

### 1-7 days

1. Implement persistent GDrive processed-state backend and deletion reconciliation safety.
2. Deploy automated backups + restore drill for Qdrant/Postgres/Redis.
3. Patch host packages and reboot with post-maintenance checks.
4. Parameterize preflight scripts for both `dev-*` and `vps-*` profiles.

### 1-4 weeks

1. Container hardening baseline (`read_only`, `cap_drop`, `no-new-privileges`, pids limits).
2. Clean up stale services/timers and deprecated infra scripts.
3. Split plan status by environment and enforce runtime verification gates before marking "complete".
