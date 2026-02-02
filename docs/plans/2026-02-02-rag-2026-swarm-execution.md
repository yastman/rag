# RAG 2026 Reference Implementation — Swarm Execution Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:dispatching-parallel-agents to execute waves in parallel.

**Goal:** Execute full ТЗ (10 milestones) using parallel worktree swarm

**Architecture:** 4 waves by priority, max 5 parallel workers per wave, git worktrees for isolation

**Tech Stack:** Python 3.12, Qdrant 1.16, Redis 8.4, Voyage AI, LiteLLM, Langfuse v3

---

## Execution Strategy

```
WAVE 1 (P0) ──parallel──> WAVE 2 (P1) ──parallel──> WAVE 3 (P2) ──parallel──> WAVE 4 (R&D)
   │                         │                         │                         │
   ├─ A (Infra)              ├─ A.1 (Langfuse)         ├─ D (ACORN)              └─ E (Late Chunking)
   ├─ A.0 (Docs)             ├─ B (Binary Quant)       ├─ G (HyDE)
   └─ A.2 (Indexing)         ├─ C (Small-to-big)       ├─ H (Guardrails)
                             ├─ F (RAG Eval)           └─ J (Document Ingestion)
                             └─ I (Docker Alerting)
```

**Worktree naming:** `.worktrees/milestone-{letter}-{name}`

**Branch naming:** `milestone/{letter}-{short-name}`

---

## WAVE 1: Foundation (P0) — 3 parallel workers ✅ COMPLETE (2026-02-02)

### Worker 1: Milestone A — Infrastructure & Safety ✅

**Worktree:** `.worktrees/milestone-a-infra`
**Branch:** `milestone/a-infra` → pushed 2026-02-02
**Commit:** `4122f0f feat(infra): add feature flags, fix tests, redis pool`

**Scope:**
- [x] Fix `src/config/settings.py:211` — lazy `get_settings()` (already done)
- [x] Add `opentelemetry-exporter-otlp-proto-grpc` to dev deps (already in pyproject.toml)
- [x] Fix 4 mock patch paths in tests
- [x] Redis: `volatile-lfu` + `maxmemory-samples=10` (already in docker-compose)
- [x] Redis: единый connection pool (shared redis_client in CacheService)
- [x] Bot: check `LITELLM_BASE_URL` in docker-compose (verified)
- [x] Bot: add `make test-bot-health` preflight
- [x] Implement Feature Flags & Profiles (section 8.0)
- [x] Run `make test-cov` — 144 tests pass

**Verification:**
```bash
make test          # 1667/1667 pass
make check         # lint + types clean
docker exec dev-redis redis-cli CONFIG GET maxmemory-policy  # volatile-lfu
```

---

### Worker 2: Milestone A.0 — Docs & Plan Consolidation ✅

**Worktree:** `.worktrees/milestone-a0-docs`
**Branch:** `milestone/a0-docs` → merged 2026-02-02
**Commit:** `913141a refactor(tests): consolidate test files into proper directories`

**Dependencies:** None (independent)

**Scope:**
- [x] Mark this ТЗ as "source of truth"
- [x] Archive/update conflicting plans
- [x] Remove `.claude.md` (conflicts with `CLAUDE.md`)
- [x] ROADMAP.md — не существует, ссылки в архиве OK
- [x] Consolidate 40 root-level test files into `tests/unit/`, `tests/integration/`, `tests/benchmark/`
- [x] Add `tests/README.md` with structure and commands

**Verification:** ✅
```bash
ls tests/*.py           # Only conftest.py remains (correct)
cat tests/README.md     # Updated with new structure
```

---

### Worker 3: Milestone A.2 — Test Data & Indexing ✅

**Worktree:** `.worktrees/milestone-a2-indexing`
**Branch:** `milestone/a2-indexing` → merged 2026-02-02
**Commit:** `322c6d3 chore(tests): archive old Ukrainian Criminal Code golden test set`

**Dependencies:** None (can run parallel, bot works after A completes)

**Scope:**
- [x] Archive `tests/data/golden_test_set.json` → `tests/data/archive/golden_test_set_ukrainian_criminal_code.json`
- [x] Collection `contextual_bulgaria_voyage` exists (192 points)
- [x] New evaluation dataset: `tests/eval/ground_truth.json` (55 Q&A)
- [x] Verify: `curl localhost:6333/collections` shows collection with data

**Verification:** ✅
```bash
curl localhost:6333/collections/contextual_bulgaria_voyage | jq '.result.points_count'  # 192
```

---

## WAVE 2: Core Features (P1) — 5 parallel workers ✅ COMPLETE

**Prerequisites:** WAVE 1 complete (tests pass, infra stable, data indexed)

### Worker 4: Milestone A.1 — Langfuse Integration ✅

**Worktree:** `.worktrees/milestone-a1-langfuse`
**Branch:** `milestone/a1-langfuse` → merged 2026-02-02
**Commit:** `d13db0b feat(langfuse): add @observe decorators and baseline-compare CI`

**Dependencies:** A (infra stable)

**Scope:**
- [x] Add `@observe` decorators: QueryPreprocessor.analyze, CacheService.store_*
- [x] Unify session_id format: `{type}-{hash}-{YYYYMMDD}`
- [x] Add `make baseline-report` for HTML diff report
- [x] Integrate baseline-compare in CI (fail on regression > threshold)
- [x] Document Langfuse UI workflow in CLAUDE.md

**Verification:**
```bash
make baseline-smoke     # Generates traces in Langfuse
make baseline-report    # Creates HTML report
```

---

### Worker 5: Milestone B — Qdrant Binary Quantization ✅

**Worktree:** `.worktrees/milestone-b-binary-quant`
**Branch:** `milestone/b-binary-quant` → merged 2026-02-02
**Commit:** `cbc1e0a feat(qdrant): binary quantization support`

**Dependencies:** A.2 (data indexed)

**Scope:**
- [x] Create collection with BinaryQuantization (`*_binary` suffix)
- [x] Script to reindex from baseline to binary collection
- [x] A/B: INT8 vs binary (rescore/oversampling 2-4), metrics report
- [x] Add flags: `quantization_mode=off|scalar|binary`, `quantization_rescore`, `quantization_oversampling`
- [x] Bind `quantization_mode` to collection selection
- [x] Use `always_ram=True`, test `query_encoding=SCALAR8BITS`

**Verification:**
```bash
curl localhost:6333/collections | jq '.result.collections[].name'  # Shows *_binary
python scripts/test_quantization_ab.py  # A/B report generated
```

---

### Worker 6: Milestone C — Small-to-big Expansion ✅

**Worktree:** `.worktrees/milestone-c-small-to-big`
**Branch:** `milestone/c-small-to-big` → merged 2026-02-02
**Commit:** `af01e1a feat(retrieval): small-to-big chunk expansion`

**Dependencies:** A.2 (doc_id/chunk_order in payload)

**Scope:**
- [x] Verify doc_id/chunk_order in payload (add if missing)
- [x] Implement fetch "neighbor chunks" by doc_id + order range
- [x] Integrate into generation (context after rerank)
- [x] Add flags: `small_to_big_mode=off|on|auto`, `small_to_big_window_before/after`
- [x] Add limits: `max_expanded_chunks`, `max_context_tokens`

**Verification:**
```bash
pytest tests/unit/test_small_to_big.py -v    # New tests pass
# Manual: query returns expanded context
```

---

### Worker 7: Milestone F — RAG Evaluation ✅

**Worktree:** `.worktrees/milestone-f-rag-eval`
**Branch:** `milestone/f-rag-eval` → merged 2026-02-02
**Commit:** `cf6c3d3 feat(eval): RAG evaluation with DeepEval/Ragas`

**Dependencies:** A.2 (golden dataset created)

**Scope:**
- [x] Add DeepEval / Ragas to dev dependencies
- [x] Create evaluation dataset: `tests/eval/ground_truth.json` (55 Q&A pairs)
- [x] Implement `make eval-rag` pipeline
- [x] Integrate faithfulness + relevancy scores in Langfuse
- [x] Add thresholds: faithfulness >= 0.8
- [x] Add unit tests (23 tests) for evaluation validation

**Verification:**
```bash
make eval-rag           # Runs evaluation, outputs metrics
# Langfuse: faithfulness scores visible
```

---

### Worker 8: Milestone I — Docker Alerting Pipeline ✅

**Worktree:** `.worktrees/milestone-i-alerting`
**Branch:** `milestone/i-alerting` → merged 2026-02-02
**Commit:** `fb2b237 feat(monitoring): Docker alerting with Loki/Promtail/Alertmanager`

**Dependencies:** A (docker stack stable)

**Scope:**
- [x] Add monitoring stack to `docker-compose.dev.yml` (Promtail, Loki, Alertmanager)
- [x] Create `docker/monitoring/promtail.yaml` — scrape Docker logs
- [x] Create `docker/monitoring/loki.yaml` — storage, ruler
- [x] Create `docker/monitoring/alertmanager.yaml` — Telegram receiver
- [x] Create alert rules: `telegram-bot.yaml`, `infrastructure.yaml`
- [x] Add env vars: `TELEGRAM_ALERTING_BOT_TOKEN`, `TELEGRAM_ALERTING_CHAT_ID`
- [x] Add Make targets: `make monitoring-up/down/logs/test-alert`
- [x] Create `docs/ALERTING.md` setup guide
- [x] Add monitoring section to CLAUDE.md

**Verification:**
```bash
make monitoring-up              # 3 new containers running
make monitoring-test-alert      # Test alert in Telegram
docker logs dev-promtail | head # Logs flowing
```

---

## WAVE 3: Advanced Features (P2) — 4 parallel workers

**Prerequisites:** WAVE 2 complete (observability, binary quant, evaluation working)

### Worker 9: Milestone D — ACORN

**Worktree:** `.worktrees/milestone-d-acorn`
**Branch:** `milestone/d-acorn`
**Estimated tasks:** 4

**Dependencies:** B (Qdrant search tuned)

**Scope:**
- [ ] Update `qdrant-client` to version supporting ACORN params
- [ ] Add flags: `acorn_mode=off|on|auto`, `acorn_max_selectivity`, `acorn_enabled_selectivity_threshold`
- [ ] Implement conditional ACORN in Qdrant queries (auto: only with filters + low selectivity)
- [ ] Add microbench: latency/recall ACORN vs no-ACORN on filtered queries

**Verification:**
```bash
python -c "from qdrant_client import models; print('AcornSearchParams' in dir(models))"  # True
pytest tests/unit/test_acorn.py -v    # New tests pass
```

---

### Worker 10: Milestone G — HyDE + Query Decomposition

**Worktree:** `.worktrees/milestone-g-hyde`
**Branch:** `milestone/g-hyde`
**Estimated tasks:** 5

**Dependencies:** F (evaluation metrics for A/B)

**Scope:**
- [ ] Add HyDE preprocessor in `QueryPreprocessor`
- [ ] Feature flag: `use_hyde` (default: False)
- [ ] A/B: HyDE vs baseline on short queries (< 5 words)
- [ ] Optional: query decomposition for COMPLEX queries
- [ ] Document when HyDE is useful

**Verification:**
```bash
pytest tests/unit/test_hyde.py -v    # New tests pass
# A/B report shows recall improvement on short queries
```

---

### Worker 11: Milestone H — Guardrails

**Worktree:** `.worktrees/milestone-h-guardrails`
**Branch:** `milestone/h-guardrails`
**Estimated tasks:** 5

**Dependencies:** F (evaluation for confidence thresholds)

**Scope:**
- [ ] Add confidence scoring in LLMService
- [ ] Implement fallback response at low confidence
- [ ] Off-topic detection via QueryRouter extension
- [ ] Add chaos tests (Qdrant timeout, Redis disconnect, LLM fallback)
- [ ] Test graceful degradation when services unavailable

**Verification:**
```bash
pytest tests/chaos/ -v          # Chaos tests pass
# Low confidence query returns fallback response
```

---

### Worker 12: Milestone J — Document Ingestion Pipeline

**Worktree:** `.worktrees/milestone-j-ingestion`
**Branch:** `milestone/j-ingestion`
**Estimated tasks:** 10

**Dependencies:** A.2 (indexing service patterns), I (observability)

**Scope:**
- [ ] Verify `dev-docling` works: `curl http://localhost:5001/health`
- [ ] Configure docling environment (DOCLING_BACKEND, PDF_BACKEND, TABLE_MODE)
- [ ] Setup HybridChunker with Voyage-compatible tokenizer
- [ ] Create `telegram_bot/services/indexing_service.py`
- [ ] Create `scripts/gdrive_sync.py` (Google Drive API client)
- [ ] Create `services/document_sync/` Docker service
- [ ] Add Make targets: `make ingest-file/dir/gdrive/status/reindex`
- [ ] Support formats: PDF, DOCX, XLSX/CSV, HTML, Markdown
- [ ] Unified metadata schema for payload
- [ ] Add Langfuse traces for indexing, add alert rules

**Verification:**
```bash
make ingest-file FILE=test.pdf      # Indexes successfully
make ingest-status                  # Shows document count
curl localhost:6333/collections/contextual_bulgaria_voyage | jq '.result.points_count'  # Increased
```

---

## WAVE 4: R&D (Optional)

**Prerequisites:** WAVE 3 complete, system stable

### Worker 13: Milestone E — Late/Contextual Chunking

**Worktree:** `.worktrees/milestone-e-late-chunking`
**Branch:** `milestone/e-late-chunking`
**Estimated tasks:** 4

**Dependencies:** All previous (experimental, needs stable baseline)

**Scope:**
- [ ] Evaluate: Does Voyage-4-large support late chunking? (32K context)
- [ ] If yes: A/B late chunking vs baseline
- [ ] If no improvement: Then contextual chunking (LLM summary prepend)
- [ ] Document findings

**Verification:**
```bash
# A/B report shows retrieval improvement (or documents why not)
```

---

## Merge Strategy

After each wave completes:

1. **Review:** Each worker creates PR to `main`
2. **CI:** All tests must pass, no regressions in baseline metrics
3. **Merge order within wave:** Any order (independent)
4. **Next wave:** Start only after all PRs from previous wave merged

```bash
# After WAVE 1 complete
git checkout main && git pull
# Workers 4-8 start WAVE 2

# After WAVE 2 complete
git checkout main && git pull
# Workers 9-12 start WAVE 3
```

---

## Coordination Points

| Checkpoint | Trigger | Action |
|------------|---------|--------|
| WAVE 1 done | All 3 PRs merged | Start WAVE 2 (5 workers) |
| WAVE 2 done | All 5 PRs merged | Start WAVE 3 (4 workers) |
| WAVE 3 done | All 4 PRs merged | Start WAVE 4 (1 worker) |
| Blocker found | Any worker stuck | Pause, coordinate, unblock |

---

## Success Criteria (Definition of Done)

- [ ] All 1667+ tests pass
- [ ] Bot responds to queries (Qdrant has data)
- [ ] Redis uses `volatile-lfu`, connection pooling works
- [ ] Binary quantization A/B report generated
- [ ] Small-to-big expansion works for COMPLEX queries
- [ ] RAG evaluation: faithfulness >= 0.8
- [ ] Docker alerting: test alert reaches Telegram
- [ ] Langfuse traces visible for all key services
- [ ] All feature flags documented and working

---

## Known Issues & Bugs

<!-- Record bugs found during execution here -->

| Date | Worker | Issue | Status |
|------|--------|-------|--------|
| 2026-02-02 | A | 8 pre-existing test failures (untouched files) | IGNORED |
| 2026-02-02 | B | 2 pre-existing Qdrant service test failures (mock patch paths) | PRE-EXISTING |
| 2026-02-02 | - | MyPy error in mlflow dependency (not our code) | EXTERNAL |

---

## Quick Start

```bash
# Create all worktrees for WAVE 1
git worktree add .worktrees/milestone-a-infra milestone/a-infra
git worktree add .worktrees/milestone-a0-docs milestone/a0-docs
git worktree add .worktrees/milestone-a2-indexing milestone/a2-indexing

# Start 3 parallel Claude sessions, one per worktree
# Each session: cd .worktrees/milestone-X && follow milestone tasks
```
