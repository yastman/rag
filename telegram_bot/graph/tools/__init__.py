"""SDK-native tool factories for ``create_agent`` (#2050).

Companion to :mod:`telegram_bot.graph.middleware` (#2052). These factories
return ``langchain.tools.BaseTool`` instances that #2051 wires into
``langchain.agents.create_agent(tools=[...])`` for the voice path.

Each factory accepts its dependencies as keyword arguments so production
code injects real services (``QdrantService``, embedder, reranker, LLM)
and tests pass mocks. The legacy node modules in
``telegram_bot.graph.nodes`` stay in place until #2050 + #2051 + the
guard-removal cleanup retire the StateGraph.
"""

from telegram_bot.graph.tools.rerank import make_rerank_tool
from telegram_bot.graph.tools.retrieve import make_retrieve_tool
from telegram_bot.graph.tools.rewrite import make_rewrite_tool


__all__ = [
    "make_rerank_tool",
    "make_retrieve_tool",
    "make_rewrite_tool",
]
