# agents/

## Purpose

Agent SDK tools and RAG pipeline functions. Alternative to the full LangGraph graph for simpler or agent-driven flows. Provides async RAG pipeline functions and agent tools that return **context** (documents, scores, latency) rather than final answers. Used when the bot needs agent-style tool calling or a lighter pipeline than the 11-node LangGraph graph.

## Entrypoints

| File | Role |
|------|------|
| [`rag_pipeline.py`](./rag_pipeline.py) | Async RAG orchestrator: cache → retrieve → grade → rerank → rewrite loop |
| [`rag_tool.py`](./rag_tool.py) | Agent-facing RAG tool wrapper |
| [`agent.py`](./agent.py) | Agent SDK configuration and runner |
| [`apartment_tools.py`](./apartment_tools.py) | Property search and filter tools |
| [`crm_tools.py`](./crm_tools.py) | CRM integration tools |
| [`manager_tools.py`](./manager_tools.py) | Manager escalation and notification tools |
| [`utility_tools.py`](./utility_tools.py) | General utility tools |
| [`history_tool.py`](./history_tool.py) | Conversation history retrieval |
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
- [`../graph/README.md`](../graph/README.md) — Full LangGraph pipeline
- [`../../docs/HITL.md`](../../docs/HITL.md) — Human-in-the-loop design
