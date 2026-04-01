# 2026-04-01 Open Issues Triage Snapshot

Retrieved: `2026-04-01` (UTC)

Source command:
`gh issue list --state open --limit 30 --json number,title,labels,assignees,updatedAt,url`

Reference spec:
`docs/superpowers/specs/2026-04-01-issue-triage-workflow-design.md`

This file is a dated working snapshot, not canonical backlog policy.
Lane labels record provisional triage on the retrieval date above, and `Needs discovery / defer` holds open issues that were intentionally left unclassified or deferred instead of force-fit into a lane.

## Quick execution
- `#1075` `audit: remove unused imports in __init__.py files [priority:high]`
- `#1076` `audit: deduplicate convert_to_python_types and create_search_engine [priority:high]`
- `#1078` `audit: filter extractors — shared base class and constants [priority:medium]`
- `#1079` `audit: dead code removal`

## Plan needed
- `#1071` `fix: sync Docker and k8s image versions + complete k8s secrets template`
- `#1073` `chore: dependency updates — version audit April 2026`
- `#1074` `audit: compose.vps.yml — broken overrides and missing BOT_USERNAME`
- `#1080` `langfuse не может подключиться к postgres, clickhouse, redis`
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
