"""Contract: Python runtime version matrix — guards intentional drift (#2623).

Supported Python matrix
-----------------------
| Component            | requires-python | Docker runtime | Justification                         |
|----------------------|-----------------|----------------|---------------------------------------|
| root / core / ingest | >=3.12          | 3.13           | Langfuse/pydantic.v1 compat; uv floor |
| telegram_bot         | >=3.12          | 3.13           | Langfuse/pydantic.v1 compat           |
| services/bge-m3-api  | (no pyproject)  | 3.14           | Independent ML service; no Langfuse   |

This contract fails on:
- root requires-python below 3.12
- telegram_bot requires-python below 3.12

The Langfuse-importing Docker runtime constraint (>=3.13) is enforced by
``test_dockerfile_runtime_policy_contract.py``. This contract covers the
pyproject-level floor only.

Note: services/docling was removed in the Docling migration (phase_6508bc74ca4a);
its pyproject.toml row has been dropped from this matrix.
"""

from __future__ import annotations

import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

# Documented minimum Python floors per component
ROOT_REQUIRES_PYTHON_FLOOR = "3.12"
BOT_REQUIRES_PYTHON_FLOOR = "3.12"


def _load_toml(rel: str) -> dict:
    path = REPO_ROOT / rel
    assert path.is_file(), f"{rel} not found at {path}"
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _extract_floor(requires_python: str) -> str:
    """Extract version floor from requires-python string like '>=3.12'."""
    return requires_python.replace(">=", "").strip()


def test_root_requires_python_floor() -> None:
    """Root pyproject.toml requires-python must be >= 3.12 (#2623)."""
    data = _load_toml("pyproject.toml")
    requires = data["project"]["requires-python"]
    floor = _extract_floor(requires)
    assert floor >= ROOT_REQUIRES_PYTHON_FLOOR, (
        f"root pyproject.toml requires-python={requires!r}; "
        f"must be >={ROOT_REQUIRES_PYTHON_FLOOR} (#2623)"
    )


def test_bot_requires_python_floor() -> None:
    """telegram_bot/pyproject.toml requires-python must be >= 3.12 (#2623)."""
    data = _load_toml("telegram_bot/pyproject.toml")
    requires = data["project"]["requires-python"]
    floor = _extract_floor(requires)
    assert floor >= BOT_REQUIRES_PYTHON_FLOOR, (
        f"telegram_bot/pyproject.toml requires-python={requires!r}; "
        f"must be >={BOT_REQUIRES_PYTHON_FLOOR} (#2623)"
    )


def test_python_version_file() -> None:
    """.python-version must be 3.12 (local dev floor matches matrix)."""
    path = REPO_ROOT / ".python-version"
    assert path.is_file(), ".python-version not found"
    version = path.read_text(encoding="utf-8").strip()
    assert version.startswith("3.12"), (
        f".python-version={version!r}; must be 3.12.x to match matrix floor (#2623)"
    )
