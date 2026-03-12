"""Unit tests for scripts/index_services.py.

Tests cover:
- Parsing services.yaml → list of service dicts
- Building chunks from parsed services
- Deterministic point IDs (idempotency guarantee)
- Skipping services with empty/missing card_text
"""

from __future__ import annotations

import textwrap
import uuid
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers — import under test after path manipulation
# ---------------------------------------------------------------------------


def _get_module():
    """Import scripts/index_services module lazily."""
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "index_services",
        Path(__file__).parents[2] / "scripts" / "index_services.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["index_services"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_YAML = textwrap.dedent(
    """\
    services:
      passive_income:
        emoji: "💰"
        title: "Пассивный доход"
        callback_id: "svc:passive_income"
        card_text: |
          💰 Пассивный доход — сдаём вашу недвижимость

          Полный цикл управления.
      infotour:
        emoji: "✈️"
        title: "Инфотур"
        callback_id: "svc:infotour"
        card_text: |
          ✈️ Инфотур «Недвижимость в Болгарии»

          Акционная цена 150 евро.
      no_text_service:
        emoji: "❓"
        title: "Без текста"
        callback_id: "svc:no_text"
    """
)


@pytest.fixture()
def services_yaml_file(tmp_path: Path) -> Path:
    """Write sample YAML to a temp file and return path."""
    f = tmp_path / "services.yaml"
    f.write_text(SAMPLE_YAML, encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# parse_services_yaml
# ---------------------------------------------------------------------------


class TestParseServicesYaml:
    def test_returns_list_of_services(self, services_yaml_file: Path) -> None:
        mod = _get_module()
        result = mod.parse_services_yaml(services_yaml_file)
        # Only services WITH card_text are returned
        assert isinstance(result, list)
        assert len(result) == 2

    def test_service_has_required_fields(self, services_yaml_file: Path) -> None:
        mod = _get_module()
        result = mod.parse_services_yaml(services_yaml_file)
        first = result[0]
        assert "service_key" in first
        assert "title" in first
        assert "card_text" in first

    def test_service_key_matches_yaml_key(self, services_yaml_file: Path) -> None:
        mod = _get_module()
        result = mod.parse_services_yaml(services_yaml_file)
        keys = {s["service_key"] for s in result}
        assert "passive_income" in keys
        assert "infotour" in keys

    def test_skips_service_without_card_text(self, services_yaml_file: Path) -> None:
        mod = _get_module()
        result = mod.parse_services_yaml(services_yaml_file)
        keys = {s["service_key"] for s in result}
        assert "no_text_service" not in keys

    def test_card_text_not_empty(self, services_yaml_file: Path) -> None:
        mod = _get_module()
        result = mod.parse_services_yaml(services_yaml_file)
        for svc in result:
            assert svc["card_text"].strip() != ""

    def test_raises_on_missing_file(self, tmp_path: Path) -> None:
        mod = _get_module()
        with pytest.raises((FileNotFoundError, SystemExit)):
            mod.parse_services_yaml(tmp_path / "nonexistent.yaml")


# ---------------------------------------------------------------------------
# build_chunks
# ---------------------------------------------------------------------------


class TestBuildChunks:
    def test_returns_one_chunk_per_service(self, services_yaml_file: Path) -> None:
        mod = _get_module()
        services = mod.parse_services_yaml(services_yaml_file)
        chunks = mod.build_chunks(services)
        assert len(chunks) == len(services)

    def test_chunk_has_required_fields(self, services_yaml_file: Path) -> None:
        mod = _get_module()
        services = mod.parse_services_yaml(services_yaml_file)
        chunks = mod.build_chunks(services)
        for chunk in chunks:
            assert "id" in chunk
            assert "text" in chunk
            assert "service_key" in chunk
            assert "title" in chunk
            assert "source" in chunk

    def test_source_is_services_yaml(self, services_yaml_file: Path) -> None:
        mod = _get_module()
        services = mod.parse_services_yaml(services_yaml_file)
        chunks = mod.build_chunks(services)
        for chunk in chunks:
            assert chunk["source"] == "services.yaml"

    def test_text_contains_card_text(self, services_yaml_file: Path) -> None:
        mod = _get_module()
        services = mod.parse_services_yaml(services_yaml_file)
        chunks = mod.build_chunks(services)
        passive = next(c for c in chunks if c["service_key"] == "passive_income")
        assert "Пассивный доход" in passive["text"]


# ---------------------------------------------------------------------------
# Idempotency — deterministic IDs
# ---------------------------------------------------------------------------


class TestDeterministicIds:
    def test_same_input_produces_same_ids(self, services_yaml_file: Path) -> None:
        mod = _get_module()
        services = mod.parse_services_yaml(services_yaml_file)
        chunks1 = mod.build_chunks(services)
        chunks2 = mod.build_chunks(services)
        ids1 = [c["id"] for c in chunks1]
        ids2 = [c["id"] for c in chunks2]
        assert ids1 == ids2

    def test_ids_are_valid_uuids(self, services_yaml_file: Path) -> None:
        mod = _get_module()
        services = mod.parse_services_yaml(services_yaml_file)
        chunks = mod.build_chunks(services)
        for chunk in chunks:
            parsed = uuid.UUID(chunk["id"])
            assert parsed.version == 5

    def test_different_services_have_different_ids(self, services_yaml_file: Path) -> None:
        mod = _get_module()
        services = mod.parse_services_yaml(services_yaml_file)
        chunks = mod.build_chunks(services)
        ids = [c["id"] for c in chunks]
        assert len(ids) == len(set(ids)), "All chunk IDs must be unique"


# ---------------------------------------------------------------------------
# build_points — PointStruct construction (no network calls)
# ---------------------------------------------------------------------------


class TestBuildPoints:
    def test_build_points_returns_correct_count(self, services_yaml_file: Path) -> None:
        mod = _get_module()
        services = mod.parse_services_yaml(services_yaml_file)
        chunks = mod.build_chunks(services)

        # Fake embeddings matching chunk count
        n = len(chunks)
        fake_embeddings = {
            "dense": [[0.1] * 4 for _ in range(n)],
            "sparse": [{"indices": [0, 1], "values": [0.5, 0.5]} for _ in range(n)],
            "colbert": [[[0.1] * 4] for _ in range(n)],
        }
        points = mod.build_points(chunks, fake_embeddings)
        assert len(points) == n

    def test_build_points_uses_chunk_ids(self, services_yaml_file: Path) -> None:
        mod = _get_module()
        services = mod.parse_services_yaml(services_yaml_file)
        chunks = mod.build_chunks(services)

        n = len(chunks)
        fake_embeddings = {
            "dense": [[0.1] * 4 for _ in range(n)],
            "sparse": [{"indices": [0], "values": [1.0]} for _ in range(n)],
            "colbert": [[[0.1] * 4] for _ in range(n)],
        }
        points = mod.build_points(chunks, fake_embeddings)
        point_ids = {str(p.id) for p in points}
        chunk_ids = {c["id"] for c in chunks}
        assert point_ids == chunk_ids

    def test_build_points_payload_has_source(self, services_yaml_file: Path) -> None:
        mod = _get_module()
        services = mod.parse_services_yaml(services_yaml_file)
        chunks = mod.build_chunks(services)

        n = len(chunks)
        fake_embeddings = {
            "dense": [[0.1] * 4 for _ in range(n)],
            "sparse": [{"indices": [0], "values": [1.0]} for _ in range(n)],
            "colbert": [[[0.1] * 4] for _ in range(n)],
        }
        points = mod.build_points(chunks, fake_embeddings)
        for p in points:
            assert p.payload is not None
            assert p.payload.get("metadata", {}).get("source") == "services.yaml"
