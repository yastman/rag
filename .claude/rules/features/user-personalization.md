---
paths: "**/cesc*.py, **/user_context*.py"
---

***REMOVED*** User Personalization (CESC)

Context-Enabled Semantic Cache with user preferences.

***REMOVED******REMOVED*** Purpose

Personalize cached responses based on user history and preferences without re-running full RAG.

***REMOVED******REMOVED*** Architecture

```
Query → is_personalized_query()?
     → [NO: return generic cached response]
     → [YES: load user context → CESCPersonalizer → adapted response]
```

***REMOVED******REMOVED*** Key Files

| File | Line | Description |
|------|------|-------------|
| `telegram_bot/services/cesc.py` | 14 | PERSONAL_MARKERS patterns |
| `telegram_bot/services/cesc.py` | 39 | is_personalized_query() |
| `telegram_bot/services/cesc.py` | 72 | CESCPersonalizer class |
| `telegram_bot/services/user_context.py` | 12 | UserContextService |

***REMOVED******REMOVED*** CESC Flow

1. **Check personalization needed:** `is_personalized_query(query, context)`
2. **Skip if generic:** Return cached response as-is
3. **Load context:** `user_context_service.get_context(user_id)`
4. **Personalize:** `cesc_personalizer.personalize(cached, context, query)`
5. **Return adapted response**

***REMOVED******REMOVED*** Personal Markers

Triggers personalization:

| Pattern | Example |
|---------|---------|
| `\bмне\b` | "покажи мне квартиры" |
| `\bмой бюджет\b` | "в рамках моего бюджета" |
| `\bкак в прошлый раз\b` | "как в прошлый раз" |
| `\bfor me\b` | "find for me" |

***REMOVED******REMOVED*** User Context Structure

```json
{
  "user_id": 123456,
  "language": "ru",
  "preferences": {
    "cities": ["Несебр", "Бургас"],
    "budget_max": 80000,
    "property_types": ["apartment"],
    "rooms": 2
  },
  "profile_summary": "Интересуется: Несебр, Бургас. Бюджет до 80000€",
  "interaction_count": 15,
  "last_queries": ["...", "..."],
  "created_at": "2026-01-15T...",
  "updated_at": "2026-02-02T..."
}
```

***REMOVED******REMOVED*** Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `context_ttl` | 30 days | Redis storage lifetime |
| `extraction_frequency` | 3 | Extract preferences every N queries |

***REMOVED******REMOVED*** Common Patterns

***REMOVED******REMOVED******REMOVED*** Check if personalization needed

```python
from telegram_bot.services.cesc import is_personalized_query

if is_personalized_query(query, user_context):
    ***REMOVED*** Run CESC personalization
    pass
else:
    ***REMOVED*** Return generic cached response
    pass
```

***REMOVED******REMOVED******REMOVED*** Get user context

```python
from telegram_bot.services.user_context import UserContextService

service = UserContextService(cache_service, llm_service)
context = await service.get_context(user_id)
```

***REMOVED******REMOVED******REMOVED*** Update from query

```python
***REMOVED*** Extracts preferences every 3rd query
context = await service.update_from_query(user_id, query)
```

***REMOVED******REMOVED******REMOVED*** Personalize response

```python
from telegram_bot.services.cesc import CESCPersonalizer

personalizer = CESCPersonalizer(llm_service)

if personalizer.should_personalize(user_context):
    response = await personalizer.personalize(
        cached_response=cached,
        user_context=context,
        query=query,
    )
```

***REMOVED******REMOVED*** Preference Extraction

LLM extracts preferences from queries:

```
Query: "квартира в Несебре до 70000"
Extracted: {"cities": ["Несебр"], "budget_max": 70000}
```

Preferences merge over time:
- Cities: accumulate (deduplicated)
- Scalars (budget, rooms): overwrite

***REMOVED******REMOVED*** Dependencies

- Redis: user context storage (`user_context:{user_id}`)
- LLM: preference extraction, personalization

***REMOVED******REMOVED*** Testing

```bash
pytest tests/unit/test_cesc.py -v
pytest tests/unit/test_user_context.py -v
```

***REMOVED******REMOVED*** Troubleshooting

| Error | Fix |
|-------|-----|
| Context not persisting | Check Redis connection |
| Over-personalization | Tune personal markers |
| Extraction failing | Falls back to empty preferences |

***REMOVED******REMOVED*** Development Guide

***REMOVED******REMOVED******REMOVED*** Adding new personal marker

```python
***REMOVED*** telegram_bot/services/cesc.py
PERSONAL_MARKERS = [
    ...
    r"\bnew pattern\b",
]
```

***REMOVED******REMOVED******REMOVED*** Adding new preference field

1. Add to extraction prompt in `UserContextService`
2. Add to `_merge_preferences()` logic
3. Add to `CESCPersonalizer` prompt template
