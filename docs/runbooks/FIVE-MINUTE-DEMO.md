# Five-Minute Demo — Operator Runbook (#3206)

The exact procedure for rehearsing and presenting the frozen five-minute
real-estate Telegram demo. It is built on the artifacts that exist in the repo
today: the automated gate `make demo-gate` (#3205), the data bootstrap pair
`make demo-bootstrap` / `make demo-verify` (#3202), the readiness remediation
`make qdrant-ensure-indexes` (#3202), the polling-lock release
`make release-polling-lock` (#3199), the truthful shipped seed (#3203) and the
deterministic routing surfaces (#3204).

> **Status (2026-09-03, SHA `0e310f7dd`):** this runbook's repo-verifiable steps
> were executed for real and their outputs are recorded in
> [`DEMO-REHEARSAL-LOG.md`](DEMO-REHEARSAL-LOG.md) ("Verified on the authoring
> host"). The **three live rehearsals have NOT been executed yet** — the
> authoring host has no Telegram bot token, no Telegram userbot credentials, no
> LLM key and no BGE-M3 service. The issue closes only after three passing,
> timestamped rehearsals on the presentation host at one exact SHA, recorded in
> the log and in #3197.

## 0. What a rehearsal proves (and what it must not claim)

One rehearsal = one full pass of the frozen ten-step client journey against a
**real deployed bot**, started from a **clean bot/service restart**, finishing
within the five-minute budget, producing a JSON artifact tied to the exact Git
SHA. Nothing about README / DOCKER / bot-README promises may be reconciled with
behavior that the **final** passing gate has not proven (issue #3206 scope).

## 1. Environment, names, secrets

### 1.1 Topology (local presentation host)

| Surface | Address | Started by |
|---|---|---|
| Qdrant | `http://localhost:6333` | `make local-up` (compose.yml + compose.dev.yml) |
| Redis | `redis://localhost:6379` | `make local-up` |
| BGE-M3 embeddings | `http://localhost:8000` (`/health`) | `make local-up` (service `bge-m3`) |
| PostgreSQL (optional dep) | from `REALESTATE_DATABASE_URL` | `make local-up` (service `postgres`) |
| Bot | Telegram long polling, host process | `make bot` (logs to `logs/bot-run.log`) |
| E2E userbot (gate client) | Telegram MTProto, host process | `make demo-gate` |

Collections (fixed names, do not invent alternatives for the demo):

- knowledge: `gdrive_documents_bge` (override: `QDRANT_COLLECTION`, quantization suffix may apply)
- apartments: `apartments` (hard-coded, `APARTMENTS_COLLECTION` in `src/runtime/qdrant/readiness.py`)

### 1.2 Required configuration (`.env` at the repo root)

| Variable | Used by | Notes |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | bot | `<bot_id>:<35+ chars>` format is validated at startup |
| `LLM_MODEL` + one of `LLM_API_KEY` / `OPENAI_API_KEY` / `CEREBRAS_API_KEY` | bot, gate | grounded Q&A and safe no-answer steps fail without it |
| `QDRANT_URL`, `REDIS_URL`, `BGE_M3_URL` | bot, gate | defaults `http://localhost:6333`, `redis://localhost:6379`, `http://localhost:8000` |
| `QDRANT_COLLECTION` | bot, gate | knowledge collection name |
| `REALESTATE_DATABASE_URL` | bot preflight | Postgres is an **optional** dependency (non-fatal); the frozen journey does not exercise Postgres-backed features |
| `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` | gate (userbot) | from <https://my.telegram.org> |
| `E2E_BOT_USERNAME` | gate | the demo bot's `@username` |

Secret handling: `.env` is gitignored — never paste tokens into tickets, logs or
the rehearsal log. Reference the variable *name* only. The userbot session file
(`e2e_tester.session`) is a credential too; keep it on the presentation host.

### 1.3 Python environment

```bash
uv sync --python 3.12             # core + dev tools
uv sync --python 3.12 --extra telegram   # adds aiogram — REQUIRED by the demo gate
```

The gate imports `telegram_bot.keyboards` (single sources of truth for the frozen
button labels). Without the `telegram` extra it fails with
`ModuleNotFoundError: No module named 'aiogram'` (verified on the authoring host).

## 2. One-time preparation (clean-checkout path)

```bash
git clone https://github.com/yastman/rag.git rag && cd rag     # or your fork/checkout
git checkout <FINAL_SHA>                                       # pin the exact SHA (see §7)
git status --porcelain --untracked-files=no                    # must print NOTHING
uv sync --python 3.12 && uv sync --python 3.12 --extra telegram
```

The gate's `git` probe fails on a dirty tracked tree by design: the artifact must
be reproducible from one exact SHA. Commit or revert before rehearsing; never
rehearse from a dirty tree.

### 2.1 Authorize the E2E userbot (once per host)

```bash
uv run python -m scripts.e2e.auth --phone +359XXXXXXXXX
uv run python -m scripts.e2e.auth --phone +359XXXXXXXXX --code <CODE>
# 2FA only:  append --password <PASSWORD>
```

Expected: `e2e_tester.session` appears at the repo root. The gate's `telegram`
readiness probe checks exactly this file plus `TELEGRAM_API_ID`/`TELEGRAM_API_HASH`.

## 3. Services and data bootstrap

### 3.1 Start services and check health

```bash
make local-up               # postgres redis qdrant bge-m3
make local-service-health   # scripts/check_services.sh — Qdrant, Redis, BGE-M3, Ingestion
```

Expected: `local-service-health` reports all required services up (exit 0).

### 3.2 Bootstrap demo data (idempotent, non-destructive)

```bash
make demo-bootstrap
```

Expected tail: `Demo bootstrap PASSED: both product collections are ready.`
(creates a missing collection with the contract schema; ingests the shipped seed
only into an **empty** collection; requires BGE-M3 running — both corpora are
embedded at ingest time).

### 3.3 Read-only readiness gate

```bash
make demo-verify
```

Expected tail:

```
  [OK] knowledge/<knowledge-collection>: N points ...
  [OK] apartments/apartments: N points (probes: {...})
Demo bootstrap PASSED: both product collections are ready.
✓ Demo readiness verified
```

### 3.4 Readiness remediation (only if §3.3 fails with missing indexes)

Real failure signature (captured on the authoring host against a schema-only
fixture collection):

```
Demo bootstrap FAILED — actionable errors:
  - [schema_incompatible] apartments: missing payload index 'city' (keyword) —
    run `make qdrant-ensure-indexes` (non-destructive) or run `make demo-bootstrap` ...
```

Fix — non-destructive, idempotent, safe on populated collections:

```bash
make qdrant-ensure-indexes
make demo-verify     # must now pass
```

Never drop/recreate a populated collection between rehearsals (issue rule: no
Qdrant/PostgreSQL edits between runs).

## 4. Pre-flight readiness snapshot (gate prerequisites mode)

```bash
make demo-gate MODE=--prerequisites-only
```

This never contacts the bot. All seven surfaces are probed; a skipped surface
fails by design. Expected on a fully prepared presentation host — all `ok`:

```
readiness git: ok
readiness telegram: ok
readiness qdrant: ok
readiness golden_queries: ok
readiness bge: ok
readiness llm: ok
readiness redis: ok
Readiness snapshot complete (prerequisites-only mode).
✓ Demo gate complete
```

Real captured output on the **unprovisioned authoring host** (no secrets, no BGE,
empty Qdrant; throwaway `i3206-*` collections made the qdrant probe pass) — the
failure wording an operator will see:

```
readiness git: ok            readiness telegram: fail
readiness qdrant: ok         readiness golden_queries: fail
readiness bge: fail          readiness llm: fail
readiness redis: ok
Readiness gate failed — the bot was NOT contacted.
  - [telegram] telegram: TELEGRAM_API_ID not set
  - [telegram] telegram: session file e2e_tester.session not found — run
    'uv run python -m scripts.e2e.auth' to authorize the e2e userbot
  - [golden_queries] golden query 'Студия в Солнечном берегу до 100 000€'
    returns 0 listings (≥ 3 required) — re-ingest the shipped demo seed:
    uv run python -m src.ingestion.apartments.runner
  - [bge] BGE-M3 service unreachable at http://localhost:8000/health ...
  - [llm] LLM is not configured: set LLM_API_KEY (or OPENAI_API_KEY) ...
```

With the default (absent) collections the `qdrant` probe additionally fails with
the collection-missing remediation. Every failure line names its fix; see §8.

## 5. Start / stop the bot

```bash
make bot          # foreground, output teed to logs/bot-run.log  (or: make run-bot)
```

Wait for the startup preflight to pass (Qdrant readiness contracts, BGE health +
warmup, Redis; Postgres is non-fatal). The bot must print its startup/polling
line before any rehearsal step.

Stop with `Ctrl+C`. After an abrupt kill (or before starting a second bot),
release the Redis polling lock — **only after confirming no bot is alive**:

```bash
make release-polling-lock        # refuses while a bot container is running
# emergency only: RELEASE_POLLING_LOCK_FORCE=1 make release-polling-lock
```

The gate's `redis` probe fails with a pointer to this same target if the lock
key exists without a TTL (stale permanent lease, #3199).

Optional between-run sanity check that the bot actually answers:
`make bot-response-smoke` (#2192).

## 6. The frozen ten-step journey

`make demo-gate` (full mode) replays exactly this story through the real
Telegram userbot transport against `E2E_BOT_USERNAME`. A human presenter can
mirror every step manually; the surfaces below are frozen in the repo (single
sources of truth: `telegram_bot/keyboards/`, `src/runtime/domain_defaults.py`).

| # | Step | Operator action | Expected surface / reply |
|---|---|---|---|
| 1 | `clean_start` | send `/start` | root menu with the full reply keyboard, incl. «🎯 Демонстрация» and «💬 Задать вопрос» |
| 2 | `demo_open` | press reply «🎯 Демонстрация» | demo menu message («Демонстрация возможностей») with inline «🏖 Подбор апартаментов» |
| 3 | `demo_apartments` | click inline «🏖 Подбор апартаментов» | demo intro («Или выберите пример») with example-query buttons |
| 4 | `apartment_search_1` | click the first example button | status «Ищу подходящие…», then results header «Найдено N вариантов…» with **N ≥ 1** |
| 5 | `apartment_search_2` | type «Студия в Солнечном берегу до 100 000€» | «Найдено N вариантов…» with **N ≥ 3** (`GOLDEN_QUERY_MIN_RESULTS`) |
| 6 | `return_navigation` | press reply «🏠 Главное меню» | root menu again |
| 7 | `ask_open` | press reply «💬 Задать вопрос» | Ask prompt («Напишите вопрос») with inline «📋 Какие документы нужны для покупки?» |
| 8 | `grounded_qa` | click that inline button (`ask:docs` route) | **exactly one** grounded answer; must not match any canned/safe family; must not contain listing rows |
| 9 | `safe_no_answer` | type «Найди замок в Софии с частным аэропортом и вертолётной площадкой» | **exactly one** safe no-answer reply (never fabricated listings) |
| 10 | `clean_close` | send `/start` | root menu — chat left clean for the next run |

Gate-level assertions per step: single-send counts for steps 8–9, result-count
thresholds for steps 4–5, required reply/inline buttons for steps 1–3 and 7,
status messages excluded from answer counts. Whole journey must finish within
`FIVE_MINUTE_BUDGET_S = 300`.

## 7. Rehearsal procedure (repeat exactly three times)

For each rehearsal *k* = 1..3, from the repo root at the **same** `FINAL_SHA`:

```bash
# 0) confirm the pinned, clean state
git rev-parse HEAD                                # == FINAL_SHA for all three runs
git status --porcelain --untracked-files=no       # empty

# 1) clean service restart (data persists in volumes; no Qdrant/Postgres edits)
make local-down && make local-up
make local-service-health

# 2) data readiness (read-only; must pass unchanged every time)
make demo-verify

# 3) readiness snapshot (must be all-ok before the bot is contacted)
make demo-gate MODE=--prerequisites-only

# 4) clean bot start (rehearsal 1 = cold; rehearsals 2-3 = warm restart)
make bot                                          # Ctrl-C to stop afterwards
# -> in another terminal, after the bot's startup preflight passes:

# 5) the gate = the five-minute story
make demo-gate

# 6) archive evidence
cp logs/bot-run.log logs/bot-run-rehearsal-<k>.log
ls -t reports/demo-gate | head -1                 # newest artifact JSON
```

`make demo-gate` exits 0 and prints `verdict: passed` only when all ten steps
pass **and** the journey fits the 300 s budget. Fill one
[rehearsal log](DEMO-REHEARSAL-LOG.md) block per run. Acceptance (#3206): three
`verdict: passed` artifacts at the same SHA, then reconcile README / DOCKER /
bot-README / LOCAL-DEVELOPMENT claims with — and only with — the proven behavior,
and post the cold/warm latency, external-provider dependencies and exact SHA to
#3197.

Artifact location (gitignored, per run):
`reports/demo-gate/demo-gate-<sha8>-<UTC timestamp>.json`
— schema v1, contains the readiness snapshot, per-step `duration_ms`, message
ids, single-send counts, result counts, `total_duration_ms` vs
`five_minute_budget_ms`, and `git_sha`.

## 8. Failure remediation matrix

### 8.1 Readiness probes (gate fails BEFORE contacting the bot)

| Probe failure (verbatim prefix) | Cause | Fix |
|---|---|---|
| `git: tracked working tree is dirty...` | uncommitted tracked changes | commit/revert; artifact must tie to one SHA |
| `telegram: TELEGRAM_API_ID/HASH not set` | `.env` missing userbot creds | fill from my.telegram.org (§1.2) |
| `telegram: session file ... not found` | userbot never authorized | §2.1 `scripts.e2e.auth` |
| `qdrant: collection ... is missing / missing required dense vector / missing payload index` | collection absent or schema drift | `make demo-bootstrap`; if indexes only → `make qdrant-ensure-indexes` (§3.4) |
| `golden query '...' returns 0 listings (≥ 3 required)` | apartments seed missing/stale | re-ingest the shipped seed: `uv run python -m src.ingestion.apartments.runner` (needs BGE-M3) |
| `BGE-M3 service unreachable at .../health` | service down | `make local-up`; re-check `make local-service-health` |
| `LLM is not configured: set LLM_API_KEY...` | no provider key | set `LLM_MODEL` + a provider key in `.env` |
| `redis: ... polling lock key ... exists WITHOUT a TTL` | stale permanent lease | `make release-polling-lock` (§5) |
| `ModuleNotFoundError: No module named 'aiogram'` (import time) | `telegram` extra not installed | `uv sync --extra telegram` (§1.3) |

### 8.2 Journey steps (gate fails mid-story; fix, restart the bot, rerun the whole gate)

| Symptom | Meaning | First remedy |
|---|---|---|
| step fails with `required surface missing` | deployment drift: a frozen button/label is not on the deployed bot | verify the bot runs the same SHA as the gate (`git rev-parse HEAD` on the bot host) |
| `search returned the empty state (0 listings) but ≥ N required` | apartments data does not match the frozen query | re-ingest the shipped seed (§8.1 golden row), then `make demo-verify` |
| `only N listings shown, ≥ 3 required` | filter/index drift | `make qdrant-ensure-indexes`; re-check with `make demo-verify` |
| `expected exactly one answer message, got k` | duplicate sends — routing/policy regression | stop; do not present; diagnose the routing regression at that SHA |
| grounded Q&A matched a safe/canned family, or produced listing rows | retrieval/generation regression | stop; this is a product bug at that SHA — do not reconcile any docs |
| `timeout:` on a step | LLM/BGE latency spike or bot down | check `logs/bot-run-rehearsal-<k>.log`; restart bot + services; rerun |
| `verdict: failed` with `within_budget: false` | journey exceeded 300 s | record it as a failed rehearsal; investigate cold-start latency (esp. rehearsal 1) |
| Telegram `connect failed` | userbot session/network issue | re-run §2.1; check `E2E_BOT_USERNAME` |

## 9. Documentation reconciliation rule (post-gate, part of #3206 acceptance)

Only after the third passing rehearsal: update README / DOCKER.md /
`telegram_bot/README.md` / `docs/LOCAL-DEVELOPMENT.md` so that every demo-related
claim matches behavior proven by the final gate artifact. Any claim the gate did
not exercise stays unproven — either drop it or mark it explicitly as unproven.
Then run `make docs-check` (markdown link audit).

## 10. Verification status of this runbook

See [`DEMO-REHEARSAL-LOG.md`](DEMO-REHEARSAL-LOG.md): every repo-verifiable step
above was executed for real on the authoring host at SHA `0e310f7dd` (core gate,
remediation chain, prerequisites mode — including the exact captured outputs
quoted in §3.4, §4, §8.1), and the three live rehearsals are explicitly recorded
as **NOT YET EXECUTED**.
