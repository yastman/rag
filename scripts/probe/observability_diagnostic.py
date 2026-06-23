#!/usr/bin/env python3
"""Local Langfuse / LiteLLM observability diagnostic (#2199).

Ingests recent log lines from the running compose stack, classifies each
into a stable :class:`DiagnosticCategory`, and reports a summary that
maps directly onto the issue's acceptance criteria:

  - Langfuse worker queue socket timeouts (degraded if above noise
    threshold over the inspected window).
  - LiteLLM ``/v1/models`` unauthenticated probes (auth contract noise).
  - Langfuse prompt-lookup misses (expected dev state vs config drift).
  - Bot ``/metrics`` port collisions — already tracked in #2190; the
    classifier still surfaces them so the operator has evidence.

The script is structured so the classification is pure and unit-testable;
log collection is a thin shell over ``docker compose logs``.

CLI::

    # Collect last 200 lines from the running compose stack and classify.
    uv run python -m scripts.probe.observability_diagnostic

    # Read pre-collected log lines from a file (CI-friendly, deterministic).
    uv run python -m scripts.probe.observability_diagnostic --from-file logs.txt

Refs #2199.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess  # nosec B404
import sys
from collections import Counter
from collections.abc import Iterable
from enum import StrEnum
from pathlib import Path


# ---------------------------------------------------------------------------
# Categories + thresholds
# ---------------------------------------------------------------------------


class DiagnosticCategory(StrEnum):
    LANGFUSE_QUEUE_TIMEOUT = "langfuse_queue_timeout"
    LITELLM_AUTH_NOISE = "litellm_auth_noise"
    LANGFUSE_PROMPT_MISS = "langfuse_prompt_miss"
    METRICS_PORT_CONFLICT = "metrics_port_conflict"
    HEALTHY = "healthy"
    UNKNOWN = "unknown"


# Threshold for "repeated queue socket timeouts" interpreted from the
# acceptance criterion "5 minutes of healthy worker logs".  We inspect the
# last N lines per service; more than this many timeouts in the window is
# the degraded signal we surface.
QUEUE_TIMEOUT_NOISE_THRESHOLD = 3


# ---------------------------------------------------------------------------
# Classifier (pure)
# ---------------------------------------------------------------------------

_PATTERNS: tuple[tuple[re.Pattern[str], DiagnosticCategory], ...] = (
    # Langfuse worker queue timeouts. Matches the canonical message
    # "Error: Socket timeout. Expecting data..." emitted by ioredis when a
    # background queue command exceeds the configured timeout, plus any
    # truncated form ("Error: Socket timeout.") seen in summaries.
    (
        re.compile(
            r"Socket timeout",
            re.IGNORECASE,
        ),
        DiagnosticCategory.LANGFUSE_QUEUE_TIMEOUT,
    ),
    # LiteLLM auth noise: unauthenticated /v1/models probes etc.
    (
        re.compile(r"No api key passed in", re.IGNORECASE),
        DiagnosticCategory.LITELLM_AUTH_NOISE,
    ),
    (
        re.compile(r'"GET /(?:v1/)?models[^"]*"\s+401', re.IGNORECASE),
        DiagnosticCategory.LITELLM_AUTH_NOISE,
    ),
    # Bot metrics bind failure (#2190).
    (
        re.compile(
            r"Cannot bind Prometheus metrics server.*Address already in use",
            re.IGNORECASE,
        ),
        DiagnosticCategory.METRICS_PORT_CONFLICT,
    ),
    # Langfuse prompt lookup miss (expected dev state when prompts are not
    # seeded into the local Langfuse project yet).
    (
        re.compile(
            r"Langfuse prompt .* not found.*fallback",
            re.IGNORECASE,
        ),
        DiagnosticCategory.LANGFUSE_PROMPT_MISS,
    ),
    # Healthy markers seen during the audit (used to keep noise out of UNKNOWN).
    (re.compile(r"BGSAVE done", re.IGNORECASE), DiagnosticCategory.HEALTHY),
    (
        re.compile(
            r"Background saving terminated with success",
            re.IGNORECASE,
        ),
        DiagnosticCategory.HEALTHY,
    ),
    (re.compile(r"^INFO:", re.IGNORECASE), DiagnosticCategory.HEALTHY),
)


def classify_log_line(line: str) -> DiagnosticCategory:
    """Classify one log line using the priority-ordered patterns."""
    for pattern, category in _PATTERNS:
        if pattern.search(line):
            return category
    return DiagnosticCategory.UNKNOWN


def summarize_classifications(lines: Iterable[str]) -> dict[DiagnosticCategory, int]:
    """Count classified categories across an iterable of log lines."""
    counts: Counter[DiagnosticCategory] = Counter(classify_log_line(line) for line in lines)
    # Return a complete dict so callers can index every category.
    return {cat: counts.get(cat, 0) for cat in DiagnosticCategory}


def is_degraded(summary: dict[DiagnosticCategory, int]) -> bool:
    """Return True when the summary crosses any degraded threshold."""
    return summary.get(DiagnosticCategory.LANGFUSE_QUEUE_TIMEOUT, 0) > QUEUE_TIMEOUT_NOISE_THRESHOLD


# ---------------------------------------------------------------------------
# Log collection (thin)
# ---------------------------------------------------------------------------

DEFAULT_SERVICES: tuple[str, ...] = (
    "langfuse-worker",
    "langfuse-web",
    "litellm",
    "bot",
)
DEFAULT_TAIL_LINES = 200


def collect_compose_logs(
    services: Iterable[str] = DEFAULT_SERVICES,
    *,
    tail: int = DEFAULT_TAIL_LINES,
) -> list[str]:
    """Tail compose service logs and return them as a list of lines.

    Returns an empty list when ``docker`` is not on PATH or any compose
    invocation fails — the diagnostic should never crash a healthy host
    just because Docker is unreachable.
    """
    if shutil.which("docker") is None:
        return []
    out: list[str] = []
    for service in services:
        try:
            cp = subprocess.run(  # nosec B603 B607
                [
                    "docker",
                    "compose",
                    "logs",
                    "--no-color",
                    "--tail",
                    str(tail),
                    service,
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (subprocess.TimeoutExpired, OSError):
            continue
        if cp.returncode != 0:
            continue
        out.extend(cp.stdout.splitlines())
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_summary(summary: dict[DiagnosticCategory, int]) -> None:
    print("Observability diagnostic summary (#2199):")
    for cat in DiagnosticCategory:
        print(f"  {cat.value:<26}  {summary.get(cat, 0)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--from-file",
        type=Path,
        default=None,
        help="Read log lines from a file instead of running docker compose logs.",
    )
    parser.add_argument(
        "--tail",
        type=int,
        default=DEFAULT_TAIL_LINES,
        help="Lines per service to tail when collecting from compose.",
    )
    args = parser.parse_args(argv)

    if args.tail < 1:
        parser.error("--tail must be a positive integer")

    if args.from_file is not None:
        if not args.from_file.is_file():
            parser.error(f"--from-file does not exist: {args.from_file}")
        lines = args.from_file.read_text(encoding="utf-8").splitlines()
    else:
        lines = collect_compose_logs(tail=args.tail)

    summary = summarize_classifications(lines)
    _print_summary(summary)
    return 1 if is_degraded(summary) else 0


if __name__ == "__main__":
    sys.exit(main())
