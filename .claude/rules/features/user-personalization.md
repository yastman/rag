---
paths: "**/cesc*.py, **/user_context*.py"
---

# User Personalization (CESC)

Context-Enabled Semantic Cache with user preferences.

## Purpose

Personalize cached responses based on user history and preferences without re-running full RAG.

## Architecture

```
Query → is_personalized_query()?
     → [NO: return generic cached response]
     → [YES: load user context → CESCPersonalizer → adapted response]
```

## Key Files

| File | Line | Description |
|------|------|-------------|
| `telegram_bot/services/cesc.py` | 14 | PERSONAL_MARKERS patterns |
| `telegram_bot/services/cesc.py` | 39 | is_personalized_query() |
| `telegram_bot/services/cesc.py` | 72 | CESCPersonalizer class |
| `telegram_bot/services/user_context.py` | 12 | UserContextService |

## CESC Flow

1. **Check personalization needed:** `is_personalized_query(query, context)`
2. **Skip if generic:** Return cached response as-is
3. **Load context:** `user_context_service.get_context(user_id)`
4. **Personalize:** `cesc_personalizer.personalize(cached, context, query)`
5. **Return adapted response**

## Personal Markers

Triggers personalization:

| Pattern | Example |
|---------|---------|
| `\bмне\b` | "покажи мне квартиры" |
| `\bмой бюджет\b` | "в рамках моего бюджета" |
| `\bкак в прошлый раз\b` | "как в прошлый раз" |
| `\bfor me\b` | "find for me" |

## User Context Structure

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

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `context_ttl` | 30 days | Redis storage lifetime |
| `extraction_frequency` | 3 | Extract preferences every N queries |

## Common Patterns

### Check if personalization needed

```python
from telegram_bot.services.cesc import is_personalized_query

if is_personalized_query(query, user_context):
    # Run CESC personalization
    pass
else:
    # Return generic cached response
    pass
```

### Get user context

```python
from telegram_bot.services.user_context import UserContextService

service = UserContextService(cache_service, llm_service)
context = await service.get_context(user_id)
```

### Update from query

```python
# Extracts preferences every 3rd query
context = await service.update_from_query(user_id, query)
```

### Personalize response

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

## Preference Extraction

LLM extracts preferences from queries:

```
Query: "квартира в Несебре до 70000"
Extracted: {"cities": ["Несебр"], "budget_max": 70000}
```

Preferences merge over time:
- Cities: accumulate (deduplicated)
- Scalars (budget, rooms): overwrite

## Dependencies

- Redis: user context storage (`user_context:{user_id}`)
- LLM: preference extraction, personalization

## Testing

```bash
pytest tests/unit/test_cesc.py -v
pytest tests/unit/test_user_context.py -v
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| Context not persisting | Check Redis connection |
| Over-personalization | Tune personal markers |
| Extraction failing | Falls back to empty preferences |

## Development Guide

### Adding new personal marker

```python
# telegram_bot/services/cesc.py
PERSONAL_MARKERS = [
    ...
    r"\bnew pattern\b",
]
```

### Adding new preference field

1. Add to extraction prompt in `UserContextService`
2. Add to `_merge_preferences()` logic
3. Add to `CESCPersonalizer` prompt template
