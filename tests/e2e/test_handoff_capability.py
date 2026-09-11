"""Live handoff E2E: capability gating and forum handoff lifecycle (#3420).

Proves the manager forum-handoff journey end-to-end through the REAL
registered routes: ``Dispatcher.feed_update`` drives actual Updates through
the production middlewares, the aiogram-dialog qualification router
(``HandoffSG``), the production :class:`~src.services.handoff_state.HandoffState`
machine backed by a REAL Redis server, and the production
:class:`~telegram_bot.services.forum_bridge.ForumBridge` on top of a
deterministic in-process Telegram forum transport (the real aiogram client
stack with a recorded ``BaseSession``). No production credential, no paid
provider, no fake SDK packages (#3414 A11: direct ``ForumBridge`` mock calls
are unit tests — this lane pins Dispatcher-level linkage).

Stack scoping follows the proven #3413 conventions: the handoff journey
never touches retrieval (Qdrant/BGE-M3/LLM) or PostgreSQL, so the lane runs
against ONE real dependency — Redis — provided as a disposable,
authenticated container per module (#3368 conventions: unique name,
ephemeral host port, random password, no persistence, removed and proven
gone on teardown). Required mode (``E2E_HARNESS_REQUIRED=1``, legacy
``E2E_CORE_STRICT=1``) turns a missing Docker daemon into a FAILURE, never
a skip.

Scenarios (issue #3420 acceptance):

1. Capability gating per the #3354/#3362 Redis contract:
   ``disabled`` mode cannot combine with ``HANDOFF_ENABLED`` at config time,
   and a disabled-mode bot answers the manager button through the real
   dispatcher route with the durable phone-request fallback (#3213) — zero
   forum effects, zero durable handoff state. ``multi_instance`` keeps the
   durable handoff capability enabled against the real server (multi requires
   a Redis URL; handoff state is exactly the shared durable state the mode
   exists for). Polling-lock/owner topology is the #3368 lane's contract.
2. Qualification (menu button → goal → chat contact) starts the handoff,
   stores run-owned state under ``handoff:{client}`` + ``topic_map:{topic}``,
   creates the manager topic exactly once, and a duplicate manager-button
   update is idempotent (FSM re-entry guard, no second topic).
3. Manager reply linkage: a manager message in the topic transitions
   ``human_waiting → human`` and is relayed to the originating client.
4. Client message linkage + state-loss safety: after an FSM state loss
   (production restarts drop MemoryStorage while Redis handoff state
   survives), the client's message is relayed to the topic and the agent
   pipeline stays short-circuited (no ``sendChatAction``).
5. Close lifecycle: ``/close`` in the topic clears both durable keys, closes
   the topic, notifies the client; a duplicate ``/close`` update is
   idempotent (guarded delete, #3487).
6. Setup failure recovery (#3488): a context-pack failure after topic
   creation compensates the orphaned topic, shows truthful failure copy, and
   a retry starts a clean session.
7. Stale topic protection (#3487): re-qualification with a deleted topic
   replaces the session, drops the stale reverse mapping, and messages in
   the dead topic never resolve to the client.

Rollback (#3420): purge exactly the run-owned keys ``handoff:{client}`` and
``topic_map:{topic}`` recorded by each journey; the disposable container is
removed whole.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
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
from aiogram.types import CallbackQuery, Chat, ForumTopicCreated, Message, Update, User
from pydantic import ValidationError

from src.runtime.integrations.cache import CacheLayerManager
from src.runtime.integrations.redis_mode import RedisCapability, RedisMode
from tests.e2e_core.live_harness import guard_service_skip
from tests.unit._bot_config_factory import make_full_bot_config
from tests.unit._property_bot_factory import make_property_bot


pytestmark = [pytest.mark.e2e, pytest.mark.requires_services]

# The journey paces its feeds to stay above the production throttling rates
# (1.0 s per user for messages, 0.3 s for callbacks) instead of exempting the
# test user: the throttling middleware stays on the real path. The catch-all
# query handler uses its own 2.0 s bucket, so each journey feeds at most one
# free-text query.
_MESSAGE_PACE_S = 1.05
_CALLBACK_PACE_S = 0.35

_MANAGER_MENU_TEXT = "👤 Связаться с менеджером"
_GOAL_PROMPT = "📋 Какая тема вас интересует?"
_CONTACT_PROMPT = "Какой способ связи предпочитаете?"
_ALREADY_CONNECTED_REPLY = "Вы уже на связи с менеджером, ожидайте ответа 💬"
_HANDOFF_FAILURE_PREFIX = "⚠️ Не удалось передать ваш запрос менеджеру"
_CONTEXT_PACK_PREFIX = "--- Новый клиент ---"
_CONNECTED_NOTICE_PREFIX = "🟢 "
_CLOSE_CLIENT_NOTICE = "Диалог с менеджером завершён"
_CANCEL_NOTICE = "😊 Заявка отменена"
_PHONE_FALLBACK_PROMPT = "📞 Оставьте номер телефона"

_WAITING_PHONE_STATE = "PhoneCollectorStates:waiting_phone"
_HANDOFF_ACTIVE_STATE = "HandoffStates:active"

_MANAGERS_GROUP_ID = -100_3420_0001
_MANAGER_USER_ID = 34_209_001
_BOT_TOKEN = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"

_MODULE_LOOP = pytest.mark.asyncio(loop_scope="module")

# Topic ids land in the durable reverse map (topic_map:{id}), so they must be
# unique for the whole pytest process, across every journey and session.
_TOPIC_ID_SEQUENCE = itertools.count(3_420_5000)


# ---------------------------------------------------------------------------
# Disposable authenticated Redis container (#3368/#3413 conventions)
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


async def _wait_until_ready(live: LiveRedis, ready_deadline_s: float = 30.0) -> None:
    """Block until the disposable server answers PING (#3368 conventions).

    The host port is published before ``redis-server`` starts listening, so
    building the bot immediately after ``docker port`` races the startup.
    """
    deadline = time.monotonic() + ready_deadline_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            client = aioredis.from_url(live.url, decode_responses=True, socket_connect_timeout=2)
            try:
                # redis-py ping is a sync/async union type (#3362 seam convention).
                await client.ping()  # type: ignore[misc]
            finally:
                await client.aclose()
            return
        except Exception as error:  # readiness probe — retried until the deadline
            last_error = error
            await asyncio.sleep(0.2)
    raise RuntimeError(f"disposable Redis {live.name} never became ready: {last_error}")


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def handoff_stack() -> AsyncIterator[tuple[Any, LiveRedis]]:
    """One assembled single-instance bot + one disposable Redis for the module."""
    if not _docker_daemon_available():
        guard_service_skip("Docker daemon unavailable — handoff live harness cannot start")
    name = f"rag-e2e-3420-{uuid.uuid4().hex[:10]}"
    password = f"pw-{uuid.uuid4().hex}"
    live: LiveRedis | None = None
    bot: Any = None
    try:
        port = _start_redis_container(name, password)
        live = LiveRedis(name=name, password=password, port=port)
        await _wait_until_ready(live)
        bot = await _build_handoff_bot(live)
        yield bot, live
    finally:
        if bot is not None:
            with contextlib.suppress(Exception):
                await bot._cache.close()
        if live is not None:
            _docker("rm", "-f", name)
        assert _container_gone(name), f"disposable Redis container {name} survived cleanup"


_CLIENT_ID_SEQUENCE = iter(range(3420_0001, 3420_0001 + 100))


@pytest.fixture(autouse=True)
def _deterministic_business_hours(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the business-hours gate to in-hours for every journey.

    The real zoneinfo database is not available on Windows (tzdata is not a
    dependency), so ``is_business_hours`` cannot resolve any IANA key — the
    same documented limitation as the unit recovery lane
    (tests/unit/handlers/test_handoff_recovery.py). Pinning it keeps the
    qualification completion path pristine and deterministic; the hours math
    itself is owned by the unit lane.
    """
    monkeypatch.setattr(
        "telegram_bot.handlers.bot_handoff.is_business_hours", lambda **_kwargs: True
    )


@pytest_asyncio.fixture(loop_scope="module")
async def journey(handoff_stack: tuple[Any, LiveRedis]) -> AsyncIterator[_HandoffJourney]:
    """One client's journey: fresh transport, unique id, exact key cleanup."""
    bot, live = handoff_stack
    # A fresh recorded session per test keeps side-effect counts absolute.
    bot.bot.session = RecordingTelegramSession()
    client = aioredis.from_url(live.url, decode_responses=True)
    current = _HandoffJourney(bot, bot.bot.session, next(_CLIENT_ID_SEQUENCE))
    current.redis_client = client
    try:
        yield current
    finally:
        await _purge_journey_keys(client, current)
        await client.aclose()


async def _purge_journey_keys(client: aioredis.Redis, journey: _HandoffJourney) -> None:
    """Rollback (#3420): purge exactly this journey's run-owned keys."""
    keys = [f"handoff:{journey.client_id}"]
    keys += [f"topic_map:{topic_id}" for topic_id in journey.transport.topic_ids()]
    if keys:
        await client.delete(*keys)
    for key in keys:
        assert await client.exists(key) == 0, f"run-owned key survived rollback: {key}"


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
    """In-process Telegram/forum transport for the handoff journey.

    Every ``make_request`` is recorded (method name, payload, canned result)
    so tests assert real side effects at the transport boundary. Selected
    methods can be made to fail deterministically via :attr:`fail_when`, and
    :attr:`dead_topics` emulates topics deleted on the Telegram side (a send
    into a dead topic lands in General, i.e. returns a message whose thread
    id no longer matches, exactly like the production ``send_to_topic``
    contract).
    """

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramCall] = []
        self._next_message_id = 20_000
        self.fail_when: Callable[[str, dict[str, Any], Any], Exception | None] | None = None
        self.dead_topics: set[int] = set()

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
        raise NotImplementedError("the handoff journey never downloads files")
        yield b""  # pragma: no cover

    def calls_of(self, method: str) -> list[TelegramCall]:
        return [call for call in self.calls if call.method == method]

    def topic_ids(self) -> list[int]:
        return [
            int(call.result.message_thread_id)
            for call in self.calls_of("createForumTopic")
            if call.result is not None
        ]

    def texts_sent_to(self, chat_id: int) -> list[str]:
        return [
            str(call.payload.get("text") or "")
            for call in self.calls_of("sendMessage")
            if call.payload.get("chat_id") == chat_id
        ]

    def surface_texts_for(self, chat_id: int) -> list[str]:
        """All client-visible texts across sendMessage and editMessageText."""
        texts = list(self.texts_sent_to(chat_id))
        texts += [
            str(call.payload.get("text") or "")
            for call in self.calls_of("editMessageText")
            if call.payload.get("chat_id") == chat_id
        ]
        return texts

    def group_sends(self) -> list[TelegramCall]:
        return [
            call
            for call in self.calls_of("sendMessage")
            if call.payload.get("chat_id") == _MANAGERS_GROUP_ID
        ]

    def copies_to(self, chat_id: int) -> list[TelegramCall]:
        return [
            call for call in self.calls_of("copyMessage") if call.payload.get("chat_id") == chat_id
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
            thread_id = payload.get("message_thread_id")
            if thread_id is not None and int(thread_id) in self.dead_topics:
                # A send into a deleted topic lands in General (#3488 contract).
                thread_id = None
            result = Message(
                message_id=self._next_message_id,
                date=datetime.now(UTC),
                chat=Chat(id=chat_id, type="supergroup" if chat_id < 0 else "private"),
                text=payload.get("text"),
                message_thread_id=thread_id,
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
            result = ForumTopicCreated(
                message_thread_id=next(_TOPIC_ID_SEQUENCE),
                name=str(payload.get("name") or ""),
                icon_color=0x6FB9F0,
            )
        self.calls.append(TelegramCall(method=name, payload=payload, result=result))
        return result


# ---------------------------------------------------------------------------
# Journey assembly: production lifecycle over real Redis + recorded transport
# ---------------------------------------------------------------------------


class _HandoffJourney:
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

    def _build_message(self, **kwargs: Any) -> Message:
        self._next_update_id += 1
        return Message(
            message_id=self._next_update_id,
            date=datetime.now(UTC),
            from_user=kwargs.get("from_user", self._journey_user()),
            **{key: value for key, value in kwargs.items() if key != "from_user"},
        )

    async def feed_update(self, update: Update) -> None:
        await self.bot.dp.feed_update(self.bot.bot, update)

    async def feed_client_message(self, text: str | None = None, **kwargs: Any) -> Update:
        await asyncio.sleep(_MESSAGE_PACE_S)
        message = self._build_message(
            chat=Chat(id=self.client_id, type="private"),
            text=text,
            **kwargs,
        )
        update = Update(update_id=self._next_update_id, message=message)
        await self.feed_update(update)
        return update

    async def feed_client_callback(self, data: str) -> None:
        await asyncio.sleep(_CALLBACK_PACE_S)
        self._next_update_id += 1
        update = Update(
            update_id=self._next_update_id,
            callback_query=CallbackQuery(
                id=str(self._next_update_id),
                from_user=self._journey_user(),
                chat_instance="handoff-e2e",
                data=data,
                message=Message(
                    message_id=1,
                    date=datetime.now(UTC),
                    chat=Chat(id=self.client_id, type="private"),
                ),
            ),
        )
        await self.feed_update(update)

    async def feed_manager_message(self, text: str | None, topic_id: int) -> Update:
        """A manager's message inside one forum topic of the managers group."""
        await asyncio.sleep(_MESSAGE_PACE_S)
        manager = User(
            id=_MANAGER_USER_ID,
            is_bot=False,
            first_name="Мария",
            last_name="Менеджер",
            username="manager",
            language_code="ru",
        )
        message = self._build_message(
            from_user=manager,
            chat=Chat(id=_MANAGERS_GROUP_ID, type="supergroup"),
            text=text,
            message_thread_id=topic_id,
        )
        update = Update(update_id=self._next_update_id, message=message)
        await self.feed_update(update)
        return update

    def fsm(self) -> FSMContext:
        return FSMContext(
            storage=self.bot.dp.storage,
            key=StorageKey(bot_id=self.bot.bot.id, chat_id=self.client_id, user_id=self.client_id),
        )

    async def handoff_state_raw(self) -> dict[str, str]:
        raw: dict[str, str] = await self.redis_client.hgetall(  # type: ignore[misc]
            f"handoff:{self.client_id}"
        )
        return raw

    async def topics(self) -> list[int]:
        return self.transport.topic_ids()


async def _qualify(journey: _HandoffJourney) -> int:
    """Manager button → goal → chat contact through the real routes."""
    await journey.feed_client_message(_MANAGER_MENU_TEXT)
    await journey.feed_client_callback("handoff_goal:consult")
    await journey.feed_client_callback("handoff_contact_chat")
    topics = await journey.topics()
    assert len(topics) == 1, f"qualification must create exactly one topic, got {topics}"
    return topics[0]


def _build_config(live_redis: LiveRedis) -> Any:
    return make_full_bot_config(
        telegram_token=_BOT_TOKEN,
        redis_url=live_redis.url,
        redis_mode="single_instance",
        handoff_enabled=True,
        managers_group_id=_MANAGERS_GROUP_ID,
    )


async def _build_handoff_bot(live_redis: LiveRedis) -> Any:
    """Assemble the production single-instance bot over real Redis."""
    cache = CacheLayerManager(redis_url=live_redis.url, mode=RedisMode.SINGLE_INSTANCE)
    await cache.initialize()
    config = _build_config(live_redis)
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
    assert bot._handoff_state is not None, "production lifecycle must wire the handoff state"
    assert bot._forum_bridge is not None, "managers group must wire the forum bridge"
    assert bot.forum_handoff_available, "single-instance capability must be enabled"
    return bot


async def _assemble_capability_bot(live_redis: LiveRedis | None, *, mode: RedisMode) -> Any:
    """Assemble a bot for one capability probe (disabled or multi_instance).

    aiogram-dialog routers are module singletons attachable to exactly one
    dispatcher per process (they are already owned by the module-scoped
    single-instance bot), so capability probes skip ``_setup_dialogs``: the
    gated routes they prove (phone fallback, durable wiring) never reach the
    dialog layer.
    """
    redis_url = live_redis.url if live_redis is not None else "redis://localhost:6379/0"
    cache = CacheLayerManager(redis_url=redis_url, mode=mode)
    await cache.initialize()
    config = make_full_bot_config(
        telegram_token=_BOT_TOKEN,
        redis_url=redis_url,
        redis_mode=mode.value,
        handoff_enabled=(mode is not RedisMode.DISABLED),
        managers_group_id=_MANAGERS_GROUP_ID,
    )
    bot = make_property_bot(
        config,
        service_overrides={"cache": cache, "apartments_service": None},
    )
    bot.bot = Bot(token=_BOT_TOKEN, session=RecordingTelegramSession())
    bot._setup_handoff_services()
    bot._setup_workflow_data()
    return bot


# ---------------------------------------------------------------------------
# Scenario 1 — disabled mode: config contract + dispatcher-level fallback
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(120)
async def test_disabled_mode_blocks_handoff_config_and_falls_back_to_phone_sink() -> None:
    # Config contract (#3362): disabled mode cannot run an explicitly enabled
    # Redis-only durable feature — the error surfaces before polling starts.
    # BotConfig wraps the RedisModeConfigError into a ValidationError (#3362
    # convention, see tests/unit/test_config_handoff.py).
    with pytest.raises(ValidationError, match="REDIS_MODE=disabled cannot run"):
        make_full_bot_config(
            redis_mode="disabled",
            handoff_enabled=True,
            managers_group_id=_MANAGERS_GROUP_ID,
        )

    bot = await _assemble_capability_bot(None, mode=RedisMode.DISABLED)
    try:
        # Honest degraded wiring (#3354): no client, no durable substitutes.
        assert bot._cache.capability == RedisCapability.DISABLED
        assert bot._cache.redis is None
        bot._setup_handoff_services()
        assert bot._handoff_state is None, "disabled mode must not build handoff state"
        assert bot._forum_bridge is None, "disabled mode must not build the forum bridge"
        assert bot._lead_sink is None
        assert bot.forum_handoff_available is False

        # The real dispatcher route: the manager button cannot start the
        # forum handoff and degrades to the durable phone-request sink.
        journey = _HandoffJourney(bot, bot.bot.session, next(_CLIENT_ID_SEQUENCE))
        await journey.feed_client_message(_MANAGER_MENU_TEXT)

        texts = journey.transport.texts_sent_to(journey.client_id)
        assert any(_PHONE_FALLBACK_PROMPT in text for text in texts), texts
        assert await journey.fsm().get_state() == _WAITING_PHONE_STATE
        assert journey.transport.calls_of("createForumTopic") == []
        assert journey.transport.calls_of("copyMessage") == []
        assert journey.transport.group_sends() == []
    finally:
        with contextlib.suppress(Exception):
            await bot._cache.close()


# ---------------------------------------------------------------------------
# Scenario 2 — multi_instance mode keeps the durable handoff capability
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(180)
async def test_multi_instance_mode_keeps_durable_handoff_capability(
    handoff_stack: tuple[Any, LiveRedis],
) -> None:
    _, live = handoff_stack

    # Mode contract: multi_instance without a Redis URL is a config error —
    # shared durable state (the handoff state machine) is the point of multi.
    with pytest.raises(ValidationError, match="requires a nonempty REDIS_URL"):
        make_full_bot_config(redis_mode="multi_instance", redis_url="")

    bot = await _assemble_capability_bot(live, mode=RedisMode.MULTI_INSTANCE)
    try:
        assert bot._cache.capability == RedisCapability.ENABLED
        assert bot._cache.redis is not None
        bot._setup_handoff_services()
        assert bot._handoff_state is not None, "multi mode requires the shared handoff state"
        assert bot._forum_bridge is not None
        assert bot.forum_handoff_available is True

        # The production state machine works against the REAL shared server;
        # a fresh client has no session (read-only probe, no residue).
        fresh_client_id = next(_CLIENT_ID_SEQUENCE)
        assert await bot._handoff_state.get_by_client(fresh_client_id) is None
    finally:
        with contextlib.suppress(Exception):
            await bot._cache.close()


# ---------------------------------------------------------------------------
# Scenario 3 — qualification: run-owned state, one topic, idempotent duplicate
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(240)
async def test_qualification_stores_run_state_creates_topic_once_and_guards_reentry(
    journey: _HandoffJourney,
) -> None:
    client_id = journey.client_id
    client = journey.redis_client

    await journey.feed_client_message(_MANAGER_MENU_TEXT)
    surface = journey.transport.surface_texts_for(client_id)
    assert any(_GOAL_PROMPT in text for text in surface), surface

    await journey.feed_client_callback("handoff_goal:consult")
    surface = journey.transport.surface_texts_for(client_id)
    assert any(_CONTACT_PROMPT in text for text in surface), surface

    await journey.feed_client_callback("handoff_contact_chat")

    # One topic, one context pack in it.
    topics = await journey.topics()
    assert len(topics) == 1, topics
    topic_id = topics[0]
    group_sends = journey.transport.group_sends()
    assert len(group_sends) == 1, group_sends
    assert group_sends[0].payload.get("message_thread_id") == topic_id
    assert str(group_sends[0].payload.get("text") or "").startswith(_CONTEXT_PACK_PREFIX)
    topic_name = str(journey.transport.calls_of("createForumTopic")[0].payload["name"])
    assert "Тест Клиент" in topic_name, topic_name

    # Run-owned durable state: forward hash + reverse topic mapping + TTL.
    raw = await journey.handoff_state_raw()
    assert int(raw["client_id"]) == client_id
    assert int(raw["topic_id"]) == topic_id
    assert raw["mode"] == "human_waiting"
    assert raw["manager_joined_at"] == ""
    assert json.loads(raw["qualification"]) == {"goal": "consult", "contact": "chat"}
    assert await client.ttl(f"handoff:{client_id}") > 0, "handoff state must be ephemeral"
    assert await client.get(f"topic_map:{topic_id}") == str(client_id)

    # FSM sentinel: the qualification re-entry guard is armed.
    assert await journey.fsm().get_state() == _HANDOFF_ACTIVE_STATE

    # A duplicate manager-button update is idempotent: informational reply,
    # no second dialog render, no second topic, state untouched.
    await journey.feed_client_message(_MANAGER_MENU_TEXT)
    assert await journey.topics() == topics, "duplicate update must not create a topic"
    surface = journey.transport.surface_texts_for(client_id)
    assert any(_ALREADY_CONNECTED_REPLY in text for text in surface), surface
    assert (await journey.handoff_state_raw())["topic_id"] == str(topic_id)


# ---------------------------------------------------------------------------
# Scenario 4 — relay linkage: manager reply → client; client message → topic
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(240)
async def test_manager_reply_reaches_client_and_client_message_reaches_topic(
    journey: _HandoffJourney,
) -> None:
    client_id = journey.client_id
    client = journey.redis_client
    topic_id = await _qualify(journey)

    # Manager joins the topic: mode transition + relay to the client.
    await journey.feed_manager_message("Здравствуйте! Чем могу помочь?", topic_id)

    raw = await journey.handoff_state_raw()
    assert raw["mode"] == "human", "first manager message must transition to human"
    assert raw["manager_joined_at"] != ""
    assert await client.ttl(f"handoff:{client_id}") > 0

    texts = journey.transport.texts_sent_to(client_id)
    assert any(t.startswith(_CONNECTED_NOTICE_PREFIX) for t in texts), texts
    copies = journey.transport.copies_to(client_id)
    assert len(copies) == 1, copies
    assert copies[0].payload["from_chat_id"] == _MANAGERS_GROUP_ID
    assert copies[0].payload["message_id"] == journey._next_update_id

    # State-loss safety: a production restart wipes MemoryStorage FSM while
    # the durable Redis session survives. The client's message must still
    # reach the topic through the catch-all handoff gate.
    await journey.fsm().set_state(None)

    client_sends_before = len(journey.transport.texts_sent_to(client_id))
    await journey.feed_client_message("Спасибо! Подскажите по документам")

    relayed = journey.transport.copies_to(_MANAGERS_GROUP_ID)
    assert len(relayed) == 1, relayed
    assert relayed[0].payload["from_chat_id"] == client_id
    assert relayed[0].payload["message_id"] == journey._next_update_id
    assert relayed[0].payload["message_thread_id"] == topic_id

    # Dispatcher sentinel: the relay short-circuits the agent pipeline —
    # the production pipeline always raises a typing action first.
    assert journey.transport.calls_of("sendChatAction") == [], (
        "relayed client message must never reach the agent pipeline"
    )
    # No bot answer on top of the relay.
    assert len(journey.transport.texts_sent_to(client_id)) == client_sends_before
    # The durable session is untouched by the relay.
    assert (await journey.handoff_state_raw())["mode"] == "human"


# ---------------------------------------------------------------------------
# Scenario 5 — close lifecycle: state cleared, duplicate close idempotent
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(240)
async def test_close_clears_state_and_duplicate_close_is_idempotent(
    journey: _HandoffJourney,
) -> None:
    client_id = journey.client_id
    client = journey.redis_client
    topic_id = await _qualify(journey)
    await journey.feed_manager_message("Здравствуйте!", topic_id)

    await journey.feed_manager_message("/close", topic_id)

    # Both durable keys cleared.
    assert await journey.handoff_state_raw() == {}
    assert await client.get(f"topic_map:{topic_id}") is None

    # Topic closed and the client informed.
    closes = journey.transport.calls_of("closeForumTopic")
    assert [c.payload.get("message_thread_id") for c in closes] == [topic_id]
    assert any(_CLOSE_CLIENT_NOTICE in t for t in journey.transport.texts_sent_to(client_id))
    assert await journey.fsm().get_state() is None

    def _client_notice_count() -> int:
        return sum(
            1 for t in journey.transport.texts_sent_to(client_id) if _CLOSE_CLIENT_NOTICE in t
        )

    notices_before = _client_notice_count()
    closes_before = len(journey.transport.calls_of("closeForumTopic"))

    # Duplicate /close update: the guarded delete (#3487) finds no session —
    # the repeat must be a no-op with zero duplicated notifications.
    await journey.feed_manager_message("/close", topic_id)

    assert len(journey.transport.calls_of("closeForumTopic")) == closes_before
    assert _client_notice_count() == notices_before
    assert await journey.handoff_state_raw() == {}
    assert await client.get(f"topic_map:{topic_id}") is None


# ---------------------------------------------------------------------------
# Scenario 6 — setup failure recovery (#3488): orphan compensation + retry
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(240)
async def test_setup_failure_compensates_orphan_topic_and_retry_recovers(
    journey: _HandoffJourney,
) -> None:
    client_id = journey.client_id
    client = journey.redis_client
    transport = journey.transport

    def _fail_context_pack(name: str, payload: dict[str, Any], method: Any) -> Exception | None:
        if (
            name == "sendMessage"
            and payload.get("chat_id") == _MANAGERS_GROUP_ID
            and str(payload.get("text") or "").startswith(_CONTEXT_PACK_PREFIX)
        ):
            return TelegramServerError(method=method, message="deterministic forum outage")
        return None

    # Attempt 1: topic created, context pack fails → compensate the orphan.
    transport.fail_when = _fail_context_pack
    await journey.feed_client_message(_MANAGER_MENU_TEXT)
    await journey.feed_client_callback("handoff_goal:consult")
    await journey.feed_client_callback("handoff_contact_chat")
    transport.fail_when = None

    orphan_topics = await journey.topics()
    assert len(orphan_topics) == 1, "the orphan topic was created before the failure"
    closes = [c.payload.get("message_thread_id") for c in transport.calls_of("closeForumTopic")]
    assert closes == orphan_topics, closes

    surface = transport.surface_texts_for(client_id)
    assert any(t.startswith(_HANDOFF_FAILURE_PREFIX) for t in surface), surface
    assert await journey.handoff_state_raw() == {}
    assert await client.get(f"topic_map:{orphan_topics[0]}") is None
    assert await journey.fsm().get_state() is None, "failed setup must not arm the FSM guard"

    # Attempt 2: transport healed — a clean new session starts.
    await journey.feed_client_message(_MANAGER_MENU_TEXT)
    await journey.feed_client_callback("handoff_goal:consult")
    await journey.feed_client_callback("handoff_contact_chat")

    topics = await journey.topics()
    assert len(topics) == 2, topics
    assert topics[1] != orphan_topics[0]
    raw = await journey.handoff_state_raw()
    assert int(raw["topic_id"]) == topics[1]
    assert raw["mode"] == "human_waiting"
    assert await client.get(f"topic_map:{topics[1]}") == str(client_id)
    assert await journey.fsm().get_state() == _HANDOFF_ACTIVE_STATE


# ---------------------------------------------------------------------------
# Scenario 7 — stale topic protection (#3487): replace + dead-topic isolation
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(240)
async def test_stale_topic_is_replaced_and_old_topic_is_protected(
    journey: _HandoffJourney,
) -> None:
    client_id = journey.client_id
    client = journey.redis_client
    transport = journey.transport

    old_topic = await _qualify(journey)

    # The old topic dies on the Telegram side; the client cancels the FSM
    # (production cancel route) — the durable session must survive the FSM
    # cancel and then be replaced, not reused, on re-qualification.
    transport.dead_topics.add(old_topic)
    await journey.feed_client_message("отмена")
    assert any(_CANCEL_NOTICE in t for t in transport.texts_sent_to(client_id))
    assert await journey.fsm().get_state() is None
    raw = await journey.handoff_state_raw()
    assert int(raw["topic_id"]) == old_topic, "cancel clears FSM, never the durable session"

    # Re-qualification: the stale topic is detected as dead and replaced.
    await journey.feed_client_message(_MANAGER_MENU_TEXT)
    await journey.feed_client_callback("handoff_goal:consult")
    await journey.feed_client_callback("handoff_contact_chat")

    topics = await journey.topics()
    assert len(topics) == 2, topics
    new_topic = topics[1]
    raw = await journey.handoff_state_raw()
    assert int(raw["topic_id"]) == new_topic
    assert raw["mode"] == "human_waiting"
    # The stale reverse mapping is gone; the new one resolves (#3487).
    assert await client.get(f"topic_map:{old_topic}") is None
    assert await client.get(f"topic_map:{new_topic}") == str(client_id)
    assert await journey.fsm().get_state() == _HANDOFF_ACTIVE_STATE

    # A manager message in the DEAD topic must never resolve to the client.
    await journey.feed_manager_message("Клиент здесь?", old_topic)
    assert transport.copies_to(client_id) == []
    assert not any(
        t.startswith(_CONNECTED_NOTICE_PREFIX) for t in transport.texts_sent_to(client_id)
    )
    assert (await journey.handoff_state_raw())["mode"] == "human_waiting"

    # The replaced session stays fully live in its own topic.
    await journey.feed_manager_message("Здравствуйте, это менеджер!", new_topic)
    copies = transport.copies_to(client_id)
    assert len(copies) == 1, copies
    assert copies[0].payload["from_chat_id"] == _MANAGERS_GROUP_ID
    assert (await journey.handoff_state_raw())["mode"] == "human"
