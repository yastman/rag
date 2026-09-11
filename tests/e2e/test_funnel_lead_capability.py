"""Live funnel E2E: qualification, phone collection, lead durability (#3413).

Proves the Telegram funnel/contact journey end-to-end through the REAL
registered routes: ``Dispatcher.feed_update`` drives actual Updates through
the production middlewares, aiogram-dialog routers (funnel criteria, viewing
wizard), the phone-collector FSM, and the production
:class:`~telegram_bot.services.lead_sink.LeadRequestSink` backed by a REAL
Redis server. The manager notification travels through the production
:class:`~telegram_bot.services.forum_bridge.ForumBridge` on top of a
deterministic in-process Telegram transport (the real aiogram client stack
with a recorded ``BaseSession``) — no production credential, no paid
provider, no fake SDK packages.

Stack scoping (#3413, documented decision): the lead journey never touches
retrieval (Qdrant/BGE-M3/LLM) or PostgreSQL, so the lane runs against ONE
real dependency — Redis — provided as a disposable, authenticated container
per module following the proven ``test_redis_modes_live.py`` (#3368)
conventions: unique name, ephemeral host port, random password, no
persistence, removed and proven gone on teardown. Required mode
(``E2E_HARNESS_REQUIRED=1``, legacy ``E2E_CORE_STRICT=1``) turns a missing
Docker daemon into a FAILURE, never a skip (#3414 policy).

Scenarios (issue #3413 acceptance):

1. Funnel qualification (city -> property type -> budget -> preferences ->
   summary) traverses the real registered menu/dialog route to the summary
   preview — and a sentinel proves ZERO durable writes and ZERO manager side
   effects before the explicit phone confirmation.
2. Invalid phone input is visibly rejected, the FSM retains
   ``waiting_phone`` for retry, and nothing durable happens.
3. Phone text AND contact-share submissions traverse the real FSM route and
   produce one v2 durable record per logical request with the product
   contract fields (E.164 phone, service key, objects, date), one manager
   topic/message each, truthful success copy — while a pre-existing legacy
   ``lead_request:{client}`` hash stays byte-identical (read-only).
4. A retry of the SAME request id never duplicates the record nor replays
   the acknowledged manager notification (#3477 identity policy).
5. Persistence failure produces no manager topic/message and no success
   confirmation; the retry preserves the logical request id (#3322).
6. A topic created before a send failure is REUSED on retry — the topic is
   never re-created (#3477 documented policy).

Raw phone values never appear in application logs (privacy contract).

The bot is assembled once per module: aiogram-dialog routers are module
singletons, so a dispatcher can attach them exactly once per process
(production runs one bot per process). Per-test isolation comes from a
fresh transport session, a unique client id (FSM/throttle/Redis namespaces)
and exact run-owned Redis key cleanup.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import shutil
import subprocess
import time
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
import redis.asyncio as aioredis
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramServerError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import CallbackQuery, Chat, Contact, ForumTopicCreated, Message, Update, User

from src.runtime.integrations.cache import CacheLayerManager
from src.runtime.integrations.redis_mode import RedisMode
from tests.e2e_core.live_harness import guard_service_skip
from tests.unit._bot_config_factory import make_full_bot_config
from tests.unit._property_bot_factory import make_property_bot


pytestmark = [pytest.mark.e2e, pytest.mark.requires_services]

# The journey paces its feeds to stay above the production throttling rates
# (1.0 s per user for messages, 0.3 s for callbacks) instead of exempting the
# test user: the throttling middleware stays on the real path.
_MESSAGE_PACE_S = 1.05
_CALLBACK_PACE_S = 0.35

_CLIENT_MENU_SEARCH_TEXT = "🏠 Подобрать квартиру"
_VALID_PHONE_RAW = "+359 88 123 4567"
_VALID_PHONE_E164 = "+359881234567"
_CONTACT_PHONE_RAW = "+359 88 811 12 22"
_CONTACT_PHONE_E164 = "+359888111222"
_VIEWING_SUCCESS_TEXT = "✅ Заявка оформлена! Скоро менеджер свяжется с вами."
_PHONE_FAILURE_PREFIX = "⚠️ Не удалось сохранить заявку"
_PHONE_INVALID_TEXT = "Пожалуйста, введите корректный номер телефона"
_MANAGERS_GROUP_ID = -100_3413_0001
_BOT_TOKEN = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"

_WAITING_PHONE_STATE = "PhoneCollectorStates:waiting_phone"
_MODULE_LOOP = pytest.mark.asyncio(loop_scope="module")


# ---------------------------------------------------------------------------
# Disposable authenticated Redis container (#3368 conventions)
# ---------------------------------------------------------------------------


def _docker(*args: str, timeout: float = 60.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _docker_daemon_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return _docker("info", "--format", "{{.ServerVersion}}", timeout=30.0).returncode == 0


@dataclass(frozen=True, slots=True)
class LiveRedis:
    """One disposable, authenticated Redis server owned by this module."""

    name: str
    password: str
    port: int

    @property
    def url(self) -> str:
        return f"redis://:{self.password}@127.0.0.1:{self.port}/0"


def _start_redis_container(name: str, password: str) -> int:
    """Start the disposable server; return its ephemeral host port (#3368)."""
    run = _docker(
        "run",
        "-d",
        "--rm",
        "--name",
        name,
        "-P",
        "redis:8.10.1",
        "redis-server",
        "--requirepass",
        password,
        "--save",
        "",
        "--appendonly",
        "no",
        timeout=120.0,
    )
    if run.returncode != 0:
        raise RuntimeError(f"docker run redis failed: {run.stderr.strip()}")
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        published = _docker("port", name, "6379")
        for line in published.stdout.splitlines():
            host_port = line.strip().rsplit(":", 1)[-1]
            if host_port.isdigit():
                return int(host_port)
        time.sleep(0.2)
    _docker("rm", "-f", name)
    raise RuntimeError(f"docker did not publish a host port for {name}")


def _container_gone(name: str) -> bool:
    listed = _docker("ps", "-a", "--filter", f"name=^{name}$", "--format", "{{.Names}}")
    return listed.returncode == 0 and listed.stdout.strip() == ""


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def funnel_bot() -> AsyncIterator[tuple[Any, LiveRedis]]:
    """One assembled bot + one disposable Redis for the whole module."""
    if not _docker_daemon_available():
        guard_service_skip("Docker daemon unavailable — funnel live harness cannot start")
    name = f"rag-e2e-3413-{uuid.uuid4().hex[:10]}"
    password = f"pw-{uuid.uuid4().hex}"
    live: LiveRedis | None = None
    bot: Any = None
    try:
        port = _start_redis_container(name, password)
        live = LiveRedis(name=name, password=password, port=port)
        bot = await _build_funnel_bot(live)
        yield bot, live
    finally:
        if bot is not None:
            with contextlib.suppress(Exception):
                await bot._cache.close()
        if live is not None:
            _docker("rm", "-f", name)
        assert _container_gone(name), f"disposable Redis container {name} survived cleanup"


_CLIENT_ID_SEQUENCE = iter(range(3413_0001, 3413_0001 + 100))


@pytest_asyncio.fixture(loop_scope="module")
async def journey(funnel_bot: tuple[Any, LiveRedis]) -> AsyncIterator[_FunnelJourney]:
    """One client's journey: fresh transport, unique id, exact key cleanup."""
    bot, live = funnel_bot
    # A fresh recorded session per test keeps side-effect counts absolute.
    bot.bot.session = RecordingTelegramSession()
    client = aioredis.from_url(live.url, decode_responses=True)
    current = _FunnelJourney(bot, bot.bot.session, next(_CLIENT_ID_SEQUENCE))
    current.redis_client = client
    try:
        yield current
    finally:
        await _cleanup_client_keys(client, current.client_id)
        await client.aclose()


# ---------------------------------------------------------------------------
# Deterministic Telegram transport: real client stack, recorded API calls
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TelegramCall:
    """One recorded Bot API call at the transport boundary."""

    method: str
    payload: dict[str, Any]
    result: Any = None


class RecordingTelegramSession(BaseSession):
    """In-process Telegram/forum transport for the funnel journey.

    Every ``make_request`` is recorded (method name, payload, canned result)
    so tests assert real side effects at the transport boundary. Selected
    methods can be made to fail deterministically via :attr:`fail_when`.
    """

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramCall] = []
        self._next_message_id = 10_000
        self._next_topic_id = 3_400
        self.fail_when: Callable[[str, dict[str, Any], Any], Exception | None] | None = None

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
        raise NotImplementedError("the funnel journey never downloads files")
        yield b""  # pragma: no cover

    def calls_of(self, method: str) -> list[TelegramCall]:
        return [call for call in self.calls if call.method == method]

    def texts_sent_to(self, chat_id: int) -> list[str]:
        return [
            str(call.payload.get("text") or "")
            for call in self.calls_of("sendMessage")
            if call.payload.get("chat_id") == chat_id
        ]

    def manager_sends(self) -> list[TelegramCall]:
        return [
            call
            for call in self.calls_of("sendMessage")
            if call.payload.get("chat_id") == _MANAGERS_GROUP_ID
        ]

    async def make_request(self, bot: Bot, method: Any, timeout: int | None = None) -> Any:  # noqa: ASYNC109
        name = method.__api_method__
        payload = method.model_dump(warnings=False)
        if self.fail_when is not None:
            failure = self.fail_when(name, payload, method)
            if failure is not None:
                self.calls.append(TelegramCall(method=name, payload=payload))
                raise failure

        result: Any = True
        if name == "sendMessage":
            self._next_message_id += 1
            chat_id = int(payload.get("chat_id") or 0)
            result = Message(
                message_id=self._next_message_id,
                date=datetime.now(UTC),
                chat=Chat(id=chat_id, type="supergroup" if chat_id < 0 else "private"),
                text=payload.get("text"),
                message_thread_id=payload.get("message_thread_id"),
            )
        elif name == "editMessageText":
            # aiogram-dialog reads media attributes off the edited message.
            chat_id = int(payload.get("chat_id") or 0)
            result = Message(
                message_id=int(payload.get("message_id") or 0),
                date=datetime.now(UTC),
                chat=Chat(id=chat_id, type="supergroup" if chat_id < 0 else "private"),
                text=payload.get("text"),
                message_thread_id=payload.get("message_thread_id"),
            )
        elif name == "createForumTopic":
            self._next_topic_id += 1
            result = ForumTopicCreated(
                message_thread_id=self._next_topic_id,
                name=str(payload.get("name") or ""),
                icon_color=0x6FB9F0,
            )
        self.calls.append(TelegramCall(method=name, payload=payload, result=result))
        return result


# ---------------------------------------------------------------------------
# Journey assembly: production lifecycle over real Redis + recorded transport
# ---------------------------------------------------------------------------


class _FunnelJourney:
    """One client's live journey against one real bot + real Redis.

    ``redis_client`` is attached by the ``journey`` fixture: an independent
    observer client used only for durable-state assertions.
    """

    redis_client: aioredis.Redis

    def __init__(self, bot: Any, transport: RecordingTelegramSession, client_id: int) -> None:
        self.bot = bot
        self.transport = transport
        self.client_id = client_id
        self._next_update_id = 1

    def _journey_user(self) -> User:
        return User(
            id=self.client_id,
            is_bot=False,
            first_name="Тест",
            last_name="Клиент",
            username=f"user{self.client_id}",
            language_code="ru",
        )

    async def feed_message(
        self, text: str | None = None, *, contact: Contact | None = None
    ) -> None:
        await asyncio.sleep(_MESSAGE_PACE_S)
        self._next_update_id += 1
        update = Update(
            update_id=self._next_update_id,
            message=Message(
                message_id=self._next_update_id,
                date=datetime.now(UTC),
                chat=Chat(id=self.client_id, type="private"),
                from_user=self._journey_user(),
                text=text,
                contact=contact,
            ),
        )
        await self.bot.dp.feed_update(self.bot.bot, update)

    async def feed_callback(self, data: str) -> None:
        await asyncio.sleep(_CALLBACK_PACE_S)
        self._next_update_id += 1
        update = Update(
            update_id=self._next_update_id,
            callback_query=CallbackQuery(
                id=str(self._next_update_id),
                from_user=self._journey_user(),
                chat_instance="funnel-e2e",
                data=data,
                message=Message(
                    message_id=1,
                    date=datetime.now(UTC),
                    chat=Chat(id=self.client_id, type="private"),
                ),
            ),
        )
        await self.bot.dp.feed_update(self.bot.bot, update)

    def fsm(self) -> FSMContext:
        return FSMContext(
            storage=self.bot.dp.storage,
            key=StorageKey(bot_id=self.bot.bot.id, chat_id=self.client_id, user_id=self.client_id),
        )

    async def dialog_state(self) -> str | None:
        """Read the aiogram-dialog context state (its own storage destiny).

        aiogram-dialog 2.6 keeps dialog contexts under ``aiogd:stack:`` /
        ``aiogd:context:<intent>`` destinies of the dispatcher storage, so the
        default-destiny FSM state stays empty while a dialog owns the chat.
        """
        storage = self.bot.dp.storage

        def _destiny_key(destiny: str) -> StorageKey:
            return StorageKey(
                bot_id=self.bot.bot.id,
                chat_id=self.client_id,
                user_id=self.client_id,
                destiny=destiny,
            )

        stack = await storage.get_data(_destiny_key("aiogd:stack:"))
        intents = stack.get("intents") or []
        if not intents:
            return None
        context = await storage.get_data(_destiny_key(f"aiogd:context:{intents[-1]}"))
        state = context.get("state")
        return str(state) if state else None


async def _build_funnel_bot(live_redis: LiveRedis) -> Any:
    """Assemble the production bot over real Redis via the DI/test seams."""
    cache = CacheLayerManager(redis_url=live_redis.url, mode=RedisMode.SINGLE_INSTANCE)
    await cache.initialize()
    config = make_full_bot_config(
        telegram_token=_BOT_TOKEN,
        redis_url=live_redis.url,
        redis_mode="single_instance",
        managers_group_id=_MANAGERS_GROUP_ID,
    )
    bot = make_property_bot(
        config,
        service_overrides={"cache": cache, "apartments_service": None},
    )
    # Deterministic Telegram/forum boundary: the real aiogram Bot on a
    # recorded session. Swapped BEFORE the handoff lifecycle builds the
    # ForumBridge, so the production bridge owns this transport.
    bot.bot = Bot(token=_BOT_TOKEN, session=RecordingTelegramSession())
    # The exact production lifecycle steps that wire the durable stack.
    bot._setup_handoff_services()
    bot._setup_workflow_data()
    bot._setup_dialogs()
    assert bot._lead_sink is not None, "production lifecycle must wire the lead sink"
    assert bot._forum_bridge is not None, "managers group must wire the forum bridge"
    return bot


async def _start_viewing_journey(journey: _FunnelJourney, *, property_id: str) -> None:
    """Catalog card -> viewing wizard -> date criterion -> phone prompt."""
    await journey.fsm().set_data(
        {
            "apartment_results": [
                {
                    "id": property_id,
                    "payload": {
                        "complex_name": "Солнечный берег",
                        "property_type": "2-спальни",
                        "area_m2": 61,
                        "price_eur": 89000,
                    },
                }
            ]
        }
    )
    await journey.feed_callback(f"card:viewing:{property_id}")
    await journey.feed_callback("viewing_date:nearest")
    state = await journey.fsm().get_state()
    assert state == _WAITING_PHONE_STATE, f"journey must reach the phone FSM, got {state}"


async def _assert_zero_durable_writes(client: aioredis.Redis, client_id: int) -> None:
    for key in (f"lead_request:v2:{client_id}", f"lead_request:{client_id}"):
        assert await client.hgetall(key) == {}, f"unexpected durable record in {key}"


async def _assert_zero_notify_state(client: aioredis.Redis, client_id: int) -> None:
    assert await client.hgetall(f"lead_notify:v2:{client_id}") == {}


def _assert_zero_manager_side_effects(transport: RecordingTelegramSession) -> None:
    assert transport.calls_of("createForumTopic") == [], "unexpected manager topic"
    assert transport.manager_sends() == [], "unexpected manager message"


async def _cleanup_client_keys(client: aioredis.Redis, client_id: int) -> None:
    await client.delete(
        f"lead_request:v2:{client_id}",
        f"lead_request:{client_id}",
        f"lead_notify:v2:{client_id}",
    )


def _first_field(raw_v2: dict[str, str]) -> str:
    """Deterministic field pick for single-record hashes."""
    assert len(raw_v2) == 1, f"expected exactly one record, got {sorted(raw_v2)}"
    return next(iter(raw_v2))


# ---------------------------------------------------------------------------
# Scenario 1 — funnel qualification: real route, preview, zero-side-effect sentinel
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(180)
async def test_funnel_qualification_routes_real_updates_and_persists_nothing_before_confirmation(
    journey: _FunnelJourney,
) -> None:
    client = journey.redis_client
    # Start -> criteria through the real menu button and funnel dialog:
    # city -> property type -> budget -> preferences -> summary preview.
    await journey.feed_message(_CLIENT_MENU_SEARCH_TEXT)
    await journey.feed_callback("city:Солнечный берег")
    await journey.feed_callback("property_type:2bed")
    await journey.feed_callback("budget:mid")
    await journey.feed_callback("pref_done")

    # The dialog context is the summary (preview + confirmation) window.
    assert await journey.dialog_state() == "FunnelSG:summary"

    # The rendered preview reflects the selected criteria.
    surface_texts = [
        call.payload.get("text") or ""
        for call in journey.transport.calls
        if call.method in {"sendMessage", "editMessageText"}
    ]
    preview = "\n".join(surface_texts)
    assert "Город: Солнечный берег" in preview, preview
    assert "Тип: 2-спальни" in preview, preview
    assert "Бюджет: 50 000 – 100 000 €" in preview, preview

    # Sentinel: before the explicit phone confirmation there is no durable
    # record, no notification state, no manager side effect.
    await _assert_zero_durable_writes(client, journey.client_id)
    await _assert_zero_notify_state(client, journey.client_id)
    _assert_zero_manager_side_effects(journey.transport)


# ---------------------------------------------------------------------------
# Scenario 2 — invalid phone: visible rejection, state retained, nothing durable
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(180)
async def test_invalid_phone_is_visibly_rejected_and_writes_nothing(
    journey: _FunnelJourney,
) -> None:
    client = journey.redis_client
    await _start_viewing_journey(journey, property_id="apt-3413-2")

    # Five digits: a phone attempt that fails validation.
    await journey.feed_message("12345")

    client_texts = journey.transport.texts_sent_to(journey.client_id)
    assert any(_PHONE_INVALID_TEXT in text for text in client_texts), client_texts

    # State is retained so the user can retry (cancellation still works).
    assert await journey.fsm().get_state() == _WAITING_PHONE_STATE

    # Sentinel: no durable writes, no manager side effects.
    await _assert_zero_durable_writes(client, journey.client_id)
    await _assert_zero_notify_state(client, journey.client_id)
    _assert_zero_manager_side_effects(journey.transport)


# ---------------------------------------------------------------------------
# Scenario 3 — phone + contact submissions: one v2 record each, manager
# notification, legacy read-only, E.164, no raw phone in logs
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(240)
async def test_phone_and_contact_submissions_create_distinct_v2_records_and_notify_manager(
    journey: _FunnelJourney,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client_id = journey.client_id
    client = journey.redis_client
    bot = journey.bot
    # Pre-existing legacy data must survive the whole journey untouched.
    legacy_fields = {"client_id": str(client_id), "phone": "+359885000002", "service_key": "rent"}
    await client.hset(f"lead_request:{client_id}", mapping=legacy_fields)
    with caplog.at_level(logging.INFO):
        # Submission 1: typed phone through the real FSM route.
        await _start_viewing_journey(journey, property_id="apt-3413-3")
        await journey.feed_message(_VALID_PHONE_RAW)

        client_texts = journey.transport.texts_sent_to(client_id)
        assert any(_VIEWING_SUCCESS_TEXT in text for text in client_texts), client_texts
        assert await journey.fsm().get_state() is None, "FSM must be cleared after success"

        # Submission 2: contact share — a NEW logical request, own id.
        await _start_viewing_journey(journey, property_id="apt-3413-3")
        await journey.feed_message(
            contact=Contact(phone_number=_CONTACT_PHONE_RAW, first_name="Тест")
        )

    # --- Durable records: two distinct v2 ids coexist -----------------------
    raw_v2 = await client.hgetall(f"lead_request:v2:{client_id}")
    assert len(raw_v2) == 2, sorted(raw_v2)
    records = [json.loads(value) for value in raw_v2.values()]
    assert sorted(r["phone"] for r in records) == [
        _VALID_PHONE_E164,
        _CONTACT_PHONE_E164,
    ]
    assert len({r["request_id"] for r in records}) == 2, "each logical request owns one id"

    # Required product-contract fields on the typed-phone record.
    typed = next(r for r in records if r["phone"] == _VALID_PHONE_E164)
    assert set(typed) == {
        "client_id",
        "request_id",
        "phone",
        "service_key",
        "username",
        "display_name",
        "viewing_objects",
        "date_range",
        "created_at",
    }
    assert typed["phone"] == _VALID_PHONE_E164, "raw input must be normalized to E.164"
    assert typed["service_key"] == "viewing"
    assert typed["client_id"] == str(client_id)
    assert typed["username"] == f"user{client_id}"
    assert typed["date_range"] == "nearest"
    assert typed["created_at"].isdigit()
    assert json.loads(typed["viewing_objects"]) == [
        {
            "id": "apt-3413-3",
            "complex_name": "Солнечный берег",
            "property_type": "2-спальни",
            "area_m2": 61,
            "price_eur": 89000,
        }
    ]

    # --- Manager notification: one topic + one message per request ---------
    assert len(journey.transport.calls_of("createForumTopic")) == 2
    manager_sends = journey.transport.manager_sends()
    assert len(manager_sends) == 2, manager_sends
    notification = str(manager_sends[0].payload["text"])
    assert notification.startswith("--- Новая заявка ---")
    assert f"Телефон: {_VALID_PHONE_E164}" in notification
    assert "Тип: viewing" in notification
    assert "Когда: ближайшие дни" in notification
    assert "id=apt-3413-3" in notification

    # Notification state: both requests acknowledged durably.
    notify_state = await client.hgetall(f"lead_notify:v2:{client_id}")
    assert len(notify_state) == 2
    assert all(json.loads(v)["status"] == "notified" for v in notify_state.values())
    assert all(json.loads(v)["notified"] is True for v in notify_state.values())

    # --- Legacy hash remained read-only -------------------------------------
    assert await client.hgetall(f"lead_request:{client_id}") == legacy_fields
    listed = await bot._lead_sink.list_requests(client_id)
    assert sorted(r["record_version"] for r in listed) == ["legacy", "v2", "v2"]

    # --- Privacy: raw phone values never reach application logs -------------
    log_text = caplog.text
    assert _VALID_PHONE_RAW not in log_text
    assert _VALID_PHONE_E164 not in log_text
    assert _CONTACT_PHONE_RAW not in log_text
    assert _CONTACT_PHONE_E164 not in log_text
    assert "phone_state=provided" in log_text, "journey must be observable without PII"


# ---------------------------------------------------------------------------
# Scenario 4 — same-request-id retry: no duplicate record, no replayed notification
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(240)
async def test_same_request_id_retry_does_not_duplicate_record_or_replay_notification(
    journey: _FunnelJourney,
) -> None:
    client_id = journey.client_id
    client = journey.redis_client
    bot = journey.bot
    await _start_viewing_journey(journey, property_id="apt-3413-4")
    await journey.feed_message(_VALID_PHONE_RAW)
    assert any(_VIEWING_SUCCESS_TEXT in t for t in journey.transport.texts_sent_to(client_id))

    raw_v2 = await client.hgetall(f"lead_request:v2:{client_id}")
    request_id = json.loads(raw_v2[_first_field(raw_v2)])["request_id"]
    topics_before = len(journey.transport.calls_of("createForumTopic"))
    manager_sends_before = len(journey.transport.manager_sends())

    # Retry the SAME logical request id at the durable sink boundary.
    assert await bot._lead_sink.record_request(
        client_id=client_id,
        request_id=request_id,
        phone="+359111222333",  # a later retry's kwargs must NOT win
        service_key="viewing",
    )

    # One record, unchanged payload (the first persisted write is authority).
    raw_v2_after = await client.hgetall(f"lead_request:v2:{client_id}")
    record_after = json.loads(raw_v2_after[_first_field(raw_v2_after)])
    assert record_after["request_id"] == request_id
    assert record_after["phone"] == _VALID_PHONE_E164, "retry kwargs must not rewrite the record"

    # No new topic, no replayed manager message.
    assert len(journey.transport.calls_of("createForumTopic")) == topics_before
    assert len(journey.transport.manager_sends()) == manager_sends_before
    notify_state = json.loads((await client.hgetall(f"lead_notify:v2:{client_id}"))[request_id])
    assert notify_state["status"] == "notified"


# ---------------------------------------------------------------------------
# Scenario 5 — persistence failure: no manager effect, no success copy;
# retry preserves the logical request id (#3322/#3477)
# ---------------------------------------------------------------------------


class _FailingPipeline:
    """Pipeline proxy whose execute() fails at the Redis transport boundary."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __getattr__(self, item: str) -> Any:
        return getattr(self._inner, item)

    async def execute(self) -> Any:
        raise ConnectionError("deterministic persistence outage")


class _PersistFailingRedis:
    """Redis proxy that fails exactly the sink's persistence pipelines."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def pipeline(self) -> _FailingPipeline:
        return _FailingPipeline(self._inner.pipeline())

    def __getattr__(self, item: str) -> Any:
        return getattr(self._inner, item)


@_MODULE_LOOP
@pytest.mark.timeout(240)
async def test_persistence_failure_blocks_manager_and_success_copy_retry_preserves_request_id(
    journey: _FunnelJourney,
) -> None:
    client_id = journey.client_id
    client = journey.redis_client
    bot = journey.bot
    await _start_viewing_journey(journey, property_id="apt-3413-5")

    # Inject persistence failure into the injected lead sink only: the
    # production sink class runs unmodified against a failing transport.
    failing_sink = bot._lead_sink.__class__(
        redis=_PersistFailingRedis(client),
        forum_bridge=bot._forum_bridge,
    )
    bot.dp["lead_sink"] = failing_sink
    try:
        await journey.feed_message(_VALID_PHONE_RAW)
    finally:
        bot.dp["lead_sink"] = bot._lead_sink

    # Truthful failure copy; FSM retained for retry.
    client_texts = journey.transport.texts_sent_to(client_id)
    assert any(t.startswith(_PHONE_FAILURE_PREFIX) for t in client_texts), client_texts
    assert not any(_VIEWING_SUCCESS_TEXT in t for t in client_texts)
    assert await journey.fsm().get_state() == _WAITING_PHONE_STATE

    # No durable write, no manager side effect.
    await _assert_zero_durable_writes(client, client_id)
    await _assert_zero_notify_state(client, client_id)
    _assert_zero_manager_side_effects(journey.transport)

    # The logical request id was generated once at the FSM boundary.
    fsm_data = await journey.fsm().get_data()
    request_id = fsm_data["lead_request_id"]
    assert request_id, fsm_data

    # Retry with the production sink: same id, one durable record.
    await journey.feed_message(_VALID_PHONE_RAW)

    raw_v2 = await client.hgetall(f"lead_request:v2:{client_id}")
    assert json.loads(raw_v2[_first_field(raw_v2)])["request_id"] == request_id
    assert any(_VIEWING_SUCCESS_TEXT in t for t in journey.transport.texts_sent_to(client_id))
    notify_state = json.loads((await client.hgetall(f"lead_notify:v2:{client_id}"))[request_id])
    assert notify_state["status"] == "notified"


# ---------------------------------------------------------------------------
# Scenario 6 — topic created, send fails: retry reuses the recorded topic
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(240)
async def test_manager_send_failure_after_topic_creation_reuses_topic_on_retry(
    journey: _FunnelJourney,
) -> None:
    client_id = journey.client_id
    client = journey.redis_client
    transport = journey.transport

    def _fail_group_sends(name: str, payload: dict[str, Any], method: Any) -> Exception | None:
        if name == "sendMessage" and payload.get("chat_id") == _MANAGERS_GROUP_ID:
            return TelegramServerError(method=method, message="deterministic forum outage")
        return None

    await _start_viewing_journey(journey, property_id="apt-3413-6")

    # Attempt 1: topic created, manager send fails -> truthful failure copy.
    transport.fail_when = _fail_group_sends
    await journey.feed_message(_VALID_PHONE_RAW)

    assert len(transport.calls_of("createForumTopic")) == 1
    client_texts = transport.texts_sent_to(client_id)
    assert any(t.startswith(_PHONE_FAILURE_PREFIX) for t in client_texts), client_texts
    assert not any(_VIEWING_SUCCESS_TEXT in t for t in client_texts)
    # The record itself persisted; only the notification is pending.
    raw_v2 = await client.hgetall(f"lead_request:v2:{client_id}")
    request_id = json.loads(raw_v2[_first_field(raw_v2)])["request_id"]
    notify_state = json.loads((await client.hgetall(f"lead_notify:v2:{client_id}"))[request_id])
    recorded_topic_id = notify_state["topic_id"]
    assert isinstance(recorded_topic_id, int)
    assert await journey.fsm().get_state() == _WAITING_PHONE_STATE

    # Attempt 2: transport healed — the recorded topic is resumed.
    transport.fail_when = None
    await journey.feed_message(_VALID_PHONE_RAW)

    assert len(transport.calls_of("createForumTopic")) == 1, "topic must never be re-created"
    manager_sends = transport.manager_sends()
    assert len(manager_sends) == 2, manager_sends
    assert all(c.payload.get("message_thread_id") == recorded_topic_id for c in manager_sends)
    assert any(_VIEWING_SUCCESS_TEXT in t for t in transport.texts_sent_to(client_id))
    healed_state = json.loads((await client.hgetall(f"lead_notify:v2:{client_id}"))[request_id])
    assert healed_state["status"] == "notified"
    assert healed_state["topic_id"] == recorded_topic_id
