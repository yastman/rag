# ADR #2846: Layering Violation Resolution

**Status:** Architecture Review  
**Owner:** Architecture Team  
**Related:** Epic #2846, #2855 (module tree collapse), #1948 (reverse-layering), #2045–#2049 (migration phases)

## Problem Statement

The stated repository layering is:

```
src/*           — reusable RAG library, no application coupling
telegram_bot/*  — bot application, consumer of src/*
mini_app/*      — Mini App backend, consumer of src/*
```

However, `src/` modules import from `telegram_bot/` in violation of this contract. This breaks:

1. **SDK reusability:** Code that imports `src.*` accidentally pulls in `telegram_bot` dependencies (Telegram library, bot-specific config, scoring logic).
2. **Deployment flexibility:** Mini App cannot use `src/` modules without a Telegram bot runtime in the same container.
3. **Test isolation:** Tests cannot mock bot dependencies when testing `src/` logic alone.

## Layering Violations Found

### Cross-Layer Imports

**Search command:** `grep -r "from telegram_bot" src/ --include="*.py"`

**Results:**

No direct `from telegram_bot` imports found in production code. However, the following modules are referenced in `src/runtime/__init__.py` as migration targets (indicating planned moves):

| Source Module | Dependency | Purpose | Status |
|---|---|---|---|
| (planned) `src/runtime/graph/` | `telegram_bot/graph/` | LangGraph compatibility facades | Not yet moved |
| (planned) `src/runtime/integrations/cache` | `telegram_bot/integrations/cache.py` | Semantic cache, embedding cache | Not yet moved |
| (planned) `src/runtime/services/qdrant` | `telegram_bot/services/qdrant.py` | Hybrid Qdrant client | Not yet moved |
| (planned) `src/runtime/observability/` | `telegram_bot/observability.py` | Trace observation decorators | Not yet moved |

### Root Cause

The violations listed above are **planned future moves** documented in `src/runtime/__init__.py`. The actual state is:

1. Core RAG modules (`src/core/`, `src/ingestion/`, `src/utils/`) have no telegram_bot imports ✓
2. Shared kernel modules currently live in `telegram_bot/` (graph facades, cache, services)
3. Integration points (`src/api/main.py`, `mini_app/`) import from `telegram_bot/` **by design** (awaiting #2045–#2049)

**Observation:** This is not a violation *yet*—it's a **temporary structural gap** during the migration from the "monolith-in-telegram_bot" to a "true SDK" architecture.

## Current State Evidence

- ✓ `src/ingestion/unified/` — no telegram_bot imports
- ✓ `src/core/` — uses `CoreDependencies` (defined in-tree), not telegram_bot
- ✓ `src/utils/` — no telegram_bot imports
- ✓ `src/runtime/` — placeholder directory, exposes *no* symbols yet (awaits slices #2045–#2049)
- ⚠ `tests/data/known_layering_violations.json` — empty (ratchet allowlist not yet populated)

## Proposed Resolution: Dependency Inversion

### Phase 1: Explicit Module Ownership (NOW)

Create a layering map document (`docs/architecture/STRUCTURE.md`) that lists **every module**, its owner layer, and what it is allowed to import.

**Example entries:**

```yaml
src/core/:
  owner: core
  allows_imports_from: [python, third_party]
  disallows_imports_from: [telegram_bot, mini_app, external_services]
  status: owned

src/runtime/:
  owner: architecture
  allows_imports_from: [src/core, src/utils, third_party]
  disallows_imports_from: [telegram_bot]
  status: placeholder_during_migration_2045_2049

telegram_bot/graph/:
  owner: bot
  allows_imports_from: [src/*, telegram_bot/*, third_party]
  disallows_imports_from: [mini_app]
  status: owned
  note: "Will migrate to src/runtime/graph/ in #2045"
```

### Phase 2: Tool Enforcement (AFTER #2045–#2049)

Once all modules are in their permanent homes, enforce via:

1. **import-linter** (Python tool):
   ```toml
   [tool:importlinter]
   
   [importlinter:checker:layering]
   layers =
       HIGH: src.core | src.utils
       MID:  src.runtime | src.ingestion
       BOT:  telegram_bot
       APP:  mini_app
   
   unallowed =
       src -> telegram_bot
       src -> mini_app
       mini_app -> telegram_bot
   ```

2. **Ruff rule** (linter integration):
   ```toml
   [tool.ruff.lint]
   blocked-modules = {
       "telegram_bot": ["src"],
       "mini_app": ["src", "telegram_bot"]
   }
   ```

3. **CI gate:**
   ```yaml
   - name: Check layering
     run: import-linter --fail-on-failure
   ```

### Phase 3: Future Multi-Package Separation

After verification:

```
monorepo/
  ├── codeindexer-core/        (current src/)
  ├── codeindexer-telegram-bot/ (current telegram_bot/)
  ├── codeindexer-mini-app/     (future)
  └── codeindexer-ingestion/    (future)
```

Each package has independent `src/`, `tests/`, `pyproject.toml`, versioning.

## Impact on #2855 (Module Tree Collapse)

Epic #2855 ("module tree collapse") proposes flattening the directory structure. This ADR is **orthogonal**:

- **Without this ADR:** Flatten anywhere, risk accidental cross-layer imports.
- **With this ADR:** Layering rules are explicit and enforced; flattening is a refactoring detail, not an architectural risk.

## Enforcement Actions

### During Migration (#2045–#2049)

**Temporary ratchet allowlist:**

```json
{
  "known_layering_violations": [
    {
      "from": "src.api.main",
      "to": "telegram_bot.graph",
      "reason": "awaiting_migration_2045",
      "expires": "2026-Q2"
    }
  ]
}
```

### After Migration

- Delete the ratchet file
- Enable import-linter in CI
- Add to PR template: "Check: `make check-layering`"

## Documentation Artifacts

| File | Purpose |
|------|---------|
| `docs/architecture/STRUCTURE.md` | Module ownership map and allowed imports |
| `.ruff.toml` section | Blocked module rules |
| `import-linter.toml` (future) | Layering checker config |
| `GITHUB_ACTIONS.md` → "Layering Check" | CI process |

## Done Criteria

- ✓ `docs/architecture/STRUCTURE.md` created with ownership map for all major modules
- ✓ Ratchet allowlist in `tests/data/known_layering_violations.json` documents all exceptions with expiry
- ✓ Ruff or import-linter integration documented; CI gate created (or marked as "awaiting tooling")
- ✓ Planning issues #2045–#2049 reference this ADR
- ✓ PR template reminder added: "Verify layering: `make check-layering`"

## Non-Goals

- Move modules now (that's #2045–#2049)
- Break existing imports during this ADR (enforcement is phase 2)
- Decide on monorepo-vs-multi-package now (#2855 handles structure choices)

## References

- `src/runtime/__init__.py` — migration plan and rationale
- `docs/designs/product-simplification-e2e-plan.md` — related refactor context
- Issue #2855 — module tree collapse
- Issues #2045–#2049 — migration implementation slices
