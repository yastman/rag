# Test Suite & Documentation Remediation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restore green test suite and synchronize documentation with actual codebase state

**Problem Statement:** `make test` claims 1667/1667 pass in swarm execution plan, but pytest fails at collection with 12 errors. Additionally, alerting rules, ingestion targets, and guardrails documentation don't match actual code.

**Tech Stack:** Python 3.12, pytest, OpenTelemetry, Qdrant SDK

---

## Executive Summary

| Priority | Category | Issues | Acceptance |
|----------|----------|--------|------------|
| **P0** | Test Collection | 12 errors blocking `pytest tests/` | 0 collection errors |
| **P0** | Alerting Rules | Missing rule files, docs out of sync | `make monitoring-up` loads rules |
| **P1** | Ingestion | Makefile vs docs mismatch, gdrive stub | Consistent interface |
| **P1** | Guardrails | Plan vs code (threshold, method name) | Plan reflects reality |
| **P2** | Redis Policy | dev vs local inconsistency | Documented or unified |
| **P2** | Repo Hygiene | `test_*.py` in root | Moved or renamed |

---

## P0: Test Collection Errors (BLOCKING)

### Current State

```bash
$ uv run python -m pytest tests/ --collect-only
# collected 2045 items / 12 errors
```

| # | File | Error | Root Cause |
|---|------|-------|------------|
| 1 | `tests/baseline/test_cli.py` | SyntaxError | `cli.py:191` has `f\"\"\"` (escaped quotes in f-string) |
| 2 | `tests/benchmark/test_docling_vs_pymupdf.py` | ModuleNotFoundError | `pymupdf_chunker` not in path |
| 3 | `tests/e2e/test_e2e_pipeline.py` | ImportError | `HybridRetrieverService` not exported |
| 4 | `tests/integration/test_docker_services.py` | ModuleNotFoundError | `asyncpg` not in dependencies |
| 5 | `tests/legacy/test_api_comparison.py` | ModuleNotFoundError | `contextualize_groq_async` not in path |
| 6 | `tests/legacy/test_api_comparison_multi.py` | ModuleNotFoundError | Same |
| 7 | `tests/legacy/test_api_extended.py` | ModuleNotFoundError | Same |
| 8 | `tests/legacy/test_api_quick.py` | ModuleNotFoundError | Same |
| 9 | `tests/legacy/test_api_safe.py` | ModuleNotFoundError | Same |
| 10 | `tests/legacy/test_chunking_quality.py` | ModuleNotFoundError | `pymupdf_chunker` not in path |
| 11 | `tests/legacy/test_dbsf_fusion.py` | ImportError | `config.QDRANT_API_KEY` doesn't exist |
| 12 | `tests/smoke/test_chunking_smoke.py` | ModuleNotFoundError | `pymupdf_chunker` not in path |

---

### Task P0.1: Fix SyntaxError in cli.py

**File:** `tests/baseline/cli.py:191`

**Problem:** Line contains `f\"\"\"<!DOCTYPE html>` — the backslash-escaped quotes are invalid Python syntax. This is likely a copy-paste artifact.

**Fix:** Replace `f\"\"\"` with `f"""` (proper triple-quoted f-string).

**Verification:**
```bash
python -c "import tests.baseline.cli"  # Should not raise SyntaxError
```

---

### Task P0.2: Fix HybridRetrieverService Import

**File:** `tests/e2e/test_e2e_pipeline.py:12`

**Problem:**
```python
from telegram_bot.services import HybridRetrieverService  # Doesn't exist
```

**Actual export in `telegram_bot/services/__init__.py`:**
```python
from .retriever import RetrieverService  # Line 34
```

**Decision needed:** Either:
- **Option A:** Add alias export: `HybridRetrieverService = RetrieverService`
- **Option B:** Update test import to use `RetrieverService`

**Recommendation:** Option B — update test to use actual name, avoid confusion.

**Verification:**
```bash
pytest tests/e2e/test_e2e_pipeline.py --collect-only
```

---

### Task P0.3: Fix asyncpg Dependency

**File:** `tests/integration/test_docker_services.py:2`

**Problem:**
```python
import asyncpg  # Not in dependencies
```

**Decision needed:**
- **Option A:** Add `asyncpg` to dev dependencies
- **Option B:** Add `pytest.importorskip("asyncpg")` at module top

**Recommendation:** Option B — this is an optional integration test, skip if dependency missing.

**Fix:**
```python
# At top of file, after imports
asyncpg = pytest.importorskip("asyncpg", reason="asyncpg not installed")
```

**Verification:**
```bash
pytest tests/integration/test_docker_services.py --collect-only
```

---

### Task P0.4: Fix Legacy Module Imports

**Files:**
- `tests/legacy/test_api_*.py` (5 files) → import `contextualize_groq_async`
- `tests/legacy/test_chunking_quality.py` → import `pymupdf_chunker`
- `tests/legacy/test_dbsf_fusion.py` → import `config.QDRANT_API_KEY`

**Actual locations:**
- `legacy/contextualize_groq_async.py` exists
- `legacy/pymupdf_chunker.py` exists
- `config.QDRANT_API_KEY` → now `src/config/settings.py` with different structure

**Decision needed:**
- **Option A:** Add `legacy/` to Python path in conftest
- **Option B:** Exclude `tests/legacy/` from default test collection
- **Option C:** Fix imports to use proper paths

**Recommendation:** Option B — these are legacy tests for deprecated code. Exclude from default run.

**Fix in `pyproject.toml`:**
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
# Add ignore pattern
norecursedirs = ["tests/legacy"]
```

Or alternatively, rename directory to `tests/_legacy/` (underscore prefix = auto-ignored).

**Verification:**
```bash
pytest tests/ --collect-only --ignore=tests/legacy
```

---

### Task P0.5: Fix Benchmark/Smoke pymupdf_chunker Imports

**Files:**
- `tests/benchmark/test_docling_vs_pymupdf.py:18`
- `tests/smoke/test_chunking_smoke.py:17`

**Problem:** Import `pymupdf_chunker` which lives in `legacy/pymupdf_chunker.py`

**Decision needed:**
- **Option A:** Add shim file `pymupdf_chunker.py` in root that re-exports from legacy
- **Option B:** Update imports to `from legacy.pymupdf_chunker import ...`
- **Option C:** Move these tests to `tests/legacy/` and exclude

**Recommendation:** Option C for benchmark, Option B for smoke (if smoke tests are actively used).

**Verification:**
```bash
pytest tests/benchmark/ tests/smoke/ --collect-only
```

---

### Task P0.6: Full Collection Verification

After all P0.1-P0.5 fixes:

```bash
uv run python -m pytest tests/ --collect-only
# Expected: collected 2045+ items / 0 errors
```

**Acceptance criteria:**
- [ ] `pytest tests/ --collect-only` exits with code 0
- [ ] No `ERROR collecting` messages
- [ ] `make test` aligns with CLAUDE.md documentation

---

## P0: Alerting Rules Sync

### Current State

**Expected (per docs/ALERTING.md:86 and compose):**
```
docker/monitoring/rules/
├── telegram-bot.yaml
└── infrastructure.yaml
```

**Actual:**
```
docker/monitoring/rules/
└── fake/
    ├── telegram-bot.yaml
    ├── infrastructure.yaml
    └── extended-services.yaml
```

The rules exist but in a `fake/` subdirectory, meaning Loki ruler doesn't load them.

---

### Task P0.7: Move Alerting Rules to Correct Location

**Option A (Recommended):** Move files from `fake/` to parent:
```bash
mv docker/monitoring/rules/fake/*.yaml docker/monitoring/rules/
rmdir docker/monitoring/rules/fake
```

**Option B:** Update compose volume mount to include `fake/`:
```yaml
volumes:
  - ./docker/monitoring/rules/fake:/etc/loki/rules
```

**Recommendation:** Option A — remove the `fake/` indirection.

---

### Task P0.8: Sync docs/ALERTING.md

**File:** `docs/ALERTING.md`

Verify all path references match actual file locations after P0.7.

**Verification:**
```bash
make monitoring-up
# Check Loki ruler loaded rules:
curl -s http://localhost:3100/loki/api/v1/rules | jq '.data.groups[].name'
```

**Acceptance criteria:**
- [ ] `make monitoring-up` starts without errors
- [ ] Loki API shows loaded rule groups
- [ ] `make monitoring-test-alert` works
- [ ] `docs/ALERTING.md` references match actual paths

---

## P1: Ingestion Interface Sync

### Current State

**Plan claims (docs/plans/2026-02-02-rag-2026-swarm-execution.md:318):**
```
make ingest-setup
make ingest-run
make ingest-continuous
make ingest-status
```

**Actual Makefile targets:**
```
make ingest-setup
make ingest-dir
make ingest-gdrive    # Returns "not yet implemented"
make ingest-status
make ingest-test
```

**Missing:** `ingest-run`, `ingest-continuous`
**Stub:** `ingest-gdrive` → `src/ingestion/service.py:180` returns error

---

### Task P1.1: Decide on ingest-gdrive

**Options:**
- **Option A:** Mark as experimental/not-supported in docs, keep stub
- **Option B:** Remove target from Makefile entirely
- **Option C:** Implement Google Drive ingestion

**Recommendation:** Option A — document current state, don't claim it works.

---

### Task P1.2: Sync Plan with Makefile

**File:** `docs/plans/2026-02-02-rag-2026-swarm-execution.md`

Update Milestone J to reflect actual targets:
- Remove references to `ingest-run`, `ingest-continuous`
- Add `ingest-dir`, `ingest-test`
- Mark `ingest-gdrive` as stub/experimental

**Acceptance criteria:**
- [ ] Plan documents only existing Makefile targets
- [ ] No "✅ выполнено" for non-existent functionality

---

## P1: Guardrails Sync

### Current State

**Plan claims (docs/plans/2026-02-02-rag-2026-swarm-execution.md:287):**
```python
LOW_CONFIDENCE_THRESHOLD = 0.3
create_low_confidence_response()
```

**Actual code (telegram_bot/services/llm.py):**
```python
LOW_CONFIDENCE_THRESHOLD = 0.5  # Line 17
get_low_confidence_response()   # Line 445
```

---

### Task P1.3: Update Plan References

**File:** `docs/plans/2026-02-02-rag-2026-swarm-execution.md`

Fix:
- `LOW_CONFIDENCE_THRESHOLD = 0.3` → `0.5`
- `create_low_confidence_response` → `get_low_confidence_response`

**Acceptance criteria:**
- [ ] Plan matches actual symbol names and values

---

## P1: Plan References Cleanup

### Task P1.4: Fix Variable Names

**File:** `docs/plans/2026-02-02-rag-2026-swarm-execution.md`

| Line | Claimed | Actual | Fix |
|------|---------|--------|-----|
| 45 | `LITELLM_BASE_URL` | `LLM_BASE_URL` | Update reference |
| 40 | `src/config/settings.py:211` | `src/config/settings.py:293` | Update line number |
| 206 | commit `fb2b237` | commit `fb52a69` | Update hash |

---

### Task P1.5: Remove Duplicate Lines

**File:** `docs/plans/2026-02-02-rag-2026-swarm-execution.md`

Section J (around line 308) has duplicate entries. Remove duplicates.

**Acceptance criteria:**
- [ ] Plan can be used as source of truth without manual verification

---

## P2: Redis Policy Consistency

### Current State

| File | Policy |
|------|--------|
| `docker-compose.dev.yml` | `--maxmemory-policy volatile-lfu` |
| `docker-compose.local.yml:27` | `--maxmemory-policy allkeys-lfu` |

**Difference:**
- `volatile-lfu` — evicts only keys with TTL set
- `allkeys-lfu` — evicts any key

---

### Task P2.1: Document or Unify Redis Policy

**Options:**
- **Option A:** Unify to `volatile-lfu` (safer, requires TTLs)
- **Option B:** Document difference in CLAUDE.md or docker rules

**Recommendation:** Option B — dev and local have different use cases.

**Acceptance criteria:**
- [ ] Difference documented OR unified

---

## P2: Repo Hygiene

### Current State

Root directory contains:
```
test_*.py files
```

These are not collected (pyproject.toml `testpaths = ["tests"]`), but create noise.

---

### Task P2.2: Move or Rename Root Test Files

**Find files:**
```bash
ls -la *.py | grep test_
```

**Options:**
- **Option A:** Move to `scripts/` or `evaluation/`
- **Option B:** Rename to not match `test_*.py` pattern
- **Option C:** Delete if obsolete

**Acceptance criteria:**
- [ ] No `test_*.py` in repo root

---

## Verification Checklist

### P0 (Must pass before merge)

- [ ] `uv run python -m pytest tests/ --collect-only` → 0 errors
- [ ] `make test` → passes (or documents expected skips)
- [ ] `make monitoring-up` → Loki loads alerting rules
- [ ] `curl http://localhost:3100/loki/api/v1/rules` → shows rule groups

### P1 (Should fix)

- [ ] `docs/plans/2026-02-02-rag-2026-swarm-execution.md` → no false claims
- [ ] `Makefile` ingestion targets → documented correctly
- [ ] Guardrails threshold/method names → match code

### P2 (Nice to have)

- [ ] Redis policy → documented or unified
- [ ] Root `test_*.py` → cleaned up

---

## Appendix A: Original OTEL/Qdrant Mock Fixes

*Preserved from original plan — these are runtime test failures, not collection errors.*

### OTEL Tests: Switch to HTTP Exporters

**Files:**
- `src/observability/otel_setup.py:6-7`
- `tests/unit/test_otel_setup.py`

**Problem:** `ModuleNotFoundError: No module named 'opentelemetry.exporter.otlp.proto.grpc'`

**Fix:** Change imports from gRPC to HTTP:
```python
# From:
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# To:
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
```

Update endpoints from port 4317 (gRPC) to 4318 (HTTP).

---

### Qdrant Mock Timing

**Files:** `tests/unit/test_qdrant_service.py:790-803, 834-846`

**Problem:** `reset_qdrant_modules()` fixture clears module cache before patch applies.

**Fix:** Move import inside `with patch(...)` context:
```python
async def test_close_calls_client_close(self):
    with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as mock_cls:
        import sys
        sys.modules.pop("telegram_bot.services.qdrant", None)
        from telegram_bot.services.qdrant import QdrantService
        # ... rest of test
```

---

## PR Strategy (Suggested)

| PR | Scope | Reviewer Focus |
|----|-------|----------------|
| **PR 1** | P0.1-P0.6 (test collection) | Does `pytest --collect-only` pass? |
| **PR 2** | P0.7-P0.8 (alerting rules) | Do rules load in Loki? |
| **PR 3** | P1.1-P1.5 (docs sync) | Do references match code? |
| **PR 4** | P2.1-P2.2 (hygiene) | No functional changes |
| **PR 5** | Appendix A (OTEL/Qdrant) | Do all tests pass? |

Or combine P0 into single PR if reviewer bandwidth limited.
