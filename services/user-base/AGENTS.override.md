***REMOVED*** AGENTS.override.md

***REMOVED******REMOVED*** Scope
- Applies to `services/user-base/**`.
- Extends root `AGENTS.md` and `services/AGENTS.override.md` for the USER2-base Russian dense embedding service.

***REMOVED******REMOVED*** Local Rules
- Keep the `/health` and embedding endpoints stable; downstream vectorizer clients depend on the response shape.
- Respect schema/migration assumptions of any user store consumers — do not silently rename fields or change vector dim (768).
- Preserve optional ONNX backend toggle (`EMBEDDING_BACKEND=onnx`) and its fallback to the default backend.
- Keep the internal container port at `8000`; host mapping (`8003`) belongs to compose, not the service.

***REMOVED******REMOVED*** Required Validation
- Sync deps locally: `uv sync` (in `services/user-base/`).
- Unit tests: `uv run pytest tests/unit/test_userbase_endpoints.py -q`.
- Dockerfile checks: `uv run pytest tests/unit/test_userbase_dockerfile_permissions.py tests/unit/test_dockerfile_python_abi.py -q -k user-base`.

***REMOVED******REMOVED*** Guardrails
- Do not change the internal port, healthcheck path, or model identifier without updating `compose.yml` and the smoke suite.
- No persistent local state in this service — keep it stateless.

***REMOVED******REMOVED*** References
- `services/user-base/README.md`
- `services/AGENTS.override.md`
- root `AGENTS.md`
