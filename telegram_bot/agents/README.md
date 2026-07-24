# agents/

## Purpose

Agent SDK tools and RAG pipeline functions. Alternative to the full LangGraph graph for simpler or agent-driven flows. Provides async RAG pipeline functions and agent tools that return **context** (documents, scores, latency) rather than final answers. Used when the bot needs agent-style tool calling or a lighter pipeline than the full LangGraph pipeline (the graph itself now lives in [`../../src/runtime/graph/`](../../src/runtime/graph/)).

## Entrypoints

| File | Role |
|------|------|
| [`rag_pipeline.py`](./rag_pipeline.py) | Async RAG orchestrator: cache → retrieve → grade → rerank → rewrite loop |
| [`retrieval_stage.py`](./retrieval_stage.py) · [`cache_stage.py`](./cache_stage.py) | Retrieval + cache stages of the agent pipeline |
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
