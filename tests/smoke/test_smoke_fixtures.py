# tests/smoke/test_smoke_fixtures.py
"""Regression locks for tests/smoke/conftest.py contracts (#1766).

These run without live services: they verify the fixture contract itself
and the SDK-native message access pattern, so the smoke tier does not
silently regress to fixture-not-found errors or HumanMessage subscript bugs.
"""

import pytest


@pytest.mark.smoke
def test_redis_url_fixture_is_provided(redis_url: str) -> None:
    """Smoke conftest must expose a `redis_url` fixture.

    Regression for #1766: `require_live_services` and `cache_service`
    consume `redis_url` via `request.getfixturevalue("redis_url")`. Before
    the fix, no `redis_url` fixture existed anywhere in the test tree, so
    smoke runs errored at fixture resolution.
    """
    assert isinstance(redis_url, str)
    assert redis_url.startswith(("redis://", "rediss://"))


@pytest.mark.smoke
def test_redis_url_fixture_injects_password(monkeypatch: pytest.MonkeyPatch) -> None:
    """`redis_url` mirrors `_build_redis_url`: injects REDIS_PASSWORD if not embedded."""
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    monkeypatch.setenv("REDIS_PASSWORD", "topsecret")

    # Reimport / recompute by calling the fixture function directly.
    from tests.smoke.conftest import redis_url as redis_url_fixture

    # Module-scoped pytest fixtures are wrapped; reach the underlying function.
    func = getattr(redis_url_fixture, "__wrapped__", redis_url_fixture)
    url = func() if callable(func) else None
    assert url == "redis://:topsecret@localhost:6379", url


@pytest.mark.smoke
def test_redis_url_fixture_preserves_explicit_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """`redis_url` does not double-inject credentials when URL already has @."""
    monkeypatch.setenv("REDIS_URL", "redis://:already@host:6379")
    monkeypatch.setenv("REDIS_PASSWORD", "ignored")

    from tests.smoke.conftest import redis_url as redis_url_fixture

    func = getattr(redis_url_fixture, "__wrapped__", redis_url_fixture)
    url = func() if callable(func) else None
    assert url == "redis://:already@host:6379", url


@pytest.mark.smoke
def test_initial_state_message_uses_dot_notation() -> None:
    """`state["messages"][0]` is a HumanMessage; access content via attribute (#1766).

    LangChain SDK contract (per langgraph graph-api docs): when state uses
    `add_messages`, messages are deserialized to BaseMessage objects and
    must be read with dot notation, not dict subscript.
    """
    from langchain_core.messages import HumanMessage

    from telegram_bot.graph.state import make_initial_state

    state = make_initial_state(user_id=1, session_id="s", query="hello")
    assert isinstance(state["messages"][0], HumanMessage)
    assert state["messages"][0].content == "hello"

    # Subscript must remain unsupported — protect against accidental
    # reintroduction of dict-style access in tests.
    with pytest.raises(TypeError):
        _ = state["messages"][0]["content"]  # type: ignore[index]
