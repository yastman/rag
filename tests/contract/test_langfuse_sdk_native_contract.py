"""Contract: lock SDK-native Langfuse v4 usage (#1648).

Issue #1648 — Langfuse v4 native usage SDK-audit.

Verified via Context7 (/langfuse/langfuse-python):
- ``@observe`` decorator wraps spans and captures inputs/outputs.
- ``langfuse.get_client()`` returns the active client for the running context.
- ``propagate_attributes(session_id=..., user_id=..., tags=..., metadata=...)``
  cascades trace attributes to all child spans.
- ``update_current_span(level="ERROR", status_message=...)`` reports failures
  on the active span without holding a direct reference.

Custom OTEL bootstrap (``OTLPSpanExporter`` / ``TracerProvider`` /
``BatchSpanProcessor``) is the EXCEPTION — only the LiveKit voice agent
constructs them because the LiveKit telemetry helper requires an explicit
provider, and the observability bootstrap module imports the type for an
``isinstance`` check during graceful shutdown. Everywhere else must rely on
Langfuse SDK auto-init through the singleton in
``telegram_bot.observability``.

Likewise, direct ``Langfuse(...)`` construction is restricted to the
production bootstrap, the evaluation modules, and a fixed list of CLI
scripts that legitimately spin up their own client.

Both allowlists are FROZEN BASELINES: they may shrink as code is
consolidated, but new entries require a deliberate review and update of
this contract. Allowlist values are exact relative paths — no wildcards,
no patterns — to keep the policy explicit and easy to audit.

Content was rephrased for compliance with licensing restrictions.

Refs #1648.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent

SCAN_DIRS: tuple[Path, ...] = (
    REPO_ROOT / "src",
    REPO_ROOT / "telegram_bot",
    REPO_ROOT / "mini_app",
    REPO_ROOT / "services",
    REPO_ROOT / "scripts",
)

# Files allowed to construct OTLPSpanExporter / TracerProvider /
# BatchSpanProcessor or to import TracerProvider from
# ``opentelemetry.sdk.trace``. Frozen baseline — must shrink, never grow.
OTEL_BOOTSTRAP_ALLOWLIST: frozenset[str] = frozenset(
    {
        # LiveKit's set_tracer_provider helper requires an explicit
        # SDK TracerProvider; this is the only legitimate manual OTEL
        # bootstrap in the production runtime.
        "src/voice/agent.py",
        # isinstance check on the active provider during graceful
        # shutdown — imports the symbol but never constructs it.
        # Lives in src/ since the observability bootstrap was unified there;
        # telegram_bot/observability_bootstrap.py is now a thin re-export shim.
        "src/observability_bootstrap.py",
    }
)

# Files allowed to construct ``Langfuse(...)`` directly. Frozen baseline —
# must shrink, never grow. The production runtime singleton lives in
# src/observability.py (re-exported by telegram_bot/observability.py for
# back-compat); evaluation modules and CLI scripts each create their own
# client because they run as standalone processes.
LANGFUSE_CTOR_ALLOWLIST: frozenset[str] = frozenset(
    {
        # Production singleton bootstrap.
        "src/observability.py",
        # Evaluation modules instantiate dedicated short-lived clients.
        "src/evaluation/langfuse_integration.py",
        "src/evaluation/ragas_evaluation.py",
        # CLI scripts running outside the bot process.
        "scripts/e2e/langfuse_latest_trace_audit.py",
        "scripts/e2e/langfuse_trace_validator.py",
        "scripts/eval/calibrate_judge.py",
        "scripts/eval/goldset_sync.py",
        "scripts/eval/run_experiment.py",
        "scripts/export_traces_to_dataset.py",
        "scripts/generate_gold_set.py",
        "scripts/langfuse_alert.py",
        "scripts/langfuse_triage.py",
        "scripts/setup_langfuse_dashboards.py",
        "scripts/setup_score_configs.py",
        "scripts/update_advisor_prompts.py",
        "scripts/validate_traces.py",
        "scripts/validate_voice_traces.py",
    }
)

OTEL_FORBIDDEN_CTOR_NAMES: frozenset[str] = frozenset(
    {
        "OTLPSpanExporter",
        "TracerProvider",
        "BatchSpanProcessor",
    }
)

OTEL_FORBIDDEN_IMPORT_MODULE = "opentelemetry.sdk.trace"
OTEL_FORBIDDEN_IMPORT_NAME = "TracerProvider"


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for d in SCAN_DIRS:
        if not d.exists():
            continue
        for p in d.rglob("*.py"):
            spath = str(p)
            if "/.venv/" in spath or "/__pycache__/" in spath:
                continue
            files.append(p)
    return files


def _parse(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return None


def _find_forbidden_otel_ctor_calls(tree: ast.AST) -> list[tuple[str, int]]:
    """Return (name, lineno) for each forbidden OTEL constructor call.

    Matches both bare names ``TracerProvider(...)`` and attribute-style
    ``foo.TracerProvider(...)`` to defend against re-export aliases.
    """
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in OTEL_FORBIDDEN_CTOR_NAMES:
            found.append((func.id, node.lineno))
        elif isinstance(func, ast.Attribute) and func.attr in OTEL_FORBIDDEN_CTOR_NAMES:
            found.append((func.attr, node.lineno))
    return found


def _find_otel_sdk_imports(tree: ast.AST) -> list[int]:
    """Return line numbers of `from opentelemetry.sdk.trace import TracerProvider`."""
    found: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module != OTEL_FORBIDDEN_IMPORT_MODULE:
            continue
        for alias in node.names:
            if alias.name == OTEL_FORBIDDEN_IMPORT_NAME:
                found.append(node.lineno)
    return found


def _find_langfuse_constructor_calls(tree: ast.AST) -> list[int]:
    """Return line numbers of bare ``Langfuse(...)`` constructor calls."""
    found: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "Langfuse":
            found.append(node.lineno)
    return found


def test_no_unallowlisted_otel_bootstrap() -> None:
    """Custom OTEL bootstrap is forbidden outside the explicit allowlist."""
    offenders: list[str] = []
    for py_file in _iter_python_files():
        rel = py_file.relative_to(REPO_ROOT).as_posix()
        if rel in OTEL_BOOTSTRAP_ALLOWLIST:
            continue
        tree = _parse(py_file)
        if tree is None:
            continue
        for name, lineno in _find_forbidden_otel_ctor_calls(tree):
            offenders.append(f"  {rel}:{lineno} -> {name}(...)")
        for lineno in _find_otel_sdk_imports(tree):
            offenders.append(
                f"  {rel}:{lineno} -> from opentelemetry.sdk.trace import TracerProvider"
            )
    if offenders:
        raise AssertionError(
            "Custom OTEL bootstrap detected outside the allowlist (#1648).\n"
            "Use SDK-native Langfuse v4 instead: @observe, langfuse.get_client(), "
            "propagate_attributes(...).\n"
            "Allowlist (exact relative paths):\n"
            + "\n".join(f"  {p}" for p in sorted(OTEL_BOOTSTRAP_ALLOWLIST))
            + "\nOffenders:\n"
            + "\n".join(offenders)
        )


def test_no_unallowlisted_langfuse_constructor() -> None:
    """Direct ``Langfuse(...)`` construction is forbidden outside the allowlist."""
    offenders: list[str] = []
    for py_file in _iter_python_files():
        rel = py_file.relative_to(REPO_ROOT).as_posix()
        if rel in LANGFUSE_CTOR_ALLOWLIST:
            continue
        tree = _parse(py_file)
        if tree is None:
            continue
        for lineno in _find_langfuse_constructor_calls(tree):
            offenders.append(f"  {rel}:{lineno} -> Langfuse(...)")
    if offenders:
        raise AssertionError(
            "Direct Langfuse() construction outside the allowlist (#1648).\n"
            "Use telegram_bot.observability.get_langfuse_client() for the bot "
            "singleton, or langfuse.get_client() inside @observe-decorated code.\n"
            "Allowlist (exact relative paths):\n"
            + "\n".join(f"  {p}" for p in sorted(LANGFUSE_CTOR_ALLOWLIST))
            + "\nOffenders:\n"
            + "\n".join(offenders)
        )


def test_allowlist_paths_exist() -> None:
    """Allowlist entries must point to real files — protects against drift on rename."""
    missing: list[str] = []
    for rel in sorted(OTEL_BOOTSTRAP_ALLOWLIST | LANGFUSE_CTOR_ALLOWLIST):
        if not (REPO_ROOT / rel).exists():
            missing.append(rel)
    assert not missing, (
        "Allowlist points to missing files (#1648). Update the contract test "
        "after a rename/delete:\n" + "\n".join(f"  {p}" for p in missing)
    )


def test_allowlist_entries_actually_use_pattern() -> None:
    """Stale allowlist entries are rejected — forces shrinkage as code is consolidated."""
    stale: list[str] = []

    for rel in OTEL_BOOTSTRAP_ALLOWLIST:
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        tree = _parse(path)
        if tree is None:
            continue
        has_ctor = bool(_find_forbidden_otel_ctor_calls(tree))
        has_import = bool(_find_otel_sdk_imports(tree))
        if not (has_ctor or has_import):
            stale.append(f"  {rel} (no OTEL bootstrap usage remains)")

    for rel in LANGFUSE_CTOR_ALLOWLIST:
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        tree = _parse(path)
        if tree is None:
            continue
        if not _find_langfuse_constructor_calls(tree):
            stale.append(f"  {rel} (no Langfuse() constructor remains)")

    assert not stale, (
        "Stale allowlist entries (#1648) — remove from this contract test:\n"
        + "\n".join(stale)
    )
