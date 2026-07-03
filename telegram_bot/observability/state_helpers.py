"""State-shape helper functions extracted from ``telegram_bot/bot.py`` (#1265).

Slice 1 PR-1 of the bot.py decomposition plan. These three helpers are pure
read-only accessors over the per-thread state dict that ``PropertyBot``
keeps in the LangGraph checkpointer:

* :func:`_state_apartment_results` — read cached apartment payloads from
  legacy or dialog-owned state shapes.
* :func:`_state_control_message_id` — locate the catalog control message id
  used to update inline keyboards in place.
* :func:`_extract_current_turn` — slice agent checkpointer history down to
  the messages that belong to the current user turn.

They are byte-for-byte the bodies that previously lived in ``bot.py``;
``telegram_bot/bot.py`` re-exports them from this module so existing
callers (and ``from telegram_bot.bot import _extract_current_turn`` in
``tests/unit/test_bot_scores.py``) continue to resolve to the same
callables.

The module has no aiogram / fastapi / langgraph imports, which keeps it
cheap to import and easy to unit-test in isolation.
"""

from __future__ import annotations

from typing import Any


def _state_apartment_results(state_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Read cached apartment payloads from legacy or dialog-owned state."""
    raw_results = state_data.get("apartment_results")
    if isinstance(raw_results, list):
        return [item for item in raw_results if isinstance(item, dict)]

    runtime = state_data.get("catalog_runtime")
    if isinstance(runtime, dict):
        runtime_results = runtime.get("results")
        if isinstance(runtime_results, list):
            return [item for item in runtime_results if isinstance(item, dict)]

    return []


def _state_control_message_id(state_data: dict[str, Any]) -> int | None:
    runtime = state_data.get("catalog_runtime")
    if isinstance(runtime, dict):
        control_message_id = runtime.get("control_message_id")
        if isinstance(control_message_id, int):
            return control_message_id

    footer_msg_id = state_data.get("apartment_footer_msg_id")
    if isinstance(footer_msg_id, int):
        return footer_msg_id
    return None


def _extract_current_turn(messages: list[Any]) -> list[Any]:
    """Extract current-turn messages from full checkpointer history (#507).

    Agent checkpointer returns full conversation history across turns.
    For per-turn scoring we only need messages after the last HumanMessage.
    """
    last_human_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        if getattr(messages[i], "type", None) == "human":
            last_human_idx = i
            break
    if last_human_idx < 0:
        return messages
    return messages[last_human_idx:]


__all__ = [
    "_extract_current_turn",
    "_state_apartment_results",
    "_state_control_message_id",
]
