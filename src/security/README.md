# security/

## Purpose

Security guardrails for production RAG deployment.
Owns source-level security helpers under `src/security/`.
Currently provides PII redaction before sensitive data reaches logs or traces.

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

- Redacts **before** logging to Langfuse/MLflow; original query is still used for search accuracy
- Does not perform authentication or authorization
- Does not own Telegram middleware policy; see [`../../telegram_bot/middlewares/`](../../telegram_bot/middlewares/)

## Focused checks

```bash
uv run pytest tests/unit/security/ -q
```

## See Also

- [`docs/ERROR_RESPONSES.md`](../../docs/ERROR_RESPONSES.md) — Error taxonomy
- [`telegram_bot/middlewares/`](../../telegram_bot/middlewares/) — Request middleware
