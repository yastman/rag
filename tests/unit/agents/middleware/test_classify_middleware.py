"""Behaviour parity tests for ``ClassifyMiddleware`` (Slice 2.5 / #2051).

Pin the routing the legacy ``classify_node`` provides today:

* CHITCHAT / OFF_TOPIC → emit canned response + ``jump_to=end``.
* All other types → annotate ``query_type`` and return without jumping.
* Empty messages → no-op (``None``).
* ``skip_canned_response=True`` → set ``query_type`` even on
  CHITCHAT/OFF_TOPIC but leave message emission to the caller.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from langchain.messages import AIMessage, HumanMessage

from telegram_bot.graph.middleware.classify import (
    ClassifyMiddleware,
    _ClassifyAwareState,
)


def _state(text: str = "") -> dict:
    if not text:
        return {"messages": []}
    return {"messages": [HumanMessage(content=text)]}


def _runtime() -> MagicMock:
    rt = MagicMock()
    rt.context = {}
    return rt


@pytest.fixture(autouse=True)
def _stub_observability(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = MagicMock()
    fake.update_current_span = MagicMock()
    monkeypatch.setattr("telegram_bot.graph.middleware.classify.get_client", lambda: fake)


@pytest.fixture
def middleware() -> ClassifyMiddleware:
    return ClassifyMiddleware()


def test_returns_none_for_empty_messages(middleware: ClassifyMiddleware) -> None:
    assert middleware.before_agent(_state(""), _runtime()) is None


def test_chitchat_short_circuits_with_canned_response(
    middleware: ClassifyMiddleware,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "telegram_bot.graph.middleware.classify.classify_query", lambda _q: "CHITCHAT"
    )
    monkeypatch.setattr(
        "telegram_bot.graph.middleware.classify._get_chitchat_response",
        lambda _q: "Привет! Чем могу помочь?",
    )

    result = middleware.before_agent(_state("привет"), _runtime())

    assert result is not None
    assert result["jump_to"] == "end"
    assert result["query_type"] == "CHITCHAT"
    assert result["response"] == "Привет! Чем могу помочь?"
    [msg] = result["messages"]
    assert isinstance(msg, AIMessage)
    assert msg.content == "Привет! Чем могу помочь?"


def test_off_topic_short_circuits_with_canned_response(
    middleware: ClassifyMiddleware,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "telegram_bot.graph.middleware.classify.classify_query", lambda _q: "OFF_TOPIC"
    )
    # Neutralise random.choice so the test is deterministic.
    monkeypatch.setattr(
        "telegram_bot.graph.nodes.classify.OFF_TOPIC_RESPONSES",
        ["Я отвечаю только по недвижимости."],
    )

    result = middleware.before_agent(_state("сколько весит марс"), _runtime())

    assert result is not None
    assert result["jump_to"] == "end"
    assert result["query_type"] == "OFF_TOPIC"
    [msg] = result["messages"]
    assert isinstance(msg, AIMessage)


@pytest.mark.parametrize("classified_type", ["FAQ", "ENTITY", "STRUCTURED", "GENERAL"])
def test_cacheable_types_pass_through(
    middleware: ClassifyMiddleware,
    monkeypatch: pytest.MonkeyPatch,
    classified_type: str,
) -> None:
    monkeypatch.setattr(
        "telegram_bot.graph.middleware.classify.classify_query", lambda _q: classified_type
    )

    result = middleware.before_agent(_state("сколько стоит ВНЖ"), _runtime())

    assert result is not None
    assert "jump_to" not in result
    assert result["query_type"] == classified_type
    # No canned messages on the cacheable paths.
    assert "messages" not in result


def test_skip_canned_response_flag_keeps_query_type_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "telegram_bot.graph.middleware.classify.classify_query", lambda _q: "CHITCHAT"
    )
    middleware = ClassifyMiddleware(skip_canned_response=True)

    result = middleware.before_agent(_state("привет"), _runtime())

    assert result is not None
    assert "jump_to" not in result
    assert result["query_type"] == "CHITCHAT"
    assert "messages" not in result


def test_state_schema_carries_query_type() -> None:
    annotations = _ClassifyAwareState.__annotations__
    assert "query_type" in annotations
