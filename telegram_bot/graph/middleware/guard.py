"""GuardMiddleware — SDK-native ``before_model`` hook for prompt-injection guard.

This is the create_agent-compatible counterpart of
:func:`telegram_bot.graph.nodes.guard.guard_node` (#2052, parent #1535).

The middleware reuses :func:`~telegram_bot.graph.nodes.guard.detect_injection`
and the canonical constants (``_BLOCKED_RESPONSE``, ``_INJECTION_THRESHOLD``,
``INJECTION_PATTERNS``) so the legacy StateGraph guard and the new
middleware stay byte-for-byte aligned on detection semantics until the
migration finishes (#2050 nodes -> tools, #2051 handler -> create_agent).

Behavior
--------

* ``hard`` mode + injection detected: emit the blocked
  :class:`~langchain.messages.AIMessage` and jump to ``end`` — the
  documented short-circuit shape from LangChain ``create_agent``
  middleware (verified via Context7).
* ``soft`` / ``log`` modes: detection is logged via Langfuse but no jump
  occurs; the agent proceeds normally.
* No injection detected: returns ``None`` (no state change, no jump).
"""

from __future__ import annotations

import logging
from typing import Any

from src.runtime.graph.state import Message as AIMessage
from telegram_bot.graph.middleware._compat import AgentMiddleware, AgentState, hook_config


try:
    from langgraph.runtime import Runtime
except ModuleNotFoundError:  # langgraph is an optional extra
    from telegram_bot.graph.middleware._compat import (
        _FakeRuntime as Runtime,  # type: ignore[attr-defined]
    )

from src.runtime.graph.nodes.guard import (
    _BLOCKED_RESPONSE,
    _INJECTION_THRESHOLD,
    detect_injection,
)


logger = logging.getLogger(__name__)


def _extract_query(state: AgentState | dict[str, Any]) -> str:
    """Return the latest human message text, robust to dict/object messages."""
    messages = state.get("messages") or []
    if not messages:
        return ""
    last = messages[-1]
    content = getattr(last, "content", None)
    if content is None and isinstance(last, dict):
        content = last.get("content", "")
    return content or ""


class GuardMiddleware(AgentMiddleware):
    """Block prompt-injection attempts before the model runs.

    Args:
        guard_mode: ``"hard"`` (default), ``"soft"`` or ``"log"``. Mirrors
            the ``GraphContext.guard_mode`` runtime knob honoured by
            :func:`guard_node`.
    """

    def __init__(self, *, guard_mode: str = "hard") -> None:
        super().__init__()
        self.guard_mode = guard_mode

    @hook_config(can_jump_to=["end"])
    def before_model(
        self,
        state: AgentState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:
        """Run regex injection detection; short-circuit in hard mode."""
        query = _extract_query(state)
        if not query:
            return None

        _, risk_score, pattern = detect_injection(query)
        detected = risk_score >= _INJECTION_THRESHOLD

        if not detected:
            return None

        logger.warning(
            "Injection detected (mode=%s, score=%.2f, pattern=%s): %.80s",
            self.guard_mode,
            risk_score,
            pattern,
            query,
        )

        if self.guard_mode == "hard":
            return {
                "messages": [AIMessage(content=_BLOCKED_RESPONSE)],
                "jump_to": "end",
            }
        # soft / log: detection recorded; agent continues.
        return None
