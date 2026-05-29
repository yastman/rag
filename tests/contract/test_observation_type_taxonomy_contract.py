"""Observation-type taxonomy contract (#2216 / Epic F).

Langfuse v4 supports a typed observation taxonomy via ``@observe(as_type=...)``:
span | generation | event | agent | tool | chain | retriever | embedding |
evaluator | guardrail. The Langfuse UI has dedicated filters / dashboards per
type (e.g. "show me only guardrail rejections", "tool latency").

Pre-#2216 the repo used ``embedding`` / ``generation`` / ``retriever`` /
``evaluator`` correctly but every LLM-callable agent tool and every guard
node landed in the generic ``span`` bucket. This contract enforces the
semantic taxonomy for the two unambiguous categories:

* **tool** — LLM-callable agent tools (``tool-*``, ``crm-*``, ``manager-*``
  decorators in ``telegram_bot/agents/``).
* **guardrail** — pre-flight guard nodes (``node-guard``, ``history-guard``).

A regression that drops ``as_type`` (or sets the wrong one) on a decorated
agent tool / guard fails this contract.

Scope note: aiogram-dialog handlers (``dialog-*``, ``crm-quick-*``,
``crm-task-*``) are UI flows, not LLM agent tools, so they intentionally
stay as the default ``span`` and are not covered here.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
BOT_PY = REPO_ROOT / "telegram_bot" / "bot.py"

# observe-name -> required as_type. Exact-match on the @observe(name=...) value.
_REQUIRED_AS_TYPE: dict[str, str] = {
    # --- agent tools -> "tool" ---
    "tool-rag-search": "tool",
    "tool-apartment-search": "tool",
    "tool-history-search": "tool",
    "tool-mortgage-calculator": "tool",
    "tool-daily-summary": "tool",
    "tool-handoff": "tool",
    "tool-crm-sync-lead-score": "tool",
    "manager-get-funnel-analytics": "tool",
    "manager-run-nurturing-batch": "tool",
    "crm-get-deal": "tool",
    "crm-get-contacts": "tool",
    "crm-create-lead": "tool",
    "crm-update-lead": "tool",
    "crm-upsert-contact": "tool",
    "crm-add-note": "tool",
    "crm-create-task": "tool",
    "crm-link-contact-to-deal": "tool",
    "crm-search-leads": "tool",
    "crm-get-my-leads": "tool",
    "crm-get-my-tasks": "tool",
    "crm-update-contact": "tool",
    # --- guard nodes -> "guardrail" ---
    "node-guard": "guardrail",
    "history-guard": "guardrail",
}

_SCAN_DIRS = (
    REPO_ROOT / "telegram_bot" / "agents",
    REPO_ROOT / "src" / "runtime" / "graph" / "nodes",
)


def _decorator_name_and_kwargs(dec: ast.Call) -> tuple[str | None, dict[str, ast.expr]]:
    """Return (name_value, {kwarg: node}) for an ``@observe(...)`` Call."""
    name_value: str | None = None
    kwargs: dict[str, ast.expr] = {}
    for kw in dec.keywords:
        if kw.arg is None:
            continue
        kwargs[kw.arg] = kw.value
        if kw.arg == "name" and isinstance(kw.value, ast.Constant):
            name_value = kw.value.value
    return name_value, kwargs


def _is_observe_call(dec: ast.expr) -> ast.Call | None:
    if not isinstance(dec, ast.Call):
        return None
    func = dec.func
    if isinstance(func, ast.Name) and func.id == "observe":
        return dec
    if isinstance(func, ast.Attribute) and func.attr == "observe":
        return dec
    return None


def _collect_observe_as_types() -> dict[str, str | None]:
    """Map every @observe(name=...) in scope to its as_type literal (or None)."""
    found: dict[str, str | None] = {}
    for root in _SCAN_DIRS:
        if not root.exists():
            continue
        for py_file in root.rglob("*.py"):
            if "/tests/" in str(py_file) or "/__pycache__/" in str(py_file):
                continue
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                for dec in node.decorator_list:
                    call = _is_observe_call(dec)
                    if call is None:
                        continue
                    name_value, kwargs = _decorator_name_and_kwargs(call)
                    if name_value is None:
                        continue
                    as_type_node = kwargs.get("as_type")
                    as_type_val = (
                        as_type_node.value if isinstance(as_type_node, ast.Constant) else None
                    )
                    found[name_value] = as_type_val
    return found


@pytest.fixture(scope="module")
def observe_as_types() -> dict[str, str | None]:
    return _collect_observe_as_types()


class TestAgentToolAndGuardTaxonomy:
    @pytest.mark.parametrize("observe_name,expected_type", _REQUIRED_AS_TYPE.items())
    def test_observe_has_expected_as_type(
        self,
        observe_as_types: dict[str, str | None],
        observe_name: str,
        expected_type: str,
    ) -> None:
        assert observe_name in observe_as_types, (
            f"@observe(name={observe_name!r}) not found under "
            f"telegram_bot/agents or src/runtime/graph/nodes — the taxonomy "
            f"contract expects it to exist (#2216). Did the span get renamed?"
        )
        actual = observe_as_types[observe_name]
        assert actual == expected_type, (
            f"@observe(name={observe_name!r}) must set as_type={expected_type!r} "
            f"so the Langfuse UI groups it under the {expected_type!r} taxonomy "
            f"(#2216); found as_type={actual!r}."
        )

    def test_all_required_names_present(self, observe_as_types: dict[str, str | None]) -> None:
        """Sanity: the scanner is not vacuous — it found the decorators."""
        missing = set(_REQUIRED_AS_TYPE) - set(observe_as_types)
        assert not missing, (
            "Taxonomy contract could not locate these @observe names "
            f"(scanner regression or renamed spans): {sorted(missing)}"
        )


# observe-name -> required as_type for actual agent-loop invocations in bot.py.
# These spans directly wrap ``create_agent`` SDK execution (ainvoke / astream /
# Command(resume)), so Langfuse v4 should group them under the ``agent``
# taxonomy (#2216).
_REQUIRED_AGENT_AS_TYPE: dict[str, str] = {
    "telegram-rag-agent-stream": "agent",
    "telegram-rag-agent-invoke": "agent",
    "telegram-hitl-callback": "agent",
}

# Parent/orchestration spans that may return before any agent SDK invocation
# (pre-agent guard, semantic cache hit, client direct pipeline) must stay as the
# default span type. Marking these as ``agent`` would make non-agent requests
# look like agent-loop traces in Langfuse (#2216).
_REQUIRED_DEFAULT_SPAN_TYPE: tuple[str, ...] = ("telegram-rag-supervisor",)


def _collect_bot_py_observe_as_types() -> dict[str, str | None]:
    """Map every @observe(name=...) in bot.py (functions/methods) to its as_type."""
    found: dict[str, str | None] = {}
    tree = ast.parse(BOT_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for dec in node.decorator_list:
            call = _is_observe_call(dec)
            if call is None:
                continue
            name_value, kwargs = _decorator_name_and_kwargs(call)
            if name_value is None:
                continue
            as_type_node = kwargs.get("as_type")
            found[name_value] = (
                as_type_node.value if isinstance(as_type_node, ast.Constant) else None
            )
    return found


@pytest.fixture(scope="module")
def bot_py_observe_as_types() -> dict[str, str | None]:
    return _collect_bot_py_observe_as_types()


class TestAgentEntrypointTaxonomy:
    """Only actual SDK agent-loop entry points are ``agent`` (#2216)."""

    @pytest.mark.parametrize("observe_name,expected_type", _REQUIRED_AGENT_AS_TYPE.items())
    def test_agent_entrypoint_has_agent_as_type(
        self,
        bot_py_observe_as_types: dict[str, str | None],
        observe_name: str,
        expected_type: str,
    ) -> None:
        assert observe_name in bot_py_observe_as_types, (
            f"@observe(name={observe_name!r}) not found in telegram_bot/bot.py — "
            f"the taxonomy contract expects this agent-loop entry point (#2216). "
            "Did the span get renamed?"
        )
        actual = bot_py_observe_as_types[observe_name]
        assert actual == expected_type, (
            f"@observe(name={observe_name!r}) must set as_type={expected_type!r} so "
            f"the Langfuse UI groups the agent invocation under the {expected_type!r} "
            f"taxonomy (#2216); found as_type={actual!r}."
        )

    @pytest.mark.parametrize("observe_name", _REQUIRED_DEFAULT_SPAN_TYPE)
    def test_orchestration_parent_stays_default_span(
        self,
        bot_py_observe_as_types: dict[str, str | None],
        observe_name: str,
    ) -> None:
        assert observe_name in bot_py_observe_as_types, (
            f"@observe(name={observe_name!r}) not found in telegram_bot/bot.py."
        )
        actual = bot_py_observe_as_types[observe_name]
        assert actual is None, (
            f"@observe(name={observe_name!r}) must stay at the default span type "
            "because it includes pre-agent cache/direct-pipeline return paths; "
            f"found as_type={actual!r}."
        )
