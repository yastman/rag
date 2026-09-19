"""Read apartment payloads and control-message IDs from catalog state.

Direct behavior tests live in ``tests/unit/test_bot_state_helpers.py``.
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


__all__ = [
    "_state_apartment_results",
    "_state_control_message_id",
]
