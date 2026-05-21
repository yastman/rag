"""Langfuse observability helpers with runtime initialization.

Re-exports from src.observability for backward compatibility.
The create_callback_handler function is kept here as it depends on
langfuse.langchain which is specific to the bot transport layer.
"""

import logging
from typing import Any

from src.observability import (
    _install_langfuse_warning_filters,
    _reset_langfuse_client_for_tests,
    get_client,
    get_langfuse_client,
    initialize_langfuse,
    mask_pii,
    observe,
    propagate_attributes,
    sync_langfuse_model_definitions,
    traced_pipeline,
)


logger = logging.getLogger(__name__)

__all__ = [
    "_install_langfuse_warning_filters",
    "_reset_langfuse_client_for_tests",
    "create_callback_handler",
    "get_client",
    "get_langfuse_client",
    "initialize_langfuse",
    "mask_pii",
    "observe",
    "propagate_attributes",
    "sync_langfuse_model_definitions",
    "traced_pipeline",
]


def create_callback_handler(
    *,
    trace_context: Any | None = None,
):
    """Create a native v4 Langfuse CallbackHandler for LangChain integrations.

    Returns None when Langfuse is not configured or handler init fails.
    """
    from src.observability import _LANGFUSE_AVAILABLE

    if not _LANGFUSE_AVAILABLE:
        return None
    if get_langfuse_client() is None:
        return None

    try:
        from langfuse.langchain import CallbackHandler

        return CallbackHandler(trace_context=trace_context)
    except Exception:
        logger.warning("Failed to create Langfuse CallbackHandler", exc_info=True)
        return None
