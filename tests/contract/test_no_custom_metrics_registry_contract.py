"""Contract: no parallel metrics registry, no new rolling p50/p95 stores.

Issue ***REMOVED***1648's "Forbidden" list binds the SDK-native observability
migration:

  * No new custom metrics registry. Production code must use the
    package-wide default ``prometheus_client.REGISTRY``; instantiating a
    fresh ``CollectorRegistry()`` defeats SDK-native scraping (the
    eventual ASGI ``/metrics`` mount in slice 4/4 only exposes the
    default registry).
  * No new in-memory rolling p50/p95 dictionaries. The legacy
    ``telegram_bot/services/metrics.py`` rolling-window survives slice
    2/4 as a deprecated facade for the bot's admin ``/metrics``
    Telegram command, but no new files may grow this anti-pattern;
    distributions belong in ``prometheus_client.Histogram``.

This contract test scans production paths and fails on either
violation. The metrics module that holds the deprecated facade is on a
shrinking allowlist that disappears when slice 4/4 lands.

Refs ***REMOVED***1648.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent

SCAN_DIRS = [
    REPO_ROOT / "src",
    REPO_ROOT / "scripts",
    REPO_ROOT / "telegram_bot",
    REPO_ROOT / "mini_app",
    REPO_ROOT / "services",
]

***REMOVED*** Allowlist for the deprecated rolling-window p50/p95 surface that this
***REMOVED*** slice (***REMOVED***1648 slice 2/4) keeps as a backward-compat facade. Slice 4/4
***REMOVED*** (ASGI /metrics mount) deletes the runtime rolling-window entirely;
***REMOVED*** the allowlist must shrink, never grow.
***REMOVED***
***REMOVED*** Offline / reporting paths are also allowlisted — they post-process
***REMOVED*** already-collected samples rather than maintaining a live rolling
***REMOVED*** window in the request path. They are not in scope for ***REMOVED***1648 (which
***REMOVED*** targets runtime observability) but the regex picks them up because
***REMOVED*** ``p50`` / ``p95`` are convenient evaluation column names.
ROLLING_WINDOW_ALLOWLIST: frozenset[str] = frozenset(
    {
        ***REMOVED*** Deprecated runtime facade — replaced by pipeline_latency_seconds
        ***REMOVED*** Histogram in slice 2/4; full deletion in slice 4/4.
        "telegram_bot/services/metrics.py",
        ***REMOVED*** Offline evaluation harness: computes quantiles from a list of
        ***REMOVED*** latencies recorded during a benchmark run, then emits a
        ***REMOVED*** Prometheus text-format dump. Not a runtime path.
        "src/evaluation/metrics_logger.py",
        ***REMOVED*** Reporting scripts: format Langfuse / trace dashboard payloads.
        ***REMOVED*** They consume p50/p95 columns rather than producing rolling
        ***REMOVED*** quantiles in the live request path.
        "scripts/setup_langfuse_dashboards.py",
        "scripts/validate_traces.py",
    }
)

***REMOVED*** A custom CollectorRegistry inside services/bge-m3-api would be a
***REMOVED*** violation too, but no production file currently constructs one. If a
***REMOVED*** vendored prometheus exposition tool ever needs an isolated registry
***REMOVED*** for testing, add it here with an explicit reference to the issue
***REMOVED*** tracking the exception.
COLLECTOR_REGISTRY_ALLOWLIST: frozenset[str] = frozenset()


***REMOVED*** Pattern matching ``CollectorRegistry(`` as a constructor call, but
***REMOVED*** NOT references like ``prometheus_client.REGISTRY`` (the default
***REMOVED*** instance) or imports.
_COLLECTOR_REGISTRY_CALL = re.compile(r"\bCollectorRegistry\s*\(")

***REMOVED*** Words ``p50`` / ``p95`` appearing in code (not in docstrings or
***REMOVED*** comments) signal a custom rolling-window quantile aggregator.
***REMOVED*** We use AST-level inspection to avoid false positives in documentation.
_QUANTILE_TOKENS = ("p50", "p95")


def _iter_python_files(directories: list[Path]) -> list[Path]:
    files: list[Path] = []
    for d in directories:
        if not d.exists():
            continue
        for p in d.rglob("*.py"):
            s = str(p)
            if "/.venv/" in s or "/__pycache__/" in s:
                continue
            files.append(p)
    return files


def _find_collector_registry_calls(source: str) -> list[int]:
    """Return line numbers where ``CollectorRegistry(...)`` is constructed.

    A bare reference such as ``REGISTRY = CollectorRegistry`` (no
    parens) does not count — we are after live registries.
    """
    offenders: list[int] = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        ***REMOVED*** Strip line-comment to avoid false positives in `***REMOVED*** explain CollectorRegistry()`.
        code = line.split("***REMOVED***", 1)[0]
        if _COLLECTOR_REGISTRY_CALL.search(code):
            offenders.append(lineno)
    return offenders


def _find_rolling_pxx_definitions(source: str, file_path: Path) -> list[int]:
    """Return line numbers where ``p50``/``p95`` are *defined* in code.

    We look for AST nodes that correspond to:

      * Assignment targets named ``p50``/``p95``.
      * Dict literal keys ``"p50"`` / ``"p95"`` (the legacy
        rolling-window emits these in ``get_stats()``).

    Pure references (e.g. ``stats["p50"]`` read access) are ignored —
    they may be legitimate consumers of the deprecated facade.
    """
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return []

    offenders: list[int] = []
    for node in ast.walk(tree):
        ***REMOVED*** ``p50 = ...`` or ``p95 = ...``
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in _QUANTILE_TOKENS:
                    offenders.append(node.lineno)
        ***REMOVED*** ``{"p50": ..., "p95": ...}`` literals.
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if (
                    isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                    and key.value in _QUANTILE_TOKENS
                ):
                    offenders.append(getattr(key, "lineno", node.lineno))
    return offenders


def test_no_custom_collector_registry_construction() -> None:
    """Production code must not instantiate a private ``CollectorRegistry``."""
    new_offenders: list[tuple[str, int]] = []
    for py_file in _iter_python_files(SCAN_DIRS):
        rel = str(py_file.relative_to(REPO_ROOT))
        if rel in COLLECTOR_REGISTRY_ALLOWLIST:
            continue
        for lineno in _find_collector_registry_calls(py_file.read_text()):
            new_offenders.append((rel, lineno))

    if new_offenders:
        bullets = "\n".join(f"  {rel}:{ln}" for rel, ln in new_offenders)
        raise AssertionError(
            "New CollectorRegistry() instantiations detected (***REMOVED***1648 slice 2/4):\n"
            + bullets
            + "\nUse the package-wide prometheus_client.REGISTRY default. "
            "A custom registry breaks the planned ASGI /metrics ASGI mount "
            "(slice 4/4) which only scrapes the default registry."
        )


def test_no_new_rolling_pxx_definitions_outside_allowlist() -> None:
    """Custom rolling p50/p95 dicts must stay confined to the deprecated file.

    Slice 4/4 will delete the surviving rolling-window altogether.
    Until then, only ``telegram_bot/services/metrics.py`` may keep the
    surface for the admin ``/metrics`` Telegram command.
    """
    new_offenders: list[tuple[str, int]] = []
    for py_file in _iter_python_files(SCAN_DIRS):
        rel = str(py_file.relative_to(REPO_ROOT))
        if rel in ROLLING_WINDOW_ALLOWLIST:
            continue
        for lineno in _find_rolling_pxx_definitions(py_file.read_text(), py_file):
            new_offenders.append((rel, lineno))

    if new_offenders:
        bullets = "\n".join(f"  {rel}:{ln}" for rel, ln in new_offenders)
        raise AssertionError(
            "New custom rolling p50/p95 definitions detected (***REMOVED***1648):\n"
            + bullets
            + "\nUse prometheus_client.Histogram instead. See "
            "telegram_bot/services/metrics.py::pipeline_latency_seconds "
            "for the canonical SDK-native pattern."
        )


def test_collector_registry_pattern_detects_constructor_calls() -> None:
    """Self-test: the pattern catches construction but ignores attribute access."""
    src = "from prometheus_client import CollectorRegistry\nreg = CollectorRegistry()\n"
    assert _find_collector_registry_calls(src) == [2]

    src_attr = "from prometheus_client import REGISTRY\nuse(REGISTRY)\n"
    assert _find_collector_registry_calls(src_attr) == []


def test_rolling_pxx_finder_ignores_consumer_reads() -> None:
    """Self-test: read-access ``stats['p50']`` is allowed; only definitions fail."""
    src_read = "value = stats['p50']\n"
    assert _find_rolling_pxx_definitions(src_read, Path("dummy.py")) == []

    src_def = '{"p50": 1.0, "p95": 2.0}\n'
    ***REMOVED*** Both keys live on the same dict literal line.
    assert _find_rolling_pxx_definitions(src_def, Path("dummy.py")) == [1, 1]
