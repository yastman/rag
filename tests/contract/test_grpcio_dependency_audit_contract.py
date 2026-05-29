"""Contract test for issue #2241 — keep the Qdrant gRPC dependency explicit
without redundant direct ``grpcio`` declarations.

Audit decision (issue #2241):

``grpcio`` is required by the project only because the runtime talks to
Qdrant over gRPC (``AsyncQdrantClient(..., prefer_grpc=True)``). The
canonical ``qdrant-client`` distribution already declares ``grpcio>=1.41.0``
as a hard dependency, so it is pulled in transitively wherever
``qdrant-client`` is installed.

The previous ``telegram_bot/pyproject.toml`` carried a *direct*
``grpcio>=1.60.0`` declaration that duplicated this transitive dependency.
A redundant direct pin can trigger unnecessary resolver/build work in PR
checks (notably building ``grpcio`` from source in a fresh interpreter), so
it was removed.

This test encodes four invariants so the decision does not silently drift:

1. ``grpcio`` is NOT a direct ``[project].dependencies`` entry in any
   first-party pyproject — it must stay transitive via ``qdrant-client``.
2. Every pyproject that previously relied on direct ``grpcio`` still
   declares ``qdrant-client`` (the transitive provider), so removing the
   direct pin cannot accidentally drop gRPC support.
3. The runtime Qdrant transport is still intentionally gRPC
   (``prefer_grpc=True`` in the canonical service + preflight).
4. The rationale is documented in a discoverable doc so a future reader
   understands why ``grpcio`` has no direct declaration.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]

# First-party pyprojects that resolve against an environment containing
# qdrant-client (and therefore should NOT pin grpcio directly).
PYPROJECTS = [
    REPO / "pyproject.toml",
    REPO / "telegram_bot" / "pyproject.toml",
]


def _load_pyproject(path: Path) -> dict:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _project_dep_strings(cfg: dict) -> list[str]:
    return list((cfg.get("project") or {}).get("dependencies", []) or [])


def _optional_dep_strings(cfg: dict) -> dict[str, list[str]]:
    return dict((cfg.get("project") or {}).get("optional-dependencies", {}) or {})


def _dep_name(spec: str) -> str:
    """Strip version specifiers/extras to the bare PEP 503 distribution name."""
    return re.split(r"[\s<>=!~\[]", spec, maxsplit=1)[0].strip().lower()


def test_grpcio_not_a_direct_dependency() -> None:
    """grpcio must be transitive-only (via qdrant-client), not directly pinned."""
    offenders: list[str] = []
    for path in PYPROJECTS:
        if not path.exists():
            continue
        cfg = _load_pyproject(path)
        names = {_dep_name(s) for s in _project_dep_strings(cfg)}
        names |= {_dep_name(s) for deps in _optional_dep_strings(cfg).values() for s in deps}
        if "grpcio" in names:
            offenders.append(str(path.relative_to(REPO)))
    assert offenders == [], (
        "grpcio must not be a direct dependency (issue #2241). It is pulled in "
        "transitively by qdrant-client (which declares grpcio>=1.41.0). Remove "
        f"the redundant direct declaration from: {offenders}."
    )


def test_qdrant_client_present_where_grpc_used() -> None:
    """The transitive grpcio provider (qdrant-client) must stay declared.

    This guards against the failure mode where someone removes the direct
    grpcio pin AND drops qdrant-client, silently losing gRPC support.
    """
    for path in PYPROJECTS:
        if not path.exists():
            continue
        cfg = _load_pyproject(path)
        names = {_dep_name(s) for s in _project_dep_strings(cfg)}
        names |= {_dep_name(s) for deps in _optional_dep_strings(cfg).values() for s in deps}
        assert "qdrant-client" in names, (
            f"{path.relative_to(REPO)} must declare qdrant-client so grpcio "
            "remains available transitively for prefer_grpc=True (issue #2241)."
        )


def test_qdrant_runtime_still_prefers_grpc() -> None:
    """The canonical Qdrant service + preflight still use prefer_grpc=True.

    If gRPC were ever turned off, grpcio would genuinely become unnecessary
    and this audit decision would need revisiting — so assert the transport
    is still gRPC.
    """
    qdrant_service = REPO / "src" / "runtime" / "services" / "qdrant.py"
    preflight = REPO / "telegram_bot" / "preflight.py"
    for path in (qdrant_service, preflight):
        text = path.read_text(encoding="utf-8")
        assert "prefer_grpc=True" in text, (
            f"{path.relative_to(REPO)} no longer sets prefer_grpc=True; if gRPC "
            "is intentionally disabled, revisit the grpcio audit in issue #2241."
        )


def test_grpcio_transitive_rationale_documented() -> None:
    """A discoverable doc explains why grpcio has no direct declaration."""
    doc = REPO / "docs" / "engineering" / "sdk-registry.md"
    text = doc.read_text(encoding="utf-8").lower()
    assert "grpcio" in text, (
        "docs/engineering/sdk-registry.md must document that grpcio is retained "
        "transitively via qdrant-client (prefer_grpc=True) and is not declared "
        "directly (issue #2241)."
    )
