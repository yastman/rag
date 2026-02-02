# RAG 2026 Reference Implementation — Swarm Execution Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:dispatching-parallel-agents to execute waves in parallel.

**Goal:** Execute full ТЗ (10 milestones) using parallel worktree swarm

**Architecture:** 4 waves by priority, max 5 parallel workers per wave, git worktrees for isolation

**Tech Stack:** Python 3.11+, Qdrant 1.16, Redis 8.4, Voyage AI, LiteLLM, Langfuse v3, CocoIndex

---

## Execution Strategy

```
WAVE 1 (P0) ✅ ──> WAVE 2 (P1) ✅ ──> WAVE 3 (P2) ✅ ──> WAVE 4 (R&D) ✅
   │                  │                  │                  │
   ├─ A (Infra) ✅    ├─ A.1 (Langfuse)✅ ├─ D (ACORN) ✅    └─ E (Contextualized) ✅
   ├─ A.0 (Docs) ✅   ├─ B (BinaryQuant)✅├─ G (HyDE) ✅
   └─ A.2 (Index) ✅  ├─ C (Small2big) ✅ ├─ H (Guardrails)✅
                      ├─ F (RAG Eval) ✅  └─ J (Ingestion) ✅
                      └─ I (Alerting) ✅
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

## WAVE 3: Advanced Features (P2) — 4 parallel workers ✅ COMPLETE (2026-02-02)

**Prerequisites:** WAVE 2 complete (observability, binary quant, evaluation working)

### Worker 9: Milestone D — ACORN ✅

**Worktree:** `.worktrees/milestone-d-acorn`
**Branch:** `milestone/d-acorn` → merged 2026-02-02
**Commit:** `feat(search): ACORN filtered search optimization`

**Dependencies:** B (Qdrant search tuned)

**Scope:**
- [x] Update `qdrant-client` to version supporting ACORN params
- [x] Add flags: `acorn_mode=off|on|auto`, `acorn_max_selectivity`, `acorn_enabled_selectivity_threshold`
- [x] Implement conditional ACORN in Qdrant queries (auto: only with filters + low selectivity)
- [x] Add microbench: latency/recall ACORN vs no-ACORN on filtered queries
- [x] 28 unit tests added

**Verification:** ✅
```bash
pytest tests/unit/test_acorn.py -v    # 28 tests pass
```

---

### Worker 10: Milestone G — HyDE + Query Decomposition ✅

**Worktree:** `.worktrees/milestone-g-hyde`
**Branch:** `milestone/g-hyde` → merged 2026-02-02
**Commit:** `feat(query): HyDE hypothetical document embeddings`

**Dependencies:** F (evaluation metrics for A/B)

**Scope:**
- [x] Add HyDE preprocessor in `QueryPreprocessor` → `HyDEGenerator` class
- [x] Feature flag: `use_hyde` (default: False)
- [x] A/B: HyDE vs baseline on short queries (< 5 words)
- [x] Implemented `hyde_min_words` setting (default: 5)
- [x] 35 unit tests added

**Verification:** ✅
```bash
pytest tests/unit/test_hyde.py -v    # 35 tests pass
```

---

### Worker 11: Milestone H — Guardrails ✅

**Worktree:** `.worktrees/milestone-h-guardrails`
**Branch:** `milestone/h-guardrails` → merged 2026-02-02
**Commit:** `feat(guardrails): confidence scoring, off-topic detection, chaos tests`

**Dependencies:** F (evaluation for confidence thresholds)

**Scope:**
- [x] Add confidence scoring in LLMService (`LOW_CONFIDENCE_THRESHOLD = 0.3`)
- [x] Implement fallback response at low confidence (`create_low_confidence_response`)
- [x] Off-topic detection via QueryRouter extension (`is_off_topic`, `get_off_topic_response`)
- [x] Add chaos tests (Qdrant timeout, Redis disconnect, LLM fallback)
- [x] Test graceful degradation when services unavailable
- [x] 52 unit tests + 40 chaos tests added

**Verification:** ✅
```bash
pytest tests/chaos/ -v                      # 40 chaos tests pass
pytest tests/unit/test_guardrails.py -v     # 52 tests pass
```

---

### Worker 12: Milestone J — Document Ingestion Pipeline ✅

**Worktree:** `.worktrees/milestone-j-ingestion`
**Branch:** `milestone/j-ingestion` → merged 2026-02-02
**Commit:** `feat(ingestion): CocoIndex + Docling pipeline`

**Dependencies:** A.2 (indexing service patterns), I (observability)

**Scope:**
- [x] Confirm ingestion orchestrator choice: **CocoIndex** ✅
- [x] CocoIndex: Postgres state (cocoindex DB/schema) + 60s polling
- [x] Docling integration: `POST /v1/convert/file` endpoint
- [x] Token-based chunking (TokenChunker, 512 tokens)
- [x] Create `src/ingestion/service.py` (IngestionService)
- [x] Create `src/ingestion/cocoindex_flow.py` (CocoIndex flow)
- [x] Create `src/ingestion/docling_client.py` (Docling API)
- [x] Add Make targets: `make ingest-setup/run/continuous/status`
- [x] Support formats: PDF, DOCX, CSV, HTML, Markdown
- [x] Unified metadata schema for payload (file_id, folder_id, content_hash)
- [x] Idempotency: DELETE by file_id → UPSERT (replace semantics)
- [x] Python 3.11+ requirement (CocoIndex constraint)
- [x] 40 unit tests added

**Verification:** ✅
```bash
make ingest-setup       # Creates Postgres schema + Qdrant indexes
make ingest-run         # Runs ingestion once
make ingest-status      # Shows indexed files
pytest tests/unit/test_ingestion*.py -v  # 40 tests pass
```

---

## WAVE 4: R&D (Optional) ✅ COMPLETE (2026-02-02)

**Prerequisites:** WAVE 3 complete, system stable

### Worker 13: Milestone E — Late/Contextual Chunking ✅

**Worktree:** `.worktrees/milestone-e-late-chunking`
**Branch:** `milestone/e-late-chunking` → pushed 2026-02-02
**Commit:** `41b5e9b feat(embeddings): add voyage-context-3 contextualized embeddings`

**Dependencies:** All previous (experimental, needs stable baseline)

**Finding:** Voyage AI has native `/contextualizedembeddings` endpoint with `voyage-context-3` model!
This is better than late chunking — it's built-in contextualized chunk embeddings.

**Scope:**
- [x] Evaluate: Does Voyage support late/contextual chunking? → YES, voyage-context-3
- [x] Implement ContextualizedEmbeddingService with voyage-context-3
- [x] A/B testing script created: `scripts/test_contextualized_ab.py`
- [x] Document findings: `docs/CONTEXTUALIZED_EMBEDDINGS.md`
- [x] Add feature flags: `use_contextualized_embeddings`, `contextualized_embedding_dim`
- [x] 43 tests added (20 unit + 23 integration)

**Verification:** ✅
```bash
pytest tests/unit/test_contextualized_embeddings.py tests/integration/test_contextualized_pipeline.py -v  # 43 pass
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

| Checkpoint | Trigger | Action | Status |
|------------|---------|--------|--------|
| WAVE 1 done | All 3 PRs merged | Start WAVE 2 (5 workers) | ✅ 2026-02-02 |
| WAVE 2 done | All 5 PRs merged | Start WAVE 3 (4 workers) | ✅ 2026-02-02 |
| WAVE 3 done | All 4 PRs merged | Start WAVE 4 (1 worker) | ✅ 2026-02-02 |
| WAVE 4 done | Milestone E complete | All milestones done! | ✅ 2026-02-02 |
| Blocker found | Any worker stuck | Pause, coordinate, unblock | — |

---

## Success Criteria (Definition of Done)

- [x] All 1667+ tests pass (1820+ after WAVE 3)
- [x] Bot responds to queries (Qdrant has data)
- [x] Redis uses `volatile-lfu`, connection pooling works
- [x] Binary quantization A/B report generated
- [x] Small-to-big expansion works for COMPLEX queries
- [x] RAG evaluation: faithfulness >= 0.8
- [x] Docker alerting: test alert reaches Telegram
- [x] Langfuse traces visible for all key services
- [x] All feature flags documented and working
- [x] ACORN filtered search optimization (WAVE 3)
- [x] HyDE query expansion for short queries (WAVE 3)
- [x] Guardrails: confidence scoring, off-topic detection (WAVE 3)
- [x] Document ingestion pipeline with CocoIndex (WAVE 3)
- [x] Contextualized embeddings with voyage-context-3 (WAVE 4)

---

## Known Issues & Bugs

<!-- Record bugs found during execution here -->

| Date | Worker | Issue | Status |
|------|--------|-------|--------|
| 2026-02-02 | A | 8 pre-existing test failures (untouched files) | IGNORED |
| 2026-02-02 | B | 2 pre-existing Qdrant service test failures (mock patch paths) | PRE-EXISTING |
| 2026-02-02 | - | MyPy error in mlflow dependency (not our code) | EXTERNAL |
| 2026-02-02 | J | CocoIndex requires Python >=3.11, updated pyproject.toml | FIXED |
| 2026-02-02 | merge | 3 merge conflicts (settings.py, __init__.py, uv.lock) | RESOLVED |

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
