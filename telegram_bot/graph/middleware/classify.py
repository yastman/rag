"""ClassifyMiddleware — SDK-native ``before_agent`` hook for query classification.

This is the ``create_agent``-compatible counterpart of
:func:`telegram_bot.graph.nodes.classify.classify_node`. Slice 2.5 of the
voice-path migration plan in ADR-0010 (parent #1535 / #2051).

Behaviour
---------

Runs once at the start of an agent invocation:

* Reads the latest human message text and feeds it to
  :func:`~telegram_bot.graph.nodes.classify.classify_query` (regex-only,
  ~0 ms — no LLM).
* For ``CHITCHAT`` and ``OFF_TOPIC`` query types: returns
  ``{"messages": [AIMessage(canned)], "jump_to": "end", "query_type": ...}``
  so the SDK skips both the model loop and the cache hooks. This
  matches the legacy router in ``graph.py`` which sends those types
  straight to ``respond`` without touching ``cache_check``.
* For all other types: returns ``{"query_type": ...}`` so downstream
  middleware (cache_check) and tools see the classification without
  rerunning the regex.

The middleware is intentionally tiny — it owns no embeddings, no Redis,
no LLM. It exists purely to lift the legacy classify routing into the
``create_agent`` lifecycle.
"""

from __future__ import annotations

import logging
import time
from typing import Any, NotRequired

from langchain.agents.middleware import AgentMiddleware, AgentState, hook_config
from langchain.messages import AIMessage
from langgraph.runtime import Runtime

from telegram_bot.graph.nodes.classify import (
    CHITCHAT,
    OFF_TOPIC,
    _get_chitchat_response,
    classify_query,
)
from telegram_bot.observability import get_client


logger = logging.getLogger(__name__)


class _ClassifyAwareState(AgentState):
    """Adds the classification slot to the agent state."""

    query_type: NotRequired[str]
    response: NotRequired[str]
    latency_stages: NotRequired[dict[str, float]]


def _extract_query_text(state: AgentState | dict[str, Any]) -> str:
    messages = state.get("messages") or []
    if not messages:
        return ""
    last = messages[-1]
    content = getattr(last, "content", None)
    if content is None and isinstance(last, dict):
        content = last.get("content", "")
    return content or ""


def _canned_response(query: str, query_type: str) -> str:
    """Return the canned response the legacy node would have emitted."""
    if query_type == CHITCHAT:
        return _get_chitchat_response(query)
    if query_type == OFF_TOPIC:
        # Reuse the same off-topic response set the graph node uses, via a
        # local import so the module-scope import surface stays narrow.
        from random import choice

        from telegram_bot.graph.nodes.classify import OFF_TOPIC_RESPONSES

        return choice(OFF_TOPIC_RESPONSES)
    return ""


class ClassifyMiddleware(AgentMiddleware):
    """Classify the user query and short-circuit on CHITCHAT/OFF_TOPIC.

    Reuses ``classify_query`` (regex-only, ~0 ms) so detection is byte-for-byte
    aligned with the legacy graph until Slice 5 deletes ``classify_node``.

    Args:
        skip_canned_response: When ``True`` the middleware sets
            ``query_type`` but does not emit a canned reply for
            CHITCHAT/OFF_TOPIC. Useful for tests and for callers that
            want to render those messages with custom keyboards. Default
            ``False`` (matches legacy behaviour).
    """

    state_schema = _ClassifyAwareState

    def __init__(self, *, skip_canned_response: bool = False) -> None:
        super().__init__()
        self.skip_canned_response = skip_canned_response

    @hook_config(can_jump_to=["end"])
    def before_agent(
        self,
        state: _ClassifyAwareState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:
        query = _extract_query_text(state)
        if not query:
            return None

        t0 = time.perf_counter()
        query_type = classify_query(query)
        latency = time.perf_counter() - t0

        try:
            get_client().update_current_span(
                output={"query_type": query_type, "duration_ms": round(latency * 1000, 2)}
            )
        except Exception:  # pragma: no cover — observability must never raise
            logger.debug("classify update_current_span failed", exc_info=True)

        latency_stages = {**(state.get("latency_stages") or {}), "classify": latency}

        if query_type in {CHITCHAT, OFF_TOPIC}:
            if self.skip_canned_response:
                # Caller wants to render the canned message itself.
                return {"query_type": query_type, "latency_stages": latency_stages}
            canned = _canned_response(query, query_type)
            return {
                "messages": [AIMessage(content=canned)],
                "jump_to": "end",
                "query_type": query_type,
                "response": canned,
                "latency_stages": latency_stages,
            }

        return {"query_type": query_type, "latency_stages": latency_stages}


__all__ = ("ClassifyMiddleware", "_ClassifyAwareState")
