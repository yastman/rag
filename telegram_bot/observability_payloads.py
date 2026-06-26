"""PII-safe input/output payload builders.

Re-exports from src.observability.safe_payloads for backward compatibility.
"""

from src.observability.safe_payloads import build_safe_input_payload, build_safe_output_payload


__all__ = ["build_safe_input_payload", "build_safe_output_payload"]
