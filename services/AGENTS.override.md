# AGENTS.override.md

## Scope
- Applies to `services/**` (root for standalone microservice containers).
- Extends root `AGENTS.md` with cross-service constraints.

## Local Rules
- Each subservice (`bge-m3-api/`, `docling/`, `user-base/`, ...) owns its own Dockerfile and, where applicable, service-local dependency manifest.
- Do not share Python imports across subservices — communication must go through HTTP contracts.
- Keep healthcheck path and exposed port stable; downstream consumers in `compose.yml` and `src/retrieval/` depend on them.
- See per-subservice `AGENTS.override.md` for inner rules; this file covers `services/` as a whole.

## Required Validation
- After Dockerfile or compose changes: `make verify-compose-images`.
- Run subservice-scoped unit tests, e.g. `uv run pytest tests/unit/test_bge_m3_endpoints.py tests/unit/test_userbase_endpoints.py tests/unit/test_docling*.py -q`.
- Smoke (when stack running): `uv run pytest tests/smoke/test_zoo_smoke.py -q`.

## Guardrails
- Do not change service names, ports, or healthcheck routes without updating `compose.yml`, `compose.dev.yml`, and the root `services/README.md` table.
- Do not introduce shared mutable state between subservices.

## References
- `services/README.md`
- `DOCKER.md`
- `compose.yml`
- root `AGENTS.md`
