"""Live catalog E2E: menu -> filter dialog -> Qdrant -> property card -> CTA (#3417).

Proves the apartment catalog journey end to end through the REAL registered
routes: ``Dispatcher.feed_update`` drives actual Updates through the
production middlewares and aiogram-dialog routers (client menu, funnel
criteria, filter hub, catalog shell, viewing wizard, phone collector), the
production :class:`~telegram_bot.services.apartment.apartment_catalog.ApartmentCatalog`
interface, and the production :class:`~telegram_bot.services.apartment.apartments_service.ApartmentsService`
against a LIVE run-owned Qdrant collection. Outgoing side effects are observed
at the transport boundary on a deterministic in-process Telegram transport
(the real aiogram client stack with a recorded ``BaseSession``) — no
production credential, no paid provider, no fake SDK packages.

Stack scoping (#3417, documented decision): the catalog journey needs real
apartment retrieval (Qdrant + BGE-M3 embeddings via production ingestion) plus
Redis for the bot cache/FSM. Qdrant and BGE-M3 come from the hermetic harness
stack (#3414, the ``test_markdown_ingestion_capability.py`` #3416 lane);
Redis is a disposable, authenticated container per module following the
proven ``test_redis_modes_live.py`` (#3368) / funnel (#3413) conventions:
unique name, ephemeral host port, random password, no persistence, removed
and proven gone on teardown. Required mode (``E2E_HARNESS_REQUIRED=1``, legacy
``E2E_CORE_STRICT=1``) turns missing infrastructure into a FAILURE, never a
skip (#3414 policy).

Seeding (#3417): a TINY deterministic 17-row corpus is ingested through the
production demo bootstrap path (#3460) — ``create_apartments_collection_schema``
(contract schema + payload indexes + strict mode) and
``ingest_apartments_demo`` (the incremental runner with row fingerprints,
#3371) — into the run-owned collection with the selected collection name and
API key. No 297-record production dataset is used or required.

Scenarios (issue #3417 acceptance):

1. The seeded corpus is addressable through production ingestion: point
   count, deterministic point identity, the complete dense+bm42+colbert
   vector set, and the contract payload indexes (migrated unique behavior of
   the deleted shared-state ``tests/integration/test_apartments_ingestion.py``).
2. Menu -> funnel criteria -> summary (with the LIVE matching count) ->
   search: 10 real property cards (price-ordered first page), then
   "Показать ещё" traverses the price cursor to the remaining 2 — every
   visible card field originates from a seeded record, no duplicates.
3. The filter dialog applies EXACT city/rooms/price over live Qdrant through
   the real radio widgets and the apply handler: mid-budget keeps exactly the
   12 seeded matches; narrowing to the high budget leaves exactly the one
   seeded record at 120 000 €.
4. A legitimate zero-result filter shows the "Каталог пуст" copy and parks
   the chat in CatalogSG.empty.
5. The card CTA journey: the "На осмотр" button of a rendered card (its
   callback data carries the REAL point id from the search results) starts
   the viewing wizard, collects the phone, and the durable v2 lead record and
   the manager notification carry the seeded payload of that exact card.
6. Malformed callbacks (truncated ``card:viewing``, unknown widget data) are
   answered safely: no crash, no fabricated outgoing content, and the
   catalog stays usable afterwards.

The bot is assembled once per module: aiogram-dialog routers are module
singletons, so a dispatcher can attach them exactly once per process
(production runs one bot per process). Per-test isolation comes from a fresh
transport session, a unique client id (FSM/throttle/Redis namespaces) and
exact run-owned Redis key cleanup.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import shutil
import subprocess
import time
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
import redis.asyncio as aioredis
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.types import (
    CallbackQuery,
    Chat,
    Contact,
    ForumTopicCreated,
    Message,
    Update,
    User,
)

from src.runtime.integrations.cache import CacheLayerManager
from src.runtime.integrations.redis_mode import RedisMode
from tests.e2e_core.live_harness import (
    LiveE2EEnv,
    RunNamespace,
    TeardownRegistry,
    guard_service_skip,
    require_live_services,
)
from tests.unit._bot_config_factory import make_full_bot_config
from tests.unit._property_bot_factory import make_property_bot


pytestmark = [pytest.mark.e2e, pytest.mark.requires_services]

# The journey paces its feeds to stay above the production throttling rates
# (1.0 s per user for messages, 0.3 s for callbacks) instead of exempting the
# test user: the throttling middleware stays on the real path.
_MESSAGE_PACE_S = 1.05
_CALLBACK_PACE_S = 0.35

_MENU_SEARCH_TEXT = "🏠 Подобрать квартиру"
_SHOW_MORE_TEXT = "🔄 Показать ещё"
_FILTERS_TEXT = "🔍 Фильтры"
_EMPTY_CATALOG_TEXT = "Каталог пуст. Измените фильтры или отправьте новый запрос."
_VALID_PHONE_RAW = "+359 88 341 70 00"
_VALID_PHONE_E164 = "+359883417000"
_VIEWING_SUCCESS_TEXT = "✅ Заявка оформлена! Скоро менеджер свяжется с вами."
_WAITING_PHONE_STATE = "PhoneCollectorStates:waiting_phone"
_MANAGERS_GROUP_ID = -100_3417_0001
_BOT_TOKEN = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"

_MODULE_LOOP = pytest.mark.asyncio(loop_scope="module")


# ---------------------------------------------------------------------------
# Tiny deterministic seed corpus (the "tiny seeded corpus" of #3417)
# ---------------------------------------------------------------------------

_SB = "Солнечный берег"
_SV = "Свети Влас"
_EL = "Элените"
_SB_COMPLEXES = ("Premier Fort Beach", "Panorama Fort Beach", "Messambria Fort Beach")

# 12 in-city matches for the funnel criteria (city=Солнечный берег,
# property_type=2bed -> rooms=3, budget=mid -> price_eur 50k..100k), plus five
# decoys that every exactness probe below must exclude.
SEED_ROWS: list[dict[str, Any]] = [
    {
        "complex_name": _SB_COMPLEXES[i % 3],
        "city": _SB,
        "section": f"A{i}",
        "apartment_number": str(100 + i),
        "rooms": 3,
        "floor_label": str((i % 5) + 1),
        "area_m2": str(45 + 2 * i),
        "view_raw": "sea panorama" if i % 2 else "pool",
        "price_eur": str(61000 + (i - 1) * 1000),
        "price_bgn": "0",
        "is_furnished": "true",
        "has_floor_plan": "true",
        "has_photo": "true",
        "is_promotion": "false",
    }
    for i in range(1, 13)
] + [
    {  # rooms matches, price breaks the mid budget: the exactness anchor
        "complex_name": "Nessebar Fort Residence",
        "city": _SB,
        "section": "B",
        "apartment_number": "201",
        "rooms": 3,
        "floor_label": "4",
        "area_m2": "70",
        "view_raw": "garden",
        "price_eur": "120000",
        "price_bgn": "0",
        "is_furnished": "false",
        "has_floor_plan": "false",
        "has_photo": "true",
        "is_promotion": "false",
    },
    {  # city matches, rooms break the funnel criteria
        "complex_name": "Prestige Fort Beach",
        "city": _SB,
        "section": "C",
        "apartment_number": "301",
        "rooms": 5,
        "floor_label": "6",
        "area_m2": "110",
        "view_raw": "ultra sea panorama",
        "price_eur": "250000",
        "price_bgn": "0",
        "is_furnished": "true",
        "has_floor_plan": "false",
        "has_photo": "true",
        "is_promotion": "false",
    },
    {  # another city entirely
        "complex_name": "Crown Fort Club",
        "city": _SV,
        "section": "A",
        "apartment_number": "401",
        "rooms": 2,
        "floor_label": "2",
        "area_m2": "52",
        "view_raw": "sea",
        "price_eur": "55000",
        "price_bgn": "0",
        "is_furnished": "true",
        "has_floor_plan": "false",
        "has_photo": "true",
        "is_promotion": "false",
    },
    {
        "complex_name": "Crown Fort Club",
        "city": _SV,
        "section": "B",
        "apartment_number": "402",
        "rooms": 2,
        "floor_label": "3",
        "area_m2": "56",
        "view_raw": "pool",
        "price_eur": "80000",
        "price_bgn": "0",
        "is_furnished": "true",
        "has_floor_plan": "false",
        "has_photo": "true",
        "is_promotion": "false",
    },
    {
        "complex_name": "Green Fort Suites",
        "city": _EL,
        "section": "A",
        "apartment_number": "501",
        "rooms": 4,
        "floor_label": "1",
        "area_m2": "88",
        "view_raw": "forest",
        "price_eur": "120000",
        "price_bgn": "0",
        "is_furnished": "false",
        "has_floor_plan": "false",
        "has_photo": "true",
        "is_promotion": "false",
    },
]


def _mid_budget_matches() -> list[dict[str, Any]]:
    """The seeded rows that satisfy city=СБ + rooms=3 + budget=mid, price-ordered."""
    matches = [
        row
        for row in SEED_ROWS
        if row["city"] == _SB
        and int(row["rooms"]) == 3
        and 50000 <= int(row["price_eur"]) <= 100000
    ]
    return sorted(matches, key=lambda row: int(row["price_eur"]))


def _write_seed_csv(directory: Path) -> Path:
    """Write the seed corpus as a CSV for the production ingestion runner."""
    import csv

    fieldnames = [
        "complex_name",
        "city",
        "section",
        "apartment_number",
        "rooms",
        "floor_label",
        "area_m2",
        "view_raw",
        "price_eur",
        "price_bgn",
        "is_furnished",
        "has_floor_plan",
        "has_photo",
        "is_promotion",
    ]
    csv_path = directory / "apartments_e2e_3417.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(SEED_ROWS)
    return csv_path


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
    """In-process Telegram/forum transport for the catalog journey.

    Every ``make_request`` is recorded (method name, payload, canned result)
    so tests assert real side effects at the transport boundary.
    """

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramCall] = []
        self._next_message_id = 20_000
        self._next_topic_id = 3_500

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
        raise NotImplementedError("the catalog journey never downloads files")
        yield b""  # pragma: no cover

    def calls_of(self, method: str) -> list[TelegramCall]:
        return [call for call in self.calls if call.method == method]

    def texts_sent_to(self, chat_id: int) -> list[str]:
        return [
            str(call.payload.get("text") or "")
            for call in self.calls_of("sendMessage")
            if call.payload.get("chat_id") == chat_id
        ]

    def cards_sent_to(self, chat_id: int) -> list[TelegramCall]:
        """sendMessage calls to ``chat_id`` that render a property card."""
        return [
            call
            for call in self.calls_of("sendMessage")
            if call.payload.get("chat_id") == chat_id
            and "🏠 Комплекс:" in str(call.payload.get("text") or "")
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
        elif name == "sendMediaGroup":
            chat_id = int(payload.get("chat_id") or 0)
            result = [
                Message(
                    message_id=self._next_message_id,
                    date=datetime.now(UTC),
                    chat=Chat(id=chat_id, type="private"),
                )
            ]
        self.calls.append(TelegramCall(method=name, payload=payload, result=result))
        return result


# ---------------------------------------------------------------------------
# Module stack: run-owned collection via production bootstrap + real bot
# ---------------------------------------------------------------------------


@dataclass
class _CatalogStack:
    """Everything one catalog module run owns: live services + one real bot."""

    bot: Any
    env: LiveE2EEnv
    namespace: RunNamespace
    collection: str
    live_redis: LiveRedis
    transport: RecordingTelegramSession
    seed_csv: Path
    seed_state: Path


async def _build_catalog_bot(env: LiveE2EEnv, live: LiveRedis, collection: str) -> Any:
    """Assemble the production bot over real Redis/Qdrant via the DI seams."""
    from src.runtime.services.qdrant import QdrantService
    from telegram_bot.services.apartment.apartment_extraction_pipeline import (
        ApartmentExtractionPipeline,
    )
    from telegram_bot.services.apartment.apartment_filter_extractor import (
        ApartmentFilterExtractor,
    )
    from telegram_bot.services.apartment.apartments_service import ApartmentsService

    cache = CacheLayerManager(redis_url=live.url, mode=RedisMode.SINGLE_INSTANCE)
    await cache.initialize()

    qdrant_apartments = QdrantService(
        url=env.qdrant_url,
        api_key=env.qdrant_api_key,
        collection_name=collection,
        timeout=30,
        prefer_grpc=False,
    )
    apartments_service = ApartmentsService(qdrant=qdrant_apartments)
    # The production regex-first extraction construction (llm gap-fill absent,
    # as in bot-only deployments) — the pipeline stays on the real path.
    apartment_pipeline = ApartmentExtractionPipeline(
        regex_extractor=ApartmentFilterExtractor(),
        llm_extractor=None,
        redis=cache.redis,
    )

    config = make_full_bot_config(
        telegram_token=_BOT_TOKEN,
        redis_url=live.url,
        redis_mode="single_instance",
        managers_group_id=_MANAGERS_GROUP_ID,
        qdrant_url=env.qdrant_url,
        qdrant_api_key=env.qdrant_api_key or "e2e-local",
        qdrant_collection=collection,
    )
    bot = make_property_bot(
        config,
        service_overrides={
            "cache": cache,
            "qdrant_apartments": qdrant_apartments,
            "apartments_service": apartments_service,
            "apartment_pipeline": apartment_pipeline,
        },
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
    assert bot._apartments_service is apartments_service, (
        "production lifecycle must expose the real apartments service"
    )
    return bot


def _bootstrap_owned_collection(
    env: LiveE2EEnv, collection: str, csv_path: Path, state_path: Path
) -> dict[str, int]:
    """Create + populate the run-owned collection via the demo bootstrap path.

    Production-only code path (#3460): ``create_apartments_collection_schema``
    applies the contract schema, payload indexes, and strict mode; the
    incremental runner writes ONLY to ``collection_name`` with the supplied
    credentials and tracks rows by content fingerprint (#3371).
    """
    from qdrant_client import QdrantClient

    from scripts.demo_bootstrap import (
        create_apartments_collection_schema,
        ingest_apartments_demo,
    )

    client = QdrantClient(url=env.qdrant_url, api_key=env.qdrant_api_key, timeout=60)
    try:
        create_apartments_collection_schema(client, collection)
    finally:
        client.close()

    return ingest_apartments_demo(
        str(csv_path),
        env.qdrant_url,
        env.bge_m3_url,
        str(state_path),
        collection_name=collection,
        qdrant_api_key=env.qdrant_api_key,
    )


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def catalog_stack(tmp_path_factory: pytest.TempPathFactory) -> AsyncIterator[_CatalogStack]:
    """One run-owned collection + one disposable Redis + one real bot."""
    if not _docker_daemon_available():
        guard_service_skip("Docker daemon unavailable — catalog live harness cannot start")
    env = LiveE2EEnv.from_env()
    await require_live_services(env)

    namespace = RunNamespace.resolve()
    from tests.e2e_core.qdrant_helpers import generate_collection_name

    collection = generate_collection_name(namespace.run_id, namespace.worker)
    registry = TeardownRegistry(run_id=namespace.run_id)
    registry.register_collection(env.qdrant_url, collection)

    name = f"rag-e2e-3417-{uuid.uuid4().hex[:10]}"
    password = f"pw-{uuid.uuid4().hex}"
    live: LiveRedis | None = None
    bot: Any = None
    stack: _CatalogStack | None = None
    try:
        port = _start_redis_container(name, password)
        live = LiveRedis(name=name, password=password, port=port)

        seed_dir = tmp_path_factory.mktemp("seed")
        csv_path = _write_seed_csv(seed_dir)
        state_path = seed_dir / "ingestion_state.json"
        stats = _bootstrap_owned_collection(env, collection, csv_path, state_path)
        assert stats["total"] == len(SEED_ROWS), f"seed scan mismatch: {stats}"
        assert stats["changed"] == len(SEED_ROWS), f"seed ingest mismatch: {stats}"

        bot = await _build_catalog_bot(env, live, collection)
        stack = _CatalogStack(
            bot=bot,
            env=env,
            namespace=namespace,
            collection=collection,
            live_redis=live,
            transport=bot.bot.session,
            seed_csv=csv_path,
            seed_state=state_path,
        )
        yield stack
    finally:
        if bot is not None:
            with contextlib.suppress(Exception):
                await bot._cache.close()
        if live is not None:
            _docker("rm", "-f", name)
        assert _container_gone(name), f"disposable Redis container {name} survived cleanup"
        await registry.teardown_and_verify()


# ---------------------------------------------------------------------------
# Per-test journey: fresh transport, unique client id, exact key cleanup
# ---------------------------------------------------------------------------

_CLIENT_ID_SEQUENCE = iter(range(3417_0001, 3417_0001 + 100))


class _CatalogJourney:
    """One client's live journey against one real bot + live services."""

    redis_client: aioredis.Redis

    def __init__(self, stack: _CatalogStack, client_id: int) -> None:
        self.stack = stack
        self.bot = stack.bot
        self.transport = stack.transport
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
                chat_instance="catalog-e2e",
                data=data,
                message=Message(
                    message_id=1,
                    date=datetime.now(UTC),
                    chat=Chat(id=self.client_id, type="private"),
                ),
            ),
        )
        await self.bot.dp.feed_update(self.bot.bot, update)

    def fsm(self) -> Any:
        from aiogram.fsm.context import FSMContext
        from aiogram.fsm.storage.base import StorageKey

        return FSMContext(
            storage=self.bot.dp.storage,
            key=StorageKey(bot_id=self.bot.bot.id, chat_id=self.client_id, user_id=self.client_id),
        )

    async def dialog_state(self) -> str | None:
        """Read the aiogram-dialog context state (its own storage destiny)."""
        storage = self.bot.dp.storage

        def _destiny_key(destiny: str) -> Any:
            from aiogram.fsm.storage.base import StorageKey

            return StorageKey(
                bot_id=self.bot.bot.id,
                chat_id=self.client_id,
                user_id=self.client_id,
                destiny=destiny,
            )

        stack_data = await storage.get_data(_destiny_key("aiogd:stack:"))
        intents = stack_data.get("intents") or []
        if not intents:
            return None
        context = await storage.get_data(_destiny_key(f"aiogd:context:{intents[-1]}"))
        state = context.get("state")
        return str(state) if state else None

    def card_texts(self) -> list[str]:
        return [
            str(call.payload.get("text") or "")
            for call in self.transport.cards_sent_to(self.client_id)
        ]

    def card_callbacks(self) -> list[str]:
        """Every ``card:*`` callback data rendered on cards sent to this client."""
        callbacks: list[str] = []
        for call in self.transport.cards_sent_to(self.client_id):
            markup = call.payload.get("reply_markup") or {}
            for row in markup.get("inline_keyboard") or []:
                for button in row:
                    data = str(button.get("callback_data") or "")
                    if data.startswith("card:"):
                        callbacks.append(data)
        return callbacks

    def reply_keyboard_labels(self, call: TelegramCall) -> list[str]:
        """Reply-keyboard button labels of one recorded sendMessage call."""
        markup = call.payload.get("reply_markup") or {}
        return [str(button.get("text")) for row in (markup.get("keyboard") or []) for button in row]


def _price_of(card_text: str) -> int:
    """The rendered card price as an int ('Цена: 61 000 €' -> 61000)."""
    raw = card_text.split("Цена: ", 1)[1].split(" €", 1)[0]
    return int(raw.replace(" ", ""))


@pytest_asyncio.fixture(loop_scope="module")
async def journey(catalog_stack: _CatalogStack) -> AsyncIterator[_CatalogJourney]:
    """One client's journey: fresh recorded transport, unique id, key cleanup."""
    # A fresh recorded session per test keeps side-effect counts absolute.
    catalog_stack.bot.bot.session = RecordingTelegramSession()
    catalog_stack.transport = catalog_stack.bot.bot.session
    client = aioredis.from_url(catalog_stack.live_redis.url, decode_responses=True)
    current = _CatalogJourney(catalog_stack, next(_CLIENT_ID_SEQUENCE))
    current.redis_client = client
    try:
        yield current
    finally:
        await client.delete(
            f"lead_request:v2:{current.client_id}",
            f"lead_request:{current.client_id}",
            f"lead_notify:v2:{current.client_id}",
        )
        await client.aclose()


# ---------------------------------------------------------------------------
# Shared journey steps (production routes only)
# ---------------------------------------------------------------------------


async def _run_funnel_search_to_cards(journey: _CatalogJourney) -> None:
    """Menu -> funnel criteria -> summary -> 'Карточками' search -> cards."""
    await journey.feed_message(_MENU_SEARCH_TEXT)
    await journey.feed_callback(f"city:{_SB}")
    await journey.feed_callback("property_type:2bed")
    await journey.feed_callback("budget:mid")
    await journey.feed_callback("pref_done")
    await journey.feed_callback("search_cards")


async def _assert_zero_durable_writes(client: aioredis.Redis, client_id: int) -> None:
    for key in (f"lead_request:v2:{client_id}", f"lead_request:{client_id}"):
        assert await client.hgetall(key) == {}, f"unexpected durable record in {key}"


# ---------------------------------------------------------------------------
# Scenario 1 — seeded corpus addressable through production ingestion
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(240)
async def test_seeded_corpus_is_addressable_through_production_ingestion(
    catalog_stack: _CatalogStack,
) -> None:
    """Point identity, vector completeness, payload indexes (#3417 migration)."""
    from qdrant_client import QdrantClient
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    from src.runtime.qdrant.contracts import apartment_point_id

    client = QdrantClient(
        url=catalog_stack.env.qdrant_url,
        api_key=catalog_stack.env.qdrant_api_key,
        timeout=60,
    )
    try:
        info = client.get_collection(catalog_stack.collection)
        assert info.points_count == len(SEED_ROWS), (
            "the tiny seeded corpus (not the 297-record dataset) is the collection"
        )

        # Contract payload indexes for filtered search (migrated unique
        # behavior of tests/integration/test_apartments_ingestion.py).
        indexed_fields = set(info.payload_schema.keys())
        required = {"city", "complex_name", "rooms", "price_eur", "area_m2", "floor"}
        assert not (required - indexed_fields), (
            f"Missing payload indexes: {required - indexed_fields}"
        )

        # Deterministic point identity: one known seeded row is addressable
        # through the canonical apartment_point_id function, with complete
        # dense+bm42+colbert vectors (migrated+upgraded vector assertion).
        first = SEED_ROWS[0]
        known_id = apartment_point_id(
            first["complex_name"], first["section"], first["apartment_number"]
        )
        records, _ = client.scroll(
            collection_name=catalog_stack.collection,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="city",
                        match=MatchValue(value=first["city"]),
                    ),
                    FieldCondition(
                        key="rooms",
                        match=MatchValue(value=int(first["rooms"])),
                    ),
                ]
            ),
            limit=100,
            with_payload=True,
            with_vectors=True,
        )
        payloads = {str(r.id): (r.payload or {}) for r in records}
        assert known_id in payloads, "deterministic seeded point id must be present"
        stored = payloads[known_id]
        assert stored["complex_name"] == first["complex_name"]
        assert stored["apartment_number"] == first["apartment_number"]
        assert stored["price_eur"] == float(first["price_eur"])

        vectors = dict(records[0].vector)
        assert set(vectors) == {"dense", "bm42", "colbert"}, (
            f"point must carry the complete named-vector set, got {sorted(vectors)}"
        )
        assert len(vectors["dense"]) == 1024
        assert len(vectors["bm42"].indices) > 0
        assert len(vectors["colbert"]) > 0
    finally:
        client.close()

    # Fingerprint (#3371): an incremental re-scan of the SAME csv re-embeds
    # nothing — the persisted state matches every row.
    from src.ingestion.apartments.runner import IncrementalApartmentIngester

    rescan = IncrementalApartmentIngester(
        csv_path=str(catalog_stack.seed_csv),
        qdrant_url=catalog_stack.env.qdrant_url,
        bge_url=catalog_stack.env.bge_m3_url,
        state_path=str(catalog_stack.seed_state),
        collection_name=catalog_stack.collection,
        qdrant_api_key=catalog_stack.env.qdrant_api_key,
    )
    stats = rescan.run_incremental()
    assert stats["changed"] == 0, f"unchanged rows must not re-embed: {stats}"
    assert stats["unchanged"] == len(SEED_ROWS), stats
    assert stats["removed"] == 0, stats


# ---------------------------------------------------------------------------
# Scenario 2 — menu -> funnel criteria -> live search -> cards -> show more
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(300)
async def test_menu_funnel_search_renders_seeded_cards_and_pages_through_cursor(
    journey: _CatalogJourney,
) -> None:
    await _run_funnel_search_to_cards(journey)

    # The summary preview showed the LIVE matching count before the search.
    surface_texts = [
        call.payload.get("text") or ""
        for call in journey.transport.calls
        if call.method in {"sendMessage", "editMessageText"}
    ]
    preview = "\n".join(surface_texts)
    assert "Город: Солнечный берег" in preview, preview
    assert "Тип: 2-спальни" in preview, preview
    assert "Найдено: 12 апартаментов" in preview, (
        "summary must carry the live Qdrant count for the selected criteria"
    )

    # Page 1: exactly 10 price-ordered property cards.
    expected = _mid_budget_matches()
    cards = journey.transport.cards_sent_to(journey.client_id)
    assert len(cards) == 10, f"page 1 must render 10 cards, got {len(cards)}"

    first_text = str(cards[0].payload.get("text") or "")
    first = expected[0]
    assert f"🏠 Комплекс: {first['complex_name']}" in first_text, first_text
    assert f"🏗 Секция: {first['section']}" in first_text, first_text
    assert f"🚪 №: {first['apartment_number']}" in first_text, first_text
    assert f"📍 Город: {first['city']}" in first_text, first_text
    assert "💰 Цена: 61 000 €" in first_text, first_text
    assert "🌅 Вид:" in first_text, "the seeded view tags must be visible on the card"

    # Controls message: live counters + the show-more reply keyboard.
    controls = [
        call
        for call in journey.transport.calls_of("sendMessage")
        if call.payload.get("chat_id") == journey.client_id
        and "Показано" in str(call.payload.get("text") or "")
    ]
    assert any("Показано 10 из 12" in str(c.payload.get("text")) for c in controls), controls
    last_controls = journey.reply_keyboard_labels(controls[-1])
    assert any(label.startswith(_SHOW_MORE_TEXT) for label in last_controls), last_controls

    # Next page through the production cursor: 2 more cards, no duplicates.
    await journey.feed_message(_SHOW_MORE_TEXT)

    cards_after = journey.transport.cards_sent_to(journey.client_id)
    assert len(cards_after) == 12, f"pages 1+2 must render 12 cards, got {len(cards_after)}"
    tail_prices = sorted(_price_of(str(c.payload.get("text") or "")) for c in cards_after[10:])
    assert tail_prices == [71000, 72000], tail_prices

    refreshed = [
        call
        for call in journey.transport.calls_of("sendMessage")
        if call.payload.get("chat_id") == journey.client_id
        and "Показано 12 из 12" in str(call.payload.get("text") or "")
    ]
    assert refreshed, "the controls message must reflect the exhausted cursor"
    final_labels = journey.reply_keyboard_labels(refreshed[-1])
    assert not any(label.startswith(_SHOW_MORE_TEXT) for label in final_labels), final_labels

    # No card repeats: every rendered card is a distinct seeded record.
    card_keys = [str(call.payload.get("text") or "") for call in cards_after]
    assert len(set(card_keys)) == 12, "every visible card must originate from a distinct seed row"


# ---------------------------------------------------------------------------
# Scenario 3 — filter dialog: exact city/rooms/price over live Qdrant
# ---------------------------------------------------------------------------


async def _apply_filters(
    journey: _CatalogJourney,
    *,
    city: str | None = None,
    budget: str | None = None,
) -> None:
    """Open the filter dialog, optionally change one selection, and apply.

    The dialog is started with the CURRENT catalog runtime filters
    (``_handle_catalog_filters_message`` prefills ``dialog_data``), so only
    selections that actually CHANGE are driven here: re-selecting the checked
    radio item is a documented no-op that fires no ``on_state_changed``.
    """
    await journey.feed_message(_FILTERS_TEXT)
    if city is not None:
        await journey.feed_callback("sw_city")
        await journey.feed_callback(f"r_city:{city}")
    if budget is not None:
        await journey.feed_callback("sw_budget")
        await journey.feed_callback(f"r_budget:{budget}")
    await journey.feed_callback("btn_apply")


@_MODULE_LOOP
@pytest.mark.timeout(300)
async def test_filter_dialog_applies_exact_city_rooms_price_over_live_qdrant(
    journey: _CatalogJourney,
) -> None:
    await _run_funnel_search_to_cards(journey)
    funnel_cards = len(journey.card_texts())
    assert funnel_cards == 10, funnel_cards
    funnel_texts = len(journey.transport.texts_sent_to(journey.client_id))

    # Exact criteria — the funnel selections (Солнечный берег, 2-спальни ->
    # rooms=3, mid budget) arrive prefilled from the catalog runtime and are
    # applied unchanged: live Qdrant counts 12 matches and the first page
    # renders 10 of them, price-ordered.
    await _apply_filters(journey)

    cards = journey.card_texts()[funnel_cards:]
    assert len(cards) == 10, f"the applied filter must render its first page, got {len(cards)}"
    prices = sorted(_price_of(text) for text in cards)
    assert prices == [61000 + i * 1000 for i in range(10)], prices
    assert all(f"📍 Город: {_SB}" in text for text in cards), (
        "every card must match the city filter"
    )
    assert not any("Nessebar Fort Residence" in text for text in cards), (
        "the 120k rooms=3 anchor must be excluded by the mid budget"
    )
    assert not any("Crown Fort Club" in text for text in cards), (
        "other-city rows must be excluded by the city filter"
    )
    applied_controls = [
        text
        for text in journey.transport.texts_sent_to(journey.client_id)[funnel_texts:]
        if "Показано" in text
    ]
    assert any("Показано 10 из 12" in text for text in applied_controls), applied_controls

    # Narrow the budget to high (100k..150k): exactly the one seeded anchor.
    mid_cards = len(journey.card_texts())
    await _apply_filters(journey, budget="high")

    narrowed = journey.card_texts()[mid_cards:]
    assert len(narrowed) == 1, f"the high budget must leave exactly one card, got {len(narrowed)}"
    anchor = next(row for row in SEED_ROWS if row["complex_name"] == "Nessebar Fort Residence")
    text = narrowed[0]
    assert f"🏠 Комплекс: {anchor['complex_name']}" in text, text
    assert f"🚪 №: {anchor['apartment_number']}" in text, text
    assert "💰 Цена: 120 000 €" in text, text


# ---------------------------------------------------------------------------
# Scenario 4 — legitimate zero result: truthful copy, empty state
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(300)
async def test_zero_result_filter_shows_no_result_copy_and_empty_state(
    journey: _CatalogJourney,
) -> None:
    client = journey.redis_client
    await _run_funnel_search_to_cards(journey)
    cards_before = len(journey.card_texts())
    texts_before = len(journey.transport.texts_sent_to(journey.client_id))

    # Switch the city to Элените (rooms=3 and the mid budget stay prefilled):
    # Элените has no rooms=3 seeded row, so this is a legitimate empty result.
    await _apply_filters(journey, city=_EL)

    texts_after_apply = journey.transport.texts_sent_to(journey.client_id)[texts_before:]
    assert any(_EMPTY_CATALOG_TEXT in text for text in texts_after_apply), texts_after_apply
    assert await journey.dialog_state() == "CatalogSG:empty", (
        "a zero-result filter must park the chat in the catalog empty state"
    )
    assert len(journey.card_texts()) == cards_before, (
        "no property card may be fabricated for an empty result"
    )

    # A legitimate no-result is still a clean journey: nothing durable.
    await _assert_zero_durable_writes(client, journey.client_id)


# ---------------------------------------------------------------------------
# Scenario 5 — card CTA journey: durable lead carries the seeded payload
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(300)
async def test_card_cta_journey_creates_durable_lead_from_seeded_card(
    journey: _CatalogJourney,
) -> None:
    client_id = journey.client_id
    client = journey.redis_client
    await _run_funnel_search_to_cards(journey)

    # The "На осмотр" button of the FIRST RENDERED card carries the real id.
    viewing_callbacks = [
        data for data in journey.card_callbacks() if data.startswith("card:viewing:")
    ]
    assert len(viewing_callbacks) == 10, viewing_callbacks
    card_id = viewing_callbacks[0].split(":", 2)[2]
    expected_first = _mid_budget_matches()[0]
    from src.runtime.qdrant.contracts import apartment_point_id

    assert card_id == apartment_point_id(
        expected_first["complex_name"],
        expected_first["section"],
        expected_first["apartment_number"],
    ), "the card CTA must reference the seeded record the card was rendered from"

    # Card -> viewing wizard -> nearest date -> phone prompt.
    await journey.feed_callback(f"card:viewing:{card_id}")
    await journey.feed_callback("viewing_date:nearest")
    state = await journey.fsm().get_state()
    assert state == _WAITING_PHONE_STATE, f"journey must reach the phone FSM, got {state}"

    # Phone text through the real FSM route: durable v2 lead + manager notify.
    await journey.feed_message(_VALID_PHONE_RAW)

    texts = journey.transport.texts_sent_to(client_id)
    assert any(_VIEWING_SUCCESS_TEXT in text for text in texts), texts

    raw_v2 = await client.hgetall(f"lead_request:v2:{client_id}")
    assert len(raw_v2) == 1, sorted(raw_v2)
    record = json.loads(next(iter(raw_v2.values())))
    assert record["phone"] == _VALID_PHONE_E164
    assert record["service_key"] == "viewing"
    assert json.loads(record["viewing_objects"]) == [
        {
            "id": card_id,
            "complex_name": expected_first["complex_name"],
            "property_type": "",
            "area_m2": float(expected_first["area_m2"]),
            "price_eur": float(expected_first["price_eur"]),
        }
    ], "the durable lead must carry the seeded payload of the rendered card"

    manager_sends = [
        call
        for call in journey.transport.calls_of("sendMessage")
        if call.payload.get("chat_id") == _MANAGERS_GROUP_ID
    ]
    assert len(manager_sends) == 1, manager_sends
    notification = str(manager_sends[0].payload["text"])
    assert notification.startswith("--- Новая заявка ---")
    assert f"Телефон: {_VALID_PHONE_E164}" in notification
    assert f"id={card_id}" in notification

    notify_state = await client.hgetall(f"lead_notify:v2:{client_id}")
    assert json.loads(notify_state[record["request_id"]])["status"] == "notified"


# ---------------------------------------------------------------------------
# Scenario 6 — malformed callback safety
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(300)
async def test_malformed_callbacks_are_answered_safely_and_catalog_stays_usable(
    journey: _CatalogJourney,
) -> None:
    await _run_funnel_search_to_cards(journey)
    baseline = len(journey.transport.texts_sent_to(journey.client_id))
    baseline_cards = len(journey.card_texts())

    # Truncated card callback (no property id): answered, nothing sent.
    await journey.feed_callback("card:viewing")
    assert len(journey.transport.texts_sent_to(journey.client_id)) == baseline
    assert await journey.fsm().get_state() is None, "a malformed CTA must not start a wizard"

    # Unknown widget callback data inside the active catalog dialog.
    await journey.feed_callback("totally_unknown_widget:42")
    assert len(journey.transport.texts_sent_to(journey.client_id)) == baseline

    # The malformed feeds must not corrupt the journey: the catalog still
    # pages, and the CTA of a real card still opens the viewing wizard.
    await journey.feed_message(_SHOW_MORE_TEXT)
    assert len(journey.card_texts()) == baseline_cards + 2

    real_cta = next(data for data in journey.card_callbacks() if data.startswith("card:viewing:"))
    await journey.feed_callback(real_cta)
    await journey.feed_callback("viewing_date:nearest")
    assert await journey.fsm().get_state() == _WAITING_PHONE_STATE
