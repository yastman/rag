# Five-Minute Demo — Rehearsal Log (#3206)

Template + evidence ledger for the three required rehearsals of the frozen
five-minute demo. Procedure: [`FIVE-MINUTE-DEMO.md`](FIVE-MINUTE-DEMO.md).

**Acceptance rule (#3206):** the issue closes only when this log holds three
`verdict: passed` rehearsal blocks at the **same exact SHA**, executed on the
presentation host from clean bot/service restarts, each backed by its
`reports/demo-gate/demo-gate-<sha8>-<stamp>.json` artifact.

> Current status: **0 of 3 rehearsals executed.** Every block below is a
> template with explicit `NOT YET EXECUTED` placeholders. Do not delete the
> placeholders until a real rehearsal replaces them; never backfill a block
> from memory — fill it from the artifact JSON and the bot log of that run.

- FINAL_SHA (pinned for all three rehearsals): **NOT YET PINNED** — the runbook
  verification below ran at `0e310f7dda680716dd7407dc1dcd0294e625b793`; fill the
  exact full SHA chosen for the rehearsals before rehearsal 1
- Presentation host: **NOT YET RECORDED**

---

## Rehearsal 1 (cold start) — NOT YET EXECUTED

| Field | Value |
|---|---|
| Date / UTC start–end | **NOT YET EXECUTED** |
| Host | **NOT YET EXECUTED** |
| Git SHA (`git rev-parse HEAD`) | **NOT YET EXECUTED** — must equal FINAL_SHA |
| Tracked tree clean (`git status --porcelain --untracked-files=no`) | **NOT YET EXECUTED** |
| Services restart done (`make local-down && make local-up`) | **NOT YET EXECUTED** |
| `make local-service-health` | **NOT YET EXECUTED** |
| `make demo-verify` | **NOT YET EXECUTED** |
| `make demo-gate MODE=--prerequisites-only` | **NOT YET EXECUTED** |
| Bot start mode | cold (first start after data prep) |
| Bot log archive | `logs/bot-run-rehearsal-1.log` — **NOT YET EXECUTED** |
| Gate command | `make demo-gate` |
| Artifact path | `reports/demo-gate/demo-gate-<sha8>-<stamp>.json` — **NOT YET EXECUTED** |
| Verdict | **NOT YET EXECUTED** |
| Journey seconds / budget 300 s (`total_duration_ms`) | **NOT YET EXECUTED** |
| `within_budget` | **NOT YET EXECUTED** |

Per-step timings — copy `duration_ms` (and `result_count` where relevant) from
the artifact:

| # | Step | duration_ms | result_count | status |
|---|---|---|---|---|
| 1 | clean_start | **NOT YET EXECUTED** | — | **NOT YET EXECUTED** |
| 2 | demo_open | **NOT YET EXECUTED** | — | **NOT YET EXECUTED** |
| 3 | demo_apartments | **NOT YET EXECUTED** | — | **NOT YET EXECUTED** |
| 4 | apartment_search_1 | **NOT YET EXECUTED** | **NOT YET EXECUTED** | **NOT YET EXECUTED** |
| 5 | apartment_search_2 | **NOT YET EXECUTED** | **NOT YET EXECUTED** | **NOT YET EXECUTED** |
| 6 | return_navigation | **NOT YET EXECUTED** | — | **NOT YET EXECUTED** |
| 7 | ask_open | **NOT YET EXECUTED** | — | **NOT YET EXECUTED** |
| 8 | grounded_qa | **NOT YET EXECUTED** | — | **NOT YET EXECUTED** |
| 9 | safe_no_answer | **NOT YET EXECUTED** | — | **NOT YET EXECUTED** |
| 10 | clean_close | **NOT YET EXECUTED** | — | **NOT YET EXECUTED** |

External-provider dependencies observed (LLM provider/model, Telegram latency,
any rate limiting): **NOT YET EXECUTED**
Deviations / incidents: **NOT YET EXECUTED**

---

## Rehearsal 2 (warm restart) — NOT YET EXECUTED

Same table set as Rehearsal 1. Differences to record: bot restart only (services
restarted per procedure), warm latencies. All fields: **NOT YET EXECUTED**.

| Field | Value |
|---|---|
| Date / UTC start–end | **NOT YET EXECUTED** |
| Git SHA | **NOT YET EXECUTED** — must equal FINAL_SHA |
| `make demo-verify` / prerequisites snapshot | **NOT YET EXECUTED** |
| Bot log archive | `logs/bot-run-rehearsal-2.log` — **NOT YET EXECUTED** |
| Artifact path | **NOT YET EXECUTED** |
| Verdict / journey seconds / within_budget | **NOT YET EXECUTED** |
| Per-step table | **NOT YET EXECUTED** |
| External-provider dependencies / deviations | **NOT YET EXECUTED** |

---

## Rehearsal 3 (warm restart) — NOT YET EXECUTED

Same table set as Rehearsal 1. All fields: **NOT YET EXECUTED**.

| Field | Value |
|---|---|
| Date / UTC start–end | **NOT YET EXECUTED** |
| Git SHA | **NOT YET EXECUTED** — must equal FINAL_SHA |
| `make demo-verify` / prerequisites snapshot | **NOT YET EXECUTED** |
| Bot log archive | `logs/bot-run-rehearsal-3.log` — **NOT YET EXECUTED** |
| Artifact path | **NOT YET EXECUTED** |
| Verdict / journey seconds / within_budget | **NOT YET EXECUTED** |
| Per-step table | **NOT YET EXECUTED** |
| External-provider dependencies / deviations | **NOT YET EXECUTED** |

---

## Post-rehearsal acceptance checklist (#3206)

- [ ] Three `verdict: passed` artifacts exist at the same FINAL_SHA
- [ ] All three journeys `within_budget: true`
- [ ] Cold vs warm latency recorded (rehearsal 1 vs 2–3 totals)
- [ ] External-provider dependencies recorded in #3197 with exact SHA
- [ ] README / DOCKER.md / `telegram_bot/README.md` / `docs/LOCAL-DEVELOPMENT.md`
      reconciled **only** with behavior proven by the final gate; `make docs-check` passes

---

## Verified on the authoring host (2026-09-03, SHA `0e310f7dda680716dd7407dc1dcd0294e625b793`)

The authoring host has **no** Telegram bot token, userbot credentials, LLM key
or BGE-M3 service, so the live journey cannot run here. Everything below was
actually executed against the live local Qdrant :6333 / Redis :6379; the two
`demo-gate` artifact files named here were produced by real runs (gitignored,
kept in the authoring worktree only — they are **not** rehearsal evidence).
Schema-only checks used throwaway `i3206-*` collections, deleted afterwards.

| Runbook step | Command (as run) | Real result |
|---|---|---|
| §1.3 venv | `uv sync --python 3.12` then `--extra telegram` | exit 0 (extra required: base sync lacks `aiogram`) |
| Local quality contract | `make test-core` | **295 passed in 9.69s**, `✓ Monolith core test gate complete` |
| §3.4 verify BEFORE indexes | `uv run --no-sync python -m scripts.demo_bootstrap --verify-only --knowledge-collection i3206-knowledge --apartments-collection i3206-apartments` | **exit 1** — 22 × `[schema_incompatible] ... missing payload index '...' — run make qdrant-ensure-indexes ...` |
| §3.4 remediation | `... python -m scripts.qdrant_ensure_indexes --collection i3206-knowledge --apartments-collection i3206-apartments` | **exit 0** — created all 10 knowledge + 12 apartments payload indexes, `Done.` |
| §3.3 verify AFTER indexes | same `demo_bootstrap --verify-only` line | **exit 0** — `[OK] knowledge/i3206-knowledge: 1 points`, `[OK] apartments/i3206-apartments: 1 points (probes: {'intentional-no-result': 0})`, `Demo bootstrap PASSED...`; shipped-data probes correctly `[SKIP]`ped on non-shipped data |
| §4 prerequisites (qdrant surfaces) | `E2E_QDRANT_DOC_COLLECTION=i3206-knowledge E2E_QDRANT_APARTMENT_COLLECTION=i3206-apartments make demo-gate MODE=--prerequisites-only` | **exit 1 (expected)** — `git ok`, `qdrant ok`, `redis ok`; `telegram`/`golden_queries`/`bge`/`llm` fail with the exact remediation lines quoted in the runbook §4; artifact `reports/demo-gate/demo-gate-0e310f7d-20260903T221058Z.json`; `Readiness gate failed — the bot was NOT contacted.` |
| §4 prerequisites (defaults, unprovisioned) | `make demo-gate MODE=--prerequisites-only` | `qdrant fail` additionally (collections absent); artifact `...221118Z.json` |
| §1.2 Redis / polling lock | redis-py probe | `ping True`, lock key absent (`pttl -2`) — sane state |
| Cleanup | delete `i3206-knowledge`, `i3206-apartments` | done — live Qdrant restored to its prior state |

Not executed here (requires presentation-host credentials/services): §2.1
userbot authorization, §3.2 `make demo-bootstrap` ingest (needs BGE-M3), §5 bot
start, §7 `make demo-gate` full journey, and Rehearsals 1–3.
