"""Recovery for partial handoff setup and close failures (#3488).

Fault-injection tables over the real handlers with a FakeRedis-backed
``HandoffState``. Test doubles sit only at the Telegram/forum boundary
(``ForumBridge`` collaborators, aiogram Bot, FSM storage) plus deliberate
fault injection into ``HandoffState.set`` for the persist row.

Guarantees pinned here (#3488):

* a notification failure after a successful close never leaves the client
  in active human mode (FSM cleanup is independent of notifications);
* an error after topic creation leaves no silent orphan — the topic is
  compensated (closed) and the client sees truthful failure copy, never a
  false success;
* persistence failure and compensation failure have separate outcomes;
* a repeated close/setup is safe for an already-completed session and for
  a new session, cooperating with the #3487 guarded delete.
"""

from __future__ import annotations

import contextlib
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.handoff_state import HandoffData, HandoffState
from telegram_bot.handlers import bot_handoff
from telegram_bot.handlers.handoff import HandoffStates


# Truthful failure copy marker (#3239): "обращение не было отправлено".
_FAILURE_COPY_MARKER = "не был"


def _message() -> MagicMock:
    message = MagicMock()
    message.answer = AsyncMock()
    message.edit_text = AsyncMock()
    return message


def _fsm() -> MagicMock:
    fsm = MagicMock()
    fsm.set_state = AsyncMock()
    return fsm


def _bridge(*, topic_id: int = 111) -> MagicMock:
    """Forum boundary double: all Telegram calls mocked, nothing else."""
    bridge = MagicMock()
    bridge.create_topic = AsyncMock(return_value=topic_id)
    bridge.post_context_pack = AsyncMock()
    bridge.send_to_topic = AsyncMock(return_value=True)
    bridge.close_topic = AsyncMock()
    return bridge


def _bot(bridge: MagicMock, handoff_state: HandoffState | None) -> MagicMock:
    """Partially constructed PropertyBot with real handoff state."""
    from telegram_bot.bot import PropertyBot

    bot = PropertyBot.__new__(PropertyBot)
    bot.config = SimpleNamespace(
        handoff_summary_min_messages=3,
        business_hours_start=9,
        business_hours_end=18,
        business_hours_tz="Europe/Sofia",
    )
    bot._forum_bridge = bridge
    bot._handoff_state = handoff_state
    bot._llm = None
    cache = MagicMock()
    cache.redis = None
    bot._cache = cache
    bot.bot = AsyncMock()
    bot.bot.id = 100
    bot.dp = MagicMock()
    bot.dp.storage = AsyncMock()
    return bot


async def _run_setup(bot: MagicMock, message: MagicMock, fsm: MagicMock) -> None:
    await bot_handoff._complete_handoff(
        bot,
        user_id=999,
        username="u",
        display_name="User",
        locale="ru",
        qualification={"goal": "consult"},
        message=message,
        state=fsm,
    )


async def _no_leak(coro: object, *, scenario: str) -> None:
    """Await a handler call; a leaked exception is the defect itself (#3488)."""
    try:
        await coro  # type: ignore[misc]
    except Exception as exc:
        pytest.fail(f"{scenario}: handler leaked exception {exc!r}")


def _failure_copy_shown(message: MagicMock) -> bool:
    return any(
        _FAILURE_COPY_MARKER in (call.args[0] if call.args else "")
        for call in message.edit_text.await_args_list
    )


def _recovery_error_logged(caplog: pytest.LogCaptureFixture) -> bool:
    return any(
        record.levelno >= logging.ERROR and "#3488" in record.getMessage()
        for record in caplog.records
    )


# --- setup fault table (_complete_handoff) ------------------------------------

_SETUP_FAULTS = (
    # fault_point, failure_copy, compensation_close, persisted, fsm_active, error_logged
    pytest.param(
        "create",
        {
            "failure_copy": True,
            "compensation_close": False,
            "persisted": False,
            "fsm_active": False,
            "error_logged": False,
        },
        id="setup_fault_create_topic_fails",
    ),
    pytest.param(
        "context_post",
        {
            "failure_copy": True,
            "compensation_close": True,
            "persisted": False,
            "fsm_active": False,
            "error_logged": True,
        },
        id="setup_fault_context_post_fails",
    ),
    pytest.param(
        "persist",
        {
            "failure_copy": True,
            "compensation_close": True,
            "persisted": False,
            "fsm_active": False,
            "error_logged": True,
        },
        id="setup_fault_persist_fails",
    ),
    pytest.param(
        "notify",
        {
            "failure_copy": False,
            "compensation_close": False,
            "persisted": True,
            "fsm_active": True,
            "error_logged": True,
        },
        id="setup_fault_completion_notice_fails",
    ),
)


@pytest.mark.asyncio
@pytest.mark.parametrize(("fault_point", "expected"), _SETUP_FAULTS)
async def test_complete_handoff_setup_fault_table(
    mock_redis: object,
    caplog: pytest.LogCaptureFixture,
    fault_point: str,
    expected: dict[str, object],
) -> None:
    """Tabular fault injection for handoff setup (#3488).

    create/context_post/persist/notify faults: no silent orphan topic, no
    false success for the client, and local completion never depends on the
    optional completion notice.
    """
    caplog.set_level(logging.ERROR, logger="telegram_bot.handlers.bot_handoff")
    state = HandoffState(mock_redis, ttl_hours=24)  # type: ignore[arg-type]
    bridge = _bridge(topic_id=111)
    bot = _bot(bridge, state)
    message = _message()
    fsm = _fsm()

    with contextlib.ExitStack() as faults:
        if fault_point == "create":
            bridge.create_topic.side_effect = RuntimeError("forum down")
        elif fault_point == "context_post":
            bridge.post_context_pack.side_effect = RuntimeError("context post down")
        elif fault_point == "persist":
            faults.enter_context(
                patch.object(HandoffState, "set", side_effect=RuntimeError("redis down"))
            )
        elif fault_point == "notify":
            faults.enter_context(
                patch("telegram_bot.handlers.bot_handoff.is_business_hours", return_value=False)
            )
            message.answer.side_effect = RuntimeError("telegram down")
        await _no_leak(
            _run_setup(bot, message, fsm),
            scenario=f"setup fault {fault_point}",
        )

    assert _failure_copy_shown(message) is expected["failure_copy"], (
        f"setup fault {fault_point}: failure copy mismatch"
    )
    if expected["compensation_close"]:
        bridge.close_topic.assert_awaited_once_with(topic_id=111)
    else:
        bridge.close_topic.assert_not_awaited()

    stored = await state.get_by_client(999)
    assert (stored is not None) is expected["persisted"], (
        f"setup fault {fault_point}: unexpected persistence outcome"
    )
    if expected["persisted"]:
        assert stored is not None and stored.topic_id == 111

    if expected["fsm_active"]:
        fsm.set_state.assert_awaited_once_with(HandoffStates.active)
    else:
        fsm.set_state.assert_not_awaited()

    assert _recovery_error_logged(caplog) is expected["error_logged"], (
        f"setup fault {fault_point}: recovery error observability mismatch"
    )


@pytest.mark.asyncio
async def test_setup_compensation_failure_is_observable(
    mock_redis: object, caplog: pytest.LogCaptureFixture
) -> None:
    """Context post AND compensation close both fail — still no false success (#3488).

    Distinct outcome from a successful compensation: the orphan topic cannot
    be closed, so the failure must be loudly logged for manual recovery while
    the client still sees truthful failure copy.
    """
    caplog.set_level(logging.ERROR, logger="telegram_bot.handlers.bot_handoff")
    state = HandoffState(mock_redis, ttl_hours=24)  # type: ignore[arg-type]
    bridge = _bridge(topic_id=111)
    bridge.post_context_pack.side_effect = RuntimeError("context post down")
    bridge.close_topic.side_effect = RuntimeError("close down")
    bot = _bot(bridge, state)
    message = _message()
    fsm = _fsm()

    await _no_leak(_run_setup(bot, message, fsm), scenario="compensation failure")

    assert _failure_copy_shown(message), "client was not told the handoff failed"
    assert _recovery_error_logged(caplog), "compensation failure was not observable"
    assert await state.get_by_client(999) is None
    fsm.set_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_setup_retry_after_compensation_starts_new_session(mock_redis: object) -> None:
    """A new setup after a compensated failure is safe for a new session (#3488)."""
    state = HandoffState(mock_redis, ttl_hours=24)  # type: ignore[arg-type]
    bridge = _bridge(topic_id=111)
    bridge.post_context_pack.side_effect = RuntimeError("context post down")
    bot = _bot(bridge, state)
    message = _message()
    fsm = _fsm()

    await _no_leak(_run_setup(bot, message, fsm), scenario="first setup attempt")
    bridge.close_topic.assert_awaited_once_with(topic_id=111)
    assert await state.get_by_client(999) is None

    # Retry with a healthy forum: a fresh topic replaces the compensated one.
    # is_business_hours is patched because the real zoneinfo database is not
    # available on Windows (tzdata is not a dependency); the notice path is
    # covered by the notify fault row.
    bridge.post_context_pack.side_effect = None
    bridge.create_topic = AsyncMock(return_value=222)
    with patch("telegram_bot.handlers.bot_handoff.is_business_hours", return_value=True):
        await _no_leak(_run_setup(bot, message, fsm), scenario="setup retry")

    bridge.create_topic.assert_awaited_once()
    stored = await state.get_by_client(999)
    assert stored is not None and stored.topic_id == 222
    fsm.set_state.assert_awaited_once_with(HandoffStates.active)
    assert bridge.close_topic.await_count == 1, "retry must not close the new topic"


@pytest.mark.asyncio
async def test_setup_for_already_completed_session_reuses_topic(mock_redis: object) -> None:
    """A repeated setup with a live handoff reuses it — no duplicate topic (#3488)."""
    state = HandoffState(mock_redis, ttl_hours=24)  # type: ignore[arg-type]
    await state.set(HandoffData(client_id=999, topic_id=42, mode="human_waiting"))
    bridge = _bridge()
    bot = _bot(bridge, state)
    message = _message()
    fsm = _fsm()

    await _no_leak(_run_setup(bot, message, fsm), scenario="repeat setup")

    bridge.create_topic.assert_not_awaited()
    bridge.close_topic.assert_not_awaited()
    fsm.set_state.assert_awaited_once_with(HandoffStates.active)
    stored = await state.get_by_client(999)
    assert stored is not None and stored.topic_id == 42


# --- close fault table (_close_handoff) ----------------------------------------

_CLOSE_FAULTS = (
    pytest.param("none", {"error_logged": False}, id="close_no_fault_baseline"),
    pytest.param("close", {"error_logged": True}, id="close_fault_topic_close_fails"),
    pytest.param("notify", {"error_logged": True}, id="close_fault_client_notify_fails"),
    pytest.param("cleanup", {"error_logged": True}, id="close_fault_fsm_cleanup_fails"),
)


@pytest.mark.asyncio
@pytest.mark.parametrize(("fault_point", "expected"), _CLOSE_FAULTS)
async def test_close_handoff_fault_table(
    mock_redis: object,
    caplog: pytest.LogCaptureFixture,
    fault_point: str,
    expected: dict[str, object],
) -> None:
    """Tabular fault injection for handoff close (#3488).

    In every fault row the guarded Redis delete (#3487) has removed the
    session, so local cleanup must complete independently of notifications:
    the FSM is cleared and the client is still handled, failures are
    observable, and a retry is safe.
    """
    caplog.set_level(logging.ERROR, logger="telegram_bot.handlers.bot_handoff")
    state = HandoffState(mock_redis, ttl_hours=24)  # type: ignore[arg-type]
    await state.set(HandoffData(client_id=999, topic_id=42, mode="human"))
    handoff = await state.get_by_topic(42)
    assert handoff is not None
    bridge = _bridge()
    bot = _bot(bridge, state)

    if fault_point == "close":
        bridge.close_topic.side_effect = RuntimeError("topic close down")
    elif fault_point == "notify":
        bot.bot.send_message.side_effect = RuntimeError("telegram down")
    elif fault_point == "cleanup":
        bot.dp.storage.set_state.side_effect = RuntimeError("fsm storage down")

    await _no_leak(
        bot_handoff._close_handoff(bot, handoff),  # type: ignore[arg-type]
        scenario=f"close fault {fault_point}",
    )

    # The session is always gone (guarded delete stays first, #3487).
    assert await state.get_by_client(999) is None
    assert await state.get_by_topic(42) is None

    # Local cleanup is attempted exactly once regardless of the fault point.
    bot.dp.storage.set_state.assert_awaited_once()
    if fault_point != "cleanup":
        assert bot.dp.storage.set_state.await_args.kwargs["state"] is None

    # The client-facing and topic-facing steps are still attempted.
    bot.bot.send_message.assert_awaited_once()
    bridge.send_to_topic.assert_awaited_once()
    bridge.close_topic.assert_awaited_once()

    assert _recovery_error_logged(caplog) is expected["error_logged"], (
        f"close fault {fault_point}: recovery error observability mismatch"
    )


@pytest.mark.asyncio
async def test_close_with_already_deleted_topic_skips_close_and_still_cleans(
    mock_redis: object, caplog: pytest.LogCaptureFixture
) -> None:
    """A /close racing a deleted topic must not call close_topic (#3488).

    ``send_to_topic`` reports the topic is gone (message landed in General);
    closing it would raise against Telegram. Local cleanup continues anyway.
    """
    caplog.set_level(logging.ERROR, logger="telegram_bot.handlers.bot_handoff")
    state = HandoffState(mock_redis, ttl_hours=24)  # type: ignore[arg-type]
    await state.set(HandoffData(client_id=999, topic_id=42, mode="human"))
    handoff = await state.get_by_topic(42)
    assert handoff is not None
    bridge = _bridge()
    bridge.send_to_topic = AsyncMock(return_value=False)
    bot = _bot(bridge, state)

    await _no_leak(
        bot_handoff._close_handoff(bot, handoff),  # type: ignore[arg-type]
        scenario="close with deleted topic",
    )

    bridge.close_topic.assert_not_awaited()
    bot.bot.send_message.assert_awaited_once()
    bot.dp.storage.set_state.assert_awaited_once()
    assert await state.get_by_client(999) is None
    assert not _recovery_error_logged(caplog)


@pytest.mark.asyncio
async def test_repeated_close_after_completed_close_is_safe(mock_redis: object) -> None:
    """A stale snapshot /close after completion is a no-op (#3487 + #3488)."""
    state = HandoffState(mock_redis, ttl_hours=24)  # type: ignore[arg-type]
    await state.set(HandoffData(client_id=999, topic_id=42, mode="human"))
    handoff = await state.get_by_topic(42)
    assert handoff is not None
    bridge = _bridge()
    bot = _bot(bridge, state)

    await _no_leak(
        bot_handoff._close_handoff(bot, handoff),  # type: ignore[arg-type]
        scenario="first close",
    )
    await _no_leak(
        bot_handoff._close_handoff(bot, handoff),  # type: ignore[arg-type]
        scenario="repeated close",
    )

    bot.bot.send_message.assert_awaited_once(), "client must not be notified twice"
    bridge.close_topic.assert_awaited_once()
    assert await state.get_by_client(999) is None


@pytest.mark.asyncio
async def test_setup_summary_failure_degrades_gracefully(
    mock_redis: object, caplog: pytest.LogCaptureFixture
) -> None:
    """An AI-summary failure must not orphan the topic (#3488).

    The summary is optional context: when its generation fails, the handoff
    continues without it — topic created, context pack posted, state saved —
    and the failure is observable.
    """
    caplog.set_level(logging.WARNING, logger="telegram_bot.handlers.bot_handoff")
    state = HandoffState(mock_redis, ttl_hours=24)  # type: ignore[arg-type]
    bridge = _bridge(topic_id=111)
    bot = _bot(bridge, state)
    history = [
        json.dumps({"role": "user", "content": "Требуется квартира"}),
        json.dumps({"role": "assistant", "content": "Какой бюджет?"}),
        json.dumps({"role": "user", "content": "До 100 тысяч"}),
    ]
    bot._cache.redis = MagicMock()
    bot._cache.redis.lrange = AsyncMock(return_value=history)
    message = _message()
    fsm = _fsm()

    with (
        patch(
            "telegram_bot.services.crm.handoff_summary.generate_handoff_summary",
            side_effect=RuntimeError("llm down"),
        ),
        patch("telegram_bot.handlers.bot_handoff.is_business_hours", return_value=True),
    ):
        await _no_leak(_run_setup(bot, message, fsm), scenario="summary failure")

    # Handoff completed without the summary.
    bridge.post_context_pack.assert_awaited_once()
    assert bridge.post_context_pack.await_args.kwargs["summary"] is None
    bridge.close_topic.assert_not_awaited()
    stored = await state.get_by_client(999)
    assert stored is not None and stored.topic_id == 111
    fsm.set_state.assert_awaited_once_with(HandoffStates.active)
    assert any(record.levelno >= logging.WARNING for record in caplog.records), (
        "summary failure was not observable"
    )


@pytest.fixture
def mock_redis() -> object:
    """In-memory Redis mock using fakeredis."""
    import fakeredis.aioredis

    return fakeredis.aioredis.FakeRedis(decode_responses=True)
