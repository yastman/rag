# Issue #858: Reduce mypy silences and `ignore_errors` risk — Execution Plan

> **Status:** Planning only — no code/config changes in this PR.
> **Verified:** 2026-05-01 against `pyproject.toml`, `Makefile`, and current `HEAD`.

---

## 1. Current state (verified facts)

### 1.1 Global mypy config (`pyproject.toml`)
```toml
[tool.mypy]
python_version = "3.14"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = false   # ← broad silence
ignore_missing_imports = true   # ← broad silence
explicit_package_bases = true

[[tool.mypy.overrides]]
module = "FlagEmbedding.*"
ignore_missing_imports = true   # ← redundant (already global)

[[tool.mypy.overrides]]
module = "src.retrieval.topic_classifier"
disallow_untyped_defs = true    # ← only strict override
```

### 1.2 `ignore_errors = true` overrides
**Count: 0** — no `ignore_errors = true` entries exist in `pyproject.toml`, source, tests, or docs.

### 1.3 `# type: ignore` occurrences
**Total: 182** across 59 files.

| Directory | Files | Comments |
|-----------|-------|----------|
| `src/` | 9 | 62 |
| `telegram_bot/` | 31 | 88 |
| `tests/` | 19 | 32 |
| **Total** | **59** | **182** |

**Bare `# type: ignore` (no error code): 18**
- `src/utils/structure_parser.py`: 11
- `src/evaluation/smoke_test.py`: 4
- `src/ingestion/cocoindex_flow.py`: 3

**Top error codes (coded ignores only):**

| Code | Count |
|------|-------|
| `index` | 37 |
| `arg-type` | 27 |
| `union-attr` | 20 |
| `call-overload` | 20 |
| `attr-defined` | 13 |
| `method-assign` | 11 |
| `no-any-return` | 9 |
| `misc` | 9 |
| `assignment` | 8 |
| `call-arg` | 4 |
| `import-untyped` | 3 |
| Others | 6 |

### 1.4 Live mypy error counts (current `HEAD`)

| Scope | Command | Errors |
|-------|---------|--------|
| `src/` | `mypy src/ --ignore-missing-imports` | **0** |
| `telegram_bot/` | `mypy telegram_bot/ --ignore-missing-imports` | **0** |
| `tests/` | `mypy tests/ --ignore-missing-imports` | **438** |
| `src/` + `telegram_bot/` | combined | **0** |

### 1.5 CI / Makefile gap
`Makefile` target `type-check` (and therefore `check`, `ci`, `pre-commit`) only runs:
```makefile
uv run mypy src/ --ignore-missing-imports
```
**`telegram_bot/` and `tests/` are not type-checked in CI**, despite `telegram_bot/` being clean and `tests/` having 438 errors.

---

## 2. Risk analysis

| Silence | Risk | Mitigation |
|---------|------|------------|
| `disallow_untyped_defs = false` (global) | Untyped function bodies are unchecked; regressions in type safety go unnoticed | Enable per-module via overrides, or migrate module-by-module |
| `ignore_missing_imports = true` (global) | Missing stubs for new deps hide API drift | Remove redundant override; add per-module overrides only where stubs are unavailable |
| `# type: ignore` (182) | Localized masking of real type bugs; bare ignores obscure intent | Replace bare ignores with specific codes; fix or narrow each ignore |
| `telegram_bot/` excluded from CI | Zero mypy coverage for the largest surface area | Add to `make type-check` immediately (zero errors today) |
| `tests/` excluded from CI | 438 errors accumulate; test code quality drifts | Add to CI with staged fixes or a temporary scoped override |

---

## 3. Phased PR decomposition

### Phase 0 — Smallest first slice (can be implemented without broad refactor)
**Goal:** Close the CI coverage gap for `telegram_bot/` and remove one redundant override.

**Owner:** infra / qa
**Files touched:**
- `Makefile` (line ~123)
- `pyproject.toml` (line ~308-310)

**Changes:**
1. Expand `make type-check` to include `telegram_bot/`:
   ```makefile
   uv run mypy src/ telegram_bot/ --ignore-missing-imports
   ```
2. Remove the redundant `FlagEmbedding.*` override block.

**Acceptance checks:**
- `make type-check` passes
- `make check` passes
- `uv run mypy src/ telegram_bot/ --ignore-missing-imports --no-error-summary` exits 0
- No source code changes required

**Blast radius:** Minimal — only build config. `telegram_bot/` is already clean.

---

### Phase 1 — Harden `src/` module-by-module
**Goal:** Remove `# type: ignore` comments and enable `disallow_untyped_defs = true` for the cleanest modules.

**Owner:** backend / retrieval
**Modules (in priority order):**

1. **`src/retrieval/topic_classifier`** — already has `disallow_untyped_defs = true`; audit existing ignores (0 currently) and keep it as the reference module.
2. **`src/utils/structure_parser.py`** — 11 bare ignores. Replace with specific codes or fix types (the `metadata: dict[str, Any]` pattern should eliminate most).
3. **`src/models/contextualized_embedding.py`** — 3 ignores (`arg-type`, `assignment`, `misc`). Narrow or fix.
4. **`src/evaluation/` scripts** — 37 ignores, mostly `index` on `CONFIG_SNAPSHOT` dict access. Type the snapshot as `TypedDict` or `dataclass`.

**Likely mypy commands:**
```bash
uv run mypy src/utils/structure_parser.py --ignore-missing-imports --warn-unused-ignores
uv run mypy src/models/contextualized_embedding.py --ignore-missing-imports --warn-unused-ignores
uv run mypy src/evaluation/ --ignore-missing-imports --warn-unused-ignores
```

**Acceptance checks:**
- Each targeted file/module shows 0 mypy errors and 0 unused ignores.
- `# type: ignore` count in `src/` drops by at least 30 %.
- `make type-check` still passes.

---

### Phase 2 — Harden `telegram_bot/` services and handlers
**Goal:** Remove `# type: ignore` from high-touch bot files.

**Owner:** bot / telegram
**Files (sorted by ignore count):**

| File | Ignores | Dominant codes |
|------|---------|----------------|
| `telegram_bot/bot.py` | 19 | `union-attr`, `arg-type`, `misc`, `return-value` |
| `telegram_bot/services/llm.py` | 8 | `arg-type`, `call-overload` |
| `telegram_bot/graph/graph.py` | 10 | `call-overload` |
| `telegram_bot/handlers/demo_handler.py` | 4 | `assignment`, `arg-type`, `attr-defined` |
| `telegram_bot/keyboards/services_keyboard.py` | 5 | `union-attr` |
| `telegram_bot/dialogs/crm_contacts.py` | 4 | `arg-type` |
| `telegram_bot/services/content_loader.py` | 6 | `no-any-return`, `import-untyped` |

**Likely mypy commands:**
```bash
uv run mypy telegram_bot/bot.py --ignore-missing-imports --warn-unused-ignores
uv run mypy telegram_bot/services/llm.py --ignore-missing-imports --warn-unused-ignores
uv run mypy telegram_bot/graph/graph.py --ignore-missing-imports --warn-unused-ignores
```

**Acceptance checks:**
- Each file reduces ignores by ≥ 50 % or reaches 0.
- `uv run mypy telegram_bot/ --ignore-missing-imports` still exits 0.
- Unit tests for touched handlers/services pass: `pytest tests/unit/ -k "<module_name>" -v`

---

### Phase 3 — Address `tests/` mypy coverage
**Goal:** Add `tests/` to CI type-checking and drive the 438 errors to 0 (or to a bounded, documented exception list).

**Owner:** qa / infra
**Error breakdown (438 total):**

| Code | Count | Typical cause |
|------|-------|---------------|
| `union-attr` | 146 | Mock objects, monkey-patching |
| `arg-type` | 118 | Test fixtures with loose types |
| `call-arg` | 43 | `BotConfig(_env_file=...)` misuse, missing defaults |
| `no-any-return` | 27 | `yaml.safe_load` returns `Any` |
| `attr-defined` | 27 | Dynamic attribute assignment on mocks |
| `method-assign` | 24 | Replacing methods on instances in tests |
| `import-untyped` | 20 | Missing stubs for `yaml`, `docling`, etc. |
| Others | 33 | Index, operator, assignment, etc. |

**Recommended approach (non-refactor):**
1. Add a dedicated `mypy-tests` Makefile target that runs with `--ignore-missing-imports`.
2. Fix the easy wins first:
   - Add `types-PyYAML` or `yaml` stub fallback to dev deps (or use `# type: ignore[import-untyped]` only on import lines).
   - Fix `BotConfig(_env_file=...)` calls — use `model_config` or correct constructor.
   - Replace bare method patching with `unittest.mock.patch.object` where possible.
3. For the remaining errors, add per-file `# mypy: ignore-errors` **only** inside `tests/` as a temporary safety net, with a ticket to remove it.

**Likely mypy commands:**
```bash
uv run mypy tests/ --ignore-missing-imports --no-error-summary | grep "error:" | wc -l
```

**Acceptance checks:**
- `mypy-tests` target exists and is documented.
- Error count drops by at least 30 % in the first PR.
- No new errors are introduced (baseline file or CI gate).

---

### Phase 4 — Flip `disallow_untyped_defs` for core modules
**Goal:** Enable strict typing module-by-module, avoiding a big-bang PR.

**Owner:** backend + bot leads
**Method:** Add `[[tool.mypy.overrides]]` entries for each clean module:
```toml
[[tool.mypy.overrides]]
module = "src.retrieval.search_engines"
disallow_untyped_defs = true
```

**Candidate modules (start with smallest, already-clean):**
1. `src.retrieval.topic_classifier` — already enabled; keep.
2. `src.utils.structure_parser` — after Phase 1 fixes.
3. `src.models.contextualized_embedding` — after Phase 1 fixes.
4. `telegram_bot.services.content_loader` — small file, low complexity.

**Acceptance checks:**
- `uv run mypy src/ telegram_bot/ --ignore-missing-imports` exits 0.
- Each new override is justified by 0 existing errors in that module.

---

### Phase 5 — Global `ignore_missing_imports` cleanup
**Goal:** Remove the global `ignore_missing_imports = true` and replace with per-module overrides only where stubs are genuinely unavailable.

**Owner:** infra
**Files touched:** `pyproject.toml`

**Approach:**
1. Set `ignore_missing_imports = false` globally.
2. Run `mypy src/ telegram_bot/` and collect modules that fail with `import-untyped` / `import-not-found`.
3. Add targeted overrides for those modules only.
4. Where stubs exist (e.g. `types-PyYAML`, `types-redis`), add them to `[dependency-groups] dev`.

**Acceptance checks:**
- `make type-check` passes.
- Number of `[[tool.mypy.overrides]]` blocks does not exceed 15 (arbitrary sanity bound).

---

## 4. Rollback / safety guidelines

- **Never** enable `ignore_errors = true` for a whole package — always use per-module overrides or fix the root cause.
- Each phase must keep `make type-check` green; no phase may increase the error count in `src/` or `telegram_bot/`.
- If a `# type: ignore` is removed and mypy still errors, either fix the type or re-add with a **specific** error code and a `TODO(#858)` comment.
- Prefer `warn_unused_ignores = true` in local runs to catch stale ignores.

---

## 5. Success metrics

| Metric | Current | Phase 0 | Phase 1 | Phase 2 | Phase 3 | Phase 5 |
|--------|---------|---------|---------|---------|---------|---------|
| `# type: ignore` total | 182 | 182 | ≤ 150 | ≤ 110 | ≤ 80 | ≤ 50 |
| Bare `# type: ignore` | 18 | 18 | 0 | 0 | 0 | 0 |
| `ignore_errors = true` | 0 | 0 | 0 | 0 | 0 | 0 |
| `disallow_untyped_defs` modules | 1 | 1 | ≥ 3 | ≥ 5 | ≥ 5 | ≥ 10 |
| CI mypy coverage | `src/` only | `src/` + `telegram_bot/` | same | same | + `tests/` gate | same |
| mypy errors in `tests/` | 438 | 438 | 438 | 438 | ≤ 300 | ≤ 300 |

---

## 6. References

- Issue: https://github.com/yastman/rag/issues/858
- `pyproject.toml` — `[tool.mypy]` section
- `Makefile` — `type-check`, `check`, `ci` targets
- Verification commands run on 2026-05-01:
  ```bash
  rg -n "ignore_errors|# type: ignore|disallow_untyped_defs|\[\[tool\.mypy\.overrides\]\]" pyproject.toml src telegram_bot tests docs -g '*.py' -g '*.toml' -g '*.md'
  uv run mypy src/ --ignore-missing-imports --no-error-summary
  uv run mypy telegram_bot/ --ignore-missing-imports --no-error-summary
  uv run mypy tests/ --ignore-missing-imports --no-error-summary
  make check
  ```
