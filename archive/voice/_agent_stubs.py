"""Self-contained stubs for voice-agent compatibility surface.

Replaces the former ``telegram_bot.agents.agent`` and
``telegram_bot.agents.rag_tool`` imports so the archived voice module does
not depend on live application code (#2748).
"""

from __future__ import annotations

from typing import Any


class AgentMessage:
    """Minimal message object compatible with voice agent result handling."""

    def __init__(self, content: str) -> None:
        self.content = content


class ImperativeBotAgent:
    """Minimal async agent base retained for voice-agent compatibility."""

    def __init__(self, *, tools: list[Any], prompt: str, model: str, role: str) -> None:
        self.tools = tools
        self.prompt = prompt
        self.model = model
        self.role = role

    async def _run_core_or_tool(self, query: str, config: dict[str, Any]) -> str:
        if not self.tools:
            return "Не нашёл подходящий инструмент для обработки запроса."
        tool = next(
            (
                t
                for t in self.tools
                if getattr(t, "name", getattr(t, "__name__", "")) == "rag_search"
            ),
            self.tools[0],
        )
        try:
            result = tool(query, config)
        except TypeError:
            result = tool(query)
        if hasattr(result, "__await__"):
            result = await result
        return str(result or "")


async def rag_search(query: str, *_: Any, **__: Any) -> str:
    """Stub — voice archive uses RagApiClient directly, not the live rag_search tool."""
    return f"[rag_search stub] query={query!r}"


__all__ = ("AgentMessage", "ImperativeBotAgent", "rag_search")
