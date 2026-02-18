# ADR: Kommo SDK Feasibility PoC — Decision

**Date:** 2026-02-18
**Issue:** #313 (spike)
**Parent:** #312 (Kommo CRM deal lifecycle)
**Status:** Accepted
**Decision:** **ADOPT** first-party async adapter (`httpx` + `tenacity`)
**Related:** `docs/plans/2026-02-18-kommo-crm-tool-design.md`

## Context

Для реализации Kommo CRM deal lifecycle (#312) нужен Python-клиент для Kommo API v4. Оценили три community SDK и вариант собственного async-адаптера.

**Kommo API ключевые факты:**
- REST API v4, base URL: `https://{subdomain}.kommo.com/api/v4`
- Rate limit: **7 req/s** (IP блокировка при превышении)
- Auth: OAuth 2.0 (access token ~24h, refresh token ~3 мес) + long-lived tokens для private integrations
- Entities: Leads, Contacts, Companies, Tasks, Notes, Pipelines
- Нет официального Python SDK (есть JS SDK, Web SDK, Salesbot SDK)

## Candidates Evaluated

### 1. `Krukov/amocrm_api` — REJECT

| Критерий | Оценка |
|----------|--------|
| GitHub | 111 stars, 21 open issues |
| Last commit | **Dec 2021** (3+ года назад) |
| API version | **v2 only** (v4 не поддерживается) |
| Async | **Нет** — sync `requests` |
| Domain | **Hardcoded** `.amocrm.ru` (не `.kommo.com`) |
| OAuth2 | Да (MemoryTokensStorage, FileStorage, RedisTokensStorage) |
| Python | Не указано, вероятно 3.6+ |
| Typed | Нет |
| Maintenance | **Dormant** — 17 contributors, но активность прекратилась |
| Bus factor | 1 (Krukov) |

**Причины отказа:**
- API v2 — устарел, Kommo перешёл на v4
- Sync-only — не совместим с нашим async стеком (asyncio + LangGraph)
- Домен `.amocrm.ru` захардкожен — наш аккаунт на `.kommo.com`
- 3+ года без обновлений — risk abandoned library

### 2. `GearPlug/kommo-python` — REJECT

| Критерий | Оценка |
|----------|--------|
| GitHub | **5 stars**, 0 open issues |
| Last commit | **Feb 2024** (1 год назад) |
| API version | v4 (единственный SDK с v4!) |
| Async | **Нет** — sync `requests` |
| Domain | `.kommo.com` (корректный) |
| OAuth2 | Да (manual token management) |
| Python | >=3.7 |
| PyPI | `kommo-python` v0.1.2 |
| Typed | Нет |
| Maintenance | **Minimal** — 2 contributors, 1 push за всю историю |
| Bus factor | 1-2 (GearPlug team) |

**Причины отказа:**
- Sync-only (`requests`) — нужен async мост
- Минимальная зрелость (v0.1.2, 5 stars, 2 коммитера)
- Token refresh требует ручного вызова `refresh_access_token()` + `set_token()` — нет auto-refresh
- Нет typed responses, нет retry logic, нет error mapping
- Покрытие API: leads, contacts, companies, webhooks — но нет notes, tasks в документации

### 3. `bzdvdn/amocrm-api-wrapper` — REJECT

| Критерий | Оценка |
|----------|--------|
| GitHub | 21 stars, 1 open issue |
| Last commit | **Apr 2022** (2+ года назад) |
| API version | v2/v4 dual |
| Async | **Нет** — sync |
| Domain | Configurable (плюс) |
| OAuth2 | Legacy auth (login/password) + OAuth2 |
| Python | >=3.6 |
| PyPI | `amocrm-api-wrapper` v0.0.19 |
| Typed | Нет |
| Maintenance | **Dormant** — 75 commits, solo developer |
| Bus factor | 1 (bzdvdn) |

**Причины отказа:**
- Sync-only
- Legacy auth support (ненужная сложность)
- Solo developer, dormant
- v0.0.19 — pre-release quality

### 4. First-Party Async Adapter (`httpx` + `tenacity`) — ADOPT

| Критерий | Оценка |
|----------|--------|
| Async | **Нативный** — `httpx.AsyncClient` + `asyncio` |
| OAuth2 | Auto-refresh в `KommoTokenStore` (Redis-backed) |
| Domain | `.kommo.com` (configurable subdomain) |
| Typed | **Pydantic v2** модели для всех сущностей |
| Retry | `tenacity` exponential backoff + jitter |
| Error mapping | Typed exceptions (`KommoAPIError`, `KommoAuthError`) |
| Rate limiting | Встроенный respect 7 req/s limit |
| Maintenance | **Наша команда** — полный контроль |
| Bus factor | Team (не зависим от external maintainers) |
| Pattern | Уже проверен: `BGEM3Client` в codebase |
| Dependencies | **Нулевые** — `httpx` и `tenacity` уже в проекте |

## Comparison Matrix

| Критерий | Weight | Krukov | GearPlug | bzdvdn | **First-party** |
|----------|--------|--------|----------|--------|-----------------|
| Async native | 25% | 0 | 0 | 0 | **10** |
| OAuth2 auto-refresh | 15% | 7 | 3 | 5 | **10** |
| API v4 support | 15% | 0 | 10 | 7 | **10** |
| Typed responses | 10% | 0 | 0 | 0 | **10** |
| Maintenance / bus factor | 15% | 2 | 3 | 2 | **10** |
| Error handling / retry | 10% | 2 | 1 | 2 | **10** |
| Kommo.com domain | 5% | 0 | 10 | 8 | **10** |
| API coverage (leads, contacts, notes, tasks) | 5% | 7 | 6 | 5 | **10** |
| **Weighted Total** | 100% | **2.1** | **3.0** | **2.5** | **10.0** |

## Conceptual Lifecycle Validation

Проверили, что Kommo API v4 поддерживает весь необходимый deal lifecycle:

| Step | Kommo API | Method | Notes |
|------|-----------|--------|-------|
| 1. Token refresh | `POST /oauth2/access_token` | `grant_type=refresh_token` | Refresh token 3 мес, access ~24h |
| 2. Create/upsert contact | `GET /contacts?query={phone}` + `POST /contacts` | Search by phone, create if not found | Custom fields: PHONE, EMAIL |
| 3. Create lead/deal | `POST /leads` | JSON array body | `pipeline_id`, `price`, `custom_fields_values` |
| 4. Link contact to lead | `POST /leads/{id}/link` | `to_entity_type: "contacts"` | Kommo handles dedup |
| 5. Add note | `POST /leads/{id}/notes` | `note_type: "common"` | Text notes, no size limit documented |
| 6. Create follow-up task | `POST /tasks` | `entity_id`, `entity_type`, `complete_till` | Unix timestamp deadline |

**Rate limit impact:** Полный `finalize_deal` = 5-6 API calls. При rate limit 7 req/s — один lifecycle ≈ 1 секунда. Достаточно для нашего use case (единичные сделки из Telegram).

## Architecture Decision

```
telegram_bot/services/
  kommo_client.py       ← httpx.AsyncClient + tenacity retry
  kommo_tokens.py       ← Redis-backed OAuth2 token store
  kommo_models.py       ← Pydantic v2 request/response models
```

**Паттерн: BGEM3Client**
- Существующий `bge_m3_client.py` (~274 LOC) — проверенный паттерн async HTTP клиента
- Тот же стек: `httpx.AsyncClient` + `tenacity` + typed dataclasses/models
- Connection pooling, granular timeouts, batch support

**Отличие от BGE-M3:** добавляется OAuth2 token management через `KommoTokenStore`:
- Redis hash `kommo:oauth:tokens` — persistence across restarts
- Auto-refresh за 5 мин до expiry
- Force refresh на 401
- Initial exchange auth_code → token pair

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Kommo API v4 breaking changes | Low | High | Pin to documented endpoints, add integration tests |
| Token refresh race condition (concurrent requests) | Medium | Medium | Redis SETNX lock during refresh |
| Rate limit (7 req/s) exceeded | Low | Medium | `tenacity` backoff + queue serialization |
| Kommo account suspended/blocked | Low | High | `KOMMO_ENABLED=false` kill switch, fail-soft |
| OAuth2 refresh token expiry (3 months) | Low | High | Monitoring alert + re-auth procedure documented |

## Consequences

**Positive:**
- Полный контроль над async lifecycle
- Zero new dependencies (httpx, tenacity уже в проекте)
- Typed models → IDE support, runtime validation
- Consistent codebase pattern (BGEM3Client)
- Testable: respx mock для unit tests

**Negative:**
- ~400 LOC нового кода (client + tokens + models) вместо `pip install`
- Ответственность за maintenance Kommo API compatibility
- Нет community support / shared bug fixes

**Trade-off:** 400 LOC собственного кода vs. dependency на dormant/sync SDK с необходимостью async wrapper (~300 LOC) + type stubs (~100 LOC) + risk abandonment. Net cost примерно одинаковый, но контроль и качество значительно выше.

## References

- [Kommo API v4 Overview](https://developers.kommo.com/docs/about-kommo-api)
- [Kommo OAuth 2.0 Documentation](https://developers.kommo.com/docs/oauth-20)
- [Kommo API Rate Limits](https://kommo.com/developers/content/api_v4/recommendations) — 7 req/s
- [Krukov/amocrm_api](https://github.com/Krukov/amocrm_api) — 111 stars, last commit Dec 2021
- [GearPlug/kommo-python](https://github.com/GearPlug/kommo-python) — 5 stars, v0.1.2, last push Feb 2024
- [bzdvdn/amocrm-api-wrapper](https://github.com/bzdvdn/amocrm-api-wrapper) — 21 stars, last commit Apr 2022
- [httpx AsyncClient docs](https://www.python-httpx.org/async/)
- Existing pattern: `telegram_bot/services/bge_m3_client.py`
- Design doc: `docs/plans/2026-02-18-kommo-crm-tool-design.md`
