# Developer Guide: Adding New Features

This guide explains how to add new pipeline nodes, agent tools, and query types to the RAG system.

## Adding a New LangGraph Node

### 1. Create the Node File

Create a new file in `telegram_bot/graph/nodes/`:

```python
"""My custom node."""

from __future__ import annotations

from typing import Any


async def my_node(state: dict[str, Any], **deps) -> dict[str, Any]:
    """Node description.

    Args:
        state: RAGState dict with pipeline data
        **deps: Injected dependencies (cache, llm, qdrant, etc.)

    Returns:
        Dict with fields to update in state
    """
    # Your logic here
    return {"field_name": value}
```

### 2. Understand the State Contract

The `RAGState` TypedDict (in `telegram_bot/graph/state.py`) defines all fields. Key fields:

| Field | Type | Description |
|-------|------|-------------|
| `query` | str | User query text |
| `query_type` | str | Classification result |
| `documents` | list[dict] | Retrieved documents |
| `response` | str | Generated response |
| `cache_hit` | bool | Cache hit flag |
| `latency_stages` | dict | Per-stage timing |

### 3. Register the Node in build_graph()

In `telegram_bot/graph/graph.py`:

```python
from telegram_bot.graph.nodes import my_node

def build_graph(...) -> StateGraph:
    graph = StateGraph(RAGState)

    # Add node
    graph.add_node("my_node", my_node)

    # Add edges
    graph.add_edge("retrieve", "my_node")
    graph.add_edge("my_node", "generate")

    return graph.compile(...)
```

### 4. Conditional Routing

For conditional edges, use the edge routing pattern:

```python
def route_after_my_node(state: dict) -> str:
    """Decide next node after my_node."""
    if state.get("some_condition"):
        return "generate"
    return "respond"

graph.add_conditional_edges("my_node", route_after_my_node, {
    "generate": "generate",
    "respond": "respond",
})
```

## Adding a New Agent Tool

### 1. Create the Tool

In `telegram_bot/agents/`:

```python
"""My custom tool."""

from typing import Any
from langchain_core.tools import tool

from telegram_bot.agents.context import BotContext


@tool
async def my_tool(query: str, ctx: BotContext) -> str:
    """Tool description for the agent.

    Args:
        query: Input parameter description
        ctx: BotContext with dependencies (user_id, kommo_client, etc.)

    Returns:
        Tool result as string
    """
    # Tool implementation
    return "result string"
```

### 2. Register in create_bot_agent()

In `telegram_bot/agents/agent.py`:

```python
from telegram_bot.agents.my_tool import my_tool

def create_bot_agent(model, tools: list, context_schema, checkpointer=None):
    # ... existing code ...

    # Add your tool
    all_tools = [*base_tools, my_tool]

    agent = create_agent(
        model,
        all_tools,
        checkpointer=checkpointer,
        context_schema=context_schema,
    )
    return agent
```

### 3. Role-Gated Tools

If the tool should only be available to certain roles:

```python
from telegram_bot.agents.manager_tools import build_tools_for_role

def get_all_tools(ctx: BotContext) -> list:
    tools = [rag_search, history_search]  # Base tools

    # Add role-specific tools
    if ctx.role == "manager":
        tools.append(my_manager_only_tool)

    return tools
```

## Adding a New Query Type

### 1. Define the Type

In `telegram_bot/graph/nodes/classify.py` or query classification logic:

```python
# Add to query type enum/mapping
QUERY_TYPES = ["CHITCHAT", "OFF_TOPIC", "SIMPLE", "GENERAL", "FAQ", "ENTITY", "STRUCTURED", "COMPLEX", "MY_NEW_TYPE"]
```

### 2. Handle in Classification

Update the classification logic to assign your new type based on query characteristics.

### 3. Update Cache Thresholds

In `telegram_bot/integrations/cache.py`:

```python
self.cache_thresholds = cache_thresholds or {
    # ... existing types ...
    "MY_NEW_TYPE": 0.08,  # Appropriate threshold
}
```

### 4. Handle in Pipeline Routing

In `telegram_bot/pipelines/client.py` or routing logic:

```python
# Determine if query type affects pipeline behavior
_PIPELINE_STORE_TYPES = {"FAQ", "GENERAL", "ENTITY", "MY_NEW_TYPE"}
```

## Testing New Nodes/Tools

### Unit Test Pattern

```python
# tests/unit/graph/test_my_node.py
import pytest
from telegram_bot.graph.nodes.my_node import my_node

@pytest.fixture
def mock_state():
    return {"query": "test query", "documents": []}

@pytest.mark.asyncio
async def test_my_node(mock_state):
    result = await my_node(mock_state, cache=mock_cache)
    assert "field_name" in result
```

### Integration Test Pattern

```python
# tests/integration/test_graph_paths.py
@pytest.mark.asyncio
async def test_my_node_in_graph():
    graph = build_graph(...)
    state = make_initial_state(query="test")
    result = await graph.ainvoke(state)
    assert result.get("field_name") == expected
```

## Dependencies and Dependency Injection

### Available Dependencies

| Dependency | How to Access | Purpose |
|------------|---------------|---------|
| `cache` | Node parameter | CacheLayerManager |
| `llm` | Node parameter | AsyncOpenAI client |
| `qdrant` | Node parameter | QdrantService |
| `embeddings` | Node parameter | BGEM3HybridEmbeddings |
| `reranker` | Node parameter | ColbertRerankerService |
| `message` | Node parameter | aiogram Message (voice path only) |

### Adding New Dependencies

1. Define in `GraphConfig` (`telegram_bot/graph/config.py`)
2. Pass to `build_graph()` in `PropertyBot.__init__()`
3. Nodes receive via `**deps` parameter

## Best Practices

1. **Always return a dict** — nodes must return fields to update in state
2. **Use `@observe`** — add Langfuse tracing for observability
3. **Handle errors gracefully** — return error state, don't raise
4. **Document state changes** — comment what fields your node reads/writes
5. **Test edge cases** — empty documents, timeout, etc.
