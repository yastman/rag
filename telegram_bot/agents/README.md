# agents/

## Purpose

Agent SDK tools for agent-driven flows. Agent tools return **context** (documents, scores, latency) rather than final answers; grounded RAG retrieval is owned by [`src/runtime/pipeline/`](../../src/runtime/pipeline/) and wrapped here via `rag_tool.py` / `retrieve_tool.py`.

## Entrypoints

| File | Role |
|------|------|
| [`rag_tool.py`](./rag_tool.py) · [`retrieve_tool.py`](./retrieve_tool.py) | Agent-facing RAG / retrieve tool wrappers |
| [`agent.py`](./agent.py) | Agent SDK configuration and runner |
| [`tool_assembly.py`](./tool_assembly.py) · [`tooling.py`](./tooling.py) | Tool registry assembly |
| [`apartment_tools.py`](./apartment_tools.py) | Property search and filter tools |
| [`manager_tools.py`](./manager_tools.py) | Manager escalation and notification tools |
| [`utility_tools.py`](./utility_tools.py) | General utility tools |
| [`history_tool.py`](./history_tool.py) · [`context.py`](./context.py) | Conversation history + agent context |
| [`hitl.py`](./hitl.py) | Human-in-the-loop hooks |
| [`history_graph/graph.py`](./history_graph/graph.py) | Small history-specific LangGraph |

## Boundaries

- Returns context, not final answers; the caller (bot or another agent) generates responses.
- Does not own Telegram transport handling; see [`../bot.py`](../bot.py).
- Does not modify Qdrant collections or ingestion schemas.

## Focused Checks

```bash
uv run pytest tests/unit/ -k "agent" -q
uv run pytest tests/integration/test_graph_paths.py -n auto --dist=worksteal -q
```

## See Also

- [`../README.md`](../README.md) — Telegram transport layer
