"""Contract: Docling native-SDK authority guards (P23 stabilization).

Ensures the Docling migration invariants hold permanently:
- services/docling sidecar is gone
- src/ingestion/docling_client.py (HTTP client) is gone
- No DOCLING_URL env var in compose or config
- Bot/base Dockerfiles do NOT install docling-native
- Dockerfile.ingestion DOES install --extra docling-native
- pyproject extras are consolidated (no ingest/ingestion duplicates)
- docling-core[chunking] is present
- transformers is present in docling-native
- uv.lock has no CUDA/nvidia wheels
- torch is CPU-only

All tests are static (no live services required).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]

# Compose files to scan for docling service and DOCLING_URL.
# compose.vps.yml is absent in this repo checkout — we only scan what exists.
_COMPOSE_CANDIDATES = [
    "compose.yml",
    "compose.dev.yml",
    "compose.core.yml",
    "compose.vps.yml",
]


def _existing_compose_files() -> list[Path]:
    return [REPO_ROOT / name for name in _COMPOSE_CANDIDATES if (REPO_ROOT / name).exists()]


# ---------------------------------------------------------------------------
# 1. services/docling directory absent
# ---------------------------------------------------------------------------


def test_docling_service_directory_absent() -> None:
    """services/docling sidecar directory must not exist after migration."""
    target = REPO_ROOT / "services" / "docling"
    assert not target.exists(), (
        "services/docling/ still exists; the Docling migration removed the "
        "HTTP sidecar — this directory must stay deleted."
    )


# ---------------------------------------------------------------------------
# 2. src/ingestion/docling_client.py absent
# ---------------------------------------------------------------------------


def test_docling_http_client_absent() -> None:
    """src/ingestion/docling_client.py must not exist after migration."""
    target = REPO_ROOT / "src" / "ingestion" / "docling_client.py"
    assert not target.exists(), (
        "src/ingestion/docling_client.py still exists; the HTTP client was "
        "replaced by the native SDK adapter (src/ingestion/docling_native.py)."
    )


# ---------------------------------------------------------------------------
# 3. compose.yml has no docling service
# ---------------------------------------------------------------------------


def test_compose_yml_no_docling_service() -> None:
    """compose.yml must not define a 'docling' service."""
    path = REPO_ROOT / "compose.yml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    services = data.get("services", {})
    assert "docling" not in services, (
        "compose.yml still defines a 'docling' service. Remove it — Docling "
        "runs in-process; no HTTP sidecar is needed."
    )


# ---------------------------------------------------------------------------
# 4. compose.dev.yml has no docling service (skip if absent)
# ---------------------------------------------------------------------------


def test_compose_dev_no_docling_service() -> None:
    """compose.dev.yml must not define a 'docling' service (skipped if file absent)."""
    path = REPO_ROOT / "compose.dev.yml"
    if not path.exists():
        pytest.skip("compose.dev.yml does not exist")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    services = data.get("services", {})
    assert "docling" not in services, (
        "compose.dev.yml still defines a 'docling' service. Remove it."
    )


# ---------------------------------------------------------------------------
# 5. No DOCLING_URL in any compose file
# ---------------------------------------------------------------------------


def test_no_docling_url_in_compose_files() -> None:
    """No compose file may contain a DOCLING_URL environment variable."""
    violations: list[str] = []
    for path in _existing_compose_files():
        text = path.read_text(encoding="utf-8")
        if "DOCLING_URL" in text:
            violations.append(path.name)

    assert not violations, (
        "DOCLING_URL found in compose file(s): "
        + ", ".join(violations)
        + ". Docling runs in-process; DOCLING_URL must be fully removed."
    )


# ---------------------------------------------------------------------------
# 6. Bot/base Dockerfiles do NOT install docling-native
# ---------------------------------------------------------------------------


_BOT_DOCKERFILES = [
    "Dockerfile",  # root-level base image (may not exist)
    "Dockerfile.bot",  # bot-specific image (may not exist)
    "telegram_bot/Dockerfile",  # the actual telegram bot image
]


@pytest.mark.parametrize("rel_path", _BOT_DOCKERFILES)
def test_bot_dockerfile_no_docling_native(rel_path: str) -> None:
    """Bot/base Dockerfiles must NOT install --extra docling-native."""
    path = REPO_ROOT / rel_path
    if not path.exists():
        pytest.skip(f"{rel_path} does not exist in this checkout")
    content = path.read_text(encoding="utf-8")
    assert "--extra docling-native" not in content, (
        f"{rel_path} installs --extra docling-native; "
        "only Dockerfile.ingestion should carry docling-native."
    )


# ---------------------------------------------------------------------------
# 7. Dockerfile.ingestion DOES install --extra docling-native
# ---------------------------------------------------------------------------


def test_ingestion_dockerfile_uses_docling_native() -> None:
    """Dockerfile.ingestion must install --extra docling-native."""
    path = REPO_ROOT / "Dockerfile.ingestion"
    assert path.exists(), "Dockerfile.ingestion not found in repo root."
    content = path.read_text(encoding="utf-8")
    assert "--extra docling-native" in content, (
        "Dockerfile.ingestion does not use '--extra docling-native'. "
        "The ingestion image must install the Docling SDK."
    )


# ---------------------------------------------------------------------------
# 8. pyproject.toml has no duplicate ingest/ingestion extras
# ---------------------------------------------------------------------------


def test_pyproject_no_duplicate_ingest_extras() -> None:
    """pyproject.toml must not define stale 'ingest' or 'ingestion' optional-deps."""
    path = REPO_ROOT / "pyproject.toml"
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    opt_deps = data.get("project", {}).get("optional-dependencies", {})
    for forbidden in ("ingest", "ingestion"):
        assert forbidden not in opt_deps, (
            f"pyproject.toml still has an '{forbidden}' extra in "
            "[project.optional-dependencies]. These were consolidated "
            "into 'docling-native' and should be removed."
        )


# ---------------------------------------------------------------------------
# 9. docling-core[chunking] is present in docling-native extra
# ---------------------------------------------------------------------------


def test_pyproject_docling_native_has_chunking() -> None:
    """docling-native extra must include docling-core[chunking]."""
    path = REPO_ROOT / "pyproject.toml"
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    opt_deps = data.get("project", {}).get("optional-dependencies", {})
    assert "docling-native" in opt_deps, (
        "pyproject.toml has no 'docling-native' optional-dependency group."
    )
    entries: list[str] = opt_deps["docling-native"]
    # A valid entry looks like "docling-core[chunking]>=2.74.1"
    has_chunking = any("docling-core" in e and "[chunking]" in e for e in entries)
    assert has_chunking, (
        "docling-native extra does not contain 'docling-core[chunking]'. "
        "HybridChunker requires the [chunking] extra. "
        f"Current entries: {entries}"
    )


# ---------------------------------------------------------------------------
# 10. transformers is present in docling-native extra
# ---------------------------------------------------------------------------


def test_pyproject_docling_native_has_transformers() -> None:
    """docling-native extra must include transformers."""
    path = REPO_ROOT / "pyproject.toml"
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    opt_deps = data.get("project", {}).get("optional-dependencies", {})
    assert "docling-native" in opt_deps, (
        "pyproject.toml has no 'docling-native' optional-dependency group."
    )
    entries: list[str] = opt_deps["docling-native"]
    has_transformers = any(e.startswith("transformers") for e in entries)
    assert has_transformers, (
        "docling-native extra does not contain a 'transformers' entry. "
        "Docling's TableFormer model requires transformers. "
        f"Current entries: {entries}"
    )


# ---------------------------------------------------------------------------
# 11. uv.lock has no CUDA/nvidia wheels
# ---------------------------------------------------------------------------

# These substrings in wheel names or URLs indicate a CUDA build was resolved.
_CUDA_MARKERS = ("nvidia-", "+cu", "+cuda", "cuda")


def test_uv_lock_no_cuda_wheels() -> None:
    """uv.lock must not contain CUDA or nvidia wheel references.

    The ingestion pipeline uses CPU-only torch (via the cpu index in
    [tool.uv.sources]). If CUDA wheels appear in the lockfile, the image
    will be tens of GB larger than necessary.
    """
    lock_path = REPO_ROOT / "uv.lock"
    assert lock_path.exists(), "uv.lock not found in repo root."
    text = lock_path.read_text(encoding="utf-8")

    violations: list[str] = []
    for line in text.splitlines():
        line_lower = line.lower()
        if any(marker in line_lower for marker in _CUDA_MARKERS):
            violations.append(line.strip())

    assert not violations, (
        "uv.lock contains CUDA/nvidia wheel references — torch must resolve "
        "from the CPU-only index (https://download.pytorch.org/whl/cpu). "
        "Violations:\n"
        + "\n".join(f"  {v}" for v in violations[:20])
        + ("\n  ..." if len(violations) > 20 else "")
    )
