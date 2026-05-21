"""Contract tests: Qdrant storage optimisation config (***REMOVED***1545).

Qdrant's ``gdrive_documents_bge`` collection has been accumulating vectors
indefinitely, growing the ``dev_qdrant_data`` volume past 3.1 GB with no
bounds.  This contract file is the RED gate that forces the repo to:

1. Ship ``docker/qdrant/config.yaml`` with storage optimisations.
2. Mount that file into the Qdrant container via ``compose.yml``.
3. Expose a ``qdrant-cleanup`` target in the ``Makefile`` for operators.

All tests here are static (no Docker, no network).  They parse files and
YAML; they never start services.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
QDRANT_CONFIG = REPO_ROOT / "docker" / "qdrant" / "config.yaml"
COMPOSE_FILE = REPO_ROOT / "compose.yml"
MAKEFILE = REPO_ROOT / "Makefile"


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 1. Config file exists
***REMOVED*** ---------------------------------------------------------------------------


def test_qdrant_config_file_exists() -> None:
    """``docker/qdrant/config.yaml`` must exist (***REMOVED***1545)."""
    assert QDRANT_CONFIG.exists(), (
        f"Missing: {QDRANT_CONFIG}\n"
        "Create docker/qdrant/config.yaml with storage optimisation settings "
        "(on_disk_payload, indexing_threshold_kb) to fix issue ***REMOVED***1545."
    )


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 2. Config has a 'storage' section with required keys
***REMOVED*** ---------------------------------------------------------------------------


def test_qdrant_config_has_storage_section() -> None:
    """``docker/qdrant/config.yaml`` must contain a 'storage' key (***REMOVED***1545)."""
    assert QDRANT_CONFIG.exists(), "Prerequisite: docker/qdrant/config.yaml is missing."
    with QDRANT_CONFIG.open() as fh:
        cfg = yaml.safe_load(fh)
    assert isinstance(cfg, dict), "config.yaml must be a YAML mapping at the top level."
    assert "storage" in cfg, (
        "config.yaml must contain a top-level 'storage' key with at least "
        "'on_disk_payload: true' to reduce memory pressure (***REMOVED***1545)."
    )
    storage = cfg["storage"]
    assert isinstance(storage, dict), "'storage' must be a YAML mapping."
    assert "on_disk_payload" in storage, (
        "'storage.on_disk_payload' must be set to true in docker/qdrant/config.yaml "
        "so that payloads not needed for filtering are read from disk rather than RAM."
    )
    assert storage["on_disk_payload"] is True, (
        "'storage.on_disk_payload' must be true to move payload storage to disk "
        "and reduce the unbounded RAM / volume growth observed in ***REMOVED***1545."
    )


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 3. compose.yml mounts the config into the Qdrant container
***REMOVED*** ---------------------------------------------------------------------------


def test_qdrant_compose_mounts_config() -> None:
    """``compose.yml`` must mount ``docker/qdrant/config.yaml`` into the Qdrant service (***REMOVED***1545).

    Qdrant reads ``/qdrant/config/production.yaml`` when present, so we
    require that exact target path to be declared in the volumes list of the
    ``qdrant`` service.
    """
    assert COMPOSE_FILE.exists(), f"compose.yml not found at {COMPOSE_FILE}."
    with COMPOSE_FILE.open() as fh:
        compose = yaml.safe_load(fh)

    services = compose.get("services", {})
    assert "qdrant" in services, "Qdrant service not found in compose.yml."

    qdrant_service = services["qdrant"]
    volumes: list[str | dict] = qdrant_service.get("volumes", [])

    ***REMOVED*** Accept either short syntax ("./docker/qdrant/config.yaml:/qdrant/config/production.yaml:ro")
    ***REMOVED*** or long syntax (type: bind + source + target).
    config_source = "docker/qdrant/config.yaml"
    config_target = "/qdrant/config/production.yaml"

    found = False
    for vol in volumes:
        if isinstance(vol, str):
            if config_source in vol and config_target in vol:
                found = True
                break
        elif isinstance(vol, dict):
            src = vol.get("source", "")
            tgt = vol.get("target", "")
            if config_source in src and tgt == config_target:
                found = True
                break

    assert found, (
        f"The Qdrant service in compose.yml must mount '{config_source}' "
        f"to '{config_target}' so the storage optimisation config is picked up "
        "at runtime.  Add the volume entry to the qdrant service (***REMOVED***1545)."
    )


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 4. Makefile exposes a qdrant-cleanup target
***REMOVED*** ---------------------------------------------------------------------------


def test_makefile_has_qdrant_cleanup_target() -> None:
    """``Makefile`` must define a ``qdrant-cleanup`` target (***REMOVED***1545)."""
    assert MAKEFILE.exists(), f"Makefile not found at {MAKEFILE}."
    content = MAKEFILE.read_text(encoding="utf-8")
    assert "qdrant-cleanup" in content, (
        "Makefile is missing the 'qdrant-cleanup' target required by ***REMOVED***1545.  "
        "Add a target that helps operators prune stale Qdrant data."
    )
