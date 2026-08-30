# Issue #3257 E2E Config Hermeticity Specification

## Outcome

Local pytest results do not depend on provider keys or ancestor dotenv files outside the test's
explicit environment.

## Contract

- Keep each `E2EConfig.validate()` call inside the same cleared environment used to construct the
  settings object.
- After the shared pytest bootstrap handles its one permitted dotenv load, set
  `PYTHON_DOTENV_DISABLED=1` so later zero-argument `load_dotenv()` calls cannot search upward.
- Preserve the bootstrap's existing opt-out and non-overriding behavior.
- Use only existing dependencies and never print credential values.

The exact current-checkout dotenv path remains owned by #3246.

## Acceptance

- The missing-key test passes both with a fabricated parent provider key and with no provider key.
- A downstream zero-argument `load_dotenv()` returns without invoking dotenv discovery.
- Focused E2E config and bootstrap regressions pass locally.
- `pyproject.toml` and `uv.lock` are unchanged.

## Rollback

Revert this issue's commit. No runtime or data migration is involved.
