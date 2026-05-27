"""Tests for scripts/probe/observability_diagnostic.py classifier (#2199).

The diagnostic probe ingests recent Langfuse worker logs and LiteLLM proxy
logs and classifies each line as one of:

  - LANGFUSE_QUEUE_TIMEOUT  — repeated 'Socket timeout' on worker queues
  - LITELLM_AUTH_NOISE      — 'No api key passed in.' from /v1/models probes
  - LANGFUSE_PROMPT_MISS    — prompt lookup warnings (expected dev state)
  - METRICS_PORT_CONFLICT   — bot /metrics bind failure (#2190 — already
                              tracked, but we still classify it for
                              evidence collection)
  - HEALTHY                 — line is benign / informational
  - UNKNOWN                 — could not be classified

The classifier is pure (no I/O) so it is unit-testable.
"""

from __future__ import annotations

import pytest

from scripts.probe.observability_diagnostic import (
    DiagnosticCategory,
    classify_log_line,
    summarize_classifications,
)


@pytest.mark.parametrize(
    "line,expected",
    [
        (
            "Queue job ... errored: Error: Socket timeout. Expecting data, but didn't receive any in 30000ms.",
            DiagnosticCategory.LANGFUSE_QUEUE_TIMEOUT,
        ),
        (
            "[langfuse] data-retention queue: Error: Socket timeout. Expecting data...",
            DiagnosticCategory.LANGFUSE_QUEUE_TIMEOUT,
        ),
        (
            "litellm.proxy.proxy_server.user_api_key_auth(): Exception occured - No api key passed in.",
            DiagnosticCategory.LITELLM_AUTH_NOISE,
        ),
        (
            'INFO: 127.0.0.1:55432 - "GET /models HTTP/1.1" 401 Unauthorized',
            DiagnosticCategory.LITELLM_AUTH_NOISE,
        ),
        (
            "Cannot bind Prometheus metrics server on 127.0.0.1:9091: [Errno 98] Address already in use; /metrics disabled",
            DiagnosticCategory.METRICS_PORT_CONFLICT,
        ),
        (
            "Langfuse prompt 'router-classifier' not found in cache or remote; using fallback",
            DiagnosticCategory.LANGFUSE_PROMPT_MISS,
        ),
        (
            "INFO: app started",
            DiagnosticCategory.HEALTHY,
        ),
        (
            "BGSAVE done",
            DiagnosticCategory.HEALTHY,
        ),
    ],
)
def test_classify_known_lines(line: str, expected: DiagnosticCategory) -> None:
    assert classify_log_line(line) is expected


def test_unknown_pattern_falls_back_to_unknown() -> None:
    assert classify_log_line("totally novel error pattern from new component") is (
        DiagnosticCategory.UNKNOWN
    )


def test_summarize_counts_categories() -> None:
    lines = [
        "Queue job ... errored: Error: Socket timeout.",
        "Queue job ... errored: Error: Socket timeout.",
        "user_api_key_auth(): Exception occured - No api key passed in.",
        "INFO: routine log",
    ]
    summary = summarize_classifications(lines)
    assert summary[DiagnosticCategory.LANGFUSE_QUEUE_TIMEOUT] == 2
    assert summary[DiagnosticCategory.LITELLM_AUTH_NOISE] == 1
    assert summary[DiagnosticCategory.HEALTHY] == 1


def test_summarize_handles_empty_input() -> None:
    summary = summarize_classifications([])
    # All categories present with zero counts.
    for cat in DiagnosticCategory:
        assert summary[cat] == 0


def test_summary_threshold_for_queue_timeouts() -> None:
    """The acceptance criterion 'no repeated queue timeouts in 5 minutes' is
    interpreted as: more than ``QUEUE_TIMEOUT_NOISE_THRESHOLD`` socket
    timeouts in the inspected window is a degraded signal.
    """
    from scripts.probe.observability_diagnostic import (
        QUEUE_TIMEOUT_NOISE_THRESHOLD,
        is_degraded,
    )

    # Below threshold → not degraded.
    summary = dict.fromkeys(DiagnosticCategory, 0)
    summary[DiagnosticCategory.LANGFUSE_QUEUE_TIMEOUT] = max(0, QUEUE_TIMEOUT_NOISE_THRESHOLD - 1)
    assert is_degraded(summary) is False

    # Above threshold → degraded.
    summary[DiagnosticCategory.LANGFUSE_QUEUE_TIMEOUT] = QUEUE_TIMEOUT_NOISE_THRESHOLD + 1
    assert is_degraded(summary) is True
