import json
from pathlib import Path


ROOT = Path(__file__).parents[3]
PACKAGE_JSON = ROOT / "mini_app/frontend/package.json"
PACKAGE_LOCK = ROOT / "mini_app/frontend/package-lock.json"
DOCKERFILE = ROOT / "mini_app/frontend/Dockerfile"
NODE_FLOOR = "^20.19.0 || >=22.12.0"


def test_frontend_package_declares_supported_node_floor() -> None:
    data = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    assert data["engines"]["node"] == NODE_FLOOR


def test_frontend_lockfile_records_supported_node_floor() -> None:
    data = json.loads(PACKAGE_LOCK.read_text(encoding="utf-8"))
    assert data["packages"][""]["engines"]["node"] == NODE_FLOOR


def test_frontend_builder_pins_supported_node_floor() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "FROM node:20.19.0-slim AS builder" in text
