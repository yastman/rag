# Issue #3258 E2E Config Secret Representation Specification

## Outcome

Rendering `E2EConfig` for diagnostics or assertion failures never includes credential values.

## Contract

- Exclude `telegram_api_hash`, `judge_api_key`, and `anthropic_api_key` from Pydantic
  representations with native field metadata.
- Keep non-secret identifiers and routing diagnostics visible.
- Prove redaction with fabricated sentinel values only.
- Do not change validation, provider routing, dependencies, or credential storage.

No other current `E2EConfig` field stores credential material: Telegram API ID and usernames are
identifiers; session, collection, report, and voice fields are names or paths.

## Acceptance

- No fabricated secret sentinel appears in `repr(config)` or assertion-style output.
- Non-secret diagnostic fields remain visible.
- Existing E2E configuration tests pass.
- `pyproject.toml` and `uv.lock` are unchanged.

## Rollback

Revert this issue's commit. No runtime, secret, or data migration is involved.
