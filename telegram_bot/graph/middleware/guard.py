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
import time
from typing import Any

from langchain.agents.middleware import AgentMiddleware, AgentState, hook_config
from langchain.messages import AIMessage
from langgraph.runtime import Runtime

from telegram_bot.graph.nodes.guard import (
    _BLOCKED_RESPONSE,
    _INJECTION_THRESHOLD,
    detect_injection,
)
from telegram_bot.observability import get_client


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
        t0 = time.perf_counter()
        query = _extract_query(state)
        if not query:
            return None

        _, risk_score, pattern = detect_injection(query)
        detected = risk_score >= _INJECTION_THRESHOLD
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        if not detected:
            self._observe(detected=False, risk=0.0, pattern=None, elapsed_ms=elapsed_ms)
            return None

        logger.warning(
            "Injection detected (mode=%s, score=%.2f, pattern=%s): %.80s",
            self.guard_mode,
            risk_score,
            pattern,
            query,
        )
        self._observe(detected=True, risk=risk_score, pattern=pattern, elapsed_ms=elapsed_ms)

        if self.guard_mode == "hard":
            return {
                "messages": [AIMessage(content=_BLOCKED_RESPONSE)],
                "jump_to": "end",
            }
        # soft / log: detection recorded; agent continues.
        return None

    @staticmethod
    def _observe(*, detected: bool, risk: float, pattern: str | None, elapsed_ms: float) -> None:
        """Record a Langfuse span output mirroring guard_node's observability."""
        try:
            client = get_client()
        except Exception:  # pragma: no cover — observability must never raise
            return
        try:
            client.update_current_span(
                output={
                    "injection_detected": detected,
                    "risk_score": risk,
                    "pattern": pattern,
                    "elapsed_ms": elapsed_ms,
                }
            )
        except Exception:  # pragma: no cover — defensive
            logger.debug("Langfuse update_current_span failed", exc_info=True)
