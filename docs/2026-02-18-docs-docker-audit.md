# Documentation And Docker Audit

Date: 2026-02-18

## Scope

Audit compared the following sources of truth:
- `Makefile`
- `docker-compose.dev.yml`
- `docker-compose.local.yml`
- `docker-compose.vps.yml`
- runtime modules under `telegram_bot/`, `src/api/`, `src/ingestion/unified/`, `src/voice/`

## Key Findings

1. Canonical docs contained stale architecture statements (legacy models/providers and old flow details).
2. Docker docs were partially outdated for compose profiles, required env vars, and service inventory.
3. Ingestion docs mixed deprecated and active paths, making operational flow unclear.
4. Local setup docs duplicated instructions and diverged over time.

## Actions Completed

Updated canonical docs to reflect current runtime:
- `README.md`
- `DOCKER.md`
- `docs/PROJECT_STACK.md`
- `docs/PIPELINE_OVERVIEW.md`
- `docs/LOCAL-DEVELOPMENT.md`
- `docs/QDRANT_STACK.md`
- `docs/INGESTION.md`
- `docs/ALERTING.md`
- `docs/LOCAL-DEV-SETUP.md` (reduced to WSL2 note + canonical links)

## Validation Checklist

- Commands referenced in updated docs are present in `Makefile`.
- Docker profile and service descriptions match compose files.
- Ingestion CLI commands match `src/ingestion/unified/cli.py --help`.
- Endpoint examples align with compose port mappings.

## Remaining Risks

- Historical docs in `docs/archive/` and dated reports remain intentionally unchanged and may describe older states.
- If compose service names/ports change later, canonical docs listed above must be updated in the same PR.
