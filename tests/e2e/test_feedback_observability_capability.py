"""Live feedback observability capability E2E (#3422, audit A11).

Proves the feedback capability end-to-end through the REAL registered
dispatcher routes: ``Dispatcher.feed_update`` drives production
``FeedbackCB``/``FeedbackReasonCB`` callback Updates through the actual
middlewares and the ``FeedbackCB.filter()`` / ``FeedbackReasonCB.filter()``
registrations in ``PropertyBot._register_handlers``, the accepted/reason
handlers persist ONE redacted feedback record through the configured local
persistence/event writer (the lifecycle-owned ``FeedbackEventStore`` on the
production asyncpg pool of a run-owned schema, the #3414 harness seam), and
the outgoing acknowledgement is observed at a deterministic in-process
Telegram transport (the real aiogram client stack on a recorded
``BaseSession``).

Characterization ownership (issue "Exact ownership"): direct parser/keyboard
cases stay in their consolidated unit owners
(``tests/unit/test_feedback.py``, ``tests/unit/test_callback_data.py``,
``tests/unit/test_feedback_handler.py``,
``tests/unit/test_bot_feedback_integration.py``); this lane only pins the
dispatcher-level linkage, the persisted record contract, idempotency, the
banned-key redaction, and the storage-failure behavior. No observability
framework, no persistence redesign: the store is the established
``telegram_bot/services/observability`` append-only asyncpg pattern and its
append signature is an explicit allowlist (user/session/request linkage plus
the enumerated action and the fixed reason code), so a token, phone number,
or raw prompt cannot enter the record or the structured error log.

Scenarios (issue acceptance):

1. A like callback stores EXACTLY one record linked to the request
   (``request_id`` == the keyboard ``trace_id``) and the session (the
   production ``make_session_id("chat", chat_id)`` format); the outgoing
   acknowledgement is observed once; ``done`` dismisses without a record.
2. A dislike first shows the reason keyboard and stores NOTHING (the
   feedback is not accepted yet); selecting a reason stores the single
   record with the reason; the acknowledgement is observed.
3. Duplicate and repeated callbacks are idempotent: still exactly one record
   per request, with an optional reason updating that same record.
4. A storage failure keeps the safe UI (thanks acknowledgement plus
   confirmation keyboard, nothing user-visible breaks) and logs ONE
   structured error carrying ``request_id``/``action`` fields with no banned
   content.

Redaction is proven against the full stored row (exact column allowlist plus
banned-needle scan) and the structured error text. The lane never touches
Langfuse/OTEL/dashboard telemetry (neither package is even importable after
the run — the capability imports none of them).

Teardown (#3422 rollback): the journey purges exactly its own rows by
``user_id`` and proves zero remain; the module's run-owned schema is dropped
and proven gone by the #3414 ``TeardownRegistry``.

Focused run (per the issue):

    E2E_CORE_STRICT=1 uv run --no-sync pytest -q tests/e2e/test_feedback_observability_capability.py

Required mode (``E2E_CORE_STRICT``/``E2E_HARNESS_REQUIRED``) has ZERO
service-related skips: missing PostgreSQL fails, never skips. The canonical
hermetic entry is ``make e2e-harness`` with
``E2E_HARNESS_PATHS=tests/e2e/test_feedback_observability_capability.py``.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import sys
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from telegram_bot.callback_data import FeedbackCB, FeedbackReasonCB
from telegram_bot.observability.context import make_session_id
from telegram_bot.startup_status import StartupReport
from tests.e2e_core.live_harness import (
    RunNamespace,
    TeardownRegistry,
    guard_service_skip,
    provide_postgres_schema,
)
from tests.unit._bot_config_factory import make_full_bot_config
from tests.unit._property_bot_factory import make_property_bot


pytestmark = [pytest.mark.e2e, pytest.mark.requires_services]

# The production throttling middleware paces callbacks at 0.3 s per user;
# the journey paces its feeds above that instead of exempting the test user.
_CALLBACK_PACE_S = 0.35

_BOT_TOKEN = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"

_THANKS_TEXT = "Спасибо за отзыв!"

# Distinct banned-content needles that must never reach the stored record or
# the structured error log: a bot token, a phone number, and a raw user
# prompt. None of them is part of the feedback flow, so any appearance is a
# leak. The journey identity (first/last name, username) is likewise
# operational data the handler can see but must never persist.
_BANNED_TOKEN = _BOT_TOKEN
_BANNED_PHONE = "+79991234567"
_BANNED_PROMPT = "Какие документы нужны для оформления ВНЖ?"

_MODULE_LOOP = pytest.mark.asyncio(loop_scope="module")

_SALT_SEQUENCE = itertools.count(1)

# The exact persisted column allowlist (#3422 redaction contract): linkage
# plus the enumerated state — no free-text payload column exists.
_FEEDBACK_EVENT_COLUMNS = {
    "id",
    "user_id",
    "session_id",
    "request_id",
    "action",
    "reason",
    "created_at",
    "updated_at",
}


def _deterministic_telegram_id(run_id: str, salt: int) -> int:
    """Stable per-run client id so re-runs against the schema stay clean."""
    return (int(run_id[:8], 16) + salt) % (2**31 - 1)


def _schema_pinned_dsn(dsn: str, schema: str) -> str:
    """Append ``search_path`` so the production pool hits the run-owned schema.

    Mirrors tests/e2e/test_postgres_capability.py: asyncpg forwards unknown
    DSN query parameters as server settings, so the production bot DSN is
    pointed at the namespaced schema without touching production code.
    """
    separator = "&" if "?" in dsn else "?"
    return f"{dsn}{separator}search_path={schema}"


# ---------------------------------------------------------------------------
# Deterministic Telegram transport: real client stack, recorded API calls
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TelegramCall:
    """One recorded Bot API call at the transport boundary."""

    method: str
    payload: dict[str, Any]


class RecordingTelegramSession(BaseSession):
    """In-process Telegram transport for the feedback journey.

    Every ``make_request`` is recorded (method name, payload) so the tests
    assert real outgoing side effects — the acknowledgement
    (``answerCallbackQuery``) and the keyboard swaps
    (``editMessageText``) — at the transport boundary.
    """

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramCall] = []

    async def close(self) -> None:
        return None

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,  # noqa: ASYNC109 — supertype signature
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        raise NotImplementedError("the feedback journey never downloads files")
        yield b""  # pragma: no cover

    def calls_of(self, method: str) -> list[TelegramCall]:
        return [call for call in self.calls if call.method == method]

    def acks(self) -> list[TelegramCall]:
        return self.calls_of("answerCallbackQuery")

    def edits(self) -> list[TelegramCall]:
        """Keyboard swaps: the handler's ``Message.edit_reply_markup`` calls."""
        return self.calls_of("editMessageReplyMarkup")

    async def make_request(self, bot: Bot, method: Any, timeout: int | None = None) -> Any:  # noqa: ASYNC109
        name = method.__api_method__
        payload = method.model_dump(warnings=False)
        result: Any = True
        if name == "editMessageText":
            chat_id = int(payload.get("chat_id") or 0)
            result = Message(
                message_id=int(payload.get("message_id") or 0),
                date=datetime.now(UTC),
                chat=Chat(id=chat_id, type="private"),
                text=payload.get("text"),
            )
        self.calls.append(TelegramCall(method=name, payload=payload))
        return result


# ---------------------------------------------------------------------------
# Module stack: run-owned schema + production lifecycle wiring
# ---------------------------------------------------------------------------


@dataclass
class _FeedbackStack:
    """Production bot + run-owned Postgres schema ownership handles."""

    namespace: RunNamespace
    lease: Any  # PostgresLease
    bot: Any
    report: StartupReport


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def feedback_stack() -> AsyncIterator[_FeedbackStack]:
    """One run-owned schema with the production capability wiring applied.

    Provisioning doubles as the availability probe: unreachable PostgreSQL
    skips in optional mode and FAILS in required mode (``guard_service_skip``)
    — a required capability can never go green through a skip. The production
    ``setup_postgres`` bootstrap creates the schema (including
    ``feedback_events``), wires the feedback store on the production pool, and
    ``_setup_workflow_data`` publishes it to the real dispatcher's workflow
    data. Teardown closes the pool (mirroring ``lifecycle.stop_bot``), then
    drops ONLY the run-owned schema and proves it is gone.
    """
    namespace = RunNamespace.resolve()
    registry = TeardownRegistry(run_id=namespace.run_id)
    bot: Any = None
    try:
        try:
            lease = await provide_postgres_schema(None, namespace)
        except Exception as exc:
            guard_service_skip(
                f"PostgreSQL unavailable for the feedback capability lane: "
                f"{type(exc).__name__}: {exc}"
            )
        registry.register_postgres(lease)

        from telegram_bot.lifecycle.lifecycle import setup_postgres

        config = make_full_bot_config(
            telegram_token=_BOT_TOKEN,
            realestate_database_url=_schema_pinned_dsn(lease.dsn, lease.schema),
        )
        bot = make_property_bot(config)
        # Deterministic Telegram boundary: the real aiogram Bot on a recorded
        # session, so acknowledgements are observed, never sent to Telegram.
        bot.bot = Bot(token=_BOT_TOKEN, session=RecordingTelegramSession())

        report = StartupReport()
        await setup_postgres(bot, {"postgres": True}, report)
        assert bot._feedback_store is not None, (
            "production setup_postgres must wire the feedback event store (#3422)"
        )
        bot._setup_workflow_data()
        assert bot.dp["feedback_store"] is bot._feedback_store, (
            "the real dispatcher must receive the configured feedback store"
        )

        yield _FeedbackStack(namespace=namespace, lease=lease, bot=bot, report=report)
    finally:
        if bot is not None:
            from telegram_bot.capabilities import set_bookmarks_ready

            set_bookmarks_ready(bot, service=None)
            pool = bot._pg_pool
            if pool is not None:
                await pool.close()
        teardown_report = await registry.teardown_and_verify()
        assert teardown_report["schemas"] == 1


# ---------------------------------------------------------------------------
# Journey: one client's callbacks with exact row rollback
# ---------------------------------------------------------------------------


class _FeedbackJourney:
    """One client's live feedback journey against the real dispatcher."""

    def __init__(self, stack: _FeedbackStack, transport: RecordingTelegramSession) -> None:
        self.stack = stack
        self.bot = stack.bot
        self.transport = transport
        self.client_id = _deterministic_telegram_id(stack.namespace.run_id, next(_SALT_SEQUENCE))
        self._next_update_id = 1

    @property
    def session_id(self) -> str:
        """The production session id the query pipeline derives for this chat."""
        return make_session_id("chat", self.client_id)

    def _journey_user(self) -> User:
        return User(
            id=self.client_id,
            is_bot=False,
            first_name="Тест",
            last_name="Клиент",
            username=f"user{self.client_id}",
            language_code="ru",
        )

    async def feed_callback(self, data: str) -> None:
        """One production callback Update through ``Dispatcher.feed_update``."""
        await asyncio.sleep(_CALLBACK_PACE_S)
        self._next_update_id += 1
        update = Update(
            update_id=self._next_update_id,
            callback_query=CallbackQuery(
                id=str(self._next_update_id),
                from_user=self._journey_user(),
                chat_instance=f"feedback-e2e-{self.client_id}",
                data=data,
                message=Message(
                    message_id=self._next_update_id,
                    date=datetime.now(UTC),
                    chat=Chat(id=self.client_id, type="private"),
                ),
            ),
        )
        await self.bot.dp.feed_update(self.bot.bot, update)

    def like(self, trace_id: str) -> str:
        """The exact bytes the production like button puts on the keyboard."""
        return FeedbackCB(action="like", trace_id=trace_id).pack()

    def dislike(self, trace_id: str) -> str:
        """The exact bytes the production dislike button puts on the keyboard."""
        return FeedbackCB(action="dislike", trace_id=trace_id).pack()

    def reason(self, code: str, trace_id: str) -> str:
        """The exact bytes a production reason button puts on the keyboard."""
        return FeedbackReasonCB(code=code, trace_id=trace_id).pack()

    def done(self) -> str:
        """The exact bytes the production confirmation button puts on the keyboard."""
        return FeedbackCB(action="done", trace_id="").pack()


@pytest_asyncio.fixture(loop_scope="module")
async def journey(
    feedback_stack: _FeedbackStack,
) -> AsyncIterator[_FeedbackJourney]:
    """One client's journey: fresh transport, unique id, exact row rollback."""
    # A fresh recorded session per test keeps side-effect counts absolute.
    feedback_stack.bot.bot.session = RecordingTelegramSession()
    current = _FeedbackJourney(feedback_stack, feedback_stack.bot.bot.session)
    try:
        yield current
    finally:
        await _purge_journey_rows(feedback_stack.lease, current.client_id)


async def _connect(dsn: str) -> Any:
    import asyncpg

    return await asyncpg.connect(dsn, timeout=10)


async def _rows_for_request(lease: Any, request_id: str) -> list[dict[str, Any]]:
    """The feedback records stored for one request in the run-owned schema."""
    connection = await _connect(lease.dsn)
    try:
        rows = await connection.fetch(
            f'SELECT * FROM "{lease.schema}".feedback_events WHERE request_id = $1 ORDER BY id',
            request_id,
        )
    finally:
        await connection.close()
    return [dict(row) for row in rows]


async def _owned_row_count(lease: Any, user_id: int) -> int:
    connection = await _connect(lease.dsn)
    try:
        count = await connection.fetchval(
            f'SELECT COUNT(*) FROM "{lease.schema}".feedback_events WHERE user_id = $1',
            user_id,
        )
    finally:
        await connection.close()
    return int(count)


async def _purge_journey_rows(lease: Any, user_id: int) -> None:
    """Rollback (#3422): delete exactly this journey's rows and prove it."""
    connection = await _connect(lease.dsn)
    try:
        await connection.execute(
            f'DELETE FROM "{lease.schema}".feedback_events WHERE user_id = $1',
            user_id,
        )
    finally:
        await connection.close()
    assert await _owned_row_count(lease, user_id) == 0, (
        f"run-owned feedback rows survived rollback for user_id={user_id}"
    )


def _row_text(row: dict[str, Any]) -> str:
    return json.dumps(row, ensure_ascii=False, default=str)


def _assert_redacted_row(row: dict[str, Any], journey: _FeedbackJourney) -> None:
    """The stored record is exactly the allowlisted linkage + state."""
    assert set(row.keys()) == _FEEDBACK_EVENT_COLUMNS
    text = _row_text(row)
    for needle in (
        _BANNED_TOKEN,
        _BANNED_PHONE,
        _BANNED_PROMPT,
        "Тест",
        "Клиент",
        f"user{journey.client_id}",
    ):
        assert needle not in text, f"banned content {needle!r} leaked into the stored record"


def _assert_acknowledged(journey: _FeedbackJourney, *, texts: list[str | None]) -> None:
    """The outgoing acknowledgement sequence observed at the transport.

    Every callback Update is first auto-answered with no text by the
    production aiogram ``CallbackAnswerMiddleware`` (spinner dismissal,
    registered ``pre=True`` in ``setup_throttling_middleware``) — its presence
    proves the real middleware chain ran; the handler's own answer (the
    thanks text or a plain dismissal) follows.
    """
    acks = journey.transport.acks()
    assert [call.payload.get("text") for call in acks] == texts


def _keyboard_rows(call: TelegramCall) -> list[Any]:
    markup = call.payload.get("reply_markup")
    assert markup is not None, "the handler must swap the reply keyboard"
    return markup["inline_keyboard"]


# ---------------------------------------------------------------------------
# Scenario 1 — like: one redacted linked record + observed acknowledgement
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(120)
async def test_like_stores_one_redacted_linked_record_with_acknowledgement(
    journey: _FeedbackJourney,
) -> None:
    """A like callback persists exactly one linked record and answers once."""
    trace_id = f"req-{journey.stack.namespace.run_id}-{journey.stack.namespace.worker}-1"

    await journey.feed_callback(journey.like(trace_id))

    # Outgoing acknowledgement observed at the transport: the middleware's
    # spinner auto-answer, then the handler's thanks + confirmation keyboard.
    _assert_acknowledged(journey, texts=[None, _THANKS_TEXT])
    edits = journey.transport.edits()
    assert len(edits) >= 1
    confirmation_rows = _keyboard_rows(edits[0])
    assert len(confirmation_rows) == 1, "the confirmation keyboard is a single button"

    # Exactly one record, linked to the request AND the session.
    rows = await _rows_for_request(journey.stack.lease, trace_id)
    assert len(rows) == 1
    row = rows[0]
    assert row["request_id"] == trace_id
    assert row["user_id"] == journey.client_id
    assert row["session_id"] == journey.session_id
    assert row["action"] == "like"
    assert row["reason"] is None
    _assert_redacted_row(row, journey)

    # done dismisses the keyboard: answered without text, no new record.
    await journey.feed_callback(journey.done())
    _assert_acknowledged(journey, texts=[None, _THANKS_TEXT, None, None])
    assert len(await _rows_for_request(journey.stack.lease, trace_id)) == 1

    # The capability never touches Langfuse/OTEL/dashboard telemetry.
    assert not [name for name in sys.modules if name.startswith(("langfuse", "opentelemetry"))]


# ---------------------------------------------------------------------------
# Scenario 2 — dislike: reason keyboard first, then the single reason record
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(120)
async def test_dislike_reason_selection_stores_the_single_record(
    journey: _FeedbackJourney,
) -> None:
    """Dislike shows reasons and stores nothing; a reason stores one record."""
    trace_id = f"req-{journey.stack.namespace.run_id}-{journey.stack.namespace.worker}-2"

    # Step 1: the dislike is not accepted yet — reasons, no thanks text,
    # and NO record.
    await journey.feed_callback(journey.dislike(trace_id))
    _assert_acknowledged(journey, texts=[None, None])
    reason_rows = _keyboard_rows(journey.transport.edits()[0])
    assert len(reason_rows) == 3, "the dislike reason keyboard is 3 rows of 2"
    assert all(button["callback_data"].startswith("fbr:") for row in reason_rows for button in row)
    assert await _rows_for_request(journey.stack.lease, trace_id) == []

    # Step 2: selecting a reason accepts the feedback — one record with it.
    await journey.feed_callback(journey.reason("fm", trace_id))
    _assert_acknowledged(journey, texts=[None, None, None, _THANKS_TEXT])
    rows = await _rows_for_request(journey.stack.lease, trace_id)
    assert len(rows) == 1
    row = rows[0]
    assert row["request_id"] == trace_id
    assert row["user_id"] == journey.client_id
    assert row["session_id"] == journey.session_id
    assert row["action"] == "dislike"
    assert row["reason"] == "formatting"
    _assert_redacted_row(row, journey)


# ---------------------------------------------------------------------------
# Scenario 3 — duplicates and reason updates stay one record (idempotent)
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(120)
async def test_duplicate_and_repeated_callbacks_update_one_record(
    journey: _FeedbackJourney,
) -> None:
    """Exactly one record per request; reasons update that same record."""
    trace_id = f"req-{journey.stack.namespace.run_id}-{journey.stack.namespace.worker}-3"

    await journey.feed_callback(journey.like(trace_id))
    rows = await _rows_for_request(journey.stack.lease, trace_id)
    assert len(rows) == 1 and rows[0]["action"] == "like"

    # Duplicate identical callback (double-tap): still exactly one record.
    await journey.feed_callback(journey.like(trace_id))
    rows = await _rows_for_request(journey.stack.lease, trace_id)
    assert len(rows) == 1 and rows[0]["action"] == "like" and rows[0]["reason"] is None

    # The optional reason refines the SAME record — the row is not duplicated
    # and the accepted state moves to the latest feedback.
    await journey.feed_callback(journey.reason("wt", trace_id))
    rows = await _rows_for_request(journey.stack.lease, trace_id)
    assert len(rows) == 1
    assert rows[0]["action"] == "dislike"
    assert rows[0]["reason"] == "wrong_topic"

    # A duplicate reason callback is idempotent; a different reason updates
    # the same single record again.
    await journey.feed_callback(journey.reason("wt", trace_id))
    rows = await _rows_for_request(journey.stack.lease, trace_id)
    assert len(rows) == 1 and rows[0]["reason"] == "wrong_topic"
    await journey.feed_callback(journey.reason("mi", trace_id))
    rows = await _rows_for_request(journey.stack.lease, trace_id)
    assert len(rows) == 1
    assert rows[0]["action"] == "dislike"
    assert rows[0]["reason"] == "missing_info"
    _assert_redacted_row(rows[0], journey)


# ---------------------------------------------------------------------------
# Scenario 4 — storage failure: safe UI + one structured error
# ---------------------------------------------------------------------------


class _ExplodingPool:
    """Deterministic storage outage seam for the production store."""

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("deterministic feedback store outage")


@_MODULE_LOOP
@pytest.mark.timeout(120)
async def test_storage_failure_keeps_safe_ui_and_logs_structured_error(
    journey: _FeedbackJourney,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failing store must not break the UI and must log one structured error."""
    trace_id = f"req-{journey.stack.namespace.run_id}-{journey.stack.namespace.worker}-4"
    from telegram_bot.services.observability.feedback_event_store import FeedbackEventStore

    configured_store = journey.bot._feedback_store
    assert configured_store is not None
    journey.bot.dp["feedback_store"] = FeedbackEventStore(pool=_ExplodingPool())
    try:
        with caplog.at_level(logging.ERROR, logger="telegram_bot.handlers.feedback_handlers"):
            await journey.feed_callback(journey.like(trace_id))

        # Safe UI: the thanks acknowledgement and the confirmation keyboard
        # still went out; nothing user-visible broke.
        _assert_acknowledged(journey, texts=[None, _THANKS_TEXT])
        edits = journey.transport.edits()
        assert len(edits) >= 1 and len(_keyboard_rows(edits[0])) == 1

        # Nothing was stored.
        assert await _rows_for_request(journey.stack.lease, trace_id) == []

        # Exactly one structured error carrying the linkage fields.
        records = [
            record
            for record in caplog.records
            if record.name == "telegram_bot.handlers.feedback_handlers"
            and record.levelno == logging.ERROR
        ]
        assert len(records) == 1
        assert records[0].request_id == trace_id  # type: ignore[attr-defined]
        assert records[0].action == "like"  # type: ignore[attr-defined]
        logged = records[0].getMessage()
        assert "RuntimeError" in logged
        for needle in (
            _BANNED_TOKEN,
            _BANNED_PHONE,
            _BANNED_PROMPT,
            "Тест",
            "Клиент",
            f"user{journey.client_id}",
        ):
            assert needle not in logged, f"banned content {needle!r} leaked into the log"
    finally:
        journey.bot.dp["feedback_store"] = configured_store
