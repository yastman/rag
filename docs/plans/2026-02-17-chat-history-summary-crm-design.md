# ADR: Chat History + CRM (Kommo) Design

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2026-02-17 |
| **Decision** | Unified agentic runtime: supervisor tools for history, summary, and CRM lifecycle |
| **Related issues** | #305 (Phase 1, DONE), #312 (Phase 2, open), #313 (SDK PoC, open), #310 (monolith removal, open) |
| **Supersedes** | n/a |

## Context

The bot has dual runtime paths (supervisor + monolith) and no CRM integration.
Phase 1 (#305, PR #309 -- merged 2026-02-17) delivered the foundation:
`get_session_turns()`, `SessionSummary`, `generate_summary()`, `format_summary_as_note()`.

## Decision

Build a unified agentic runtime for chat history and CRM:

`Telegram -> LangGraph supervisor tools -> Qdrant history + Redis session -> Kommo -> Langfuse`

## Design Principles

- Supervisor-first runtime (no parallel monolith path in steady-state).
- SDK-first approach: use official/maintained clients, custom adapter only after PoC.
- Fail-soft semantics for CRM write path (do not break user-facing response).
- Idempotency by design for deal/note/task creation operations.

## Functional Blocks

1. History storage/search:
   - long-term: Qdrant (`conversation_history` collection);
   - short-term: Redis (session window, TTL).

2. Session summary:
   - `SessionSummary` structured output (Pydantic v2);
   - `responses.parse` primary + `beta.chat.completions.parse` fallback.

3. CRM lifecycle tools:
   - draft generation from session summary/history;
   - contact upsert by Telegram;
   - deal creation/linking;
   - note/task writeback.

4. Observability:
   - single Langfuse trace tree for supervisor + selected tools + CRM writes.

## Scope Boundaries

In scope:
- history + summary + CRM tools integration via supervisor path;
- local prod-like validation (docker profile + smoke routing);
- typed contracts + unit/integration tests.

Out of scope:
- external MCP-router as primary runtime;
- full ingestion pipeline rework.

## Technical Decisions

1. Kommo integration path:
   - decide via #313 PoC: community SDK vs first-party async adapter.

2. Runtime unification:
   - legacy query path removed in #310;
   - supervisor becomes default path.

3. Observability contract:
   - trace attributes and score names fixed; no duplication between paths.

## Key File References

| File | Purpose | Status |
|------|---------|--------|
| `telegram_bot/services/session_summary.py` | SessionSummary model + generate + format | Exists (Phase 1) |
| `telegram_bot/services/history_service.py` | get_session_turns() | Exists (Phase 1) |
| `telegram_bot/config.py` | Feature flags (session_summary_enabled, kommo_enabled, use_supervisor) | Exists (Phase 1) |
| `telegram_bot/agents/tools.py` | Supervisor tools (CRM tools to be added) | Exists |
| `telegram_bot/bot.py` | PropertyBot orchestrator | Exists |
| `telegram_bot/services/kommo_client.py` | Kommo async client | TO-CREATE (Phase 2, #312) |
| `telegram_bot/services/deal_draft.py` | DealDraft from SessionSummary | TO-CREATE (Phase 2, #312) |
| `src/evaluation/search_engines.py` | Evaluation search engines (SDK migration target) | Exists (#314) |

## Risks

1. `langfuse.openai.AsyncOpenAI` compatibility with `responses.parse` in target environment (#315).
2. Architectural drift during dual-path existence (supervisor + monolith).
3. Loss of idempotency during CRM write retries.

## Validation

- `make check`
- `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`
- `uv run pytest tests/integration/test_graph_paths.py -v`
- targeted CRM/supervisor tool tests
