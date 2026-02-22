---
paths: "**/response_style_detector.py, **/session_summary*.py, **/user_service.py, telegram_bot/config.py"
---

# User Personalization

Response style adaptation and user context tracking.

## Status

| Component | Status | Files |
|-----------|--------|-------|
| CESC (Context-Enabled Semantic Cache) | **Config only — service files removed** | `telegram_bot/config.py` (CESC settings) |
| ResponseStyleDetector | **Implemented** | `telegram_bot/services/response_style_detector.py` |
| SessionSummary | **Implemented** | `telegram_bot/services/session_summary.py` |
| UserService | **Implemented** | `telegram_bot/services/user_service.py` |

## ResponseStyleDetector (#129)

Zero-latency (no LLM) classifier for response length control.

**File:** `telegram_bot/services/response_style_detector.py`

```
Query → regex patterns → StyleInfo(style, difficulty, reasoning)

style:      "short" | "balanced" | "detailed"
difficulty: "easy" | "medium" | "hard"
```

| Trigger type | Examples | Result |
|-------------|----------|--------|
| Detailed keywords | "подробно", "объясни", "сравни", "почему" | `detailed` |
| Short keywords | "кратко", "да или нет", "какая цена", "где находится" | `short` |
| Transactional patterns | "сколько стоит", "до N евро", "есть ли" | `short` |
| Default | — | `balanced` |

Used by `generate_node` to adapt prompt/token limits (`response_style_enabled` flag in GraphConfig).

## UserService

**File:** `telegram_bot/services/user_service.py`

- CRUD operations on `users` table (asyncpg)
- `get_or_create(telegram_id, first_name, language_code)` — upsert on conflict
- `detect_locale(language_code)` — maps Telegram language_code → `ru`/`en`/`uk`

Locale mapping: `ru` → ru, `uk` → uk, `en` → en, `be` → ru (Belarusian fallback). Default: `ru`.

## SessionSummary (CRM)

**File:** `telegram_bot/services/session_summary.py`

Generates structured Pydantic summaries from Q&A dialog for Kommo CRM notes.

```python
class SessionSummary(BaseModel):
    brief: str             # 1-2 sentences: topic + outcome
    client_needs: list[str]
    budget: str | None
    preferences: list[str]
    next_steps: list[str]
    sentiment: Literal["positive", "neutral", "negative"]
```

Uses `responses.parse` (Responses API) with `beta.chat.completions.parse` fallback for older versions.

## CESC Configuration (BotConfig)

CESC config is defined in `telegram_bot/config.py` — service implementation pending:

| Parameter | Env Var | Default | Description |
|-----------|---------|---------|-------------|
| `cesc_enabled` | `CESC_ENABLED` | `true` | Enable CESC personalization |
| `cesc_extraction_frequency` | `CESC_EXTRACTION_FREQUENCY` | `3` | Extract preferences every N queries |
| `user_context_ttl` | `USER_CONTEXT_TTL` | 30 days | Redis storage lifetime |

**Note:** `cesc.py` and `user_context.py` service files no longer exist. `LLMService.generate_text()` (line 353) is documented as "for CESC use" but CESC service layer is not wired up.

## Testing

```bash
pytest tests/unit/test_response_style_detector.py -v
pytest tests/unit/test_user_service.py -v
pytest tests/unit/test_session_summary.py -v
```
