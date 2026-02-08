# Telegram Bot Go-Live Bug Register

Date: 2026-02-06
Project: `/opt/rag-fresh`
Source of truth for Telegram bot bugs found during review.

## Rules

- `ACTIVE` section contains only currently open and reproducible bugs.
- After fix + verification, bug must be removed from `ACTIVE` and moved to `CLOSED`.
- If a bug is not reproducible anymore, it should be cleaned from `ACTIVE` immediately.

## Current Runtime Status

- `make test-bot-health-vps` passes (Qdrant + LiteLLM reachable).
- Bot receives Telegram updates.
- RAG path still has a reproducible runtime failure (see `BUG-001`).

## ACTIVE Bugs

| ID | Severity | Bug | Evidence | Impact | Verification |
|---|---|---|---|---|---|
| BUG-001 | Critical | RAG handler crashes due to rerank cache API mismatch | Call with kwargs in `telegram_bot/bot.py:432`; method signature expects positional in `telegram_bot/services/cache.py:683`; runtime error in `vps-bot` logs: `TypeError ... unexpected keyword argument 'query_embedding'` | User requests in RAG path fail, update marked not handled | Reproduced 2026-02-06 |
| BUG-002 | High | Rerank cache contract drift (payload/key schema inconsistency) | Stored payload created as tuples in `telegram_bot/bot.py:457`; cache method typed as `list[dict[str, Any]]` in `telegram_bot/services/cache.py:731`; call site passes `collection`, key builder ignores it in `telegram_bot/services/cache.py:702` | Risk of unstable cache behavior and cross-collection key collisions after API fix | Confirmed by code review 2026-02-06 |
| BUG-003 | High | Unit tests do not guard real cache API compatibility | Cache methods fully mocked in `tests/unit/test_bot_scores.py:213` and `tests/unit/test_bot_scores.py:217`; no contract test for real `PropertyBot -> CacheService` call signature | Signature regressions reach production undetected | Confirmed by code review 2026-02-06 |
| BUG-004 | Medium | QueryAnalyzer timeout causes degraded responses | `httpx.AsyncClient(timeout=30.0)` in `telegram_bot/services/query_analyzer.py:28`; `httpx.ReadTimeout` observed in `vps-bot` logs | Slower responses and fallback mode instead of extracted filters | Reproduced in logs 2026-02-06 |
| BUG-005 | Medium | Langfuse bot observability is disabled in VPS | Repeated warnings in `vps-bot` logs about missing `LANGFUSE_PUBLIC_KEY` | No clean traces, increased warning noise during incidents | Reproduced 2026-02-06 |

## CLOSED Bugs

- None yet.

## Next Verification Pass

1. Fix `BUG-001` and `BUG-002` together (single cache contract update).
2. Add regression test for `BUG-003`.
3. Re-run with real Telegram message and ensure no `TypeError` in last 200 bot log lines.
