"""Live voice E2E: OGG download, STT boundary, catalog handoff, typed fallback (#3418).

Proves the Telegram voice journey end to end through the REAL registered
routes: ``Dispatcher.feed_update`` drives an actual voice Update through the
production middlewares and aiogram-dialog routers (client menu, funnel
criteria, catalog shell), the production voice adapter chain —
:meth:`aiogram.Bot.get_file` + :meth:`aiogram.Bot.download_file` on the real
aiogram client stack over a recorded ``BaseSession`` serving REAL OGG/Opus
bytes, then the production :func:`~telegram_bot.services.voice_transcription.transcribe_voice`
— and the transcript lands on the SAME real catalog search path as typed text
(:func:`~telegram_bot.dialogs.catalog._search.search_catalog_from_query` ->
:class:`~telegram_bot.services.apartment.apartment_catalog.ApartmentCatalog`
-> live Qdrant). Outgoing side effects are observed at the transport boundary.

Deterministic STT boundary (#3418, documented decision): the official
``AsyncOpenAI`` transcription client (production code path, untouched
lifecycle per #3388) is pointed at an IN-PROCESS loopback provider through
the SDK's own ``OPENAI_BASE_URL`` seam. The loopback provider records every
request, so the tests prove the STT boundary was crossed EXACTLY ONCE with a
typed request (model, language, ``voice.ogg`` filename, the exact downloaded
OGG bytes, config key) — and that no other provider endpoint (chat/LLM
assistant) is ever contacted. No paid provider, no fake key beyond the
harness config value, no fake SDK packages, no network egress: the autouse
fixture pins ``OPENAI_BASE_URL`` to the loopback for every scenario, so even
a production bug could not leak a request off-process.

Media limits characterization (issue RED-first note): production delegates
the platform media limits to Telegram itself — ``getFile`` refuses bot
downloads over 20 MB — and voice input degrades to the typed-input path on
every failure (download, provider error, timeout) with the preserved failure
copy. The tests pin exactly that behavior at the transport boundary.

Stack scoping (#3418, documented decision): the transcript must reach a REAL
apartment search. The production apartment search contract
(:meth:`~telegram_bot.services.apartment.apartments_service.ApartmentsService.scroll_with_filters`)
is a payload-filtered, price-ordered Qdrant scroll — no vector search happens
on this path — so the lane runs against TWO real dependencies: Qdrant (from
the run-owned harness compose stack, loopback-enforced) and Redis (a
disposable, authenticated container per module following the proven
``test_redis_modes_live.py`` (#3368) / funnel (#3413) / catalog (#3417)
conventions). No BGE-M3 embeddings are read or written: the tiny 3-row corpus
is seeded through the PRODUCTION payload contracts only — the canonical
collection schema (:func:`~scripts.demo_bootstrap.create_apartments_collection_schema`),
deterministic point ids (:func:`~src.runtime.qdrant.contracts.apartment_point_id`)
and the production :meth:`~src.models.apartment.ApartmentRecord.to_payload`
payload builder. Required mode (``E2E_HARNESS_REQUIRED=1``, legacy
``E2E_CORE_STRICT=1``) turns missing infrastructure into a FAILURE, never a
skip (#3414 policy).

Temp audio (#3418 acceptance): production buffers the downloaded audio in
memory (``io.BytesIO``) and never spills a temp file; the harness's own
temporary fixture file (the synthetic OGG the transport serves) is removed
at module teardown and PROVEN gone — also when a scenario above it failed.

Scenarios (issue #3418 acceptance):

1. Valid voice follows the production path: real ``getFile`` + multi-chunk
   download of the synthetic OGG through the recorded Telegram transport,
   exactly one loopback STT request carrying the downloaded bytes, and the
   transcript drives ONE real catalog search over live Qdrant that keeps the
   matching seeded row and excludes the pool-view and over-budget decoys.
2. Telegram refuses to serve the voice file (the Bot API ``getFile``
   behavior for oversized downloads) is safe: the preserved
   transcription-failure copy is shown and no STT request, no transcript
   echo, no search happens.
3. An STT timeout (provider stalls past ``voice_timeout``) is safe: the
   boundary was crossed exactly once, the failure copy degrades to typed
   input, and no downstream search runs.
4. A non-voice document inside the catalog window crosses no boundary at
   all: nothing is sent, nothing is transcribed, the dialog stays parked.
5. Voice-not-ready config hands the user to the proven typed-input path:
   no download, no STT, no fabricated output.

The bot is assembled once per module: aiogram-dialog routers are module
singletons, so a dispatcher can attach them exactly once per process
(production runs one bot per process). Per-test isolation comes from a fresh
transport session, a unique client id (FSM/throttle/Redis namespaces) and
exact run-owned Redis key cleanup (lead keys + the extraction cache entry).
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import shutil
import struct
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
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    Chat,
    Document,
    File,
    ForumTopicCreated,
    Message,
    Update,
    User,
    Voice,
)

from src.runtime.integrations.cache import CacheLayerManager
from src.runtime.integrations.redis_mode import RedisMode
from tests.e2e_core.live_harness import (
    LiveE2EEnv,
    RunNamespace,
    TeardownRegistry,
    guard_service_skip,
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
_MANAGERS_GROUP_ID = -100_3418_0001
_BOT_TOKEN = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"

# Voice configuration of the assembled production bot (#3240 fields).
_STT_MODEL = "whisper-e2e"
_VOICE_LANGUAGE = "ru"
_STT_CONFIG_KEY = "e2e-loopback-stt-key"
_VOICE_UNAVAILABLE_TEXT = "🎙 Голосовой ввод сейчас недоступен — напишите запрос текстом."
_RECOGNIZING_TEXT = "🎤 Распознаю голос..."
_RECOGNIZED_PREFIX = "📝 Распознано: "
_SEARCHING_TEXT = "🔍 Ищу подходящие варианты..."
_STT_FAILURE_TEXT = "Не удалось распознать речь. Попробуйте ещё раз или напишите запрос текстом."

# The synthetic voice message + served file (one deterministic OGG per module).
_VOICE_FILE_ID = "voice-e2e-3418-001"
_VOICE_FILE_PATH = "voice/file_3418.ogg"
_VOICE_FILE_URL = f"https://api.telegram.org/file/bot{_BOT_TOKEN}/{_VOICE_FILE_PATH}"

# The transcript the deterministic STT provider returns. Through the REAL
# regex extractor: "двушка" -> rooms=3, "до 90000 евро" -> max_price_eur=90000,
# "с видом на море" -> view_tags=["sea"].
_TRANSCRIPT = "двушка до 90000 евро с видом на море"

_EXTRACTION_CACHE_PREFIX = "extraction:v1:"
_MODULE_LOOP = pytest.mark.asyncio(loop_scope="module")


def _synthetic_ogg_opus() -> bytes:
    """Minimal structurally-correct Ogg/Opus capture (OpusHead page)."""
    opus_head = (
        b"OpusHead"
        + bytes([2, 1])
        + struct.pack("<H", 0)
        + struct.pack("<I", 48000)
        + struct.pack("<h", 0)
        + bytes([0])
    )
    return (
        b"OggS"
        + bytes([0, 2])
        + struct.pack("<q", 0)
        + struct.pack("<I", 0x3418)
        + struct.pack("<I", 0)
        + struct.pack("<I", 0)
        + bytes([1, len(opus_head)])
        + opus_head
    )


def _extraction_cache_key(query: str) -> str:
    """The production extraction-cache Redis key for ``query`` (#3238)."""
    digest = hashlib.sha256(query.lower().encode()).hexdigest()[:16]
    return _EXTRACTION_CACHE_PREFIX + digest


# ---------------------------------------------------------------------------
# Tiny deterministic seed corpus (the voice-search exactness anchors)
# ---------------------------------------------------------------------------

_SB = "Солнечный берег"

# All three rows satisfy the funnel criteria (city=СБ, 2bed -> rooms=3,
# mid budget 50k..100k) so the voice Update can be fed inside the real
# CatalogSG.results window; ONLY the first also satisfies the transcript's
# extracted filters (rooms=3, price <= 90000, view_tags sea).
SEED_ROWS: list[dict[str, Any]] = [
    {  # matches the voice query end to end
        "complex_name": "Sea Garden Residence",
        "city": _SB,
        "section": "A",
        "apartment_number": "101",
        "rooms": 3,
        "floor_label": "2",
        "area_m2": "55",
        "view_raw": "sea panorama",
        "price_eur": "80000",
        "price_bgn": "0",
        "is_furnished": "true",
        "has_floor_plan": "true",
        "has_photo": "true",
        "is_promotion": "false",
    },
    {  # pool view: kept by the funnel, excluded by the transcript's sea view
        "complex_name": "Pool Park Residence",
        "city": _SB,
        "section": "A",
        "apartment_number": "102",
        "rooms": 3,
        "floor_label": "3",
        "area_m2": "58",
        "view_raw": "pool",
        "price_eur": "85000",
        "price_bgn": "0",
        "is_furnished": "true",
        "has_floor_plan": "false",
        "has_photo": "true",
        "is_promotion": "false",
    },
    {  # 95 000 €: kept by the funnel, excluded by the transcript's max price
        "complex_name": "Sea Terrace Residence",
        "city": _SB,
        "section": "B",
        "apartment_number": "201",
        "rooms": 3,
        "floor_label": "1",
        "area_m2": "60",
        "view_raw": "sea panorama",
        "price_eur": "95000",
        "price_bgn": "0",
        "is_furnished": "false",
        "has_floor_plan": "false",
        "has_photo": "true",
        "is_promotion": "false",
    },
]


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
# Deterministic STT provider: in-process loopback transcription endpoint
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class STTRequest:
    """One recorded transcription request at the loopback STT boundary."""

    method: str
    path: str
    authorization: str
    body: bytes


class DeterministicSTTServer:
    """Loopback OpenAI-compatible transcription provider (#3418).

    Serves ``POST {base}/audio/transcriptions`` with the canned transcript on
    127.0.0.1 only. Every request is recorded so tests prove the STT boundary
    was crossed with a TYPED request (model/language/filename/audio bytes)
    and that nothing else — no assistant chat completion — ever left the bot.
    ``delay_seconds`` stalls the response to characterize the production
    ``voice_timeout`` handling.
    """

    def __init__(self, transcript: str = _TRANSCRIPT) -> None:
        self.transcript = transcript
        self.delay_seconds = 0.0
        self.requests: list[STTRequest] = []
        self._server: asyncio.Server | None = None
        self.port = 0
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._tasks):
            with contextlib.suppress(BaseException):
                await task

    def _record(self, request_line: bytes, headers: dict[str, str], body: bytearray) -> None:
        parts = request_line.split(b" ") if request_line else []
        self.requests.append(
            STTRequest(
                method=parts[0].decode("latin-1") if parts else "",
                path=parts[1].decode("latin-1") if len(parts) > 1 else "",
                authorization=headers.get("authorization", ""),
                body=bytes(body),
            )
        )

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        assert task is not None
        self._tasks.add(task)
        try:
            request_line = await reader.readline()
            headers: dict[str, str] = {}
            while True:
                line = await reader.readline()
                if line in (b"\r\n", b"\n", b""):
                    break
                name, _, value = line.decode("latin-1").partition(":")
                headers[name.strip().lower()] = value.strip()
            length = int(headers.get("content-length", "0"))
            body = bytearray()
            while len(body) < length:
                chunk = await reader.read(65536)
                if not chunk:
                    break
                body.extend(chunk)
            # Recorded BEFORE any stall: crossing the boundary is the
            # request's arrival, observable even when the client times out
            # and hangs up mid-stall.
            self._record(request_line, headers, body)
            if self.delay_seconds:
                await asyncio.sleep(self.delay_seconds)
            payload = json.dumps({"text": self.transcript}).encode("utf-8")
            writer.write(
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: application/json\r\n"
                + f"Content-Length: {len(payload)}\r\n".encode("latin-1")
                + b"Connection: close\r\n\r\n"
                + payload
            )
            await writer.drain()
        except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
            pass  # the client hit its timeout and hung up (voice_timeout scenario)
        finally:
            with contextlib.suppress(Exception):
                writer.close()
                await writer.wait_closed()
            self._tasks.discard(task)


# ---------------------------------------------------------------------------
# Deterministic Telegram transport: real client stack, recorded API + files
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TelegramCall:
    """One recorded Bot API call at the transport boundary."""

    method: str
    payload: dict[str, Any]
    result: Any = None


class RecordingVoiceTelegramSession(BaseSession):
    """In-process Telegram transport that SERVES the staged OGG file.

    ``make_request`` records every Bot API call; ``getFile`` resolves the
    synthetic voice's file path. ``stream_content`` is the real download
    boundary aiogram's ``Bot.download_file`` uses: it records the file URL
    aiogram built and streams the staged OGG payload in small chunks so the
    download loop accumulates the bytes exactly like production.
    """

    def __init__(self, file_payload: bytes) -> None:
        super().__init__()
        self.calls: list[TelegramCall] = []
        self.downloads: list[str] = []
        self.file_payload = file_payload
        self.fail_get_file_with: Exception | None = None
        self._next_message_id = 30_000
        self._next_topic_id = 3_600

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
        self.downloads.append(url)
        payload = self.file_payload
        assert payload, "the voice journey must stage the OGG payload it serves"
        for start in range(0, len(payload), 16):
            yield payload[start : start + 16]

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

        if name == "getFile" and self.fail_get_file_with is not None:
            failure = self.fail_get_file_with
            self.calls.append(TelegramCall(method=name, payload=payload))
            raise failure

        result: Any = True
        if name == "getFile":
            result = File(
                file_id=str(payload.get("file_id") or _VOICE_FILE_ID),
                file_unique_id="voice-unique-3418",
                file_size=len(self.file_payload),
                file_path=_VOICE_FILE_PATH,
            )
        elif name == "sendMessage":
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
class _VoiceStack:
    """Everything one voice module run owns: live services, bot, providers."""

    bot: Any
    env: LiveE2EEnv
    namespace: RunNamespace
    collection: str
    live_redis: LiveRedis
    stt: DeterministicSTTServer
    ogg_bytes: bytes
    temp_ogg_path: Path


async def _build_voice_bot(env: LiveE2EEnv, live: LiveRedis, collection: str, ogg: bytes) -> Any:
    """Assemble the production bot, voice-enabled, over real Redis/Qdrant."""
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
        # Voice enabled (#3240): the whole point of this lane. The STT key is
        # the harness config value; it only ever reaches the loopback provider.
        voice_enabled=True,
        llm_api_key=_STT_CONFIG_KEY,
        stt_model=_STT_MODEL,
        voice_language=_VOICE_LANGUAGE,
        voice_timeout=30,
        show_transcription=True,
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
    # Deterministic Telegram boundary: the real aiogram Bot on a recorded
    # session that serves the staged OGG. Swapped BEFORE the handoff
    # lifecycle builds the ForumBridge, so the bridge owns this transport.
    bot.bot = Bot(token=_BOT_TOKEN, session=RecordingVoiceTelegramSession(ogg))
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


def _require_qdrant(env: LiveE2EEnv) -> None:
    """Require the one live service this lane needs; required mode fails."""
    import httpx

    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{env.qdrant_url.rstrip('/')}/collections")
            response.raise_for_status()
    except Exception as exc:
        guard_service_skip(
            f"Qdrant unavailable at {env.qdrant_url}: {type(exc).__name__} — voice live "
            "harness cannot start"
        )


def _seed_owned_collection(env: LiveE2EEnv, collection: str) -> int:
    """Seed the run-owned collection through the PRODUCTION payload contracts.

    The canonical collection schema (contract payload indexes + strict mode),
    deterministic apartment point ids, and the production
    :meth:`ApartmentRecord.to_payload` payloads — exactly what the voice
    journey's payload-filtered scroll reads. No vectors: the apartment search
    contract on this path never touches them.
    """
    from qdrant_client import QdrantClient
    from qdrant_client import models as qmodels

    from scripts.demo_bootstrap import create_apartments_collection_schema
    from src.models.apartment import ApartmentRecord
    from src.runtime.qdrant.contracts import apartment_point_id

    client = QdrantClient(url=env.qdrant_url, api_key=env.qdrant_api_key, timeout=60)
    try:
        create_apartments_collection_schema(client, collection)
        client.upsert(
            collection_name=collection,
            points=[
                qmodels.PointStruct(
                    id=apartment_point_id(
                        row["complex_name"], row["section"], row["apartment_number"]
                    ),
                    vector={},
                    payload=ApartmentRecord.from_raw(row).to_payload(),
                )
                for row in SEED_ROWS
            ],
            wait=True,
        )
        count = client.count(collection_name=collection, exact=True).count
    finally:
        client.close()
    assert count == len(SEED_ROWS), f"seed point mismatch: {count}"
    return count


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def voice_stack(tmp_path_factory: pytest.TempPathFactory) -> AsyncIterator[_VoiceStack]:
    """One run-owned collection + one disposable Redis + one real bot + STT."""
    if not _docker_daemon_available():
        guard_service_skip("Docker daemon unavailable — voice live harness cannot start")
    env = LiveE2EEnv.from_env()
    _require_qdrant(env)

    namespace = RunNamespace.resolve()
    from tests.e2e_core.qdrant_helpers import generate_collection_name

    collection = generate_collection_name(namespace.run_id, namespace.worker)
    registry = TeardownRegistry(run_id=namespace.run_id)
    registry.register_collection(env.qdrant_url, collection)

    name = f"rag-e2e-3418-{uuid.uuid4().hex[:10]}"
    password = f"pw-{uuid.uuid4().hex}"
    live: LiveRedis | None = None
    bot: Any = None
    stt = DeterministicSTTServer()
    ogg = _synthetic_ogg_opus()
    temp_dir = tmp_path_factory.mktemp("voice-3418")
    temp_ogg = temp_dir / "voice_note_3418.ogg"
    temp_ogg.write_bytes(ogg)
    try:
        port = _start_redis_container(name, password)
        live = LiveRedis(name=name, password=password, port=port)

        seeded = _seed_owned_collection(env, collection)
        assert seeded == len(SEED_ROWS), f"seed mismatch: {seeded}"

        await stt.start()
        bot = await _build_voice_bot(env, live, collection, ogg)
        yield _VoiceStack(
            bot=bot,
            env=env,
            namespace=namespace,
            collection=collection,
            live_redis=live,
            stt=stt,
            ogg_bytes=ogg,
            temp_ogg_path=temp_ogg,
        )
    finally:
        if bot is not None:
            with contextlib.suppress(Exception):
                await bot._cache.close()
        if live is not None:
            _docker("rm", "-f", name)
        assert _container_gone(name), f"disposable Redis container {name} survived cleanup"
        await registry.teardown_and_verify()
        await stt.close()
        # Temp audio cleanup (#3418): the harness's exact fixture path is
        # removed even when a scenario failed, and PROVEN gone.
        temp_ogg.unlink(missing_ok=True)
        assert not temp_ogg.exists(), f"temp audio {temp_ogg} survived the harness teardown"


# ---------------------------------------------------------------------------
# Per-test journey: fresh transport, unique client id, exact key cleanup
# ---------------------------------------------------------------------------

_CLIENT_ID_SEQUENCE = iter(range(3418_0001, 3418_0001 + 100))


class _VoiceJourney:
    """One client's live voice journey against one real bot + live services."""

    redis_client: aioredis.Redis

    def __init__(self, stack: _VoiceStack, client_id: int) -> None:
        self.stack = stack
        self.bot = stack.bot
        self.transport: RecordingVoiceTelegramSession = stack.bot.bot.session
        self.stt = stack.stt
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
        self,
        text: str | None = None,
        *,
        contact: Any = None,
        voice: Voice | None = None,
        document: Document | None = None,
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
                voice=voice,
                document=document,
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
                chat_instance="voice-e2e",
                data=data,
                message=Message(
                    message_id=1,
                    date=datetime.now(UTC),
                    chat=Chat(id=self.client_id, type="private"),
                ),
            ),
        )
        await self.bot.dp.feed_update(self.bot.bot, update)

    async def feed_voice(self, *, file_id: str = _VOICE_FILE_ID) -> None:
        """Feed the synthetic Telegram voice note through the real dispatcher."""
        await self.feed_message(
            voice=Voice(
                file_id=file_id,
                file_unique_id=f"{file_id}-unique",
                duration=3,
                mime_type="audio/ogg",
            )
        )

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

    def new_texts(self, baseline: int) -> list[str]:
        """Client-visible texts produced after ``baseline`` was captured."""
        return self.transport.texts_sent_to(self.client_id)[baseline:]

    def new_card_texts(self, baseline: int) -> list[str]:
        return [
            str(call.payload.get("text") or "")
            for call in self.transport.cards_sent_to(self.client_id)[baseline:]
        ]


@pytest_asyncio.fixture(loop_scope="module")
async def journey(voice_stack: _VoiceStack) -> AsyncIterator[_VoiceJourney]:
    """One client's journey: fresh recorded transport, unique id, key cleanup."""
    # A fresh recorded session per test keeps side-effect counts absolute.
    voice_stack.bot.bot.session = RecordingVoiceTelegramSession(voice_stack.ogg_bytes)
    client = aioredis.from_url(voice_stack.live_redis.url, decode_responses=True)
    current = _VoiceJourney(voice_stack, next(_CLIENT_ID_SEQUENCE))
    current.redis_client = client
    try:
        yield current
    finally:
        await client.delete(
            f"lead_request:v2:{current.client_id}",
            f"lead_request:{current.client_id}",
            f"lead_notify:v2:{current.client_id}",
            _extraction_cache_key(_TRANSCRIPT),
        )
        await client.aclose()


@pytest.fixture(autouse=True)
def _loopback_stt_only(voice_stack: _VoiceStack, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin STT at the in-process loopback provider for EVERY scenario.

    Even a production bug that tried to call the real provider could not
    leave the process: the official SDK reads ``OPENAI_BASE_URL``, and it
    points at this module's loopback server for the duration of each test.
    """
    monkeypatch.setenv("OPENAI_BASE_URL", voice_stack.stt.base_url)


@contextlib.contextmanager
def _bot_config_override(journey: _VoiceJourney, **updates: Any) -> Any:
    """Swap the injected bot_config for one journey step (funnel-lane seam)."""
    original = journey.bot.dp["bot_config"]
    journey.bot.dp["bot_config"] = original.model_copy(update=updates)
    try:
        yield
    finally:
        journey.bot.dp["bot_config"] = original


async def _run_funnel_search_to_cards(journey: _VoiceJourney) -> int:
    """Menu -> funnel criteria -> 'Карточками' search -> cards; card baseline."""
    baseline = len(journey.transport.cards_sent_to(journey.client_id))
    await journey.feed_message(_MENU_SEARCH_TEXT)
    await journey.feed_callback(f"city:{_SB}")
    await journey.feed_callback("property_type:2bed")
    await journey.feed_callback("budget:mid")
    await journey.feed_callback("pref_done")
    await journey.feed_callback("search_cards")
    cards = journey.new_card_texts(baseline)
    assert len(cards) == len(SEED_ROWS), (
        f"the funnel search must render every seeded row before the voice step: {cards}"
    )
    return len(journey.transport.cards_sent_to(journey.client_id))


# ---------------------------------------------------------------------------
# Scenario 1 — valid voice: production download -> STT once -> real search
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(300)
async def test_valid_voice_downloads_ogg_transcribes_once_and_drives_real_catalog_search(
    journey: _VoiceJourney,
) -> None:
    stt = journey.stt
    stt_baseline = len(stt.requests)

    cards_baseline = await _run_funnel_search_to_cards(journey)
    texts_baseline = len(journey.transport.texts_sent_to(journey.client_id))

    # The synthetic voice note enters through the REAL dispatcher route.
    await journey.feed_voice()

    # --- Telegram download boundary: typed getFile + real file URL ----------
    get_file_calls = journey.transport.calls_of("getFile")
    assert len(get_file_calls) == 1, get_file_calls
    assert get_file_calls[0].payload["file_id"] == _VOICE_FILE_ID
    assert journey.transport.downloads == [_VOICE_FILE_URL], journey.transport.downloads

    # --- STT boundary: crossed EXACTLY ONCE, with a typed request ----------
    stt_requests = stt.requests[stt_baseline:]
    assert len(stt.requests) - stt_baseline == 1, stt_requests
    request = stt_requests[0]
    assert request.method == "POST"
    assert request.path == "/v1/audio/transcriptions", request.path
    assert request.authorization == f"Bearer {_STT_CONFIG_KEY}"
    body = request.body
    assert f'name="model"\r\n\r\n{_STT_MODEL}'.encode() in body, body[:400]
    assert f'name="language"\r\n\r\n{_VOICE_LANGUAGE}'.encode() in body, body[:400]
    assert b'filename="voice.ogg"' in body, body[:400]
    assert journey.stack.ogg_bytes in body, "the downloaded OGG bytes must reach the STT call"
    # The loopback transcription endpoint is the ONLY provider ever contacted
    # in the whole journey — no assistant/LLM chat completion happened.
    assert all(r.path == "/v1/audio/transcriptions" for r in stt.requests), stt.requests

    # --- Exactly one safe response set, driven by the transcript ----------
    new_texts = journey.new_texts(texts_baseline)
    assert new_texts.count(_RECOGNIZING_TEXT) == 1, new_texts
    recognized = [t for t in new_texts if t.startswith(_RECOGNIZED_PREFIX)]
    assert recognized == [_RECOGNIZED_PREFIX + _TRANSCRIPT], new_texts
    assert new_texts.count(_SEARCHING_TEXT) == 1, new_texts

    lists = [t for t in new_texts if "Найдено <b>1</b> апартаментов" in t]
    assert len(lists) == 1, f"exactly one result list may be rendered for the voice: {new_texts}"
    list_text = lists[0]
    assert "Sea Garden Residence" in list_text, list_text
    assert "80 000 €" in list_text, list_text
    assert "Pool Park Residence" not in list_text, "the sea-view filter must exclude the pool row"
    assert "Sea Terrace Residence" not in list_text, "the 90k max price must exclude the 95k row"

    # The transcript routed the dialog to the same real catalog shell.
    assert await journey.dialog_state() == "CatalogSG:results"
    # No further cards were fabricated by the voice path (the funnel search
    # rendered all three; the voice search renders the list view only).
    assert len(journey.new_card_texts(cards_baseline)) == 0


# ---------------------------------------------------------------------------
# Scenario 2 — Telegram refuses the download (oversized-file Bot API copy)
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(240)
async def test_download_failure_is_safe_with_no_stt_and_no_downstream_search(
    journey: _VoiceJourney,
) -> None:
    stt = journey.stt
    stt_baseline = len(stt.requests)
    await _run_funnel_search_to_cards(journey)
    texts_baseline = len(journey.transport.texts_sent_to(journey.client_id))

    # The Bot API refuses bot downloads over 20 MB at getFile; the recorded
    # transport reproduces exactly that platform behavior deterministically.
    journey.transport.fail_get_file_with = TelegramBadRequest(
        method=None, message="Bad Request: file is too big"
    )
    try:
        await journey.feed_voice()
    finally:
        journey.transport.fail_get_file_with = None

    new_texts = journey.new_texts(texts_baseline)
    assert new_texts.count(_RECOGNIZING_TEXT) == 1, new_texts
    assert new_texts.count(_STT_FAILURE_TEXT) == 1, new_texts
    assert not any(t.startswith(_RECOGNIZED_PREFIX) for t in new_texts), new_texts
    assert not any("Найдено <b>" in t for t in new_texts), (
        f"a failed download must not reach the catalog search: {new_texts}"
    )

    # No STT request, no transcript, and the catalog window stays usable.
    assert len(stt.requests) - stt_baseline == 0, stt.requests[stt_baseline:]
    assert await journey.dialog_state() == "CatalogSG:results"


# ---------------------------------------------------------------------------
# Scenario 3 — STT timeout: boundary crossed once, typed fallback, no search
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(240)
async def test_stt_timeout_degrades_to_typed_input_and_runs_no_search(
    journey: _VoiceJourney,
) -> None:
    stt = journey.stt
    stt_baseline = len(stt.requests)
    await _run_funnel_search_to_cards(journey)
    texts_baseline = len(journey.transport.texts_sent_to(journey.client_id))

    # One-second voice budget (per-test injected config seam); the loopback
    # provider stalls past it before answering.
    stt.delay_seconds = 3.0
    try:
        with _bot_config_override(journey, voice_timeout=1):
            await journey.feed_voice()
    finally:
        stt.delay_seconds = 0.0

    new_texts = journey.new_texts(texts_baseline)
    assert new_texts.count(_RECOGNIZING_TEXT) == 1, new_texts
    assert new_texts.count(_STT_FAILURE_TEXT) == 1, new_texts
    assert not any(t.startswith(_RECOGNIZED_PREFIX) for t in new_texts), new_texts
    assert not any("Найдено <b>" in t for t in new_texts), (
        f"a timed-out transcription must not reach the catalog search: {new_texts}"
    )

    # The boundary WAS crossed exactly once before the timeout, and nothing
    # else was ever sent to any provider endpoint.
    assert len(stt.requests) - stt_baseline == 1, stt.requests[stt_baseline:]
    assert all(r.path == "/v1/audio/transcriptions" for r in stt.requests), stt.requests
    assert await journey.dialog_state() == "CatalogSG:results"


# ---------------------------------------------------------------------------
# Scenario 4 — non-voice media crosses no boundary at all
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(240)
async def test_document_in_catalog_window_crosses_no_boundary(journey: _VoiceJourney) -> None:
    stt = journey.stt
    stt_baseline = len(stt.requests)
    await _run_funnel_search_to_cards(journey)
    texts_baseline = len(journey.transport.texts_sent_to(journey.client_id))
    downloads_baseline = len(journey.transport.downloads)

    await journey.feed_message(
        document=Document(
            file_id="doc-e2e-3418",
            file_unique_id="doc-e2e-3418-unique",
            mime_type="application/pdf",
        )
    )

    # The dialog re-renders its window text for the unsupported type
    # (aiogram-dialog's real unmatched-input behavior): nothing fabricated,
    # and the voice/STT/download boundaries are never crossed.
    assert journey.new_texts(texts_baseline) == ["Каталог активен."], journey.new_texts(
        texts_baseline
    )
    assert len(stt.requests) - stt_baseline == 0, stt.requests[stt_baseline:]
    assert len(journey.transport.downloads) == downloads_baseline
    assert await journey.dialog_state() == "CatalogSG:results", (
        "an unsupported media type must not disturb the catalog window"
    )


# ---------------------------------------------------------------------------
# Scenario 5 — voice not ready: preserved typed-input handoff
# ---------------------------------------------------------------------------


@_MODULE_LOOP
@pytest.mark.timeout(240)
async def test_voice_not_ready_hands_user_to_typed_input(journey: _VoiceJourney) -> None:
    stt = journey.stt
    stt_baseline = len(stt.requests)
    await _run_funnel_search_to_cards(journey)
    texts_baseline = len(journey.transport.texts_sent_to(journey.client_id))
    downloads_baseline = len(journey.transport.downloads)

    with _bot_config_override(journey, voice_enabled=False):
        await journey.feed_voice()

    new_texts = journey.new_texts(texts_baseline)
    assert new_texts == [_VOICE_UNAVAILABLE_TEXT], new_texts
    # The typed handoff crossed NO provider boundary.
    assert len(stt.requests) - stt_baseline == 0, stt.requests[stt_baseline:]
    assert len(journey.transport.downloads) == downloads_baseline
    assert await journey.dialog_state() == "CatalogSG:results"


# ---------------------------------------------------------------------------
# Harness self-check — the temp fixture audio the transport served is real
# ---------------------------------------------------------------------------


def test_voice_fixture_bytes_are_structurally_valid_ogg_opus(
    voice_stack: _VoiceStack,
) -> None:
    ogg = voice_stack.ogg_bytes
    assert ogg[:4] == b"OggS", ogg[:8]
    assert b"OpusHead" in ogg, ogg
    assert voice_stack.temp_ogg_path.read_bytes() == ogg, "temp fixture must serve what it holds"
    assert _extraction_cache_key(_TRANSCRIPT).startswith(_EXTRACTION_CACHE_PREFIX)
