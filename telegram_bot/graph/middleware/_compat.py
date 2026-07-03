"""Local compatibility shims for the agent middleware layer.

``langchain.agents.middleware`` was a fictional import in the original
middleware files.  These minimal stubs provide the same interface so
``cache.py``, ``classify.py``, and ``guard.py`` can be imported and
tested without a real langchain install.

The classes are intentionally minimal — only what the middleware tests
and implementations actually use.
"""

from __future__ import annotations

from functools import wraps
from typing import Any


class _AgentStateBase(dict):
    """Minimal AgentState: a dict subclass with TypedDict-style annotations."""

    def get(self, key: str, default: Any = None) -> Any:  # type: ignore[override]
        return super().get(key, default)


# AgentState used as a TypedDict-like base — subclasses just add annotations.
AgentState = _AgentStateBase


class _FakeRuntime:
    """Minimal Runtime stub when langgraph is not installed."""

    def __init__(self, context: dict[str, Any] | None = None) -> None:
        self.context: dict[str, Any] = context or {}


class AgentMiddleware:
    """Minimal base class for before/after agent hooks."""

    state_schema: type | None = None

    def before_agent(
        self,
        state: dict[str, Any],
        runtime: Any,
    ) -> dict[str, Any] | None:
        return None  # pragma: no cover

    async def abefore_agent(
        self,
        state: dict[str, Any],
        runtime: Any,
    ) -> dict[str, Any] | None:
        return None  # pragma: no cover

    async def aafter_agent(
        self,
        state: dict[str, Any],
        runtime: Any,
    ) -> dict[str, Any] | None:
        return None  # pragma: no cover


def hook_config(**kwargs: Any):
    """No-op decorator — just passes through the decorated function."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kw):
            return fn(*args, **kw)

        @wraps(fn)
        async def async_wrapper(*args, **kw):
            return await fn(*args, **kw)

        import asyncio

        if asyncio.iscoroutinefunction(fn):
            return async_wrapper
        return wrapper

    return decorator
