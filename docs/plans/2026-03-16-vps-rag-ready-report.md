# VPS RAG-Ready Rehearsal Report

## Baseline

- Date: 2026-03-16
- Branch: `vps`
- Plan: `docs/plans/2026-03-16-vps-rag-ready-implementation-plan.md`
- Local validation before rehearsal:
  - `make check` -> passed
  - `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit` -> passed (`5329 passed, 20 skipped`)
  - targeted tests (`test_vps_runtime_inventory`, `test_vps_rag_preflight`, `test_docs_runtime_references`, `test_deploy_vps_script`) -> `7 passed`

## Inventory

- Status: completed
- Command: `uv run python scripts/vps_runtime_inventory.py --host vps --project-dir /opt/rag-fresh`
- Result:
  - `compose_file`: `compose.yml:compose.vps.yml`
  - container names are in Compose underscore format (for example `vps_postgres_1`, `vps_qdrant_1`, `vps_litellm_1`)
  - no running `bot` container found in inventory output
  - many listed containers are `Up ... (unhealthy)`

## Preflight

- Status: failed
- Command: `make vps-rag-preflight`
- Exit: non-zero
- Result: `Missing/unhealthy core services: vps-postgres, vps-redis, vps-qdrant, vps-bge-m3, vps-litellm, vps-bot`

## Telegram Smoke

- Status: blocked
- Test question: `Какие документы нужны иностранцу для покупки квартиры в Болгарии?`
- Bot answered: not executed
- Retrieval/generation errors: not executed
- Note: manual smoke not started because preflight failed and `vps-bot` was not present in runtime inventory.

## Restart/Recreate Smoke

- Status: failed
- Command: `make deploy-vps-verify`
- Exit: non-zero
- Result: deploy stopped during rsync with VPS disk-space error:
  - `No space left on device (28)`
  - `rsync error: error in file IO (code 11)`

## Final Decision

- `not ready`

## Blockers

- VPS runtime does not satisfy preflight requirements (`vps-*` core services and healthy status).
- `vps-bot` container not found in inventory output, so Telegram KB smoke could not be executed.
- `make deploy-vps-verify` failed due VPS filesystem capacity (`No space left on device`), so restart/recreate rehearsal is incomplete.
