"""src.observability package — consolidated observability helpers.

Re-exports all public symbols from submodules for backwards compatibility.
Consumers can import from ``src.observability`` (shim), ``src.observability.*``
(new canonical paths), or any of the old ``src.observability_*.py`` shims.
"""

from src.observability.bootstrap import disable_otel_exporter, is_endpoint_reachable
from src.observability.langfuse_client import (
    _LANGFUSE_AVAILABLE,
    Langfuse,
    _disable_otel_exporter,
    _install_langfuse_warning_filters,
    _is_endpoint_reachable,
    _reset_langfuse_client_for_tests,
    flush_langfuse,
    get_client,
    get_langfuse_client,
    initialize_langfuse,
    make_lifecycle_session_id,
    mask_pii,
    observe,
    propagate_attributes,
    sync_langfuse_model_definitions,
    traced_pipeline,
    try_update_lifecycle_trace_async,
    update_lifecycle_trace,
)
from src.observability.safe_payloads import build_safe_input_payload, build_safe_output_payload
from src.observability.scores import (
    compute_checkpointer_overhead_proxy_ms,
    score,
    write_crm_scores,
    write_history_scores,
    write_langfuse_scores,
)
from src.observability.sentry_integration import (
    add_safe_breadcrumb,
    hash_id,
    initialize_sentry,
    runtime_scope,
    set_runtime_tags,
)


__all__ = [
    "_LANGFUSE_AVAILABLE",
    "Langfuse",
    "_disable_otel_exporter",
    "_install_langfuse_warning_filters",
    "_is_endpoint_reachable",
    "_reset_langfuse_client_for_tests",
    "add_safe_breadcrumb",
    "build_safe_input_payload",
    "build_safe_output_payload",
    "compute_checkpointer_overhead_proxy_ms",
    "disable_otel_exporter",
    "flush_langfuse",
    "get_client",
    "get_langfuse_client",
    "hash_id",
    "initialize_langfuse",
    "initialize_sentry",
    "is_endpoint_reachable",
    "make_lifecycle_session_id",
    "mask_pii",
    "observe",
    "propagate_attributes",
    "runtime_scope",
    "score",
    "set_runtime_tags",
    "sync_langfuse_model_definitions",
    "traced_pipeline",
    "try_update_lifecycle_trace_async",
    "update_lifecycle_trace",
    "write_crm_scores",
    "write_history_scores",
    "write_langfuse_scores",
]
