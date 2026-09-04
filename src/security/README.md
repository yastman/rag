# security/

## Purpose

Security guardrails for production RAG deployment.
Owns source-level security helpers under `src/security/`.
Provides PII redaction helpers for sensitive data that must reach logs or
traces only in redacted form. Runtime pipelines do not log raw user queries,
generated rewrites, hypothetical documents, transliterations, or injection
excerpts at all: the rewrite, preprocessing, semantic-cache, and guard paths
emit metadata only (request identifiers, types, categories, sizes, latency,
model, cache outcome). This guarantee is executable:
`tests/contract/test_log_privacy_contract.py` sends e-mail, phone, and
passport canaries through those paths and asserts none reaches any log
level or exception text (#3356).

## Files

| File | Purpose |
|------|---------|
| `pii_redaction.py` | PII redaction for Ukrainian data (passport, tax ID, phone, email, Telegram user ID) |

## What it does

`PIIRedactor` detects and replaces sensitive patterns in query strings before logging:

- Ukrainian passport numbers (`АА123456` → `[PASSPORT]`)
- Tax IDs / РНОКПП (10 digits → `[TAX_ID]`)
- Phone numbers (`+380...` or `0...` → `[PHONE]`)
- Email addresses (`user@example.com` → `[EMAIL]`)
- Telegram user IDs (9–10 digit standalone numbers → `[USER_ID]`)

The class also provides `mask()` for recursive redaction in dicts and lists.

## Usage

```python
from src.security.pii_redaction import PIIRedactor

redactor = PIIRedactor()
redacted, meta = redactor.redact_query("Паспорт АА123456")
```

## Boundaries

- The pipeline log boundary is "metadata only, no user text" — enforced by
  `tests/contract/test_log_privacy_contract.py` (#3356), not by a manual
  redaction step. `PIIRedactor` remains available for callers that
  intentionally log redacted content.
- Search, embeddings, cache keys, and returned behavior are unaffected: the
  original query is still used everywhere except in logs
- Does not perform authentication or authorization
- Does not own Telegram middleware policy; see [`../../telegram_bot/middlewares/`](../../telegram_bot/middlewares/)

## Focused checks

```bash
uv run pytest tests/unit/security/ -q
```

## See Also

- [`telegram_bot/middlewares/`](../../telegram_bot/middlewares/) — Request middleware
