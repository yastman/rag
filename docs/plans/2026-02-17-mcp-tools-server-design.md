# MCP Tools Server — Design Document

**Issue:** #232 — `feat(agent): MCP server for bot tools`
**Date:** 2026-02-17
**Status:** Research / Design

---

## 1. Контекст и цели

### Текущее состояние

| Consumer | Способ доступа к RAG | Проблема |
|----------|---------------------|----------|
| Telegram Bot | Прямой import `build_graph()` | Тесная связанность, нет изоляции |
| Voice Agent (LiveKit) | REST POST `/query` (httpx) | Нет стандартизации, нет tool discovery |
| Внешние агенты | Нет | Невозможно подключить |

### Целевое состояние

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Telegram Bot │     │ Voice Agent  │     │ External AI  │
│ (MCP client) │     │ (MCP client) │     │ (MCP client) │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       └────────────────────┼────────────────────┘
                            │
                    ┌───────▼────────┐
                    │   MCP Server   │
                    │ (Streamable    │
                    │  HTTP :8090)   │
                    ├────────────────┤
                    │ Tools:         │
                    │ • rag_search   │
                    │ • get_history  │
                    │ • list_collections│
                    │ • get_collection_info│
                    └───────┬────────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
        ┌─────▼─────┐ ┌────▼────┐ ┌─────▼─────┐
        │ LangGraph │ │ Qdrant  │ │  Redis    │
        │ Pipeline  │ │ :6334   │ │  :6379    │
        └───────────┘ └─────────┘ └───────────┘
```

### Цели (из video notes)

- **Переиспользование**: подключил сервер — агент получил список инструментов
- **Изоляция**: агент не знает о реализации
- **Безопасность**: централизованный контроль доступа
- **Наблюдаемость**: все вызовы через MCP — легко трейсить через Langfuse

---

## 2. Сравнение подходов

### Approach A: FastAPI-MCP (tadata-org/fastapi-mcp)

**Концепция:** Автоматически оборачивает существующие FastAPI endpoints в MCP tools.

```python
from fastapi import FastAPI
from fastapi_mcp import FastApiMCP

app = FastAPI()  # existing RAG API

# 3 строки — и MCP server готов
mcp = FastApiMCP(app, name="RAG Tools", base_url="http://localhost:8080")
mcp.mount()  # доступен на /mcp
```

| Плюсы | Минусы |
|-------|--------|
| Zero-config, 3 строки кода | Ограничен существующими endpoints |
| Сохраняет OpenAPI schemas | Нет гранулярного контроля tools |
| Auth через FastAPI Depends() | Tool = endpoint (1:1 маппинг) |
| MIT, активный проект (454 stars) | Доп. зависимость |

**Вердикт:** Подходит для быстрого старта. Но у нас только 1 endpoint (`POST /query`) — MCP server с 1 tool бесполезен. Нужны дополнительные tools.

### Approach B: FastMCP (official MCP Python SDK)

**Концепция:** Нативный MCP server с `@mcp.tool()` декораторами.

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("RAG Tools")

@mcp.tool()
async def rag_search(query: str, user_id: int = 0, session_id: str = "") -> str:
    """Search the knowledge base using hybrid RAG pipeline."""
    # ... invoke LangGraph pipeline
    return result

@mcp.tool()
async def get_history(user_id: int, limit: int = 10) -> list[dict]:
    """Get conversation history for a user."""
    # ... query Redis/memory
    return entries

@mcp.tool()
async def list_collections() -> list[dict]:
    """List available Qdrant collections with metadata."""
    # ... query Qdrant
    return collections

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

| Плюсы | Минусы |
|-------|--------|
| Полный контроль tool schema | Новый сервер, новый код |
| Nативный MCP protocol | Дублирование логики с RAG API |
| Любое кол-во tools | Свой lifecycle management |
| Official SDK (`mcp` package) | Отдельный порт/deployment |

**Вердикт:** Максимальная гибкость. Позволяет спроектировать tools оптимально для LLM.

### Approach C: Hybrid (FastAPI + FastMCP mount)

**Концепция:** FastAPI app (существующий RAG API) + FastMCP mounted как sub-app.

```python
from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP

# Existing FastAPI app
app = FastAPI(title="RAG API", lifespan=lifespan)

# MCP server
mcp = FastMCP("RAG Tools")

@mcp.tool()
async def rag_search(query: str, user_id: int = 0) -> str:
    """Search knowledge base."""
    # reuse app.state.graph
    ...

@mcp.tool()
async def list_collections() -> list[dict]:
    """List Qdrant collections."""
    # reuse app.state.qdrant
    ...

# Mount MCP alongside REST
app.mount("/mcp", mcp.http_app())

# REST endpoints preserved
@app.post("/query")
async def query(req: QueryRequest) -> QueryResponse: ...

@app.get("/health")
async def health(): ...
```

| Плюсы | Минусы |
|-------|--------|
| Один сервер, один порт (8080) | Более сложный setup |
| REST + MCP одновременно | Shared state management |
| Переиспользование lifespan/services | Не все MCP features доступны |
| Обратная совместимость | FastMCP mount API может меняться |

**Вердикт:** ✅ **Рекомендуемый подход.** Один сервис, минимальные изменения, обратная совместимость.

---

## 3. Рекомендуемая архитектура (Approach C — Hybrid)

### 3.1 MCP Tools (4 инструмента)

| Tool | Описание | Input | Output |
|------|----------|-------|--------|
| `rag_search` | Hybrid RAG поиск через LangGraph pipeline | `query: str, user_id: int, session_id: str, channel: str` | `{response, query_type, cache_hit, documents_count, latency_ms}` |
| `get_conversation_history` | История переписки пользователя | `user_id: int, limit: int` | `[{role, content, timestamp}]` |
| `list_collections` | Список доступных Qdrant коллекций | — | `[{name, vectors_count, points_count}]` |
| `get_collection_info` | Метаданные коллекции | `collection_name: str` | `{name, vectors_count, config, segments}` |

### 3.2 Файловая структура

```
src/mcp/
├── __init__.py
├── server.py          # FastMCP instance + tool definitions
├── tools/
│   ├── __init__.py
│   ├── rag.py         # rag_search tool
│   ├── history.py     # get_conversation_history tool
│   └── collections.py # list_collections, get_collection_info
└── auth.py            # API key / token validation (опционально)
```

### 3.3 Integration в RAG API

```python
# src/api/main.py (изменения)
from src.mcp.server import create_mcp_server

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... existing initialization ...
    # Create MCP server with shared services
    mcp = create_mcp_server(
        graph=app.state.graph,
        qdrant=app.state.qdrant,
        cache=app.state.cache,
    )
    app.mount("/mcp", mcp.http_app())
    yield
    # ... existing cleanup ...
```

### 3.4 Transport

| Transport | Когда использовать |
|-----------|-------------------|
| **Streamable HTTP** (рекомендован) | Production. `/mcp` endpoint на порту 8080 |
| stdio | Локальная разработка, CLI tools |
| SSE | **Deprecated** — не использовать |

### 3.5 Langfuse Observability

```python
@mcp.tool()
async def rag_search(query: str, user_id: int = 0, ...) -> str:
    with propagate_attributes(
        session_id=session_id,
        user_id=str(user_id),
        tags=["mcp", channel, "rag"],
    ):
        result = await graph.ainvoke(state)
        lf = get_client()
        lf.update_current_trace(
            input=query,
            output=result.get("response", ""),
            metadata={"source": "mcp", "tool": "rag_search"},
        )
        _write_langfuse_scores(lf, result)
    return json.dumps(result_dict)
```

---

## 4. Client Integration

### 4.1 Telegram Bot (LangGraph + MCP)

**Пакет:** `langchain-mcp-adapters`

```python
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

# В supervisor node
client = MultiServerMCPClient({
    "rag": {
        "url": "http://rag-api:8080/mcp",
        "transport": "streamable_http",
    }
})
tools = await client.get_tools()
# tools = [rag_search, get_conversation_history, list_collections, get_collection_info]
```

**Варианты использования в LangGraph:**

| Вариант | Описание | Подходит для |
|---------|----------|-------------|
| **ReAct agent** | Supervisor вызывает tools через MCP | #240 Multi-agent supervisor |
| **Direct tool call** | Конкретный node вызывает tool | Текущая архитектура (10-node graph) |
| **Hybrid** | Supervisor для routing, direct для heavy nodes | Переходный период |

### 4.2 Voice Agent (LiveKit)

```python
# src/voice/agent.py — замена httpx POST на MCP client
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def _call_rag_mcp(query: str, user_id: int) -> str:
    async with streamablehttp_client("http://rag-api:8080/mcp") as (r, w, _):
        async with ClientSession(r, w) as session:
            await session.initialize()
            result = await session.call_tool("rag_search", {
                "query": query,
                "user_id": user_id,
                "channel": "voice",
            })
            return result.content[0].text
```

---

## 5. Docker / Deployment

### 5.1 Изменения в docker-compose

```yaml
# Нет нового сервиса — MCP endpoint на существующем rag-api
services:
  rag-api:
    # ... existing config ...
    environment:
      MCP_ENABLED: "true"           # Feature flag
      MCP_AUTH_TOKEN: ${MCP_AUTH_TOKEN:-}  # Optional auth
    ports:
      - "8080:8080"  # REST + MCP on same port
```

### 5.2 k8s (VPS)

```yaml
# k8s/base/bot/deployment.yaml — добавить env
- name: MCP_SERVER_URL
  value: "http://rag-api:8080/mcp"
```

---

## 6. Зависимости

### Новые пакеты

| Пакет | Версия | Для чего | Где |
|-------|--------|----------|-----|
| `mcp` | `>=1.9.0` | MCP SDK (FastMCP server) | `pyproject.toml` (root) |
| `langchain-mcp-adapters` | `>=0.2.0` | MCP client для LangGraph | `telegram_bot/pyproject.toml` |
| `fastapi-mcp` | — | **НЕ нужен** (используем FastMCP напрямую) | — |

### Почему НЕ fastapi-mcp

- У нас 1 REST endpoint → 1 MCP tool (бесполезно)
- Нужны custom tools (history, collections) которых нет в REST
- FastMCP дает полный контроль над tool schema

---

## 7. Миграция (поэтапная)

### Phase 1: MCP Server (без client изменений)

1. Создать `src/mcp/server.py` с 4 tools
2. Mount на `/mcp` в `src/api/main.py`
3. Тесты: `tests/unit/mcp/`
4. Feature flag `MCP_ENABLED`

### Phase 2: Voice Agent → MCP Client

1. Заменить `httpx POST /query` на MCP `call_tool("rag_search")`
2. Добавить `langchain-mcp-adapters` или raw MCP client
3. Langfuse trace linking через `langfuse_trace_id`

### Phase 3: Bot → MCP Client (после #240 supervisor)

1. Supervisor node использует MCP tools
2. `MultiServerMCPClient` для tool discovery
3. Postепенный переход node-by-node

### Phase 4: Access Control

1. API key auth на MCP endpoint
2. Per-tool permissions
3. Rate limiting

---

## 8. Альтернативы (отклоненные)

| Альтернатива | Почему отклонена |
|-------------|------------------|
| **FastAPI-MCP only** | 1 endpoint → 1 tool, нет history/collections |
| **Отдельный MCP сервис** | Лишний контейнер, дублирование lifespan |
| **gRPC вместо MCP** | Не стандарт для LLM agents, нет tool discovery |
| **REST only** | Нет tool discovery, нет стандартизации |

---

## 9. Риски и mitigation

| Риск | Mitigation |
|------|-----------|
| MCP SDK breaking changes | Pin version `mcp>=1.9.0,<2.0` |
| Performance overhead (MCP vs REST) | Benchmark перед Phase 2. MCP HTTP ~= REST |
| langchain-mcp-adapters instability | Fallback на raw MCP client |
| Shared state race conditions | Используем async, один event loop |
| Auth bypass | Phase 4, не блокирует Phase 1-3 |

---

## 10. Key Research Sources

| Источник | Описание |
|----------|----------|
| [FastMCP docs](https://gofastmcp.com) | Official MCP Python SDK |
| [FastAPI-MCP](https://github.com/tadata-org/fastapi_mcp) | FastAPI → MCP wrapper (MIT) |
| [langchain-mcp-adapters](https://github.com/langchain-ai/langchain-mcp-adapters) | LangChain/LangGraph ↔ MCP bridge |
| [MCP Specification](https://modelcontextprotocol.io) | Protocol spec |
| [LangGraph + MCP](https://langchain-ai.github.io/langgraph/agents/mcp/) | LangGraph MCP integration docs |

---

## 11. Резюме

**Рекомендация:** Approach C (Hybrid) — mount FastMCP на существующий RAG API.

**Ключевые решения:**
1. **4 tools**: rag_search, get_conversation_history, list_collections, get_collection_info
2. **Streamable HTTP** transport на `/mcp` endpoint
3. **Поэтапная миграция**: server → voice client → bot client → auth
4. **`mcp` SDK** (не fastapi-mcp) для полного контроля
5. **langchain-mcp-adapters** для интеграции с LangGraph supervisor (#240)
