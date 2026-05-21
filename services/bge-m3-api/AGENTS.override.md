***REMOVED*** AGENTS.override.md

***REMOVED******REMOVED*** Scope
- Applies to `services/bge-m3-api/**`.
- Extends root `AGENTS.md` and `services/AGENTS.override.md` for the BGE-M3 dense + sparse + ColBERT embedding API.

***REMOVED******REMOVED*** Local Rules
- Preserve the `/health`, `/encode`, and `/rerank` endpoint contracts and Prometheus metric names.
- Keep model loading, warmup, and inference lifecycle in `app.py`; configuration in `config.py`.
- Pin model weights and runtime deps via `pyproject.toml` / `requirements.txt` / `uv.lock` — do not drift between them.

***REMOVED******REMOVED*** Required Validation
- Sync deps locally: `uv sync` (in `services/bge-m3-api/`).
- Unit tests: `uv run pytest tests/unit/test_bge_m3_endpoints.py tests/unit/test_bge_m3_rerank.py -q`.
- Dockerfile static checks: `uv run pytest tests/unit/test_docker_static_validation.py -q -k bge-m3`.

***REMOVED******REMOVED*** Guardrails
- Do not change service port (`8000`), healthcheck path, or metric shapes without updating `compose.yml` and `src/retrieval/` consumers.
- Do not embed secrets or model paths assuming a single host layout.

***REMOVED******REMOVED*** References
- `services/bge-m3-api/README.md`
- `docs/QDRANT_STACK.md`
- `services/AGENTS.override.md`
- root `AGENTS.md`
