"""Live E2E harness for the product simplification golden path."""

from __future__ import annotations

import contextlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import yaml

from tests.e2e_core.qdrant_helpers import (
    QdrantTestContext,
    generate_collection_name,
    should_keep_collection,
)


FIXTURES_DIR = Path(__file__).parent / "fixtures"
DOCS_DIR = FIXTURES_DIR / "docs"
GOLDEN_CASES_PATH = FIXTURES_DIR / "golden_cases.yaml"


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

    @classmethod
    def from_env(cls) -> LiveE2EEnv:
        """Resolve live-test endpoints from explicit overrides or runtime env."""

        return cls(
            qdrant_url=(
                os.getenv("E2E_CORE_QDRANT_URL")
                or os.getenv("QDRANT_URL")
                or "http://localhost:6333"
            ),
            bge_m3_url=(
                os.getenv("E2E_CORE_BGE_URL") or os.getenv("BGE_M3_URL") or "http://localhost:8000"
            ),
            qdrant_api_key=os.getenv("QDRANT_API_KEY") or None,
            strict=_truthy(os.getenv("E2E_CORE_STRICT")),
        )


@dataclass
class MarkdownChunk:
    """Minimal chunk shape accepted by QdrantHybridWriter."""

    text: str
    order: int
    chunk_id: int
    document_name: str
    extra_metadata: dict[str, Any]


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
        self, dense_vector: list[float], filters: dict[str, Any] | None
    ) -> None:
        return None

    async def store_search_results(
        self,
        dense_vector: list[float],
        filters: dict[str, Any] | None,
        results: list[dict[str, Any]],
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
    streaming_enabled = False
    show_sources = False
    response_style_enabled = False
    response_style_shadow_mode = False

    def create_llm(self, *, auto_trace: bool = False) -> Any:
        return _FakeLLM()

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


async def require_live_services(env: LiveE2EEnv) -> None:
    """Require Qdrant and BGE-M3, skipping or failing depending on strict mode."""

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

    if not failures:
        return

    message = "; ".join(failures)
    if env.strict:
        pytest.fail(message)
    pytest.skip(message)


def make_qdrant_context(env: LiveE2EEnv) -> QdrantTestContext:
    """Create metadata for a fresh ephemeral collection."""

    return QdrantTestContext(
        collection_name=generate_collection_name(),
        qdrant_url=env.qdrant_url,
        keep=should_keep_collection(),
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

    client = QdrantClient(url=env.qdrant_url, api_key=env.qdrant_api_key, timeout=30.0)
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

    class _NoColbertQdrantHybridWriter(QdrantHybridWriter):
        def _embed_colbert(self, texts: list[str]) -> list[list[list[float]]]:
            return []

    selected_ids = set(document_ids or [])
    writer = _NoColbertQdrantHybridWriter(
        qdrant_url=env.qdrant_url,
        qdrant_api_key=env.qdrant_api_key,
        bge_m3_url=env.bge_m3_url,
        use_local_embeddings=True,
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
            stats = await writer.upsert_chunks(
                chunks=[chunk],
                file_id=path.stem,
                source_path=str(path),
                file_metadata={
                    "file_name": path.name,
                    "mime_type": "text/markdown",
                    "language": "en",
                    "source_type": "fixture",
                },
                collection_name=collection_name,
            )
            total += stats.points_upserted
    finally:
        writer._bge_client.close()
        writer.client.close()
    return total


def build_live_core_harness(env: LiveE2EEnv, collection_name: str) -> LiveCoreHarness:
    """Build CoreDependencies for ``run_assistant_request`` using live retrieval."""

    from src.core.assistant import CoreDependencies
    from src.runtime.services.qdrant import QdrantService

    embeddings = LiveBGEEmbeddings(env.bge_m3_url)
    sparse_embeddings = LiveBGESparseEmbeddings(env.bge_m3_url)
    qdrant = QdrantService(
        url=env.qdrant_url,
        api_key=env.qdrant_api_key,
        collection_name=collection_name,
        timeout=30,
        prefer_grpc=False,
    )
    dependencies = CoreDependencies(
        cache=NoopLiveCache(),
        embeddings=embeddings,
        sparse_embeddings=sparse_embeddings,
        qdrant=qdrant,
        reranker=None,
        config=FakeLLMConfig(),
    )

    async def _cleanup() -> None:
        await embeddings.aclose()
        await sparse_embeddings.aclose()
        await qdrant.close()

    return LiveCoreHarness(dependencies=dependencies, cleanup=_cleanup)


def cleanup_collection(env: LiveE2EEnv, context: QdrantTestContext) -> None:
    """Drop the ephemeral collection unless E2E_KEEP_COLLECTION asks to retain it."""

    if context.keep:
        return

    from qdrant_client import QdrantClient

    client = QdrantClient(url=env.qdrant_url, api_key=env.qdrant_api_key, timeout=30.0)
    try:
        client.delete_collection(context.collection_name)
    except Exception:
        pass
    finally:
        client.close()


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
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs: Any) -> Any:
        messages = kwargs.get("messages", [])
        user_message = messages[-1].get("content", "") if messages else ""
        answer = _answer_from_context(str(user_message))
        return SimpleNamespace(
            model="fake-live-e2e",
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=10, total_tokens=20),
            choices=[SimpleNamespace(message=SimpleNamespace(content=answer))],
        )


def _answer_from_context(message: str) -> str:
    context = message.split("Вопрос:", 1)[0].replace("Контекст:", "").strip()
    if not context or "Релевантной информации не найдено" in context:
        return "не найдено"

    lines = [line.strip() for line in context.splitlines() if line.strip()]
    selected = [
        line.replace(",", "")
        for line in lines
        if "Sunny Beach" in line or "110000" in line.replace(",", "")
    ]
    if selected:
        return "\n".join(selected)
    return "\n".join(lines[:6])
