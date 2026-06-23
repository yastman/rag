# `src/runtime` — shared runtime kernel scaffold

Migration target for [#1948](https://github.com/yastman/rag/issues/1948)
("reverse layering: `src/api` and `mini_app` import from `telegram_bot`")
and the parallel decomposition slice in
[#1265](https://github.com/yastman/rag/issues/1265).

## Why this directory exists

`src/api/main.py` currently imports from `telegram_bot.graph.*`,
`telegram_bot.integrations.cache`, `telegram_bot.services.qdrant`, and
`telegram_bot.scoring`. The current violation list lives in
[`tests/data/known_layering_violations.json`](../../tests/data/known_layering_violations.json)
and is locked by
[`tests/contract/test_layering_no_telegram_bot_imports_contract.py`](../../tests/contract/test_layering_no_telegram_bot_imports_contract.py).

The plan in #1948 is to relocate the truly shared kernel modules to
`src/runtime/` so `src/api`, `mini_app`, and `telegram_bot` all import
from a single home, and the dependency arrows finally point in the
direction the README/`pyproject` advertise.

## Migration plan (one PR per row)

| Phase | Issue | Modules to move | Drops from allowlist |
|---|---|---|---|
| Phase 1 — pure | [#2045](https://github.com/yastman/rag/issues/2045) | `phone_utils`, `scoring`, `observability`, `content_loader`, `kommo_client` (no graph/cache/qdrant deps) | partial: `telegram_bot.scoring` and any other pure-module entries |
| Phase 3 — coupled | [#2047](https://github.com/yastman/rag/issues/2047) | `graph/`, `integrations/cache.py`, `services/qdrant.py` | `telegram_bot.graph.*`, `telegram_bot.integrations.cache`, `telegram_bot.services.qdrant` |
| Cleanup | [#2049](https://github.com/yastman/rag/issues/2049) | nothing — drop the allowlist file | the JSON itself |

Phase 2 is the parallel `telegram_bot/bot.py` decomposition slice
([#2046](https://github.com/yastman/rag/issues/2046),
[#2048](https://github.com/yastman/rag/issues/2048) — #1265).

## Per-slice procedure

For each module relocated into `src/runtime/`:

1. `git mv telegram_bot/<path>.py src/runtime/<path>.py`.
2. Update internal `telegram_bot/` callers to
   `from src.runtime.<path> import ...`.
3. Add a thin compat shim back at the original path that re-exports
   from `src.runtime` (preserves any external dependents while we
   migrate Docker images and k8s manifests). The shim should be
   marked `# Deprecated: re-export shim, drop after #2049.`
4. Update `src/api/main.py` and any `mini_app/` callers to import
   from `src.runtime.<path>`.
5. Remove the corresponding entry from
   `tests/data/known_layering_violations.json`. The contract test
   refuses to leave stale entries, so a missed step here fails CI.
6. Run the existing contract suite + any tests that touch the moved
   surface.

## What this scaffold PR does NOT do

- It does **not** move any module — that is the work of #2045/#2047.
- It does **not** change runtime behaviour. Importing
  `src.runtime` succeeds and yields an empty namespace until the first
  migration slice lands.
- It does **not** modify the existing ratchet contract or the
  allowlist JSON — both already enforce "no new violations" on `dev`.

## Verification

The ratchet contract has been on `dev` since 2026-05-22 (PR landing
the migration scaffolding for #1948). Running it against this scaffold
shows zero changes:

```bash
uv run pytest tests/contract/test_layering_no_telegram_bot_imports_contract.py -q
```
