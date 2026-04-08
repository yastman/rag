***REMOVED*** ADR-0006: Kommo CRM Integration

**Status:** Accepted

**Date:** 2026-03-01

***REMOVED******REMOVED*** Context

We needed a CRM system for managing:
- Lead capture from Telegram queries
- Contact management
- Deal/pipeline tracking
- Follow-up task creation

***REMOVED******REMOVED*** Decision

Use **Kommo** (formerly amoCRM) as the CRM system.

***REMOVED******REMOVED******REMOVED*** Why Kommo

| Factor | Kommo | Other CRMs |
|--------|-------|------------|
| API | RESTful, well-documented | Varies |
| Telegram integration | Existing bot patterns | Custom |
| Russian market | Strong presence | Varies |
| Pricing | Competitive | Varies |

***REMOVED******REMOVED******REMOVED*** Constraints

1. **OAuth2 authentication** — Requires server-side OAuth flow
2. **Token management** — Long-lived tokens with refresh
3. **Pipeline configuration** — Custom fields for lead scoring

***REMOVED******REMOVED*** Consequences

***REMOVED******REMOVED******REMOVED*** Positive
- Full CRM capabilities for lead management
- Automatic lead capture from conversations
- Pipeline visibility for sales team

***REMOVED******REMOVED******REMOVED*** Negative
- External dependency (Kommo service)
- OAuth complexity in deployment
- Custom field setup required

***REMOVED******REMOVED*** Token Management

Tokens stored in Redis with auto-refresh:

```python
***REMOVED*** Init chain
KOMMO_AUTH_CODE → exchange → tokens in Redis
                  ↓
           Check existing Redis tokens
                  ↓
           Seed from KOMMO_ACCESS_TOKEN env (long-lived token)
```

***REMOVED******REMOVED*** References

- Kommo client: `telegram_bot/services/kommo_client.py`
- Token store: `telegram_bot/services/kommo_token_store.py`
- CRM tools: `telegram_bot/agents/crm_tools.py`
