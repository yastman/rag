"""Contract for the standalone local meeting-RAG Compose sidecars."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "compose.local-rag.yml"
LOCAL_DEV = REPO_ROOT / "docs" / "LOCAL-DEVELOPMENT.md"


def test_local_rag_compose_contains_only_loopback_sidecars() -> None:
    """The native meeting-RAG path exposes only its three local dependencies."""
    compose = COMPOSE.read_text(encoding="utf-8")

    assert "  qdrant:\n" in compose
    assert "  redis:\n" in compose
    assert "  bge-m3:\n" in compose
    assert "  bot:\n" not in compose
    assert "  ingestion:\n" not in compose
    assert "  postgres:\n" not in compose
    for port in ("127.0.0.1:6333:6333", "127.0.0.1:6379:6379", "127.0.0.1:8000:8000"):
        assert port in compose


def test_local_rag_compose_uses_existing_bge_artifact_and_readiness_contracts() -> None:
    """The sidecar stack builds the existing ONNX service and checks every dependency."""
    compose = COMPOSE.read_text(encoding="utf-8")

    assert "context: ./services/bge-m3-api" in compose
    assert "BGE_M3_ONNX_MODEL_HOST_DIR" in compose
    assert "/readyz" in compose
    assert 'redis-cli", "ping"' in compose
    assert "http://localhost:8000/health" in compose
    assert (
        "redis:8.6.3@sha256:4d25e2fe601f7ffaeb4437cb6ced3518bc36edf34ebe98863c80836943d94529"
        in compose
    )


def test_local_runtime_guide_scopes_sidecar_lifecycle_and_artifact_evidence() -> None:
    """Operators get start/status/stop and artifact-evidence commands without full stack."""
    guide = LOCAL_DEV.read_text(encoding="utf-8")

    assert "compose.local-rag.yml" in guide
    assert "docker compose -f compose.local-rag.yml up -d" in guide
    assert "docker compose -f compose.local-rag.yml ps" in guide
    assert "docker compose -f compose.local-rag.yml down" in guide
    assert "Get-FileHash" in guide
    assert "model.int8.onnx.data" in guide
    assert "e4b993d0e996ab07ec5ee576d2f102af6d534381d5861bdfcbc24981efc01c80" in guide
    assert "2976067612ae0a7c804a32b5abe64f512056655c689455c6a994029529c62c28" in guide
