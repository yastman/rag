***REMOVED*** Review Fix Log — PR ***REMOVED***1457 Static Validation

***REMOVED******REMOVED*** Scope
- Fixed merge blocker in `tests/unit/test_docker_static_validation.py`.
- No production files changed.

***REMOVED******REMOVED*** Blocker
- Static validation tests still asserted legacy nginx temp paths under `/tmp/nginx/*`.
- Static validation tests still implied Dockerfile should pre-create `/tmp/nginx/*` temp dirs.

***REMOVED******REMOVED*** Changes
- Updated Dockerfile runtime contract assertion to forbid legacy `/tmp/nginx` pre-create pattern.
- Updated nginx temp path assertions to require direct `/tmp/client_temp` and `/tmp/proxy_temp`.

***REMOVED******REMOVED*** Verification
- `uv run pytest tests/unit/test_docker_static_validation.py -q` → `19 passed, 3 skipped`.
- `uv run pytest tests/unit/mini_app/test_frontend_runtime_contract.py tests/unit/test_docker_static_validation.py -q` → `24 passed, 3 skipped`.
- `git diff --check` → clean.

***REMOVED******REMOVED*** Notes
- Warnings about Python 3.14/langfuse are pre-existing and unrelated to this static contract fix.
