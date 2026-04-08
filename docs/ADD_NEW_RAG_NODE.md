# Adding a New RAG Node

Guide for extending the LangGraph pipeline with a new node.

## When to Add a Node

Add a new node when:
- You need a distinct step in the pipeline with its own logic
- The node needs its own Langfuse tracing
- The node has stateful operations that should be checkpointed
- You need conditional routing based on node output

For simple transformations within existing logic, prefer inline functions.

## Step-by-Step

### 1. Create the Node File

Create `telegram_bot/graph/nodes/your_node.py`:

```python
"""Your node description."""

from typing import Any

from telegram_bot.observability import observe


@observe(name="node-your_node", capture_input=False, capture_output=False)
async def your_node(state: dict[str, Any], context: Any) -> dict[str, Any]:
    """Process state and return updates.

    Args:
        state: Current RAGState
        context: GraphContext DI container

    Returns:
        Dict of state updates (merged via | operator)
    """
    # Your logic here
    result = await context.some_service.do_something(state["query"])

    return {
        "your_field": result,
        # Optional: add to trace
        "trace_context": {"your_node_output": result},
    }
```

### 2. Add State Fields

If your node adds new state fields, update `telegram_bot/graph/state.py`:

```python
class RAGState(TypedDict):
    # ... existing fields ...

    # Your new field
    your_field: str | None
```

### 3. Register in Graph Builder

In `telegram_bot/graph/graph.py`:

```python
from .nodes.your_node import your_node

def build_graph(...) -> CompiledGraph:
    # ... existing code ...

    graph.add_node("your_node", your_node)

    # Add edges
    graph.add_edge("existing_node", "your_node")
    # OR conditional edge:
    graph.add_conditional_edges(
        "existing_node",
        route_your_node,
        {
            "your_node": lambda s: s.get("condition"),
            "other_node": lambda s: not s.get("condition"),
        }
    )

    return graph.compile(...)
```

### 4. Add Route Function (if conditional)

```python
def route_your_node(state: RAGState) -> str:
    """Return next node name based on state."""
    if state.get("your_field"):
        return "next_node"
    return "fallback_node"
```

### 5. Update Type Annotations

If using `GraphContext` for DI, update `telegram_bot/graph/context.py`:

```python
class GraphContext(TypedDict):
    # ... existing fields ...
    your_service: YourServiceType
```

## Node Template

```python
"""Node description."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from telegram_bot.observability import ObserveContext
else:
    ObserveContext = Any

from telegram_bot.observability import observe


@observe(name="node-{node_name}", capture_input=False, capture_output=False)
async def {node_name}_node(
    state: dict[str, Any],
    context: ObserveContext,
) -> dict[str, Any]:
    """Short description of what this node does.

    Args:
        state: Current RAGState
        context: GraphContext DI container

    Returns:
        State updates to merge
    """
    # 1. Extract inputs from state
    # 2. Do work (use context for dependencies)
    # 3. Return state updates
    return {"output_field": "value"}
```

## Checklist

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

## Example: Adding a Sentiment Node

```python
# telegram_bot/graph/nodes/sentiment.py
@observe(name="node-sentiment", capture_input=False, capture_output=False)
async def sentiment_node(state: dict, context: Any) -> dict:
    sentiment = await context.sentiment_analyzer.analyze(state["query"])
    return {"sentiment": sentiment, "query_sentiment": sentiment}
```

Then in `graph.py`:
```python
graph.add_node("sentiment", sentiment_node)
graph.add_edge("classify", "sentiment")
graph.add_edge("sentiment", "guard")
```

## Code Locations

| File | Purpose |
|------|---------|
| `telegram_bot/graph/graph.py` | Graph builder + route functions |
| `telegram_bot/graph/state.py` | RAGState TypedDict |
| `telegram_bot/graph/context.py` | GraphContext DI container |
| `telegram_bot/observability.py` | @observe decorator |
| `tests/unit/telegram_bot/graph/` | Node tests |
