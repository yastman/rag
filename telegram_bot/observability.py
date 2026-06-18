"""Langfuse observability helpers with runtime initialization.

Re-exports from src.observability for backward compatibility.
create_callback_handler is now implemented in src.observability.langfuse_client
so that langfuse.langchain is accessed only through the observability kernel.
"""

import logging

from src.observability import (
    _LANGFUSE_AVAILABLE,
    _install_langfuse_warning_filters,
    _reset_langfuse_client_for_tests,
    create_callback_handler,
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
    "_LANGFUSE_AVAILABLE",
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
