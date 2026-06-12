"""Minimal tool-call helpers for the imperative assistant adapter.

The LangChain decorators previously provided only two things the local code
relied on at runtime: keeping the function callable and exposing lightweight
metadata such as a tool name/description.  This module keeps that tiny surface
without importing LangChain.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast


RunnableConfig = dict[str, Any]
BaseTool = Callable[..., Any]


def tool(
    func: Callable[..., Any] | str | None = None, **metadata: Any
) -> Callable[..., Any] | Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Attach local tool metadata and return the original callable."""

    if isinstance(func, str):
        metadata = {**metadata, "name": func}
        func = None

    def decorate(inner: Callable[..., Any]) -> Callable[..., Any]:
        target = cast(Any, inner)
        target.name = metadata.get("name") or inner.__name__
        target.description = metadata.get("description") or (inner.__doc__ or "")
        target.tool_metadata = dict(metadata)
        return inner

    if func is None:
        return decorate
    return decorate(cast(Callable[..., Any], func))


__all__ = ["BaseTool", "RunnableConfig", "tool"]
