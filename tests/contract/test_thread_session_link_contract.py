"""LangGraph thread_id <-> Langfuse session_id linkage contract (#2224).

Operational hygiene: an operator who finds a Langfuse trace must be able to
recover the LangGraph checkpointer thread for that conversation.

Scope: the **supervisor (text) agent** path — the ``configurable`` dicts whose
``thread_id`` is built by ``_supervisor_thread_id(...)``. The voice path and the
HITL ``Command(resume=...)`` path use their own thread/session handling and are
out of scope here (tracked as follow-ups on #2224).

Two things are locked:

1. **Co-location** — every supervisor ``configurable`` dict carrying a
   ``_supervisor_thread_id`` thread_id must also carry ``session_id`` so the
   LangGraph<->Langfuse mapping is always recoverable.
2. **Trace linkage** — ``telegram_bot/bot.py`` records the checkpointer
   ``thread_id`` on the Langfuse trace as ``langgraph_thread_id`` metadata (via
   ``update_current_trace``), so the correlation is visible from the trace.

Design note (see ``docs/BOT_INTERNAL_STRUCTURE.md``): ``thread_id`` is
**intentionally not unified** with ``session_id``. ``make_session_id`` is
date-rotating (``chat-<hash>-<YYYYMMDD>``) while the checkpointer thread
(``_supervisor_thread_id`` -> ``tg_<chat_id>``) must persist across days;
unifying them would reset conversation memory daily. They are linked via
metadata, not made equal.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BOT_PY = REPO_ROOT / "telegram_bot" / "bot.py"


def _dict_string_keys(node: ast.Dict) -> set[str]:
    return {k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}


def _is_supervisor_thread_id_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_supervisor_thread_id"
    )


def _supervisor_configurable_keysets(tree: ast.AST) -> list[set[str]]:
    """Key-sets of every ``"configurable": {...}`` whose thread_id is built by
    ``_supervisor_thread_id(...)`` (i.e. the supervisor/text-agent path)."""
    out: list[set[str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values, strict=False):
            if not (
                isinstance(key, ast.Constant)
                and key.value == "configurable"
                and isinstance(value, ast.Dict)
            ):
                continue
            tid_value = None
            for k2, v2 in zip(value.keys, value.values, strict=False):
                if isinstance(k2, ast.Constant) and k2.value == "thread_id":
                    tid_value = v2
            if tid_value is not None and _is_supervisor_thread_id_call(tid_value):
                out.append(_dict_string_keys(value))
    return out


def _emits_thread_id_to_trace(source: str) -> bool:
    return "update_current_trace" in source and "langgraph_thread_id" in source


class TestSupervisorThreadSessionColocation:
    def test_bot_py_exists(self) -> None:
        assert BOT_PY.exists(), f"missing: {BOT_PY}"

    def test_supervisor_configurable_has_thread_and_session(self) -> None:
        tree = ast.parse(BOT_PY.read_text(encoding="utf-8"))
        keysets = _supervisor_configurable_keysets(tree)
        assert keysets, (
            "expected at least one supervisor 'configurable' using _supervisor_thread_id"
        )
        offenders = [keys for keys in keysets if "session_id" not in keys]
        assert not offenders, (
            "Every supervisor 'configurable' (thread_id via _supervisor_thread_id) "
            "must also carry session_id so the LangGraph<->Langfuse mapping stays "
            f"recoverable (#2224). Offending key-sets: {offenders}"
        )


class TestTraceLinkage:
    def test_bot_py_records_langgraph_thread_id_on_trace(self) -> None:
        source = BOT_PY.read_text(encoding="utf-8")
        assert _emits_thread_id_to_trace(source), (
            "telegram_bot/bot.py must record the checkpointer thread_id on the "
            "Langfuse trace as langgraph_thread_id metadata via "
            "update_current_trace(...) so operators can correlate a trace to the "
            "LangGraph conversation state (#2224)."
        )


class TestDetectorSelfChecks:
    _COLOCATED = (
        "config = {'configurable': {'thread_id': _supervisor_thread_id(c), "
        "'session_id': sid, 'role': r}}\n"
    )
    _MISSING_SESSION = (
        "config = {'configurable': {'thread_id': _supervisor_thread_id(c), 'role': r}}\n"
    )
    _VOICE_PATH = "cfg = {'configurable': {'thread_id': str(uid), 'checkpoint_ns': ns}}\n"
    _BARE_THREAD = "draft_state = {'thread_id': forum_thread_id}\n"

    def test_supervisor_colocated_passes(self) -> None:
        keysets = _supervisor_configurable_keysets(ast.parse(self._COLOCATED))
        assert keysets == [{"thread_id", "session_id", "role"}]

    def test_missing_session_is_detectable(self) -> None:
        keysets = _supervisor_configurable_keysets(ast.parse(self._MISSING_SESSION))
        assert keysets == [{"thread_id", "role"}]
        assert "session_id" not in keysets[0]

    def test_voice_path_excluded(self) -> None:
        # thread_id is not built by _supervisor_thread_id -> out of scope
        assert _supervisor_configurable_keysets(ast.parse(self._VOICE_PATH)) == []

    def test_bare_thread_dict_excluded(self) -> None:
        assert _supervisor_configurable_keysets(ast.parse(self._BARE_THREAD)) == []

    def test_trace_linkage_detector(self) -> None:
        assert _emits_thread_id_to_trace(
            "lf.update_current_trace(metadata={'langgraph_thread_id': tid})"
        )
        assert not _emits_thread_id_to_trace("lf.update_current_span(metadata={'x': 1})")
