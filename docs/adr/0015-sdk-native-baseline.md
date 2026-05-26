# ADR-0015: SDK-Native Baseline (aiogram, LangGraph, Langfuse, Qdrant)

**Status:** Accepted

**Date:** 2026-05-25

**Closes:** [#1538](https://github.com/yastman/rag/issues/1538) (audit)

**Related:** [#1535](https://github.com/yastman/rag/issues/1535) (voice path), [#1232](https://github.com/yastman/rag/issues/1232) / [#2055](https://github.com/yastman/rag/issues/2055) (phone collector FSM exception), [#2049](https://github.com/yastman/rag/issues/2049) (reverse-layering cleanup), [#2112](https://github.com/yastman/rag/pull/2112) (draft-streaming SDK contract follow-up)

## Context

A 2026-05-14 audit (issue #1538) catalogued where the codebase uses SDK-native patterns versus custom implementations across aiogram, LangChain/LangGraph v1, Langfuse, and Qdrant. The audit was informational — it did not propose specific PRs, but it did rank custom code by whether an SDK equivalent exists and whether the custom implementation is justified.

This ADR distils the audit's conclusions into the project's working baseline so the policy survives the issue closing. Future PRs that add custom code in any of these areas must justify the deviation against the baseline below.

## Decision

The default for every new feature is **SDK-native first**. Custom implementations are allowed only when documented in this ADR (under "Justified custom code") or when added with a per-PR exception that updates this ADR.

### SDK-native baseline (locked in)

| Area | SDK / pattern | Where |
|---|---|---|
| Bot handlers | `aiogram.Router` + `Dispatcher.include_router(...)` | `telegram_bot/bot.py`, `telegram_bot/handlers/` |
| FSM dialogs | `aiogram_dialog.Dialog` with `Window`, `MessageInput`, `Select`, `Cancel`, `Column`, etc. | `telegram_bot/dialogs/*.py`, locked by `tests/unit/dialogs/test_dialogs_fsm_coverage.py` and per-dialog migration contracts (`test_demo_dialog_*`, `test_crm_quick_actions_fsm_migration_contract.py`) |
| Agent (text path) | `langchain.agents.create_agent` v1 with `before_model` middleware | `telegram_bot/bot.py::_handle_query_supervisor`, `telegram_bot/agents/` |
| Agent draft streaming | LangGraph `agent.astream(..., stream_mode=["messages", "values"])` plus direct Telegram `send_message_draft(...)`; no `DraftStreamer` abstraction | `telegram_bot/_bot_streaming.py::_stream_agent_to_draft`, `tests/unit/services/test_draft_streamer_removed.py`; follow-up PR #2112 pins the current contract |
| History trimmer | `before_model` middleware | `telegram_bot/agents/` |
| Observability — traces | Langfuse SDK + OTEL with graceful Python 3.14 degradation | `src/observability.py` (canonical), `telegram_bot/observability.py` (re-export shim) |
| Observability — metrics | `prometheus_client.Histogram` + `Counter` registered against the default `prometheus_client.REGISTRY` | `src/runtime/services/metrics.py` |
| Observability — error tracking | `sentry-sdk` 2.x with `EventScrubber`, `before_send` PII redaction, `send_default_pii=False` | `src/observability_sentry.py` |
| Vector search | Qdrant SDK `query_points` + `Prefetch` + `RrfQuery` for hybrid search; server-side ColBERT rerank via the ColBERT vector field | `src/runtime/services/qdrant.py` |
| Ingestion | CocoIndex SDK | `src/ingestion/cocoindex_flow.py` |
| Type checking | MyPy + Ruff | `pyproject.toml`, `.pre-commit-config.yaml` |
| Security | Bandit + Gitleaks via pre-commit and CI workflow | `.github/workflows/ci.yml`, `.pre-commit-config.yaml` |

### Tracked migrations off custom code (where the SDK already exists)

These are not justified deviations — they are tracked work items kept in flight via dedicated issues. Adding new code that follows the deprecated pattern is a regression and is blocked by the relevant contract test or umbrella issue.

| Custom code | SDK target | Tracked under |
|---|---|---|
| Voice path 11-node `StateGraph` (`telegram_bot/graph/graph.py::build_graph`) | `langchain.agents.create_agent` (already used on text path) | [#1535](https://github.com/yastman/rag/issues/1535), child slices [#2050](https://github.com/yastman/rag/issues/2050) / [#2051](https://github.com/yastman/rag/issues/2051) / [#2052](https://github.com/yastman/rag/issues/2052) |
| Regex-based prompt-injection guard (`graph/nodes/guard.py`) | LangChain `InjectedState` + middleware | low-priority follow-up; current regex covers the threat model |

### Justified custom code (no SDK equivalent or domain-specific)

The following modules implement behavior that the underlying SDK does not provide; they stay custom by design and are not migration targets. New code that fits these criteria does not require an exception in this ADR.

| Module | Why custom |
|---|---|
| `src/runtime/integrations/cache.py` (5-tier Redis cache) | RedisVL ships `SemanticCache`; the project layers four additional tiers (embeddings / sparse / search / rerank) on top with per-query-type thresholds and TTLs |
| `telegram_bot/services/apartment_extraction_pipeline.py` | Domain-specific filter extraction (Russian-language regex + LLM fallback) |
| `telegram_bot/services/forum_bridge.py` | Telegram-specific feature (manager ↔ client topic relay) — no SDK |
| `telegram_bot/services/kommo_client.py` | Kommo CRM third-party API — no maintained Python SDK |
| `telegram_bot/handlers/phone_collector.py` raw `aiogram.fsm` | Justified #1232/#2055 exception: Telegram one-tap contact capture requires `KeyboardButton(request_contact=True)` via `ReplyKeyboardMarkup`; aiogram-dialog does not provide an equivalent contact-share widget, and replacing it with inline buttons would degrade lead-capture UX |
| `telegram_bot/_bot_streaming.py::_stream_agent_to_draft` | Thin bridge from LangGraph SDK streaming to Telegram draft API. It already consumes `agent.astream(..., stream_mode=["messages", "values"])` directly and exists only to throttle/filter draft writes, so it is not a migration target |
| `src/security/pii_redaction.py` | Locale-specific patterns (Ukrainian passport / РНОКПП / phone formats) that vendor scrubbers do not model |
| `src/runtime/services/metrics.py::PipelineMetrics` slim facade | Thin singleton over the SDK Histogram + Counter; preserves existing `record(stage, ms)` / `inc(name)` import surface used in 5 graph-node call-sites |

## Reopen Conditions

This ADR should be **revisited** when **any** of these signals appear:

1. **New SDK release** changes the recommendation for one of the rows in the "tracked migrations" table (e.g. LangGraph adds a recommended pattern that supersedes `create_agent` for the voice path).
2. **A new "justified custom" claim** — when adding code in this category, append a row above and document the SDK gap.
3. **A migration completes** (e.g. voice path moves to `create_agent`) — drop the row from "tracked migrations" and add a contract test pinning the migration if it is reversible.
4. **A new SDK area is introduced** (e.g. a different RAG framework, an alternative tracing backend) — add a row to the SDK-native baseline table.

## Consequences

### Positive

- A reviewer can answer "should this be custom or SDK?" by consulting one document instead of running an audit.
- Tracked migrations have explicit owners (issue numbers) so progress is visible.
- Justified custom code is auditable — the next reviewer can challenge a claim against the documented criteria.
- The audit (#1538) does not have to live as a stale open issue forever; the conclusions are pinned here.

### Negative

- The ADR must be touched whenever an SDK landscape shifts (medium maintenance cost).
- A reviewer who skips this document might still propose a custom fix in an SDK-supported area; mitigation is the per-area contract tests (e.g. `test_dialogs_fsm_coverage.py`, `test_crm_quick_actions_fsm_migration_contract.py`, the layering ratchet).

## Implementation

This ADR is documentation only. The behavioral guarantees are enforced by existing contract tests (listed inline above). Adding rows to the "tracked migrations" or "justified custom" tables does not require code changes — only updates to this file.

## References

- Issue [#1538](https://github.com/yastman/rag/issues/1538) — original SDK-vs-custom audit (closed by this ADR)
- Issue [#1535](https://github.com/yastman/rag/issues/1535) — voice path migration umbrella (still open)
- Issue [#1232](https://github.com/yastman/rag/issues/1232) — FSM-to-dialog migration tracker; this ADR does not close it
- Issue [#2055](https://github.com/yastman/rag/issues/2055) — phone collector design exception for one-tap contact share
- PR [#2112](https://github.com/yastman/rag/pull/2112) — follow-up contract pin for SDK-native draft streaming
- ADR [0010](0010-voice-path-create-agent-migration-plan.md) — voice path migration plan
- ADR [0012](0012-langgraph-orchestration.md) — LangGraph orchestration
