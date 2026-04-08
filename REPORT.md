# Issues Research Report

Research for: 858, 988, 1003, 1070, 1072-1077, 1081-1085, 1088-1095

**Branch:** `clawteam/issues-review/test-researcher`
**Date:** 2026-04-02
**Researcher:** test-researcher

---

## Summary Table

| # | Title | Category | Effort | Complexity | Status |
|---|-------|----------|--------|------------|--------|
| 858 | mypy silences 16 core modules | code-quality | HIGH | HIGH | OPEN |
| 988 | Residual VPS parity follow-ups | infra | MEDIUM | MEDIUM | OPEN |
| 1003 | Langfuse local-to-VPS migration | infra | HIGH | HIGH | OPEN |
| 1070 | PropertyBot monolith split (5000+ lines) | refactor | VERY HIGH | VERY HIGH | OPEN |
| 1072 | Bare `except Exception:` + magic numbers | code-quality | MEDIUM | MEDIUM | OPEN |
| 1073 | Dependency updates April 2026 | dependencies | LOW-MEDIUM | LOW-MEDIUM | OPEN |
| 1074 | compose.vps.yml broken overrides | docker | LOW | LOW | CLOSED |
| 1075 | Unused imports in `__init__.py` | code-quality | LOW | LOW | CLOSED |
| 1076 | Duplicate `convert_to_python_types` | code-quality | LOW | LOW | CLOSED |
| 1077 | Contextualization providers base class | refactor | MEDIUM | MEDIUM | OPEN |
| 1081 | PostgreSQL 7 crashes, WAL corruption | infra | MEDIUM | HIGH | OPEN |
| 1082 | ClickHouse IPv6 bind + 200s lock contention | infra | MEDIUM | MEDIUM | OPEN |
| 1083 | Qdrant telemetry failed + invalid vector name | infra | LOW | LOW | OPEN |
| 1084 | Sync k8s runtime config with compose | infra | LOW | LOW | MERGED |
| 1085 | File structure reorganization | cleanup | MEDIUM | LOW-MEDIUM | OPEN |
| 1088 | PropertyBot router handlers test coverage | test-coverage | HIGH | HIGH | OPEN |
| 1089 | LangGraph voice pipeline subgraph coverage | test-coverage | MEDIUM | MEDIUM | OPEN |
| 1090 | Kommo CRM error scenarios + edge cases | test-coverage | MEDIUM | MEDIUM | OPEN |
| 1091 | Ingestion/unified state_manager + pipeline | test-coverage | MEDIUM | HIGH | OPEN |
| 1092 | Caching layers coverage (Redis + Qdrant) | test-coverage | MEDIUM | MEDIUM | OPEN |
| 1093 | Dialogs FSM states + transitions coverage | test-coverage | MEDIUM | MEDIUM | OPEN |
| 1094 | HandoffData JSON → Pydantic serialization | SDK-audit | LOW | LOW | OPEN |
| 1095 | Consolidate duplicated retry decorators | SDK-audit | MEDIUM | LOW | OPEN |

---

## Detailed Analysis

### TEST COVERAGE ISSUES (1088–1093, 1094–1095)

#### 1088 — PropertyBot router handlers unit test coverage gap
**Problem:** `PropertyBot` is 5,013 lines / 100+ methods. Only indirect handler tests exist — the class itself and its key methods are untested.

**Coverage gaps:**
- Critical: `PropertyBot.start()` (518 lines, 15+ services), `_handle_query_supervisor` (798 lines, 5 phases), `handle_menu_button`, `_handle_apartment_fast_path`, `handle_service_callback`/`handle_cta_callback`
- High: PropertyBot FSM integration, `_build_agent_tools()`, `get_memory()`/`get_llm()`/`get_rag_pipeline()` DI, `handle_voice`, `handle_feedback`

**Approach:** After router extraction (#1070), each router tests in isolation. Before — integration tests at `dp.emit` level.

**Effort:** HIGH | **Complexity:** HIGH | **Dependency:** Blocks on #1070

**Key files:**
- `telegram_bot/bot.py` (5013 lines)
- `telegram_bot/handlers/` (command_handlers, menu_router, callback_router, supervisor_handler, voice_handler, feedback_handler, handoff_handler — proposed extraction)

---

#### 1089 — LangGraph voice pipeline subgraph integration coverage
**Problem:** 11-node LangGraph has isolated node tests but no full subgraph or parent graph orchestration coverage.

**Coverage gaps:**
- Voice subgraph: end-to-end execution, error propagation
- Query subgraph: rewrite → retrieve loop (max 3 iterations)
- Parent graph: full 11-node pipeline, RAGState transitions, conditional routing edges
- HITL: escalation and resume, state preservation

**Key files:**
- `telegram_bot/graph/graph.py` — `build_graph()` (11-node StateGraph)
- `telegram_bot/graph/state.py` — `RAGState` TypedDict (25 fields)
- `telegram_bot/graph/nodes/` — 9 node modules (guard, transcribe, classify, cache, retrieve, grade, rerank, generate, rewrite)

**Effort:** MEDIUM | **Complexity:** MEDIUM

---

#### 1090 — Kommo CRM error scenarios and edge cases
**Problem:** Kommo integration tests cover only the happy path.

**Coverage gaps:**
- Error handling: 401 (token refresh), 400 (malformed payload), 429 (rate limit backoff), 500 (retry), network timeout, `RuntimeError: No refresh_token`
- Lead operations: `create_lead`, `smart_upsert_lead`, `update_lead_status`, lead score sync
- OAuth flow: token refresh, token invalidation

**Key files:**
- `telegram_bot/services/kommo_client.py` — `KommoClient` (async httpx, OAuth2 auto-refresh on 401)
- `telegram_bot/services/kommo_token_store.py` — `KommoTokenStore` (Redis hash)
- `telegram_bot/services/kommo_models.py` — Pydantic v2 models

**Effort:** MEDIUM | **Complexity:** MEDIUM

---

#### 1091 — Ingestion/unified state_manager and pipeline coverage
**Problem:** Complex state management in unified ingestion pipeline has no full integration coverage.

**Coverage gaps:**
- StateManager: async/sync transitions, file state transitions (pending → processing → done/failed), race conditions, checkpoint persistence
- Unified flow: `unified/flow.py` end-to-end, manifest parsing/validation, target sync execution
- QdrantHybridWriter: dense + sparse embedding writes, ColBERT rerank backfill

**Effort:** MEDIUM | **Complexity:** HIGH

---

#### 1092 — Caching layers (Redis + Qdrant) cache policy coverage
**Problem:** Multi-level caching (Redis + Qdrant + memory) is critical for TTFT, but error scenarios and policy enforcement are untested.

**Coverage gaps:**
- CachePolicy: TTL enforcement, RRF guard threshold (~0.005)
- Redis: connection pool exhaustion, key eviction policies, cache key generation
- Qdrant: vector cache, cache invalidation

**Key files:**
- `telegram_bot/services/cache_policy.py`
- Existing: `tests/unit/services/test_cache_layers.py` (incomplete)

**Effort:** MEDIUM | **Complexity:** MEDIUM

---

#### 1093 — Dialogs FSM states and transitions coverage
**Problem:** Complex FSM logic in dialogs has many uncovered transition paths.

**Coverage gaps:**
- FSM states: all `Dialogs` enum states, `FunnelState`, `ManagerDialogs`, CRM sub-states
- Transition coverage: catalog → filter → results, settings language change, demo → catalog → client menu, handoff → manager → resume

**Key files:**
- `telegram_bot/dialogs/` — aiogram-dialog menus: crm_submenu, faq, filter_dialog, funnel, manager_menu, settings

**Effort:** MEDIUM | **Complexity:** MEDIUM

---

#### 1094 — HandoffData JSON → Pydantic serialization
**Problem:** `telegram_bot/services/handoff_state.py:36-59` uses manual `json.dumps`/`json.loads` for `qualification` field serialization instead of Pydantic v2.

**Current:**
```python
"qualification": json.dumps(self.qualification, ensure_ascii=False),
qualification=json.loads(raw.get("qualification", "{}")),
```

**Fix:** Replace with `model_dump_json()` / `model_validate()`.

**Effort:** LOW | **Complexity:** LOW

---

#### 1095 — Consolidate duplicated retry decorators
**Problem:** Two identical tenacity retry decorator definitions:
- `telegram_bot/services/kommo_client.py:52-58` (`_kommo_retry`)
- `telegram_bot/services/bge_m3_client.py:41-47` (`_bge_retry`)

Both use: retry on transport errors + HTTP status codes, exponential backoff with jitter.

**Fix:** Shared module `telegram_bot/services/_retry.py` with common decorator factory. Tenacity already a dependency (`tenacity>=8.2.0`).

**Effort:** MEDIUM | **Complexity:** LOW

---

### SDK REFACTOR ISSUES (1070–1077, 858)

#### 1070 — PropertyBot monolith split (5000+ lines) — EPIC
**Problem:** `PropertyBot` is 5,013 lines, 100+ methods. Violates Single Responsibility. 188 bare `except Exception:`. Duplicate tool assembly in 3 places.

**Proposed Architecture (3 phases):**

**Phase 1 — Extract aiogram Routers:**
```
telegram_bot/
├── bot.py                      # PropertyBot (init, start/stop, wiring only)
├── handlers/
│   ├── command_handlers.py     # ~300 lines
│   ├── menu_router.py          # ~200 lines
│   ├── callback_router.py      # ~400 lines
│   ├── supervisor_handler.py   # ~850 lines
│   ├── voice_handler.py        # ~220 lines
│   ├── feedback_handler.py     # ~160 lines
│   └── handoff_handler.py     # ~180 lines
└── services/                   # 60+ files, already well-separated
```

**Phase 2 — LangGraph Subgraph Decomposition:**

| Subgraph | Nodes | Lines Saved |
|----------|-------|-------------|
| `voice_subgraph` | transcribe → guard → classify → cache → retrieve → grade → generate | ~400 |
| `query_subgraph` | rewrite → retrieve (loop) | ~200 |

**Phase 3 — FastAPI Microservices (optional):** webhook handler, background workers, bot query API.

**Effort:** VERY HIGH (epic) | **Complexity:** VERY HIGH | **Labels:** epic, P0-critical, refactor

**Dependencies:** Unblocks #1088 (test coverage)

---

#### 1072 — Eliminate bare `except Exception:` and scattered magic numbers
**Problem:** 188 bare `except Exception:` catches across `telegram_bot/` and `src/`. Magic numbers scattered.

**Bare except locations:**
- `observability.py`: 269, 278, 302, 316, 398, 432
- `error_handler.py`: 72, 80, 112, 123
- `rag_pipeline.py`: 257, 262, 650, 730, 827
- `agent.py`: multiple
- `src/voice/agent.py`: 278, 327, 359, 417, 476

**Magic numbers:**
- `_TELEGRAM_MESSAGE_LIMIT = 4096` in `bot.py:96` AND `pipelines/client.py:40` (duplicate)
- `_FEEDBACK_CONFIRMATION_TTL_S = 5.0` in `bot.py:98`
- `_APARTMENT_PAGE_SIZE = 5` in `bot.py:99`
- TTL values 3600, 86400 in `config.py:152,243,584`

**Global state issues:**
- `observability.py:338-340`: `global _langfuse_client`, `_langfuse_init_attempted`, `_langfuse_endpoint_warned`
- `session_summary.py:87`: `global _force_chat_completions_fallback`, `_compat_checked`

**Effort:** MEDIUM | **Complexity:** MEDIUM

---

#### 1073 — Dependency updates April 2026
**Problem:** Multiple dependency issues requiring attention.

**Critical Issues:**

1. **`voyageai>=0.3.0` is impossible** — latest is v0.1.7. `uv sync` may silently resolve to older version or fail.
   - Fix: `voyageai>=0.1.7`

2. **langfuse v3 → v4 (breaking)** — v4.0.4 released March 30, 2026
   - Smart default span filtering changed
   - `update_current_trace()` replaced by `propagate_attributes()` context manager
   - `start_span()`/`start_generation()` → `start_observation()` with `as_type`
   - `DatasetItemClient.run()` removed
   - Pydantic v1 support dropped
   - Recommendation: stay on v3, add upper bound `langfuse>=3.14.0,<4.0`

**Safe Updates:**
- `aiogram-dialog` 2.5.0 → 2.6.0 (small jump, likely compatible)
- `redis` 7.1.0 → 7.4.0 (minor, backwards compatible)
- `langgraph`/`langgraph-sdk` 1.0.8 → 1.1.4 (constraint allows)
- `fastapi` 0.128.8 → 0.135.2
- `livekit-agents` 1.4.1 → 1.5.0

**Effort:** LOW (immediate fixes) | **Complexity:** LOW (version pins), HIGH (langfuse v4 migration ~2-3 days)

---

#### 1077 — Contextualization providers base class extraction
**Problem:** `src/contextualization/claude.py`, `openai.py`, `groq.py` have 80% identical code:
- `contextualize()` loop pattern is identical
- `contextualize_single` retry/error handling is identical
- Token tracking and cost calculation duplicated

Tests also duplicated: `tests/unit/contextualization/test_claude.py`, `test_groq.py`, `test_openai.py` — fixture `contextualizer` is identical.

**Fix:**
1. Extract common logic into `ContextualizeProvider` base class
2. Keep only client, model, and response parsing in each provider
3. Create parameterized fixture in `tests/unit/contextualization/conftest.py`

**Effort:** MEDIUM | **Complexity:** MEDIUM

---

#### 858 — mypy silences 16 core modules with `ignore_errors=true`
**Problem:** CLAUDE.md claims "MyPy strict" but 183 `# type: ignore` across 56 files, `disallow_untyped_defs = false`.

**Note:** Current `pyproject.toml` mypy config does NOT show `ignore_errors = true` for the 16 modules mentioned. Either partially fixed or issue description needs verification.

Current config:
```toml
[tool.mypy]
python_version = "3.12"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = false  # Set to true for strict mode
ignore_missing_imports = true
explicit_package_bases = true
```

Only `src.retrieval.topic_classifier` has `disallow_untyped_defs = true`.

**Effort:** HIGH | **Complexity:** HIGH | **Labels:** vps, HIGH severity

---

### INFRASTRUCTURE ISSUES (1081–1085)

#### 1081 — PostgreSQL 7 crashes, WAL corruption, autovacuum failures
**Problem:** 7 unclean shutdowns between 2026-03-24 and 2026-04-01. WAL corruption (`invalid record length at 0/3D64530`). Autovacuum worker startup failures. Logical replication launcher exits.

**Root cause:** Container receives SIGKILL instead of SIGTERM → `docker stop` issue or external killing.

**Container:** `dev-postgres-1`

**Needed investigation:**
1. Docker restart policy
2. Who/what kills the container
3. Cron/systemd tasks affecting containers

**Effort:** MEDIUM (investigation) | **Complexity:** HIGH (requires docker/system forensics)

---

#### 1082 — ClickHouse IPv6 bind failures + lock contention up to 200s
**Problem:**
1. IPv6 bind failures on ports 9009, 8123, 9000, 9004, 9005 — `listen_host` needs `0.0.0.0` not `[::]`
2. MergeTreeBackgroundExecutor lock contention — acquisition took up to **200 seconds** on `default.observations` and `system.part_log`

**Lock contention possible causes:** CPU/IO insufficiency, high storage load, conflict between long-running queries and background merges.

**Container:** `dev-clickhouse-1`

**Effort:** MEDIUM | **Complexity:** MEDIUM

---

#### 1083 — Qdrant telemetry reporting failed + invalid vector name queries
**Problem:**
1. Telemetry reporting failed — `https://telemetry.qdrant.io/` unreachable (TLS CloseNotify). Non-critical but check network connectivity.
2. gRPC query failures — someone queries Qdrant with non-existent vector name. Possible code bug.

**Container:** `dev-qdrant-1`

**Effort:** LOW | **Complexity:** LOW

---

#### 1085 — File structure reorganization
**Problem:** Root has 17 `tmp.*/` directories, 30+ `tmp*.json/csv`, 14 `uv-*.lock` files. Dockerfiles in `src/`. docs/plans/ and docs/reports/ not archived. 50+ scripts, many one-time. Duplicate `search_engines.py`. Empty `src/governance/`.

**Plan:** Detailed 15-task plan at `docs/superpowers/plans/2026-04-01-file-structure-reorganization-plan.md`

**Phase 1:** Delete tmp*/uv-*.lock (~60 items), move e2e_tester.session and .test_durations, delete duplicate GitHub workflows
**Phase 2:** Move AGENTS.override.md → .claude/rules/features/, archive docs/plans/ and docs/reports/, delete docs/documents/ .docx
**Phase 3:** Move Dockerfiles to docker/, rename duplicate search_engines.py, archive legacy ingestion files, delete empty src/governance/
**Phase 4:** Archive old scripts, delete empty settings.local.json, update .gitignore, update README, add pre-commit hook

**Effort:** MEDIUM | **Complexity:** LOW-MEDIUM

---

### OTHER ISSUES (988, 1003)

#### 988 — Residual VPS parity follow-ups
**Remaining scope:**
- Docker artifact hygiene on VPS (#841)
- Host-only observability/debug exposure gaps for Qdrant, LiteLLM, BGE-M3 (#843)

**Evidence:** `docs/plans/2026-03-24-vps-snapshot-revalidation-report.md`

**Effort:** MEDIUM | **Complexity:** MEDIUM

---

#### 1003 — Langfuse local-to-VPS migration
**Plan:** `docs/plans/2026-03-18-langfuse-local-to-vps-implementation-plan.md`

**Scope:**
1. Backup current VPS Langfuse PostgreSQL and MinIO state
2. Export local canonical Langfuse PostgreSQL and MinIO state
3. Replace VPS state from local
4. Restart and validate Langfuse on VPS
5. Realign VPS bot env to migrated Langfuse keys
6. Write redacted migration report

**Constraints:** Don't touch ClickHouse, keep rollback path, don't commit secrets/dumps/archives.

**Effort:** HIGH | **Complexity:** HIGH

---

## Priority Recommendations

### Immediate (P0 — Fix Now)
1. **#1073** — Fix `voyageai>=0.3.0` → `voyageai>=0.1.7` (broken constraint)
2. **#1081** — PostgreSQL crashes (data integrity risk)
3. **#1082** — ClickHouse 200s lock contention (performance critical)

### Next Sprint (P1)
1. **#1070** — PropertyBot split (enables #1088)
2. **#1072** — Bare except catches (code quality)
3. **#1088** — PropertyBot test coverage (after #1070)
4. **#1073** — Add `langfuse<4.0` upper bound

### Backlog (P2)
1. **#1089** — LangGraph voice pipeline coverage
2. **#1090** — Kommo error scenarios
3. **#1091** — Ingestion state_manager coverage
4. **#1092** — Caching layers coverage
5. **#1093** — Dialogs FSM coverage
6. **#1077** — Contextualization base class
7. **#1094** — HandoffData Pydantic
8. **#1095** — Retry decorator consolidation
9. **#1085** — File structure reorganization
10. **#858** — MyPy cleanup

### Already Closed/Merged
- **#1074** — compose.vps.yml (CLOSED)
- **#1075** — unused imports (CLOSED)
- **#1076** — duplicate convert_to_python_types (CLOSED)
- **#1084** — k8s config sync (MERGED)
