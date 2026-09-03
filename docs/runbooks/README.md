# Operational Runbooks

Operational checks and investigations for the RAG Q&A chatbot. This is an index of the
operational assets that exist today; for the full runtime/Compose/ports/env reference see
[`../../DOCKER.md`](../../DOCKER.md).

## Service health & preflight

| Task | Command / asset |
|---|---|
| Are the sidecars healthy? | `scripts/check_services.sh` |
| Qdrant/Redis config preflight | `make test-preflight` |
| Smoke the live stack | `make test-smoke` |
| Prove the bot actually answers | `make bot-response-smoke` |
| Audit Qdrant payload indexes | `make qdrant-audit-indexes` (`scripts/qdrant_audit_indexes.py`) |

## Demo

| Task | Command / asset |
|---|---|
| Rehearse / present the five-minute demo | [`FIVE-MINUTE-DEMO.md`](FIVE-MINUTE-DEMO.md) (gate: `make demo-gate`) |
| Record rehearsal evidence | [`DEMO-REHEARSAL-LOG.md`](DEMO-REHEARSAL-LOG.md) |

## Production / VPS

| Task | Command / asset |
|---|---|
| Validate prod env vars | `scripts/validate_prod_env.sh` |
| Compose config validation | `docker compose -f compose.yml -f compose.dev.yml config` |
| Remove stale Compose source files | [`COMPOSE_SOURCE_CLEANUP.md`](COMPOSE_SOURCE_CLEANUP.md) |

> Production access (VPS, secrets, SSH, real CRM write paths) is out of scope for routine
> work — prefer local/test environments and redact secrets.

## Reference

- Runtime infra/config audit: [`../audits/runtime-infra-config-audit-2026-06.md`](../audits/runtime-infra-config-audit-2026-06.md)
- Compose services, profiles, ports, env: [`../../DOCKER.md`](../../DOCKER.md)
- Local setup & validation: [`../LOCAL-DEVELOPMENT.md`](../LOCAL-DEVELOPMENT.md)

> Working-tree hygiene (isolated git worktrees for non-trivial edits) and the swarm/PR
> orchestration process live in the Kiro skills (`roadmap-orchestrator`, `gh-pr-review`),
> not in this repo.
