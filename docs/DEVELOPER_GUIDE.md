***REMOVED*** Developer Guide: Extending the Platform

This guide explains how to add new pipeline nodes, agent tools, query types, and ingestion sources to the system.

***REMOVED******REMOVED*** Adding a New LangGraph Node

***REMOVED******REMOVED******REMOVED*** When to Add a Node

Add a new node when:

- You need a distinct step in the pipeline with its own logic
- The node needs its own Langfuse tracing
- The node has stateful operations that should be checkpointed
- You need conditional routing based on node output

For simple transformations within existing logic, prefer inline functions.

***REMOVED******REMOVED******REMOVED*** Step-by-Step

***REMOVED******REMOVED******REMOVED******REMOVED*** 1. Create the Node File

Create `telegram_bot/graph/nodes/your_node.py`:

```python
"""Your node description."""

from typing import Any

from langgraph.runtime import Runtime

from telegram_bot.graph.context import GraphContext
from telegram_bot.observability import observe


@observe(name="node-your_node", capture_input=False, capture_output=False)
async def your_node(
    state: dict[str, Any],
    runtime: Runtime[GraphContext],
) -> dict[str, Any]:
    """Process state and return updates.

    Args:
        state: Current RAGState
        runtime: LangGraph Runtime with GraphContext dependencies

    Returns:
        Dict of state updates
    """
    some_service = runtime.context["some_service"]
    messages = state.get("messages") or []
    last_message = messages[-1] if messages else {}
    query = (
        last_message.content
        if hasattr(last_message, "content")
        else last_message.get("content", "")
    )

    result = await some_service.do_something(query)

    return {
        "your_field": result,
        ***REMOVED*** Optional: add to trace
        "trace_context": {"your_node_output": result},
    }
```

***REMOVED******REMOVED******REMOVED******REMOVED*** 2. Add State Fields

If your node adds new state fields, update `telegram_bot/graph/state.py`:

```python
class RAGState(TypedDict):
    ***REMOVED*** ... existing fields ...

    ***REMOVED*** Your new field
    your_field: str | None
```

Key existing state fields:

| Field | Type | Description |
|-------|------|-------------|
| `query` | str | User query text |
| `query_type` | str | Classification result |
| `documents` | list[dict] | Retrieved documents |
| `response` | str | Generated response |
| `cache_hit` | bool | Cache hit flag |
| `latency_stages` | dict | Per-stage timing |

***REMOVED******REMOVED******REMOVED******REMOVED*** 3. Register in Graph Builder

In `telegram_bot/graph/graph.py`:

```python
from .nodes.your_node import your_node

def build_graph(...) -> CompiledGraph:
    ***REMOVED*** ... existing code ...

    graph.add_node("your_node", your_node)

    ***REMOVED*** Add edges
    graph.add_edge("existing_node", "your_node")
    ***REMOVED*** OR conditional edge:
    graph.add_conditional_edges(
        "existing_node",
        route_your_node,
        {
            "your_node": "your_node",
            "other_node": "other_node",
        }
    )

    return graph.compile(...)
```

***REMOVED******REMOVED******REMOVED******REMOVED*** 4. Add Route Function (if conditional)

```python
def route_your_node(state: RAGState) -> str:
    """Return next node name based on state."""
    if state.get("your_field"):
        return "your_node"
    return "other_node"
```

***REMOVED******REMOVED******REMOVED******REMOVED*** 5. Update GraphContext

If your node introduces a new dependency, update `telegram_bot/graph/context.py`:

```python
class GraphContext(TypedDict):
    ***REMOVED*** ... existing fields ...
    your_service: YourServiceType
```

***REMOVED******REMOVED******REMOVED*** Node Template

```python
"""Node description."""

from typing import Any

from langgraph.runtime import Runtime

from telegram_bot.graph.context import GraphContext
from telegram_bot.observability import observe


@observe(name="node-{node_name}", capture_input=False, capture_output=False)
async def {node_name}_node(
    state: dict[str, Any],
    runtime: Runtime[GraphContext],
) -> dict[str, Any]:
    """Short description of what this node does.

    Args:
        state: Current RAGState
        runtime: LangGraph Runtime with GraphContext dependencies

    Returns:
        State updates to merge
    """
    ***REMOVED*** 1. Extract inputs from state
    ***REMOVED*** 2. Do work (use runtime.context for dependencies)
    ***REMOVED*** 3. Return state updates
    dependency = runtime.context.get("dependency")
    return {"output_field": "value"}
```

***REMOVED******REMOVED******REMOVED*** Checklist

- [ ] Create node file in `telegram_bot/graph/nodes/`
- [ ] Add `@observe` decorator with unique name
- [ ] Update `RAGState` in `state.py` if adding fields
- [ ] Add node to graph in `graph.py`
- [ ] Add edge(s) from previous node(s)
- [ ] Add conditional routing if needed
- [ ] Add route function if conditional
- [ ] Update `GraphContext` if using DI
- [ ] Add unit test in `tests/unit/telegram_bot/graph/`
- [ ] Run `make check` and `make test-unit`

***REMOVED******REMOVED******REMOVED*** Example: Adding a Sentiment Node

```python
***REMOVED*** telegram_bot/graph/nodes/sentiment.py
@observe(name="node-sentiment", capture_input=False, capture_output=False)
async def sentiment_node(
    state: dict[str, Any],
    runtime: Runtime[GraphContext],
) -> dict[str, Any]:
    analyzer = runtime.context["sentiment_analyzer"]
    messages = state.get("messages") or []
    query = messages[-1].content if hasattr(messages[-1], "content") else messages[-1]["content"]
    sentiment = await analyzer.analyze(query)
    return {"sentiment": sentiment, "query_sentiment": sentiment}
```

Then in `graph.py`:

```python
graph.add_node("sentiment", sentiment_node)
graph.add_edge("classify", "sentiment")
graph.add_edge("sentiment", "guard")
```

***REMOVED******REMOVED******REMOVED*** Code Locations

| File | Purpose |
|------|---------|
| `telegram_bot/graph/graph.py` | Graph builder + route functions |
| `telegram_bot/graph/state.py` | RAGState TypedDict |
| `telegram_bot/graph/context.py` | GraphContext DI container |
| `telegram_bot/observability.py` | @observe decorator |
| `tests/unit/telegram_bot/graph/` | Node tests |

***REMOVED******REMOVED*** Adding a New Agent Tool

***REMOVED******REMOVED******REMOVED*** 1. Create the Tool

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
    ***REMOVED*** Tool implementation
    return "result string"
```

***REMOVED******REMOVED******REMOVED*** 2. Register in create_bot_agent()

In `telegram_bot/agents/agent.py`:

```python
from telegram_bot.agents.my_tool import my_tool

def create_bot_agent(model, tools: list, context_schema, checkpointer=None):
    ***REMOVED*** ... existing code ...

    ***REMOVED*** Add your tool
    all_tools = [*base_tools, my_tool]

    agent = create_agent(
        model,
        all_tools,
        checkpointer=checkpointer,
        context_schema=context_schema,
    )
    return agent
```

***REMOVED******REMOVED******REMOVED*** 3. Role-Gated Tools

If the tool should only be available to certain roles:

```python
from telegram_bot.agents.manager_tools import build_tools_for_role

def get_all_tools(ctx: BotContext) -> list:
    tools = [rag_search, history_search]  ***REMOVED*** Base tools

    ***REMOVED*** Add role-specific tools
    if ctx.role == "manager":
        tools.append(my_manager_only_tool)

    return tools
```

***REMOVED******REMOVED*** Adding a New Query Type

***REMOVED******REMOVED******REMOVED*** 1. Define the Type

In `telegram_bot/graph/nodes/classify.py` or query classification logic:

```python
***REMOVED*** Add to query type enum/mapping
QUERY_TYPES = ["CHITCHAT", "OFF_TOPIC", "SIMPLE", "GENERAL", "FAQ", "ENTITY", "STRUCTURED", "COMPLEX", "MY_NEW_TYPE"]
```

***REMOVED******REMOVED******REMOVED*** 2. Handle in Classification

Update the classification logic to assign your new type based on query characteristics.

***REMOVED******REMOVED******REMOVED*** 3. Update Cache Thresholds

In `telegram_bot/integrations/cache.py`:

```python
self.cache_thresholds = cache_thresholds or {
    ***REMOVED*** ... existing types ...
    "MY_NEW_TYPE": 0.08,  ***REMOVED*** Appropriate threshold
}
```

***REMOVED******REMOVED******REMOVED*** 4. Handle in Pipeline Routing

In `telegram_bot/pipelines/client.py` or routing logic:

```python
***REMOVED*** Determine if query type affects pipeline behavior
_PIPELINE_STORE_TYPES = {"FAQ", "GENERAL", "ENTITY", "MY_NEW_TYPE"}
```

***REMOVED******REMOVED*** Adding a New Ingestion Source

The ingestion pipeline lives in `src/ingestion/unified/` and uses CocoIndex flows for orchestration with Docling for document parsing.

To add a new source:

1. **Create a source connector** following the `LocalFile` pattern in `src/ingestion/unified/`. Each source defines how documents are discovered, read, and tracked for changes.
2. **Register in the CLI** so the new source can be triggered via the ingestion command interface.
3. **Add state tracking** via the PostgreSQL state backend so CocoIndex can detect additions, updates, and deletions.

For the full ingestion architecture (flow structure, parsing, chunking, vector upsert/delete, and troubleshooting), see [INGESTION.md](INGESTION.md).

***REMOVED******REMOVED*** Dependencies and Dependency Injection

Nodes receive dependencies through `runtime.context`, which provides a typed `GraphContext` dictionary.

***REMOVED******REMOVED******REMOVED*** Available Dependencies

| Dependency | How to Access | Purpose |
|------------|---------------|---------|
| `cache` | `runtime.context["cache"]` | CacheLayerManager |
| `llm` | `runtime.context["llm"]` | AsyncOpenAI client |
| `qdrant` | `runtime.context["qdrant"]` | QdrantService |
| `embeddings` | `runtime.context["embeddings"]` | BGEM3HybridEmbeddings |
| `reranker` | `runtime.context["reranker"]` | Optional reranker hook; ColBERT runs server-side through Qdrant in normal runtime |
| `message` | `runtime.context["message"]` | aiogram Message (voice path only) |

***REMOVED******REMOVED******REMOVED*** Adding New Dependencies

1. Define in `GraphContext` (`telegram_bot/graph/context.py`)
2. Pass to `build_graph()` in `PropertyBot.__init__()`
3. Nodes access via `runtime.context["your_dependency"]`

***REMOVED******REMOVED*** Testing New Nodes and Tools

***REMOVED******REMOVED******REMOVED*** Unit Test Pattern

```python
***REMOVED*** tests/unit/telegram_bot/graph/test_your_node.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from telegram_bot.graph.nodes.your_node import your_node


@pytest.fixture
def mock_state():
    return {"query": "test query", "documents": []}


@pytest.fixture
def mock_runtime():
    runtime = MagicMock()
    runtime.context = {"some_service": AsyncMock()}
    return runtime


@pytest.mark.asyncio
async def test_your_node(mock_state, mock_runtime):
    result = await your_node(mock_state, mock_runtime)
    assert "your_field" in result
```

***REMOVED******REMOVED******REMOVED*** Integration Test Pattern

```python
***REMOVED*** tests/integration/test_graph_paths.py
@pytest.mark.asyncio
async def test_node_in_graph():
    graph = build_graph(...)
    state = make_initial_state(query="test")
    result = await graph.ainvoke(state)
    assert result.get("field_name") == expected
```

***REMOVED******REMOVED******REMOVED*** Testing Checklist

- [ ] Unit test covers the happy path
- [ ] Unit test covers error/empty-input cases
- [ ] Integration test verifies the node works within the graph
- [ ] `make check` passes (Ruff lint + MyPy)
- [ ] `make test-unit` passes

***REMOVED******REMOVED*** Best Practices

1. **Always return a dict** -- nodes must return fields to update in state
2. **Use `@observe`** -- add Langfuse tracing for observability
3. **Handle errors gracefully** -- return error state, don't raise
4. **Document state changes** -- comment what fields your node reads/writes
5. **Test edge cases** -- empty documents, timeout, etc.
