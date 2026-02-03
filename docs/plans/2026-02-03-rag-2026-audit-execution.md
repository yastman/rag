# RAG 2026 Implementation Audit — Execution Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Verify all 13 milestones from RAG 2026 plan are fully implemented and working

**Architecture:** Sequential verification in 6 phases — health check, file verification, feature flags, test counts, integration, known issues

**Tech Stack:** pytest, make, curl, docker, grep, jq

---

## Phase 1: Quick Health Check

### Task 1.1: Run All Tests

**Files:**
- Check: `Makefile` (test target)

**Step 1: Run test suite**

Run: `make test 2>&1 | tail -30`
Expected: All tests pass (1667+ minimum, 1820+ after Wave 3)

**Step 2: Record result**

Note the exact count: `X passed, Y warnings in Z seconds`

**Step 3: Commit checkpoint (if issues found)**

Only if tests fail — document which tests fail.

---

### Task 1.2: Run Lint and Type Check

**Files:**
- Check: `Makefile` (check target)

**Step 1: Run lint + types**

Run: `make check 2>&1 | tail -20`
Expected: Clean output, no errors

**Step 2: Record result**

Note any warnings or errors.

---

### Task 1.3: Check Docker Services

**Files:**
- Check: `docker-compose.dev.yml`

**Step 1: Check running containers**

Run: `docker compose -f docker-compose.dev.yml ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || docker compose ps`
Expected: qdrant, redis, litellm running

**Step 2: Check Qdrant collections**

Run: `curl -s localhost:6333/collections 2>/dev/null | jq -r '.result.collections[].name' || echo "Qdrant not reachable"`
Expected: `contextual_bulgaria_voyage` (and possibly `*_binary`, `*_scalar`)

**Step 3: Check Redis config**

Run: `docker exec dev-redis redis-cli CONFIG GET maxmemory-policy 2>/dev/null || echo "Redis not reachable"`
Expected: `volatile-lfu`

---

## Phase 2: Wave 1 Verification (Infrastructure)

### Task 2.1: Milestone A — Infrastructure & Safety

**Files:**
- Check: `src/config/settings.py`
- Check: `src/core/cache_service.py`

**Step 1: Verify lazy get_settings()**

Run: `grep -n "def get_settings" src/config/settings.py | head -5`
Expected: Function exists

**Step 2: Verify feature flags exist**

Run: `grep -E "(quantization_mode|small_to_big_mode|acorn_mode|use_hyde|use_contextualized)" src/config/settings.py | head -20`
Expected: All 5 flag types present

**Step 3: Verify Redis connection pool**

Run: `grep -n "redis_client\|connection_pool\|ConnectionPool" src/core/cache_service.py 2>/dev/null || grep -rn "redis_client" src/ --include="*.py" | head -5`
Expected: Shared redis client pattern

---

### Task 2.2: Milestone A.0 — Docs Consolidation

**Files:**
- Check: `tests/README.md`
- Check: `tests/` directory structure

**Step 1: Verify tests/README.md exists**

Run: `head -30 tests/README.md 2>/dev/null || echo "tests/README.md not found"`
Expected: Documentation of test structure

**Step 2: Verify test consolidation**

Run: `ls tests/*.py 2>/dev/null | grep -v conftest || echo "Only conftest.py remains (correct)"`
Expected: Only `conftest.py` in root, tests in subdirectories

**Step 3: Verify test subdirectories**

Run: `ls -d tests/*/ 2>/dev/null | head -10`
Expected: `tests/unit/`, `tests/integration/`, `tests/benchmark/`, etc.

---

### Task 2.3: Milestone A.2 — Test Data & Indexing

**Files:**
- Check: `tests/data/archive/`
- Check: `tests/eval/ground_truth.json`

**Step 1: Verify archived golden test set**

Run: `ls tests/data/archive/*ukrainian* 2>/dev/null || echo "Archive not found"`
Expected: `golden_test_set_ukrainian_criminal_code.json`

**Step 2: Verify new evaluation dataset**

Run: `cat tests/eval/ground_truth.json 2>/dev/null | jq 'length' || echo "ground_truth.json not found"`
Expected: 55 (Q&A pairs)

**Step 3: Verify Qdrant collection data**

Run: `curl -s localhost:6333/collections/contextual_bulgaria_voyage 2>/dev/null | jq '.result.points_count' || echo "Collection not found"`
Expected: 192

---

## Phase 3: Wave 2 Verification (Core Features)

### Task 3.1: Milestone A.1 — Langfuse Integration

**Files:**
- Check: `src/core/query_preprocessor.py`
- Check: `src/core/cache_service.py`

**Step 1: Verify @observe decorators**

Run: `grep -rn "@observe" src/ --include="*.py" | head -10`
Expected: Decorators in QueryPreprocessor, CacheService

**Step 2: Verify baseline targets in Makefile**

Run: `grep -E "baseline-smoke|baseline-report" Makefile | head -5`
Expected: Both targets exist

---

### Task 3.2: Milestone B — Binary Quantization

**Files:**
- Check: `src/config/settings.py`
- Check: `scripts/test_quantization_ab.py`

**Step 1: Verify quantization flags**

Run: `grep -E "quantization_mode|quantization_rescore|quantization_oversampling" src/config/settings.py`
Expected: All 3 settings present

**Step 2: Verify A/B script exists**

Run: `ls scripts/test_quantization_ab.py 2>/dev/null && echo "EXISTS" || echo "NOT FOUND"`
Expected: EXISTS

**Step 3: Verify binary collection exists**

Run: `curl -s localhost:6333/collections 2>/dev/null | jq -r '.result.collections[].name' | grep -E "(binary|scalar)" || echo "No quantized collections"`
Expected: At least one quantized collection (or note if intentionally not created yet)

---

### Task 3.3: Milestone C — Small-to-big Expansion

**Files:**
- Check: `src/config/settings.py`
- Check: `tests/unit/test_small_to_big.py`

**Step 1: Verify small-to-big flags**

Run: `grep -E "small_to_big_mode|small_to_big_window|max_expanded_chunks|max_context_tokens" src/config/settings.py`
Expected: All 5 settings present

**Step 2: Verify tests exist**

Run: `pytest tests/unit/test_small_to_big.py --collect-only 2>&1 | grep -E "test session|collected" | head -3`
Expected: Tests collected

**Step 3: Run tests**

Run: `pytest tests/unit/test_small_to_big.py -v 2>&1 | tail -15`
Expected: All pass

---

### Task 3.4: Milestone F — RAG Evaluation

**Files:**
- Check: `tests/eval/ground_truth.json`
- Check: `src/evaluation/` or `src/core/evaluation.py`

**Step 1: Verify evaluation dataset**

Run: `cat tests/eval/ground_truth.json 2>/dev/null | jq '.[0] | keys' || echo "Dataset not found"`
Expected: Keys like `question`, `answer`, `context`

**Step 2: Verify eval-rag target**

Run: `grep "eval-rag" Makefile | head -3`
Expected: Target exists

**Step 3: Verify DeepEval/Ragas in dependencies**

Run: `grep -E "deepeval|ragas" pyproject.toml | head -5`
Expected: At least one present

---

### Task 3.5: Milestone I — Alerting Pipeline

**Files:**
- Check: `docker/monitoring/`
- Check: `docs/ALERTING.md`

**Step 1: Verify monitoring configs**

Run: `ls docker/monitoring/*.yaml 2>/dev/null || ls docker/monitoring/*.yml 2>/dev/null || echo "No monitoring configs"`
Expected: promtail, loki, alertmanager configs

**Step 2: Verify alert rules**

Run: `ls docker/monitoring/rules/ 2>/dev/null || ls docker/monitoring/alerts/ 2>/dev/null || find docker/monitoring -name "*.yaml" -exec grep -l "alert:" {} \; 2>/dev/null | head -5`
Expected: Alert rule files

**Step 3: Verify ALERTING.md**

Run: `head -20 docs/ALERTING.md 2>/dev/null || echo "ALERTING.md not found"`
Expected: Documentation exists

**Step 4: Verify Make targets**

Run: `grep -E "monitoring-up|monitoring-down|monitoring-test-alert" Makefile | head -5`
Expected: All 3 targets

---

## Phase 4: Wave 3 Verification (Advanced Features)

### Task 4.1: Milestone D — ACORN

**Files:**
- Check: `src/config/settings.py`
- Check: `tests/unit/test_acorn.py`

**Step 1: Verify ACORN flags**

Run: `grep -E "acorn_mode|acorn_max_selectivity|acorn_enabled_selectivity" src/config/settings.py`
Expected: All 3 settings

**Step 2: Verify test count**

Run: `pytest tests/unit/test_acorn.py --collect-only 2>&1 | grep -E "collected|test session" | head -3`
Expected: ~28 tests collected

**Step 3: Run tests**

Run: `pytest tests/unit/test_acorn.py -v 2>&1 | tail -20`
Expected: All pass

---

### Task 4.2: Milestone G — HyDE

**Files:**
- Check: `src/core/hyde.py` or similar
- Check: `tests/unit/test_hyde.py`

**Step 1: Verify HyDE implementation**

Run: `grep -rn "class HyDEGenerator\|class HyDE\|def generate_hypothetical" src/ --include="*.py" | head -5`
Expected: HyDE class/function found

**Step 2: Verify HyDE flags**

Run: `grep -E "use_hyde|hyde_min_words" src/config/settings.py`
Expected: Both settings

**Step 3: Verify test count**

Run: `pytest tests/unit/test_hyde.py --collect-only 2>&1 | grep -E "collected|test session" | head -3`
Expected: ~35 tests collected

**Step 4: Run tests**

Run: `pytest tests/unit/test_hyde.py -v 2>&1 | tail -20`
Expected: All pass

---

### Task 4.3: Milestone H — Guardrails

**Files:**
- Check: `src/core/llm_service.py` or `src/services/llm.py`
- Check: `tests/unit/test_guardrails.py`
- Check: `tests/chaos/`

**Step 1: Verify confidence scoring**

Run: `grep -rn "LOW_CONFIDENCE_THRESHOLD\|create_low_confidence_response" src/ --include="*.py" | head -5`
Expected: Both found

**Step 2: Verify off-topic detection**

Run: `grep -rn "is_off_topic\|get_off_topic_response" src/ --include="*.py" | head -5`
Expected: Both found

**Step 3: Verify guardrails tests**

Run: `pytest tests/unit/test_guardrails.py --collect-only 2>&1 | grep -E "collected" | head -3`
Expected: ~52 tests

**Step 4: Verify chaos tests**

Run: `pytest tests/chaos/ --collect-only 2>&1 | grep -E "collected" | head -3`
Expected: ~40 tests

**Step 5: Run chaos tests**

Run: `pytest tests/chaos/ -v 2>&1 | tail -20`
Expected: All pass

---

### Task 4.4: Milestone J — Ingestion Pipeline

**Files:**
- Check: `src/ingestion/service.py`
- Check: `src/ingestion/cocoindex_flow.py`
- Check: `src/ingestion/docling_client.py`
- Check: `docs/INGESTION.md`

**Step 1: Verify ingestion service**

Run: `ls src/ingestion/*.py 2>/dev/null | head -10`
Expected: service.py, cocoindex_flow.py, docling_client.py

**Step 2: Verify INGESTION.md**

Run: `head -20 docs/INGESTION.md 2>/dev/null || echo "INGESTION.md not found"`
Expected: Documentation exists

**Step 3: Verify Make targets**

Run: `grep -E "ingest-setup|ingest-run|ingest-status" Makefile | head -5`
Expected: All 3 targets

**Step 4: Verify ingestion tests**

Run: `pytest tests/unit/test_ingestion*.py --collect-only 2>&1 | grep -E "collected" | head -3`
Expected: ~40 tests

---

## Phase 5: Wave 4 Verification (R&D)

### Task 5.1: Milestone E — Contextualized Embeddings

**Files:**
- Check: `src/core/contextualized_embeddings.py` or similar
- Check: `docs/CONTEXTUALIZED_EMBEDDINGS.md`
- Check: `scripts/test_contextualized_ab.py`

**Step 1: Verify ContextualizedEmbeddingService**

Run: `grep -rn "class ContextualizedEmbedding\|voyage-context-3" src/ --include="*.py" | head -5`
Expected: Implementation found

**Step 2: Verify flags**

Run: `grep -E "use_contextualized_embeddings|contextualized_embedding_dim" src/config/settings.py`
Expected: Both settings

**Step 3: Verify documentation**

Run: `head -20 docs/CONTEXTUALIZED_EMBEDDINGS.md 2>/dev/null || echo "Doc not found"`
Expected: Documentation exists

**Step 4: Verify A/B script**

Run: `ls scripts/test_contextualized_ab.py 2>/dev/null && echo "EXISTS" || echo "NOT FOUND"`
Expected: EXISTS

**Step 5: Verify test count**

Run: `pytest tests/unit/test_contextualized*.py tests/integration/test_contextualized*.py --collect-only 2>&1 | grep -E "collected" | head -3`
Expected: ~43 tests

**Step 6: Run tests**

Run: `pytest tests/unit/test_contextualized*.py tests/integration/test_contextualized*.py -v 2>&1 | tail -30`
Expected: All pass

---

## Phase 6: Integration & Known Issues

### Task 6.1: End-to-End Query Test

**Files:**
- Check: Bot health endpoint

**Step 1: Check bot health (if available)**

Run: `make test-bot-health 2>&1 | head -10 || echo "No test-bot-health target"`
Expected: Health check passes or target documented

**Step 2: Manual Qdrant query test**

Run: `curl -s -X POST "http://localhost:6333/collections/contextual_bulgaria_voyage/points/search" -H "Content-Type: application/json" -d '{"vector": [0.1] * 1024, "limit": 1}' 2>/dev/null | jq '.status' || echo "Query test skipped"`
Expected: `ok` or informative error

---

### Task 6.2: Known Issues Review

**Files:**
- Check: `docs/plans/2026-02-02-rag-2026-swarm-execution.md` (Known Issues section)

**Step 1: Check pre-existing test failures**

Run: `make test 2>&1 | grep -E "FAILED|ERROR" | head -10 || echo "No failures"`
Expected: Only pre-existing failures (if any) documented in plan

**Step 2: Check MyPy mlflow issue**

Run: `make check 2>&1 | grep -i mlflow | head -5 || echo "No mlflow issues"`
Expected: External dependency issue (not our code)

**Step 3: Check Python version**

Run: `grep -E "python.*3.11|requires-python" pyproject.toml | head -3`
Expected: Python >= 3.11 (CocoIndex requirement)

---

## Phase 7: Generate Report

### Task 7.1: Compile Audit Report

**Files:**
- Create: `docs/plans/2026-02-03-rag-2026-audit-report.md`

**Step 1: Create report from findings**

Compile all results from Phases 1-6 into report using this template:

```markdown
# RAG 2026 Audit Report — 2026-02-03

## Summary
- Tests: X/Y pass
- Lint: PASS/FAIL
- Feature Flags: X/15 implemented
- Documentation: X/4 complete
- Integration: X/4 working

## Phase Results

### Phase 1: Health Check
- Tests: [result]
- Lint: [result]
- Docker: [result]

### Phase 2-5: Milestone Verification
[Results per milestone]

### Phase 6: Integration
[E2E results]

## Issues Found
| # | Severity | Milestone | Description | Status |
|---|----------|-----------|-------------|--------|

## Recommendations
1. ...

## Conclusion
[ ] PASS — All criteria met
[ ] PASS WITH NOTES — Minor issues
[ ] FAIL — Critical issues found
```

**Step 2: Commit report**

Run: `git add docs/plans/2026-02-03-rag-2026-audit-report.md && git commit -m "docs: add RAG 2026 audit report"`

---

## Summary

| Phase | Tasks | Focus |
|-------|-------|-------|
| 1 | 1.1-1.3 | Quick health check |
| 2 | 2.1-2.3 | Wave 1 (Infrastructure) |
| 3 | 3.1-3.5 | Wave 2 (Core Features) |
| 4 | 4.1-4.4 | Wave 3 (Advanced Features) |
| 5 | 5.1 | Wave 4 (R&D) |
| 6 | 6.1-6.2 | Integration & Known Issues |
| 7 | 7.1 | Generate Report |

**Total:** 18 tasks, ~40 verification steps

---

## Execution Notes

- Run sequentially — later phases depend on earlier findings
- Document every unexpected result
- If tests fail, note which ones and check against Known Issues
- If file not found, check alternate locations before marking as missing
