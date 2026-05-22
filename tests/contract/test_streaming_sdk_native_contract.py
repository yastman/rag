"""Contract test: bot streaming path stays on the LangGraph native API.

Issue #1538 audited SDK-native vs custom code. The live finding (after the
2026-05 refresh) is that ``_stream_agent_to_draft`` already streams via
``agent.astream(..., stream_mode=["messages", "values"])`` and unpacks the
``(message, metadata)`` 2-tuple that ``MessagesStreamPart`` documents. No
custom polling / `DraftStreamer` abstraction lives between the agent and
the Telegram ``send_message_draft`` call.

This contract pins that state. If a future refactor:

- removes the call to ``agent.astream(...)`` from the streaming function,
- drops ``"messages"`` from ``stream_mode``, or
- reintroduces a class named ``DraftStreamer`` (the name from the audit
  body),

the contract fails with an actionable message pointing at #1538.

Context7-verified (``/langchain-ai/langgraph``,
``MessagesStreamPart``): the ``messages`` stream mode emits a 2-tuple
``(message, metadata)`` where ``message`` is a ``BaseMessage``
(typically ``AIMessageChunk``) and ``metadata`` carries
``langgraph_node`` / ``langgraph_step`` / ``langgraph_triggers``.
Content was rephrased for licensing compliance.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BOT_PY = REPO_ROOT / "telegram_bot" / "bot.py"


def _function_node(tree: ast.AST, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _calls_in(node: ast.AST) -> list[ast.Call]:
    return [n for n in ast.walk(node) if isinstance(n, ast.Call)]


def test_stream_agent_to_draft_uses_native_astream_with_messages_mode() -> None:
    """`_stream_agent_to_draft` must call `agent.astream(..., stream_mode=[...])`
    with `"messages"` included in the mode list.
    """
    assert BOT_PY.exists(), "telegram_bot/bot.py not found"
    tree = ast.parse(BOT_PY.read_text(), filename=str(BOT_PY))
    fn = _function_node(tree, "_stream_agent_to_draft")
    assert fn is not None, (
        "Streaming entry point `_stream_agent_to_draft` is missing from "
        "telegram_bot/bot.py. If it was renamed, update this contract "
        "(#1538) so the SDK pin still applies."
    )

    astream_calls = [
        call
        for call in _calls_in(fn)
        if isinstance(call.func, ast.Attribute) and call.func.attr == "astream"
    ]
    assert astream_calls, (
        "`_stream_agent_to_draft` must call `<agent>.astream(...)` (LangGraph "
        "native streaming). Issue #1538 prohibits replacing this with a "
        "custom polling helper or a `DraftStreamer`-style abstraction."
    )

    found_messages_mode = False
    for call in astream_calls:
        for kw in call.keywords:
            if kw.arg != "stream_mode":
                continue
            value = kw.value
            # Accept stream_mode=["messages", ...] or stream_mode="messages"
            if isinstance(value, ast.List):
                for elt in value.elts:
                    if isinstance(elt, ast.Constant) and elt.value == "messages":
                        found_messages_mode = True
            elif isinstance(value, ast.Constant) and value.value == "messages":
                found_messages_mode = True
    assert found_messages_mode, (
        "`_stream_agent_to_draft` calls `agent.astream(...)` but does not pass "
        '`stream_mode` containing "messages". Per LangGraph SDK '
        "(`/langchain-ai/langgraph` `MessagesStreamPart`), this mode is the "
        "canonical way to stream `(AIMessageChunk, metadata)` pairs to a "
        "draft surface. Restore it (#1538)."
    )


def test_no_draft_streamer_class_reintroduced() -> None:
    """The audit (#1538) called out a `DraftStreamer` polling abstraction
    that was removed by #1671. Reintroducing a class with that name is a
    regression — the current path goes through `agent.astream(...)`
    directly, no extra layer.
    """
    candidates: list[Path] = []
    for parent in (REPO_ROOT / "telegram_bot", REPO_ROOT / "src"):
        if not parent.exists():
            continue
        for py in parent.rglob("*.py"):
            if "/.venv/" in str(py):
                continue
            try:
                tree = ast.parse(py.read_text(), filename=str(py))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == "DraftStreamer":
                    candidates.append(py.relative_to(REPO_ROOT))
                    break
    assert candidates == [], (
        f"`DraftStreamer` class reintroduced in {candidates}. Issue "
        f"#1538 requires the streaming path to remain SDK-only via "
        f"`agent.astream(stream_mode=[...])`; do not add a custom "
        f"polling abstraction (#1671 removed the original)."
    )
