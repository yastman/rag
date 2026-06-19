"""src.observability package — observability helpers.

Langfuse removed (#2844). Public API stubs preserved for backwards compatibility.
Structured product logs (src/utils/product_events.py) are the canonical observability path.
"""

from src.observability.bootstrap import disable_otel_exporter, is_endpoint_reachable
from src.observability.langfuse_client import (
    _LANGFUSE_AVAILABLE,
    Langfuse,
    _install_langfuse_warning_filters,
    _reset_langfuse_client_for_tests,
    create_callback_handler,
    flush_langfuse,
    get_client,
    get_langfuse_client,
    get_score_config_types,
    initialize_langfuse,
    make_lifecycle_session_id,
    mask_pii,
    observe,
    propagate_attributes,
    traced_pipeline,
    try_update_lifecycle_trace_async,
    update_lifecycle_trace,
)
from src.observability.langfuse_model_sync import sync_langfuse_model_definitions
from src.observability.safe_payloads import build_safe_input_payload, build_safe_output_payload
from src.observability.scores import (
    compute_checkpointer_overhead_proxy_ms,
    score,
    write_history_scores,
    write_langfuse_scores,
)


# Legacy aliases
_disable_otel_exporter = disable_otel_exporter
_is_endpoint_reachable = is_endpoint_reachable

__all__ = [
    "_LANGFUSE_AVAILABLE",
    "Langfuse",
    "_disable_otel_exporter",
    "_install_langfuse_warning_filters",
    "_is_endpoint_reachable",
    "_reset_langfuse_client_for_tests",
    "build_safe_input_payload",
    "build_safe_output_payload",
    "compute_checkpointer_overhead_proxy_ms",
    "create_callback_handler",
    "disable_otel_exporter",
    "flush_langfuse",
    "get_client",
    "get_langfuse_client",
    "get_score_config_types",
    "initialize_langfuse",
    "is_endpoint_reachable",
    "make_lifecycle_session_id",
    "mask_pii",
    "observe",
    "propagate_attributes",
    "score",
    "sync_langfuse_model_definitions",
    "traced_pipeline",
    "try_update_lifecycle_trace_async",
    "update_lifecycle_trace",
    "write_history_scores",
    "write_langfuse_scores",
]
