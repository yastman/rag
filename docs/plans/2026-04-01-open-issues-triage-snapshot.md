# 2026-04-01 Open Issues Triage Snapshot

Retrieved: `2026-04-01` (UTC)

Source command:
`gh issue list --state open --limit 30 --json number,title,labels,assignees,updatedAt,url`

Reference spec:
`docs/superpowers/specs/2026-04-01-issue-triage-workflow-design.md`

This file is a dated working snapshot, not canonical backlog policy.
Lane labels record provisional triage on the retrieval date above, and `Needs discovery / defer` holds open issues that were intentionally left unclassified or deferred instead of force-fit into a lane.

## Execution updates

- [x] `#1075` `audit: remove unused imports in __init__.py files [priority:high]`
  implemented in `PR #1087`, merged into `dev` at `780f996af465b4506153036b06255185284b27f6`.
- [x] `#1076` `audit: deduplicate convert_to_python_types and create_search_engine [priority:high]`
  implemented in `PR #1127`, merged into `dev` and closed on `2026-04-01`.
- [x] `#1071` `fix: sync Docker and k8s image versions + complete k8s secrets template`
  completed by merged `dev` PRs `#1084` (`2026-04-01T12:39:34Z`) and `#1129`
  (`2026-04-01T15:51:44Z`); issue closed on `2026-04-02`.
- [x] `#1078` `audit: filter extractors — shared base class and constants [priority:medium]`
  implemented in `PR #1130`, merged into `dev` at `2026-04-02T14:17:32Z`.
- [x] `#1079` `audit: dead code removal`
  implemented in `PR #1131`, merged into `dev` at `2026-04-02T14:31:37Z`;
  issue closed on `2026-04-02`.
- [ ] `#1073` `chore: dependency updates — version audit April 2026`
  verified local changes were preserved in stash
  `autosave: issue-1073-deps-audit before branch cleanup`; issue reopened on
  `2026-04-02` pending reintegration.
- [x] `#1074` `audit: compose.vps.yml — broken overrides and missing BOT_USERNAME`
  implemented in local branch `issue-1074-compose-vps-audit`, verified with
  compose/runtime checks, and issue closed on `2026-04-02`.
- [x] `#1080` `langfuse не может подключиться к postgres, clickhouse, redis`
  implemented in local branch `issue-1080-fix`, verified with compose runtime
  checks, `make check`, and `make test-unit`; issue closed on `2026-04-02`.
- [ ] Next recommended task: `#1081` `postgres: 7 аварийных остановок, WAL corruption, autovacuum failures`
  Treat this as `Plan needed`; it remains `OPEN`.

## Quick execution

## Plan needed
- `#1073` `chore: dependency updates — version audit April 2026`
- `#1081` `postgres: 7 аварийных остановок, WAL corruption, autovacuum failures`
- `#1082` `clickhouse: IPv6 bind failures + lock contention до 200 сек`
- `#1083` `qdrant: telemetry reporting failed + invalid vector name queries`

## Design first
- `#1070` `refactor: split PropertyBot monolith (5000+ lines) into router modules + microservices`

## Needs discovery / defer

This is a holding bucket, not a fourth execution lane.

- `#1085` `File structure reorganization — cleanup and archival`
- `#1077` `audit: contextualization providers — extract shared base class [priority:high]`
- `#1072` `fix: eliminate bare  catches and scattered magic numbers`
- `#1003` `Langfuse local-to-VPS migration`
- `#988` `Residual VPS parity follow-ups`
- `#858` `fix: mypy silences 16 core modules with ignore_errors=true`
- `#852` `fix(docker): no network isolation — all services share default bridge`
- `#850` `fix(docker): postgres shared superuser — all DBs use same credentials`
- `#849` `fix(vps): hardcoded default passwords — minio, clickhouse, redis-langfuse`
- `#843` `fix(vps): service ports not exposed to host — no external monitoring possible`
- `#841` `fix(vps): disk bloat — 76% used, ~47GB reclaimable`
- `#11` `Dependency Dashboard`
