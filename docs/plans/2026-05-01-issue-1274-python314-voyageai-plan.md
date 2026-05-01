# Execution Plan: Unblock Broad Unit Tests on Python 3.14 for `voyageai` / Pydantic v1 Compatibility

> Issue: #1274
> Branch: `plan/1274-py314-voyage`
> Date: 2026-05-01

---

## 1. Current Dependency Facts

### 1.1 `pyproject.toml` (production)
- `requires-python = ">=3.11"`
- `voyageai = ">=0.3.0"` — declared in **main** dependencies (not optional).
- `pydantic-settings>=2.0.0` is also a main dependency; it transitively pulls `pydantic` v2.
- Ruff `target-version = "py314"`, MyPy `python_version = "3.14"`, Pylint `py-version = "3.14"`.

### 1.2 `uv.lock` (resolved)
- `voyageai==0.3.7` (sdist + wheel, uploaded 2025-12-16).
- `pydantic==2.12.3` (resolved for the entire graph).
- `voyageai` declares `dependencies = ["pydantic"]` with **no upper-bound or version qualifier**.
- `voyageai` also declares `numpy` with marker `python_full_version < '3.14'`, meaning under 3.14 the SDK may already be partially unsupported by its own metadata.

### 1.3 The Failure Symptom
Under CPython 3.14, importing `voyageai` triggers Pydantic model construction inside `voyageai.object.multimodal_embeddings.MultimodalInput`:

```
ValueError: On field "content" ... constraints ... min_items
```

This is a Pydantic v1-style constraint (`min_items`) being evaluated by Pydantic v2 core under Python 3.14, where certain validation semantics have tightened or changed. The upstream `voyageai` wheel does not guard against this at import time.

---

## 2. Current Import Chain & Coupling

### 2.1 Eager (top-level) `voyageai` imports

| File | Import style | Consumer |
|------|-------------|----------|
| `telegram_bot/services/voyage.py` | `import voyageai` (line 13) | **Module-level** — loaded whenever `telegram_bot.services.voyage` is imported |
| `src/models/contextualized_embedding.py` | `import voyageai` (line 23) | **Module-level** — loaded on any import of `ContextualizedEmbeddingService` |
| `tests/unit/test_contextualized_embeddings.py` | `import voyageai` | Direct test of contextualized API |

### 2.2 Consumers of `VoyageService` (indirect `voyageai` trigger)

| File | Import pattern | Notes |
|------|---------------|-------|
| `src/ingestion/gdrive_indexer.py` | `from telegram_bot.services import VoyageService` | **Deprecated** legacy ingestion; eagerly instantiates `VoyageService` inside `GDriveIndexer.__init__` |
| `src/ingestion/gdrive_flow.py` | `from src.ingestion.gdrive_indexer import GDriveIndexer` | Legacy flow; test `tests/unit/ingestion/test_gdrive_flow.py` imports this module at **test-collection time** (lines 14-16) |
| `src/ingestion/unified/qdrant_writer.py` | `from telegram_bot.services import VoyageService` | Unified ingestion; imports at module top-level |
| `src/ingestion/cocoindex_flow.py` | Lazy `from telegram_bot.services import VoyageService` inside method | Already lazy; **good pattern** |
| `telegram_bot/services/__init__.py` | `__getattr__` lazy map for `VoyageService` | Lazy at package boundary, but **bypassed** by direct `from telegram_bot.services.voyage import VoyageService` or by any code that touches `telegram_bot/services/voyage.py` |

### 2.3 Why the test suite breaks

```
tests/unit/ingestion/test_gdrive_flow.py
  └─ from src.ingestion.gdrive_flow import ...
       └─ from src.ingestion.gdrive_indexer import GDriveIndexer
            └─ from telegram_bot.services import VoyageService
                 └─ telegram_bot/services/voyage.py  →  import voyageai  →  💥
```

Because `test_gdrive_flow.py` does its import inside a `warnings.catch_warnings()` block at **module scope** (lines 14-16), pytest collects the file and immediately executes the import chain, which loads `voyageai` unconditionally.

---

## 3. Options Matrix

| Option | Description | Blast Radius | Effort | Risk |
|--------|-------------|--------------|--------|------|
| **A. Upgrade `voyageai`** | Bump to latest upstream release that fixes Pydantic v1 constraints on 3.14 | Low (single dep) | Low | **Medium** — upstream may not have released a fix yet; `numpy` marker `<3.14` suggests upstream 3.14 support is incomplete |
| **B. Pin / replace `voyageai`** | Pin to a fork, replace with raw HTTP client, or vendor the small subset we use (embed + rerank) | Medium | Medium-High | **High** — re-implements retry, batching, observability contracts; long-term maintenance burden |
| **C. Lazy import `voyageai`** | Move `import voyageai` from module top-level into `VoyageService.__init__` and methods; same for `ContextualizedEmbeddingService` | Low-Medium | Low | **Low** — aligns with existing repo convention (`redisvl`, `langmem` are already lazy); does not fix production runtime on 3.14, but **unblocks unit tests** |
| **D. Test isolation (skip / mock at collection time)** | Ensure any test that transitively touches `voyageai` either mocks before import or is gated behind `requires_extras` / `pytest.skip` | Low | Low | **Low** — immediate unblock for CI; leaves production code unchanged |
| **E. Adapter boundary (optional extra)** | Move `voyageai` from main deps into an optional extra (e.g. `voyage`) and gate all consumers behind `try/except ImportError` | Medium | Medium | **Medium** — changes install contract; deployment images that rely on voyage would need `--extra voyage`; ingestion paths would need runtime guards |

### 3.1 Recommended Path: **C + D + A (phased)**

1. **Phase 1 (Immediate unblock):** Apply **C** (lazy imports) + **D** (test isolation) so that `tests/unit/` passes under Python 3.14 without touching `voyageai` at collection time.
2. **Phase 2 (Upstream watch):** Track **A** (upgrade `voyageai`) once upstream ships a 3.14-compatible release; remove lazy-import workarounds only when the upgraded SDK is proven stable.
3. **Phase 3 (Structural hardening — optional):** If upstream never fixes 3.14, evaluate **E** (adapter boundary / optional extra) or **B** (HTTP replacement) as a longer-term architectural change.

---

## 4. SDK / Dependency Lookup Plan

Per `AGENTS.md` SDK lookup order:

1. **Repo registry** — `docs/engineering/sdk-registry.md` already has a `voyageai` entry (lines 349-361). It notes:
   - "Тяжёлый import (pandas, scipy) — lazy import ОБЯЗАТЕЛЬНО"
   - "НЕ импортировать на top-level в модулях бота"

   **Gap:** The registry mandates lazy import for performance reasons, but `telegram_bot/services/voyage.py` and `src/models/contextualized_embedding.py` currently violate this by importing `voyageai` at module top-level.

2. **Current code usage** — Audit of all `voyageai` surface area:
   - `voyageai.Client` → `VoyageService.__init__`
   - `voyageai.error.*` → `tenacity` retry decorators (module-level `retry_if_exception_type` calls)
   - `voyageai` direct import → `tests/unit/test_contextualized_embeddings.py`

3. **Official docs / Context7** — Before any upgrade decision, query Context7 for `voyageai` changelog and Python 3.14 compatibility notes:
   ```bash
   # Context7 library ID from sdk-registry.md
   /voyage-ai/voyageai-python
   ```
   Key questions:
   - Does `voyageai>=0.3.8` (or later) fix Pydantic v1 constraint errors?
   - Is `numpy` optional or removed as a hard dependency in newer releases?
   - Does upstream CI test against CPython 3.14?

4. **Web search fallback** — Only if Context7 has no 3.14-specific guidance.

---

## 5. Phased Implementation PRs

### PR 1: `fix(tests): isolate voyageai from Python 3.14 unit test collection`
**Goal:** `tests/unit/` passes under Python 3.14 without changing production runtime behavior.

**Reserved files:**
- `telegram_bot/services/voyage.py`
- `src/models/contextualized_embedding.py`
- `tests/unit/ingestion/test_gdrive_flow.py`
- `tests/unit/test_voyage_service.py`
- `tests/unit/test_contextualized_embeddings.py`
- `tests/unit/services/test_voyage_observability.py`
- `tests/unit/ingestion/test_gdrive_indexer.py`
- `tests/unit/ingestion/test_qdrant_writer_behavior.py`

**Tasks:**
1. **Lazy-import `voyageai` in `telegram_bot/services/voyage.py`**
   - Move `import voyageai` from line 13 into `VoyageService.__init__`.
   - Move `voyageai.error.*` references into a local property or into `__init__` by storing exception classes on `self`.
   - Refactor `@retry` decorators so that `retry_if_exception_type` receives actual exception classes resolved at call time (e.g. wrap the decorated method with a thin helper that captures `voyageai.error` lazily, or use a callable class for `retry=`).

2. **Lazy-import `voyageai` in `src/models/contextualized_embedding.py`**
   - Same pattern: `import voyageai` inside `ContextualizedEmbeddingService.__init__`.
   - Move `voyageai.error` references into instance-level or method-level resolution.

3. **Fix test collection-time imports**
   - `tests/unit/ingestion/test_gdrive_flow.py`: replace module-scope `from src.ingestion.gdrive_flow import ...` with imports inside test functions / fixtures, or patch `GDriveIndexer` before the import is resolved.
   - `tests/unit/ingestion/test_gdrive_indexer.py`: ensure `VoyageService` is mocked before any real import happens.
   - `tests/unit/test_voyage_service.py`: already uses late import inside each test method; verify no module-level `voyageai` leak.
   - `tests/unit/test_contextualized_embeddings.py`: wrap `import voyageai` or service instantiation inside test functions.

4. **Focused checks**
   ```bash
   # Preflight — cheap, no external services
   uv run pytest tests/unit/ingestion/test_gdrive_flow.py -v --collect-only
   uv run pytest tests/unit/test_voyage_service.py -v --collect-only
   uv run pytest tests/unit/test_contextualized_embeddings.py -v --collect-only

   # Acceptance — broad unit suite under current Python (3.12)
   PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit

   # Acceptance — same suite under 3.14 (CI simulation)
   uv python install 3.14
   uv sync --python 3.14 --frozen --no-dev
   uv run --python 3.14 pytest tests/unit/ -n auto --dist=worksteal -q --timeout=30 -m "not legacy_api and not requires_extras and not slow"
   ```

**Rationale for keeping changes test-only + lazy-import:** We do not want to change the production API contract of `VoyageService`; we only want to ensure that importing the *module* does not require `voyageai` to be importable.

### PR 2: `chore(deps): evaluate voyageai upgrade for Python 3.14 runtime`
**Goal:** Decide whether upstream `voyageai` can replace the lazy-import workaround.

**Reserved files:**
- `pyproject.toml`
- `uv.lock`
- `docs/engineering/sdk-registry.md`

**Tasks:**
1. Query Context7 `/voyage-ai/voyageai-python` for 3.14 compatibility.
2. If a compatible version exists:
   - Run `make update-pkg PKG=voyageai` locally.
   - Execute the acceptance command from PR 1 under Python 3.14.
   - If tests pass *without* the lazy-import patches, revert PR 1 laziness and document the upgrade path.
   - If tests still fail, document the blocker and keep PR 1 as the canonical fix.
3. Update `docs/engineering/sdk-registry.md` with the final 3.14 compatibility note.

**Do NOT merge PR 2 until the upgrade is proven to fix collection-time and runtime errors under 3.14.**

### PR 3 (Future / Optional): `refactor(services): introduce voyageai adapter boundary`
**Goal:** Long-term structural safety if upstream never fixes 3.14.

**Reserved files:**
- `telegram_bot/services/voyage.py`
- `telegram_bot/services/voyage_adapter.py` (new)
- `pyproject.toml` (optional extra)

**Tasks:**
1. Create `VoyageAdapter` protocol / interface that hides `voyageai` completely.
2. Move `voyageai` dependency to `[project.optional-dependencies] voyage = ["voyageai>=x.y.z"]`.
3. Update all consumers to use the adapter with `try/except ImportError` fallback.
4. Update CI and deployment docs to include `--extra voyage` where needed.

**Trigger condition:** Only open PR 3 if Phase 2 confirms upstream will not support 3.14 within one release cycle.

---

## 6. Acceptance Commands

### 6.1 Cheaper preflight (no Docker, no external services)
```bash
# Verify that test collection under 3.14 no longer crashes on voyageai import
uv python install 3.14
uv sync --python 3.14 --frozen --no-dev
uv run --python 3.14 pytest tests/unit/ --collect-only -q
```
Expected: exit 0, no `ValueError: On field "content"` traceback.

### 6.2 Full unit gate (from issue)
```bash
# Run under Python 3.14 with dev deps installed
uv sync --python 3.14 --frozen
uv run --python 3.14 pytest tests/unit/ -n auto --dist=worksteal -q --timeout=30 -m "not legacy_api and not requires_extras and not slow"
```
Expected: all tests pass (exit 0).

### 6.3 Baseline check (must not regress 3.12)
```bash
PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit
```
Expected: all tests pass (exit 0).

---

## 7. Broad-Suite Gate Rationale

The issue asks for "broad `tests/unit/` passes under Python 3.14". The broad suite includes:
- `tests/unit/ingestion/test_gdrive_flow.py` — **currently broken** because of collection-time import.
- `tests/unit/ingestion/test_gdrive_indexer.py` — **currently broken** via same chain.
- `tests/unit/test_voyage_service.py` — may work individually, but contributes to the import graph.
- `tests/unit/test_contextualized_embeddings.py` — directly imports `voyageai`.
- `tests/unit/services/test_voyage_observability.py` — imports `VoyageService` class object.
- `tests/unit/ingestion/test_qdrant_writer_behavior.py` — mocks `VoyageService`, but if collection triggers the real module, it still fails.

**Why a broad gate matters:**
- The split-runtime workaround (lint on 3.14, tests on 3.12) masks integration drift. Code that passes type-check on 3.14 may fail at runtime due to dependency incompatibilities.
- Python 3.14 is the declared target version (`target-version = py314`, `python_version = 3.14`). CI should eventually run the full fast gate on the target runtime, not just a subset.
- Ingestion tests are a canary: they touch the deepest transitive dependency chain (`gdrive_flow` → `gdrive_indexer` → `VoyageService` → `voyageai`). If we fix the canary, we likely fix all remaining hidden import-time failures.

---

## 8. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Python 3.14 runtime incompatibilities beyond `voyageai`** | Medium | High | After unblocking collection, run the full `tests/unit/` suite under 3.14; catalog any new failures in a follow-up issue. |
| **Pydantic v1 constraints inside `voyageai` are never fixed upstream** | Medium | High | Keep the lazy-import + adapter-boundary option (PR 3) in the backlog; evaluate raw HTTP replacement if the SDK becomes unmaintained. |
| **Optional extras / CI runtime split confusion** | Low | Medium | Document clearly in `docs/engineering/sdk-registry.md` that `voyageai` is a **main** dependency (not optional) but guarded by lazy imports; do not change the CI split until PR 2 succeeds. |
| **Ingestion tests rely on real `VoyageService` instantiation** | Low | High | Verify that all ingestion unit tests mock `VoyageService` or its methods; if any test instantiates the real client, add `pytest.mark.requires_extras` or mock it. |
| **Lazy import of `voyageai.error` breaks `tenacity` retry decorators** | Medium | Medium | Refactor retry decorators to use a dynamic exception checker (e.g. `retry_if_exception_type((Exception,))` combined with a custom `before_sleep` that filters voyage exceptions by module name), or wrap the decorated coroutine in a helper that catches generic exceptions and re-raises voyage-specific ones after lazy resolution. |
| **Removing the split-runtime workaround too early** | Low | High | Only remove the CI 3.12 fallback after `make test-unit` passes under 3.14 for **two consecutive CI runs** on `dev`. |

---

## 9. Decision Log

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Do not upgrade `voyageai` in this plan** | The worker prompt explicitly forbids modifying `pyproject.toml`, `uv.lock`, or source code in this slice. Upgrade evaluation is reserved for PR 2. |
| 2 | **Do not move `voyageai` to optional extras yet** | Changing the install contract requires Docker/Compose/K8s validation (`scripts/validate_prod_env.sh`). That is out of scope for the immediate unblock and belongs to PR 3. |
| 3 | **Prefer lazy imports over test-only skips** | Lazy imports align with the existing repo convention (`redisvl`, `langmem`) and fix the root cause (import-time crash) rather than hiding it. They also protect against future collection-time regressions. |
| 4 | **Keep `numpy` marker observation as context only** | `uv.lock` shows `numpy` guarded by `python_full_version < '3.14'` under `voyageai` dependencies. This suggests upstream already knows 3.14 is problematic. We document it but do not attempt to patch the wheel. |

---

## 10. Next Actions

1. **Review this plan** — confirm Phase 1 scope and reserved files.
2. **Implement PR 1** — lazy imports + test isolation (separate worker).
3. **Run preflight** (`pytest --collect-only` under 3.14) to verify the fix.
4. **Run full acceptance** (`make test-unit` under 3.12 + 3.14).
5. **Open PR 2 tracker** — assign a watcher to check `voyageai` upstream releases for 3.14 compatibility.
6. **Close #1274 only after** the CI split-runtime workaround is removed and `tests/unit/` is green under 3.14.
