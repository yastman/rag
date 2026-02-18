# Kommo CRM Deal Lifecycle via Supervisor Tools — Design

**Date:** 2026-02-18
**Issue:** #312 (Phase 2), #313 (SDK PoC), #324 (execution plan)
**Epic:** #263 (supervisor migration)
**Branch:** `feat/kommo-crm-tool`
**Status:** Approved

## Summary

Реализация полного Kommo CRM deal lifecycle через supervisor tools. Включает async HTTP adapter (`KommoClient`), OAuth2 token management (Redis), 7 supervisor tools и LLM-based deal draft extraction.

## Decision: First-Party Async Adapter

**Выбор:** собственный async adapter на `httpx` + `tenacity`.

**Причины:**
- Нет официального Python SDK от Kommo
- Community SDKs (`Krukov/amocrm_api`, `GearPlug/kommo-python`, `bzdvdn/amocrm-api-wrapper`) — все sync-only, устаревшие, привязаны к `.amocrm.ru`
- Паттерн проекта: `BGEM3Client` (async httpx + typed responses)
- Best practice 2026: `httpx.AsyncClient` + connection pooling + granular timeouts

**Отвергнуто:**
- Community SDK wrapper (sync→async мост, risk abandoned library)
- MCP Server (out of scope per #312, overhead, #232 не реализован)

## Architecture

### Подход: Модульный CRM пакет

```
telegram_bot/
  agents/
    crm_tools.py              # 7 CRM tool factories
  services/
    kommo_client.py            # KommoClient (async httpx, OAuth2 auto-refresh)
    kommo_models.py            # Pydantic v2 models
    kommo_tokens.py            # KommoTokenStore (Redis-backed)
  config.py                    # + KOMMO_* env vars
  bot.py                       # + conditional CRM tools registration
```

### Supervisor Integration

CRM tools регистрируются условно при `KOMMO_ENABLED=true`:

```python
# bot.py: _handle_query_supervisor()
tools = [rag_agent, direct_response]
if self._history_service:
    tools.append(history_search)
if self.config.kommo_enabled and self._kommo_client:
    tools.extend(create_crm_tools(
        kommo=self._kommo_client,
        llm=self._llm,
        history_service=self._history_service,
    ))
supervisor_graph = build_supervisor_graph(supervisor_llm=supervisor_llm, tools=tools)
```

## KommoClient

### API Contract

```python
class KommoClient:
    """Async Kommo CRM API adapter."""

    def __init__(self, subdomain: str, token_store: KommoTokenStore):
        self._base_url = f"https://{subdomain}.kommo.com/api/v4"
        self._token_store = token_store
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=5),
        )

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """Auto-refresh token, retry on 401."""
        token = await self._token_store.get_valid_token()
        headers = {"Authorization": f"Bearer {token}"}
        response = await self._client.request(method, path, headers=headers, **kwargs)
        if response.status_code == 401:
            token = await self._token_store.force_refresh()
            headers["Authorization"] = f"Bearer {token}"
            response = await self._client.request(method, path, headers=headers, **kwargs)
        response.raise_for_status()
        return response.json()

    # CRUD
    async def create_lead(self, lead: LeadCreate) -> Lead: ...
    async def update_lead(self, lead_id: int, data: LeadUpdate) -> Lead: ...
    async def create_contact(self, contact: ContactCreate) -> Contact: ...
    async def upsert_contact(self, phone: str, data: ContactCreate) -> Contact: ...
    async def link_contact_to_lead(self, lead_id: int, contact_id: int) -> None: ...
    async def add_note(self, entity_type: str, entity_id: int, text: str) -> Note: ...
    async def create_task(self, task: TaskCreate) -> Task: ...
    async def list_pipelines(self) -> list[Pipeline]: ...

    async def close(self):
        await self._client.aclose()
```

### Kommo API Endpoints Used

| Operation | Method | Endpoint |
|-----------|--------|----------|
| Create lead | POST | `/leads` |
| Update lead | PATCH | `/leads/{id}` |
| Create contact | POST | `/contacts` |
| Search contact | GET | `/contacts?query={phone}` |
| Link contact | POST | `/leads/{id}/link` |
| Add note | POST | `/leads/{id}/notes` |
| Create task | POST | `/tasks` |
| List pipelines | GET | `/leads/pipelines` |
| Token refresh | POST | `/oauth2/access_token` |

## Token Management

### KommoTokenStore (Redis-backed)

```python
class KommoTokenStore:
    REDIS_KEY = "kommo:oauth:tokens"
    REFRESH_BUFFER_SEC = 300  # refresh 5 min before expiry

    def __init__(self, redis_url, client_id, client_secret, subdomain, redirect_uri): ...

    async def get_valid_token(self) -> str:
        """Return valid access_token, refreshing if near expiry."""

    async def force_refresh(self) -> str:
        """Force token refresh via POST /oauth2/access_token."""

    async def initialize(self, authorization_code: str | None = None):
        """First-time: exchange auth_code → tokens. After: load from Redis."""
```

**Token lifecycle:**
1. Initial setup: `authorization_code` → exchange → `{access_token, refresh_token, expires_in}`
2. Runtime: `get_valid_token()` checks TTL, auto-refreshes if < 5 min remaining
3. Fallback: `force_refresh()` on 401 response

**Storage format (Redis hash):**
```
kommo:oauth:tokens → {
    access_token: "...",
    refresh_token: "...",
    expires_at: 1739900000,  # Unix timestamp
    subdomain: "mycompany"
}
```

## CRM Tools (7 tools)

### Tool List

| # | Tool | Description | Kommo API | Idempotency |
|---|------|-------------|-----------|-------------|
| 1 | `crm_generate_deal_draft` | LLM extracts DealDraft from chat history | LLM call (no Kommo) | Stateless |
| 2 | `crm_upsert_contact` | Find/create contact by phone | GET+POST /contacts | Phone dedup |
| 3 | `crm_create_deal` | Create lead in pipeline | POST /leads | session_id field |
| 4 | `crm_link_contact_to_deal` | Bind contact ↔ lead | POST /leads/{id}/link | Kommo dedup |
| 5 | `crm_add_note` | Attach chat summary as note | POST /leads/{id}/notes | — |
| 6 | `crm_create_followup_task` | Create follow-up task | POST /tasks | — |
| 7 | `crm_finalize_deal` | Orchestrator: steps 1-6 in sequence | All above | idempotency_key |

### Tool Factory Pattern

```python
def create_crm_tools(*, kommo: KommoClient, llm: Any, history_service: Any) -> list[Any]:
    @tool
    async def crm_generate_deal_draft(query: str, config: RunnableConfig) -> str:
        """Generate a structured deal draft from chat history using LLM extraction."""
        user_id, session_id = _get_user_context(config)
        history = await history_service.get_recent(user_id, session_id)
        draft = await _extract_deal_data(llm, history)
        return draft.model_dump_json()

    @tool
    async def crm_finalize_deal(query: str, config: RunnableConfig) -> str:
        """End-to-end deal creation: contact → deal → link → note → task."""
        # Orchestrates all steps, idempotency via session_id
        ...

    return [crm_generate_deal_draft, crm_upsert_contact, crm_create_deal,
            crm_link_contact_to_deal, crm_add_note, crm_create_followup_task,
            crm_finalize_deal]
```

### DealDraft Model

```python
class DealDraft(BaseModel):
    """Structured deal data extracted from chat history by LLM."""
    client_name: str | None = None
    phone: str | None = None
    email: str | None = None
    budget: int | None = None
    property_type: str | None = None
    location: str | None = None
    notes: str | None = None
    source: str = "telegram_bot"
```

## Data Flow

```
User: "создай сделку по нашему разговору"
  │
  ▼
Supervisor (LLM) → selects crm_finalize_deal
  │
  ▼
crm_finalize_deal(config: {user_id, session_id})
  │
  ├─1. history_service.get_recent(user_id, session_id) → chat messages
  ├─2. LLM extraction → DealDraft(name, phone, budget, property_type)
  ├─3. kommo.upsert_contact(phone, ContactCreate(...)) → contact_id
  ├─4. kommo.create_lead(LeadCreate(name, budget, pipeline_id, custom: {session_id})) → lead_id
  ├─5. kommo.link_contact_to_lead(lead_id, contact_id)
  ├─6. kommo.add_note("leads", lead_id, chat_summary)
  └─7. kommo.create_task(TaskCreate(lead_id, "Follow up", due_at=+24h))
  │
  ▼
Return: "Сделка #12345 создана в pipeline 'Недвижимость'.
Контакт: Иван (+380....). Задача follow-up назначена."
```

## Configuration

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `KOMMO_ENABLED` | `false` | No | Feature flag — CRM tools off by default |
| `KOMMO_SUBDOMAIN` | — | Yes* | Account subdomain (e.g. `mycompany`) |
| `KOMMO_CLIENT_ID` | — | Yes* | OAuth2 integration client ID |
| `KOMMO_CLIENT_SECRET` | — | Yes* | OAuth2 integration client secret |
| `KOMMO_REDIRECT_URI` | — | Yes* | OAuth2 redirect URI |
| `KOMMO_AUTH_CODE` | — | One-time | Initial authorization code (exchanged on first boot) |
| `KOMMO_DEFAULT_PIPELINE_ID` | — | Yes* | Default pipeline ID for new leads |
| `KOMMO_RESPONSIBLE_USER_ID` | — | No | Default responsible user for tasks |

*Required when `KOMMO_ENABLED=true`

## Observability (Langfuse Scores)

Per #312:

| Score | Type | When |
|-------|------|------|
| `crm_deal_created` | BOOLEAN | After successful deal creation |
| `crm_deal_create_latency_ms` | NUMERIC | Time for full finalize flow |
| `crm_deal_idempotent_skip` | BOOLEAN | When duplicate session_id detected |
| `crm_task_created` | BOOLEAN | After follow-up task creation |
| `crm_write_success` | BOOLEAN | Overall CRM write result |
| `crm_contact_upserted` | BOOLEAN | Contact found or created |

All CRM tools decorated with `@observe(name="crm-*")` for Langfuse span hierarchy.

## Idempotency & Safety

1. **Contact upsert:** search by phone before creating → dedup
2. **Deal creation:** `session_id` stored in Kommo custom field → check before creating
3. **Finalize orchestrator:** `idempotency_key = f"{user_id}:{session_id}"` stored in Redis → skip on repeat
4. **Fail-soft:** CRM errors don't break main RAG pipeline (logged, scored, user notified)
5. **Rollback:** `KOMMO_ENABLED=false` disables all CRM tools, zero impact on query availability

## Error Handling

| Error | Action |
|-------|--------|
| Kommo API 401 | Auto-refresh token, retry once |
| Kommo API 429 | Exponential backoff (tenacity) |
| Kommo API 5xx | Retry 3x with backoff, then fail-soft |
| Token refresh fails | Log error, disable CRM tools for session, alert |
| Network timeout | httpx timeout (30s), retry once |
| Invalid DealDraft (LLM) | Return partial draft, ask user to confirm/complete |

## Test Plan

### Unit Tests
- `test_kommo_client.py` — CRUD operations with httpx mock (respx)
- `test_kommo_tokens.py` — token lifecycle, auto-refresh, Redis mock
- `test_crm_tools.py` — all 7 tools with mocked KommoClient
- `test_deal_draft_generation.py` — LLM extraction with mock responses
- `test_finalize_deal_from_session.py` — orchestrator flow, idempotency

### Integration Tests
- `test_kommo_deal_lifecycle.py` — end-to-end with Kommo sandbox (if available)

## Dependencies

**New:**
- `tenacity` (already in project for retry logic)
- No new packages required — `httpx` already a dependency

**Existing (reused):**
- `httpx` (async HTTP)
- `redis` (token storage)
- `pydantic` (models)
- `langfuse` (observability)

## Future: Migration to Postgres

When Postgres is added (#384 lead scoring), token storage migrates from Redis to Postgres. `KommoTokenStore` interface stays the same — swap implementation.

## Future: MCP Server

When #232 (MCP tools server) is implemented, CRM tools can be exposed via MCP alongside RAG tools. Current modular design supports this — `KommoClient` + tools are self-contained.
