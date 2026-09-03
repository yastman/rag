# telegram_bot/preflight/

Startup dependency preflight for the bot: probes external dependencies (Redis, Qdrant,
Postgres, BGE-M3) and classifies each as **CRITICAL** or **OPTIONAL** so the bot can decide
whether it may start.

## Files

| File | Purpose |
|------|---------|
| [`checks.py`](./checks.py) | Dependency checks with CRITICAL/OPTIONAL classification; builds a `StartupReport` of `DependencyCheckResult`s (with retry on critical deps) |
| [`remediation.py`](./remediation.py) | Human-readable remediation hints + deeper Redis/cache verification (`_check_redis_deep`, `_verify_cache_synthetic`) and the Qdrant readiness-contract validation (`_qdrant_validate_collection`, `_qdrant_validate_product_collections`) |
| [`__init__.py`](./__init__.py) | Backward-compat re-export surface (checks + remediation) |

## Boundaries

- Preflight only **reads** dependency health; it does not mutate collections or schemas.
  A missing/empty collection is an actionable failure — create and populate both product
  collections with `make demo-bootstrap` (#3202; contracts in
  `src/runtime/qdrant/readiness.py`).
- Both product collections are enforced before polling (#3202): the configured knowledge
  collection and the hard-coded `apartments` collection must each satisfy their readiness
  contract (vector names + dimensions, payload indexes, point count).
- Severity taxonomy comes from `telegram_bot/startup_status.py`
  (`StartupSeverity`, `StartupReport`, `StartupSignal`).

## See Also

- [`../lifecycle/README.md`](../lifecycle/README.md) — startup path that runs these checks
- [`../../docs/runbooks/README.md`](../../docs/runbooks/README.md) — operational preflight commands
