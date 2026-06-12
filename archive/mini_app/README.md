# Archived Mini App

This directory preserves the former Telegram Mini App backend and React/Vite
frontend for reference only. The Mini App is no longer part of the required
runtime, Compose stack, CI lint path, dependency extras, or local validation
lanes.

## Current status

- **Archived path**: `archive/mini_app/`
- **Former backend service**: `mini-app-api`
- **Former frontend service**: `mini-app-frontend`
- **Required runtime**: none; do not start these services as part of the core
  RAG assistant path.
- **Required tests**: none; the historical Mini App test lanes were removed
  with the archive.

The top-level `mini_app/` directory is now a documentation-only shim that points
here for legacy path compatibility. Do not add runtime code, tests, Docker
services, or required-path assets back under that shim.

## Preserved contents

- [`api.py`](api.py) — historical FastAPI backend entrypoint.
- [`auth.py`](auth.py), [`phone.py`](phone.py), and [`expert_start.py`](expert_start.py)
  — historical backend support modules.
- [`Dockerfile`](Dockerfile) — historical backend container recipe.
- [`frontend/`](frontend/) — historical React/Vite frontend and nginx image.

## If this surface is unarchived

Open a fresh product decision before reintroducing any of the following into the
required path:

1. Compose services (`mini-app-api`, `mini-app-frontend`) or exposed ports.
2. CI/Makefile lint, typecheck, frontend, smoke, or contract lanes.
3. Optional dependency extras for Mini App runtime packages.
4. Browser tracing, remote frontend logging, or observability requirements.
5. Telegram bot integration that depends on Mini App runtime availability.

Any unarchive should restore current tests and contracts intentionally instead
of relying on the deleted required-lane tests from the pre-archive state.

## See also

- [`../../DOCKER.md`](../../DOCKER.md) — current Compose/runtime contract.
- [`../../docs/LOCAL-DEVELOPMENT.md`](../../docs/LOCAL-DEVELOPMENT.md) — current local validation ladder.
- [`../../docs/indexes/runtime-services.md`](../../docs/indexes/runtime-services.md) — service ownership index.
- [`../../docs/observability/MINIAPP_BROWSER_TRACING_DECISION.md`](../../docs/observability/MINIAPP_BROWSER_TRACING_DECISION.md) — archived browser tracing decision.
