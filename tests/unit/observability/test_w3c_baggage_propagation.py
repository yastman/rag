"""Unit tests for W3C Baggage propagation across HTTP boundaries (#2226).

Background: Langfuse v4 SDK is built on top of OpenTelemetry. The default
``opentelemetry.propagate.get_global_textmap()`` is a CompositePropagator
that already serializes ``traceparent``, ``tracestate`` and ``baggage``
on outbound HTTP requests when ``HTTPXClientInstrumentor`` (#2225) is
active. The Langfuse-canonical way to populate ``baggage`` with
``user_id`` / ``session_id`` / ``tags`` from a server-side request is
``propagate_attributes(..., as_baggage=True)``.

Pass-5 finding from #2215 audit confirmed that #2229 used **bare OTEL**
``propagate.extract`` / ``propagate.inject`` for bge-m3 cross-service
trace context — that carries ``traceparent`` (parent-child wiring works)
but does NOT carry the Langfuse trace attributes. Result: bge-m3 spans
land under the right trace in Langfuse UI but with empty user_id /
session_id / tags filters.

This file pins the contract:

1. Every entry-point ``propagate_attributes(...)`` in the codebase that
   surrounds a cross-process boundary (bot ingress, mini-app ingress,
   rag-api receiver, voice agent) MUST pass ``as_baggage=True``.
2. After this change, no per-call ``inject(headers)`` plumbing is needed
   on the client side — ``HTTPXClientInstrumentor`` (#2225) injects the
   default propagator (which includes baggage) automatically.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]


# Entry points that surround cross-process boundaries. Each must call
# ``propagate_attributes(..., as_baggage=True)`` so the Langfuse SDK puts
# user_id/session_id/tags into the W3C ``baggage`` HTTP header that
# HTTPXClientInstrumentor (Epic O #2225) injects automatically.
_REQUIRED_AS_BAGGAGE_CALL_SITES: tuple[tuple[str, str], ...] = (
    # (relative_path, function_name_or_class_marker)
    ("telegram_bot/middlewares/langfuse_middleware.py", "LangfuseContextMiddleware"),
    ("mini_app/api.py", "start_expert / submit_phone"),
    ("src/api/main.py", "_execute_query"),
)


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _find_propagate_attributes_calls(source: str) -> list[str]:
    """Return text of every ``propagate_attributes(...)`` call in ``source``."""
    calls: list[str] = []
    pattern = re.compile(r"propagate_attributes\s*\(", re.MULTILINE)
    for match in pattern.finditer(source):
        depth = 0
        i = match.end() - 1  # at the opening paren
        start = i
        while i < len(source):
            if source[i] == "(":
                depth += 1
            elif source[i] == ")":
                depth -= 1
                if depth == 0:
                    calls.append(source[start : i + 1])
                    break
            i += 1
    return calls


class TestPropagateAttributesUsesBaggage:
    """Each cross-boundary entry point must pass ``as_baggage=True``."""

    @pytest.mark.parametrize("path,marker", _REQUIRED_AS_BAGGAGE_CALL_SITES)
    def test_propagate_attributes_at_entry_point_uses_as_baggage(
        self, path: str, marker: str
    ) -> None:
        source = _read(path)
        calls = _find_propagate_attributes_calls(source)
        assert calls, (
            f"{path}: expected at least one propagate_attributes(...) call but "
            f"found none — the {marker} entry point would not propagate "
            f"user_id/session_id/tags to downstream services (#2226)."
        )

        # Direct kwarg in the call OR ``"as_baggage": True`` in any kwargs
        # dict that the file unpacks via ``**kwargs`` into propagate_attributes.
        baggage_inline = [c for c in calls if "as_baggage=True" in c]
        baggage_via_kwargs = re.search(
            r'["\']as_baggage["\']\s*:\s*True', source
        ) is not None and any("**" in c for c in calls)
        if baggage_inline or baggage_via_kwargs:
            return

        pytest.fail(
            f"{path}: every propagate_attributes(...) at the {marker} entry "
            f"point must pass as_baggage=True so the Langfuse SDK injects "
            f"user_id/session_id/tags into the W3C 'baggage' HTTP header "
            f"(#2226). Found calls without as_baggage=True:\n  "
            + "\n  ".join(c.replace("\n", " ") for c in calls)
        )


class TestComposedPropagatorIncludesBaggage:
    """The OTEL default global propagator must include W3C Baggage.

    OTEL Python defaults to ``CompositePropagator(['baggage', 'traceparent',
    'tracestate'])`` — we don't need to call ``set_global_textmap(...)``,
    but if anyone changes it later, this test catches a regression that
    would silently disable as_baggage=True propagation.
    """

    def test_default_global_propagator_carries_baggage(self) -> None:
        from opentelemetry import propagate

        propagator = propagate.get_global_textmap()
        assert "baggage" in propagator.fields, (
            "Global OTEL propagator must include 'baggage' so "
            "propagate_attributes(as_baggage=True) actually serializes "
            "user_id/session_id/tags to outbound HTTP headers (#2226). "
            f"Current fields: {sorted(propagator.fields)}"
        )
        assert "traceparent" in propagator.fields, (
            "Global OTEL propagator must include 'traceparent' for "
            "parent-child trace wiring across HTTP boundaries (#2226)."
        )


class TestPropagateAttributesSignatureSupportsBaggage:
    """Sanity check: the installed Langfuse SDK signature actually accepts
    ``as_baggage``. If a future SDK upgrade renames the parameter, this
    test fails fast instead of silently dropping the kwarg."""

    def test_propagate_attributes_accepts_as_baggage_kwarg(self) -> None:
        from langfuse import propagate_attributes

        sig = inspect.signature(propagate_attributes)
        assert "as_baggage" in sig.parameters, (
            "Langfuse SDK propagate_attributes() must accept as_baggage "
            "kwarg (#2226). Available kwargs: " + ", ".join(sig.parameters)
        )
