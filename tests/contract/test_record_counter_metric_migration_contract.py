"""Contract test for issue #2056 — log/record_counter_metric → record_pipeline_event.

Issue #1648 slice 3/4 (#2056) replaces the legacy
``record_counter_metric(name)`` shim with the SDK-native
``record_pipeline_event(event)`` Counter API exported by
``telegram_bot.services.metrics``.

The legacy ``record_counter_metric`` function is intentionally kept inside
``telegram_bot/services/metrics.py`` as a thin compatibility wrapper —
removing it is scoped to #2058 (slice 4/4 cleanup), not this issue. So
this contract enforces a directional rule:

* ``record_counter_metric`` may only be **defined** in
  ``telegram_bot/services/metrics.py``.
* ``record_counter_metric`` may not be **imported** or **called** from
  any first-party module under ``telegram_bot/``, ``src/``, ``mini_app/``,
  or ``services/``.
* All event-counter call-sites must use ``record_pipeline_event``.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
METRICS_OWNER = REPO / "src" / "runtime" / "services" / "metrics.py"

FIRST_PARTY_ROOTS = ("src", "telegram_bot", "mini_app", "services")

IMPORT_RE = re.compile(
    r"^\s*from\s+(telegram_bot|src\.runtime)\.services\.metrics\s+import\s+[^#\n]*\brecord_counter_metric\b",
    re.MULTILINE,
)
CALL_RE = re.compile(r"\brecord_counter_metric\s*\(")


def _python_files() -> list[Path]:
    skip = {".git", ".venv", "venv", "__pycache__", ".pytest_cache"}
    out: list[Path] = []
    for root_name in FIRST_PARTY_ROOTS:
        root = REPO / root_name
        if not root.exists():
            continue
        for py in root.rglob("*.py"):
            if any(part in skip for part in py.parts):
                continue
            out.append(py)
    return out


def test_record_counter_metric_not_imported_outside_metrics_module() -> None:
    offenders: list[str] = []
    for path in _python_files():
        if path == METRICS_OWNER:
            continue
        text = path.read_text(encoding="utf-8")
        if IMPORT_RE.search(text):
            offenders.append(str(path.relative_to(REPO)))
    assert offenders == [], (
        "record_counter_metric is a legacy compatibility shim (issue #2056). "
        "First-party code must import record_pipeline_event from "
        "src.runtime.services.metrics (or its telegram_bot.services.metrics shim) instead. "
        f"Offending imports: {offenders}"
    )


def test_record_counter_metric_not_called_outside_metrics_module() -> None:
    offenders: list[str] = []
    for path in _python_files():
        if path == METRICS_OWNER:
            continue
        text = path.read_text(encoding="utf-8")
        if CALL_RE.search(text):
            offenders.append(str(path.relative_to(REPO)))
    assert offenders == [], (
        "record_counter_metric() is a legacy compatibility shim (issue #2056). "
        "First-party call-sites must use record_pipeline_event(event, amount). "
        f"Offending callers: {offenders}"
    )


def test_record_pipeline_event_remains_the_canonical_counter_api() -> None:
    """Sanity guard: the new SDK-native helper still exists and is exported."""
    text = METRICS_OWNER.read_text(encoding="utf-8")
    assert "def record_pipeline_event(" in text, (
        "record_pipeline_event() must remain the canonical Counter API in "
        "src/runtime/services/metrics.py (issue #2056)."
    )
    assert '"record_pipeline_event"' in text or "'record_pipeline_event'" in text, (
        "record_pipeline_event must be in the module __all__ export list."
    )
