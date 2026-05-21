***REMOVED*** AGENTS.override.md

***REMOVED******REMOVED*** Scope
- Applies to `scripts/**`.
- Extends root `AGENTS.md` with rules for operational and one-shot scripts.

***REMOVED******REMOVED*** Local Rules
- Shell scripts must start with `***REMOVED***!/usr/bin/env bash` and `set -euo pipefail`.
- Keep scripts idempotent — reruns must converge, not duplicate side effects.
- Prefer Python entrypoints under `scripts/` for anything that benefits from typing or testing.
- Do not import from `telegram_bot/` or `mini_app/` runtime modules; scripts are out-of-process tools.

***REMOVED******REMOVED*** Required Validation
- Lint shell scripts: `bash -n scripts/<file>.sh` and `shellcheck scripts/<file>.sh` where applicable.
- Lint Python entrypoints: `make check`.
- For scripts touching CI/maintenance flows, also run targeted unit tests (e.g. `tests/unit/test_check_*`).

***REMOVED******REMOVED*** Guardrails
- No destructive cluster/db operations without an explicit `--yes` / dry-run flag.
- Do not hardcode credentials or environment-specific paths; read from env or args.

***REMOVED******REMOVED*** References
- `docs/engineering/repo-hygiene-runbook.md`
- `docs/LOCAL-DEVELOPMENT.md`
- `scripts/README.md`
