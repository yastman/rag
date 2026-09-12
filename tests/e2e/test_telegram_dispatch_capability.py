"""Telegram dispatch E2E: commands, text, and callbacks through real aiogram routing (#3419).

Proves the bot's ROUTING surface end to end: a synthetic aiogram ``Update``
enters the real ``Dispatcher.feed_update`` and must traverse the production
middleware stack (the lane's E2E sentinel middleware records every event that
reaches the chain — a direct handler invocation can never satisfy it), the
registered routers (commands router, aiogram-dialog routers, the catch-all
query route), FSM, and the production supervisor
(``telegram_bot.pipeline.supervisor``) through the assistant-core adapter into
live BGE-M3/Qdrant (the #3421 harness stack). Every user-visible effect is
observed at the transport boundary on a deterministic in-process Telegram
transport (the real aiogram client stack with a recorded ``BaseSession``) —
no production credential, no paid provider, no fake SDK packages.

Stack scoping follows the proven #3413/#3417/#3420 conventions: the free-text
journey needs real retrieval (Qdrant + BGE-M3) plus Redis for the bot
cache/FSM, so the lane runs against the hermetic harness services (#3414) and
ONE disposable, authenticated Redis container per module (#3368 conventions:
unique name, ephemeral host port, random password, no persistence, removed
and proven gone on teardown). Required mode (``E2E_HARNESS_REQUIRED=1``,
legacy ``E2E_CORE_STRICT=1``) turns missing infrastructure into a FAILURE,
never a skip.

Unique routing ground (not covered by the merged #3413/#3417/#3420/#3421
lanes): the free-text catch-all → supervisor → core path, the commands router
(``/start``), the feedback callback family closed out of a REAL response's
inline keyboard, the dispatcher-owned absorption of a repeated update id, and
the safe dependency-failure response through the production error surfaces.

Scenarios (issue #3419 acceptance):

1. ``/start`` selects the commands router and answers exactly once with the
   client root keyboard — zero core invocation (no generation, no rewrite).
2. Known text after ``/start`` traverses the catch-all into ONE assistant-core
   call and answers exactly once with correct chat linkage; the response
   carries the feedback inline keyboard keyed by the real core request id;
   known corpus facts are present and unrelated ones absent (golden case via
   the live BGE/Qdrant/core path).
3. Unsupported text gets the truthful no-claim answer — no fabrication.
4. The representative callback (the response's own ``fb:like`` button) fed
   back through the real dispatcher is acknowledged and the keyboard becomes
   the confirmation — the feedback family routes without touching the core.
5. A dead Qdrant backend yields the canonical safe service-unavailable text
   exactly once — zero generation calls, and NOT the dispatcher error text
   (the core owns the failure, safely).
6. A repeated update id (the same update delivered twice while the first is
   still in flight) is absorbed by the production throttling middleware:
   exactly one answer, exactly one core call, one truthful throttle notice.

The bot is assembled once per module: aiogram-dialog routers are module
singletons, so a dispatcher can attach them exactly once per process
(production runs one bot per process). Per-test isolation comes from a fresh
transport session, a unique client id (FSM/throttle/Redis namespaces) and the
whole-container Redis teardown.

Rollback (#3419): test-only — the disposable container is removed whole and
the run-owned Qdrant collection is dropped and proven gone by the harness
registry; no external cleanup exists.
"""

from __future__ import annotations

import asyncio
import contextlib
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
from aiogram import BaseMiddleware, Bot
from aiogram.client.session.base import BaseSession
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from src.runtime.integrations.cache import CacheLayerManager
from src.runtime.integrations.redis_mode import RedisMode
from src.runtime.services.qdrant import QdrantService
from tests.e2e_core.live_harness import (
    FakeLLMConfig,
    LiveBGEEmbeddings,
    LiveBGESparseEmbeddings,
    LiveE2EEnv,
    RunNamespace,
    TeardownRegistry,
    guard_service_skip,
    index_fixture_documents,
    load_golden_case,
    recreate_collection,
    require_live_services,
)
from tests.unit._bot_config_factory import make_full_bot_config
from tests.unit._property_bot_factory import make_property_bot


pytestmark = [pytest.mark.e2e, pytest.mark.requires_services]

# The journey paces its feeds to stay above the production throttling rates
# (1.0 s per user for messages, 0.3 s for callbacks) instead of exempting the
# test user: the throttling middleware stays on the real path. The catch-all
# query handler uses its own 2.0 s bucket.
_MESSAGE_PACE_S = 1.05
_CALLBACK_PACE_S = 0.35

_BOT_TOKEN = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"

# Canonical user-visible texts (production surfaces this lane must observe).
_THROTTLE_NOTICE = "⏱ Слишком частые запросы. Подождите немного."
_DISPATCH_ERROR_TEXT = "❌ Произошла ошибка при обработке запроса"
_SAFE_UNAVAILABLE_TEXT = "Сервис временно недоступен. Пожалуйста, повторите через минуту."
_FEEDBACK_ACK_TEXT = "Спасибо за отзыв!"
_FEEDBACK_CONFIRMATION_BUTTON = "✅ Спасибо за отзыв!"
_MENU_SEARCH_TEXT = "🏠 Подобрать квартиру"

# Golden cases driving the live core path.
#
# Known answer: the free-text journey pins a NON-filter-sensitive phrasing of
# the #3421 golden corpus question. Characterization (#3419): the production
# transport path deterministically extracts retrieval filters from
# filter-sensitive Russian phrasings (``detect_filter_sensitive_query`` →
# ``_extract_request_filters`` → ``_hybrid_retrieval(filters=...)``), and the
# relaxation chain never drops USER filters — so a price/distance-sensitive
# query ("...до 120000 евро", "...у моря") legitimately yields zero documents
# on the markdown corpus (whose payload carries no ``price``/``distance_to_sea``
# fields) and answers the truthful no-claim fallback. The #3421 core lane
# cannot observe this: it drives ``run_assistant_request`` without transport
# filter extraction. The English phrasing below reaches the same corpus
# unfiltered and grounds the golden answer end to end.
_KNOWN_QUERY = "Tell me about the Sunny Beach studio apartment"
_KNOWN_ANSWER_MARKERS = ("Sunny Beach", "110000")
_KNOWN_ANSWER_FORBIDDEN = ("Mountain View Villa", "Bansko")
_UNSUPPORTED_CASE_ID = "missing_in_corpus_no_claim"

# Every core-consuming journey asks about a DIFFERENT corpus document: the
# production semantic cache matches by embedding similarity, so a repeated
# query text (even with a unique suffix) would be served from the semantic
# tier and bypass the pipeline stage the scenario must prove (#3419 run
# evidence). Latin-entity phrasings stay clear of the Russian filter regexes.
_FEEDBACK_QUERY = "Tell me about the mountain view villa with a panoramic terrace"
_DEPENDENCY_QUERY = "How much does the apartment in the city center of Sofia cost?"
_DUPLICATE_QUERY = "Is there a penthouse with a sea view in Nessebar?"

# The full fixture corpus, so every per-journey document question is answerable.
_GOLDEN_DOC_IDS = [
    "sunny_beach_studio",
    "sunny_beach_2bed",
    "mountain_view_villa",
    "city_center_sofia",
    "nessebar_penthouse",
    "sotirovo_garden",
    "services_cleaning",
    "rules_hitl",
]

_MODULE_LOOP = pytest.mark.asyncio(loop_scope="module")


def _namespaced_query(base: str, client_id: int) -> str:
    """Make one journey's query text unique for exact-text cache keys.

    The bot's cache is the production ``CacheLayerManager`` on the module's
    disposable Redis. Exact-text isolation only — scenarios that must reach
    the pipeline (never the semantic tier) additionally ask about distinct
    documents, because the semantic cache matches by embedding similarity.
    """
    return f"{base} [{client_id}]"


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
    """Block until the disposable server answers PING (#3368 conventions)."""
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
    """In-process Telegram transport for the dispatch journey (#3419).

    Every ``make_request`` is recorded (method name, payload, canned result)
    so tests assert real user-visible effects at the transport boundary.
    """

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramCall] = []
        self._next_message_id = 20_000

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
        raise NotImplementedError("the dispatch journey never downloads files")
        yield b""  # pragma: no cover

    def calls_of(self, method: str) -> list[TelegramCall]:
        return [call for call in self.calls if call.method == method]

    def texts_sent_to(self, chat_id: int) -> list[str]:
        return [
            str(call.payload.get("text") or "")
            for call in self.calls_of("sendMessage")
            if call.payload.get("chat_id") == chat_id
        ]

    async def make_request(self, bot: Bot, method: Any, timeout: int | None = None) -> Any:  # noqa: ASYNC109
        name = method.__api_method__
        payload = method.model_dump(warnings=False)

        result: Any = True
        if name == "sendMessage":
            self._next_message_id += 1
            chat_id = int(payload.get("chat_id") or 0)
            result = Message(
                message_id=self._next_message_id,
                date=datetime.now(UTC),
                chat=Chat(id=chat_id, type="supergroup" if chat_id < 0 else "private"),
                text=payload.get("text"),
            )
        elif name == "editMessageText":
            # aiogram-dialog reads media attributes off the edited message.
            chat_id = int(payload.get("chat_id") or 0)
            result = Message(
                message_id=int(payload.get("message_id") or 0),
                date=datetime.now(UTC),
                chat=Chat(id=chat_id, type="supergroup" if chat_id < 0 else "private"),
                text=payload.get("text"),
            )
        elif name == "editMessageReplyMarkup":
            chat_id = int(payload.get("chat_id") or 0)
            result = Message(
                message_id=int(payload.get("message_id") or 0),
                date=datetime.now(UTC),
                chat=Chat(id=chat_id, type="supergroup" if chat_id < 0 else "private"),
            )
        self.calls.append(TelegramCall(method=name, payload=payload, result=result))
        return result


# ---------------------------------------------------------------------------
# Deterministic core seams: counting generation/rewrite LLM (#3421 shape)
# ---------------------------------------------------------------------------


class _CountingLLM:
    """Deterministic harness LLM that counts every completion call."""

    def __init__(self) -> None:
        self._inner = FakeLLMConfig().create_llm()
        self.completion_calls = 0

    async def completion(self, **kwargs: Any) -> Any:
        self.completion_calls += 1
        return await self._inner.completion(**kwargs)


class _CountingLLMConfig(FakeLLMConfig):
    """FakeLLMConfig whose ``create_llm`` factory records every request.

    The supervisor's core request resolves answer generation through
    ``config.create_llm`` (CoreDependencies.config), so ``create_calls``
    counts full generation attempts of the production core path.
    """

    def __init__(self) -> None:
        self.create_calls = 0

    def create_llm(self, *, auto_trace: bool = False) -> Any:
        self.create_calls += 1
        return _CountingLLM()


# ---------------------------------------------------------------------------
# E2E sentinel middleware: proof of real dispatcher traversal (#3419)
# ---------------------------------------------------------------------------


class _RoutingSentinel(BaseMiddleware):
    """Record every event that traverses the real dispatcher middleware chain.

    The lane's acceptance forbids direct handler invocation: only
    ``Dispatcher.feed_update`` pushes an update through the registered
    middleware stack, so every scenario asserts the sentinel observed its
    update BEFORE the transport recorded the bot's answer.
    """

    def __init__(self) -> None:
        self.seen: list[tuple[str, int | str]] = []

    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Any],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            self.seen.append(("message", int(event.message_id)))
        elif isinstance(event, CallbackQuery):
            self.seen.append(("callback", str(event.id)))
        return await handler(event, data)


# ---------------------------------------------------------------------------
# Module stack: run-owned collection + disposable Redis + one real bot
# ---------------------------------------------------------------------------


@dataclass
class _DispatchStack:
    """Everything one dispatch module run owns: live services + one real bot."""

    bot: Any
    env: LiveE2EEnv
    namespace: RunNamespace
    collection: str
    live_redis: LiveRedis
    sentinel: _RoutingSentinel
    llm_config: _CountingLLMConfig
    rewrite_llm: _CountingLLM
    embeddings: LiveBGEEmbeddings
    sparse: LiveBGESparseEmbeddings
    qdrant: QdrantService


async def _build_dispatch_bot(stack: _DispatchStack) -> Any:
    """Assemble the production bot over real Redis/BGE/Qdrant via the DI seams."""
    cache = CacheLayerManager(redis_url=stack.live_redis.url, mode=RedisMode.SINGLE_INSTANCE)
    await cache.initialize()
    stack.qdrant = QdrantService(
        url=stack.env.qdrant_url,
        api_key=stack.env.qdrant_api_key,
        collection_name=stack.collection,
        timeout=30,
        prefer_grpc=False,
    )
    stack.embeddings = LiveBGEEmbeddings(stack.env.bge_m3_url)
    stack.sparse = LiveBGESparseEmbeddings(stack.env.bge_m3_url)

    config = make_full_bot_config(
        telegram_token=_BOT_TOKEN,
        redis_url=stack.live_redis.url,
        redis_mode="single_instance",
        qdrant_url=stack.env.qdrant_url,
        qdrant_api_key=stack.env.qdrant_api_key or "e2e-local",
        qdrant_collection=stack.collection,
    )
    bot = make_property_bot(
        config,
        service_overrides={
            "graph_config": stack.llm_config,
            "cache": cache,
            "hybrid": stack.embeddings,
            "embeddings": stack.embeddings,
            "sparse": stack.sparse,
            "qdrant": stack.qdrant,
            "llm": stack.rewrite_llm,
        },
    )
    # Deterministic Telegram boundary: the real aiogram Bot on a recorded
    # session. Swapped BEFORE the handoff lifecycle builds the ForumBridge.
    bot.bot = Bot(token=_BOT_TOKEN, session=RecordingTelegramSession())
    # The exact production lifecycle steps that wire the durable stack and
    # the dialog routers + catch-all query handler.
    bot._setup_handoff_services()
    bot._setup_workflow_data()
    bot._setup_dialogs()
    # The E2E sentinel rides the REAL middleware chain (outer, after the
    # production FSM-cancel middleware registered at construction).
    bot.dp.message.outer_middleware(stack.sentinel)
    bot.dp.callback_query.outer_middleware(stack.sentinel)
    return bot


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def dispatch_stack() -> AsyncIterator[_DispatchStack]:
    """One run-owned collection + one disposable Redis + one real bot."""
    if not _docker_daemon_available():
        guard_service_skip("Docker daemon unavailable — dispatch live harness cannot start")
    env = LiveE2EEnv.from_env()
    await require_live_services(env)

    namespace = RunNamespace.resolve()
    from tests.e2e_core.qdrant_helpers import generate_collection_name

    collection = generate_collection_name(namespace.run_id, namespace.worker)
    registry = TeardownRegistry(run_id=namespace.run_id)
    registry.register_collection(env.qdrant_url, collection)
    recreate_collection(env, collection)

    name = f"rag-e2e-3419-{uuid.uuid4().hex[:10]}"
    password = f"pw-{uuid.uuid4().hex}"
    live: LiveRedis | None = None
    stack: _DispatchStack | None = None
    try:
        port = _start_redis_container(name, password)
        live = LiveRedis(name=name, password=password, port=port)
        await _wait_until_ready(live)

        # The golden corpus for the live core path (#3421 fixture documents).
        points = await index_fixture_documents(env, collection, document_ids=_GOLDEN_DOC_IDS)
        assert points >= 1, "ephemeral corpus must index at least one document"

        stack = _DispatchStack(
            bot=None,
            env=env,
            namespace=namespace,
            collection=collection,
            live_redis=live,
            sentinel=_RoutingSentinel(),
            llm_config=_CountingLLMConfig(),
            rewrite_llm=_CountingLLM(),
            embeddings=None,  # type: ignore[arg-type]
            sparse=None,  # type: ignore[arg-type]
            qdrant=None,  # type: ignore[arg-type]
        )
        stack.bot = await _build_dispatch_bot(stack)
        yield stack
    finally:
        if stack is not None:
            with contextlib.suppress(Exception):
                await stack.bot._cache.close()
            for resource in (stack.embeddings, stack.sparse):
                if resource is not None:
                    with contextlib.suppress(Exception):
                        await resource.aclose()
            if stack.qdrant is not None:
                with contextlib.suppress(Exception):
                    await stack.qdrant.close()
        if live is not None:
            _docker("rm", "-f", name)
        assert _container_gone(name), f"disposable Redis container {name} survived cleanup"
        await registry.teardown_and_verify()


# ---------------------------------------------------------------------------
# Per-test journey: fresh transport, unique client id, sentinel reset
# ---------------------------------------------------------------------------

_CLIENT_ID_SEQUENCE = iter(range(3419_0001, 3419_0001 + 100))


class _DispatchJourney:
    """One client's live journey against the real dispatcher + core stack."""

    def __init__(self, stack: _DispatchStack, client_id: int) -> None:
        self.stack = stack
        self.bot = stack.bot
        self.sentinel = stack.sentinel
        self.transport = stack.bot.bot.session
        self.client_id = client_id
        self._next_update_id = 1
        # Cumulative core counters snapshotted at journey start: every test
        # asserts its own DELTA, never the module-wide absolute.
        self._generations_before = stack.llm_config.create_calls
        self._rewrites_before = stack.rewrite_llm.completion_calls

    @property
    def generations(self) -> int:
        """Core generation factory calls made during THIS journey."""
        return self.stack.llm_config.create_calls - self._generations_before

    @property
    def rewrites(self) -> int:
        """Rewrite-LLM completions made during THIS journey."""
        return self.stack.rewrite_llm.completion_calls - self._rewrites_before

    def _journey_user(self) -> User:
        return User(
            id=self.client_id,
            is_bot=False,
            first_name="Тест",
            last_name="Клиент",
            username=f"user{self.client_id}",
            language_code="ru",
        )

    def build_message_update(self, text: str) -> Update:
        """Build (without feeding) one private-chat text Update."""
        self._next_update_id += 1
        return Update(
            update_id=self._next_update_id,
            message=Message(
                message_id=self._next_update_id,
                date=datetime.now(UTC),
                chat=Chat(id=self.client_id, type="private"),
                from_user=self._journey_user(),
                text=text,
            ),
        )

    async def feed_update(self, update: Update) -> None:
        await self.bot.dp.feed_update(self.bot.bot, update)

    async def feed_message(self, text: str, *, pace_s: float = _MESSAGE_PACE_S) -> Update:
        if pace_s:
            await asyncio.sleep(pace_s)
        update = self.build_message_update(text)
        await self.feed_update(update)
        return update

    async def feed_callback(self, data: str, *, pace_s: float = _CALLBACK_PACE_S) -> Update:
        if pace_s:
            await asyncio.sleep(pace_s)
        self._next_update_id += 1
        update = Update(
            update_id=self._next_update_id,
            callback_query=CallbackQuery(
                id=str(self._next_update_id),
                from_user=self._journey_user(),
                chat_instance="dispatch-e2e",
                data=data,
                message=Message(
                    message_id=1,
                    date=datetime.now(UTC),
                    chat=Chat(id=self.client_id, type="private"),
                ),
            ),
        )
        await self.feed_update(update)
        return update

    # -- observation helpers (transport + sentinel boundaries) ------------

    def surface_texts(self) -> list[str]:
        return list(self.transport.texts_sent_to(self.client_id))

    def inline_button_data(self) -> list[str]:
        """Every inline button callback_data rendered to this client."""
        callbacks: list[str] = []
        for call in self.transport.calls_of("sendMessage"):
            if call.payload.get("chat_id") != self.client_id:
                continue
            markup = call.payload.get("reply_markup") or {}
            for row in markup.get("inline_keyboard") or []:
                for button in row:
                    data = str(button.get("callback_data") or "")
                    if data:
                        callbacks.append(data)
        return callbacks

    def assert_saw(self, update: Update) -> None:
        """The sentinel must have observed this update on the real chain."""
        if update.message is not None:
            identity: tuple[str, int | str] = ("message", int(update.message.message_id))
        else:
            assert update.callback_query is not None
            identity = ("callback", str(update.callback_query.id))
        assert identity in self.sentinel.seen, (
            f"update {identity} never traversed the real dispatcher middleware chain; "
            f"sentinel saw {self.sentinel.seen}"
        )


@pytest_asyncio.fixture(loop_scope="module")
async def journey(dispatch_stack: _DispatchStack) -> AsyncIterator[_DispatchJourney]:
    """One client's journey: fresh recorded transport, unique id, sentinel reset."""
    # A fresh recorded session per test keeps side-effect counts absolute.
    dispatch_stack.bot.bot.session = RecordingTelegramSession()
    dispatch_stack.sentinel.seen.clear()
    # The disposable Redis container is removed whole at module teardown;
    # every durable key this lane writes (bot cache tiers, semantic cache)
    # lives inside it, so no per-journey purge is required.
    yield _DispatchJourney(dispatch_stack, next(_CLIENT_ID_SEQUENCE))


# ---------------------------------------------------------------------------
# Scenario 1 — /start: commands router selects the client root, zero core
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(300)
async def test_start_command_answers_client_root_once_without_core_invocation(
    journey: _DispatchJourney,
) -> None:
    from telegram_bot.keyboards.client_keyboard import build_client_keyboard

    update = await journey.feed_message("/start")

    journey.assert_saw(update)

    # Exactly one user-visible response: the welcome message with the client
    # reply keyboard (bookmarks capability is absent — no PostgreSQL service).
    texts = journey.surface_texts()
    assert len(texts) == 1, texts
    assert texts[0].startswith("Привет"), texts

    sends = [
        call
        for call in journey.transport.calls_of("sendMessage")
        if call.payload.get("chat_id") == journey.client_id
    ]
    assert len(sends) == 1, sends
    markup = sends[0].payload.get("reply_markup") or {}
    labels = [str(button.get("text")) for row in (markup.get("keyboard") or []) for button in row]
    expected = build_client_keyboard(i18n=None, bookmarks_available=False)
    expected_labels = [
        str(button.text)
        for row in expected.keyboard
        for button in row  # type: ignore[union-attr]
    ]
    assert labels == expected_labels, labels
    assert _MENU_SEARCH_TEXT in labels, labels

    # /start must never touch the assistant core (no generation, no rewrite).
    assert journey.generations == 0, "generation ran for /start"
    assert journey.rewrites == 0, "rewrite ran for /start"

    # No dispatcher-level failure leaked to the user.
    assert not any(_DISPATCH_ERROR_TEXT in text for text in texts), texts


# ---------------------------------------------------------------------------
# Scenario 2 — known text: catch-all → supervisor → live core, one answer
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(600)
async def test_known_text_after_start_answers_exactly_once_through_live_core(
    journey: _DispatchJourney,
) -> None:
    query = _namespaced_query(_KNOWN_QUERY, journey.client_id)

    start = await journey.feed_message("/start")
    journey.assert_saw(start)
    update = await journey.feed_message(query)
    journey.assert_saw(update)

    # Exactly two user-visible responses: the /start welcome, then ONE answer.
    texts = journey.surface_texts()
    assert len(texts) == 2, texts
    answer = texts[1]
    for expected in _KNOWN_ANSWER_MARKERS:
        assert expected in answer, (expected, answer)
    for forbidden in _KNOWN_ANSWER_FORBIDDEN:
        assert forbidden not in answer, (forbidden, answer)

    # The one answer ran through ONE assistant-core generation.
    assert journey.generations == 1, f"exactly one generation expected, got {journey.generations}"

    # Chat/reply linkage: every user-visible send went to the sender's chat.
    chat_ids = {
        int(call.payload.get("chat_id") or 0) for call in journey.transport.calls_of("sendMessage")
    }
    assert chat_ids == {journey.client_id}, chat_ids

    # The answer carries the feedback keyboard keyed by the real request id.
    like_buttons = [data for data in journey.inline_button_data() if data.startswith("fb:like:")]
    assert len(like_buttons) == 1, journey.inline_button_data()
    assert like_buttons[0].count(":") == 2, like_buttons

    # No production failure surface fired.
    texts = journey.surface_texts()
    assert not any(_THROTTLE_NOTICE in text for text in texts), texts
    assert not any(_DISPATCH_ERROR_TEXT in text for text in texts), texts
    assert not any(_SAFE_UNAVAILABLE_TEXT in text for text in texts), texts


# ---------------------------------------------------------------------------
# Scenario 3 — unsupported text: truthful no-claim answer, no fabrication
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(600)
async def test_unsupported_text_answers_truthful_no_claim_through_live_core(
    journey: _DispatchJourney,
) -> None:
    case = load_golden_case(_UNSUPPORTED_CASE_ID)
    query = _namespaced_query(case.query, journey.client_id)

    update = await journey.feed_message(query)
    journey.assert_saw(update)

    texts = journey.surface_texts()
    assert len(texts) == 1, texts
    answer = texts[0]
    for expected in case.must_contain:
        assert expected.casefold() in answer.casefold(), (expected, answer)
    for forbidden in case.must_not_contain:
        assert forbidden.casefold() not in answer.casefold(), (forbidden, answer)

    # The no-claim answer still came from exactly one core generation.
    assert journey.generations == 1, f"exactly one generation expected, got {journey.generations}"
    assert not any(_DISPATCH_ERROR_TEXT in text for text in texts), texts


# ---------------------------------------------------------------------------
# Scenario 4 — representative callback: the response's own feedback button
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(600)
async def test_feedback_callback_from_real_response_round_trips_through_real_routes(
    journey: _DispatchJourney,
) -> None:
    query = _namespaced_query(_FEEDBACK_QUERY, journey.client_id)
    await journey.feed_message(query)

    like_buttons = [data for data in journey.inline_button_data() if data.startswith("fb:like:")]
    assert len(like_buttons) == 1, journey.inline_button_data()
    generations_after_answer = journey.stack.llm_config.create_calls

    # The callback rides the REAL dispatcher chain (sentinel proves it) into
    # the feedback callback family — never into the core again.
    update = await journey.feed_callback(like_buttons[0])
    journey.assert_saw(update)

    # Acknowledged with the production feedback copy.
    acknowledgements = [
        str(call.payload.get("text") or "")
        for call in journey.transport.calls_of("answerCallbackQuery")
        if _FEEDBACK_ACK_TEXT in str(call.payload.get("text") or "")
    ]
    assert acknowledgements, journey.transport.calls_of("answerCallbackQuery")

    # The keyboard became the confirmation (the like button's own message).
    confirmations = [
        call
        for call in journey.transport.calls_of("editMessageReplyMarkup")
        if _FEEDBACK_CONFIRMATION_BUTTON in str(call.payload.get("reply_markup") or "")
    ]
    assert confirmations, journey.transport.calls_of("editMessageReplyMarkup")

    # The callback never invoked the assistant core.
    assert journey.stack.llm_config.create_calls == generations_after_answer, (
        "feedback callback must not run the core"
    )
    assert not any(_DISPATCH_ERROR_TEXT in text for text in journey.surface_texts())


# ---------------------------------------------------------------------------
# Scenario 5 — dependency failure: canonical safe error, exactly once
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(300)
async def test_dead_qdrant_dependency_answers_safe_error_exactly_once(
    journey: _DispatchJourney,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Sever the retrieval backend at the DI seam: the live embeddings still
    # answer, every retrieval attempt hits a refused loopback port (#3421
    # dead-backend convention).
    dead_qdrant = QdrantService(
        url="http://127.0.0.1:1",
        collection_name=journey.stack.collection,
        timeout=2,
        prefer_grpc=False,
    )
    monkeypatch.setattr(journey.bot, "_qdrant", dead_qdrant)

    # A query about its own document: semantically distinct from earlier
    # journeys, so the semantic tier cannot serve this request — it must
    # reach (and fail at) the retrieval backend.
    query = _namespaced_query(_DEPENDENCY_QUERY, journey.client_id)
    update = await journey.feed_message(query)
    journey.assert_saw(update)

    texts = journey.surface_texts()
    assert len(texts) == 1, texts
    assert _SAFE_UNAVAILABLE_TEXT in texts[0], texts

    # The failure stayed inside the core: zero generation, zero rewrite, and
    # the dispatcher error handler never had to answer.
    assert journey.generations == 0, (
        "generation must never run after a retrieval dependency failure"
    )
    assert journey.rewrites == 0, "rewrite must never run after a retrieval dependency failure"
    assert not any(_DISPATCH_ERROR_TEXT in text for text in texts), texts
    assert not any(_THROTTLE_NOTICE in text for text in texts), texts


# ---------------------------------------------------------------------------
# Scenario 6 — repeated update id: absorbed exactly once by the real chain
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(600)
async def test_duplicate_update_id_is_absorbed_with_exactly_one_answer(
    journey: _DispatchJourney,
) -> None:
    # A fresh document question: the first delivery must run the full
    # pipeline (semantic-cache miss), so the absorption proof is real.
    query = _namespaced_query(_DUPLICATE_QUERY, journey.client_id)
    update = journey.build_message_update(query)

    # Deliver the SAME update twice: the duplicate enters while the first is
    # still inside the production pipeline, inside the catch-all's 2.0 s
    # throttle bucket window.
    first = asyncio.create_task(journey.feed_update(update))
    await asyncio.sleep(0.5)
    await journey.feed_update(update)
    await first

    # Both deliveries traversed the REAL middleware chain (same message id).
    identity = ("message", int(update.message.message_id))  # type: ignore[union-attr]
    assert journey.sentinel.seen.count(identity) == 2, journey.sentinel.seen

    # Exactly one answer from exactly one core call.
    texts = journey.surface_texts()
    assert len(texts) == 2, texts
    answers = [text for text in texts if _THROTTLE_NOTICE not in text]
    assert len(answers) == 1, texts
    assert journey.generations == 1, (
        f"the duplicate update must not re-run the core, got {journey.generations} generations"
    )

    # The duplicate got the truthful throttle notice — never a second answer,
    # never a dispatcher error.
    texts = journey.surface_texts()
    throttle_notices = [text for text in texts if _THROTTLE_NOTICE in text]
    assert len(throttle_notices) == 1, texts
    assert not any(_DISPATCH_ERROR_TEXT in text for text in texts), texts

    # Chat/reply linkage on every user-visible send.
    chat_ids = {
        int(call.payload.get("chat_id") or 0) for call in journey.transport.calls_of("sendMessage")
    }
    assert chat_ids == {journey.client_id}, chat_ids
