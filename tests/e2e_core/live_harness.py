"""Hermetic live E2E harness for the golden-path capability lanes (#3414).

Contract (issue #3414, A10/A11):

- One run id per invocation (``E2E_RUN_ID``, set by the canonical Make entry
  or generated once per pytest process in ``tests/conftest.py``) and one
  isolated Compose project (``rag-e2e-<run-id>``) per run.
- Per xdist worker: a UUID Qdrant collection, a Redis prefix/database, and a
  PostgreSQL schema, all derived from :class:`RunNamespace`.
- Real local Redis/Qdrant/PostgreSQL/BGE-M3 only: loopback endpoints are
  enforced (explicit ``E2E_HARNESS_ALLOW_REMOTE=1`` escapes for remote dev
  Docker hosts), and known production collection names are refused.
- Required mode (``E2E_HARNESS_REQUIRED=1``; legacy ``E2E_CORE_STRICT``) has
  ZERO service-related skips: missing/unready infrastructure fails.
- Teardown deletes only exact run-owned resources and proves zero leaks;
  deletions of anything else are refused.
- No report artifacts are written unless ``E2E_CORE_ARTIFACT_DIR`` is set.
- Provider transports (Telegram/LLM/CRM/STT) are deterministic in-process
  adapters; no fake packages are injected into ``sys.modules``.

The safety/policy helpers live in ``qdrant_helpers.py`` (stdlib-only) and the
top of this module; consumers that only need policy import those without
pulling service clients.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest
import yaml

from src.runtime.config import GraphConfig
from src.runtime.services.qdrant import QdrantService
from tests.e2e_core.qdrant_helpers import (
    HarnessSafetyError,
    QdrantTestContext,
    assert_owned_collection_name,
    generate_collection_name,
    should_keep_collection,
    validate_run_id,
)


__all__ = [
    "DeterministicSTT",
    "DeterministicTelegramTransport",
    "FailingLLMConfig",
    "FakeLLMConfig",
    "GoldenCase",
    "HarnessSafetyError",
    "LiveBGEEmbeddings",
    "LiveBGESparseEmbeddings",
    "LiveCoreHarness",
    "LiveE2EEnv",
    "MarkdownChunk",
    "MockCrmClient",
    "NoopLiveCache",
    "PostgresLease",
    "RedisLease",
    "RunNamespace",
    "TeardownRegistry",
    "build_live_core_harness",
    "cleanup_collection",
    "compose_project_name",
    "dense_dimension",
    "guard_service_skip",
    "health_model_loaded",
    "index_fixture_documents",
    "load_golden_case",
    "make_qdrant_context",
    "no_fake_sdk_modules",
    "recreate_collection",
    "require_live_services",
    "require_live_stack",
    "required_mode",
    "validate_report_artifact",
    "verify_bge_runtime",
    "write_case_artifact",
]


FIXTURES_DIR = Path(__file__).parent / "fixtures"
DOCS_DIR = FIXTURES_DIR / "docs"
GOLDEN_CASES_PATH = FIXTURES_DIR / "golden_cases.yaml"

_TRUTHY = {"1", "true", "yes", "on"}
# Loopback hosts the harness may contact (real LOCAL services, #3414).
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
# aiogram-family modules that must never be MagicMock stand-ins in the e2e
# lane (mirrors tests/e2e/conftest.py restoration scope).
_FAKE_SDK_MODULES = ("aiogram", "aiogram_dialog", "fluentogram", "fluent_compiler")

# Default local endpoints for the run-owned Compose project.
DEFAULT_QDRANT_URL = "http://127.0.0.1:6333"
DEFAULT_BGE_M3_URL = "http://127.0.0.1:8000"
DEFAULT_REDIS_HOST = "127.0.0.1:6379"
DEFAULT_POSTGRES_DSN = "postgresql://postgres@127.0.0.1:5432/realestate"

REDIS_OWNER_MARKER = "__owner"
REDIS_OWNER_TTL = 3600


# ---------------------------------------------------------------------------
# Policy: required mode fails where optional developer mode may skip
# ---------------------------------------------------------------------------


def required_mode() -> bool:
    """True when the harness runs in required (never-skip) mode.

    ``E2E_HARNESS_REQUIRED=1`` is the canonical flag; ``E2E_CORE_STRICT=1``
    remains accepted as the legacy alias from the pre-#3414 core lane.
    """
    return any(
        os.environ.get(name, "").strip().lower() in _TRUTHY
        for name in ("E2E_HARNESS_REQUIRED", "E2E_CORE_STRICT")
    )


def guard_service_skip(reason: str, *, required: bool | None = None) -> None:
    """Fail in required mode, skip otherwise — never both, never silent."""
    if required if required is not None else required_mode():
        pytest.fail(reason)
    pytest.skip(f"{reason} (set E2E_HARNESS_REQUIRED=1 to make this a failure)")


def allow_remote_services() -> bool:
    """True when the documented remote-dev-Docker escape hatch is enabled."""
    return os.environ.get("E2E_HARNESS_ALLOW_REMOTE", "").strip().lower() in _TRUTHY


def no_fake_sdk_modules() -> list[str]:
    """Return aiogram-family module names currently faked by MagicMocks.

    The e2e lane fails closed on these: deterministic provider adapters own
    all provider behavior, and fake packages in ``sys.modules`` would silently
    replace the real client stack.
    """
    from unittest.mock import MagicMock

    offenders: list[str] = []
    for name in _FAKE_SDK_MODULES:
        module = sys_modules().get(name)
        if module is not None and isinstance(module, MagicMock):
            offenders.append(name)
    return offenders


def sys_modules() -> dict[str, Any]:  # pragma: no cover - indirection helper
    import sys

    return sys.modules


# ---------------------------------------------------------------------------
# Run namespace: one run id, per-worker isolated resources, compose project
# ---------------------------------------------------------------------------


def compose_project_name(run_id: str) -> str:
    """The isolated Compose project for one harness run."""
    validate_run_id(run_id)
    return f"rag-e2e-{run_id}"


@dataclass(frozen=True)
class RunNamespace:
    """Run/worker-owned resource names for one harness invocation.

    Attributes:
        run_id: 12-hex run label shared by every xdist worker of the run.
        worker: ``main`` or ``gw<N>`` (``PYTEST_XDIST_WORKER``).
        qdrant_collection: UUID collection owned by this worker.
        redis_prefix: Key prefix owned by this worker.
        redis_db: Logical Redis database owned by this worker (1..15).
        postgres_schema: Schema identifier owned by this worker.
    """

    run_id: str
    worker: str

    @property
    def qdrant_collection(self) -> str:
        return generate_collection_name(self.run_id, self.worker)

    @property
    def redis_prefix(self) -> str:
        return f"rag_e2e:{self.run_id}:{self.worker}:"

    @property
    def postgres_schema(self) -> str:
        return f"rag_e2e_{self.run_id}_{self.worker}"

    @property
    def compose_project(self) -> str:
        return compose_project_name(self.run_id)

    @staticmethod
    def redis_db_for_worker(worker: str) -> int:
        """Deterministic logical Redis DB for a worker (``main`` uses db 1)."""
        from tests.e2e_core.qdrant_helpers import validate_worker

        validate_worker(worker)
        if worker == "main":
            return 1
        index = int(worker[2:])
        return 2 + (index % 14)

    @property
    def redis_db(self) -> int:
        return RunNamespace.redis_db_for_worker(self.worker)

    @classmethod
    def resolve(cls, worker: str | None = None) -> RunNamespace:
        """Resolve the namespace from ``E2E_RUN_ID`` (or a fresh run id).

        The canonical entry exports ``E2E_RUN_ID``; when absent, each pytest
        process generates one run id (``tests/conftest.py`` pins it once per
        invocation so xdist workers inherit the same id).
        """
        worker_label = worker or os.environ.get("PYTEST_XDIST_WORKER") or "main"
        run_id = os.environ.get("E2E_RUN_ID") or uuid.uuid4().hex[:12]
        return cls(run_id=validate_run_id(run_id), worker=worker_label)


# ---------------------------------------------------------------------------
# Golden-case fixtures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GoldenCase:
    """Product golden-case assertions loaded from YAML fixtures."""

    id: str
    query: str
    must_retrieve: list[str]
    must_contain: list[str]
    must_not_contain: list[str]
    answer_policy: str


@dataclass(frozen=True)
class LiveE2EEnv:
    """Resolved service endpoints for the live core E2E test."""

    qdrant_url: str
    bge_m3_url: str
    qdrant_api_key: str | None = None
    strict: bool = False
    real_llm: bool = False
    required: bool = False

    @classmethod
    def from_env(cls) -> LiveE2EEnv:
        """Resolve live-test endpoints; reject non-loopback endpoints."""
        qdrant_url = (
            os.getenv("E2E_CORE_QDRANT_URL") or os.getenv("QDRANT_URL") or DEFAULT_QDRANT_URL
        )
        bge_m3_url = os.getenv("E2E_CORE_BGE_URL") or os.getenv("BGE_M3_URL") or DEFAULT_BGE_M3_URL
        cls.assert_safe_local_url(qdrant_url, label="QDRANT_URL")
        cls.assert_safe_local_url(bge_m3_url, label="BGE_M3_URL")
        required = required_mode()
        return cls(
            qdrant_url=qdrant_url,
            bge_m3_url=bge_m3_url,
            qdrant_api_key=os.getenv("QDRANT_API_KEY") or None,
            strict=required,
            real_llm=_truthy(os.getenv("E2E_CORE_REAL_LLM")),
            required=required,
        )

    @staticmethod
    def assert_safe_local_url(url: str, *, label: str = "endpoint") -> str:
        """Return ``url`` when it points at loopback; raise otherwise.

        Known production endpoints are unreachable by construction: the live
        harness only ever talks to the run's local Compose project (unless
        ``E2E_HARNESS_ALLOW_REMOTE=1`` documents a remote dev Docker host).
        """
        host = _url_host(url)
        if host is None:
            raise HarnessSafetyError(f"{label} {url!r} is not a valid URL")
        if host in _LOOPBACK_HOSTS or allow_remote_services():
            return url
        raise HarnessSafetyError(
            f"{label} must be loopback (127.0.0.1/localhost/[::1]); got {url!r}. "
            "The harness runs against the run-owned local Compose project (#3414)."
        )


def _url_host(url: str) -> str | None:
    try:
        return httpx.URL(url).host
    except Exception:
        return None


@dataclass
class MarkdownChunk:
    """Minimal chunk shape accepted by QdrantHybridWriter."""

    text: str
    order: int
    chunk_id: int
    document_name: str
    extra_metadata: dict[str, Any]


# ---------------------------------------------------------------------------
# Deterministic provider adapters (Telegram / CRM / LLM / STT)
# ---------------------------------------------------------------------------


@dataclass
class MockCrmClient:
    """Recording CRM mock for HITL E2E assertions."""

    writes: list[dict[str, Any]] = field(default_factory=list)

    async def create_lead(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.writes.append({"action": "create_lead", "payload": payload})
        return {"id": len(self.writes), **payload}

    async def schedule_viewing(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.writes.append({"action": "schedule_viewing", "payload": payload})
        return {"id": len(self.writes), **payload}

    async def request_documents(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.writes.append({"action": "request_documents", "payload": payload})
        return {"id": len(self.writes), **payload}


@dataclass
class DeterministicSTT:
    """In-process speech-to-text adapter returning a canned transcript."""

    transcript: str = "двушка до 100 тысяч у моря"
    calls: int = 0

    async def transcribe(self, audio_bytes: bytes) -> str:
        self.calls += 1
        return self.transcript


@dataclass
class DeterministicTelegramTransport:
    """In-process Telegram transport recording outgoing messages."""

    sent: list[SimpleNamespace] = field(default_factory=list)
    _next_id: int = 1

    async def send_message(self, chat_id: int, text: str) -> str:
        message_id = f"det-{self._next_id}"
        self._next_id += 1
        self.sent.append(SimpleNamespace(chat_id=chat_id, text=text, message_id=message_id))
        return message_id


class NoopLiveCache:
    """Small async cache adapter that keeps the live test focused on retrieval."""

    async def get_bge_m3_query_bundle(self, query: str) -> None:
        return None

    async def store_bge_m3_query_bundle(self, query: str, bundle: Any) -> None:
        return None

    async def get_embedding(self, query: str) -> None:
        return None

    async def store_embedding(self, query: str, vector: list[float]) -> None:
        return None

    async def get_sparse_embedding(self, query: str) -> None:
        return None

    async def store_sparse_embedding(self, query: str, vector: Any) -> None:
        return None

    async def check_semantic(self, **kwargs: Any) -> None:
        return None

    async def get_search_results(
        self,
        dense_vector: list[float],
        filters: dict[str, Any] | None = None,
        retrieval_config: dict[str, Any] | None = None,
    ) -> None:
        return None

    async def store_search_results(
        self,
        dense_vector: list[float],
        filters: dict[str, Any] | None,
        results: list[dict[str, Any]],
        retrieval_config: dict[str, Any] | None = None,
    ) -> None:
        return None

    async def get_rerank_results(
        self, query: str, documents: list[dict[str, Any]], top_k: int
    ) -> None:
        return None

    async def store_rerank_results(
        self,
        query: str,
        documents: list[dict[str, Any]],
        top_k: int,
        reranked: list[dict[str, Any]],
    ) -> None:
        return None


class LiveBGEEmbeddings:
    """No-ColBERT BGE adapter for the first live RRF golden path."""

    def __init__(self, base_url: str) -> None:
        from src.services.bge_m3_client import BGEM3Client

        self._client = BGEM3Client(base_url=base_url, timeout=120.0)

    async def aembed_hybrid(self, text: str) -> tuple[list[float], dict[str, Any]]:
        result = await self._client.encode_hybrid([text])
        return result.dense_vecs[0], result.lexical_weights[0]

    async def aembed_query(self, text: str) -> list[float]:
        result = await self._client.encode_dense([text])
        return result.vectors[0]

    async def aclose(self) -> None:
        await self._client.aclose()


class LiveBGESparseEmbeddings:
    """Sparse-only BGE adapter for fallback paths in rag_pipeline."""

    def __init__(self, base_url: str) -> None:
        from src.services.bge_m3_client import BGEM3Client

        self._client = BGEM3Client(base_url=base_url, timeout=120.0)

    async def aembed_query(self, text: str) -> dict[str, Any]:
        result = await self._client.encode_sparse([text])
        return result.weights[0]

    async def aclose(self) -> None:
        await self._client.aclose()


class FakeLLMConfig:
    """GraphConfig-compatible deterministic LLM config for golden-case assertions."""

    domain = "недвижимость в Болгарии"
    llm_model = "fake-live-e2e"
    llm_temperature = 0.0
    generate_max_tokens = 600
    show_sources = False
    response_style_enabled = False
    response_style_shadow_mode = False

    def create_llm(self, *, auto_trace: bool = False) -> Any:
        return _FakeLLM()

    def get_reasoning_kwargs(self) -> dict[str, Any]:
        return {}


@dataclass(frozen=True)
class FailingLLMConfig:
    """GraphConfig-compatible config that simulates an LLM provider failure."""

    error_message: str = "llm provider unavailable"
    domain: str = "недвижимость в Болгарии"
    llm_model: str = "failing-live-e2e"
    llm_temperature: float = 0.0
    generate_max_tokens: int = 600
    show_sources: bool = False
    response_style_enabled: bool = False
    response_style_shadow_mode = False

    def create_llm(self, *, auto_trace: bool = False) -> Any:
        return _FailingLLM(self.error_message)

    def get_reasoning_kwargs(self) -> dict[str, Any]:
        return {}


@dataclass
class LiveCoreHarness:
    """Created live dependencies plus async cleanup."""

    dependencies: Any
    cleanup: Callable[[], Any]

    async def aclose(self) -> None:
        await self.cleanup()


def load_golden_case(case_id: str) -> GoldenCase:
    """Load a single golden case from ``golden_cases.yaml``."""

    cases = yaml.safe_load(GOLDEN_CASES_PATH.read_text(encoding="utf-8"))
    if not isinstance(cases, list):
        raise ValueError("golden_cases.yaml must contain a list of cases")

    for raw in cases:
        if isinstance(raw, dict) and raw.get("id") == case_id:
            return GoldenCase(
                id=str(raw["id"]),
                query=str(raw["query"]),
                must_retrieve=[str(value) for value in raw.get("must_retrieve", [])],
                must_contain=[str(value) for value in raw.get("must_contain", [])],
                must_not_contain=[str(value) for value in raw.get("must_not_contain", [])],
                answer_policy=str(raw["answer_policy"]),
            )

    raise KeyError(f"Golden case not found: {case_id}")


def write_case_artifact(
    *,
    case: GoldenCase,
    collection_name: str,
    response_text: str,
    retrieved_doc_ids: list[str],
    route: str,
    error_type: str | None,
) -> Path | None:
    """Write a debugging artifact only when explicitly opted in (#3414).

    No report artifacts are produced by default; exporting
    ``E2E_CORE_ARTIFACT_DIR=<dir>`` turns artifact writing on for one run.
    """

    artifact_root = os.getenv("E2E_CORE_ARTIFACT_DIR")
    if not artifact_root:
        return None
    artifact_dir = Path(artifact_root)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"{case.id}.json"
    payload = {
        "case": asdict(case),
        "collection_name": collection_name,
        "route": route,
        "error_type": error_type,
        "retrieved_doc_ids": retrieved_doc_ids,
        "response_text": response_text,
    }
    artifact_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact_path


def validate_report_artifact(path: Path | None) -> bool:
    """True when ``path`` is an existing harness case artifact."""
    return bool(path) and Path(path).is_file()  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Live service guards
# ---------------------------------------------------------------------------


async def require_live_services(env: LiveE2EEnv) -> None:
    """Require Qdrant and BGE-M3: fail in required mode, skip otherwise."""

    failures: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{env.qdrant_url.rstrip('/')}/collections")
            response.raise_for_status()
    except Exception as exc:
        failures.append(f"Qdrant unavailable at {env.qdrant_url}: {type(exc).__name__}")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{env.bge_m3_url.rstrip('/')}/encode/dense",
                json={"texts": ["health check"], "batch_size": 1, "max_length": 32},
            )
            response.raise_for_status()
    except Exception as exc:
        failures.append(f"BGE-M3 unavailable at {env.bge_m3_url}: {type(exc).__name__}")

    failures.extend(real_llm_config_errors(env))

    if not failures:
        return

    guard_service_skip("; ".join(failures), required=env.required or None)


async def _probe_qdrant(qdrant_url: str) -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(f"{qdrant_url.rstrip('/')}/collections")
        response.raise_for_status()


async def _probe_bge(bge_m3_url: str) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{bge_m3_url.rstrip('/')}/encode/dense",
            json={"texts": ["health check"], "batch_size": 1, "max_length": 32},
        )
        response.raise_for_status()


async def _probe_redis(db: int) -> None:
    import redis.asyncio as aioredis

    client = aioredis.from_url(_redis_url_with_db(None, db), socket_connect_timeout=2)
    try:
        await cast("Awaitable[Any]", client.ping())
    finally:
        with contextlib.suppress(Exception):
            await cast("Awaitable[Any]", client.aclose())


def _postgres_dsn_from_env() -> str:
    dsn = os.getenv("POSTGRES_DSN") or os.getenv("REALESTATE_DATABASE_URL")
    if dsn:
        return dsn
    password = os.getenv("POSTGRES_PASSWORD", "")
    if password:
        return f"postgresql://postgres:{password}@127.0.0.1:5432/realestate"
    return DEFAULT_POSTGRES_DSN


async def _probe_postgres(dsn: str) -> None:
    import asyncpg

    connection = await asyncpg.connect(dsn, timeout=5)
    try:
        await connection.fetchval("SELECT 1")
    finally:
        await connection.close()


async def collect_stack_failures(env: LiveE2EEnv) -> list[str]:
    """Probe the full local stack (Qdrant/BGE/Redis/PostgreSQL); return errors."""
    failures: list[str] = []
    try:
        await _probe_qdrant(env.qdrant_url)
    except Exception as exc:
        failures.append(f"Qdrant unavailable at {env.qdrant_url}: {type(exc).__name__}")
    try:
        await _probe_bge(env.bge_m3_url)
    except Exception as exc:
        failures.append(f"BGE-M3 unavailable at {env.bge_m3_url}: {type(exc).__name__}")
    try:
        await _probe_redis(RunNamespace.resolve().redis_db)
    except Exception as exc:
        failures.append(f"Redis unavailable: {type(exc).__name__}")
    try:
        await _probe_postgres(_postgres_dsn_from_env())
    except Exception as exc:
        failures.append(f"PostgreSQL unavailable: {type(exc).__name__}")
    return failures


async def require_live_stack(env: LiveE2EEnv) -> None:
    """Require the full real stack; required mode fails, optional skips."""

    failures = await collect_stack_failures(env)
    failures.extend(real_llm_config_errors(env))
    if not failures:
        return
    guard_service_skip("; ".join(failures), required=env.required or None)


def health_model_loaded(payload: dict[str, Any]) -> bool:
    """True when a BGE /health payload reports the model actually loaded."""
    return bool(payload.get("model_loaded"))


def dense_dimension(payload: dict[str, Any]) -> int:
    """Dimension of the first dense vector in an /encode/dense payload."""
    vectors = payload.get("dense_vecs") or []
    if not vectors:
        return 0
    return len(vectors[0])


async def verify_bge_runtime(env: LiveE2EEnv, *, expected_dimension: int = 1024) -> dict[str, Any]:
    """Prove the running BGE-M3 serves the real pinned model.

    Runtime-mode artifact gate (#3414): the static 41-byte CI fixture (or any
    substituted model) cannot produce a health check with ``model_loaded``
    plus a full-dimension dense encoding — this probe fails in required mode
    when either is missing.
    """

    async with httpx.AsyncClient(timeout=30.0) as client:
        health = await client.get(f"{env.bge_m3_url.rstrip('/')}/health")
        health.raise_for_status()
        health_payload = health.json()

        encode = await client.post(
            f"{env.bge_m3_url.rstrip('/')}/encode/dense",
            json={"texts": ["проверка связи"], "batch_size": 1, "max_length": 256},
        )
        encode.raise_for_status()
        encode_payload = encode.json()

    problems: list[str] = []
    if not health_model_loaded(health_payload):
        problems.append(f"/health does not report model_loaded: {health_payload}")
    dimension = dense_dimension(encode_payload)
    if dimension != expected_dimension:
        problems.append(
            f"/encode/dense returned dimension {dimension}, expected {expected_dimension}"
        )
    if problems:
        guard_service_skip(
            f"BGE-M3 runtime verification failed at {env.bge_m3_url}: " + "; ".join(problems),
            required=env.required or None,
        )
    return {"health": health_payload, "dimension": dimension}


def real_llm_config_errors(env: LiveE2EEnv) -> list[str]:
    """Return missing real-LLM configuration for opt-in live LLM runs."""

    if not env.real_llm:
        return []

    errors: list[str] = []
    if not os.getenv("E2E_CORE_REAL_LLM"):
        errors.append("E2E_CORE_REAL_LLM=1 is required for real LLM mode")
    if not os.getenv("LLM_MODEL"):
        errors.append("LLM_MODEL is required for real LLM mode")
    provider_keys = (
        os.getenv("CEREBRAS_API_KEY"),
        os.getenv("GROQ_API_KEY"),
        os.getenv("OPENAI_API_KEY"),
        os.getenv("LLM_API_KEY"),
    )
    if not any(provider_keys):
        errors.append(
            "one of CEREBRAS_API_KEY, GROQ_API_KEY, OPENAI_API_KEY, or LLM_API_KEY is required for real LLM mode"
        )
    return errors


# ---------------------------------------------------------------------------
# Namespaced resource provisioners (Qdrant / Redis / PostgreSQL)
# ---------------------------------------------------------------------------


def make_qdrant_context(env: LiveE2EEnv, run_id: str | None = None) -> QdrantTestContext:
    """Create metadata for a fresh run-owned ephemeral collection."""

    namespace = (
        RunNamespace(
            run_id=validate_run_id(run_id), worker=os.environ.get("PYTEST_XDIST_WORKER") or "main"
        )
        if run_id
        else RunNamespace.resolve()
    )
    return QdrantTestContext(
        collection_name=namespace.qdrant_collection,
        qdrant_url=env.qdrant_url,
        keep=should_keep_collection(),
        run_id=namespace.run_id,
    )


def recreate_collection(env: LiveE2EEnv, collection_name: str) -> None:
    """Create an empty live collection with the repo's hybrid vector contract."""

    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance,
        HnswConfigDiff,
        Modifier,
        MultiVectorComparator,
        MultiVectorConfig,
        SparseVectorParams,
        VectorParams,
    )

    from tests.e2e_core.qdrant_helpers import assert_owned_collection_format

    assert_owned_collection_format(collection_name)
    client = QdrantClient(url=env.qdrant_url, api_key=env.qdrant_api_key, timeout=30)
    try:
        with contextlib.suppress(Exception):
            client.delete_collection(collection_name)
        client.create_collection(
            collection_name=collection_name,
            vectors_config={
                "dense": VectorParams(size=1024, distance=Distance.COSINE),
                "colbert": VectorParams(
                    size=1024,
                    distance=Distance.COSINE,
                    multivector_config=MultiVectorConfig(comparator=MultiVectorComparator.MAX_SIM),
                    hnsw_config=HnswConfigDiff(m=0),
                ),
            },
            sparse_vectors_config={"bm42": SparseVectorParams(modifier=Modifier.IDF)},
        )
    finally:
        client.close()


async def index_fixture_documents(
    env: LiveE2EEnv,
    collection_name: str,
    *,
    document_ids: list[str] | None = None,
) -> int:
    """Index all Markdown fixture docs into the ephemeral Qdrant collection."""

    from src.ingestion.unified.qdrant_writer import QdrantHybridWriter

    selected_ids = set(document_ids or [])
    writer = QdrantHybridWriter(
        qdrant_url=env.qdrant_url,
        qdrant_api_key=env.qdrant_api_key,
        bge_m3_url=env.bge_m3_url,
    )
    total = 0
    try:
        for path in sorted(DOCS_DIR.glob("*.md")):
            if selected_ids and path.stem not in selected_ids:
                continue
            chunk = MarkdownChunk(
                text=path.read_text(encoding="utf-8"),
                order=0,
                chunk_id=0,
                document_name=path.name,
                extra_metadata={"headings": [_extract_title(path)]},
            )
            stats = await asyncio.to_thread(
                writer.upsert_chunks_sync,
                [chunk],
                path.stem,
                str(path),
                {
                    "file_name": path.name,
                    "mime_type": "text/markdown",
                    "language": "en",
                    "source_type": "fixture",
                },
                collection_name,
            )
            total += stats.points_upserted
    finally:
        writer._bge_client.close()
        writer.client.close()
    return total


def build_live_core_harness(
    env: LiveE2EEnv,
    collection_name: str,
    *,
    crm: MockCrmClient | None = None,
    config: Any | None = None,
) -> LiveCoreHarness:
    """Build CoreDependencies for ``run_assistant_request`` using live retrieval."""

    from src.core.assistant import CoreDependencies

    embeddings = LiveBGEEmbeddings(env.bge_m3_url)
    sparse_embeddings = LiveBGESparseEmbeddings(env.bge_m3_url)
    qdrant = QdrantService(
        url=env.qdrant_url,
        api_key=env.qdrant_api_key,
        collection_name=collection_name,
        timeout=30,
        prefer_grpc=False,
    )
    llm_config = config or _build_live_llm_config(env)
    dependencies = CoreDependencies(
        cache=NoopLiveCache(),
        embeddings=embeddings,
        sparse_embeddings=sparse_embeddings,
        qdrant=qdrant,
        reranker=None,
        config=llm_config,
    )
    if crm is not None:
        dependencies.crm = crm  # type: ignore[attr-defined]

    async def _cleanup() -> None:
        await embeddings.aclose()
        await sparse_embeddings.aclose()
        await qdrant.close()

    return LiveCoreHarness(dependencies=dependencies, cleanup=_cleanup)


def _build_live_llm_config(env: LiveE2EEnv) -> Any:
    if not env.real_llm:
        return FakeLLMConfig()

    config = GraphConfig.from_env()
    config.domain = "недвижимость в Болгарии"
    config.llm_temperature = 0.0
    config.generate_max_tokens = int(os.getenv("E2E_CORE_REAL_LLM_MAX_TOKENS", "600"))
    config.show_sources = False
    config.response_style_enabled = False
    config.response_style_shadow_mode = False
    return config


def cleanup_collection(env: LiveE2EEnv, context: QdrantTestContext) -> None:
    """Drop the run-owned collection and PROVE it is gone (#3414).

    Refuses non-owned names, never swallows unexpected errors, and verifies
    the collection is absent after deletion. ``E2E_KEEP_COLLECTION=1`` is the
    documented debug override that skips deletion entirely.
    """

    from qdrant_client import QdrantClient

    if context.run_id:
        assert_owned_collection_name(context.collection_name, context.run_id)
    else:
        from tests.e2e_core.qdrant_helpers import assert_owned_collection_format

        assert_owned_collection_format(context.collection_name)
    if context.keep:
        return

    client = QdrantClient(url=env.qdrant_url, api_key=env.qdrant_api_key, timeout=30)
    try:
        names = {item.name for item in client.get_collections().collections}
        if context.collection_name in names:
            client.delete_collection(context.collection_name)
        names_after = {item.name for item in client.get_collections().collections}
        if context.collection_name in names_after:
            raise HarnessSafetyError(
                f"leaked owned collection {context.collection_name!r}: still present after teardown"
            )
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Redis and PostgreSQL namespaces
# ---------------------------------------------------------------------------


def _redis_url_with_db(url_base: str | None, db: int) -> str:
    base = url_base or os.getenv("REDIS_URL") or f"redis://{DEFAULT_REDIS_HOST}"
    password = os.getenv("REDIS_PASSWORD", "")
    if password and "@" not in base:
        base = base.replace("redis://", f"redis://:{password}@", 1)
    base = base.rstrip("/")
    return re.sub(r"/\d+$", f"/{db}", base) if re.search(r"/\d+$", base) else f"{base}/{db}"


@dataclass
class RedisLease:
    """A run-owned Redis prefix/database with verified cleanup."""

    url: str
    db: int
    prefix: str

    async def release_and_verify(self) -> int:
        """Delete every key under the owned prefix; prove zero remain."""
        if not self.prefix.startswith("rag_e2e:"):
            raise HarnessSafetyError(f"refusing non-owned redis prefix {self.prefix!r}")
        return int(await _release_redis_prefix(self.url, self.prefix))


@dataclass
class PostgresLease:
    """A run-owned PostgreSQL schema with verified cleanup."""

    dsn: str
    schema: str

    async def release_and_verify(self) -> None:
        await _drop_postgres_schema(self.dsn, self.schema)


async def provide_redis_namespace(lease_url: str | None, namespace: RunNamespace) -> RedisLease:
    """Claim a Redis prefix/db for the worker; ownership marker proves the claim."""
    lease = RedisLease(
        url=lease_url or _redis_url_with_db(None, namespace.redis_db),
        db=namespace.redis_db,
        prefix=namespace.redis_prefix,
    )
    await _claim_redis_namespace(lease, namespace)
    return lease


async def provide_postgres_schema(dsn: str | None, namespace: RunNamespace) -> PostgresLease:
    """Create the worker's PostgreSQL schema; verified absent after release."""
    resolved = dsn or _postgres_dsn_from_env()
    lease = PostgresLease(dsn=resolved, schema=namespace.postgres_schema)
    await _create_postgres_schema(resolved, namespace.postgres_schema)
    return lease


async def _claim_redis_namespace(lease: RedisLease, namespace: RunNamespace) -> None:
    import redis.asyncio as aioredis

    client = aioredis.from_url(lease.url, decode_responses=True, socket_connect_timeout=5)
    try:
        marker = lease.prefix + REDIS_OWNER_MARKER
        payload = json.dumps(
            {
                "run_id": namespace.run_id,
                "worker": namespace.worker,
                "pid": os.getpid(),
                "schema": namespace.postgres_schema,
            }
        )
        await client.set(marker, payload, ex=REDIS_OWNER_TTL)
        claimed = await client.get(marker)
        if claimed is None:
            raise HarnessSafetyError(f"redis ownership marker not stored under {marker!r}")
    finally:
        with contextlib.suppress(Exception):
            await client.aclose()


async def _release_redis_prefix(url: str, prefix: str) -> int:
    import redis.asyncio as aioredis

    client = aioredis.from_url(url, decode_responses=True, socket_connect_timeout=5)
    deleted = 0
    try:
        batch: list[str] = []
        async for key in client.scan_iter(match=f"{prefix}*"):
            batch.append(key)
            if len(batch) >= 200:
                deleted += await client.delete(*batch)
                batch = []
        if batch:
            deleted += await client.delete(*batch)
        remaining = [key async for key in client.scan_iter(match=f"{prefix}*")]
        if remaining:
            raise HarnessSafetyError(f"leaked owned redis keys under {prefix!r}: {remaining[:5]}")
    finally:
        with contextlib.suppress(Exception):
            await client.aclose()
    return deleted


_POSTGRES_SCHEMA_RE = re.compile(r"^rag_e2e_[0-9a-f]{12}_(main|gw\d{1,3})$")


async def _create_postgres_schema(dsn: str, schema: str) -> None:
    import asyncpg

    if not _POSTGRES_SCHEMA_RE.match(schema):
        raise HarnessSafetyError(f"refusing non-owned postgres schema {schema!r}")
    connection = await asyncpg.connect(dsn, timeout=10)
    try:
        await connection.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        present = await _schema_exists(connection, schema)
        if not present:
            raise HarnessSafetyError(f"schema {schema!r} not present after CREATE SCHEMA")
    finally:
        await connection.close()


async def _drop_postgres_schema(dsn: str, schema: str) -> None:
    import asyncpg

    if not _POSTGRES_SCHEMA_RE.match(schema):
        raise HarnessSafetyError(f"refusing non-owned postgres schema {schema!r}")
    connection = await asyncpg.connect(dsn, timeout=10)
    try:
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        if await _schema_exists(connection, schema):
            raise HarnessSafetyError(
                f"leaked owned postgres schema {schema!r}: still present after DROP"
            )
    finally:
        await connection.close()


async def _schema_exists(connection: Any, schema: str) -> bool:
    present = await connection.fetchval(
        "SELECT 1 FROM information_schema.schemata WHERE schema_name = $1", schema
    )
    return bool(present == 1)


# ---------------------------------------------------------------------------
# Teardown registry: delete only owned resources, prove zero leaks
# ---------------------------------------------------------------------------


@dataclass
class TeardownRegistry:
    """Registry of run-owned resources with leak-proof teardown (#3414).

    Register resources at creation time so a forced test failure still
    cleans everything. ``teardown_and_verify`` deletes only resources whose
    names were validated against the run namespace (non-owned registrations
    are refused at registration time) and then proves zero remain.
    """

    run_id: str
    collections: list[tuple[str, str]] = field(default_factory=list)  # (url, name)
    redis_leases: list[RedisLease] = field(default_factory=list)
    postgres_leases: list[PostgresLease] = field(default_factory=list)
    _torn_down: bool = False

    def register_collection(self, qdrant_url: str, name: str) -> str:
        assert_owned_collection_name(name, self.run_id)
        self.collections.append((qdrant_url, name))
        return name

    def register_redis(self, lease: RedisLease) -> RedisLease:
        if not lease.prefix.startswith(f"rag_e2e:{self.run_id}:"):
            raise HarnessSafetyError(f"refusing foreign redis prefix {lease.prefix!r}")
        self.redis_leases.append(lease)
        return lease

    def register_postgres(self, lease: PostgresLease) -> PostgresLease:
        if not lease.schema.startswith(f"rag_e2e_{self.run_id}_"):
            raise HarnessSafetyError(f"refusing foreign postgres schema {lease.schema!r}")
        self.postgres_leases.append(lease)
        return lease

    def refuse_non_owned_collection(self, name: str) -> None:
        """Explicit guard used by tests to prove non-owned deletion is refused."""
        assert_owned_collection_name(name, self.run_id)

    async def teardown_and_verify(self) -> dict[str, int]:
        """Clean every registered resource; prove zero owned leaks remain."""
        report = {"collections": 0, "redis_keys": 0, "schemas": 0}
        if self._torn_down:
            return report
        for url, name in self.collections:
            env = LiveE2EEnv(
                qdrant_url=url, bge_m3_url=DEFAULT_BGE_M3_URL, required=required_mode()
            )
            context = QdrantTestContext(
                collection_name=name,
                qdrant_url=url,
                keep=False,
                run_id=self.run_id,
            )
            cleanup_collection(env, context)
            report["collections"] += 1
        for lease in self.redis_leases:
            report["redis_keys"] += await lease.release_and_verify()
        for postgres_lease in self.postgres_leases:
            await postgres_lease.release_and_verify()
            report["schemas"] += 1
        self._torn_down = True
        return report


# ---------------------------------------------------------------------------
# Fake LLM internals (deterministic answer synthesis)
# ---------------------------------------------------------------------------


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    normalized = value.strip().lower()
    return bool(normalized) and normalized not in {"0", "false", "no", "off"}


def _extract_title(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return path.stem


class _FakeLLM:
    def __init__(self) -> None:
        self.completion = self._create

    async def _create(self, **kwargs: Any) -> Any:
        messages = kwargs.get("messages", [])
        user_message = messages[-1].get("content", "") if messages else ""
        answer = _answer_from_context(str(user_message))
        return SimpleNamespace(
            model="fake-live-e2e",
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=10, total_tokens=20),
            choices=[SimpleNamespace(message=SimpleNamespace(content=answer))],
        )


class _FailingLLM:
    def __init__(self, error_message: str) -> None:
        self.completion = self._create
        self._error_message = error_message

    async def _create(self, **kwargs: Any) -> Any:
        raise TimeoutError(self._error_message)


def _answer_from_context(message: str) -> str:
    context_part, _, question_part = message.partition("Вопрос:")
    context = context_part.replace("Контекст:", "").strip()
    question = question_part.lower()
    if not context or "Релевантной информации не найдено" in context:
        return "не найдено"

    lines = [line.strip() for line in context.splitlines() if line.strip()]
    sections = _split_context_sections(lines)

    if "просмотр" in question or "подтвержд" in question or "confirmation" in question:
        selected = _select_section_lines(sections, ("hitl", "confirmation", "confirm"))
        if selected:
            return "\n".join(selected)

    if "уборк" in question or "cleaning" in question:
        selected = _select_section_lines(sections, ("cleaning", "25 eur", "48 hours"))
        if selected:
            return "\n".join(selected)

    if "сад" in question or "garden" in question or "бургас" in question or "burgas" in question:
        selected = _select_section_lines(sections, ("sotirovo", "garden", "burgas"))
        if selected:
            return "\n".join(selected)

    if "мор" in question or "sea" in question or "бассейн" in question or "pool" in question:
        selected = _select_section_lines(sections, ("sunny beach", "swimming pool", "110000"))
        if selected:
            return "\n".join(selected)

    if "деш" in question or "cheapest" in question:
        selected = _select_cheapest_sunny_beach_section(sections)
        if selected:
            return "\n".join(selected)

    selected = _select_section_lines(sections, ("sunny beach", "110000"))
    if selected:
        return "\n".join(selected)
    return "\n".join(lines[:6])


def _split_context_sections(lines: list[str]) -> list[list[str]]:
    sections: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.startswith("# ") and current:
            sections.append(current)
            current = []
        current.append(line.replace(",", ""))
    if current:
        sections.append(current)
    return sections


def _select_section_lines(sections: list[list[str]], keywords: tuple[str, ...]) -> list[str]:
    for section in sections:
        normalized = "\n".join(section).lower()
        if any(keyword in normalized for keyword in keywords):
            return section
    return []


def _select_cheapest_sunny_beach_section(sections: list[list[str]]) -> list[str]:
    candidates: list[tuple[int, list[str]]] = []
    for section in sections:
        normalized = "\n".join(section).lower()
        if "sunny beach" not in normalized:
            continue
        price = _extract_price_eur(normalized)
        if price is not None:
            candidates.append((price, section))
    if not candidates:
        return []
    return min(candidates, key=lambda candidate: candidate[0])[1]


def _extract_price_eur(text: str) -> int | None:
    match = re.search(r"price:\*\*\s*([0-9 ]+)\s*eur", text)
    if not match:
        return None
    return int(match.group(1).replace(" ", ""))
