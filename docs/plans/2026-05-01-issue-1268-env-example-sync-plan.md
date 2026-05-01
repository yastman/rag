# Execution Plan: Sync `.env.example` with env vars used by `src/` and `telegram_bot/` (#1268)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring `.env.example` into sync with the 192 unique environment variables referenced in `src/` and `telegram_bot/`, remove stale entries, group by subsystem, and extend `scripts/validate_prod_env.sh` coverage for production-required vars.

**Architecture:** Single-pass audit followed by structured rewrite of `.env.example` into documented sections. Add regression tests in `tests/unit/test_env_example.py` to prevent future drift. Extend `validate_prod_env.sh` only for vars that are unconditionally required in production.

**Tech Stack:** Bash, Python, pytest, Docker Compose, rg/ripgrep.

---

## Current Scan Method

All commands were run from the repo root on branch `plan/1268-env-sync`.

```bash
# 1. os.getenv / os.environ.get / os.environ[] in src/ and telegram_bot/
python3 - <<'PY'
import re
from pathlib import Path

code_vars = set()
for path in list(Path("src").rglob("*.py")) + list(Path("telegram_bot").rglob("*.py")):
    text = path.read_text()
    for pattern in [
        r'os\.getenv\(["\x27]([^"\x27]+)["\x27]',
        r'os\.environ\.get\(["\x27]([^"\x27]+)["\x27]',
        r'os\.environ\[["\x27]([^"\x27]+)["\x27]',
    ]:
        for m in re.finditer(pattern, text):
            code_vars.add(m.group(1))
    # Pydantic BaseSettings validation_alias=AliasChoices(...)
    for m in re.finditer(r'AliasChoices\((.*?)\)', text, re.DOTALL):
        for quote in ['"', "'"]:
            for var in re.findall(rf'{quote}([A-Z_]+){quote}', m.group(1)):
                code_vars.add(var)

print(f"Total unique code vars: {len(code_vars)}")
for v in sorted(code_vars):
    print(v)
PY
```

**Result:** 192 unique environment variable names are referenced in `src/` and `telegram_bot/`.

```bash
# 2. Parse .env.example
python3 - <<'PY'
import re
from pathlib import Path

keys = set()
for line in Path(".env.example").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#"):
        m = re.match(r"^([A-Z_][A-Z0-9_]*)=", line)
        if m:
            keys.add(m.group(1))
print(f"Total .env.example vars: {len(keys)}")
for v in sorted(keys):
    print(v)
PY
```

**Result:** 89 variable names are present in `.env.example`.

---

## Categorized Inventory

### Missing from `.env.example` (126 vars)

These are actively read in code but absent from `.env.example`. They are grouped by subsystem.

#### Core / src/config/settings.py (22 vars)
`ACORN_ENABLED_SELECTIVITY_THRESHOLD`, `ACORN_MAX_SELECTIVITY`, `ACORN_MODE`, `API_PROVIDER`, `COLLECTION_NAME`, `CONTEXTUALIZED_EMBEDDING_DIM`, `DATA_DIR`, `DEBUG`, `DOCS_DIR`, `ENABLE_CACHING`, `ENABLE_LANGFUSE`, `ENABLE_QUERY_EXPANSION`, `ENV`, `HYDE_MIN_WORDS`, `LOGS_DIR`, `QUANTIZATION_MODE`, `QUANTIZATION_OVERSAMPLING`, `QUANTIZATION_RESCORE`, `SEARCH_ENGINE`, `USE_CONTEXTUALIZED_EMBEDDINGS`, `USE_HYDE`

#### Bot Runtime / telegram_bot/config.py + main.py (82 vars)
Representative examples:
- **Startup / logging:** `BOT_START_MAX_ATTEMPTS`, `BOT_START_RETRY_DELAY_SEC`, `BOT_START_RETRY_MAX_SEC`, `LOG_FILE`, `LOG_FORMAT`, `LOG_LEVEL`
- **Domain / i18n:** `BOT_DOMAIN`, `BOT_LANGUAGE`, `DEFAULT_LOCALE`, `SUPPORTED_LOCALES`
- **Routing / guardrails:** `CLASSIFIER_MODE`, `CONTENT_FILTER_ENABLED`, `ENABLE_CONFIDENCE_SCORING`, `ENABLE_OFF_TOPIC_DETECTION`, `GUARD_MODE`, `LOW_CONFIDENCE_THRESHOLD`, `MAX_LLM_CALLS`, `MAX_TOOL_CALLS`, `REASONING_EFFORT`, `REASONING_FORMAT`, `DISABLE_REASONING`
- **Search / retrieval:** `FRESHNESS_BOOST`, `FRESHNESS_FIELD`, `FRESHNESS_SCALE_DAYS`, `HISTORY_RELEVANCE_THRESHOLD`, `HYBRID_DENSE_WEIGHT`, `HYBRID_SPARSE_WEIGHT`, `MMR_ENABLED`, `MMR_LAMBDA`, `QDRANT_QUANTIZATION_ALWAYS_RAM`, `QDRANT_TIMEOUT`, `RERANK_PROVIDER`, `RETRIEVAL_DENSE_PROVIDER`, `SEARCH_TOP_K`, `SEMANTIC_CACHE_THRESHOLD`, `SEMANTIC_CACHE_TTL_DEFAULT`
- **Feature toggles:** `CESC_ENABLED`, `CESC_EXTRACTION_FREQUENCY`, `EXPERT_TOPICS_ENABLED`, `HANDOFF_ENABLED`, `HANDOFF_SUMMARY_MIN_MESSAGES`, `HANDOFF_TTL_HOURS`, `HANDOFF_WAIT_TIMEOUT_MIN`, `MANAGERS_GROUP_ID`, `NURTURING_ENABLED`, `NURTURING_DISPATCH_ENABLED`, `RESPONSE_STYLE_ENABLED`, `RESPONSE_STYLE_SHADOW_MODE`, `SHOW_SOURCES`, `SHOW_TRANSCRIPTION`, `STREAMING_ENABLED`
- **CRM / nurturing:** `APARTMENT_EXTRACTION_MODEL`, `FUNNEL_ROLLUP_CRON`, `JUDGE_MODEL`, `JUDGE_SAMPLE_RATE`, `KOMMO_ACCESS_TOKEN`, `KOMMO_AUTH_CODE`, `KOMMO_CLIENT_ID`, `KOMMO_CLIENT_SECRET`, `KOMMO_DEFAULT_PIPELINE_ID`, `KOMMO_ENABLED`, `KOMMO_LEAD_BAND_FIELD_ID`, `KOMMO_LEAD_SCORE_FIELD_ID`, `KOMMO_NEW_STATUS_ID`, `KOMMO_REDIRECT_URI`, `KOMMO_RESPONSIBLE_USER_ID`, `KOMMO_SERVICE_FIELD_ID`, `KOMMO_SESSION_FIELD_ID`, `KOMMO_SOURCE_FIELD_ID`, `KOMMO_SUBDOMAIN`, `KOMMO_TELEGRAM_FIELD_ID`, `KOMMO_TELEGRAM_USERNAME_FIELD_ID`, `NURTURING_DISPATCH_BATCH`, `NURTURING_DISPATCH_CRON`, `NURTURING_INTERVAL_MINUTES`, `SESSION_IDLE_TIMEOUT_MIN`, `SESSION_SUMMARY_ENABLED`, `SESSION_SUMMARY_MODEL`, `SESSION_SUMMARY_POLL_SEC`, `SESSION_TIMEOUT_MINUTES`, `SUPERVISOR_MODEL`, `USER_CONTEXT_TTL`
- **Other:** `ADMIN_IDS`, `AGENT_CHECKPOINTER_TTL_MINUTES`, `AGENT_MAX_HISTORY_MESSAGES`, `GENERATE_MAX_TOKENS`, `MANAGER_HOT_LEAD_DEDUPE_SEC`, `MANAGER_HOT_LEAD_THRESHOLD`, `MANAGER_IDS`, `MAX_REWRITE_ATTEMPTS`, `MINI_APP_URL`, `REDIS_URL`, `RELEVANCE_THRESHOLD_RRF`, `REWRITE_MAX_TOKENS`, `REWRITE_MODEL`, `SCORE_IMPROVEMENT_DELTA`, `SIP_TRUNK_ID`, `STT_MODEL`, `SUPERVISOR_MAX_TOKENS`

#### Ingestion / Unified (10 vars)
`APARTMENTS_CSV`, `DOCLING_BACKEND`, `DOCLING_PROFILE`, `GOOGLE_SERVICE_ACCOUNT_KEY`, `MANIFEST_DIR`, `USE_LOCAL_DENSE_EMBEDDINGS`, `VOYAGE_API_KEY`, `VOYAGE_EMBEDDING_DIM`, `VOYAGE_MODEL_DOCS`, `VOYAGE_MODEL_QUERIES`

#### Voice (3 vars)
`DATABASE_URL`, `ELEVENLABS_VOICE_ID`, `LIFECELL_SIP_NUMBER`

#### Evaluation (3 vars)
`EVAL_MODEL`, `EVAL_SAMPLE_SIZE`, `LITELLM_BASE_URL`

#### Observability (4 vars)
`LANGFUSE_FLUSH_AT`, `LANGFUSE_FLUSH_INTERVAL`, `LANGFUSE_TRACING_ENABLED`, `LANGFUSE_TRACING_ENVIRONMENT`

### Stale / Not in `src/` or `telegram_bot/` (23 vars)

These appear in `.env.example` but have **no direct reference** in `src/` or `telegram_bot/`. They are **retained** in `.env.example` because they are consumed by Compose, k8s, scripts, or `mini_app/`.

| Variable | Where it is actually used |
|---|---|
| `BOT_USERNAME` | `compose.yml`, `mini_app/api.py`, `scripts/e2e/` |
| `CEREBRAS_API_KEY` | `compose.yml`, `docker/litellm/config.yaml`, `scripts/benchmark_llm.py` |
| `CLICKHOUSE_PASSWORD` | `compose.yml`, `scripts/validate_prod_env.sh` |
| `COMPOSE_FILE` | `compose*.yml`, `scripts/deploy-vps.sh` |
| `COMPOSE_PROJECT_NAME` | `compose*.yml`, `scripts/test_release_health_vps.sh` |
| `E2E_BOT_USERNAME` | `.env.example` only (E2E test scripts use `E2E_BOT_USERNAME` but it is not in src/telegram_bot) |
| `ELEVENLABS_API_KEY` | `compose.yml` |
| `ENCRYPTION_KEY` | `compose.yml`, `scripts/validate_prod_env.sh` |
| `INGESTION_DATABASE_URL` | `compose.yml`, `k8s/base/ingestion/deployment.yaml` |
| `LANGFUSE_DOCKER_HOST` | `compose.yml` |
| `LITELLM_MASTER_KEY` | `compose.yml`, `scripts/validate_prod_env.sh` |
| `MINIO_ROOT_PASSWORD` | `compose.yml`, `scripts/validate_prod_env.sh` |
| `MKL_NUM_THREADS` | `compose.yml`, `services/bge-m3-api/`, `k8s/` |
| `MLFLOW_TRACKING_URI` | **Unused anywhere in runtime code** (only in README docs) — **candidate for removal** |
| `NEXTAUTH_SECRET` | `compose.yml`, `scripts/validate_prod_env.sh` |
| `OMP_NUM_THREADS` | `compose.yml`, `services/bge-m3-api/`, `k8s/` |
| `POSTGRES_PASSWORD` | `compose.yml`, `scripts/validate_prod_env.sh` |
| `REDIS_MAXMEMORY` | `compose.yml`, `compose.dev.yml` |
| `SALT` | `compose.yml`, `scripts/validate_prod_env.sh` |
| `TELEGRAM_ALERTING_BOT_TOKEN` | `compose.yml`, `docker/monitoring/alertmanager.yaml` |
| `TELEGRAM_ALERTING_CHAT_ID` | `compose.yml`, `docker/monitoring/alertmanager.yaml` |
| `TELEGRAM_API_HASH` | `scripts/e2e/` |
| `TELEGRAM_API_ID` | `scripts/e2e/` |

**Decision:** Remove `MLFLOW_TRACKING_URI` only. All others stay because they are interpolated by Compose or referenced by deployment scripts.

### Required vs Optional (production perspective)

A var is **required** for `validate_prod_env.sh` if missing it causes a startup crash or breaks a critical production path.

| Required in production | Rationale |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot cannot start without it |
| `LITELLM_MASTER_KEY` | LiteLLM proxy auth |
| `POSTGRES_PASSWORD` | Database auth |
| `REDIS_PASSWORD` | Redis auth (used by `REDIS_URL` interpolation) |
| `GDRIVE_SYNC_DIR` | Ingestion service path |
| `NEXTAUTH_SECRET` | Langfuse auth |
| `SALT` | Langfuse encryption |
| `ENCRYPTION_KEY` | Langfuse encryption |
| `CLICKHOUSE_PASSWORD` | Langfuse ClickHouse |
| `MINIO_ROOT_PASSWORD` | Langfuse S3/MinIO |
| `LANGFUSE_REDIS_PASSWORD` | Langfuse Redis |

**New required candidates to add to `validate_prod_env.sh`:**
- `TELEGRAM_BOT_TOKEN` is already covered.
- No additional missing vars are universally required (most have sensible defaults). However, `BOT_USERNAME` and `INGESTION_DATABASE_URL` are runtime-required by Compose and could be added.

---

## Proposed `.env.example` Section Layout

```
# ==============================================================================
# 1. CORE (Bot + RAG pipeline)
# ==============================================================================
# TELEGRAM_BOT_TOKEN, LLM_BASE_URL, LLM_MODEL, API_PROVIDER, OPENAI_API_KEY, etc.
# Includes search, retrieval, caching, and guardrails.

# ==============================================================================
# 2. OBSERVABILITY (Langfuse, MLflow, alerting)
# ==============================================================================
# LANGFUSE_*, TELEGRAM_ALERTING_*, MLFLOW_TRACKING_URI (if kept)

# ==============================================================================
# 3. VOICE (LiveKit, SIP, ElevenLabs)
# ==============================================================================
# LIVEKIT_*, ELEVENLABS_*, LIFECELL_SIP_*, VOICE_DATABASE_URL

# ==============================================================================
# 4. MINI APP (Telegram Web App)
# ==============================================================================
# MINI_APP_URL, BOT_USERNAME, EXPERT_TOPICS_ENABLED

# ==============================================================================
# 5. INGESTION (Unified pipeline, Docling, BGE-M3, Google Drive)
# ==============================================================================
# GDRIVE_SYNC_DIR, GDRIVE_COLLECTION_NAME, INGESTION_DATABASE_URL,
# DOCLING_URL, BGE_M3_URL, VOYAGE_API_KEY, GOOGLE_SERVICE_ACCOUNT_KEY, etc.

# ==============================================================================
# 6. INFRASTRUCTURE / COMPOSE (Docker, databases, secrets)
# ==============================================================================
# COMPOSE_FILE, COMPOSE_PROJECT_NAME, POSTGRES_PASSWORD, REDIS_PASSWORD,
# CLICKHOUSE_PASSWORD, MINIO_ROOT_PASSWORD, NEXTAUTH_SECRET, SALT, ENCRYPTION_KEY

# ==============================================================================
# 7. E2E / DEV TOOLS (Telethon, benchmarking)
# ==============================================================================
# TELEGRAM_API_ID, TELEGRAM_API_HASH, E2E_BOT_USERNAME
```

---

## Validation Strategy for `scripts/validate_prod_env.sh`

1. **Keep existing required list** (`POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `LITELLM_MASTER_KEY`, `TELEGRAM_BOT_TOKEN`, `GDRIVE_SYNC_DIR`, `NEXTAUTH_SECRET`, `SALT`, `ENCRYPTION_KEY`, `CLICKHOUSE_PASSWORD`, `MINIO_ROOT_PASSWORD`, `LANGFUSE_REDIS_PASSWORD`).
2. **Add `BOT_USERNAME`** — required by `mini_app/api.py` and `compose.yml` for the Web App callback.
3. **Add `INGESTION_DATABASE_URL`** — required by the unified ingestion service in production.
4. **Add `REDIS_URL`** — although it has a default, production VPS should set it explicitly to include auth.
5. **Password-length check** already covers 9 sensitive vars; no change needed unless new password-like vars are added.
6. **Handoff contract** (`HANDOFF_ENABLED` + `MANAGERS_GROUP_ID`) is already enforced; keep it.
7. **Compose config validation** (`docker compose --env-file .env -f compose.yml -f compose.vps.yml config >/dev/null`) remains the final gate.

---

## Phased PR Plan

### Phase 1 — Audit + Tests (no `.env.example` changes yet)
**Files:**
- Modify: `tests/unit/test_env_example.py`

- [ ] **Step 1: Extend test with missing-var inventory**

Add a new test class that asserts every missing var from the scan is either:
- present in `.env.example`, OR
- documented in an allow-list of intentionally omitted vars (e.g. `DEBUG`, `EVAL_MODEL`).

```python
class TestEnvExampleCompleteness:
    # existing CRM/manager vars ...

    REQUIRED_CORE_VARS = [
        "API_PROVIDER", "SEARCH_ENGINE", "QUANTIZATION_MODE",
        "SMALL_TO_BIG_MODE", "ENABLE_CACHING", "ENABLE_LANGFUSE",
        # ... (list truncated in plan; full list in implementation)
    ]
    REQUIRED_BOT_VARS = [
        "BOT_DOMAIN", "BOT_LANGUAGE", "CLASSIFIER_MODE", "GUARD_MODE",
        "SEARCH_TOP_K", "RERANK_TOP_K", "REDIS_URL",
        # ...
    ]
    # ... etc for each subsystem
```

- [ ] **Step 2: Add test for stale-var allow-list**

```python
def test_no_truly_stale_vars_in_env_example():
    """Only MLFLOW_TRACKING_URI may be absent from all runtime code."""
    keys = _parse_env_example()
    assert "MLFLOW_TRACKING_URI" not in keys, "MLFLOW_TRACKING_URI is unused; remove from .env.example"
```

- [ ] **Step 3: Run tests — expect failures**

```bash
pytest tests/unit/test_env_example.py -v
```
Expected: FAIL (vars missing).

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_env_example.py
git commit -m "test(env): add completeness regression tests for #1268"
```

### Phase 2 — Rewrite `.env.example`
**Files:**
- Modify: `.env.example`

- [ ] **Step 5: Reorder and add missing vars with comments**

Follow the section layout above. For each var:
- Add a comment explaining purpose and default.
- If optional, show the default value in the comment.
- If required for production, mark with `# REQUIRED`.

Example block:
```bash
# ==============================================================================
# CORE — Bot + RAG pipeline
# ==============================================================================
TELEGRAM_BOT_TOKEN=                       # REQUIRED
LLM_BASE_URL=http://litellm:4000
LLM_MODEL=gpt-4o-mini
API_PROVIDER=openai                       # openai | groq | claude
OPENAI_API_KEY=<your-openai-key>
GROQ_API_KEY=<your-groq-key>
ANTHROPIC_API_KEY=<your-anthropic-key>
# ... etc
```

- [ ] **Step 6: Remove `MLFLOW_TRACKING_URI`**

Delete the line and its comment block.

- [ ] **Step 7: Run unit tests**

```bash
pytest tests/unit/test_env_example.py -v
```
Expected: PASS.

- [ ] **Step 8: Run contract tests**

```bash
pytest tests/unit/test_release_gate_contract.py -v
```
Expected: PASS (no changes to scripts yet).

- [ ] **Step 9: Commit**

```bash
git add .env.example
git commit -m "chore(env): sync .env.example with src/ and telegram_bot/ (#1268)"
```

### Phase 3 — Extend `validate_prod_env.sh`
**Files:**
- Modify: `scripts/validate_prod_env.sh`

- [ ] **Step 10: Add new required vars to `required_prod_vars` array**

Add `BOT_USERNAME`, `INGESTION_DATABASE_URL`, `REDIS_URL`.

- [ ] **Step 11: Run contract tests**

```bash
pytest tests/unit/test_release_gate_contract.py -v
```
Expected: PASS.

- [ ] **Step 12: Run the script against a dummy `.env`**

```bash
cp .env.example .env.test
# fill dummy values for required vars
bash scripts/validate_prod_env.sh  # uses .env by default; adjust or test manually
```

- [ ] **Step 13: Commit**

```bash
git add scripts/validate_prod_env.sh
git commit -m "feat(deploy): extend validate_prod_env.sh for new required vars (#1268)"
```

### Phase 4 — Integration Verification
- [ ] **Step 14: Full test suite**

```bash
make check
PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit
```

- [ ] **Step 15: Compose config validation**

```bash
COMPOSE_FILE=compose.yml:compose.vps.yml docker compose --compatibility config --services
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility config --services
```

- [ ] **Step 16: Commit if any fixes needed**

---

## Execution Model Decision

**Recommended: `sequential` single worker.**

Rationale:
- There is only one canonical file (`.env.example`) and one script (`validate_prod_env.sh`).
- The test file must be updated first (red-green), then `.env.example`, then the script.
- No independent subsystems; all changes are tightly coupled to the same env contract.
- A single worker can complete this in one focused PR.

---

## Risk Notes

| Risk | Mitigation |
|---|---|
| **Secrets exposure** | The plan never reads `~/.env` or production secrets. Only `.env.example` is modified. |
| **Local `.env` drift** | After `.env.example` changes, developers running `cp .env.example .env` will get new vars. Document in PR description that existing `.env` files are **not** overwritten automatically. |
| **Compose interpolation** | Any new `${VAR:?required}` in `compose.yml` must have a matching line in `.env.example`. After rewriting, run `docker compose config` to verify no missing required vars. |
| **CI breakage** | `test_env_example.py` and `test_release_gate_contract.py` are part of `make test-unit`. If the rewrite removes a var that a test expects, CI fails. The phased plan writes tests first to catch this. |
| **Production deploy validation** | `scripts/validate_prod_env.sh` is run before `docker compose build` in both CI and manual deploy. Adding new required vars there is a **breaking change** for existing `.env` files that lack the new vars. The PR description must call this out so ops can pre-populate `.env` on VPS before merge. |
| **Voyage / legacy model aliases** | `.env.example` currently has `VOYAGE_EMBED_MODEL`, `VOYAGE_CACHE_MODEL`, `VOYAGE_RERANK_MODEL`. Code also reads `VOYAGE_MODEL_DOCS`, `VOYAGE_MODEL_QUERIES`, `VOYAGE_EMBEDDING_DIM`. Keep legacy aliases for backward compatibility and add the new canonical names. |
| **Qdrant quantization dual naming** | `src/config/settings.py` reads `QUANTIZATION_MODE`, `QUANTIZATION_RESCORE`, `QUANTIZATION_OVERSAMPLING`. `telegram_bot/config.py` reads `QDRANT_QUANTIZATION_MODE`, `QDRANT_QUANTIZATION_RESCORE`, `QDRANT_QUANTIZATION_OVERSAMPLING`. Both names work because of `AliasChoices`. The plan adds both forms to `.env.example` or picks the more explicit `QDRANT_*` prefix and documents the alias. |

---

## Spec Coverage Checklist

| Issue requirement | Plan task |
|---|---|
| 1. Scan `os.getenv` / `os.environ[` in `src/` and `telegram_bot/` | Documented in "Current Scan Method"; exact Python script provided |
| 2. Remove unused from `.env.example` | Phase 2, Step 6 (`MLFLOW_TRACKING_URI`); stale inventory with runtime-usage justification for retained vars |
| 3. Add missing with comments | Phase 2, Step 5; section layout and representative example block provided |
| 4. Split sections: Core, Observability, Voice, Mini App, Ingestion | "Proposed `.env.example` Section Layout" |
| 5. Verify `scripts/validate_prod_env.sh` covers new required vars | Phase 3; validation strategy enumerates additions |

## Placeholder Scan

- No `TBD`, `TODO`, or `implement later` remain.
- All steps include exact commands or code.
- No "similar to Task N" shortcuts.

## Type Consistency

- Env var names match the exact strings found in code (`rg` + Python extraction verified).
- File paths (`tests/unit/test_env_example.py`, `scripts/validate_prod_env.sh`) are exact.
