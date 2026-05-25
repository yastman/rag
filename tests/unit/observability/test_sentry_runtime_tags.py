"""Unit tests for Sentry runtime tags + trace context (#2061).

Covers the three new helpers in ``src.observability_sentry``:

- ``hash_id`` — stable, short, opaque hash for Telegram chat/user IDs
- ``set_runtime_tags`` — set static service/component/pipeline tags on the
  active Sentry scope
- ``runtime_scope`` — context manager that pushes PII-safe runtime tags
  (hashed IDs) and Langfuse trace context, and lets them fall off the
  scope on exit

The tests patch ``sentry_sdk`` indirection seams on
``src.observability_sentry`` so we never poke a live SDK transport.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def helper(monkeypatch):
    for var in (
        "SENTRY_DSN",
        "SENTRY_ENVIRONMENT",
        "SENTRY_RELEASE",
        "SENTRY_TRACES_SAMPLE_RATE",
        "SENTRY_DEBUG",
    ):
        monkeypatch.delenv(var, raising=False)
    sys.modules.pop("src.observability_sentry", None)
    import src.observability_sentry as m

    yield m
    sys.modules.pop("src.observability_sentry", None)


# ---------------------------------------------------------------------------
# hash_id
# ---------------------------------------------------------------------------


def test_hash_id_is_stable_for_same_input(helper):
    assert helper.hash_id(123456789) == helper.hash_id(123456789)
    assert helper.hash_id("user-abc") == helper.hash_id("user-abc")


def test_hash_id_differs_for_different_inputs(helper):
    assert helper.hash_id(1) != helper.hash_id(2)
    assert helper.hash_id("a") != helper.hash_id("b")


def test_hash_id_normalizes_int_and_str_to_same_value(helper):
    """``hash_id(123)`` and ``hash_id("123")`` must be equal so a chat_id
    hashed at handler entry equals the same id later in the pipeline.
    """
    assert helper.hash_id(123456789) == helper.hash_id("123456789")


def test_hash_id_returns_short_hex(helper):
    h = helper.hash_id(987654321)
    assert isinstance(h, str)
    assert len(h) == 16
    assert all(c in "0123456789abcdef" for c in h)


def test_hash_id_does_not_leak_raw_value(helper):
    raw = 123456789
    h = helper.hash_id(raw)
    assert str(raw) not in h


# ---------------------------------------------------------------------------
# set_runtime_tags
# ---------------------------------------------------------------------------


def test_set_runtime_tags_sets_service_tag(helper):
    with patch.object(helper, "_sentry_set_tag") as set_tag:
        helper.set_runtime_tags(service="telegram-bot")
    set_tag.assert_any_call("service", "telegram-bot")


def test_set_runtime_tags_default_service(helper):
    with patch.object(helper, "_sentry_set_tag") as set_tag:
        helper.set_runtime_tags()
    set_tag.assert_any_call("service", "telegram-bot")


def test_set_runtime_tags_omits_none_optional_fields(helper):
    """When optional fields are None, they must not be emitted as tags."""
    with patch.object(helper, "_sentry_set_tag") as set_tag:
        helper.set_runtime_tags(service="rag-api")
    keys = [call.args[0] for call in set_tag.call_args_list]
    assert "component" not in keys
    assert "pipeline_mode" not in keys
    assert "route" not in keys


def test_set_runtime_tags_emits_explicit_fields(helper):
    with patch.object(helper, "_sentry_set_tag") as set_tag:
        helper.set_runtime_tags(
            service="telegram-bot",
            component="rag_pipeline",
            pipeline_mode="text",
            route="/query",
        )
    keys = {call.args[0]: call.args[1] for call in set_tag.call_args_list}
    assert keys["service"] == "telegram-bot"
    assert keys["component"] == "rag_pipeline"
    assert keys["pipeline_mode"] == "text"
    assert keys["route"] == "/query"


def test_set_runtime_tags_supports_extra_tags(helper):
    with patch.object(helper, "_sentry_set_tag") as set_tag:
        helper.set_runtime_tags(extra_tags={"locale": "uk", "tenant": "demo"})
    keys = {call.args[0]: call.args[1] for call in set_tag.call_args_list}
    assert keys["locale"] == "uk"
    assert keys["tenant"] == "demo"


# ---------------------------------------------------------------------------
# runtime_scope
# ---------------------------------------------------------------------------


def _make_scope_mock():
    """Returns (scope_mock, context_manager_mock)."""
    scope = MagicMock()
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=scope)
    cm.__exit__ = MagicMock(return_value=False)
    return scope, cm


def test_runtime_scope_hashes_chat_id(helper):
    scope, cm = _make_scope_mock()
    expected_hash = helper.hash_id(99887766)
    with patch.object(helper, "_sentry_new_scope", return_value=cm):
        with helper.runtime_scope(chat_id=99887766):
            pass
    keys = {call.args[0]: call.args[1] for call in scope.set_tag.call_args_list}
    assert keys["chat_id_hash"] == expected_hash


def test_runtime_scope_hashes_telegram_user_id(helper):
    scope, cm = _make_scope_mock()
    expected_hash = helper.hash_id(11223344)
    with patch.object(helper, "_sentry_new_scope", return_value=cm):
        with helper.runtime_scope(telegram_user_id=11223344):
            pass
    keys = {call.args[0]: call.args[1] for call in scope.set_tag.call_args_list}
    assert keys["telegram_user_id_hash"] == expected_hash


def test_runtime_scope_does_not_emit_raw_ids(helper):
    """No raw chat_id / telegram_user_id ever reaches the scope."""
    scope, cm = _make_scope_mock()
    with patch.object(helper, "_sentry_new_scope", return_value=cm):
        with helper.runtime_scope(chat_id=99887766, telegram_user_id=11223344):
            pass

    # Aggregate every value that crossed scope.* calls
    for call in scope.set_tag.call_args_list + scope.set_context.call_args_list:
        for arg in (*call.args, *call.kwargs.values()):
            assert "99887766" not in str(arg)
            assert "11223344" not in str(arg)


def test_runtime_scope_attaches_langfuse_trace_id_to_context(helper):
    scope, cm = _make_scope_mock()
    with patch.object(helper, "_sentry_new_scope", return_value=cm):
        with helper.runtime_scope(langfuse_trace_id="lf-trace-abc"):
            pass

    tag_keys = {call.args[0]: call.args[1] for call in scope.set_tag.call_args_list}
    assert tag_keys["langfuse_trace_id"] == "lf-trace-abc"

    ctx_calls = {call.args[0]: call.args[1] for call in scope.set_context.call_args_list}
    assert "trace" in ctx_calls
    assert ctx_calls["trace"]["langfuse_trace_id"] == "lf-trace-abc"


def test_runtime_scope_attaches_trace_id_when_no_langfuse(helper):
    scope, cm = _make_scope_mock()
    with patch.object(helper, "_sentry_new_scope", return_value=cm):
        with helper.runtime_scope(trace_id="otel-trace-xyz"):
            pass
    tag_keys = {call.args[0]: call.args[1] for call in scope.set_tag.call_args_list}
    assert tag_keys["trace_id"] == "otel-trace-xyz"
    ctx_calls = {call.args[0]: call.args[1] for call in scope.set_context.call_args_list}
    assert ctx_calls["trace"]["trace_id"] == "otel-trace-xyz"


def test_runtime_scope_skips_none_fields(helper):
    """None-valued args must not produce any tag/context calls."""
    scope, cm = _make_scope_mock()
    with patch.object(helper, "_sentry_new_scope", return_value=cm):
        with helper.runtime_scope():
            pass
    scope.set_tag.assert_not_called()
    scope.set_context.assert_not_called()


def test_runtime_scope_supports_route_and_pipeline_mode(helper):
    scope, cm = _make_scope_mock()
    with patch.object(helper, "_sentry_new_scope", return_value=cm):
        with helper.runtime_scope(route="/voice", pipeline_mode="voice"):
            pass
    keys = {call.args[0]: call.args[1] for call in scope.set_tag.call_args_list}
    assert keys["route"] == "/voice"
    assert keys["pipeline_mode"] == "voice"


def test_runtime_scope_supports_extra_tags(helper):
    scope, cm = _make_scope_mock()
    with patch.object(helper, "_sentry_new_scope", return_value=cm):
        with helper.runtime_scope(extra_tags={"locale": "uk"}):
            pass
    keys = {call.args[0]: call.args[1] for call in scope.set_tag.call_args_list}
    assert keys["locale"] == "uk"


def test_runtime_scope_yields_scope_handle(helper):
    """Caller can mutate the underlying scope inside the with-block."""
    scope, cm = _make_scope_mock()
    with patch.object(helper, "_sentry_new_scope", return_value=cm):
        with helper.runtime_scope() as s:
            assert s is scope
