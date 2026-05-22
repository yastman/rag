"""Drift guard for #1265 Slice 1 PR-4 — _bot_streaming extract.

Issue #1265 published a 6-PR Slice 1 plan that extracts pure module-level
helpers out of ``telegram_bot/bot.py`` before any class-level decomposition.

This contract pins **PR-4** (streaming/draft helpers):

  - _new_draft_id          — 31-bit draft id generator for sendMessageDraft.
  - _stream_agent_to_draft — bridges agent.astream() → bot.send_message_draft.
  - _extract_stream_chunk_text — pulls human text out of LangChain chunk.

Mirrors PR-1..PR-3 contracts:

  1. ``telegram_bot/_bot_streaming.py`` exists and is import-clean
     (stdlib only — no aiogram / langgraph / fastapi / langchain).
  2. All three helpers are exposed at module top.
  3. ``_AGENT_DRAFT_INTERVAL`` is exported (callers in bot.py read it).
  4. ``_new_draft_id`` returns a positive 31-bit signed int across many
     calls (bot's draft_id contract).
  5. ``_extract_stream_chunk_text`` produces byte-for-byte identical
     output via the bot wrapper and the canonical module on a wide
     payload set (str text attr, str content, list-of-str, list-of-dict
     with "text", list-of-objects with .text attr, empty/missing).
  6. ``bot.py`` defines each helper at most once (the wrapper).
  7. ``bot.py`` line count is strictly below the 4863 baseline.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
NEW_MODULE = REPO_ROOT / "telegram_bot" / "_bot_streaming.py"
BOT_PY = REPO_ROOT / "telegram_bot" / "bot.py"

HELPERS: tuple[str, ...] = (
    "_new_draft_id",
    "_stream_agent_to_draft",
    "_extract_stream_chunk_text",
)

FORBIDDEN_MODULE_LEVEL_IMPORTS: tuple[str, ...] = (
    "aiogram",
    "langgraph",
    "fastapi",
    "langchain",
    "redis",
    "qdrant_client",
)

BOT_PY_LINE_COUNT_CEILING = 4863


# ---------------------------------------------------------------------------
# Module existence + import hygiene
# ---------------------------------------------------------------------------


def test_bot_streaming_module_exists() -> None:
    assert NEW_MODULE.exists(), (
        f"#1265 Slice 1 PR-4: expected {NEW_MODULE.relative_to(REPO_ROOT)} "
        "to own the extracted streaming helpers."
    )


def test_bot_streaming_module_imports_are_clean() -> None:
    tree = ast.parse(NEW_MODULE.read_text())
    bad: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in FORBIDDEN_MODULE_LEVEL_IMPORTS:
                    bad.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[0]
            if mod in FORBIDDEN_MODULE_LEVEL_IMPORTS:
                bad.append(node.module or "")
    assert not bad, (
        f"_bot_streaming.py module-level imports must avoid the bot stack; "
        f"found forbidden roots: {bad}"
    )


@pytest.mark.parametrize("helper", HELPERS)
def test_bot_streaming_helper_exposed(helper: str) -> None:
    """Each helper must be defined at module top-level."""
    tree = ast.parse(NEW_MODULE.read_text())
    names = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert helper in names, f"_bot_streaming.{helper} must be defined at module top."


def test_agent_draft_interval_constant_exposed() -> None:
    """``_AGENT_DRAFT_INTERVAL`` must move with the streaming helper."""
    from telegram_bot import _bot_streaming

    assert hasattr(_bot_streaming, "_AGENT_DRAFT_INTERVAL")
    assert isinstance(_bot_streaming._AGENT_DRAFT_INTERVAL, float)
    assert _bot_streaming._AGENT_DRAFT_INTERVAL > 0


# ---------------------------------------------------------------------------
# _new_draft_id contract
# ---------------------------------------------------------------------------


def test_bot_streaming_new_draft_id_returns_positive_31bit_int() -> None:
    """Generator must always produce a positive value within signed-int32."""
    from telegram_bot import _bot_streaming

    for _ in range(200):
        v = _bot_streaming._new_draft_id()
        assert isinstance(v, int)
        assert 1 <= v <= 2**31 - 1, f"draft id {v} outside [1, 2^31-1]"


def test_new_draft_id_wrapper_identity() -> None:
    """``bot._new_draft_id`` and ``_bot_streaming._new_draft_id`` produce
    same-shaped values — both within the documented draft-id range.
    """
    from telegram_bot import _bot_streaming, bot

    for _ in range(50):
        bv = bot._new_draft_id()
        cv = _bot_streaming._new_draft_id()
        assert 1 <= bv <= 2**31 - 1
        assert 1 <= cv <= 2**31 - 1


# ---------------------------------------------------------------------------
# _extract_stream_chunk_text byte-for-byte parity
# ---------------------------------------------------------------------------


PARITY_PAYLOADS: list[tuple[str, object]] = [
    ("text_attr_str", SimpleNamespace(text="hello", content="ignored")),
    ("text_attr_empty_falls_to_content", SimpleNamespace(text="", content="from_content")),
    ("content_str", SimpleNamespace(content="plain string")),
    ("content_list_of_str", SimpleNamespace(content=["a", "b", "c"])),
    (
        "content_list_of_dict_with_text",
        SimpleNamespace(content=[{"text": "x"}, {"text": "y"}, {"other": "skip"}]),
    ),
    (
        "content_list_of_obj_with_text_attr",
        SimpleNamespace(content=[SimpleNamespace(text="o1"), SimpleNamespace(text="o2")]),
    ),
    (
        "content_mixed_list",
        SimpleNamespace(content=["s1", {"text": "d1"}, SimpleNamespace(text="o1")]),
    ),
    ("content_empty_str", SimpleNamespace(content="")),
    ("content_empty_list", SimpleNamespace(content=[])),
    ("missing_both", SimpleNamespace()),
]


@pytest.mark.parametrize(
    ("label", "chunk"),
    PARITY_PAYLOADS,
    ids=[label for label, _ in PARITY_PAYLOADS],
)
def test_extract_stream_chunk_text_byte_for_byte_parity(label: str, chunk: object) -> None:
    from telegram_bot import _bot_streaming, bot

    bot_result = bot._extract_stream_chunk_text(chunk)
    new_result = _bot_streaming._extract_stream_chunk_text(chunk)
    assert bot_result == new_result, (
        f"#1265 PR-4 parity break for _extract_stream_chunk_text({label!r}): "
        f"bot={bot_result!r}, _bot_streaming={new_result!r}"
    )


# ---------------------------------------------------------------------------
# _stream_agent_to_draft — async runtime smoke
# ---------------------------------------------------------------------------


class _FakeBot:
    def __init__(self) -> None:
        self.draft_calls: list[dict] = []

    async def send_message_draft(self, **kwargs):
        self.draft_calls.append(kwargs)


class _FakeAgent:
    """Minimal async-iterable mock of ``langgraph.agent.astream``."""

    def __init__(self, events: list[tuple[str, object]]) -> None:
        self._events = events

    def astream(self, *_args, **_kwargs):
        events = self._events

        class _Stream:
            def __aiter__(self_inner):
                self_inner._iter = iter(events)
                return self_inner

            async def __anext__(self_inner):
                try:
                    return next(self_inner._iter)
                except StopIteration as exc:
                    raise StopAsyncIteration from exc

        return _Stream()


@pytest.mark.asyncio
async def test_stream_agent_to_draft_collects_and_finalizes() -> None:
    """The streaming helper must:

    - forward content-only chunks from the ``agent`` node,
    - skip non-``agent`` nodes,
    - skip tool-call chunks,
    - return the final ``values`` payload.
    """
    from telegram_bot import _bot_streaming

    msg_a = SimpleNamespace(content="Hello ", tool_calls=None)
    msg_b = SimpleNamespace(content="world", tool_calls=None)
    msg_tool = SimpleNamespace(content="ignored", tool_calls=[{"name": "x"}])
    msg_other_node = SimpleNamespace(content="from-other", tool_calls=None)
    final_state = {"messages": [msg_a, msg_b], "answer": "Hello world"}

    events = [
        ("messages", (msg_a, {"langgraph_node": "agent"})),
        ("messages", (msg_other_node, {"langgraph_node": "tools"})),
        ("messages", (msg_tool, {"langgraph_node": "agent"})),
        ("messages", (msg_b, {"langgraph_node": "agent"})),
        ("values", final_state),
    ]
    fake_bot = _FakeBot()
    agent = _FakeAgent(events)

    out = await _bot_streaming._stream_agent_to_draft(
        agent=agent,
        payload={},
        config={},
        bot=fake_bot,
        chat_id=42,
        thread_id=None,
    )
    assert out == final_state, "final state must be returned verbatim"
    # _AGENT_DRAFT_INTERVAL is 0.2s — first chunk lands immediately because
    # last_draft starts at 0.0 and time.monotonic() is much larger. The
    # second eligible chunk may or may not fire depending on timing; both
    # outcomes are acceptable, but at least one draft must have been sent.
    assert fake_bot.draft_calls, "expected at least one sendMessageDraft call"
    assert all(c["chat_id"] == 42 for c in fake_bot.draft_calls)
    assert all("message_thread_id" not in c for c in fake_bot.draft_calls)


# ---------------------------------------------------------------------------
# bot.py shape — no duplicate definition + line-count ratchet
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("helper", HELPERS)
def test_bot_py_defines_streaming_helper_at_most_once(helper: str) -> None:
    """``bot.py`` must keep at most one ``def <helper>(...)``."""
    src = BOT_PY.read_text()
    pattern = re.compile(rf"^(async\s+def|def)\s+{re.escape(helper)}\(", re.MULTILINE)
    matches = pattern.findall(src)
    assert len(matches) <= 1, (
        f"bot.py defines `{helper}` {len(matches)} times; expected at most 1 "
        "(the thin wrapper that delegates to _bot_streaming)."
    )


def test_bot_py_streaming_line_count_below_ratchet() -> None:
    line_count = sum(1 for _ in BOT_PY.read_text().splitlines())
    assert line_count < BOT_PY_LINE_COUNT_CEILING, (
        f"bot.py line count is {line_count}; #1265 Slice 1 PR-4 ratchet "
        f"requires < {BOT_PY_LINE_COUNT_CEILING}."
    )
