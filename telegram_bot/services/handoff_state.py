"""Compatibility re-export for manager handoff state.

The canonical implementation lives in :mod:`src.services.handoff_state` so
shared observability/runtime surfaces never need to depend on the Telegram
adapter package.
"""

from src.services.handoff_state import HandoffData, HandoffState


__all__ = ["HandoffData", "HandoffState"]
