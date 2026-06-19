# ADR #2855: Collapsing Parallel Module Trees

**Status:** Proposed
**Owner:** Architecture Team
**Related:** Epic #2846 (layering), #1948 (phone_utils shim), #2045–#2049 (migration phases)

## Problem Statement

The repository contains 14 same-named Python modules distributed across `src/` and `telegram_bot/`:

| Category | Count | Pattern |
|----------|-------|---------|
| **Shim re-exports** | 5 | `telegram_bot/` re-exports from `src/` for backward compatibility |
| **Duplicate logic** | 5 | Same implementation in both locations, one canonical |
| **Diverged implementations** | 4 | Different logic, unclear ownership or layering intent |

This parallel structure increases maintenance burden, obscures the canonical implementation, and violates the stated layering contract:

```
src/*           — reusable RAG library (no telegram_bot imports)
telegram_bot/*  — bot-specific application layer
```

## Inventory of Parallel Modules

### Shim Re-Exports (Canonical in src/)

These `telegram_bot/` modules are thin re-export shims for backward compatibility (#1948 layering).

| Path | Type | Status | Action |
|------|------|--------|--------|
| `src/phone_utils.py` → `telegram_bot/phone_utils.py` | Shim | **Move canonical, deprecate shim** | Migrate callers to `src/phone_utils`, keep `telegram_bot/` shim for 1 release |
| `src/services/bge_m3_client.py` → `telegram_bot/services/bge_m3_client.py` | Shim | **Move canonical, deprecate shim** | Migrate callers, keep shim |
| `src/services/bge_m3_query_bundle.py` → `telegram_bot/services/bge_m3_query_bundle.py` | Shim | **Move canonical, deprecate shim** | Migrate callers, keep shim |
| `src/services/content_loader.py` → `telegram_bot/services/content_loader.py` | Shim | **Move canonical, deprecate shim** | Migrate callers, keep shim |
| `src/services/handoff_state.py` → `telegram_bot/services/handoff_state.py` | Shim | **Move canonical, deprecate shim** | Migrate callers, keep shim |

**Action:** Already canonical in `src/`; shims exist for backward compatibility. Remove shims after deprecation period or migrate remaining internal bot callers directly to `src/` imports.

---

### Duplicate Logic (Canonical in src/)

These modules have substantively equivalent implementations in both locations. The `src/` version is the canonical library export.

| Path | src/ lines | tg/ lines | Status | Action |
|------|-----------|----------|--------|--------|
| `__init__.py` | 49 | 1 | **tg/ is minimal (just docstring)** | Remove `telegram_bot/__init__.py` stub; bot imports flow through `src` |
| `services/_retry.py` | 69 | 19 | **Re-export shim** (tg re-exports from src/) | Remove tg copy — callers already import from src/ |
| `services/vectorizers.py` | 76 | 17 | **Re-export shim** (tg re-exports from src/) | Remove tg copy — callers already use src/ path |
| `models/__init__.py` | 6 | 1 | **tg/ is minimal** | Remove stub; import from `src.models` |
| `evaluation/__init__.py` (docstring-only, no logic) | 1 | 5 | **tg/ is actual code** | Move `telegram_bot/evaluation/__init__.py` content to `src/evaluation/` |

**Action:** For each, migrate internal callers from `telegram_bot/` to `src/`, then remove the duplicate.

---

### Diverged Implementations (Needs Investigation)

These modules exist in both locations with **different implementations**, indicating unclear ownership or unfinished migration.

| Path | src/ lines | tg/ lines | Divergence | Action |
|------|-----------|----------|-----------|--------|
| `observability_bootstrap.py` | 3 | 9 | **Shim chain** (tg → src.observability_bootstrap → src.observability.bootstrap, no divergence) | Remove intermediate shim |
| `observability_payloads.py` | 3 | 9 | **Shim chain** (tg → src.observability_payloads → src.observability.safe_payloads, no divergence) | Remove intermediate shim |
| `scoring.py` | 23 | 29 | **Shim chain** (both re-export src.observability.scores, no divergence) | Remove intermediate shims |
| `services/__init__.py` | 33 | 61 | Different exports and initialization | **Investigate intent:** Bot layer may expose bot-specific services; clarify boundary |

**Action:** Audit each for intent, then converge.

---

## Current State Evidence

### File Sizes and Duplication

Total bytes in parallel modules: ~2.1 KB (small absolute size, but high conceptual debt).

- **Shims** (clearly re-export): `phone_utils.py`, all `services/*.py` except `_retry.py` and `vectorizers.py`
- **Duplicates** (substantively same): `__init__.py`, `models/__init__.py`, `evaluation/__init__.py` (docstring-only, no logic), `services/_retry.py` (shim), `services/vectorizers.py` (shim)
- **Shim chains** (no divergence): `observability_bootstrap.py`, `observability_payloads.py`, `scoring.py`
- **Diverged** (genuine): `services/__init__.py`

### Layering Contract Status

From ADR #2846:

- ✓ `src/ingestion/`, `src/core/`, `src/utils/` have no `telegram_bot` imports
- ⚠ `src/` exports and `telegram_bot/` re-exports create ambiguity about which is canonical
- ⚠ Diverged modules (`observability_*`, `scoring.py`) lack clear ownership documentation

---

## Proposed Migration Strategy

### Phase 1: Audit & Document (1 day)

1. **Clarify ownership for diverged modules:**
   - `observability_bootstrap.py`, `observability_payloads.py`: Are these bot-specific or library-wide? If both, merge with feature flags.
   - `scoring.py`: Bot-specific domain logic or reusable? If domain-specific, move to `telegram_bot/` and document as such.
   - `services/__init__.py`: Clarify export surface for each layer.

2. **Document the decision** in each module docstring: canonical home and why.

### Phase 2: Collapse Shims (1–2 days)

For each of the 5 clear shim re-exports:

1. Grep all internal `telegram_bot/` callers → update to import from `src/`
2. Add deprecation warning to `telegram_bot/` shim (if not removed immediately)
3. Remove shim or mark as `# Deprecated in v2.x, remove in v2.x+1`
4. Test: `make test-core test`

**Winning namespace:** `src/` (library layer)

### Phase 3: Collapse Duplicates (1–2 days)

For each of the 5 substantive duplicates:

1. Identify all callers of the `telegram_bot/` version
2. Migrate to `src/` version
3. Delete `telegram_bot/` duplicate
4. Test: `make test-core test`

**Winning namespace:** `src/` (library layer)

### Phase 4: Converge Diverged Modules (2–3 days)

For each diverged module:

1. **Define the boundary:** Is this bot-specific or shared?
   - If **shared**: Merge to `src/`, use feature flags if bot-specific logic needed
   - If **bot-specific**: Move to `telegram_bot/`, document ownership, remove from `src/` or mark as deprecated
2. Update imports and test
3. Document ownership in `docs/architecture/STRUCTURE.md`

**Expected outcome:** Each module has one home, one truth.

### Phase 5: Update STRUCTURE.md (1 day)

Update `docs/architecture/STRUCTURE.md` (or create if missing) to document:

- Ownership of each module (which layer is canonical)
- Allowed imports (e.g., `src.*` must not import `telegram_bot.*`)
- Migration status of each collapse target
- Rationale for layering decisions

---

## Risk Assessment

### Circular Import Risk

**Risk:** Low.
**Reason:** `src/` currently has no `telegram_bot/` imports. Collapsing can only reduce imports, not add.
**Mitigation:** Run import cycle detector after each phase: `python -m py_compile src/**/*.py telegram_bot/**/*.py`

### Test Coverage Risk

**Risk:** Medium.
**Reason:** Tests may assume both locations are independent. Removing duplicates could expose untested paths.
**Mitigation:** Run full test suite after each phase: `make test-core test`

### Backward Compatibility Risk

**Risk:** Low (internal project).
**Reason:** Bot is not a published package. Internal callers can be migrated.
**Mitigation:** Use deprecation warnings in shims for 1 release; document in changelog.

### Blast Radius

**Risk:** Medium.
**Reason:** Collapsing affects 14 modules across two major directory trees.
**Mitigation:**
- Work one category at a time (shims → duplicates → diverged)
- Commit and test after each module
- Use git worktree for isolation (#2820 workspace hygiene)

### Import Latency Risk

**Risk:** Low.
**Reason:** No new lazy imports are needed; collapse only removes re-export chains.
**Mitigation:** Measure import time before/after: `python -c "import src; import telegram_bot" | time`

---

## Implementation Sequence

### Order Rationale

1. **Shims first** (5 modules): Lowest risk, clearest intent, fastest validation.
2. **Duplicates next** (5 modules): Straightforward removal, high confidence.
3. **Diverged last** (4 modules): Needs investigation, may require design decisions.

### Per-Module Checklist

For each module in sequence:

- [ ] Identify all callers (grep): `grep -r "from [src|telegram_bot] import ..." --include="*.py"`
- [ ] Read the module to understand intent and side effects
- [ ] Migrate callers (update imports)
- [ ] Run tests: `make test-core test`
- [ ] Commit with message: `docs: #2855 collapse <module_path>`
- [ ] Verify no import cycles: `python -m py_compile src/**/*.py telegram_bot/**/*.py`

### Proposed Implementation Order

**Shims (least risky):**
1. `phone_utils.py`
2. `services/bge_m3_client.py`
3. `services/bge_m3_query_bundle.py`
4. `services/content_loader.py`
5. `services/handoff_state.py`

**Duplicates (medium risk):**
6. `__init__.py`
7. `models/__init__.py`
8. `services/_retry.py`
9. `services/vectorizers.py`
10. `evaluation/__init__.py` (docstring-only, no logic)

**Diverged (investigate):**
11. `observability_bootstrap.py` (audit ownership, then merge or clarify)
12. `observability_payloads.py` (audit ownership, then merge or clarify)
13. `scoring.py` (audit intent, move to bot if domain-specific)
14. `services/__init__.py` (clarify export surface, merge if possible)

---

## Done Criteria

- [ ] Inventory documented (this ADR): all 14 modules categorized, ownership clarified
- [ ] Diverged modules audited: ownership and boundary defined for each
- [ ] Shims collapsed: all 5 re-export shims removed or deprecated; callers migrated to `src/`
- [ ] Duplicates collapsed: all 5 substantive duplicates removed; callers migrated to `src/`
- [ ] Diverged converged: remaining 4 modules have single canonical home or clear domain boundary
- [ ] No circular imports: `python -m py_compile src/**/*.py telegram_bot/**/*.py` succeeds
- [ ] Tests pass: `make test-core test` passes with no new skips or failures
- [ ] STRUCTURE.md updated: ownership map documents all modules and allowed imports
- [ ] Changelog entry: summarize collapse, deprecation timeline, migration path for users
- [ ] PR merged: all changes reviewed and integrated

---

## Non-Goals

- Merge `src/` and `telegram_bot/` into a single directory (that's a future refactor)
- Change public API or module names (collapse is internal reorganization)
- Migrate voice agent, Mini App, or other removed surfaces (they are archived)
- Decide on monorepo-vs-multi-package structure (that's #2846)

---

## References

- ADR #2846: Layering Violation Resolution (defines ownership rules)
- Issue #1948: Reverse layering (phone_utils shim context)
- Issues #2045–#2049: Migration implementation phases
- `docs/architecture/STRUCTURE.md` (to be updated or created)
- Current file locations: `src/` and `telegram_bot/` directories
